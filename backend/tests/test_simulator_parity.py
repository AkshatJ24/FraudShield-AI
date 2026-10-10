"""Training / serving parity: the simulator must reproduce the offline holdout scores.

Scores the first demo rows exactly as the simulator does (full raw row through POST /score's
scoring path, skipped rows fed silently to the card store) and compares against
data/processed/holdout_predictions.parquet written by the modeling notebook.

Uses data/replay/*.parquet when present (else builds the replay set from features.parquet +
data/raw), and holdout_predictions.parquet (gitignored), so it is skipped when they are missing.
Takes ~1 minute: loading the replay set and warming the card store dominates.
"""
import pytest

from app.core.config import _REPO_ROOT

_PREDICTIONS = _REPO_ROOT / "data" / "processed" / "holdout_predictions.parquet"
_REPLAY = [_REPO_ROOT / "data" / "replay" / "holdout.parquet", _REPO_ROOT / "data" / "replay" / "train_val_store.parquet"]
_SOURCES = [
    _REPO_ROOT / "data" / "processed" / "features.parquet",
    _REPO_ROOT / "data" / "raw" / "train_transaction.csv",
    _REPO_ROOT / "data" / "raw" / "train_identity.csv",
]
_have_replay = all(p.exists() for p in _REPLAY) or all(p.exists() for p in _SOURCES)
pytestmark = pytest.mark.skipif(not (_PREDICTIONS.exists() and _have_replay), reason="local data files not present")

N_ROWS = 60


def test_simulator_matches_offline_holdout_scores():
    import pandas as pd

    from app.api import simulator as sim
    from app.core.model_state import ModelState
    from app.features.build import STORE_INPUT_COLS
    from app.services.scoring import score_transaction

    state = ModelState()
    state.load()
    data, store = sim.load_replay_data()
    state.card_store = store
    offline = pd.read_parquet(_PREDICTIONS).set_index("TransactionID")

    assert abs(data.holdout.loc[data.demo_idx, "isFraud"].mean() - 0.05) < 0.002

    cursor = 0
    for pos in range(N_ROWS):
        j = int(data.demo_idx[pos])
        for k in range(cursor, j):
            store.process({c: data.store_inputs[c][k] for c in STORE_INPUT_COLS}, update=True)
        cursor = j + 1
        resp = score_transaction(sim._request_from_row(data, j), state)
        expected = offline.loc[data.holdout.at[j, "TransactionID"]]
        assert resp.raw_score == pytest.approx(expected["raw_score"], rel=1e-6, abs=1e-9)
        assert resp.calibrated_prob == pytest.approx(expected["calibrated_prob"], rel=1e-6, abs=1e-9)
