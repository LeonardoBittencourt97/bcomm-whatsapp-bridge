"""Simple FastAPI wrapper for faster-whisper with OpenAI-compatible API."""
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
import tempfile
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stt")

app = FastAPI(title="faster-whisper STT")

# Load model on startup
whisper_model = None

@app.on_event("startup")
async def startup():
    global whisper_model
    from faster_whisper import WhisperModel
    model_size = os.getenv("WHISPER_MODEL", "small")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    logger.info(f"Loading whisper model: {model_size} on {device} ({compute_type})")
    whisper_model = WhisperModel(model_size, device=device, compute_type=compute_type)
    logger.info("Model loaded!")

@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    language: str = Form(default=None),
):
    """OpenAI-compatible transcription endpoint."""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        segments, info = whisper_model.transcribe(
            tmp_path,
            language=language,
            beam_size=5,
        )
        
        text = " ".join([seg.text for seg in segments])
        os.unlink(tmp_path)
        
        logger.info(f"Transcribed: {len(text)} chars, language={info.language}")
        return {"text": text.strip()}
    except Exception as e:
        logger.error(f"Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/health")
async def health():
    return {"status": "ok", "model": "faster-whisper"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
