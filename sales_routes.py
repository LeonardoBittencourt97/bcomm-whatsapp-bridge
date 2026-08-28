"""
Rotas de Vendas - BCOMM Sales Agent
Endpoints para o inbox de vendas no dashboard
"""
from datetime import datetime
from typing import Optional
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.database import select, insert, update, ensure_supabase

router = APIRouter(prefix="/sales", tags=["sales"])
logger = logging.getLogger(__name__)

LEADS_TABLE = "bcomm_inbox.sales_leads"
AGENT_STATUS_TABLE = "bcomm_inbox.sales_agent_status"


class LeadResponse(BaseModel):
    """Resposta de um lead"""
    id: str
    nome: str
    telefone: str
    endereco: str = ""
    categoria: str = ""
    avaliacao: float = 0.0
    qtd_avaliacoes: int = 0
    site: str = ""
    instagram: str = ""
    instagram_followers: int = 0
    instagram_posts: int = 0
    score: int = 0
    status: str = "pending"
    message: str = ""
    segment: str = ""
    created_at: str = ""
    updated_at: str = ""


class ApproveRequest(BaseModel):
    """Request para aprovar lead"""
    lead_id: str


class RejectRequest(BaseModel):
    """Request para rejeitar lead"""
    lead_id: str
    reason: str = ""


class AgentStatus(BaseModel):
    """Status do agente"""
    paused: bool = False
    leads_today: int = 0
    approved_today: int = 0
    sent_today: int = 0
    rejected_today: int = 0


@router.get("/leads")
async def get_leads(
    status: Optional[str] = None,
    segment: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    Retorna lista de leads

    Query params:
    - status: Filtrar por status (pending, approved, sent, rejected)
    - segment: Filtrar por segmento (estetica, barbearia, generico)
    - limit: Limite de resultados (default: 50)
    - offset: Offset para paginação
    """
    ensure_supabase()

    filters = {}
    if status:
        filters["status"] = status
    if segment:
        filters["segment"] = segment

    leads = await select(
        LEADS_TABLE,
        filters=filters if filters else None,
        order="created_at.desc",
        limit=limit,
        offset=offset,
    )

    return {
        "leads": leads or [],
        "total": len(leads) if leads else 0,
        "limit": limit,
        "offset": offset
    }


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str):
    """Retorna um lead específico"""
    ensure_supabase()

    rows = await select(LEADS_TABLE, filters={"id": lead_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Lead não encontrado")
    return rows[0]


@router.post("/leads/{lead_id}/approve")
async def approve_lead(lead_id: str):
    """Aprova um lead para envio"""
    ensure_supabase()

    now = datetime.utcnow().isoformat()
    result = await update(
        LEADS_TABLE,
        filters={"id": lead_id},
        data={"status": "approved", "updated_at": now},
    )

    if not result:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    return {"status": "approved", "lead": result[0] if result else None}


@router.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: str, reason: str = ""):
    """Rejeita um lead"""
    ensure_supabase()

    now = datetime.utcnow().isoformat()
    result = await update(
        LEADS_TABLE,
        filters={"id": lead_id},
        data={"status": "rejected", "reject_reason": reason, "updated_at": now},
    )

    if not result:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    return {"status": "rejected", "lead": result[0] if result else None}


@router.post("/leads/{lead_id}/send")
async def send_lead(lead_id: str):
    """Envia mensagem para o lead via WhatsApp"""
    ensure_supabase()

    now = datetime.utcnow().isoformat()
    result = await update(
        LEADS_TABLE,
        filters={"id": lead_id},
        data={"status": "sent", "sent_at": now, "updated_at": now},
    )

    if not result:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    # TODO: Enviar via Evolution API

    return {"status": "sent", "lead": result[0] if result else None}


@router.get("/agent/status")
async def get_agent_status():
    """Retorna status do agente de vendas"""
    ensure_supabase()

    rows = await select(AGENT_STATUS_TABLE, limit=1)
    status = rows[0] if rows else {"paused": False}

    today = datetime.utcnow().strftime("%Y-%m-%d")

    today_leads = await select(
        LEADS_TABLE,
        filters={"created_at": {"like": f"{today}%"}},
        limit=1000,
    )

    leads_today = len(today_leads) if today_leads else 0
    approved_today = sum(1 for l in (today_leads or []) if l.get("status") == "approved")
    rejected_today = sum(1 for l in (today_leads or []) if l.get("status") == "rejected")

    sent_leads = await select(
        LEADS_TABLE,
        filters={"sent_at": {"like": f"{today}%"}},
        limit=1000,
    )
    sent_today = len(sent_leads) if sent_leads else 0

    return {
        "paused": status.get("paused", False),
        "leads_today": leads_today,
        "approved_today": approved_today,
        "sent_today": sent_today,
        "rejected_today": rejected_today
    }


@router.post("/agent/pause")
async def pause_agent():
    """Pausa o agente de vendas"""
    ensure_supabase()

    rows = await select(AGENT_STATUS_TABLE, limit=1)
    if rows:
        await update(AGENT_STATUS_TABLE, filters={"id": rows[0]["id"]}, data={"paused": True})
    else:
        await insert(AGENT_STATUS_TABLE, {"paused": True})

    return {"status": "paused", "message": "Agente pausado"}


@router.post("/agent/resume")
async def resume_agent():
    """Retoma o agente de vendas"""
    ensure_supabase()

    rows = await select(AGENT_STATUS_TABLE, limit=1)
    if rows:
        await update(AGENT_STATUS_TABLE, filters={"id": rows[0]["id"]}, data={"paused": False})
    else:
        await insert(AGENT_STATUS_TABLE, {"paused": False})

    return {"status": "resumed", "message": "Agente retomado"}


@router.get("/stats")
async def get_stats():
    """Retorna estatísticas gerais"""
    ensure_supabase()

    all_leads = await select(LEADS_TABLE, limit=10000)
    leads = all_leads or []
    today = datetime.utcnow().strftime("%Y-%m-%d")

    total = len(leads)
    pending = sum(1 for l in leads if l.get("status") == "pending")
    approved = sum(1 for l in leads if l.get("status") == "approved")
    sent = sum(1 for l in leads if l.get("status") == "sent")
    rejected = sum(1 for l in leads if l.get("status") == "rejected")

    leads_today = [l for l in leads if l.get("created_at", "").startswith(today)]

    segments = {}
    for l in leads:
        seg = l.get("segment", "unknown")
        segments[seg] = segments.get(seg, 0) + 1

    scores = [l.get("score", 0) for l in leads if l.get("score")]
    avg_score = sum(scores) / len(scores) if scores else 0

    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "sent": sent,
        "rejected": rejected,
        "today": len(leads_today),
        "segments": segments,
        "avg_score": round(avg_score, 1)
    }
