"""FraudShield FastAPI application.

Startup sequence
----------------
1. `lifespan` context manager fires → `model_state.load()` is called ONCE.
   This loads the LightGBM booster, calibrator, encoders,
   thresholds, reason map, and initialises the in-memory card history store.
2. Routers are registered under the versioned prefix (/api/v1).
3. CORS is enabled for local development (all origins); tighten for production.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    health_router, score_router, stream_router, 
    transactions_router, metrics_router, simulator_router
)
from app.core.config import settings
from app.core.model_state import model_state

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan: load artefacts once at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FraudShield API starting up …")
    model_state.load()          # synchronous but fast enough for startup
    logger.info("Startup complete — model version: %s", model_state.meta.get("version", "?"))
    yield
    logger.info("FraudShield API shutting down.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "Real-time fraud scoring API for the IEEE-CIS dataset. "
        "Scores a payment transaction in < 100 ms, returns a risk score (0–100), "
        "decision (APPROVE / REVIEW / BLOCK), and SHAP-driven human-readable reasons."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS (permissive for local dev; restrict in production)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
prefix = settings.API_V1_PREFIX          # /api/v1
app.include_router(health_router)        # GET /health (no version prefix — for probes)
app.include_router(score_router, prefix=prefix)   # POST /api/v1/score
app.include_router(stream_router, prefix=prefix)
app.include_router(transactions_router, prefix=prefix)
app.include_router(metrics_router, prefix=prefix)
app.include_router(simulator_router, prefix=prefix)


# ---------------------------------------------------------------------------
# Root redirect
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root():
    return {"message": "FraudShield API — see /docs for interactive Swagger UI"}
