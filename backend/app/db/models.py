from sqlalchemy import Column, String, Float, Integer, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from app.db.database import Base

class TransactionRecord(Base):
    __tablename__ = "transactions"
    
    id = Column(String, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    decision = Column(String, nullable=False)
    score = Column(Integer, nullable=False)
    reasons = Column(JSON, nullable=False)
    latency_ms = Column(Float, nullable=False)
    is_simulated = Column(Boolean, default=False)
    true_label = Column(Boolean, nullable=True)
    review_status = Column(String, default="PENDING")
    request_data = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
