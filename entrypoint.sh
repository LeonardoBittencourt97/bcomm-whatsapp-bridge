#!/bin/bash

echo "🚀 Starting BCOMM WhatsApp Bridge + STT Server..."

# Start STT server in background (don't block bridge startup)
echo "🎤 Starting faster-whisper STT on port 8001..."
cd /app/stt-server
python -m uvicorn main:app --host 0.0.0.0 --port 8001 2>&1 &
STT_PID=$!

# Start bridge server IMMEDIATELY (don't wait for STT)
echo "🌉 Starting bridge server on port ${PORT:-8000}..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
