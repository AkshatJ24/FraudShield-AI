# FraudShield API: FastAPI + model + holdout replay simulator.
# Build from the repo root:  docker build -t fraudshield-api .
# Needs DATABASE_URL at runtime; listens on $PORT (default 7860). Runs in ~512 MB of RAM.
FROM python:3.13-slim

# libgomp: OpenMP runtime LightGBM links against.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# OMP_NUM_THREADS=1: LightGBM otherwise starts a thread per host core, and on a fractional-CPU
# host (e.g. 0.25 vCPU) the quota throttles them all; one thread scores ~2x faster there.
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=1 \
    PORT=7860

RUN useradd -m -u 1000 user
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Code, model artifacts and the compact replay set (paths match the repo layout).
COPY --chown=user backend backend
COPY --chown=user ml/artifacts ml/artifacts
COPY --chown=user data/replay data/replay

USER user
WORKDIR /app/backend

EXPOSE 7860
# Migrations + server (backend/start.sh). Hosts with a "start command" field: use `sh start.sh`.
CMD ["sh", "start.sh"]
