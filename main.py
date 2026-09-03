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
from fastapi.responses import HTMLResponse
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
from services.database import get_supabase, get_client, select, upsert, insert, ensure_supabase
# ── Auth helpers ──────────────────────────────────────────────
from routes.routes_auth import COOKIE_NAME, _verify_supabase_token
from routes.deps import get_current_user


# ── Supabase tables ─────────────────────────────────────────────
CONVERSATIONS_TABLE = "bcomm_inbox.conversations"
MESSAGES_TABLE = "bcomm_inbox.messages"

def _ensure_supabase():
    """Inicializa Supabase se ainda não estiver conectado."""
    from services.database import ensure_supabase as _es
    _es()

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

TABLE_SETTINGS = "settings"


# ── Settings helpers (Supabase) ─────────────────────────────────────

async def _load_setting(key: str, default=None):
    """Carrega um setting do Supabase."""
    try:
        rows = await select(TABLE_SETTINGS, filters={"key": key})
        if rows:
            return rows[0]["value"]
    except Exception as e:
        logger.error(f"Erro ao carregar setting '{key}': {e}")
    return default


async def _save_setting(key: str, value):
    """Salva um setting no Supabase."""
    try:
        from datetime import datetime
        await upsert(TABLE_SETTINGS, {
            "key": key,
            "value": value,
            "updated_at": datetime.now().isoformat(),
        }, on_conflict="key")
    except Exception as e:
        logger.error(f"Erro ao salvar setting '{key}': {e}")


async def load_test_mode():
    """Carrega modo teste do Supabase."""
    data = await _load_setting("test_mode", {"test_mode": False, "test_numbers": ""})
    settings.test_mode = data.get("test_mode", False)
    settings.test_numbers = data.get("test_numbers", "")
    logger.info(f"Modo teste carregado: {settings.test_mode}, números: {settings.test_numbers}")


async def save_test_mode():
    """Salva modo teste no Supabase."""
    await _save_setting("test_mode", {
        "test_mode": settings.test_mode,
        "test_numbers": settings.test_numbers,
    })
    logger.info(f"Modo teste salvo: {settings.test_mode}")


async def load_paused_clients():
    """Carrega clientes pausados do Supabase."""
    data = await _load_setting("paused_clients", {"paused": []})
    paused = data.get("paused", [])
    settings.paused_clients = ",".join(paused)
    logger.info(f"Clientes pausados carregados: {settings.paused_clients}")


async def save_paused_clients():
    """Salva clientes pausados no Supabase."""
    paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
    await _save_setting("paused_clients", {"paused": paused})
    logger.info(f"Clientes pausados salvos: {paused}")


async def load_paused_contacts():
    """Carrega contatos pausados do Supabase."""
    data = await _load_setting("paused_contacts", {"paused": []})
    paused = data.get("paused", [])
    settings.paused_contacts = ",".join(paused)
    logger.info(f"Contatos pausados carregados: {settings.paused_contacts}")


async def save_paused_contacts():
    """Salva contatos pausados no Supabase."""
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    await _save_setting("paused_contacts", {"paused": paused})
    logger.info(f"Contatos pausados salvos: {paused}")


def is_client_paused(client_name: str) -> bool:
    """Verifica se um cliente está pausado."""
    if not settings.paused_clients:
        return False
    paused = [c.strip().lower() for c in settings.paused_clients.split(",")]
    return client_name.lower() in paused


def is_contact_paused(client: str, phone: str) -> bool:
    """Verifica se um contato específico está pausado."""
    if not settings.paused_contacts:
        return False
    paused = [c.strip().lower() for c in settings.paused_contacts.split(",")]
    # Formato: "client:phone" ou apenas "phone"
    contact_key = f"{client}:{phone}".lower()
    return contact_key in paused or phone.lower() in paused


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

    # Initialize Supabase
    logger.info("📦 Conectando ao Supabase...")
    get_supabase(settings.supabase_url, settings.supabase_service_key)

    # Validate JWT secret
    if not settings.jwt_secret:
        logger.warning("⚠️  JWT_SECRET não configurada — usando fallback (gere um secret para produção)")

    # Load settings from Supabase
    await load_test_mode()
    await load_paused_clients()
    await load_paused_contacts()

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

_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth Middleware ────────────────────────────────────────────
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Protege rotas /crm/* que não são de auth."""
    from fastapi.responses import JSONResponse, RedirectResponse
    path = request.url.path

    # Rotas públicas (não precisam de auth)
    public_exact = {"/login", "/health", "/docs", "/openapi.json", "/redoc", "/",
                    "/dashboard", "/config", "/pipelines", "/organizations",
                    "/setup-master", "/crm", "/contacts", "/activities", "/users", "/agents", "/notes"}
    public_prefixes = ("/webhook/", "/health", "/docs", "/openapi", "/redoc", "/invite/", "/crm/auth/accept-invite")
    crm_auth_exact = {"/crm/auth/login"}

    # Checar se é pública
    if path in public_exact or path in crm_auth_exact:
        return await call_next(request)

    for prefix in public_prefixes:
        if path.startswith(prefix):
            return await call_next(request)

    # Proteger /crm/* (exceto arquivos estáticos e áudio)
    if path.startswith("/crm"):
        # Pular proteção para áudio, profile-picture, e arquivos .html
        skip_auth = any(x in path for x in ["/audio/", "/profile-picture/", ".html"])
        if not skip_auth:
            token = request.cookies.get(COOKIE_NAME)
            if not token:
                auth_header = request.headers.get("authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]

            if not token:
                # API call → 401; page → redirect
                if request.headers.get("accept", "").find("json") >= 0 or request.url.path.startswith("/crm/") and not any(x in path for x in [".html", "/audio/", "/profile-picture/"]):
                    return JSONResponse(status_code=401, content={"detail": "Não autenticado"})
                return RedirectResponse(url="/login", status_code=302)

            payload = await _verify_supabase_token(token)
            if not payload:
                if request.headers.get("accept", "").find("json") >= 0 or request.url.path.startswith("/crm/") and not any(x in path for x in [".html", "/audio/", "/profile-picture/"]):
                    return JSONResponse(status_code=401, content={"detail": "Sessão expirada"})
                return RedirectResponse(url="/login", status_code=302)

    return await call_next(request)



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


async def _save_audio_for_disabled(message, msg_id: str):
    """Download, decrypt, transcribe and save audio file when agent is disabled."""
    import os
    try:
        if not message.media_cdn_url:
            return

        client = await evolution_client._get_client()
        resp = await client.get(message.media_cdn_url)
        resp.raise_for_status()
        encrypted_data = resp.content
        logger.info(f"[disabled] Áudio encriptado baixado: {len(encrypted_data)} bytes")

        import ast
        mk_dict = ast.literal_eval(message.media_url)
        media_key = bytes(mk_dict.values())

        from services.whatsapp_crypto import decrypt_whatsapp_audio
        audio_bytes = decrypt_whatsapp_audio(encrypted_data, media_key)
        logger.info(f"[disabled] Áudio desencriptado: {len(audio_bytes)} bytes")

        audio_dir = "/app/data/audio"
        os.makedirs(audio_dir, exist_ok=True)

        # Save audio file
        audio_path = os.path.join(audio_dir, f"{msg_id}.ogg")
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)
        logger.info(f"[disabled] Áudio salvo em {audio_path}")

        # Transcribe and save transcription (reuse global stt_client)
        try:
            transcription = await stt_client.transcribe(audio_bytes=audio_bytes, filename="audio.ogg", language="pt")
            if transcription:
                txt_path = os.path.join(audio_dir, f"{msg_id}.txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(transcription)
                logger.info(f"[disabled] Transcrição salva: {txt_path} ({len(transcription)} chars)")
        except Exception as e:
            logger.error(f"[disabled] Erro ao transcrever: {e}")

    except Exception as e:
        logger.error(f"[disabled] Erro ao salvar áudio: {e}")


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

    # Verificar se o agente está desabilitado para esta conversa
    try:
        _ensure_supabase()
        conv_rows = await select(CONVERSATIONS_TABLE, filters={"phone": message.from_number})
        if conv_rows and not conv_rows[0].get("agent_enabled", True):
            logger.info(f"Mensagem ignorada (agente desabilitado): {message.from_number}")
            # Still register the message in Supabase for the inbox
            conv_id = conv_rows[0]["id"]
            from datetime import datetime as _dt
            # Use [audioMessage] for audio type so UI shows player
            content = "[audioMessage]" if message.message_type == "audio" else message.content
            msg_id = message.message_id if message.message_id else None
            await insert(MESSAGES_TABLE, {
                "conversation_id": conv_id,
                "sender": "user",
                "content": content,
                "message_id": msg_id,
                "responded": False,
                "created_at": _dt.now().isoformat(),
            })
            # Process audio file even when agent is disabled (for UI playback)
            if message.message_type == "audio" and msg_id:
                asyncio.create_task(_save_audio_for_disabled(message, msg_id))
            return {"status": "ignored_agent_disabled", "phone": message.from_number}
    except Exception as e:
        logger.error(f"Erro ao verificar agente_enabled: {e}")

    # ── SAVE USER MESSAGE IMMEDIATELY (for real-time inbox) ──
    try:
        from datetime import datetime as _dt_now
        _ensure_supabase()
        if get_client() is not None:
            conv_rows_imm = await select(CONVERSATIONS_TABLE, filters={"phone": message.from_number})
            if conv_rows_imm:
                _cid = conv_rows_imm[0]["id"]
                _mid = message.message_id if message.message_id else None
                if _mid:
                    _existing = await select(MESSAGES_TABLE, filters={"message_id": _mid})
                    if not _existing:
                        _ct = "[audioMessage]" if message.message_type == "audio" else (message.content or "")
                        await insert(MESSAGES_TABLE, {
                            "conversation_id": _cid,
                            "sender": "user",
                            "content": _ct,
                            "message_id": _mid,
                            "responded": False,
                            "created_at": _dt_now.now().isoformat(),
                        })
                        logger.info(f"IMMEDIATE SAVE: User msg saved for {message.from_number} msg_id={_mid}")
    except Exception as e:
        logger.error(f"Immediate save FAILED: {type(e).__name__}: {e}")

    # Processar em background (batch aguarda mensagens adicionais)
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
async def send_message(request: Request, req: SendMessageRequest):
    """
    Enviar mensagem manualmente via Evolution API.
    """
    user = await get_current_user(request)
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
async def clear_sessions(request: Request, phone: Optional[str] = None):
    """
    Limpa sessões do Hermes.
    Se phone for especificado, limpa apenas essa sessão.
    Caso contrário, limpa todas.
    """
    user = await get_current_user(request)
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
async def reload_clients(request: Request):
    """Recarrega configurações de clientes."""
    user = await get_current_user(request)
    client_loader.reload()
    return {"status": "reloaded", "count": client_loader.client_count}


# ── Test Mode ──────────────────────────────────────────────────────

@app.post("/admin/test-mode")
async def set_test_mode(request: Request, enabled: bool, numbers: str = ""):
    """Habilita/desabilita modo teste."""
    user = await get_current_user(request)
    settings.test_mode = enabled
    settings.test_numbers = numbers
    await save_test_mode()
    return {
        "test_mode": settings.test_mode,
        "test_numbers": settings.test_numbers.split(",") if settings.test_numbers else [],
    }

@app.get("/admin/test-mode")
async def get_test_mode(request: Request):
    """Verifica status do modo teste."""
    user = await get_current_user(request)
    return {
        "test_mode": settings.test_mode,
        "test_numbers": settings.test_numbers.split(",") if settings.test_numbers else [],
    }


# ── Pause/Resume ──────────────────────────────────────────────────

@app.post("/admin/pause")
async def pause_client(request: Request, client: str):
    """Pausa um cliente."""
    user = await get_current_user(request)
    paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
    if client not in paused:
        paused.append(client)
    settings.paused_clients = ",".join(paused)
    await save_paused_clients()
    return {"paused": paused, "message": f"Cliente {client} pausado"}

@app.post("/admin/resume")
async def resume_client(request: Request, client: str):
    """Retoma um cliente."""
    user = await get_current_user(request)
    paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
    if client in paused:
        paused.remove(client)
    settings.paused_clients = ",".join(paused)
    await save_paused_clients()
    return {"paused": paused, "message": f"Cliente {client} retomado"}

@app.get("/admin/pause")
async def get_paused_clients(request: Request):
    """Lista clientes pausados."""
    user = await get_current_user(request)
    paused = [c.strip() for c in settings.paused_clients.split(",") if c.strip()]
    return {"paused": paused}


# ── Contact Pause/Resume ──────────────────────────────────────────

@app.post("/admin/pause-contact")
async def pause_contact(request: Request, client: str, phone: str):
    """Pausa um contato específico."""
    user = await get_current_user(request)
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"{client}:{phone}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    await save_paused_contacts()
    return {"paused": paused, "message": f"Contato {phone} pausado para {client}"}

@app.post("/admin/resume-contact")
async def resume_contact(request: Request, client: str, phone: str):
    """Retoma um contato específico."""
    user = await get_current_user(request)
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"{client}:{phone}"
    if contact_key in paused:
        paused.remove(contact_key)
    settings.paused_contacts = ",".join(paused)
    await save_paused_contacts()
    return {"paused": paused, "message": f"Contato {phone} retomado para {client}"}

@app.get("/admin/pause-contact")
async def get_paused_contacts(request: Request):
    """Lista contatos pausados."""
    user = await get_current_user(request)
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    return {"paused": paused}

@app.post("/admin/transfer-to-human")
async def transfer_to_human(request: Request):
    """Transfere contato para atendente humano (pausa automaticamente)."""
    user = await get_current_user(request)
    body = await request.json()
    phone = body.get("phone", "")
    reason = body.get("reason", "")
    client = body.get("client", settings.evolution_instance)

    if not phone:
        raise HTTPException(status_code=400, detail="Phone é obrigatório")

    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"{client}:{phone}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    await save_paused_contacts()
    
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
async def admin_send_message(request: Request, client: str, phone: str, message: str):
    """Envia mensagem manualmente para um contato."""
    user = await get_current_user(request)
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
async def get_metrics(request: Request):
    """Retorna métricas do sistema."""
    user = await get_current_user(request)
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
async def get_config(request: Request):
    """Retorna configurações atuais."""
    user = await get_current_user(request)
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
    request: Request,
    rate_limit_per_minute: int = None,
    human_delay_enabled: bool = None,
    human_delay_min: float = None,
    human_delay_max: float = None,
    batch_wait_seconds: float = None,
    batch_max_wait: float = None,
    log_level: str = None,
):
    """Atualiza configurações."""
    user = await get_current_user(request)
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
    
    return {"status": "updated", "config": await get_config(request)}


@app.get("/admin/sessions")
async def get_sessions(request: Request):
    """Retorna sessões ativas."""
    user = await get_current_user(request)
    sessions = await hermes_client.get_active_sessions() if hasattr(hermes_client, 'get_active_sessions') else []
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



@app.get("/organizations")
async def organizations_page():
    """Pagina de gestao de organizacoes."""
    from fastapi.responses import HTMLResponse
    org_path = os.path.join(os.path.dirname(__file__), "static", "organizations.html")
    if os.path.exists(org_path):
        with open(org_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Pagina nao encontrada</h1>", status_code=404)

# ── Login Page ────────────────────────────────────────────────
@app.get("/login")
async def login_page():
    """Página de login."""
    login_path = os.path.join(os.path.dirname(__file__), "static", "login.html")
    if os.path.exists(login_path):
        with open(login_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Página de login não encontrada</h1>", status_code=404)


@app.post("/setup-master")
async def setup_master():
    """Cria usuário master inicial se não existir. Requer MASTER_PASSWORD configurada."""
    from datetime import datetime, timezone
    from routes.routes_users import _hash_password

    if not settings.master_password:
        raise HTTPException(
            status_code=400,
            detail="MASTER_PASSWORD não configurada. Defina a variável de ambiente MASTER_PASSWORD.",
        )

    _ensure_supabase()

    # Verificar se já existe master
    rows = await select("bcomm_inbox.users", filters={"role": "master"})
    if rows:
        return {"status": "exists", "message": "Usuário master já existe"}

    # Criar master
    now = datetime.now(timezone.utc).isoformat()
    master = {
        "email": settings.master_email,
        "name": "Admin Master",
        "password_hash": _hash_password(settings.master_password),
        "role": "master",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    await insert("bcomm_inbox.users", master)
    logger.info("Usuário master criado via /setup-master")

    return {
        "status": "created",
        "message": "Usuário master criado. Altere a senha após o primeiro login.",
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

# ── CRM Routes ─────────────────────────────────────────────
from crm_routes import router as crm_router
app.include_router(crm_router)


@app.get("/crm")
async def crm_page():
    """Página CRM completa."""
    from fastapi.responses import HTMLResponse
    crm_path = os.path.join(os.path.dirname(__file__), "static", "crm.html")
    if os.path.exists(crm_path):
        with open(crm_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>CRM não encontrado</h1>", status_code=404)


@app.get("/contacts")
async def contacts_page():
    """Página de contatos."""
    from fastapi.responses import HTMLResponse
    path = os.path.join(os.path.dirname(__file__), "static", "contacts.html")
    if os.path.exists(path):
        with open(path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Página não encontrada</h1>", status_code=404)


@app.get("/activities")
async def activities_page():
    """Página de atividades."""
    from fastapi.responses import HTMLResponse
    path = os.path.join(os.path.dirname(__file__), "static", "activities.html")
    if os.path.exists(path):
        with open(path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Página não encontrada</h1>", status_code=404)


@app.get("/users")
async def users_page():
    """Página de gestão de usuários."""
    from fastapi.responses import HTMLResponse
    path = os.path.join(os.path.dirname(__file__), "static", "users.html")
    if os.path.exists(path):
        with open(path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Página não encontrada</h1>", status_code=404)


@app.get("/agents")
async def agents_page():
    """Página de gestão de agentes."""
    from fastapi.responses import HTMLResponse
    path = os.path.join(os.path.dirname(__file__), "static", "agents.html")
    if os.path.exists(path):
        with open(path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Página não encontrada</h1>", status_code=404)


@app.get("/notes")
async def notes_page():
    """Página de notas."""
    from fastapi.responses import HTMLResponse
    path = os.path.join(os.path.dirname(__file__), "static", "notes.html")
    if os.path.exists(path):
        with open(path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Página não encontrada</h1>", status_code=404)


@app.get("/invite/{token}")
async def invite_page(token: str):
    """Página de aceitação de convite."""
    from fastapi.responses import HTMLResponse
    path = os.path.join(os.path.dirname(__file__), "static", "invite.html")
    if os.path.exists(path):
        with open(path, "r") as f:
            return HTMLResponse(content=f.read().replace("{{TOKEN}}", token))
    return HTMLResponse(content="<h1>Página não encontrada</h1>", status_code=404)






@app.get("/config")
async def config_page():
    """Página de configurações"""
    from fastapi.responses import HTMLResponse
    config_path = os.path.join(os.path.dirname(__file__), "static", "config.html")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Config não encontrado</h1>", status_code=404)

@app.get("/pipelines")
async def pipelines_page():
    """Página de pipelines"""
    from fastapi.responses import HTMLResponse
    pipelines_path = os.path.join(os.path.dirname(__file__), "static", "pipelines.html")
    if os.path.exists(pipelines_path):
        with open(pipelines_path, "r") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>Pipelines não encontrado</h1>", status_code=404)


# ── Novos módulos CRM ─────────────────────────────────────────
from routes.routes_auth import router as auth_router
app.include_router(auth_router)

from routes.routes_users import router as users_router
app.include_router(users_router)

from routes.routes_contacts import router as contacts_router
app.include_router(contacts_router)

from routes.routes_orgs import router as orgs_router
app.include_router(orgs_router)

from routes.routes_deals import router as deals_router
app.include_router(deals_router)

from routes.routes_activities import router as activities_router
app.include_router(activities_router)

from routes.routes_notes import router as notes_router
app.include_router(notes_router)

from routes.routes_tags import router as tags_router
app.include_router(tags_router)

from routes.routes_pipelines import router as pipelines_router
app.include_router(pipelines_router)

from routes.routes_search import router as search_router
from routes.routes_whatsapp import router as whatsapp_router

app.include_router(search_router)
app.include_router(whatsapp_router)


from routes.routes_themes import router as themes_router
app.include_router(themes_router)

from routes.routes_agents import router as agents_router
app.include_router(agents_router)

@app.get("/realtime.js")
async def realtime_js():
    from fastapi.responses import FileResponse, HTMLResponse
    import os
    path = os.path.join(os.path.dirname(__file__), "static", "realtime.js")
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read()
        return HTMLResponse(content=content, media_type="application/javascript")
    return HTMLResponse(content="// not found", status_code=404, media_type="application/javascript")
