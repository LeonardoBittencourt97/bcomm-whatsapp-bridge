"""
Dependências compartilhadas para os routers CRM.
Centraliza autenticação e helpers usados em múltiplos módulos.
"""
from fastapi import HTTPException, Request

from routes.routes_auth import _verify_supabase_token, COOKIE_NAME
from services.database import select, ensure_supabase

USERS_TABLE = "bcomm_inbox.users"


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
