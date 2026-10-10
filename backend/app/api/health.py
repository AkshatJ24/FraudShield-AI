"""GET /health and GET /health/db routers."""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.model_state import model_state
from app.db.database import engine
from app.schemas.score import DatabaseHealthResponse, HealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns model load status and basic stats. Safe to call before the model is loaded.",
)
async def health() -> HealthResponse:
    if model_state.is_loaded:
        return HealthResponse(
            status="ok",
            model_loaded=True,
            model_version=model_state.meta.get("version", "unknown"),
            n_trees=model_state.booster.num_trees(),
            n_features=len(model_state.feature_order),
            card_store_size=len(model_state.card_store),
        )
    return HealthResponse(
        status="degraded",
        model_loaded=False,
        model_version="not loaded",
        n_trees=0,
        n_features=0,
        card_store_size=0,
    )


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    summary="Database health check",
    description="Runs `SELECT 1` against PostgreSQL. Returns 503 if the database is unreachable.",
    responses={503: {"model": DatabaseHealthResponse}},
)
async def health_db():
    t0 = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3.0)
            version = (await conn.execute(text("SHOW server_version"))).scalar()
    except Exception as exc:  # unreachable, auth failure, timeout …
        logger.warning("Database health check failed: %s", exc)
        body = DatabaseHealthResponse(status="down", latency_ms=None, server_version=None, error=type(exc).__name__)
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body.model_dump())
    return DatabaseHealthResponse(
        status="ok",
        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        server_version=str(version) if version else None,
        error=None,
    )
