import asyncio
import logging
from typing import Optional
from pathlib import Path
import random
import pandas as pd

from fastapi import APIRouter
from app.schemas.score import ScoreRequest
from app.services.scoring import score_transaction
from app.core.model_state import model_state
from app.db.crud import save_transaction_task
from app.api.stream import notify_new_transaction
from app.core.config import _REPO_ROOT

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulate", tags=["Simulator"])

class SimulatorState:
    is_running: bool = False
    task: Optional[asyncio.Task] = None
    is_warmed_up: bool = False

sim_state = SimulatorState()

def get_holdout_data():
    features_path = _REPO_ROOT / "data" / "processed" / "features.parquet"
    if not features_path.exists():
        logger.error("Features file not found")
        return pd.DataFrame()
        
    df = pd.read_parquet(features_path)
    
    # Warm up cache if not done
    if not sim_state.is_warmed_up:
        logger.info("Warming up per-card cache from train/validation...")
        train_val = df[df["split"].isin(["train", "validation"])].sort_values("TransactionDT")
        from app.features.build import STORE_INPUT_COLS
        for _, row in train_val.iterrows():
            store_input = {c: row.get(c, None) for c in STORE_INPUT_COLS}
            store_input["TransactionDT"] = row["TransactionDT"]
            store_input["TransactionAmt"] = row["TransactionAmt"]
            model_state.card_store.process(store_input, update=True)
        sim_state.is_warmed_up = True
        logger.info("Cache warmup complete.")
        
    holdout = df[df["split"] == "holdout"].sort_values("TransactionDT")
    
    # Downsample legitimate transactions to ~5% fraud
    fraud = holdout[holdout["isFraud"] == 1]
    legit = holdout[holdout["isFraud"] == 0]
    
    # If 5% fraud, legit = 19 * fraud
    n_legit_keep = min(len(legit), int(len(fraud) * 19))
    if n_legit_keep > 0:
        legit = legit.sample(n=n_legit_keep, random_state=42)
        
    demo_holdout = pd.concat([fraud, legit]).sort_values("TransactionDT")
    return demo_holdout

async def simulator_loop():
    logger.info("Simulator started")
    
    while not model_state.is_loaded:
        await asyncio.sleep(1)
        
    df = await asyncio.to_thread(get_holdout_data)
    if df.empty:
        logger.error("Simulator could not load holdout data.")
        sim_state.is_running = False
        return

    logger.info(f"Loaded {len(df)} rows for simulation.")
    
    for _, row in df.iterrows():
        if not sim_state.is_running:
            break
            
        true_label = bool(row["isFraud"])
        
        # Build ScoreRequest exactly as a client would, keeping isFraud out.
        # Handle nan values by converting to None
        req_data = {}
        for field in ScoreRequest.model_fields:
            if field in row and pd.notna(row[field]):
                req_data[field] = row[field]
                
        req_data["what_if"] = False
        req = ScoreRequest(**req_data)
        
        try:
            # Score locally
            resp = score_transaction(req, model_state)
            
            # Dispatch DB save explicitly
            req_dict = req.model_dump(exclude_unset=True)
            asyncio.create_task(
                save_transaction_task(req_dict, resp, is_simulated=True, true_label=true_label)
            )
            
            # Broadcast SSE explicitly
            asyncio.create_task(notify_new_transaction(resp, true_label=true_label))
            
        except Exception as e:
            logger.error(f"Simulator error during scoring: {e}")
            
        await asyncio.sleep(random.uniform(0.5, 2.0))
        
    sim_state.is_running = False
    logger.info("Simulator finished")

@router.post("/start")
async def start_simulator():
    if sim_state.is_running:
        return {"message": "Simulator is already running"}
        
    sim_state.is_running = True
    sim_state.task = asyncio.create_task(simulator_loop())
    return {"message": "Simulator started"}

@router.post("/stop")
async def stop_simulator():
    if not sim_state.is_running:
        return {"message": "Simulator is not running"}
        
    sim_state.is_running = False
    if sim_state.task:
        sim_state.task.cancel()
        sim_state.task = None
    return {"message": "Simulator stopped"}
