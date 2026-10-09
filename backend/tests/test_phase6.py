import pytest
from httpx import AsyncClient
from app.main import app
from app.db.database import get_db
from app.db.models import TransactionRecord
from app.schemas.score import ScoreRequest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

import pytest_asyncio
from httpx import ASGITransport
from app.db.database import AsyncSessionLocal

@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

@pytest_asyncio.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session

@pytest.mark.asyncio
async def test_simulator_does_not_accept_label():
    """Ensure the score request strictly drops/ignores true_label or isFraud fields."""
    # ScoreRequest does not allow extra fields. If someone tries to pass true_label, Pydantic should error or ignore it depending on config
    # In Pydantic v2, extra='ignore' is default. But it won't be in the model_dump()
    data = {
        "TransactionAmt": 100.0,
        "true_label": True,
        "isFraud": 1
    }
    
    # Try parsing manually
    req = ScoreRequest(**data)
    assert not hasattr(req, "true_label")
    assert not hasattr(req, "isFraud")
    assert req.TransactionAmt == 100.0

@pytest.mark.asyncio
async def test_review_upsert(async_client: AsyncClient, db_session: AsyncSession):
    """Test updating the review status of a transaction."""
    await db_session.execute(TransactionRecord.__table__.delete().where(TransactionRecord.id == "test_tx_123"))
    await db_session.commit()
    
    record = TransactionRecord(
        id="test_tx_123",
        amount=50.0,
        decision="REVIEW",
        score=65,
        reasons=[],
        latency_ms=10.0,
        is_simulated=True,
        request_data={"TransactionAmt": 50.0}
    )
    db_session.add(record)
    await db_session.commit()
    
    response = await async_client.post("/api/v1/transactions/test_tx_123/review", json={"status": "FRAUD"})
    assert response.status_code == 200
    
    # Expire to read from db again
    db_session.expire_all()
    res = await db_session.execute(select(TransactionRecord).where(TransactionRecord.id == "test_tx_123"))
    db_rec = res.scalars().first()
    assert db_rec.review_status == "FRAUD"

@pytest.mark.asyncio
async def test_pagination(async_client: AsyncClient, db_session: AsyncSession):
    """Test transaction API pagination."""
    # Clean up first
    await db_session.execute(TransactionRecord.__table__.delete())
    await db_session.commit()
    
    for i in range(3):
        record = TransactionRecord(
            id=f"page_tx_{i}",
            amount=50.0,
            decision="APPROVE",
            score=10,
            reasons=[],
            latency_ms=5.0,
            is_simulated=True,
            request_data={}
        )
        db_session.add(record)
    await db_session.commit()
    
    response = await async_client.get("/api/v1/transactions?limit=2&offset=0")
    data = response.json()
    assert len(data) == 2

@pytest.mark.asyncio
async def test_source_tagging(db_session: AsyncSession):
    """Test that simulated vs manual transactions are tagged correctly via crud."""
    from app.db.crud import save_transaction_task
    from app.schemas.score import ScoreResponse
    
    await db_session.execute(TransactionRecord.__table__.delete().where(TransactionRecord.id.in_(["tx_source_1", "tx_source_2"])))
    await db_session.commit()
    
    resp = ScoreResponse(
        transaction_id="tx_source_1",
        score=10,
        decision="APPROVE",
        reasons=[],
        calibrated_prob=0.01,
        raw_score=-2.0,
        latency_ms=10.0,
        what_if=False
    )
    
    # Use task instead of async to get clean session
    await save_transaction_task({}, resp, is_simulated=True, true_label=True)
    
    resp.transaction_id = "tx_source_2"
    await save_transaction_task({}, resp, is_simulated=False, true_label=None)
    
    db_session.expire_all()
    r1 = (await db_session.execute(select(TransactionRecord).where(TransactionRecord.id == "tx_source_1"))).scalars().first()
    r2 = (await db_session.execute(select(TransactionRecord).where(TransactionRecord.id == "tx_source_2"))).scalars().first()
    
    assert r1.is_simulated is True
    assert r1.true_label is True
    
    assert r2.is_simulated is False
    assert r2.true_label is None
