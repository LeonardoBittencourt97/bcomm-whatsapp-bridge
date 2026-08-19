FROM python:3.12-slim

WORKDIR /app

# System deps (curl + ffmpeg for STT)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Python deps for bridge
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Python deps for STT server
COPY stt-server/requirements.txt stt-server/requirements.txt
RUN pip install --no-cache-dir -r stt-server/requirements.txt

# App code
COPY . .

# Non-root user
RUN useradd --create-home appuser
RUN chmod +x entrypoint.sh
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["./entrypoint.sh"]
