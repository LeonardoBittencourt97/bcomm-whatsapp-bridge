"""
Search routes — CRM bcomm_inbox
Global search across contacts, deals, organizations, and messages.
Uses database-level ilike filtering for efficiency.
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, Query

from services.database import select, ensure_supabase, get_client, _get_table_ref

logger = logging.getLogger("bridge")

router = APIRouter(prefix="/crm", tags=["crm"])

CONTACTS_TABLE = "bcomm_inbox.contacts"
DEALS_TABLE = "bcomm_inbox.deals"
ORGANIZATIONS_TABLE = "bcomm_inbox.organizations"
MESSAGES_TABLE = "bcomm_inbox.messages"


async def _db_ilike_search(table: str, fields: list, query: str, limit: int = 5) -> list:
    """Busca com ilike no banco de dados para múltiplos campos (OR)."""
    client = get_client()
    if not client:
        return []

    try:
        schema, tbl = table.split(".", 1) if "." in table else ("bcomm_inbox", table)
        q = f"%{query}%"

        or_filters = []
        for field in fields:
            or_filters.append(f"{field}.ilike.{q}")

        query_builder = client.schema(schema).table(tbl).select("*")

        if len(fields) == 1:
            query_builder = query_builder.ilike(fields[0], q)
        else:
            for field in fields:
                query_builder = query_builder.or_(f"{field}.ilike.{q}")

        result = query_builder.limit(limit).execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Erro na busca ilike em {table}: {e}")
        return []


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
    ensure_supabase()

    results = {}

    # ── Contacts: name, phone, email ──
    try:
        matched_contacts = await _db_ilike_search(
            CONTACTS_TABLE, ["name", "phone", "email", "company"], q, limit
        )
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
        matched_deals = await _db_ilike_search(
            DEALS_TABLE, ["title", "contact_name", "notes"], q, limit
        )
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
        matched_orgs = await _db_ilike_search(
            ORGANIZATIONS_TABLE, ["name", "domain"], q, limit
        )
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
        matched_messages = await _db_ilike_search(
            MESSAGES_TABLE, ["content"], q, limit
        )
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
