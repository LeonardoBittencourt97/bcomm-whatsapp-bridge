#!/bin/bash

echo "🚀 Starting BCOMM WhatsApp Bridge + STT Server..."

# Start STT server in background (don't fail if it crashes)
echo "🎤 Starting faster-whisper STT on port 8001..."
cd /app/stt-server
python -m uvicorn main:app --host 0.0.0.0 --port 8001 &
STT_PID=$!

# Wait for STT to be ready (max 60s for model download on first run)
echo "⏳ Waiting for STT server (up to 60s for model download)..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8001/health > /dev/null 2>&1; then
        echo "✅ STT server ready"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "⚠️  STT server not ready after 60s, starting bridge anyway"
    fi
    sleep 1
done

# Start bridge server (always, even if STT failed)
echo "🌉 Starting bridge server on port ${PORT:-8000}..."
cd /app
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
