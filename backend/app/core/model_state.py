"""Model + artefact loader — called ONCE at FastAPI startup.

Everything expensive (LightGBM model, SHAP explainer, CardHistoryStore warm-up)
happens here so that individual requests pay zero startup cost.
"""
from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap

from app.core.config import settings
from app.features import CardHistoryStore, FeatureEncoders

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------

class _SigmoidCalibrator:
    """Platt sigmoid: calibrated_prob = 1 / (1 + exp(a * raw + b))."""

    def __init__(self, a: float, b: float):
        self.a = a
        self.b = b

    def predict_proba(self, raw_scores: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(self.a * raw_scores + self.b))

    @classmethod
    def from_json(cls, path: Path) -> "_SigmoidCalibrator":
        data = json.loads(path.read_text())
        if data.get("method") != "sigmoid":
            raise ValueError(f"Unsupported calibration method: {data.get('method')}")
        return cls(a=float(data["a"]), b=float(data["b"]))


# ---------------------------------------------------------------------------
# Threshold helper
# ---------------------------------------------------------------------------

class Thresholds:
    def __init__(self, review_raw: float, block_raw: float):
        self.review_raw = review_raw
        self.block_raw = block_raw

    def decide(self, raw_score: float) -> str:
        if raw_score >= self.block_raw:
            return "BLOCK"
        if raw_score >= self.review_raw:
            return "REVIEW"
        return "APPROVE"

    def to_risk_score(self, calibrated_prob: float) -> int:
        """Map calibrated probability → integer 0–100 risk score."""
        return min(100, max(0, round(calibrated_prob * 100)))

    @classmethod
    def from_json(cls, path: Path) -> "Thresholds":
        data = json.loads(path.read_text())
        return cls(
            review_raw=float(data["review_threshold_raw"]),
            block_raw=float(data["block_threshold_raw"]),
        )


# ---------------------------------------------------------------------------
# The singleton model state
# ---------------------------------------------------------------------------

class ModelState:
    """Holds everything that survives across requests."""

    def __init__(self):
        self.booster: lgb.Booster | None = None
        self.explainer: shap.TreeExplainer | None = None
        self.calibrator: _SigmoidCalibrator | None = None
        self.encoders: FeatureEncoders | None = None
        self.feature_order: list[str] | None = None
        self.thresholds: Thresholds | None = None
        self.reason_map: "Any | None" = None   # ReasonMap; imported lazily in load()
        self.card_store: CardHistoryStore | None = None
        self.meta: dict[str, Any] = {}
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load all artefacts. Call once at startup (not per request)."""
        t0 = time.perf_counter()
        logger.info("Loading ML artefacts …")

        # 1. Feature schema (gives us the column order the model expects)
        schema = json.loads(settings.FEATURE_SCHEMA_PATH.read_text())
        self.feature_order = schema["feature_order"]

        # 2. LightGBM booster
        self.booster = lgb.Booster(model_file=str(settings.MODEL_PATH))
        logger.info("Booster loaded: %d trees, %d features",
                    self.booster.num_trees(), len(self.feature_order))

        # 3. SHAP TreeExplainer (fast, exact for tree ensembles)
        self.explainer = shap.TreeExplainer(self.booster)

        # 4. Calibrator
        self.calibrator = _SigmoidCalibrator.from_json(settings.CALIBRATOR_PATH)

        # 5. Categorical encoders
        self.encoders = FeatureEncoders.from_json(settings.ENCODERS_PATH)

        # 6. Thresholds
        self.thresholds = Thresholds.from_json(settings.THRESHOLDS_PATH)

        # 7. Reason map (imported here to avoid circular import at module level)
        from app.services.reasons import ReasonMap as _ReasonMap  # noqa: PLC0415
        self.reason_map = _ReasonMap.from_json(settings.REASON_MAP_PATH)

        # 8. Card history store (initially empty; warm-up happens separately)
        self.card_store = CardHistoryStore()

        # 9. Model metadata (for /health and /metrics)
        self.meta = json.loads(settings.MODEL_META_PATH.read_text())

        self._loaded = True
        elapsed = time.perf_counter() - t0
        logger.info("All artefacts loaded in %.2f s", elapsed)

    # ------------------------------------------------------------------
    def score_one(self, feature_row: np.ndarray) -> tuple[float, float]:
        """Return (raw_score, calibrated_prob) for a single feature vector."""
        assert self._loaded, "ModelState.load() must be called before scoring"
        raw = float(self.booster.predict(feature_row.reshape(1, -1))[0])
        prob = float(self.calibrator.predict_proba(np.array([raw]))[0])
        return raw, prob

    def shap_values(self, feature_row: np.ndarray) -> np.ndarray:
        """Return SHAP values (log-odds, without bias) for a single row."""
        assert self._loaded
        sv = self.explainer.shap_values(feature_row.reshape(1, -1))
        # shap_values may return ndarray or list (multiclass) — always take [0]
        if isinstance(sv, list):
            sv = sv[1] if len(sv) > 1 else sv[0]
        return sv[0]   # shape (n_features,)

    def align_feature_row(self, feature_df: pd.DataFrame) -> np.ndarray:
        """Re-order / fill-missing columns to match the trained feature order."""
        aligned = feature_df.reindex(columns=self.feature_order, fill_value=math.nan)
        return aligned.to_numpy(dtype="float32")[0]


# Singleton — imported by the FastAPI app and routers.
model_state = ModelState()
