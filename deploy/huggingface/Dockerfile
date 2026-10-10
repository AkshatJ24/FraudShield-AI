# Hugging Face Space for the FraudShield API.
# Copy this file and README.md (same folder) into the Space repo. The Space builds straight
# from GitHub, so pushing to GitHub + "Factory rebuild" on the Space deploys a new version.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NUMBA_CACHE_DIR=/tmp/numba \
    MPLCONFIGDIR=/tmp/matplotlib \
    PORT=7860

ARG REPO=https://github.com/AkshatJ24/FraudShield-AI.git
ARG BRANCH=main

# Changes whenever the branch gets a new commit, so Docker doesn't reuse a stale clone.
ADD https://api.github.com/repos/AkshatJ24/FraudShield-AI/commits/${BRANCH} /tmp/latest-commit.json
RUN git clone --depth 1 --branch ${BRANCH} ${REPO} /app

WORKDIR /app
RUN pip install -r backend/requirements.txt

RUN useradd -m -u 1000 user && chown -R user /app
USER user
WORKDIR /app/backend

EXPOSE 7860
CMD alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
