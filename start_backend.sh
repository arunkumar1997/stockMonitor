#!/bin/bash
# Start the DipSense backend (FastAPI + Python)
set -e

cd "$(dirname "$0")/backend"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
# shellcheck disable=SC1091
source venv/bin/activate

# Install / update dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip >/dev/null
pip install -r requirements.txt

# Ensure Playwright's Chromium is present (idempotent — no-op if already installed)
echo "🎭 Ensuring Playwright Chromium is installed..."
python -m playwright install chromium

echo "🚀 Starting DipSense backend on http://localhost:8000"
uvicorn main:app --reload --port 8000
