from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import Dict, Any
import json
import logging

from app.db.database import get_db
from app.db.models import TransactionRecord
from app.core.model_state import model_state
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["Metrics"])

@router.get("")
async def get_metrics(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    # 1. DB latency percentiles and counts (live demo stream)
    # Using approx_percentile or similar in postgres, but for simplicity we can do a quick scalar or basic percentile
    # For exact percentiles in postgres 16: percentile_cont
    
    latency_query = """
    SELECT 
        COUNT(id) as total_tx,
        COUNT(id) FILTER (WHERE review_status = 'PENDING' AND decision = 'REVIEW') as review_queue_size,
        COUNT(id) FILTER (WHERE review_status = 'FRAUD' AND decision = 'BLOCK') as true_positives,
        COUNT(id) FILTER (WHERE review_status = 'FALSE_POSITIVE' AND decision = 'BLOCK') as false_positives,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) as p50_latency,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_latency
    FROM transactions
    """
    
    # We execute raw sql
    from sqlalchemy import text
    result = await db.execute(text(latency_query))
    row = result.fetchone()
    
    total_tx = row[0] or 0
    review_queue_size = row[1] or 0
    tp = row[2] or 0
    fp = row[3] or 0
    analyst_precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    
    p50 = row[4] or 0.0
    p95 = row[5] or 0.0
    
    # Also get counts by decision
    dec_result = await db.execute(select(TransactionRecord.decision, func.count(TransactionRecord.id)).group_by(TransactionRecord.decision))
    decision_counts = dict(dec_result.all())
    
    # 2. Holdout metrics from artifacts
    holdout_metrics = {}
    try:
        import urllib.request
        from pathlib import Path
        holdout_path = Path(settings.MODEL_META_PATH).parent / "holdout_result.json"
        if holdout_path.exists():
            with open(holdout_path, "r") as f:
                d = json.load(f)
                lgbm = d.get("holdout", {}).get("lightgbm_tuned", {})
                holdout_metrics = {
                    "pr_auc": lgbm.get("pr_auc"),
                    "roc_auc": lgbm.get("roc_auc"),
                    "recall_at_1_fpr": lgbm.get("recall_at_fpr"),
                    "precision": lgbm.get("precision_at_thr"),
                }
    except Exception as e:
        logger.error(f"Failed to load holdout metrics: {e}")
        
    # 3. Cost curve / PR curve points
    pr_curve = []
    try:
        from pathlib import Path
        curve_path = Path(settings.MODEL_META_PATH).parent / "cost_curve.json"
        if curve_path.exists():
            with open(curve_path, "r") as f:
                c = json.load(f)
                # Ensure we have recall and precision arrays
                if "curve" in c:
                    pr_curve = c["curve"]
    except Exception as e:
        logger.error(f"Failed to load PR curve: {e}")
    
    thresholds = {}
    if model_state.is_loaded:
        thresholds = {
            "approve_max": getattr(model_state.thresholds, "approve_max", None) or 0.0015,
            "review_max": getattr(model_state.thresholds, "review_max", None) or 0.0145
        }
        
    return {
        "live_demo_stream": {
            "total_transactions": total_tx,
            "decision_counts": decision_counts,
            "p50_latency_ms": round(p50, 2),
            "p95_latency_ms": round(p95, 2),
            "review_queue_size": review_queue_size,
            "analyst_confirmed_precision": round(analyst_precision, 4)
        },
        "holdout_natural_rate": holdout_metrics,
        "pr_curve": pr_curve,
        "thresholds": thresholds
    }
