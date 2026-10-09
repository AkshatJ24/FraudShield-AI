"""POST /score router."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from app.core.model_state import model_state
from app.schemas.score import ScoreRequest, ScoreResponse
from app.services.scoring import score_transaction
from app.db.crud import save_transaction_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/score", tags=["Scoring"])


@router.post(
    "",
    response_model=ScoreResponse,
    summary="Score a transaction",
    description=(
        "Score one payment transaction. Returns a risk score (0–100), "
        "a decision (APPROVE / REVIEW / BLOCK), human-readable SHAP reasons, "
        "and the end-to-end latency. "
        "Set `what_if=true` to score without recording the transaction in the "
        "velocity store (useful for the manual form)."
    ),
    status_code=status.HTTP_200_OK,
)
async def score_endpoint(req: ScoreRequest, background_tasks: BackgroundTasks) -> ScoreResponse:
    if not model_state.is_loaded:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not yet loaded. Try again in a moment.",
        )
    try:
        resp = score_transaction(req, model_state)
        # 6.2 Async write of each scored transaction
        # Only save if not a what_if check (or maybe save all but mark what_if? The schema doesn't distinguish what_if in DB. We can save all for history).
        background_tasks.add_task(
            save_transaction_task,
            req.model_dump(exclude_unset=True),
            resp,
            False # is_simulated defaults to False for manual POST /score
        )
        # Notify SSE stream
        from app.api.stream import notify_new_transaction
        background_tasks.add_task(notify_new_transaction, resp)
        return resp
    except Exception as exc:
        logger.exception("Scoring failed for request %s", req.transaction_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scoring error: {exc}",
        ) from exc
