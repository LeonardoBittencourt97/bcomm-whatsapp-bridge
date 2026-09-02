"""
Rotas de Autenticação - BCOMM CRM
Usa Supabase Auth para autenticação.
JWT do Supabase verificado via gotrue, sessão em cookie httpOnly.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from config import settings
from services.database import select, insert, update, get_client, get_supabase

logger = logging.getLogger('bridge')

router = APIRouter(prefix="/crm", tags=["auth"])

# ── Supabase tables ──────────────────────────────────────────────
USERS_TABLE = "bcomm_inbox.users"
USER_ORGS_TABLE = "bcomm_inbox.user_organizations"

# ── Valid roles ───────────────────────────────────────────────────
VALID_ROLES = {"master", "admin_geral", "admin_contas", "agent"}

# ── Cookie name ──────────────────────────────────────────────────
COOKIE_NAME = "bcomm_crm_token"
ORG_COOKIE = "bcomm_org_id"

# ── Supabase Auth URL ────────────────────────────────────────────
SUPABASE_URL = "https://supabase.agent-bcomm.space"
SUPABASE_ANON_KEY = settings.supabase_anon_key or "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsImlhdCI6MTc4NDA4MTg4MCwiZXhwIjo0OTM5NzU1NDgwLCJyb2xlIjoiYW5vbiJ9.bR3IPrJ23ieVqy_kbJqK3qELGE6kcYqtQMTNVhWe95E"
SUPABASE_SERVICE_KEY = settings.supabase_service_key or "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJzdXBhYmFzZSIsImlhdCI6MTc4NDA4MTg4MCwiZXhwIjo0OTM5NzU1NDgwLCJyb2xlIjoic2VydmljZV9yb2xlIn0.dVqc4-jFSFR1w3P0T_3Oi_h6XJwL6QcBF-y8Hu9V1sg"


# ── Helpers ───────────────────────────────────────────────────────

def _ensure_supabase():
    """Inicializa Supabase se ainda não estiver conectado."""
    from services.database import ensure_supabase as _es
    _es()


def _sanitize_user(user: dict) -> dict:
    """Remove dados sensíveis antes de retornar ao cliente."""
    safe = {k: v for k, v in user.items() if k not in ("password_hash", "supabase_user_id")}
    return safe


def _set_auth_cookie(response: Response, access_token: str, refresh_token: str):
    """Define cookies de autenticação na response."""
    cookie_kwargs = {
        "key": COOKIE_NAME,
        "value": access_token,
        "max_age": 3600,  # 1 hour (Supabase default)
        "httponly": True,
        "samesite": "lax",
        "path": "/",
    }
    if settings.cookie_domain:
        cookie_kwargs["domain"] = settings.cookie_domain
    if settings.cookie_secure:
        cookie_kwargs["secure"] = True
    response.set_cookie(**cookie_kwargs)

    # Also store refresh token
    refresh_kwargs = {
        "key": "bcomm_refresh_token",
        "value": refresh_token,
        "max_age": 60 * 60 * 24 * 7,  # 7 days
        "httponly": True,
        "samesite": "lax",
        "path": "/",
    }
    if settings.cookie_domain:
        refresh_kwargs["domain"] = settings.cookie_domain
    if settings.cookie_secure:
        refresh_kwargs["secure"] = True
    response.set_cookie(**refresh_kwargs)


def _clear_auth_cookies(response: Response):
    """Remove cookies de autenticação."""
    for key in [COOKIE_NAME, "bcomm_refresh_token", ORG_COOKIE]:
        kwargs = {
            "key": key,
            "value": "",
            "max_age": 0,
            "httponly": True,
            "samesite": "lax",
            "path": "/",
        }
        if settings.cookie_domain:
            kwargs["domain"] = settings.cookie_domain
        if settings.cookie_secure:
            kwargs["secure"] = True
        response.delete_cookie(**kwargs)


async def _verify_supabase_token(token: str) -> Optional[dict]:
    """
    Verifica JWT do Supabase Auth.
    Decodifica localmente usando o JWT secret do Supabase (SUPABASE_JWT_SECRET).
    """
    try:
        import os
        supabase_jwt_secret = os.getenv("SUPABASE_JWT_SECRET", "")
        if not supabase_jwt_secret:
            from config import settings as cfg
            supabase_jwt_secret = cfg.jwt_secret
        if not supabase_jwt_secret:
            logger.error(
                "SUPABASE_JWT_SECRET e settings.jwt_secret estão ambos vazios. "
                "Tokens não podem ser verificados — autenticação ficará comprometida."
            )
            return None
        payload = jwt.decode(
            token,
            supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.debug("Supabase token expirado")
        return None
    except jwt.InvalidTokenError as e:
        logger.debug(f"Supabase token inválido: {e}")
        return None


async def _refresh_supabase_token(refresh_token: str) -> Optional[dict]:
    """Tenta refresh do token via Supabase Auth API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Content-Type": "application/json",
                },
                json={"refresh_token": refresh_token},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Refresh token failed: {resp.status_code}")
            return None
    except Exception as e:
        logger.error(f"Erro ao refresh token: {e}")
        return None


async def get_current_user(request: Request) -> dict:
    """
    Extrai usuário do cookie JWT do Supabase.
    Levanta HTTPException 401 se não autenticado.
    Faz refresh automático se token expirado.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")

    # Verify token
    payload = await _verify_supabase_token(token)

    # If expired, try refresh
    if not payload:
        refresh_token = request.cookies.get("bcomm_refresh_token")
        if refresh_token:
            refresh_data = await _refresh_supabase_token(refresh_token)
            if refresh_data and "access_token" in refresh_data:
                # Token refreshed - we can't set cookies here (Response not available)
                # But we can still use the new token for this request
                payload = await _verify_supabase_token(refresh_data["access_token"])
                if payload:
                    # Store new tokens for later
                    request.state.new_access_token = refresh_data.get("access_token")
                    request.state.new_refresh_token = refresh_data.get("refresh_token")

    if not payload:
        raise HTTPException(status_code=401, detail="Sessão expirada ou inválida")

    supabase_user_id = payload.get("sub")
    if not supabase_user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    # Find user in our database by supabase_user_id
    _ensure_supabase()
    rows = await select(USERS_TABLE, filters={"supabase_user_id": supabase_user_id})
    if not rows:
        # User exists in Supabase Auth but not in our DB - auto-create
        email = payload.get("email", "")
        new_user = {
            "email": email,
            "name": email.split("@")[0],
            "role": "agent",
            "is_active": True,
            "supabase_user_id": supabase_user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await insert(USERS_TABLE, new_user)
        user = result[0] if isinstance(result, list) and result else new_user
        logger.info(f"Usuário auto-criado via Supabase Auth: {email}")
    else:
        user = rows[0]

    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Conta desativada")

    return user


# ── Pydantic Models ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Request para login."""
    email: EmailStr
    password: str = Field(..., min_length=6)


class RegisterRequest(BaseModel):
    """Request para registro (apenas master)."""
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=2, max_length=255)
    role: str = Field(default="agent")


class ChangePasswordRequest(BaseModel):
    """Request para alteração de senha."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=6)


class InviteRequest(BaseModel):
    """Request para convite."""
    email: EmailStr
    organization_id: str
    role: str = Field(default="agent")


# ── Auth Endpoints ───────────────────────────────────────────────

@router.post("/auth/login")
async def login(request: Request, body: LoginRequest, response: Response):
    """
    Autentica usuário via Supabase Auth.
    Cria cookies com access_token + refresh_token.
    """
    # Call Supabase Auth API
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Content-Type": "application/json",
                },
                json={"email": body.email, "password": body.password},
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Erro ao conectar Supabase Auth: {e}")
        raise HTTPException(status_code=500, detail="Erro ao conectar com servidor de autenticação")

    if resp.status_code != 200:
        error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        msg = error_data.get("error_description", error_data.get("error", "Credenciais inválidas"))
        raise HTTPException(status_code=401, detail=msg)

    auth_data = resp.json()
    access_token = auth_data.get("access_token")
    refresh_token = auth_data.get("refresh_token")
    supabase_user_id = auth_data.get("user", {}).get("id")

    if not access_token or not supabase_user_id:
        raise HTTPException(status_code=401, detail="Resposta inválida do Supabase")

    # Set cookies
    _set_auth_cookie(response, access_token, refresh_token)

    # Find or create user in our DB
    _ensure_supabase()
    rows = await select(USERS_TABLE, filters={"supabase_user_id": supabase_user_id})

    if not rows:
        # First login - auto-create
        new_user = {
            "email": body.email,
            "name": body.email.split("@")[0],
            "role": "agent",
            "is_active": True,
            "supabase_user_id": supabase_user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await insert(USERS_TABLE, new_user)
        user = result[0] if isinstance(result, list) and result else new_user
        logger.info(f"Primeiro login - usuário criado: {body.email}")
    else:
        user = rows[0]
        # Update last_login_at
        try:
            await update(
                USERS_TABLE,
                {"last_login_at": datetime.now(timezone.utc).isoformat()},
                filters={"id": user["id"]}
            )
        except Exception:
            pass

    # Get user organizations
    orgs = await select(USER_ORGS_TABLE, filters={"user_id": user["id"]})

    logger.info(f"Login realizado: {user['email']} (role={user.get('role')})")

    return {
        "status": "ok",
        "user": _sanitize_user(user),
        "organizations": orgs or [],
        "session": {
            "user_id": user["id"],
            "role": user.get("role", "agent"),
            "supabase_user_id": supabase_user_id,
        },
    }


@router.post("/auth/logout")
async def logout(response: Response):
    """
    Encerra sessão do usuário (limpa cookies).
    """
    _clear_auth_cookies(response)
    logger.info("Logout realizado")
    return {"status": "ok", "message": "Sessão encerrada"}


class SelectOrgRequest(BaseModel):
    organization_id: Optional[str] = None


@router.post("/auth/select-org")
async def select_org(request: Request, response: Response, body: SelectOrgRequest):
    """
    Seleciona organização ativa. Salva em cookie.
    organization_id = null limpa a seleção.
    """
    from routes.deps import ORG_COOKIE, get_user_org_ids, is_unrestricted
    user = await get_current_user(request)

    if body.organization_id:
        # Verificar se tem acesso
        if not is_unrestricted(user):
            org_ids = await get_user_org_ids(user["id"])
            if body.organization_id not in org_ids:
                raise HTTPException(status_code=403, detail="Sem acesso a esta organização")

    response.set_cookie(
        key=ORG_COOKIE,
        value=body.organization_id or "",
        httponly=False,
        max_age=86400 * 30,
        samesite="lax",
        path="/",
    )
    logger.info(f"Org selecionada: {body.organization_id or 'todas'} por {user['email']}")
    return {"status": "ok", "organization_id": body.organization_id}


@router.get("/auth/me")
async def get_me(request: Request):
    """
    Retorna dados do usuário autenticado (sessão atual).
    Master/admin_geral: retorna TODAS as organizações.
    Admin_contas/agent: retorna apenas organizações vinculadas.
    """
    user = await get_current_user(request)
    _ensure_supabase()

    if user.get("role") in ("master", "admin_geral"):
        # Buscar TODAS as organizações
        all_orgs = await select("bcomm_inbox.organizations", order="name.asc")
        orgs = [{"id": o["id"], "name": o.get("name", "")} for o in (all_orgs or [])]
    else:
        # Buscar apenas vinculadas ao usuário
        raw_orgs = await select(
            USER_ORGS_TABLE,
            filters={"user_id": user["id"]}
        )
        org_ids = [o["organization_id"] for o in (raw_orgs or [])]
        if org_ids:
            all_orgs = await select("bcomm_inbox.organizations")
            orgs = [{"id": o["id"], "name": o.get("name", "")} for o in (all_orgs or []) if o["id"] in org_ids]
        else:
            orgs = []

    return {
        "user": _sanitize_user(user),
        "organizations": orgs,
    }


@router.post("/auth/register")
async def register(request: Request, body: RegisterRequest):
    """
    Registra novo usuário via Supabase Auth. Apenas master pode registrar.
    """
    current_user = await get_current_user(request)

    # Verificar permissão
    if current_user.get("role") != "master":
        raise HTTPException(status_code=403, detail="Apenas master pode registrar usuários")

    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role inválida. Valores aceitos: {', '.join(sorted(VALID_ROLES))}"
        )

    # Create user in Supabase Auth
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/admin/users",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": body.email,
                    "password": body.password,
                    "email_confirm": True,
                },
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Erro ao criar usuário no Supabase Auth: {e}")
        raise HTTPException(status_code=500, detail="Erro ao criar usuário")

    if resp.status_code not in (200, 201):
        error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        msg = error_data.get("msg", error_data.get("error_description", "Erro ao criar usuário"))
        raise HTTPException(status_code=400, detail=msg)

    auth_user = resp.json()
    supabase_user_id = auth_user.get("id")

    # Create in our DB
    _ensure_supabase()
    now = datetime.now(timezone.utc).isoformat()
    new_user = {
        "email": body.email,
        "name": body.name,
        "role": body.role,
        "is_active": True,
        "supabase_user_id": supabase_user_id,
        "created_at": now,
        "updated_at": now,
    }

    result = await insert(USERS_TABLE, new_user)
    created = result[0] if isinstance(result, list) and result else new_user

    logger.info(
        f"Usuário registrado: {body.email} (role={body.role}) "
        f"por {current_user['email']}"
    )

    return {
        "status": "ok",
        "user": _sanitize_user(created),
    }


@router.post("/auth/invite")
async def invite_user(request: Request, body: InviteRequest):
    """
    Gera link de convite para usuário.
    Master seleciona organização e gera link.
    """
    current_user = await get_current_user(request)

    # Only master, admin_geral, and admin_contas can invite
    if current_user.get("role") not in ("master", "admin_geral", "admin_contas"):
        raise HTTPException(status_code=403, detail="Sem permissão para convidar usuários")

    # Admin_contas: só suas organizações
    if current_user.get("role") == "admin_contas":
        from routes.routes_users import _get_user_organizations
        my_orgs = await _get_user_organizations(current_user["id"])
        my_org_ids = {o["organization_id"] for o in my_orgs}
        if body.organization_id not in my_org_ids:
            raise HTTPException(status_code=403, detail="Sem acesso a esta organização")

    # Admin_contas não pode convidar para roles elevadas
    if current_user.get("role") == "admin_contas" and body.role not in ("agent", "admin_contas"):
        raise HTTPException(status_code=403, detail="Sem permissão para convidar com este papel")

    _ensure_supabase()

    # Generate invitation token
    import secrets
    token = secrets.token_urlsafe(32)

    now = datetime.now(timezone.utc)
    invitation = {
        "email": body.email,
        "organization_id": body.organization_id,
        "role": body.role,
        "token": token,
        "invited_by": current_user["id"],
        "expires_at": (now + timedelta(days=7)).isoformat(),
        "created_at": now.isoformat(),
    }

    result = await insert("bcomm_inbox.user_invitations", invitation)
    created = result[0] if isinstance(result, list) and result else invitation

    # Build invitation URL
    invite_url = f"https://wa-bot.agent-bcomm.space/invite/{token}"

    logger.info(f"Convite gerado: {body.email} por {current_user['email']}")

    return {
        "status": "ok",
        "invite_url": invite_url,
        "expires_at": created.get("expires_at"),
    }


class AcceptInviteRequest(BaseModel):
    """Request para aceitar convite."""
    token: str
    password: str = Field(..., min_length=6)
    name: Optional[str] = None


@router.post("/auth/accept-invite")
async def accept_invite(request: Request, body: AcceptInviteRequest):
    """
    Aceita convite e cria usuário.
    """
    _ensure_supabase()

    # Find invitation
    rows = await select(
        "bcomm_inbox.user_invitations",
        filters={"token": body.token}
    )

    if not rows:
        raise HTTPException(status_code=404, detail="Convite não encontrado")

    invitation = rows[0]

    # Check if expired
    from datetime import datetime as dt
    expires_at = dt.fromisoformat(invitation["expires_at"].replace("Z", "+00:00"))
    if dt.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Convite expirado")

    # Check if already accepted
    if invitation.get("accepted_at"):
        raise HTTPException(status_code=400, detail="Convite já utilizado")

    # Create user in Supabase Auth
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/admin/users",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "email": invitation["email"],
                    "password": body.password,
                    "email_confirm": True,
                },
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Erro ao criar usuário: {e}")
        raise HTTPException(status_code=500, detail="Erro ao criar conta")

    if resp.status_code not in (200, 201):
        error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        msg = error_data.get("msg", "Erro ao criar conta")
        raise HTTPException(status_code=400, detail=msg)

    auth_user = resp.json()
    supabase_user_id = auth_user.get("id")

    # Create in our DB
    now = datetime.now(timezone.utc)
    new_user = {
        "email": invitation["email"],
        "name": body.name or invitation["email"].split("@")[0],
        "role": invitation.get("role", "agent"),
        "is_active": True,
        "supabase_user_id": supabase_user_id,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    result = await insert(USERS_TABLE, new_user)
    user = result[0] if isinstance(result, list) and result else new_user

    # Link to organization
    user_org = {
        "user_id": user["id"],
        "organization_id": invitation["organization_id"],
        "role": invitation.get("role", "agent"),
        "created_at": now.isoformat(),
    }
    await insert(USER_ORGS_TABLE, user_org)

    # Mark invitation as accepted
    await update(
        "bcomm_inbox.user_invitations",
        {"accepted_at": now.isoformat()},
        filters={"id": invitation["id"]}
    )

    logger.info(f"Convite aceito: {invitation['email']} -> org {invitation['organization_id']}")

    return {
        "status": "ok",
        "user": _sanitize_user(user),
        "message": "Conta criada com sucesso"
    }


@router.post("/auth/change-password")
async def change_password(request: Request, body: ChangePasswordRequest):
    """
    Altera senha do usuário via Supabase Auth.
    Requer token de autenticação.
    """
    user = await get_current_user(request)

    if not user.get("supabase_user_id"):
        raise HTTPException(status_code=400, detail="Conta sem vínculo Supabase Auth")

    # Validate current password
    try:
        async with httpx.AsyncClient() as client:
            verify_resp = await client.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Content-Type": "application/json",
                },
                json={"email": user["email"], "password": body.current_password},
                timeout=10,
            )
        if verify_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Senha atual incorreta")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao validar senha atual: {e}")
        raise HTTPException(status_code=500, detail="Erro ao validar senha")

    # Get current access token
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")

    # Update password via Supabase Auth API
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{SUPABASE_URL}/auth/v1/admin/users/{user['supabase_user_id']}",
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                },
                json={"password": body.new_password},
                timeout=10,
            )
    except Exception as e:
        logger.error(f"Erro ao alterar senha: {e}")
        raise HTTPException(status_code=500, detail="Erro ao alterar senha")

    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Erro ao alterar senha")

    logger.info(f"Senha alterada: {user['email']}")

    return {"status": "ok", "message": "Senha alterada com sucesso"}
