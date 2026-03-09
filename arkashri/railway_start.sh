#!/bin/bash
# Railway startup script for Arkashri Backend
# This script handles the startup process for Railway deployment

echo "🚀 Starting Arkashri Backend on Railway..."

# Check if required environment variables are set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL not set"
    exit 1
fi

if [ -z "$REDIS_URL" ]; then
    echo "❌ REDIS_URL not set"
    exit 1
fi

if [ -z "$JWT_SECRET_KEY" ]; then
    echo "❌ JWT_SECRET_KEY not set"
    exit 1
fi

# Run database migrations
echo "🗄️ Running database migrations..."
alembic upgrade head

# Start the FastAPI application with Gunicorn
echo "🌟 Starting FastAPI server..."
exec gunicorn -k uvicorn.workers.UvicornWorker arkashri.main:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120 --keep-alive 2 --max-requests 1000 --max-requests-jitter 50
