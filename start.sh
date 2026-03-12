#!/bin/bash
# ==============================================================================
# ADG KMS - Startup Script
# Runs database migrations, syncs tables, then starts the FastAPI server
# ==============================================================================

set -e

echo "=== ADG KMS Starting ==="

# Write service account JSON from env var to file (if provided)
if [ -n "$GDRIVE_SERVICE_ACCOUNT_JSON" ]; then
    echo "$GDRIVE_SERVICE_ACCOUNT_JSON" > /app/service-account.json
    export GDRIVE_SERVICE_ACCOUNT_FILE=/app/service-account.json
    echo "✅ Service account file created from env var"
fi

# Run Alembic migrations (skip if DATABASE_URL not set)
if [ -n "$DATABASE_URL" ]; then
    echo "🔄 Running database migrations..."
    cd /app/backend && alembic upgrade head && cd /app
    echo "✅ Migrations complete"

    # Sync tables: create any NEW tables from models.py that Alembic doesn't know about
    echo "🔄 Syncing database tables..."
    cd /app && python -m backend.db.sync_tables
    echo "✅ Table sync complete"
    
    # Seed/sync roles, permissions, and users (idempotent)
    echo "🌱 Seeding database..."
    cd /app && python -m backend.db.seed
    echo "✅ Seed complete"
else
    echo "⚠️ DATABASE_URL not set, skipping migrations"
fi

# Start FastAPI with Uvicorn
echo "🚀 Starting server on port ${PORT:-8080}..."
exec uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8080}" \
    --workers 1 \
    --log-level info
