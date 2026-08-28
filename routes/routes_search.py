"""
Search routes — CRM bcomm_inbox
Global search across contacts, deals, organizations, and messages.
"""
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.database import select, get_client

logger = logging.getLogger("bridge")

router = APIRouter(prefix="/crm", tags=["crm"])

CONTACTS_TABLE = "bcomm_inbox.contacts"
DEALS_TABLE = "bcomm_inbox.deals"
ORGANIZATIONS_TABLE = "bcomm_inbox.organizations"
MESSAGES_TABLE = "bcomm_inbox.messages"

SEARCH_LIMIT = 5


def _ensure_supabase():
    if get_client() is None:
        from config import settings
        from services.database import get_supabase
        get_supabase(settings.supabase_url, settings.supabase_service_key)


def _ilike_matches(rows: list, fields: list, query: str) -> list:
    """Filter rows where any field contains the query (case-insensitive, in-memory)."""
    q = query.lower()
    matches = []
    for row in rows:
        for field in fields:
            val = row.get(field, "")
            if val and q in str(val).lower():
                matches.append(row)
                break
    return matches


# ── Routes ──────────────────────────────────────────────────────

@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=5, ge=1, le=20),
):
    """
    Busca global no CRM — contatos, deals, organizações e mensagens.
    Retorna resultados agrupados por tipo, com limite por tipo.
    """
    _ensure_supabase()

    results = {}

    # ── Contacts: name, phone, email ──
    try:
        contacts = await select(CONTACTS_TABLE, limit=500)
        matched_contacts = _ilike_matches(
            contacts or [], ["name", "phone", "email", "company"], q
        )[:limit]
        results["contacts"] = [
            {
                "id": c.get("id"),
                "name": c.get("name", ""),
                "phone": c.get("phone", ""),
                "email": c.get("email", ""),
                "company": c.get("company", ""),
            }
            for c in matched_contacts
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar contatos: {e}")
        results["contacts"] = []

    # ── Deals: title ──
    try:
        deals = await select(DEALS_TABLE, limit=500)
        matched_deals = _ilike_matches(deals or [], ["title", "contact_name", "notes"], q)[:limit]
        results["deals"] = [
            {
                "id": d.get("id"),
                "title": d.get("title", ""),
                "contact_name": d.get("contact_name", ""),
                "value": d.get("value", 0),
                "stage_id": d.get("stage_id", ""),
            }
            for d in matched_deals
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar deals: {e}")
        results["deals"] = []

    # ── Organizations: name ──
    try:
        orgs = await select(ORGANIZATIONS_TABLE, limit=500)
        matched_orgs = _ilike_matches(orgs or [], ["name", "domain"], q)[:limit]
        results["organizations"] = [
            {
                "id": o.get("id"),
                "name": o.get("name", ""),
                "domain": o.get("domain", ""),
            }
            for o in matched_orgs
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar organizações: {e}")
        results["organizations"] = []

    # ── Messages: content ──
    try:
        messages = await select(MESSAGES_TABLE, order="created_at.desc", limit=200)
        matched_messages = _ilike_matches(messages or [], ["content"], q)[:limit]
        results["messages"] = [
            {
                "id": m.get("id"),
                "content": m.get("content", "")[:200],
                "sender": m.get("sender", ""),
                "conversation_id": m.get("conversation_id", ""),
                "created_at": m.get("created_at", ""),
            }
            for m in matched_messages
        ]
    except Exception as e:
        logger.error(f"Erro ao buscar mensagens: {e}")
        results["messages"] = []

    # ── Summary counts ──
    total = sum(len(v) for v in results.values())

    return {
        "query": q,
        "total": total,
        "results": results,
    }
