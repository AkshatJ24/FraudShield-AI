"""GET /health and GET /metrics (stub) routers."""
from __future__ import annotations

from fastapi import APIRouter

from app.core.model_state import model_state
from app.schemas.score import HealthResponse

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
