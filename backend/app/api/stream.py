import asyncio
import time
from typing import Any, AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.schemas.score import ScoreResponse
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["Streaming"])

# Broadcaster for SSE
class EventBroadcaster:
    def __init__(self):
        self.queues: list[asyncio.Queue] = []

    def add_queue(self) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=100) # Added maxsize to prevent memory leaks
        self.queues.append(q)
        return q

    def remove_queue(self, q: asyncio.Queue):
        if q in self.queues:
            self.queues.remove(q)

    async def broadcast(self, message: str):
        for q in self.queues:
            if q.full():
                # Drop oldest event if slow client
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            await q.put(message)

broadcaster = EventBroadcaster()

# Request fields the dashboard displays next to each score.
REQUEST_FIELDS = ("TransactionAmt", "ProductCD", "card1", "card4", "card6", "P_emaildomain", "DeviceType")


def _plain(v: Any) -> Any:
    """numpy scalars (from the simulator's DataFrame rows) → plain Python for json.dumps."""
    return v.item() if hasattr(v, "item") else v


async def notify_new_transaction(
    resp: ScoreResponse,
    true_label: bool | None = None,
    request: dict | None = None,
):
    # Include true_label in payload for demo
    data = resp.model_dump()
    data["true_label"] = true_label
    data["scored_at"] = int(time.time() * 1000)
    if request:
        for k in REQUEST_FIELDS:
            data[k] = _plain(request.get(k))
    await broadcaster.broadcast(json.dumps(data, default=str))

async def event_generator(request: Request) -> AsyncGenerator[str, None]:
    q = broadcaster.add_queue()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                # Wait for message with a timeout for heartbeat
                message = await asyncio.wait_for(q.get(), timeout=15.0)
                yield f"data: {message}\n\n"
            except asyncio.TimeoutError:
                # Heartbeat to keep connection alive and detect drops
                yield ": heartbeat\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        broadcaster.remove_queue(q)

@router.get("")
async def stream_transactions(request: Request):
    """SSE endpoint for live transaction feed."""
    # No caching, and tell reverse proxies (nginx, Hugging Face, …) not to buffer the stream.
    return StreamingResponse(
        event_generator(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
