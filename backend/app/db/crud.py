from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import TransactionRecord
from app.schemas.score import ScoreResponse
import json

async def save_transaction_async(session: AsyncSession, req_data: dict, resp: ScoreResponse, is_simulated: bool, true_label: bool = None):
    try:
        record = TransactionRecord(
            id=resp.transaction_id,
            amount=req_data.get("TransactionAmt", 0.0),
            decision=resp.decision,
            score=resp.score,
            reasons=[r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in resp.reasons],
            latency_ms=resp.latency_ms,
            is_simulated=is_simulated,
            true_label=true_label,
            request_data=req_data
        )
        session.add(record)
        await session.commit()
    except Exception as e:
        await session.rollback()
        import logging
        logging.getLogger(__name__).error(f"Failed to save transaction {resp.transaction_id}: {e}")

from app.db.database import AsyncSessionLocal

async def save_transaction_task(req_data: dict, resp: ScoreResponse, is_simulated: bool = False, true_label: bool = None):
    async with AsyncSessionLocal() as session:
        await save_transaction_async(session, req_data, resp, is_simulated, true_label)
