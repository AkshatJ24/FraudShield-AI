# FraudShield API: FastAPI + model + holdout replay simulator.
# Build from the repo root:  docker build -t fraudshield-api .
# Needs DATABASE_URL at runtime; listens on $PORT (default 7860, Hugging Face Spaces' port).
FROM python:3.13-slim

# libgomp: OpenMP runtime LightGBM links against.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NUMBA_CACHE_DIR=/tmp/numba \
    MPLCONFIGDIR=/tmp/matplotlib \
    PORT=7860

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Code, model artifacts and the compact replay set (paths match the repo layout).
COPY backend backend
COPY ml/artifacts ml/artifacts
COPY data/replay data/replay

# Hugging Face runs containers as uid 1000.
RUN useradd -m -u 1000 user && chown -R user /app
USER user
WORKDIR /app/backend

EXPOSE 7860
CMD alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
