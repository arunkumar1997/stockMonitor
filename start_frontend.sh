#!/bin/bash
# Start the DipSense frontend (React + Vite)
set -e

cd "$(dirname "$0")/frontend"

# Install dependencies if node_modules is missing or package.json changed
if [ ! -d "node_modules" ]; then
    echo "📥 Installing dependencies..."
    npm install
fi

echo "🌐 Starting DipSense frontend on http://localhost:5173"
npm run dev
