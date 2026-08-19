#!/bin/bash
set -e

echo "🚀 Starting BCOMM WhatsApp Bridge + STT Server..."

# Start STT server in background
echo "🎤 Starting faster-whisper STT on port 8001..."
cd /app/stt-server
python -m uvicorn main:app --host 0.0.0.0 --port 8001 &
STT_PID=$!

# Wait for STT to be ready
echo "⏳ Waiting for STT server..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ STT server ready"
        break
    fi
    sleep 1
done

# Start bridge server
echo "🌉 Starting bridge server on port ${PORT:-8000}..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
