#!/bin/sh
# Container entrypoint: apply database migrations, then serve the API on $PORT.
set -e
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-7860}"
