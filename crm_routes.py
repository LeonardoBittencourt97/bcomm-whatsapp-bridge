"""
Rotas do CRM - BCOMM Atendimento
Endpoints para gerenciamento de conversas
Endpoints para gerenciamento de pipeline de deals
Usa Supabase para persistência (tabelas bcomm_inbox.*)
"""
import json
import os
import uuid
import logging
import httpx
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from config import settings
from services.evolution import EvolutionClient
from services.database import get_supabase, get_client, select, insert, update, upsert, delete
from routes.deps import get_current_user, apply_org_filter, is_unrestricted, get_user_org_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm", tags=["crm"])

# Evolution API client for sending messages
evolution_client = EvolutionClient()

# Supabase tables
CONVERSATIONS_TABLE = "bcomm_inbox.conversations"
MESSAGES_TABLE = "bcomm_inbox.messages"
SESSIONS_TABLE = "bcomm_inbox.sessions"
DEALS_TABLE = "bcomm_inbox.deals"
PIPELINE_STAGES_TABLE = "bcomm_inbox.pipeline_stages"


# ── Helpers ─────────────────────────────────────────────────────

def _ensure_supabase():
    """Inicializa Supabase se ainda não estiver conectado."""
    from services.database import ensure_supabase as _es
    _es()


async def _get_or_create_conversation(phone: str) -> dict:
    """Busca ou cria conversa no Supabase"""
    _ensure_supabase()

    # Buscar conversa existente
    rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})

    if rows:
        return rows[0]

    # Buscar session_id do Hermes
    session_rows = await select(SESSIONS_TABLE, columns="session_id", filters={"phone": phone})
    session_id = session_rows[0]["session_id"] if session_rows else ""

    # Criar nova conversa
    now = datetime.now().isoformat()
    new_conv = {
        "phone": phone,
        "session_id": session_id,
        "status": "open",
        "agent_enabled": True,
        "client_name": "",
        "client_id": "",
    }
    result = await insert(CONVERSATIONS_TABLE, new_conv)
    if result:
        logger.info(f"Nova conversa criada no Supabase: {phone}")
        return result[0] if isinstance(result, list) else result
    return new_conv


async def _insert_message(conversation_id: str, sender: str, content: str, model: str = "", responded: bool = True, message_id: str = "") -> dict:
    """Insere uma mensagem no Supabase"""
    _ensure_supabase()

    msg_data = {
        "conversation_id": conversation_id,
        "sender": sender,
        "content": content,
        "model": model if model else None,
        "responded": responded,
        "message_id": message_id if message_id else None,
    }
    result = await insert(MESSAGES_TABLE, msg_data)
    if result:
        return result[0] if isinstance(result, list) else result
    return msg_data


async def _get_messages(conversation_id: str, limit: int = 100) -> list:
    """Busca mensagens de uma conversa"""
    _ensure_supabase()

    rows = await select(
        MESSAGES_TABLE,
        filters={"conversation_id": conversation_id},
        order="created_at.asc",
        limit=limit,
    )
    return rows or []


async def _check_conversation_access(conv: dict, user: dict):
    """Verifica se o usuário tem acesso à organização da conversa."""
    if is_unrestricted(user):
        return
    org_ids = await get_user_org_ids(user["id"])
    conv_org = conv.get("organization_id")
    if conv_org and conv_org not in org_ids:
        raise HTTPException(status_code=403, detail="Sem acesso a esta conversa")


async def _assign_org_to_conversation(conv_id: str, user: dict):
    """Atribui organization_id à conversa baseado no org do usuário (se não restrito)."""
    if is_unrestricted(user):
        return
    org_ids = await get_user_org_ids(user["id"])
    if org_ids:
        await update(CONVERSATIONS_TABLE, {"organization_id": list(org_ids)[0]}, filters={"id": conv_id})


# ── Audio Storage (in-memory with size limit) ─────────────────
import base64
from collections import OrderedDict
from fastapi.responses import Response as FastAPIResponse

_audio_cache: OrderedDict[str, bytes] = OrderedDict()
_AUDIO_CACHE_MAX = 100  # ponytail: 100 entries, upgrade to Redis if memory pressure


def _cache_get(key: str) -> bytes | None:
    if key in _audio_cache:
        _audio_cache.move_to_end(key)
        return _audio_cache[key]
    return None


def _cache_put(key: str, value: bytes):
    if key in _audio_cache:
        _audio_cache.move_to_end(key)
    else:
        if len(_audio_cache) >= _AUDIO_CACHE_MAX:
            _audio_cache.popitem(last=False)
        _audio_cache[key] = value


# ── Audio & Transcription Endpoints ────────────────────────────

@router.get("/audio/{msg_id}")
async def get_audio(msg_id: str):
    """Retorna arquivo de áudio para reprodução no player."""
    import os

    # Check in-memory cache first
    cached = _cache_get(msg_id)
    if cached is not None:
        return FastAPIResponse(content=cached, media_type="audio/ogg")

    # Check file system (saved during processing)
    audio_path = f"/app/data/audio/{msg_id}.ogg"
    if os.path.exists(audio_path):
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        _cache_put(msg_id, audio_bytes)
        return FastAPIResponse(content=audio_bytes, media_type="audio/ogg")

    # Try to fetch from Evolution API (for old messages)
    try:
        client = await evolution_client._get_client()
        from urllib.parse import quote
        resp = await client.get(f"/chat/downloadMedia/{settings.evolution_instance}/{quote(msg_id, safe='')}")
        if resp.status_code == 200:
            _cache_put(msg_id, resp.content)
            return FastAPIResponse(content=resp.content, media_type="audio/ogg")
    except Exception as e:
        logger.error(f"Erro ao buscar áudio {msg_id}: {e}")

    raise HTTPException(status_code=404, detail="Áudio não encontrado")


@router.post("/transcribe/{msg_id}")
async def transcribe_message(msg_id: str):
    """Transcreve uma mensagem de áudio on-demand."""
    from services.stt import STTClient
    import os

    _ensure_supabase()

    # Check if already transcribed (cached in memory)
    cached_key = f"transcription_{msg_id}"
    cached_val = _cache_get(cached_key)
    if cached_val is not None:
        return {"transcription": cached_val.decode(), "cached": True}

    # Check for transcription file on disk
    txt_path = f"/app/data/audio/{msg_id}.txt"
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            transcription = f.read()
        _cache_put(cached_key, transcription.encode())
        return {"transcription": transcription, "cached": True}

    # Check if DB content is already a transcription (not [audioMessage])
    rows = await select(MESSAGES_TABLE, filters={"message_id": msg_id})
    if rows:
        msg = rows[0]
        content = msg.get("content", "")
        if content and not content.startswith("[audioMessage"):
            return {"transcription": content, "cached": True}

    # Get audio bytes - try file system first
    audio_bytes = _cache_get(msg_id)
    if not audio_bytes:
        audio_path = f"/app/data/audio/{msg_id}.ogg"
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            _cache_put(msg_id, audio_bytes)

    # Try Evolution API as last resort
    if not audio_bytes:
        try:
            client = await evolution_client._get_client()
            from urllib.parse import quote
            resp = await client.get(f"/chat/downloadMedia/{settings.evolution_instance}/{quote(msg_id, safe='')}")
            if resp.status_code == 200:
                audio_bytes = resp.content
                _cache_put(msg_id, audio_bytes)
        except Exception:
            pass

    if not audio_bytes:
        return {"error": "Áudio não encontrado"}

    # Transcribe
    stt = STTClient()
    try:
        transcription = await stt.transcribe(audio_bytes=audio_bytes, filename="audio.ogg", language="pt")
        if transcription:
            # Cache in memory
            _cache_put(f"transcription_{msg_id}", transcription.encode())
            # Save to disk for persistence
            try:
                txt_path = f"/app/data/audio/{msg_id}.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(transcription)
                logger.info(f"Transcrição salva em {txt_path}")
            except Exception as e:
                logger.error(f"Erro ao salvar transcrição em disco: {e}")
            return {"transcription": transcription, "cached": False}
    except Exception as e:
        logger.error(f"Erro ao transcrever {msg_id}: {e}")
    finally:
        await stt.close()

    return {"error": "Falha na transcrição"}


@router.get("/search")
async def search_messages(q: str, http_request: Request, phone: Optional[str] = None, limit: int = Query(default=50, le=200)):
    """
    Busca mensagens por texto (inclui transcrições de áudio).

    Query params:
    - q: Texto para buscar
    - phone: Filtrar por telefone específico (opcional)
    - limit: Limite de resultados (default: 50)
    """
    _ensure_supabase()
    user = await get_current_user(http_request)
    user_org_ids = set() if is_unrestricted(user) else await get_user_org_ids(user["id"])

    # Search in messages table
    all_msgs = await select(MESSAGES_TABLE, order="created_at.desc", limit=500)
    results = []

    for msg in (all_msgs or []):
        content = msg.get("content", "")
        # Skip empty or audio placeholder messages
        if not content or content.startswith("[audioMessage"):
            # Check for transcription file
            msg_id = msg.get("message_id", "")
            if msg_id:
                txt_path = f"/app/data/audio/{msg_id}.txt"
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        content = f.read()
                else:
                    continue
            else:
                continue

        # Filter by phone if specified
        if phone:
            conv = await select(CONVERSATIONS_TABLE, filters={"id": msg.get("conversation_id", "")})
            if not conv or conv[0].get("phone") != phone:
                continue

        # Check if search term matches
        if q.lower() in content.lower():
            # Get conversation info for context
            conv = await select(CONVERSATIONS_TABLE, filters={"id": msg.get("conversation_id", "")})
            if not conv:
                continue
            # Filter by user's orgs
            if not is_unrestricted(user) and user_org_ids:
                conv_org = conv[0].get("organization_id")
                if conv_org and conv_org not in user_org_ids:
                    continue
            phone_num = conv[0].get("phone", "")
            results.append({
                "message_id": msg.get("message_id", ""),
                "phone": phone_num,
                "sender": msg.get("sender", ""),
                "content": content[:200],
                "created_at": msg.get("created_at", ""),
                "conversation_id": msg.get("conversation_id", ""),
            })

            if len(results) >= limit:
                break

    return {"results": results, "total": len(results), "query": q}


@router.get("/status/{phone}")
async def get_processing_status(phone: str):
    """Retorna status de processamento de uma conversa."""
    # Access the global hermes_client from main.py
    import main
    hermes = main.hermes_client
    status = hermes.get_processing_status(phone)
    return status


@router.get("/profile-picture/{phone}")
async def get_profile_picture(phone: str):
    """Busca foto de perfil do WhatsApp via Evolution API."""
    try:
        client = await evolution_client._get_client()
        resp = await client.post(
            f"/chat/fetchProfilePictureUrl/{settings.evolution_instance}",
            json={"number": phone}
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"url": data.get("profilePictureUrl", "")}
    except Exception as e:
        logger.error(f"Erro ao buscar foto de perfil: {e}")
    return {"url": ""}


# ── Models ──────────────────────────────────────────────────────

class Message(BaseModel):
    """Mensagem na conversa"""
    id: str = ""
    sender: str = "user"  # user, agent, manual
    content: str = ""
    timestamp: str = ""
    model: str = ""
    responded: bool = True


class SendMessageRequest(BaseModel):
    """Request para enviar mensagem"""
    content: str
    message_id: Optional[str] = None


# ── Pipeline / Deals Models ────────────────────────────────────

class PipelineStageCreate(BaseModel):
    """Request para criar estágio do pipeline"""
    id: str  # ex: "lead", "qualified" (VARCHAR, não auto-gerado)
    name: str
    position: int = 0
    color: str = "#3b9eff"


class PipelineStageUpdate(BaseModel):
    """Request para atualizar estágio do pipeline"""
    name: Optional[str] = None
    position: Optional[int] = None
    color: Optional[str] = None


class DealCreate(BaseModel):
    """Request para criar deal (campos do schema real bcomm_inbox.deals)"""
    title: str
    phone: Optional[str] = None
    contact_name: str = ""
    value: float = 0.0
    currency: str = "BRL"
    stage: str = "lead"  # ID do estágio (lead, qualified, proposal, etc.)
    tags: List[str] = []
    notes: str = ""
    conversation_id: Optional[str] = None
    lead_id: Optional[str] = None


class DealUpdate(BaseModel):
    """Request para atualizar/mover deal"""
    title: Optional[str] = None
    phone: Optional[str] = None
    contact_name: Optional[str] = None
    value: Optional[float] = None
    currency: Optional[str] = None
    stage: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    conversation_id: Optional[str] = None
    lead_id: Optional[str] = None


# ── Conversation Endpoints ─────────────────────────────────────

@router.get("/conversations")
async def get_conversations(
    request: Request,
    status: Optional[str] = None,
    agent_enabled: Optional[bool] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0)
):
    """
    Retorna lista de conversas

    Query params:
    - status: Filtrar por status (open, paused, closed)
    - agent_enabled: Filtrar por agente ativo (true/false)
    - limit: Limite de resultados (default: 50)
    - offset: Offset para paginação
    """
    _ensure_supabase()
    user = await get_current_user(request)

    # Buscar conversas com paginação
    filters = {}
    if status:
        filters["status"] = status
    if agent_enabled is not None:
        filters["agent_enabled"] = agent_enabled
    filters = await apply_org_filter(user, filters, request)

    # Buscar total antes da paginação
    all_convs = await select(
        CONVERSATIONS_TABLE,
        filters=filters if filters else None,
        order="updated_at.desc",
    )

    total = len(all_convs)
    conv_list = all_convs[offset:offset + limit]

    # Buscar todas as mensagens das conversas em uma query (evita N+1)
    conv_ids = [c["id"] for c in conv_list]
    all_messages = []
    if conv_ids:
        all_messages = await select(
            MESSAGES_TABLE,
            filters={"conversation_id": {"in": conv_ids}},
            order="created_at.asc",
            limit=1000,
        ) or []

    # Agrupar mensagens por conversation_id
    msgs_by_conv = {}
    for msg in all_messages:
        cid = msg.get("conversation_id")
        if cid not in msgs_by_conv:
            msgs_by_conv[cid] = []
        msgs_by_conv[cid].append(msg)

    # Enriquecer dados: última mensagem e contagem de não respondidas
    for conv in conv_list:
        messages = msgs_by_conv.get(conv["id"], [])

        if messages:
            last_msg = messages[-1]
            conv["last_message"] = last_msg.get("content", "")[:50]
            conv["last_message_time"] = last_msg.get("created_at", "")
        else:
            conv["last_message"] = ""
            conv["last_message_time"] = ""

        conv["unanswered_count"] = sum(
            1 for m in messages
            if m.get("sender") == "user" and not m.get("responded", True)
        )
        conv["messages"] = messages

    return {
        "conversations": conv_list,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/conversations/{phone}")
async def get_conversation(phone: str, http_request: Request):
    """Retorna conversa específica"""
    user = await get_current_user(http_request)
    conv = await _get_or_create_conversation(phone)
    await _check_conversation_access(conv, user)

    # Buscar mensagens
    messages = await _get_messages(conv["id"])
    conv["messages"] = messages

    return conv


@router.get("/conversations/{phone}/messages")
async def get_messages(phone: str, http_request: Request, limit: int = 100):
    """Retorna mensagens da conversa"""
    _ensure_supabase()
    user = await get_current_user(http_request)

    rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})
    if not rows:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv = rows[0]
    await _check_conversation_access(conv, user)
    # Buscar últimas N mensagens (mais recentes primeiro), depois inverter para ordem cronológica
    all_msgs = await _get_messages(conv["id"], limit=1000)
    recent = all_msgs[-limit:] if len(all_msgs) > limit else all_msgs

    return {
        "phone": phone,
        "messages": recent,
        "total": len(all_msgs)
    }


@router.post("/conversations/{phone}/send")
async def send_message(phone: str, body: SendMessageRequest, http_request: Request):
    """Envia mensagem manual para o cliente via Evolution API"""
    user = await get_current_user(http_request)
    conv = await _get_or_create_conversation(phone)
    await _check_conversation_access(conv, user)

    # Auto-assign organization_id para conversas novas
    if not conv.get("organization_id"):
        await _assign_org_to_conversation(conv["id"], user)

    # Enviar via Evolution API
    result = await evolution_client.send_text(
        to_number=phone,
        message=body.content,
        instance=settings.evolution_instance,
    )

    if not result.get("success"):
        logger.error(f"Falha ao enviar mensagem para {phone}: {result.get('error')}")
        return {"status": "error", "error": result.get("error", "Falha ao enviar")}

    # Inserir mensagem no Supabase
    message = await _insert_message(
        conversation_id=conv["id"],
        sender="manual",
        content=body.content,
        responded=True,
        message_id=result.get("message_id", ""),
    )

    # Mark all unanswered user messages as responded
    _ensure_supabase()
    unanswered = await select(
        MESSAGES_TABLE,
        filters={"conversation_id": conv["id"], "sender": "user"},
    )
    for m in (unanswered or []):
        if not m.get("responded", True):
            await update(MESSAGES_TABLE, {"responded": True}, filters={"id": m["id"]})

    # Atualizar updated_at da conversa
    await update(CONVERSATIONS_TABLE, {"updated_at": datetime.now().isoformat()}, filters={"id": conv["id"]})

    logger.info(f"Mensagem manual enviada para {phone}: {result.get('message_id')}")
    return {"status": "sent", "message": message, "evolution_message_id": result.get("message_id")}


@router.post("/conversations/{phone}/receive")
async def receive_message(phone: str, request: SendMessageRequest):
    """Registra mensagem recebida do cliente"""
    conv = await _get_or_create_conversation(phone)

    # Verificar se agente está habilitado
    agent_enabled = conv.get("agent_enabled", True)

    # Inserir mensagem
    message = await _insert_message(
        conversation_id=conv["id"],
        sender="user",
        content=request.content,
        responded=agent_enabled,  # Se agente desabilitado, não respondida
        message_id=request.message_id or "",
    )

    # Atualizar updated_at da conversa
    await update(CONVERSATIONS_TABLE, {"updated_at": datetime.now().isoformat()}, filters={"id": conv["id"]})

    return {
        "status": "received",
        "message": message,
        "agent_enabled": agent_enabled
    }


@router.post("/conversations/{phone}/agent-response")
async def agent_response(phone: str, request: SendMessageRequest, model: str = ""):
    """Registra resposta da IA"""
    _ensure_supabase()

    rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})
    if not rows:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv = rows[0]

    # Inserir mensagem
    message = await _insert_message(
        conversation_id=conv["id"],
        sender="agent",
        content=request.content,
        model=model,
        responded=True,
        message_id=request.message_id or "",
    )

    # Atualizar updated_at da conversa
    await update(CONVERSATIONS_TABLE, {"updated_at": datetime.now().isoformat()}, filters={"id": conv["id"]})

    return {"status": "recorded", "message": message}


@router.post("/conversations/{phone}/pause")
async def pause_conversation(phone: str, http_request: Request):
    """Pausa agente na conversa e salva contexto das últimas mensagens"""
    _ensure_supabase()
    user = await get_current_user(http_request)

    rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})
    if not rows:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv = rows[0]
    await _check_conversation_access(conv, user)
    
    # Carregar últimas mensagens para contexto
    messages = await _get_messages(conv["id"], limit=20)
    context_lines = []
    for m in messages[-10:]:
        role = "Cliente" if m.get("sender") == "user" else "Agente"
        context_lines.append(f"{role}: {m.get('content', '')[:100]}")
    context_summary = "\n".join(context_lines) if context_lines else "Nenhuma mensagem recente"
    
    # Salvar contexto na conversa
    now = datetime.now().isoformat()
    await update(CONVERSATIONS_TABLE, {
        "agent_enabled": False,
        "status": "paused",
        "updated_at": now,
        "pause_context": context_summary,
    }, filters={"phone": phone})

    logger.info(f"Agente pausado para {phone}. Contexto salvo ({len(messages)} msgs)")
    return {"status": "paused", "phone": phone, "context": context_summary}


@router.post("/conversations/{phone}/resume")
async def resume_conversation(phone: str, http_request: Request):
    """Retoma agente na conversa com contexto das últimas mensagens"""
    _ensure_supabase()
    user = await get_current_user(http_request)

    rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})
    if not rows:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv = rows[0]
    await _check_conversation_access(conv, user)
    pause_context = conv.get("pause_context", "")
    
    # Carregar últimas mensagens para contexto atualizado
    messages = await _get_messages(conv["id"], limit=20)
    context_lines = []
    for m in messages[-10:]:
        role = "Cliente" if m.get("sender") == "user" else "Agente"
        context_lines.append(f"{role}: {m.get('content', '')[:100]}")
    context_summary = "\n".join(context_lines) if context_lines else "Nenhuma mensagem recente"
    
    # Se havia contexto do pause, incluir na próxima mensagem do agente
    if pause_context:
        # Salvar flag para o handler usar o contexto
        logger.info(f"Retomando conversa {phone} com contexto do pause")
    
    now = datetime.now().isoformat()
    await update(CONVERSATIONS_TABLE, {
        "agent_enabled": True,
        "status": "open",
        "updated_at": now,
        "pause_context": None,  # Limpar contexto do pause
    }, filters={"phone": phone})

    return {"status": "resumed", "phone": phone, "context": context_summary}


@router.post("/conversations/{phone}/close")
async def close_conversation(phone: str, http_request: Request):
    """Encerra conversa"""
    _ensure_supabase()
    user = await get_current_user(http_request)

    rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})
    if not rows:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv = rows[0]
    await _check_conversation_access(conv, user)

    now = datetime.now().isoformat()
    await update(CONVERSATIONS_TABLE, {
        "status": "closed",
        "agent_enabled": False,
        "updated_at": now,
    }, filters={"phone": phone})

    return {"status": "closed", "phone": phone}


@router.get("/conversations/{phone}/summary")
async def get_summary(phone: str):
    """Retorna resumo da conversa"""
    _ensure_supabase()

    rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})
    if not rows:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")

    conv = rows[0]
    messages = await _get_messages(conv["id"])

    # Calcular estatísticas
    total_messages = len(messages)
    user_messages = sum(1 for m in messages if m.get("sender") == "user")
    agent_messages = sum(1 for m in messages if m.get("sender") == "agent")
    manual_messages = sum(1 for m in messages if m.get("sender") == "manual")
    unanswered = sum(1 for m in messages if m.get("sender") == "user" and not m.get("responded", True))

    # Duração
    if messages:
        first_msg = messages[0].get("created_at", "")
        last_msg = messages[-1].get("created_at", "")
        duration = f"{first_msg[:10]} a {last_msg[:10]}" if first_msg and last_msg else "N/A"
    else:
        duration = "N/A"

    return {
        "phone": phone,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "agent_messages": agent_messages,
        "manual_messages": manual_messages,
        "unanswered": unanswered,
        "duration": duration,
        "status": conv.get("status", "unknown"),
        "agent_enabled": conv.get("agent_enabled", True),
    }


@router.get("/stats")
async def get_stats(http_request: Request):
    """Retorna estatísticas gerais do CRM"""
    _ensure_supabase()
    user = await get_current_user(http_request)

    # Buscar conversas com filtro de org
    conv_filters = await apply_org_filter(user, {}, http_request)
    all_convs = await select(CONVERSATIONS_TABLE, filters=conv_filters if conv_filters else None)
    conv_list = all_convs or []

    # Stats
    total = len(conv_list)
    open_count = sum(1 for c in conv_list if c.get("status") == "open")
    paused_count = sum(1 for c in conv_list if c.get("status") == "paused")
    closed_count = sum(1 for c in conv_list if c.get("status") == "closed")

    # Total de mensagens (busca todas)
    all_msgs = await select(MESSAGES_TABLE)
    total_messages = len(all_msgs) if all_msgs else 0

    # Mensagens hoje
    today = datetime.now().strftime("%Y-%m-%d")
    messages_today = sum(
        1 for m in (all_msgs or [])
        if m.get("created_at", "").startswith(today)
    )

    # Agentes ativos
    active_agents = sum(1 for c in conv_list if c.get("agent_enabled", True))

    return {
        "total_conversations": total,
        "open": open_count,
        "paused": paused_count,
        "closed": closed_count,
        "total_messages": total_messages,
        "messages_today": messages_today,
        "active_agents": active_agents
    }


# ══════════════════════════════════════════════════════════════════
# PIPELINE STAGES
# ══════════════════════════════════════════════════════════════════

@router.get("/pipeline/stages")
async def get_pipeline_stages():
    """
    Retorna todos os estágios do pipeline ordenados por posição.
    Cada stage tem: id, name, color, position, created_at
    """
    _ensure_supabase()

    stages = await select(PIPELINE_STAGES_TABLE, order="position.asc")
    return {"stages": stages or []}


@router.post("/pipeline/stages")
async def create_pipeline_stage(body: PipelineStageCreate, http_request: Request):
    """
    Cria um novo estágio no pipeline.
    O campo 'id' é obrigatório (ex: "lead", "qualified").
    """
    _ensure_supabase()
    user = await get_current_user(http_request)

    now = datetime.now().isoformat()
    stage_data = {
        "id": body.id,
        "name": body.name,
        "position": body.position,
        "color": body.color,
        "created_at": now,
    }

    # Auto-assign organization_id para usuários não restritos
    if not is_unrestricted(user):
        org_ids = await get_user_org_ids(user["id"])
        if org_ids:
            stage_data["organization_id"] = list(org_ids)[0]

    result = await insert(PIPELINE_STAGES_TABLE, stage_data)
    if result is None:
        raise HTTPException(status_code=400, detail="Erro ao criar estágio (verifique se o id já existe)")
    created = result[0] if isinstance(result, list) and result else stage_data
    return {"status": "created", "stage": created}


@router.put("/pipeline/stages/{stage_id}")
async def update_pipeline_stage(stage_id: str, body: PipelineStageUpdate):
    """Atualiza um estágio do pipeline."""
    _ensure_supabase()

    # Verificar existência
    existing = await select(PIPELINE_STAGES_TABLE, filters={"id": stage_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Estágio não encontrado")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = await update(PIPELINE_STAGES_TABLE, update_data, filters={"id": stage_id})
    updated = result[0] if isinstance(result, list) and result else update_data
    return {"status": "updated", "stage": updated}


@router.delete("/pipeline/stages/{stage_id}")
async def delete_pipeline_stage(stage_id: str):
    """Deleta um estágio do pipeline."""
    _ensure_supabase()

    existing = await select(PIPELINE_STAGES_TABLE, filters={"id": stage_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Estágio não encontrado")

    await delete(PIPELINE_STAGES_TABLE, filters={"id": stage_id})
    return {"status": "deleted", "stage_id": stage_id}


# ══════════════════════════════════════════════════════════════════
# PIPELINE DEALS
# ══════════════════════════════════════════════════════════════════

@router.get("/pipelines/deals")
async def get_deals(
    http_request: Request,
    stage: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    Retorna lista de deals do pipeline.

    Query params:
    - stage: Filtrar por estágio (lead, qualified, proposal, negotiation, closed_won, closed_lost)
    - search: Busca por título, nome do contato ou telefone
    - limit / offset: paginação
    """
    _ensure_supabase()
    user = await get_current_user(http_request)

    # Buscar deals com filtros básicos
    filters = {}
    if stage:
        filters["stage"] = stage
    filters = await apply_org_filter(user, filters, http_request)

    all_deals = await select(
        DEALS_TABLE,
        filters=filters if filters else None,
        order="created_at.desc",
    )

    deals_list = all_deals or []

    # Busca textual (client-side)
    if search:
        search_lower = search.lower()
        deals_list = [
            d for d in deals_list
            if search_lower in (d.get("title") or "").lower()
            or search_lower in (d.get("contact_name") or "").lower()
            or search_lower in (d.get("phone") or "").lower()
        ]

    total = len(deals_list)
    paginated = deals_list[offset:offset + limit]

    return {
        "deals": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/pipelines/deals")
async def create_deal(body: DealCreate, http_request: Request):
    """Cria um novo deal no pipeline."""
    _ensure_supabase()
    user = await get_current_user(http_request)

    now = datetime.now().isoformat()

    deal_data = {
        "title": body.title,
        "phone": body.phone,
        "contact_name": body.contact_name or "",
        "value": body.value,
        "currency": body.currency or "BRL",
        "stage": body.stage or "lead",
        "tags": body.tags or [],
        "notes": body.notes or "",
        "conversation_id": body.conversation_id,
        "lead_id": body.lead_id,
        "created_at": now,
        "updated_at": now,
    }

    # Auto-assign organization_id para usuários não restritos
    if not is_unrestricted(user):
        org_ids = await get_user_org_ids(user["id"])
        if org_ids:
            deal_data["organization_id"] = list(org_ids)[0]

    result = await insert(DEALS_TABLE, deal_data)
    if result is None:
        raise HTTPException(status_code=400, detail="Erro ao criar deal")
    created = result[0] if isinstance(result, list) and result else deal_data
    return {"status": "created", "deal": created}


@router.get("/pipelines/deals/{deal_id}")
async def get_deal(deal_id: str):
    """Retorna um deal específico."""
    _ensure_supabase()

    rows = await select(DEALS_TABLE, filters={"id": deal_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Deal não encontrado")

    return {"deal": rows[0]}


@router.put("/pipelines/deals/{deal_id}")
async def update_deal(deal_id: str, body: DealUpdate):
    """
    Atualiza ou move um deal no pipeline.

    Para mover de estágio, envie stage: "qualified", "proposal", etc.
    """
    _ensure_supabase()

    # Verificar existência
    existing = await select(DEALS_TABLE, filters={"id": deal_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Deal não encontrado")

    update_data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    update_data["updated_at"] = datetime.now().isoformat()

    # Se moveu para estágio fechado, registrar data
    if update_data.get("stage") in ("closed_won", "closed_lost"):
        update_data["closed_at"] = datetime.now().isoformat()

    result = await update(DEALS_TABLE, update_data, filters={"id": deal_id})
    updated = result[0] if isinstance(result, list) and result else update_data
    return {"status": "updated", "deal": updated}


@router.delete("/pipelines/deals/{deal_id}")
async def delete_deal(deal_id: str):
    """Deleta um deal do pipeline."""
    _ensure_supabase()

    existing = await select(DEALS_TABLE, filters={"id": deal_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Deal não encontrado")

    await delete(DEALS_TABLE, filters={"id": deal_id})
    return {"status": "deleted", "deal_id": deal_id}


@router.get("/pipelines/stats")
async def get_pipeline_stats(http_request: Request):
    """
    Retorna estatísticas gerais do pipeline:
    - Total de deals, por estágio
    - Valor total do pipeline, por estágio
    - Deals ganhos / perdidos
    - Taxa de conversão
    """
    _ensure_supabase()
    user = await get_current_user(http_request)

    deal_filters = await apply_org_filter(user, {}, http_request)
    all_deals = await select(DEALS_TABLE, filters=deal_filters if deal_filters else None) or []
    stages = await select(PIPELINE_STAGES_TABLE, order="position.asc") or []

    # Deals por estágio (campo 'stage' no banco)
    open_deals = [d for d in all_deals if d.get("stage") not in ("closed_won", "closed_lost")]
    won_deals = [d for d in all_deals if d.get("stage") == "closed_won"]
    lost_deals = [d for d in all_deals if d.get("stage") == "closed_lost"]

    # Valores
    total_value = sum(float(d.get("value") or 0) for d in all_deals)
    open_value = sum(float(d.get("value") or 0) for d in open_deals)
    won_value = sum(float(d.get("value") or 0) for d in won_deals)
    lost_value = sum(float(d.get("value") or 0) for d in lost_deals)

    # Deals e valor por estágio
    stage_stats = {}
    for stage in stages:
        sid = stage["id"]
        stage_deals = [d for d in all_deals if d.get("stage") == sid]
        stage_stats[sid] = {
            "stage_name": stage.get("name"),
            "stage_color": stage.get("color"),
            "deal_count": len(stage_deals),
            "total_value": sum(float(d.get("value") or 0) for d in stage_deals),
        }

    # Deals de hoje
    today = datetime.now().strftime("%Y-%m-%d")
    deals_today = [d for d in all_deals if (d.get("created_at") or "").startswith(today)]

    # Taxa de conversão
    closed_total = len(won_deals) + len(lost_deals)
    conversion_rate = (len(won_deals) / closed_total * 100) if closed_total > 0 else 0.0

    return {
        "total_deals": len(all_deals),
        "open_deals": len(open_deals),
        "won_deals": len(won_deals),
        "lost_deals": len(lost_deals),
        "total_value": round(total_value, 2),
        "open_value": round(open_value, 2),
        "won_value": round(won_value, 2),
        "lost_value": round(lost_value, 2),
        "deals_today": len(deals_today),
        "conversion_rate": round(conversion_rate, 1),
        "by_stage": stage_stats,
        "stages": stages,
    }


@router.post("/conversations/{phone}/import-history")
async def import_conversation_history(
    phone: str,
    limit: int = Query(default=50, le=200),
    instance: Optional[str] = None,
):
    """
    Importa histórico de mensagens do WhatsApp via Evolution API.

    Busca as últimas N mensagens de um chat e salva no Supabase
    para que o agente tenha contexto de conversas anteriores.

    Query params:
    - limit: Número de mensagens para buscar (default: 50, max: 200)
    - instance: Nome da instância Evolution (usa a padrão se não informado)
    """
    _ensure_supabase()

    inst = instance or settings.evolution_instance
    jid = f"{phone}@s.whatsapp.net"

    # Buscar mensagens via Evolution API
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.evolution_api_url}/chat/findMessages/{inst}",
                headers={
                    "apikey": settings.evolution_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "where": {"key": {"remoteJid": jid}},
                    "limit": limit,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Erro ao buscar histórico via Evolution API: {e}")
            raise HTTPException(status_code=502, detail=f"Falha ao buscar histórico: {e}")

    records = data.get("messages", {}).get("records", [])
    if not records:
        return {"status": "imported", "count": 0, "phone": phone, "message": "Nenhuma mensagem encontrada"}

    # Ordenar por timestamp (mais antigo primeiro)
    records.sort(key=lambda r: r.get("messageTimestamp", 0))

    # Buscar ou criar conversa
    conv = await _get_or_create_conversation(phone)
    conversation_id = conv["id"]

    # Verificar mensagens existentes para evitar duplicatas
    existing = await select(
        MESSAGES_TABLE,
        columns="message_id",
        filters={"conversation_id": conversation_id},
    )
    existing_ids = {m.get("message_id") for m in (existing or []) if m.get("message_id")}

    # Inserir mensagens
    imported = 0
    for record in records:
        msg_id = record.get("id", "")
        if msg_id in existing_ids:
            continue

        # Extrair conteúdo do texto
        message_data = record.get("message", {})
        content = message_data.get("conversation", "")
        if not content:
            # Tentar outros formatos de mensagem (image, audio, etc)
            content = f"[{record.get('messageType', 'media')}]"

        # Determinar sender
        from_me = record.get("key", {}).get("fromMe", False)
        sender = "manual" if from_me else "user"

        # Converter timestamp
        ts = record.get("messageTimestamp", 0)
        if isinstance(ts, (int, float)) and ts > 1000000000:
            created_at = datetime.fromtimestamp(ts).isoformat()
        else:
            created_at = datetime.now().isoformat()

        await insert(MESSAGES_TABLE, {
            "conversation_id": conversation_id,
            "sender": sender,
            "content": content,
            "message_id": msg_id,
            "created_at": created_at,
        })
        imported += 1

    # Atualizar updated_at da conversa
    await update(CONVERSATIONS_TABLE, {
        "updated_at": datetime.now().isoformat(),
    }, filters={"id": conversation_id})

    logger.info(f"Importadas {imported} mensagens do histórico para {phone}")
    return {"status": "imported", "count": imported, "phone": phone}
