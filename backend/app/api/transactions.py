from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from app.db.database import get_db
from app.db.models import TransactionRecord

router = APIRouter(prefix="/transactions", tags=["Transactions"])

class TransactionResponse(BaseModel):
    id: str
    amount: float
    decision: str
    score: int
    reasons: list
    latency_ms: float
    is_simulated: bool
    review_status: str
    created_at: datetime
    request_data: dict
    
    class Config:
        from_attributes = True

class ReviewRequest(BaseModel):
    status: str # "FRAUD" or "FALSE_POSITIVE"

@router.get("", response_model=List[TransactionResponse])
async def get_transactions(
    decision: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(TransactionRecord).order_by(desc(TransactionRecord.created_at))
    if decision:
        stmt = stmt.where(TransactionRecord.decision == decision)
    if min_amount is not None:
        stmt = stmt.where(TransactionRecord.amount >= min_amount)
    if max_amount is not None:
        stmt = stmt.where(TransactionRecord.amount <= max_amount)
        
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    records = result.scalars().all()
    return records

@router.post("/{tx_id}/review")
async def review_transaction(tx_id: str, req: ReviewRequest, db: AsyncSession = Depends(get_db)):
    if req.status not in ["FRAUD", "FALSE_POSITIVE"]:
        raise HTTPException(status_code=400, detail="Invalid review status")
        
    result = await db.execute(select(TransactionRecord).where(TransactionRecord.id == tx_id))
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Transaction not found")
        
    record.review_status = req.status
    await db.commit()
    return {"message": "Review recorded successfully", "id": tx_id, "status": req.status}
