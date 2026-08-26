"""
bcomm-whatsapp-bridge — FastAPI server

Bridge entre Evolution API (WhatsApp) e Hermes/LLM.
"""
import asyncio
import json
import os
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from client_loader import ClientLoader
from handlers.messages import process_incoming_message
from handlers.webhook import extract_message, is_test_mode_allowed
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

    # Verificar modo teste
    if not is_test_mode_allowed(message.from_number):
        logger.info(f"Mensagem ignorada (modo teste): {message.from_number}")
        return {"status": "ignored_test_mode", "phone": message.from_number}

    # Verificar se o cliente está pausado
    client_name = message.instance or settings.evolution_instance
    if is_client_paused(client_name):
        logger.info(f"Mensagem ignorada (cliente pausado): {client_name}")
        return {"status": "ignored_paused", "client": client_name}
    
    # Verificar se o contato específico está pausado
    if is_contact_paused(client_name, message.from_number):
        logger.info(f"Mensagem ignorada (contato pausado): {message.from_number}")
        return {"status": "ignored_contact_paused", "phone": message.from_number}

    # Processar em background (batch aguarda mensagens adicionais)
    # Não usa await — retorna imediatamente
    asyncio.create_task(process_incoming_message(
        message=message,
        evolution=evolution_client,
        hermes=hermes_client,
        llm=llm_client,
        stt=stt_client,
        use_hermes=True,
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


# ── Test Mode ──────────────────────────────────────────────────────

TEST_MODE_FILE = "/app/data/test_mode.json"

def load_test_mode():
    """Carrega modo teste de arquivo."""
    if os.path.exists(TEST_MODE_FILE):
        try:
            with open(TEST_MODE_FILE, "r") as f:
                data = json.load(f)
                settings.test_mode = data.get("test_mode", False)
                settings.test_numbers = data.get("test_numbers", "")
                logger.info(f"Modo teste carregado: {settings.test_mode}, números: {settings.test_numbers}")
        except Exception as e:
            logger.error(f"Erro ao carregar modo teste: {e}")

def save_test_mode():
    """Salva modo teste em arquivo."""
    try:
        with open(TEST_MODE_FILE, "w") as f:
            json.dump({
                "test_mode": settings.test_mode,
                "test_numbers": settings.test_numbers,
            }, f)
        logger.info(f"Modo teste salvo: {settings.test_mode}")
    except Exception as e:
        logger.error(f"Erro ao salvar modo teste: {e}")

@app.post("/admin/test-mode")
async def set_test_mode(enabled: bool, numbers: str = ""):
    """Habilita/desabilita modo teste."""
    settings.test_mode = enabled
    settings.test_numbers = numbers
    save_test_mode()
    return {
        "test_mode": settings.test_mode,
        "test_numbers": settings.test_numbers.split(",") if settings.test_numbers else [],
    }

@app.get("/admin/test-mode")
async def get_test_mode():
    """Verifica status do modo teste."""
    return {
        "test_mode": settings.test_mode,
        "test_numbers": settings.test_numbers.split(",") if settings.test_numbers else [],
    }



# ── Pause/Resume ──────────────────────────────────────────────────

PAUSE_FILE = "/app/data/paused_clients.json"

def load_paused_clients():
    """Carrega clientes pausados de arquivo."""
    if os.path.exists(PAUSE_FILE):
        try:
            with open(PAUSE_FILE, "r") as f:
                data = json.load(f)
                settings.paused_clients = ",".join(data.get("paused", []))
                logger.info(f"Clientes pausados carregados: {settings.paused_clients}")
        except Exception as e:
            logger.error(f"Erro ao carregar clientes pausados: {e}")

def save_paused_clients():
    """Salva clientes pausados em arquivo."""
    try:
        paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
        with open(PAUSE_FILE, "w") as f:
            json.dump({"paused": paused}, f)
        logger.info(f"Clientes pausados salvos: {paused}")
    except Exception as e:
        logger.error(f"Erro ao salvar clientes pausados: {e}")

def is_client_paused(client_name: str) -> bool:
    """Verifica se um cliente está pausado."""
    if not settings.paused_clients:
        return False
    paused = [c.strip().lower() for c in settings.paused_clients.split(",")]
    return client_name.lower() in paused

@app.post("/admin/pause")
async def pause_client(client: str):
    """Pausa um cliente."""
    paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
    if client not in paused:
        paused.append(client)
    settings.paused_clients = ",".join(paused)
    save_paused_clients()
    return {"paused": paused, "message": f"Cliente {client} pausado"}

@app.post("/admin/resume")
async def resume_client(client: str):
    """Retoma um cliente."""
    paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
    if client in paused:
        paused.remove(client)
    settings.paused_clients = ",".join(paused)
    save_paused_clients()
    return {"paused": paused, "message": f"Cliente {client} retomado"}

@app.get("/admin/pause")
async def get_paused_clients():
    """Lista clientes pausados."""
    paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
    return {"paused": paused}



# ── Contact Pause/Resume ──────────────────────────────────────────

CONTACT_PAUSE_FILE = "/app/data/paused_contacts.json"

def load_paused_contacts():
    """Carrega contatos pausados de arquivo."""
    if os.path.exists(CONTACT_PAUSE_FILE):
        try:
            with open(CONTACT_PAUSE_FILE, "r") as f:
                data = json.load(f)
                settings.paused_contacts = ",".join(data.get("paused", []))
                logger.info(f"Contatos pausados carregados: {settings.paused_contacts}")
        except Exception as e:
            logger.error(f"Erro ao carregar contatos pausados: {e}")

def save_paused_contacts():
    """Salva contatos pausados em arquivo."""
    try:
        paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
        with open(CONTACT_PAUSE_FILE, "w") as f:
            json.dump({"paused": paused}, f)
        logger.info(f"Contatos pausados salvos: {paused}")
    except Exception as e:
        logger.error(f"Erro ao salvar contatos pausados: {e}")

def is_contact_paused(client: str, phone: str) -> bool:
    """Verifica se um contato específico está pausado."""
    if not settings.paused_contacts:
        return False
    paused = [c.strip().lower() for c in settings.paused_contacts.split(",")]
    # Formato: "client:phone" ou apenas "phone"
    contact_key = f"{client}:{phone}".lower()
    return contact_key in paused or phone.lower() in paused

@app.post("/admin/pause-contact")
async def pause_contact(client: str, phone: str):
    """Pausa um contato específico."""
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"{client}:{phone}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    save_paused_contacts()
    return {"paused": paused, "message": f"Contato {phone} pausado para {client}"}

@app.post("/admin/resume-contact")
async def resume_contact(client: str, phone: str):
    """Retoma um contato específico."""
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"{client}:{phone}"
    if contact_key in paused:
        paused.remove(contact_key)
    settings.paused_contacts = ",".join(paused)
    save_paused_contacts()
    return {"paused": paused, "message": f"Contato {phone} retomado para {client}"}

@app.get("/admin/pause-contact")
async def get_paused_contacts():
    """Lista contatos pausados."""
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    return {"paused": paused}

@app.post("/admin/transfer-to-human")
async def transfer_to_human(client: str, phone: str, reason: str = ""):
    """Transfere contato para atendente humano (pausa automaticamente)."""
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"{client}:{phone}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    save_paused_contacts()
    
    # Enviar mensagem de transferência
    try:
        await evolution_client.send_text(
            to_number=phone,
            message=f"Transferindo para um atendente humano. {reason}" if reason else "Transferindo para um atendente humano. Aguarde um momento.",
            instance=client,
        )
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem de transferência: {e}")
    
    return {"paused": paused, "message": f"Contato {phone} transferido para humano"}




@app.post("/admin/send")
async def admin_send_message(client: str, phone: str, message: str):
    """Envia mensagem manualmente para um contato."""
    try:
        result = await evolution_client.send_text(
            to_number=phone,
            message=message,
            instance=client,
        )
        return {"status": "sent", "message_id": result.get("key", {}).get("id", "")}
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
        return {"status": "error", "error": str(e)}


@app.get("/admin/metrics")
async def get_metrics():
    """Retorna métricas do sistema."""
    import time
    uptime = time.time() - _start_time
    return {
        "uptime_seconds": uptime,
        "uptime_human": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m",
        "test_mode": settings.test_mode,
        "paused_clients": len([c for c in settings.paused_clients.split(",") if c.strip()]) if settings.paused_clients else 0,
        "paused_contacts": len([c for c in settings.paused_contacts.split(",") if c.strip()]) if settings.paused_contacts else 0,
    }


@app.get("/admin/config")
async def get_config():
    """Retorna configurações atuais."""
    return {
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "human_delay_enabled": settings.human_delay_enabled,
        "human_delay_min": settings.human_delay_min,
        "human_delay_max": settings.human_delay_max,
        "batch_wait_seconds": settings.batch_wait_seconds,
        "batch_max_wait": settings.batch_max_wait,
        "log_level": settings.log_level,
    }

@app.post("/admin/config")
async def update_config(
    rate_limit_per_minute: int = None,
    human_delay_enabled: bool = None,
    human_delay_min: float = None,
    human_delay_max: float = None,
    batch_wait_seconds: float = None,
    batch_max_wait: float = None,
    log_level: str = None,
):
    """Atualiza configurações."""
    if rate_limit_per_minute is not None:
        settings.rate_limit_per_minute = rate_limit_per_minute
    if human_delay_enabled is not None:
        settings.human_delay_enabled = human_delay_enabled
    if human_delay_min is not None:
        settings.human_delay_min = human_delay_min
    if human_delay_max is not None:
        settings.human_delay_max = human_delay_max
    if batch_wait_seconds is not None:
        settings.batch_wait_seconds = batch_wait_seconds
    if batch_max_wait is not None:
        settings.batch_max_wait = batch_max_wait
    if log_level is not None:
        settings.log_level = log_level
    
    return {"status": "updated", "config": await get_config()}


@app.get("/admin/sessions")
async def get_sessions():
    """Retorna sessões ativas."""
    sessions = hermes_client.get_active_sessions() if hasattr(hermes_client, 'get_active_sessions') else []
    return {"sessions": sessions}

@app.get("/dashboard")
async def dashboard():
    """Dashboard web para gerenciamento."""
    from fastapi.responses import HTMLResponse
    dashboard_path = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Dashboard não encontrado</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

# ── Outreach Routes ─────────────────────────────────────────────
from outreach import router as outreach_router
app.include_router(outreach_router)


@app.get("/outreach")
async def outreach_page():
    """Página de outreach"""
    from fastapi.responses import HTMLResponse
    outreach_path = os.path.join(os.path.dirname(__file__), "static", "outreach.html")
    if os.path.exists(outreach_path):
        with open(outreach_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Página não encontrada</h1>", status_code=404)

