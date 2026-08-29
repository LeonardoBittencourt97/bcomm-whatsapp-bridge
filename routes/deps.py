"""
Dependências compartilhadas para os routers CRM.
Centraliza autenticação e helpers usados em múltiplos módulos.
"""
from typing import Optional, Set
from fastapi import HTTPException, Request

from routes.routes_auth import _verify_supabase_token, COOKIE_NAME
from services.database import select, ensure_supabase

USERS_TABLE = "bcomm_inbox.users"
USER_ORGS_TABLE = "bcomm_inbox.user_organizations"

# Roles que veem tudo (sem filtro de org)
UNRESTRICTED_ROLES = {"master", "admin_geral"}


async def get_current_user(request: Request) -> dict:
    """Extrai usuário da sessão via cookie JWT do Supabase.

    Usa a versão correta com filtro por supabase_user_id.
    Levanta HTTPException 401 se não autenticado.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")

    payload = await _verify_supabase_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Sessão expirada")

    supabase_user_id = payload.get("sub")
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    ensure_supabase()
    rows = await select(USERS_TABLE, filters={"supabase_user_id": supabase_user_id})
    if not rows:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    user = rows[0]
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Conta desativada")
    return user


async def get_user_org_ids(user_id: str) -> Set[str]:
    """Retorna IDs das organizações vinculadas ao usuário."""
    ensure_supabase()
    rows = await select(USER_ORGS_TABLE, filters={"user_id": user_id})
    return {r["organization_id"] for r in (rows or [])}


def is_unrestricted(user: dict) -> bool:
    """Verifica se o role do usuário tem acesso irrestrito (master/admin_geral)."""
    return user.get("role", "agent") in UNRESTRICTED_ROLES


async def apply_org_filter(user: dict, filters: dict) -> dict:
    """Se o usuário não for unrestricted, adiciona filtro de organization_id.
    Retorna os filtros atualizados. Se o usuário não tem orgs, levanta 403.
    """
    if is_unrestricted(user):
        return filters

    org_ids = await get_user_org_ids(user["id"])
    if not org_ids:
        raise HTTPException(status_code=403, detail="Sem acesso a nenhuma organização")

    # Filtrar por organization_id
    if len(org_ids) == 1:
        filters["organization_id"] = list(org_ids)[0]
    else:
        filters["organization_id"] = {"in": list(org_ids)}

    return filters
