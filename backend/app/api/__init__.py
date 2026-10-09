"""API package — all routers gathered here."""
from .health import router as health_router
from .score import router as score_router
from .stream import router as stream_router
from .transactions import router as transactions_router
from .metrics import router as metrics_router
from .simulator import router as simulator_router

__all__ = [
    "health_router", 
    "score_router",
    "stream_router",
    "transactions_router",
    "metrics_router",
    "simulator_router"
]
