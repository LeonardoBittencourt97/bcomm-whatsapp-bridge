"""
Rotas do CRM - BCOMM Atendimento
Endpoints para gerenciamento de conversas tipo Chatwoot
"""
import json
import os
import uuid
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/crm", tags=["crm"])

# Paths
DATA_DIR = Path("/app/data")
CONVERSATIONS_FILE = DATA_DIR / "crm_conversations.json"
HERMES_SESSIONS_FILE = DATA_DIR / "hermes_sessions.json"


# ── Models ──────────────────────────────────────────────────────

class Message(BaseModel):
    """Mensagem na conversa"""
    id: str = ""
    sender: str = "user"  # user, agent, manual
    content: str = ""
    timestamp: str = ""
    model: str = ""
    responded: bool = True


class ConversationSummary(BaseModel):
    """Resumo da conversa"""
    lead_name: str = ""
    score: int = 0
    segment: str = ""
    last_topic: str = ""


class Conversation(BaseModel):
    """Conversa completa"""
    phone: str
    session_id: str = ""
    status: str = "open"  # open, paused, closed
    agent_enabled: bool = True
    messages: List[dict] = []
    summary: dict = {}
    created_at: str = ""
    updated_at: str = ""
    client_name: str = ""
    client_id: str = ""


class SendMessageRequest(BaseModel):
    """Request para enviar mensagem"""
    content: str


# ── Helpers ─────────────────────────────────────────────────────

def _load_conversations() -> dict:
    """Carrega conversas do disco"""
    if not CONVERSATIONS_FILE.exists():
        return {}
    
    try:
        with open(CONVERSATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_conversations(conversations: dict):
    """Salva conversas no disco"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(CONVERSATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(conversations, f, ensure_ascii=False, indent=2)


def _load_hermes_sessions() -> dict:
    """Carrega sessões do Hermes"""
    if not HERMES_SESSIONS_FILE.exists():
        return {}
    
    try:
        with open(HERMES_SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f
)
    except Exception:
        return {}


def _get_or_create_conversation(phone: str) -> dict:
    """Busca ou cria conversa"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        hermes_sessions = _load_hermes_sessions()
        session_id = hermes_sessions.get(phone, "")
        
        conversations[phone] = {
            "phone": phone,
            "session_id": session_id,
            "status": "open",
            "agent_enabled": True,
            "messages": [],
            "summary": {},
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "client_name": "",
            "client_id": ""
        }
        _save_conversations(conversations)
    
    return conversations[phone]


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/conversations")
async def get_conversations(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0)
):
    """
    Retorna lista de conversas
    
    Query params:
    - status: Filtrar por status (open, paused, closed)
    - limit: Limite de resultados (default: 50)
    - offset: Offset para paginação
    """
    conversations = _load_conversations()
    
    # Converter para lista
    conv_list = list(conversations.values())
    
    # Filtrar por status
    if status:
        conv_list = [c for c in conv_list if c.get("status") == status]
    
    # Ordenar por última atualização (mais recente primeiro)
    conv_list.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    
    # Paginação
    total = len(conv_list)
    conv_list = conv_list[offset:offset + limit]
    
    # Enriquecer dados
    for conv in conv_list:
        # Adicionar última mensagem
        if conv.get("messages"):
            last_msg = conv["messages"][-1]
            conv["last_message"] = last_msg.get("content", "")[:50]
            conv["last_message_time"] = last_msg.get("timestamp", "")
        else:
            conv["last_message"] = ""
            conv["last_message_time"] = ""
        
        # Contar mensagens não respondidas
        conv["unanswered_count"] = sum(
            1 for m in conv.get("messages", [])
            if m.get("sender") == "user" and not m.get("responded", True)
        )
    
    return {
        "conversations": conv_list,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/conversations/{phone}")
async def get_conversation(phone: str):
    """Retorna conversa específica"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        # Criar nova conversa se não existir
        conv = _get_or_create_conversation(phone)
        return conv
    
    return conversations[phone]


@router.get("/conversations/{phone}/messages")
async def get_messages(phone: str, limit: int = 100):
    """Retorna mensagens da conversa"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    
    messages = conversations[phone].get("messages", [])
    
    # Retornar últimas N mensagens
    messages = messages[-limit:]
    
    return {
        "phone": phone,
        "messages": messages,
        "total": len(messages)
    }


@router.post("/conversations/{phone}/send")
async def send_message(phone: str, request: SendMessageRequest):
    """Envia mensagem manual para o cliente"""
    conversations = _load_conversations()
    
    # Criar conversa se não existir
    if phone not in conversations:
        _get_or_create_conversation(phone)
        conversations = _load_conversations()
    
    # Adicionar mensagem
    message = {
        "id": str(uuid.uuid4())[:8],
        "sender": "manual",
        "content": request.content,
        "timestamp": datetime.now().isoformat(),
        "responded": True
    }
    
    conversations[phone]["messages"].append(message)
    conversations[phone]["updated_at"] = datetime.now().isoformat()
    
    _save_conversations(conversations)
    
    # TODO: Enviar via Evolution API
    # Por enquanto, apenas registrar
    
    return {"status": "sent", "message": message}


@router.post("/conversations/{phone}/receive")
async def receive_message(phone: str, request: SendMessageRequest):
    """Registra mensagem recebida do cliente"""
    conversations = _load_conversations()
    
    # Criar conversa se não existir
    if phone not in conversations:
        _get_or_create_conversation(phone)
        conversations = _load_conversations()
    
    # Verificar se agente está habilitado
    agent_enabled = conversations[phone].get("agent_enabled", True)
    
    # Adicionar mensagem
    message = {
        "id": str(uuid.uuid4())[:8],
        "sender": "user",
        "content": request.content,
        "timestamp": datetime.now().isoformat(),
        "responded": agent_enabled  # Se agente desabilitado, não respondida
    }
    
    conversations[phone]["messages"].append(message)
    conversations[phone]["updated_at"] = datetime.now().isoformat()
    
    _save_conversations(conversations)
    
    return {
        "status": "received",
        "message": message,
        "agent_enabled": agent_enabled
    }


@router.post("/conversations/{phone}/agent-response")
async def agent_response(phone: str, request: SendMessageRequest, model: str = ""):
    """Registra resposta da IA"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    
    # Adicionar mensagem
    message = {
        "id": str(uuid.uuid4())[:8],
        "sender": "agent",
        "content": request.content,
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "responded": True
    }
    
    conversations[phone]["messages"].append(message)
    conversations[phone]["updated_at"] = datetime.now().isoformat()
    
    _save_conversations(conversations)
    
    return {"status": "recorded", "message": message}


@router.post("/conversations/{phone}/pause")
async def pause_conversation(phone: str):
    """Pausa agente na conversa"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    
    conversations[phone]["agent_enabled"] = False
    conversations[phone]["status"] = "paused"
    conversations[phone]["updated_at"] = datetime.now().isoformat()
    
    _save_conversations(conversations)
    
    return {"status": "paused", "phone": phone}


@router.post("/conversations/{phone}/resume")
async def resume_conversation(phone: str):
    """Retoma agente na conversa"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    
    conversations[phone]["agent_enabled"] = True
    conversations[phone]["status"] = "open"
    conversations[phone]["updated_at"] = datetime.now().isoformat()
    
    _save_conversations(conversations)
    
    return {"status": "resumed", "phone": phone}


@router.post("/conversations/{phone}/close")
async def close_conversation(phone: str):
    """Encerra conversa"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    
    conversations[phone]["status"] = "closed"
    conversations[phone]["agent_enabled"] = False
    conversations[phone]["updated_at"] = datetime.now().isoformat()
    
    _save_conversations(conversations)
    
    return {"status": "closed", "phone": phone}


@router.get("/conversations/{phone}/summary")
async def get_summary(phone: str):
    """Retorna resumo da conversa"""
    conversations = _load_conversations()
    
    if phone not in conversations:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    
    conv = conversations[phone]
    messages = conv.get("messages", [])
    
    # Calcular estatísticas
    total_messages = len(messages)
    user_messages = sum(1 for m in messages if m.get("sender") == "user")
    agent_messages = sum(1 for m in messages if m.get("sender") == "agent")
    manual_messages = sum(1 for m in messages if m.get("sender") == "manual")
    unanswered = sum(1 for m in messages if m.get("sender") == "user" and not m.get("responded", True))
    
    # Duração
    if messages:
        first_msg = messages[0].get("timestamp", "")
        last_msg = messages[-1].get("timestamp", "")
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
        "summary": conv.get("summary", {})
    }


@router.get("/stats")
async def get_stats():
    """Retorna estatísticas gerais do CRM"""
    conversations = _load_conversations()
    
    conv_list = list(conversations.values())
    
    # Stats
    total = len(conv_list)
    open_count = sum(1 for c in conv_list if c.get("status") == "open")
    paused_count = sum(1 for c in conv_list if c.get("status") == "paused")
    closed_count = sum(1 for c in conv_list if c.get("status") == "closed")
    
    # Total de mensagens
    total_messages = sum(len(c.get("messages", [])) for c in conv_list)
    
    # Mensagens hoje
    today = datetime.now().strftime("%Y-%m-%d")
    messages_today = 0
    for c in conv_list:
        for m in c.get("messages", []):
            if m.get("timestamp", "").startswith(today):
                messages_today += 1
    
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
