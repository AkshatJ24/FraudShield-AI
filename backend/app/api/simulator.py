"""Holdout replay: scores unseen holdout transactions through the same path as POST /score.

Fidelity to the offline evaluation
----------------------------------
* Each request carries the full raw row (every ScoreRequest field present in the data),
  so the model sees the same inputs it was evaluated on.
* features.parquet keeps categoricals only in encoded form (card4_code, P_emaildomain_freq, …)
  and amounts as float32, so the raw strings and float64 amounts are joined back from
  data/raw/train_*.csv.
* The card history store is warmed with ``features.build.replay`` over train + validation,
  the exact function training used.
* The demo scores a downsampled set (~5% fraud), but every holdout transaction still passes
  through the card history store in time order, so velocity / novelty features match the
  offline holdout features row for row.
"""
import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter

from app.api.stream import broadcaster, notify_new_transaction
from app.core.config import _REPO_ROOT, settings
from app.core.model_state import model_state
from app.db.crud import save_transaction_task
from app.features import CardHistoryStore, replay
from app.features.build import STORE_INPUT_COLS, _py_list
from app.schemas.score import ANONYMISED_FIELDS, ScoreRequest
from app.services.scoring import score_transaction

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulate", tags=["Simulator"])

# Raw columns joined back from the Kaggle CSVs (the parquet only has encoded versions).
_RAW_TXN_COLS = ["TransactionAmt", "ProductCD", "card4", "card6", "P_emaildomain", "R_emaildomain"] + [f"M{i}" for i in range(1, 10)]
_RAW_ID_COLS = ["DeviceType", "DeviceInfo", "id_30", "id_31", "id_33"]
# ScoreRequest fields that are not part of the data row.
_NOT_FROM_ROW = {"transaction_id", "what_if"}
_DEMO_FRAUD_SHARE = 0.05
# Simulated rows are stored without the anonymised columns (~220 → ~30 fields); the full row
# is in data/replay/holdout.parquet under the same TransactionDT / card values.
_ANONYMISED = set(ANONYMISED_FIELDS)


@dataclass
class ReplayData:
    holdout: pd.DataFrame          # every holdout row, sorted like training's replay
    demo_idx: np.ndarray           # positions in `holdout` that are scored and streamed
    store_inputs: dict             # STORE_INPUT_COLS → plain-Python lists, for silent store updates
    train_val: pd.DataFrame        # store inputs for train + validation, to rebuild the store on reset
    request_cols: list             # ScoreRequest fields present in `holdout`


class SimulatorState:
    is_running: bool = False
    task: Optional[asyncio.Task] = None
    # Loaded once and reused across start / stop, so Resume continues where Pause left off.
    data: Optional[ReplayData] = None
    load_task: Optional[asyncio.Task] = None
    # Set by /reset: the store already holds replayed holdout history and must be rebuilt.
    needs_rewarm: bool = False
    warm_task: Optional[asyncio.Task] = None
    # Demo rows scored so far, and the next holdout row the card store hasn't seen.
    position: int = 0
    cursor: int = 0

sim_state = SimulatorState()


def _read_raw(name: str, cols: list, ids: pd.Index) -> Optional[pd.DataFrame]:
    path = _REPO_ROOT / "data" / "raw" / name
    if not path.exists():
        logger.warning("%s not found; simulated requests will omit %s", path, ", ".join(cols))
        return None
    dtypes = {c: ("float64" if c == "TransactionAmt" else "string") for c in cols}
    parts = [
        chunk[chunk["TransactionID"].isin(ids)]
        for chunk in pd.read_csv(path, usecols=["TransactionID", *cols], dtype=dtypes, chunksize=200_000)
    ]
    return pd.concat(parts, ignore_index=True)


def attach_raw_columns(df: pd.DataFrame) -> pd.DataFrame:
    for name, cols in (("train_transaction.csv", _RAW_TXN_COLS), ("train_identity.csv", _RAW_ID_COLS)):
        raw = _read_raw(name, cols, pd.Index(df["TransactionID"]))
        if raw is None:
            continue
        df = df.drop(columns=[c for c in cols if c in df.columns]).merge(raw, on="TransactionID", how="left")
    return df


def warm_store(train_val: pd.DataFrame) -> CardHistoryStore:
    logger.info("Warming up per-card cache from %d train/validation rows...", len(train_val))
    _, store = replay(train_val, CardHistoryStore())
    logger.info("Cache warmup complete: %d card identities.", len(store))
    return store


# Compact replay set for deployment (see `python -m app.api.simulator --export`): everything
# the simulator needs, without the 800 MB of raw CSVs and the full feature parquet.
REPLAY_DIR = _REPO_ROOT / "data" / "replay"
REPLAY_HOLDOUT = REPLAY_DIR / "holdout.parquet"
REPLAY_TRAIN_VAL = REPLAY_DIR / "train_val_store.parquet"


def build_replay_frames() -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """From features.parquet + data/raw: (holdout with a `demo` column, train/val store inputs)."""
    features_path = _REPO_ROOT / "data" / "processed" / "features.parquet"
    if not features_path.exists():
        logger.error("Neither %s nor %s found", REPLAY_HOLDOUT, features_path)
        return None, None

    df = pd.read_parquet(features_path)
    is_holdout = df["split"] == "holdout"
    store_cols = ["TransactionID"] + [c for c in STORE_INPUT_COLS if c in df.columns]
    train_val = df.loc[~is_holdout & df["split"].isin(["train", "validation"]), store_cols]
    holdout = df.loc[is_holdout]
    del df

    train_val = attach_raw_columns(train_val)
    train_val = train_val[["TransactionID"] + [c for c in STORE_INPUT_COLS if c in train_val.columns]]
    holdout = attach_raw_columns(holdout)

    # Same order as features.build.replay (TransactionDT, then TransactionID).
    holdout = holdout.sort_values(["TransactionDT", "TransactionID"], kind="stable").reset_index(drop=True)

    # Score every fraud and enough legitimate rows for ~5% fraud; the rest only feed the store.
    is_fraud = holdout["isFraud"] == 1
    legit = holdout.index[~is_fraud]
    n_legit = min(len(legit), int(is_fraud.sum() * (1 - _DEMO_FRAUD_SHARE) / _DEMO_FRAUD_SHARE))
    keep = pd.Index(holdout.index[is_fraud]).union(pd.Series(legit).sample(n=n_legit, random_state=42))
    holdout["demo"] = holdout.index.isin(keep)

    request_cols = [c for c in ScoreRequest.model_fields if c in holdout.columns and c not in _NOT_FROM_ROW]
    holdout = holdout[["TransactionID", "isFraud", "demo", *request_cols]]
    return holdout, train_val


def export_replay_files() -> None:
    holdout, train_val = build_replay_frames()
    if holdout is None:
        raise SystemExit("Could not build the replay set (see log).")
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    holdout.to_parquet(REPLAY_HOLDOUT, index=False, compression="zstd")
    train_val.to_parquet(REPLAY_TRAIN_VAL, index=False, compression="zstd")
    for p in (REPLAY_HOLDOUT, REPLAY_TRAIN_VAL):
        logger.info("Wrote %s (%.1f MB)", p, p.stat().st_size / 1e6)


def load_replay_data() -> tuple[Optional[ReplayData], Optional[CardHistoryStore]]:
    if REPLAY_HOLDOUT.exists() and REPLAY_TRAIN_VAL.exists():
        holdout = pd.read_parquet(REPLAY_HOLDOUT)
        train_val = pd.read_parquet(REPLAY_TRAIN_VAL)
    else:
        holdout, train_val = build_replay_frames()
        if holdout is None:
            return None, None

    store = warm_store(train_val)
    demo_idx = np.flatnonzero(holdout["demo"].to_numpy())
    request_cols = [c for c in ScoreRequest.model_fields if c in holdout.columns and c not in _NOT_FROM_ROW]
    store_inputs = {c: _py_list(holdout[c]) if c in holdout else [None] * len(holdout) for c in STORE_INPUT_COLS}
    logger.info("Replay set: %d holdout rows, %d scored (%d request fields each).", len(holdout), len(demo_idx), len(request_cols))
    return ReplayData(holdout, demo_idx, store_inputs, train_val, request_cols), store


async def ensure_replay_ready() -> Optional[ReplayData]:
    """Load once, and rebuild the card store after a reset. Both run in a worker thread
    that can't be cancelled, so the task is shared: a quick stop → start waits on the
    same work instead of starting it twice."""
    if sim_state.data is None:
        if sim_state.load_task is None:
            sim_state.load_task = asyncio.create_task(asyncio.to_thread(load_replay_data))
        try:
            data, store = await asyncio.shield(sim_state.load_task)
        except Exception:
            sim_state.load_task = None
            raise
        if data is None:
            sim_state.load_task = None  # allow a retry once the file exists
            return None
        if sim_state.data is None:
            model_state.card_store = store
            sim_state.data = data
            sim_state.needs_rewarm = False

    if sim_state.needs_rewarm:
        if sim_state.warm_task is None:
            sim_state.warm_task = asyncio.create_task(asyncio.to_thread(warm_store, sim_state.data.train_val))
        store = await asyncio.shield(sim_state.warm_task)
        sim_state.warm_task = None
        if sim_state.needs_rewarm:
            model_state.card_store = store
            sim_state.needs_rewarm = False
    return sim_state.data


def _request_from_row(data: ReplayData, i: int) -> ScoreRequest:
    """Build the ScoreRequest a client holding the full row would send (isFraud stays out)."""
    row = data.holdout.iloc[i]
    req_data = {c: row[c] for c in data.request_cols if pd.notna(row[c])}
    if "has_identity" in req_data:
        req_data["has_identity"] = bool(req_data["has_identity"])
    req_data["what_if"] = False
    return ScoreRequest(**req_data)


async def simulator_loop():
    logger.info("Simulator started")

    while not model_state.is_loaded:
        await asyncio.sleep(1)

    data = await ensure_replay_ready()
    if data is None:
        logger.error("Simulator could not load holdout data.")
        sim_state.is_running = False
        return

    # Finished last time → rebuild the store and replay again from the top.
    if sim_state.position >= len(data.demo_idx):
        _rewind()
        data = await ensure_replay_ready()
    logger.info("Resuming at scored row %d of %d.", sim_state.position, len(data.demo_idx))

    last_viewer = time.monotonic()
    while sim_state.is_running and sim_state.position < len(data.demo_idx):
        # Nobody watching (no SSE clients) for a while → pause instead of replaying all night.
        if broadcaster.queues:
            last_viewer = time.monotonic()
        elif settings.SIMULATOR_IDLE_PAUSE_S and time.monotonic() - last_viewer > settings.SIMULATOR_IDLE_PAUSE_S:
            logger.info("No dashboard connected for %d s; pausing the simulator.", settings.SIMULATOR_IDLE_PAUSE_S)
            break

        target = int(data.demo_idx[sim_state.position])

        # Rows the demo skips still go into card history, in time order.
        store = model_state.card_store
        for k in range(sim_state.cursor, target):
            store.process({c: data.store_inputs[c][k] for c in STORE_INPUT_COLS}, update=True)
        sim_state.cursor = target + 1
        sim_state.position += 1

        true_label = bool(data.holdout.at[target, "isFraud"])
        try:
            req = _request_from_row(data, target)
            # Score locally (also adds the row to card history)
            resp = score_transaction(req, model_state)

            # Dispatch DB save explicitly
            req_dict = req.model_dump(exclude_unset=True)
            stored = {k: v for k, v in req_dict.items() if k not in _ANONYMISED}
            asyncio.create_task(
                save_transaction_task(stored, resp, is_simulated=True, true_label=true_label)
            )

            # Broadcast SSE explicitly
            asyncio.create_task(notify_new_transaction(resp, true_label=true_label, request=req_dict))

        except Exception as e:
            logger.error(f"Simulator error during scoring: {e}")

        await asyncio.sleep(random.uniform(0.5, 2.0))

    sim_state.is_running = False
    sim_state.task = None
    logger.info("Simulator stopped at scored row %d.", sim_state.position)


def _rewind():
    sim_state.position = 0
    sim_state.cursor = 0
    sim_state.needs_rewarm = sim_state.data is not None


def _status() -> dict:
    total = len(sim_state.data.demo_idx) if sim_state.data is not None else None
    return {
        "running": sim_state.is_running,
        "position": sim_state.position,
        "total": total,
        "warmed_up": sim_state.data is not None and not sim_state.needs_rewarm,
        "loading": (sim_state.data is None and sim_state.load_task is not None) or sim_state.warm_task is not None,
    }


def _start() -> None:
    sim_state.is_running = True
    sim_state.task = asyncio.create_task(simulator_loop())


def _stop() -> None:
    sim_state.is_running = False
    if sim_state.task:
        sim_state.task.cancel()
        sim_state.task = None


@router.get("/status")
async def simulator_status():
    """Replay progress in scored rows. `total` is null until the replay set has been loaded."""
    return _status()


@router.post("/start")
async def start_simulator():
    """Start, or resume from where the last /stop left off."""
    if sim_state.is_running:
        return {"message": "Simulator is already running", **_status()}

    resumed = sim_state.position > 0 and (sim_state.data is None or sim_state.position < len(sim_state.data.demo_idx))
    _start()
    return {"message": "Simulator resumed" if resumed else "Simulator started", **_status()}


@router.post("/stop")
async def stop_simulator():
    """Pause. The replay position is kept, so the next /start resumes."""
    if not sim_state.is_running:
        return {"message": "Simulator is not running", **_status()}

    _stop()
    return {"message": "Simulator stopped", **_status()}


@router.post("/reset")
async def reset_simulator():
    """Rewind to the first row and rebuild the card history from train + validation,
    so re-scored rows don't see their own (already replayed) history. Keeps running or
    paused as it was; while running, the rebuild happens before the next event."""
    was_running = sim_state.is_running
    if was_running:
        _stop()
    _rewind()
    if was_running:
        _start()
    return {"message": "Simulator rewound to the start", **_status()}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Holdout replay utilities.")
    ap.add_argument("--export", action="store_true", help=f"write {REPLAY_HOLDOUT.name} and {REPLAY_TRAIN_VAL.name} to data/replay/")
    if ap.parse_args().export:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
        export_replay_files()
