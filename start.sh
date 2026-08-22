#!/bin/sh
# Run database migrations then start the API server.
# Using 'sh' for maximum compatibility inside the python:3.12-slim image.

set -e

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
