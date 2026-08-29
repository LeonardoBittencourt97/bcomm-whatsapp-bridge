"""
Notes routes — CRM bcomm_inbox
CRUD for notes attached to any entity (deal, contact, organization, etc.)
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

TABLE = "bcomm_inbox.notes"


# ── Models ──────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    content: str
    entity_type: str  # deal, contact, organization, conversation
    entity_id: str
    user_id: Optional[str] = None


class NoteUpdate(BaseModel):
    content: Optional[str] = None


# ── Routes ──────────────────────────────────────────────────────

@router.get("/notes")
async def list_notes(
    request: Request,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Lista notas com filtros opcionais por entidade."""
    user = await get_current_user(request)
    ensure_supabase()

    filters = {}
    if entity_type:
        filters["entity_type"] = entity_type
    if entity_id:
        filters["entity_id"] = entity_id
    filters = await apply_org_filter(user, filters)

    rows = await select(
        TABLE,
        filters=filters if filters else None,
        order="created_at.desc",
    )

    total = len(rows)
    notes = rows[offset:offset + limit]

    return {
        "notes": notes,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/notes", status_code=201)
async def create_note(request: Request, note: NoteCreate):
    """Cria uma nova nota."""
    user = await get_current_user(request)
    ensure_supabase()

    data = note.model_dump()
    if not is_unrestricted(user):
        org_ids = await get_user_org_ids(user["id"])
        if org_ids:
            data["organization_id"] = data.get("organization_id") or list(org_ids)[0]
    now = datetime.now().isoformat()
    data["created_at"] = now
    data["updated_at"] = now

    result = await insert(TABLE, data)
    created = result[0] if isinstance(result, list) else result

    logger.info(f"Nota criada: {created.get('id')}")
    return created


@router.put("/notes/{note_id}")
async def update_note(request: Request, note_id: str, note: NoteUpdate):
    """Atualiza uma nota existente."""
    user = await get_current_user(request)
    ensure_supabase()

    rows = await select(TABLE, filters={"id": note_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Nota não encontrada")

    data = {k: v for k, v in note.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    data["updated_at"] = datetime.now().isoformat()
    await update(TABLE, data, filters={"id": note_id})

    updated = await select(TABLE, filters={"id": note_id})
    logger.info(f"Nota atualizada: {note_id}")
    return updated[0]


@router.delete("/notes/{note_id}")
async def delete_note(request: Request, note_id: str):
    """Deleta uma nota."""
    user = await get_current_user(request)
    ensure_supabase()

    rows = await select(TABLE, filters={"id": note_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Nota não encontrada")

    await delete(TABLE, filters={"id": note_id})
    logger.info(f"Nota deletada: {note_id}")
    return {"deleted": True, "id": note_id}
