"""
Tags routes — CRM bcomm_inbox
CRUD for tags used to categorize deals, contacts, etc.
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from services.database import select, insert, update, delete, ensure_supabase
from routes.deps import get_current_user

logger = logging.getLogger("bridge")

router = APIRouter(prefix="/crm", tags=["crm"])

TABLE = "bcomm_inbox.tags"


# ── Models ──────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str
    color: Optional[str] = "#3b9eff"


# ── Routes ──────────────────────────────────────────────────────

@router.get("/tags")
async def list_tags(
    request: Request,
    limit: int = Query(default=100, le=500),
):
    """Lista todas as tags."""
    user = await get_current_user(request)
    ensure_supabase()

    rows = await select(
        TABLE,
        order="name.asc",
        limit=limit,
    )

    return {
        "tags": rows or [],
        "total": len(rows) if rows else 0,
    }


@router.post("/tags", status_code=201)
async def create_tag(request: Request, tag: TagCreate):
    """Cria uma nova tag."""
    user = await get_current_user(request)
    ensure_supabase()

    # Check for duplicate name
    existing = await select(TABLE, filters={"name": tag.name})
    if existing:
        raise HTTPException(status_code=409, detail=f"Tag '{tag.name}' já existe")

    data = tag.model_dump()
    data["created_at"] = datetime.now().isoformat()

    result = await insert(TABLE, data)
    created = result[0] if isinstance(result, list) else result

    logger.info(f"Tag criada: {created.get('id')} ({tag.name})")
    return created


@router.delete("/tags/{tag_id}")
async def delete_tag(request: Request, tag_id: str):
    """Deleta uma tag."""
    user = await get_current_user(request)
    ensure_supabase()

    rows = await select(TABLE, filters={"id": tag_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Tag não encontrada")

    await delete(TABLE, filters={"id": tag_id})
    logger.info(f"Tag deletada: {tag_id}")
    return {"deleted": True, "id": tag_id}
