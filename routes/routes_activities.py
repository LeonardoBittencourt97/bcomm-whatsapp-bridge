"""
Activities routes — CRM bcomm_inbox
CRUD for activities (tasks, calls, meetings, emails, etc.)
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from services.database import select, insert, update, delete, ensure_supabase
from routes.deps import get_current_user, apply_org_filter, is_unrestricted, get_user_org_ids

logger = logging.getLogger("bridge")

router = APIRouter(prefix="/crm", tags=["crm"])

TABLE = "bcomm_inbox.activities"


# ── Models ──────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    type: str  # task, call, meeting, email, note
    subject: str
    description: Optional[str] = ""
    deal_id: Optional[str] = None
    contact_id: Optional[str] = None
    organization_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    status: Optional[str] = "pending"  # pending, in_progress, completed
    priority: Optional[str] = "low"  # low, medium, high, urgent
    due_date: Optional[str] = None


class ActivityUpdate(BaseModel):
    type: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    deal_id: Optional[str] = None
    contact_id: Optional[str] = None
    organization_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None


# ── Routes ──────────────────────────────────────────────────────

@router.get("/activities")
async def list_activities(
    request: Request,
    type: Optional[str] = None,
    status: Optional[str] = None,
    deal_id: Optional[str] = None,
    contact_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lista atividades com filtros opcionais."""
    user = await get_current_user(request)
    ensure_supabase()

    filters = {}
    if type:
        filters["type"] = type
    if status:
        filters["status"] = status
    if deal_id:
        filters["deal_id"] = deal_id
    if contact_id:
        filters["contact_id"] = contact_id
    filters = await apply_org_filter(user, filters)

    rows = await select(
        TABLE,
        filters=filters if filters else None,
        order="created_at.desc",
    )

    total = len(rows)
    activities = rows[offset:offset + limit]

    return {
        "activities": activities,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/activities", status_code=201)
async def create_activity(request: Request, activity: ActivityCreate):
    """Cria uma nova atividade."""
    user = await get_current_user(request)
    ensure_supabase()

    data = activity.model_dump()
    if not is_unrestricted(user):
        org_ids = await get_user_org_ids(user["id"])
        if org_ids:
            data["organization_id"] = data.get("organization_id") or list(org_ids)[0]
    data["created_at"] = datetime.now().isoformat()

    result = await insert(TABLE, data)
    created = result[0] if isinstance(result, list) else result

    logger.info(f"Atividade criada: {created.get('id')}")
    return created


@router.put("/activities/{activity_id}")
async def update_activity(request: Request, activity_id: str, activity: ActivityUpdate):
    """Atualiza uma atividade existente."""
    user = await get_current_user(request)
    ensure_supabase()

    rows = await select(TABLE, filters={"id": activity_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Atividade não encontrada")

    data = {k: v for k, v in activity.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    await update(TABLE, data, filters={"id": activity_id})

    updated = await select(TABLE, filters={"id": activity_id})
    logger.info(f"Atividade atualizada: {activity_id}")
    return updated[0]


@router.put("/activities/{activity_id}/complete")
async def complete_activity(request: Request, activity_id: str):
    """Marca uma atividade como concluída."""
    user = await get_current_user(request)
    ensure_supabase()

    rows = await select(TABLE, filters={"id": activity_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Atividade não encontrada")

    await update(
        TABLE,
        {"status": "completed", "completed_at": datetime.now().isoformat()},
        filters={"id": activity_id},
    )

    updated = await select(TABLE, filters={"id": activity_id})
    logger.info(f"Atividade concluída: {activity_id}")
    return updated[0]


@router.delete("/activities/{activity_id}")
async def delete_activity(request: Request, activity_id: str):
    """Deleta uma atividade."""
    user = await get_current_user(request)
    ensure_supabase()

    rows = await select(TABLE, filters={"id": activity_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Atividade não encontrada")

    await delete(TABLE, filters={"id": activity_id})
    logger.info(f"Atividade deletada: {activity_id}")
    return {"deleted": True, "id": activity_id}
