"""
Dependências compartilhadas para os routers CRM.
Centraliza autenticação e helpers usados em múltiplos módulos.
"""
from typing import Optional, Set
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from routes.routes_auth import _verify_supabase_token, COOKIE_NAME
from services.database import select, ensure_supabase

USERS_TABLE = "bcomm_inbox.users"
USER_ORGS_TABLE = "bcomm_inbox.user_organizations"
ORG_COOKIE = "bcomm_org_id"

# Roles que veem tudo (sem filtro de org)
UNRESTRICTED_ROLES = {"master", "admin_geral"}


async def get_current_user(request: Request) -> dict:
    """Extrai usuário da sessão via cookie JWT do Supabase."""
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


def get_active_org_id(request: Request) -> Optional[str]:
    """Lê organization_id selecionada do cookie."""
    return request.cookies.get(ORG_COOKIE)


async def apply_org_filter(user: dict, filters: dict, request: Request = None) -> dict:
    """Se o usuário não for unrestricted, adiciona filtro de organization_id.
    Se request tiver org_id no cookie, filtra pela org selecionada.
    """
    if is_unrestricted(user):
        # Master/admin_geral pode filtrar pela org selecionada se quiser
        if request:
            selected_org = get_active_org_id(request)
            if selected_org:
                filters["organization_id"] = selected_org
        return filters

    org_ids = await get_user_org_ids(user["id"])
    if not org_ids:
        raise HTTPException(status_code=403, detail="Sem acesso a nenhuma organização")

    # Se tem org selecionada no cookie, verificar se tem acesso
    if request:
        selected_org = get_active_org_id(request)
        if selected_org and selected_org in org_ids:
            filters["organization_id"] = selected_org
            return filters

    # Filtrar por todas as orgs do usuário
    if len(org_ids) == 1:
        filters["organization_id"] = list(org_ids)[0]
    else:
        filters["organization_id"] = {"in": list(org_ids)}

    return filters
