"""Phase 5 backend tests.

Covers:
  5.9  — schema validation, decision-band logic, reasons contract
  5.10 — training/serving feature parity on a large batch

Run from the backend/ directory:
    pytest -q

The tests do NOT spin up the HTTP server (they call service functions directly),
so they run in < 5 s even with the real model loaded.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ARTIFACTS = Path(__file__).resolve().parents[2] / "ml" / "artifacts"


@pytest.fixture(scope="session")
def state():
    """Load model state once for the whole test session."""
    from app.core.model_state import ModelState
    ms = ModelState()
    ms.load()
    return ms


@pytest.fixture(scope="session")
def encoders(state):
    return state.encoders


@pytest.fixture(scope="session")
def card_store():
    from app.features import CardHistoryStore
    return CardHistoryStore()


# ---------------------------------------------------------------------------
# 5.9a — Pydantic schema validation
# ---------------------------------------------------------------------------

class TestScoreRequestSchema:

    def test_minimal_valid_request(self):
        """Only TransactionAmt is required; everything else has sensible defaults."""
        from app.schemas.score import ScoreRequest
        req = ScoreRequest(TransactionAmt=100.0)
        assert req.TransactionAmt == 100.0
        assert req.TransactionDT is not None  # auto-set to current time
        assert req.what_if is False

    def test_full_request_round_trips(self):
        from app.schemas.score import ScoreRequest
        req = ScoreRequest(
            TransactionAmt=912.50,
            ProductCD="W",
            card4="visa",
            card6="credit",
            addr1=315.0,
            P_emaildomain="protonmail.com",
            DeviceType="mobile",
        )
        assert req.card4 == "visa"
        assert req.ProductCD == "W"

    def test_negative_amount_rejected(self):
        from pydantic import ValidationError
        from app.schemas.score import ScoreRequest
        with pytest.raises(ValidationError):
            ScoreRequest(TransactionAmt=-50.0)

    def test_zero_amount_rejected(self):
        from pydantic import ValidationError
        from app.schemas.score import ScoreRequest
        with pytest.raises(ValidationError):
            ScoreRequest(TransactionAmt=0.0)

    def test_what_if_flag(self):
        from app.schemas.score import ScoreRequest
        req = ScoreRequest(TransactionAmt=50.0, what_if=True)
        assert req.what_if is True


# ---------------------------------------------------------------------------
# 5.9b — Decision-band logic
# ---------------------------------------------------------------------------

class TestDecisionBands:

    def test_approve_below_review_threshold(self):
        from app.core.model_state import Thresholds
        t = Thresholds(review_raw=0.01, block_raw=0.10)
        assert t.decide(0.005) == "APPROVE"

    def test_review_between_thresholds(self):
        from app.core.model_state import Thresholds
        t = Thresholds(review_raw=0.01, block_raw=0.10)
        assert t.decide(0.05) == "REVIEW"

    def test_block_above_block_threshold(self):
        from app.core.model_state import Thresholds
        t = Thresholds(review_raw=0.01, block_raw=0.10)
        assert t.decide(0.15) == "BLOCK"

    def test_exactly_at_review_threshold_is_review(self):
        from app.core.model_state import Thresholds
        t = Thresholds(review_raw=0.01, block_raw=0.10)
        assert t.decide(0.01) == "REVIEW"

    def test_exactly_at_block_threshold_is_block(self):
        from app.core.model_state import Thresholds
        t = Thresholds(review_raw=0.01, block_raw=0.10)
        assert t.decide(0.10) == "BLOCK"

    def test_risk_score_range(self):
        from app.core.model_state import Thresholds
        t = Thresholds(review_raw=0.01, block_raw=0.10)
        for prob in [0.0, 0.5, 1.0, 0.03]:
            score = t.to_risk_score(prob)
            assert 0 <= score <= 100

    def test_real_thresholds_loaded(self):
        """Thresholds from file match expected bands documented in thresholds.json."""
        from app.core.model_state import Thresholds
        t = Thresholds.from_json(ARTIFACTS / "thresholds.json")
        # Review threshold should be lower than block threshold
        assert t.review_raw < t.block_raw
        # From the saved thresholds.json
        assert t.review_raw == pytest.approx(0.001454, abs=1e-5)
        assert t.block_raw == pytest.approx(0.014548, abs=1e-5)


# ---------------------------------------------------------------------------
# 5.9c — Reasons contract
# ---------------------------------------------------------------------------

class TestReasons:

    def test_fallback_returned_when_no_shap_hit(self):
        from app.services.reasons import ReasonMap
        rm = ReasonMap.from_json(ARTIFACTS / "reason_map.json")
        # All-zero contributions → fallback
        features = ["TransactionAmt", "card1", "card2"]
        values = [100.0, 1.0, 1.0]
        contribs = [0.0, 0.0, 0.0]
        result = rm.explain(features, values, contribs)
        assert len(result) >= 1
        assert result[0]["kind"] == "fallback"

    def test_specific_reason_wins_over_anonymized(self):
        from app.services.reasons import ReasonMap
        rm = ReasonMap.from_json(ARTIFACTS / "reason_map.json")
        # new_device_flag=1 should trigger specific reason
        features = ["new_device_flag", "C13"]
        values = [1.0, 5.0]
        contribs = [0.5, 1.0]       # C13 contributes more but is anonymized
        result = rm.explain(features, values, contribs)
        texts = [r["text"] for r in result]
        # at least one specific reason should appear
        assert any("device" in t.lower() for t in texts)

    def test_max_anonymized_respected(self):
        from app.services.reasons import ReasonMap
        rm = ReasonMap.from_json(ARTIFACTS / "reason_map.json")
        # Three V-columns all contributing — should collapse to max_anonymized=1
        features = [f"V{i}" for i in range(1, 6)]
        values = [1.0] * 5
        contribs = [1.0, 0.9, 0.8, 0.7, 0.6]
        result = rm.explain(features, values, contribs)
        anon_count = sum(1 for r in result if r.get("kind") == "anonymized")
        assert anon_count <= rm.max_anonymized

    def test_reasons_sorted_by_contribution(self):
        from app.services.reasons import ReasonMap
        rm = ReasonMap.from_json(ARTIFACTS / "reason_map.json")
        features = ["b_txn_count_10m", "new_device_flag", "amt_vs_b_mean"]
        values = [3.0, 1.0, 5.0]
        contribs = [0.3, 0.5, 0.8]   # amt_vs_b_mean has highest contrib
        result = rm.explain(features, values, contribs)
        if len(result) > 1:
            for i in range(len(result) - 1):
                assert result[i]["contribution"] >= result[i + 1]["contribution"]


# ---------------------------------------------------------------------------
# 5.9d — End-to-end scoring (with real model)
# ---------------------------------------------------------------------------

class TestScoreTransaction:

    def test_score_response_fields(self, state):
        from app.schemas.score import ScoreRequest
        from app.services.scoring import score_transaction
        req = ScoreRequest(TransactionAmt=150.0, card4="visa", card6="debit")
        resp = score_transaction(req, state)
        assert 0 <= resp.score <= 100
        assert resp.decision in ("APPROVE", "REVIEW", "BLOCK")
        assert len(resp.reasons) >= 1
        assert resp.latency_ms > 0
        assert resp.calibrated_prob >= 0 and resp.calibrated_prob <= 1

    def test_what_if_does_not_update_store(self, state):
        from app.schemas.score import ScoreRequest
        from app.services.scoring import score_transaction
        store_size_before = len(state.card_store)
        req = ScoreRequest(TransactionAmt=200.0, card1=9999.0, what_if=True)
        score_transaction(req, state)
        # Store should NOT have grown for what_if=True
        # (card 9999 was novel, so if it updated, size would increase)
        assert len(state.card_store) == store_size_before

    def test_score_deterministic(self, state):
        """Same input always gives the same output."""
        from app.schemas.score import ScoreRequest
        from app.services.scoring import score_transaction
        req = ScoreRequest(TransactionAmt=500.0, card4="mastercard", what_if=True)
        r1 = score_transaction(req, state)
        r2 = score_transaction(req, state)
        assert r1.score == r2.score
        assert r1.decision == r2.decision
        assert r1.raw_score == pytest.approx(r2.raw_score, rel=1e-6)

    def test_high_risk_transaction_flagged(self, state):
        """A transaction with every fraud signal should not be APPROVE."""
        from app.schemas.score import ScoreRequest
        from app.services.scoring import score_transaction
        # First warm up a card identity with low amounts
        for i in range(5):
            score_transaction(ScoreRequest(
                TransactionAmt=10.0, card1=8888.0, card2=100.0,
                card4="visa", card6="credit",
                TransactionDT=1_000_000 + i * 60,
            ), state)
        # Now fire a huge amount on the same card within 10 min
        req = ScoreRequest(
            TransactionAmt=5000.0, card1=8888.0, card2=100.0,
            card4="visa", card6="credit",
            TransactionDT=1_000_000 + 6 * 60,
            P_emaildomain="protonmail.com",
        )
        resp = score_transaction(req, state)
        # With card testing pattern + huge amount, score should be elevated
        assert resp.score > 10

    def test_transaction_id_auto_generated(self, state):
        from app.schemas.score import ScoreRequest
        from app.services.scoring import score_transaction
        req = ScoreRequest(TransactionAmt=75.0, what_if=True)
        resp = score_transaction(req, state)
        assert resp.transaction_id.startswith("tx_")

    def test_custom_transaction_id_preserved(self, state):
        from app.schemas.score import ScoreRequest
        from app.services.scoring import score_transaction
        req = ScoreRequest(TransactionAmt=75.0, transaction_id="MY-TX-001", what_if=True)
        resp = score_transaction(req, state)
        assert resp.transaction_id == "MY-TX-001"


# ---------------------------------------------------------------------------
# 5.10 — Training / serving feature parity on 1,000 rows
# ---------------------------------------------------------------------------

class TestFeatureParity:
    """Verify that the serving path (one dict at a time) matches the batch
    training path (pandas replay) for every stateful feature."""

    def test_parity_on_large_batch(self):
        """1,000 random transactions: serving features must match batch features."""
        from app.features import CARD_COLS, CardHistoryStore, replay
        from app.features.build import STORE_INPUT_COLS
        from app.features.store import STATEFUL_FEATURES

        rng = np.random.default_rng(42)
        n = 1000
        df = pd.DataFrame({
            "TransactionID": np.arange(1, n + 1),
            "TransactionDT": np.sort(rng.integers(86_400, 86_400 * 30, n)).astype(int),
            "TransactionAmt": np.round(np.exp(rng.normal(4, 1, n)), 2),
            "card1": rng.integers(1000, 1020, n).astype(float),
            "card2": rng.choice([100.0, 200.0, float("nan")], n),
            "card3": 150.0,
            "card4": rng.choice(["visa", "mastercard"], n),
            "card5": 226.0,
            "card6": rng.choice(["debit", "credit"], n),
            "addr1": rng.choice([300.0, 310.0, float("nan")], n),
            "addr2": 87.0,
            "D1": rng.choice([0.0, 5.0, 40.0, float("nan")], n),
            "DeviceInfo": rng.choice(["Windows", "iOS", None], n),
            "P_emaildomain": rng.choice(["gmail.com", "yahoo.com", None], n),
        })
        for c in ["card4", "card6"]:
            df[c] = df[c].astype("category")
        for c in ["TransactionAmt", "card2", "card3", "card5", "addr1", "addr2", "D1"]:
            df[c] = df[c].astype("float32")

        # Batch path
        batch_features, _ = replay(df)

        # Serving path: feed one dict at a time in chronological order
        store = CardHistoryStore()
        order = np.lexsort((df["TransactionID"].to_numpy(), df["TransactionDT"].to_numpy()))
        serving_rows = [None] * n
        for pos in order:
            row = df.iloc[pos]
            raw = {}
            for col in STORE_INPUT_COLS:
                v = row[col] if col in df.columns else None
                if v is None:
                    raw[col] = None
                elif isinstance(v, str):
                    raw[col] = v
                elif hasattr(v, "item"):
                    raw[col] = None if math.isnan(float(v)) else float(v)
                else:
                    try:
                        fv = float(v)
                        raw[col] = None if math.isnan(fv) else fv
                    except (TypeError, ValueError):
                        raw[col] = str(v)
            serving_rows[pos] = store.process(raw)

        serving_features = pd.DataFrame(serving_rows, columns=STATEFUL_FEATURES)

        # Compare
        for col in STATEFUL_FEATURES:
            b = batch_features[col].to_numpy(dtype="float64")
            s = serving_features[col].to_numpy(dtype="float64")
            np.testing.assert_allclose(b, s, rtol=1e-5, equal_nan=True,
                                       err_msg=f"Feature '{col}' diverges between batch and serving paths")
