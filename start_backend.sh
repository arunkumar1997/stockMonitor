#!/bin/bash
# Start the DipSense backend (FastAPI + Python)
cd "$(dirname "$0")/backend"
echo "🚀 Starting DipSense backend on http://localhost:8000"
venv/bin/uvicorn main:app --reload --port 8000
