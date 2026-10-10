"""GET /metrics — live stream stats from PostgreSQL plus offline evaluation from ml/artifacts.

Offline sections come from files written by the training notebooks / scripts:

* holdout_result.json         → threshold-free holdout metrics (PR-AUC, ROC-AUC, recall @ 1% FPR, calibration)
* phase4_holdout_result.json  → decision bands, cost savings, bootstrap CI, strategy comparison
* cost_curve.json             → recall / precision / cost at each flag rate (PR curve + cost-vs-threshold)
* thresholds.json             → review / block thresholds (raw and 0–100 risk score)
* shap_global.json            → global feature importance
* model_meta.json             → version, trees, features, validation metrics

Artifacts are read once and cached; restart the API after retraining.
"""
from __future__ import annotations

import json
import logging
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.model_state import model_state
from app.db.database import get_db
from app.db.models import TransactionRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["Metrics"])

_ARTIFACTS = Path(settings.MODEL_META_PATH).parent
_TOP_FEATURES = 15


def _clean(v: Any) -> Any:
    """NaN / ±inf → None, recursively. cost_curve.json has NaN precision at k=0, and
    Starlette's JSONResponse refuses non-finite floats."""
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def _pct(v: float | None) -> float | None:
    """phase4 `reference` rows store savings in percent; every other ratio here is a fraction."""
    return None if v is None else v / 100


def _read(name: str) -> dict:
    path = _ARTIFACTS / name
    if not path.exists():
        logger.warning("Metrics artifact missing: %s", path)
        return {}
    try:
        # json.load accepts the NaN literals Python's json.dump writes.
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to read %s: %s", path, e)
        return {}


@lru_cache(maxsize=1)
def _offline() -> dict:
    holdout = _read("holdout_result.json")
    phase4 = _read("phase4_holdout_result.json")
    curve = _read("cost_curve.json")
    thr = _read("thresholds.json")
    shap_global = _read("shap_global.json")
    meta = _read("model_meta.json")

    lgbm = holdout.get("holdout", {}).get("lightgbm_tuned", {})
    baseline = holdout.get("holdout", {}).get("logreg", {})
    p4 = phase4.get("holdout", {})

    def curve_points(split: str) -> list[dict]:
        keep = ("flagged_share", "threshold", "risk_score", "recall", "precision", "cost", "savings")
        return [{k: p.get(k) for k in keep} for p in curve.get(split, [])]

    return _clean({
        "holdout_natural_rate": {
            "n": lgbm.get("n"),
            "fraud_rate": lgbm.get("fraud_rate"),
            "pr_auc": lgbm.get("pr_auc"),
            "roc_auc": lgbm.get("roc_auc"),
            "recall_at_1_fpr": lgbm.get("recall_at_fpr"),
            "precision_at_1_fpr": lgbm.get("precision_at_fpr"),
            "fpr_target": holdout.get("fpr_target"),
            # At the validation-chosen 1%-FPR threshold, applied to holdout.
            "precision": lgbm.get("precision_at_thr"),
            "recall": lgbm.get("recall_at_thr"),
            "fpr": lgbm.get("fpr_at_thr"),
            "calibration": lgbm.get("calibration", {}),
            "baseline_logreg": {
                "pr_auc": baseline.get("pr_auc"),
                "roc_auc": baseline.get("roc_auc"),
                "recall_at_1_fpr": baseline.get("recall_at_fpr"),
            },
        },
        "bands": p4.get("bands") or thr.get("holdout", {}).get("bands", {}),
        "cost": {
            "model": phase4.get("cost_model") or curve.get("cost_model", {}),
            "savings": p4.get("savings"),
            "savings_pct": p4.get("savings_pct"),
            "savings_pct_90ci": phase4.get("bootstrap", {}).get("savings_pct_90ci"),
            "savings_per_100k_txns": p4.get("savings_per_100k_txns"),
            "cost_total": p4.get("cost_total"),
            "cost_approve_all": p4.get("cost_approve_all"),
            "breakdown": p4.get("breakdown", {}),
            "recall_review_or_block": p4.get("recall_review_or_block"),
            "recall_block_only": p4.get("recall_block_only"),
            "strategies": [
                {"name": r.get("index"), "cost": r.get("cost"), "savings_pct": _pct(r.get("savings_vs_approve_all_%"))}
                for r in phase4.get("reference", [])
            ],
        },
        "curves": {"validation": curve_points("validation"), "holdout": curve_points("holdout")},
        "thresholds_file": {
            "review_risk_score": thr.get("review_risk_score"),
            "block_risk_score": thr.get("block_risk_score"),
            "review_capacity_cap": thr.get("review_capacity_cap"),
        },
        "top_features": shap_global.get("top_features", [])[:_TOP_FEATURES],
        "model": {
            "version": meta.get("version"),
            "trained_at_utc": meta.get("trained_at_utc"),
            "model_type": meta.get("model_type"),
            "calibration_method": meta.get("calibration_method"),
            "n_trees": meta.get("n_trees"),
            "n_features": meta.get("n_features"),
            "validation": meta.get("metrics", {}).get("validation", {}),
        },
    })


_LIVE_SQL = text("""
SELECT
    COUNT(id)                                                                   AS total_tx,
    COUNT(id) FILTER (WHERE review_status = 'PENDING' AND decision = 'REVIEW')  AS review_queue_size,
    COUNT(id) FILTER (WHERE review_status = 'FRAUD')                            AS analyst_fraud,
    COUNT(id) FILTER (WHERE review_status = 'FALSE_POSITIVE')                   AS analyst_fp,
    percentile_cont(0.5)  WITHIN GROUP (ORDER BY latency_ms)                    AS p50_latency,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)                    AS p95_latency,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms)                    AS p99_latency,
    COUNT(id) FILTER (WHERE true_label IS NOT NULL)                             AS labelled,
    COUNT(id) FILTER (WHERE true_label)                                         AS fraud,
    COUNT(id) FILTER (WHERE true_label AND decision <> 'APPROVE')               AS tp_flagged,
    COUNT(id) FILTER (WHERE true_label IS FALSE AND decision <> 'APPROVE')      AS fp_flagged,
    COUNT(id) FILTER (WHERE true_label AND decision = 'BLOCK')                  AS tp_block,
    COUNT(id) FILTER (WHERE true_label IS FALSE AND decision = 'BLOCK')         AS fp_block,
    MIN(created_at)                                                             AS first_at,
    MAX(created_at)                                                             AS last_at
FROM transactions
""")


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 4) if b else None


@router.get("")
async def get_metrics(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = (await db.execute(_LIVE_SQL)).mappings().one()

    dec_result = await db.execute(
        select(TransactionRecord.decision, func.count(TransactionRecord.id)).group_by(TransactionRecord.decision)
    )
    decision_counts = {"APPROVE": 0, "REVIEW": 0, "BLOCK": 0, **dict(dec_result.all())}

    n = lambda k: int(row[k] or 0)  # noqa: E731
    flagged_labelled = n("tp_flagged") + n("fp_flagged")
    block_labelled = n("tp_block") + n("fp_block")

    offline = _offline()

    # Live thresholds from the loaded model; fall back to the file when the model isn't up.
    thresholds: dict[str, Any] = dict(offline["thresholds_file"])
    if model_state.is_loaded and model_state.thresholds is not None:
        thresholds["review_raw"] = model_state.thresholds.review_raw
        thresholds["block_raw"] = model_state.thresholds.block_raw

    return _clean({
        "live_demo_stream": {
            "total_transactions": n("total_tx"),
            "decision_counts": decision_counts,
            "p50_latency_ms": round(row["p50_latency"] or 0.0, 2),
            "p95_latency_ms": round(row["p95_latency"] or 0.0, 2),
            "p99_latency_ms": round(row["p99_latency"] or 0.0, 2),
            "review_queue_size": n("review_queue_size"),
            "analyst_reviewed": n("analyst_fraud") + n("analyst_fp"),
            "analyst_confirmed_precision": _ratio(n("analyst_fraud"), n("analyst_fraud") + n("analyst_fp")) or 0.0,
            "first_at": row["first_at"].isoformat() if row["first_at"] else None,
            "last_at": row["last_at"].isoformat() if row["last_at"] else None,
            # Simulated rows carry the holdout label; the stream is downsampled to ~5% fraud,
            # so precision here runs higher than at the natural 3.5% rate.
            "ground_truth": {
                "labelled": n("labelled"),
                "fraud": n("fraud"),
                "flagged_true_positive": n("tp_flagged"),
                "flagged_false_positive": n("fp_flagged"),
                "precision_flagged": _ratio(n("tp_flagged"), flagged_labelled),
                "recall_flagged": _ratio(n("tp_flagged"), n("fraud")),
                "precision_block": _ratio(n("tp_block"), block_labelled),
                "recall_block": _ratio(n("tp_block"), n("fraud")),
            },
        },
        "holdout_natural_rate": offline["holdout_natural_rate"],
        "bands": offline["bands"],
        "cost": offline["cost"],
        # Kept for older clients: the holdout recall / precision / cost curve.
        "pr_curve": offline["curves"]["holdout"],
        "curves": offline["curves"],
        "thresholds": thresholds,
        "top_features": offline["top_features"],
        "model": offline["model"],
    })
