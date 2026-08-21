"""
bcomm-whatsapp-bridge — FastAPI server

Bridge entre Evolution API (WhatsApp) e Hermes/LLM.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from client_loader import ClientLoader
from handlers.messages import process_incoming_message
from handlers.webhook import extract_message
from models.schemas import (
    HealthResponse,
    SendMessageRequest,
    SendMessageResponse,
    WebhookEvent,
)
from services.evolution import EvolutionClient
from services.hermes import HermesClient
from services.llm import LLMClient
from services.stt import STTClient

# ── Logging ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bridge")

# ── Multi-tenant client loader
client_loader = ClientLoader(settings.clients_dir)

# ── Global state ────────────────────────────────────────────────────

_start_time = time.time()
evolution_client = EvolutionClient()
hermes_client = HermesClient()
llm_client = LLMClient()
stt_client = STTClient()


# ── Lifespan ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    logger.info("🚀 Bridge server iniciando...")
    logger.info(f"   Evolution API: {settings.evolution_api_url}")
    logger.info(f"   Instância:     {settings.evolution_instance}")
    logger.info(f"   Hermes:        {settings.hermes_profile}")
    logger.info(f"   LLM model:     {settings.opencode_model}")
    logger.info(f"   STT model:     {settings.stt_model}")
    logger.info(f"   Porta:         {settings.port}")

    yield

    logger.info("🛑 Encerrando bridge server...")
    await evolution_client.close()
    await llm_client.close()
    await stt_client.close()


# ── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="bcomm-whatsapp-bridge",
    description="Bridge entre Evolution API e Hermes/LLM",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ───────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check com status dos serviços dependentes."""
    evo_ok = await evolution_client.health_check()
    llm_ok = await llm_client.health_check()
    stt_ok = await stt_client.health_check()
    hermes_ok = await hermes_client.is_available()

    status = "ok" if evo_ok else "degraded"

    return HealthResponse(
        status=status,
        evolution_api="ok" if evo_ok else "unavailable",
        uptime_seconds=round(time.time() - _start_time, 1),
    )


@app.post("/webhook/evolution")
async def webhook_evolution(request: Request):
    """
    Endpoint principal de webhook da Evolution API.
    
    Recebe eventos, extrai mensagens e despacha para processamento.
    Retorna imediatamente — processamento acontece em background via batch.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Parse do evento
    try:
        event = WebhookEvent(
            event=body.get("event", body.get("eventName", "unknown")),
            instance=body.get("instance", body.get("instanceName", settings.evolution_instance)),
            data=body.get("data", body),
            sender=body.get("sender"),
            timestamp=body.get("timestamp"),
        )
    except Exception as e:
        logger.warning(f"Erro ao parsear evento webhook: {e}")
        return {"status": "ignored", "event": body.get("event", "unknown")}

    logger.info(f"Webhook recebido: event={event.event}, instance={event.instance}")

    # Extrair mensagem
    message = extract_message(event)
    if message is None:
        return {"status": "ignored", "event": event.event}

    # Processar em background (batch aguarda mensagens adicionais)
    # Não usa await — retorna imediatamente
    asyncio.create_task(process_incoming_message(
        message=message,
        evolution=evolution_client,
        hermes=hermes_client,
        llm=llm_client,
        stt=stt_client,
        use_hermes=True,  # Toggle: True para usar Hermes CLI
    ))

    return {
        "status": "queued",
        "message_id": message.message_id,
    }


@app.post("/send", response_model=SendMessageResponse)
async def send_message(req: SendMessageRequest):
    """
    Enviar mensagem manualmente via Evolution API.
    """
    result = await evolution_client.send_text(
        to_number=req.to_number,
        message=req.message,
        instance=req.instance,
    )

    return SendMessageResponse(
        success=result["success"],
        message_id=result.get("message_id"),
        error=result.get("error"),
    )


@app.post("/admin/clear-sessions")
async def clear_sessions(phone: Optional[str] = None):
    """
    Limpa sessões do Hermes.
    Se phone for especificado, limpa apenas essa sessão.
    Caso contrário, limpa todas.
    """
    from services.hermes import _load_sessions, _save_sessions
    
    sessions = _load_sessions()
    
    if phone:
        if phone in sessions:
            del sessions[phone]
            _save_sessions(sessions)
            return {"status": "cleared", "phone": phone}
        return {"status": "not_found", "phone": phone}
    else:
        _save_sessions({})
        return {"status": "cleared_all", "count": len(sessions)}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "bcomm-whatsapp-bridge",
        "version": "1.0.0",
        "docs": "/docs",
    }


# ── Run ─────────────────────────────────────────────────────────────


@app.get("/clients")
async def list_clients():
    """Lista todos os clientes multi-tenant."""
    return {
        "count": client_loader.client_count,
        "clients": client_loader.list_all(),
    }


@app.post("/admin/reload")
async def reload_clients():
    """Recarrega configurações de clientes."""
    client_loader.reload()
    return {"status": "reloaded", "count": client_loader.client_count}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
