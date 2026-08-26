"""
Rotas de Vendas - BCOMM Sales Agent
Endpoints para o inbox de vendas no dashboard
"""
import json
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/sales", tags=["sales"])

# Paths
DATA_DIR = Path("/app/data/sales")
LEADS_FILE = DATA_DIR / "leads.json"
CONFIG_FILE = Path("/app/data/.env")


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


def _load_leads() -> list:
    """Carrega leads do arquivo JSON"""
    if not LEADS_FILE.exists():
        return []
    
    try:
        with open(LEADS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_leads(leads: list):
    """Salva leads no arquivo JSON"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)


def _load_agent_status() -> dict:
    """Carrega status do agente"""
    status_file = DATA_DIR / "agent_status.json"
    
    if not status_file.exists():
        return {"paused": False}
    
    try:
        with open(status_file, "r") as f:
            return json.load(f)
    except Exception:
        return {"paused": False}


def _save_agent_status(status: dict):
    """Salva status do agente"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    status_file = DATA_DIR / "agent_status.json"
    with open(status_file, "w") as f:
        json.dump(status, f)


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
    leads = _load_leads()
    
    # Filtros
    if status:
        leads = [l for l in leads if l.get("status") == status]
    
    if segment:
        leads = [l for l in leads if l.get("segment") == segment]
    
    # Ordenar por data (mais recente primeiro)
    leads.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    # Paginação
    total = len(leads)
    leads = leads[offset:offset + limit]
    
    return {
        "leads": leads,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str):
    """Retorna um lead específico"""
    leads = _load_leads()
    
    for lead in leads:
        if lead.get("id") == lead_id:
            return lead
    
    raise HTTPException(status_code=404, detail="Lead não encontrado")


@router.post("/leads/{lead_id}/approve")
async def approve_lead(lead_id: str):
    """Aprova um lead para envio"""
    leads = _load_leads()
    
    for i, lead in enumerate(leads):
        if lead.get("id") == lead_id:
            leads[i]["status"] = "approved"
            leads[i]["updated_at"] = __import__("datetime").datetime.now().isoformat()
            _save_leads(leads)
            
            return {"status": "approved", "lead": leads[i]}
    
    raise HTTPException(status_code=404, detail="Lead não encontrado")


@router.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: str, reason: str = ""):
    """Rejeita um lead"""
    leads = _load_leads()
    
    for i, lead in enumerate(leads):
        if lead.get("id") == lead_id:
            leads[i]["status"] = "rejected"
            leads[i]["reject_reason"] = reason
            leads[i]["updated_at"] = __import__("datetime").datetime.now().isoformat()
            _save_leads(leads)
            
            return {"status": "rejected", "lead": leads[i]}
    
    raise HTTPException(status_code=404, detail="Lead não encontrado")


@router.post("/leads/{lead_id}/send")
async def send_lead(lead_id: str):
    """Envia mensagem para o lead via WhatsApp"""
    leads = _load_leads()
    
    for i, lead in enumerate(leads):
        if lead.get("id") == lead_id:
            # Marcar como enviado
            leads[i]["status"] = "sent"
            leads[i]["sent_at"] = __import__("datetime").datetime.now().isoformat()
            leads[i]["updated_at"] = leads[i]["sent_at"]
            _save_leads(leads)
            
            # TODO: Enviar via Evolution API
            # Por enquanto, apenas marcar como enviado
            
            return {"status": "sent", "lead": leads[i]}
    
    raise HTTPException(status_code=404, detail="Lead não encontrado")


@router.get("/agent/status")
async def get_agent_status():
    """Retorna status do agente de vendas"""
    status = _load_agent_status()
    
    # Contar leads de hoje
    leads = _load_leads()
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    
    leads_today = [l for l in leads if l.get("created_at", "").startswith(today)]
    approved_today = [l for l in leads_today if l.get("status") == "approved"]
    sent_today = [l for l in leads if l.get("sent_at", "").startswith(today)]
    rejected_today = [l for l in leads_today if l.get("status") == "rejected"]
    
    return {
        "paused": status.get("paused", False),
        "leads_today": len(leads_today),
        "approved_today": len(approved_today),
        "sent_today": len(sent_today),
        "rejected_today": len(rejected_today)
    }


@router.post("/agent/pause")
async def pause_agent():
    """Pausa o agente de vendas"""
    status = _load_agent_status()
    status["paused"] = True
    _save_agent_status(status)
    
    return {"status": "paused", "message": "Agente pausado"}


@router.post("/agent/resume")
async def resume_agent():
    """Retoma o agente de vendas"""
    status = _load_agent_status()
    status["paused"] = False
    _save_agent_status(status)
    
    return {"status": "resumed", "message": "Agente retomado"}


@router.get("/stats")
async def get_stats():
    """Retorna estatísticas gerais"""
    leads = _load_leads()
    
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Stats gerais
    total = len(leads)
    pending = sum(1 for l in leads if l.get("status") == "pending")
    approved = sum(1 for l in leads if l.get("status") == "approved")
    sent = sum(1 for l in leads if l.get("status") == "sent")
    rejected = sum(1 for l in leads if l.get("status") == "rejected")
    
    # Stats de hoje
    leads_today = [l for l in leads if l.get("created_at", "").startswith(today)]
    
    # Por segmento
    segments = {}
    for l in leads:
        seg = l.get("segment", "unknown")
        segments[seg] = segments.get(seg, 0) + 1
    
    # Score médio
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
