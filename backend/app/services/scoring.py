"""Core scoring service — the single place where every decision is made.

Both the API (POST /score) and the simulator (Phase 6) call score_transaction().
That means there is exactly one scoring path in the whole system.

Pipeline (per request):
    1. Build a one-row DataFrame from the raw request fields
    2. Run through the shared feature module (encoders + stateless + stateful store)
    3. Align to the trained feature order
    4. LightGBM raw score → sigmoid calibrator → risk score (0-100)
    5. SHAP values → ReasonMap → human-readable reasons
    6. Apply thresholds → Approve / Review / Block
    7. Return ScoreResponse (latency measured around steps 1-6)
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any

import numpy as np
import pandas as pd

from app.core.model_state import ModelState
from app.features import (
    CARD_COLS, CardHistoryStore, FeatureEncoders,
    add_stateless_features, encoded_feature_names,
)
from app.features.build import PASSTHROUGH_BASE, STORE_INPUT_COLS
from app.features.transforms import D_COLS, ID_NUM_COLS
from app.schemas.score import Reason, ScoreRequest, ScoreResponse

# ---------------------------------------------------------------------------
# Field registry: everything the request carries that can become a feature
# ---------------------------------------------------------------------------

# All raw fields the model knows about (passthrough + encoded + stateful inputs).
_ALL_KNOWN_COLS = (
    ["TransactionID", "TransactionDT", "TransactionAmt"]
    + CARD_COLS
    + PASSTHROUGH_BASE
    + ["dist1", "dist2"]
    + [f"C{i}" for i in range(1, 15)]
    + D_COLS
    + [f"V{i}" for i in range(1, 340)]
    + ID_NUM_COLS
    + ["id_30", "id_31", "id_33"]
    + ["ProductCD", "card4", "card6", "DeviceType", "DeviceInfo"]
    + ["P_emaildomain", "R_emaildomain"]
    + [f"M{i}" for i in range(1, 10)]
)


def _request_to_df(req: ScoreRequest) -> pd.DataFrame:
    """Convert a ScoreRequest into a one-row DataFrame that the feature module can consume."""
    raw: dict[str, Any] = {}

    # Fields from the request (use __dict__ to avoid Pydantic exclusion magic)
    for field in req.__class__.model_fields:
        if field in ("transaction_id", "what_if"):
            continue
        raw[field] = getattr(req, field)

    # Synthetic TransactionID (needed by replay() for tie-breaking sort)
    raw["TransactionID"] = 0

    # has_identity: the API doesn't receive identity-table columns, so mark as 0
    # (the model handles this gracefully)
    raw["has_identity"] = 0

    # Build single-row DataFrame; fill every column the module might look up
    row = {col: raw.get(col, None) for col in _ALL_KNOWN_COLS}
    row["has_identity"] = 0

    df = pd.DataFrame([row])
    return df


def _build_feature_vector(
    req: ScoreRequest,
    encoders: FeatureEncoders,
    card_store: CardHistoryStore,
) -> tuple[np.ndarray, pd.DataFrame, list[str]]:
    """Return (feature_vector float32 array, feature_df, feature_names)."""
    df = _request_to_df(req)

    # 1. Passthrough columns (raw numerics)
    from app.features.build import passthrough_columns
    passthrough_df = df[passthrough_columns(df.columns)].astype("float32")

    # 2. Stateless features
    stateless_df = add_stateless_features(df).astype("float32")

    # 3. Encoded categoricals
    encoded_df = encoders.transform(df).astype("float32")

    # 4. Stateful features (velocity, novelty) — uses or skips update based on what_if
    store_input = {c: (None if (v := getattr(req, c, None)) is None else v)
                   for c in STORE_INPUT_COLS}
    store_input["TransactionDT"] = req.TransactionDT
    store_input["TransactionAmt"] = req.TransactionAmt
    stateful_row = card_store.process(store_input, update=not req.what_if)
    from app.features.store import STATEFUL_FEATURES
    stateful_df = pd.DataFrame([stateful_row], columns=STATEFUL_FEATURES).astype("float32")

    # 5. Concatenate
    feature_df = pd.concat([passthrough_df, stateless_df, encoded_df, stateful_df], axis=1)
    return feature_df, list(feature_df.columns)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_transaction(req: ScoreRequest, state: ModelState) -> ScoreResponse:
    """Full pipeline: request → features → model → SHAP → decision → response."""
    t_start = time.perf_counter()

    # ── assign or keep transaction_id ────────────────────────────────────────
    tx_id = req.transaction_id or f"tx_{uuid.uuid4().hex[:12]}"

    # ── build features ───────────────────────────────────────────────────────
    feature_df, feature_names = _build_feature_vector(req, state.encoders, state.card_store)
    feature_row = state.align_feature_row(feature_df)          # aligned float32 array

    # ── model inference ──────────────────────────────────────────────────────
    raw_score, calib_prob = state.score_one(feature_row)
    risk_score = state.thresholds.to_risk_score(calib_prob)
    decision = state.thresholds.decide(raw_score)

    # ── SHAP → reasons ────────────────────────────────────────────────────────
    shap_vals = state.shap_values(feature_row)

    # Values visible to the reason formatter (aligned to feature_order)
    feature_order = state.feature_order
    aligned_values = feature_df.reindex(columns=feature_order, fill_value=math.nan).to_numpy(dtype="float64")[0]

    reasons_raw = state.reason_map.explain(
        features=feature_order,
        values=aligned_values.tolist(),
        contribs=shap_vals.tolist(),
    )
    reasons = [
        Reason(text=r["text"], contribution=r["contribution"], kind=r.get("kind", "specific"))
        for r in reasons_raw
    ]

    # ── latency ──────────────────────────────────────────────────────────────
    latency_ms = (time.perf_counter() - t_start) * 1000.0

    return ScoreResponse(
        transaction_id=tx_id,
        score=risk_score,
        decision=decision,
        reasons=reasons,
        calibrated_prob=calib_prob,
        raw_score=raw_score,
        latency_ms=round(latency_ms, 2),
        what_if=req.what_if,
    )
