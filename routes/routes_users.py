"""
Rotas de Gerenciamento de Usuários - BCOMM CRM
Endpoints CRUD para users + user_organizations.
Roles: master, admin_geral, admin_contas, agent.
- Master: acesso total
- Admin_geral: acesso total, mas NÃO pode modificar usuários master
- Admin_contas: vê apenas usuários das organizações vinculadas
- Agent: vê apenas seu próprio perfil
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, EmailStr, Field
from passlib.context import CryptContext

from config import settings
from services.database import select, insert, update, delete, ensure_supabase

logger = logging.getLogger('bridge')

router = APIRouter(prefix="/crm", tags=["users"])

# ── Password hashing ─────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Supabase tables ──────────────────────────────────────────────
USERS_TABLE = "bcomm_inbox.users"
USER_ORGS_TABLE = "bcomm_inbox.user_organizations"

# ── Valid roles ───────────────────────────────────────────────────
VALID_ROLES = {"master", "admin_geral", "admin_contas", "agent"}


# ── Helpers ───────────────────────────────────────────────────────

def _ensure_supabase():
    """Inicializa Supabase se ainda não estiver conectado."""
    from services.database import ensure_supabase as _es
    _es()


def _hash_password(password: str) -> str:
    """Gera hash bcrypt da senha."""
    return pwd_context.hash(password)


def _sanitize_user(user: dict) -> dict:
    """Remove password_hash antes de retornar ao cliente."""
    return {k: v for k, v in user.items() if k != "password_hash"}


def _role_level(role: str) -> int:
    """Retorna nível hierárquico do role (maior = mais privilégio)."""
    levels = {
        "agent": 1,
        "admin_contas": 2,
        "admin_geral": 3,
        "master": 4,
    }
    return levels.get(role, 0)


async def _get_current_user(request: Request) -> dict:
    """Extrai usuário da sessão via cookie JWT do Supabase."""
    from routes.routes_auth import _verify_supabase_token, COOKIE_NAME
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
    _ensure_supabase()
    rows = await select(USERS_TABLE, filters={"supabase_user_id": supabase_user_id})
    if not rows:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    user = rows[0]
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Conta desativada")
    return user


async def _get_user_organizations(user_id: str) -> List[dict]:
    """Busca organizações vinculadas ao usuário."""
    _ensure_supabase()
    rows = await select(USER_ORGS_TABLE, filters={"user_id": user_id})
    return rows or []


async def _can_access_user(current_user: dict, target_user: dict) -> bool:
    """
    Verifica se o usuário atual pode acessar/visualizar o alvo.
    """
    current_role = current_user.get("role", "agent")

    # Master vê tudo
    if current_role == "master":
        return True

    # Admin_geral vê tudo (mas não pode editar master — checado separadamente)
    if current_role == "admin_geral":
        return True

    # Admin_contas: vê apenas usuários das mesmas organizações
    if current_role == "admin_contas":
        current_orgs = await _get_user_organizations(current_user["id"])
        current_org_ids = {o["organization_id"] for o in current_orgs}

        # Sem organizações = sem acesso a outros
        if not current_org_ids:
            return False

        # Se o alvo é ele mesmo
        if target_user["id"] == current_user["id"]:
            return True

        # Verificar se compartilham organização
        target_orgs = await _get_user_organizations(target_user["id"])
        target_org_ids = {o["organization_id"] for o in target_orgs}

        return bool(current_org_ids & target_org_ids)

    # Agent: apenas seu próprio perfil
    return target_user["id"] == current_user["id"]


async def _can_modify_user(current_user: dict, target_role: str) -> bool:
    """
    Verifica se o usuário atual pode modificar o alvo.
    Regra: admin_geral NÃO pode modificar master.
    """
    current_role = current_user.get("role", "agent")

    if current_role == "master":
        return True

    if current_role == "admin_geral":
        return target_role != "master"

    # Admin_contas e agent: só a si mesmos
    return False


async def _get_accessible_user_ids(current_user: dict) -> Optional[set]:
    """
    Retorna IDs de usuários acessíveis.
    Retorna None se o papel vê todos (master, admin_geral).
    Retorna set se é filtrado (admin_contas, agent).
    """
    current_role = current_user.get("role", "agent")

    # Master e admin_geral veem todos
    if current_role in ("master", "admin_geral"):
        return None

    # Agent: apenas si mesmo
    if current_role == "agent":
        return {current_user["id"]}

    # Admin_contas: usuários das mesmas organizações
    if current_role == "admin_contas":
        current_orgs = await _get_user_organizations(current_user["id"])
        current_org_ids = {o["organization_id"] for o in current_orgs}

        if not current_org_ids:
            return {current_user["id"]}

        # Buscar todos os user_organizations e filtrar pelos org_ids
        all_user_orgs = await select(USER_ORGS_TABLE) or []
        accessible_ids = set()
        for uo in all_user_orgs:
            if uo.get("organization_id") in current_org_ids:
                accessible_ids.add(uo["user_id"])

        # Sempre incluir a si mesmo
        accessible_ids.add(current_user["id"])
        return accessible_ids

    return {current_user["id"]}


# ── Pydantic Models ──────────────────────────────────────────────

class UserCreate(BaseModel):
    """Request para criar usuário."""
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str = Field(..., min_length=2, max_length=255)
    role: str = Field(default="agent")
    avatar_url: Optional[str] = None
    is_active: bool = True


class UserUpdate(BaseModel):
    """Request para atualizar usuário."""
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    role: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None


class OrgAssignment(BaseModel):
    """Request para atribuir/remover organização."""
    organization_id: str
    role_override: Optional[str] = None


# ── User CRUD Endpoints ──────────────────────────────────────────

@router.get("/users")
async def list_users(
    request: Request,
    role: Optional[str] = Query(default=None, description="Filtrar por role"),
    is_active: Optional[bool] = Query(default=None, description="Filtrar por status"),
    search: Optional[str] = Query(default=None, description="Buscar por nome/email"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """
    Lista usuários com base nas permissões do papel do solicitante.
    Master/admin_geral: veem todos.
    Admin_contas: veem apenas usuários das organizações vinculadas.
    Agent: vê apenas seu próprio perfil.
    """
    current_user = await _get_current_user(request)
    _ensure_supabase()

    # Determinar IDs acessíveis
    accessible_ids = await _get_accessible_user_ids(current_user)

    # Buscar todos os usuários
    all_users = await select(USERS_TABLE, order="name.asc") or []

    # Filtrar por acessibilidade
    if accessible_ids is not None:
        all_users = [u for u in all_users if u.get("id") in accessible_ids]

    # Filtrar por role
    if role:
        if role not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Role inválida. Valores aceitos: {', '.join(sorted(VALID_ROLES))}"
            )
        all_users = [u for u in all_users if u.get("role") == role]

    # Filtrar por status
    if is_active is not None:
        all_users = [u for u in all_users if u.get("is_active", True) == is_active]

    # Busca por texto
    if search:
        search_lower = search.lower()
        all_users = [
            u for u in all_users
            if search_lower in (u.get("name") or "").lower()
            or search_lower in (u.get("email") or "").lower()
        ]

    # Paginação
    total = len(all_users)
    paginated = all_users[offset:offset + limit]

    # Sanitizar
    safe_users = [_sanitize_user(u) for u in paginated]

    return {
        "users": safe_users,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/users/{user_id}")
async def get_user(request: Request, user_id: str):
    """
    Retorna dados de um usuário específico.
    Verifica permissões de acesso do papel do solicitante.
    """
    current_user = await _get_current_user(request)
    _ensure_supabase()

    rows = await select(USERS_TABLE, filters={"id": user_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    target_user = rows[0]

    # Verificar acesso
    if not await _can_access_user(current_user, target_user):
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este usuário")

    # Incluir organizações vinculadas
    orgs = await _get_user_organizations(user_id)

    return {
        "user": _sanitize_user(target_user),
        "organizations": orgs,
    }


@router.post("/users")
async def create_user(request: Request, body: UserCreate):
    """
    Cria novo usuário.
    Master: pode criar qualquer role.
    Admin_geral: pode criar qualquer role exceto master.
    Admin_contas/agent: não podem criar.
    """
    current_user = await _get_current_user(request)
    current_role = current_user.get("role", "agent")

    # Verificar permissão
    if current_role not in ("master", "admin_geral"):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para criar usuários"
        )

    # Validar role
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role inválida. Valores aceitos: {', '.join(sorted(VALID_ROLES))}"
        )

    # Admin_geral não pode criar master
    if current_role == "admin_geral" and body.role == "master":
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para criar usuários master"
        )

    _ensure_supabase()

    # Verificar email duplicado
    existing = await select(USERS_TABLE, filters={"email": body.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email já cadastrado")

    # Criar usuário
    now = datetime.now().isoformat()
    new_user = {
        "email": body.email,
        "name": body.name,
        "password_hash": pwd_context.hash(body.password),
        "role": body.role,
        "avatar_url": body.avatar_url,
        "is_active": body.is_active,
        "created_at": now,
        "updated_at": now,
    }

    result = await insert(USERS_TABLE, new_user)
    created = result[0] if isinstance(result, list) and result else new_user

    logger.info(
        f"Usuário criado: {body.email} (role={body.role}) "
        f"por {current_user['email']}"
    )

    return {
        "status": "ok",
        "user": _sanitize_user(created),
    }


@router.put("/users/{user_id}")
async def update_user(request: Request, user_id: str, body: UserUpdate):
    """
    Atualiza dados de um usuário.
    Verifica permissões: admin_geral não pode modificar master.
    Cada usuário pode atualizar seu próprio perfil (exceto role).
    """
    current_user = await _get_current_user(request)
    _ensure_supabase()

    # Buscar usuário alvo
    rows = await select(USERS_TABLE, filters={"id": user_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    target_user = rows[0]
    target_role = target_user.get("role", "agent")

    # Verificar acesso
    if not await _can_access_user(current_user, target_user):
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este usuário")

    # Se está tentando mudar role, verificar permissão
    if body.role is not None:
        if not await _can_modify_user(current_user, target_role):
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para alterar este usuário"
            )
        # Validar nova role
        if body.role not in VALID_ROLES:
            raise HTTPException(
                status_code=400,
                detail=f"Role inválida. Valores aceitos: {', '.join(sorted(VALID_ROLES))}"
            )
        # Admin_geral não pode promover a master
        current_role = current_user.get("role", "agent")
        if current_role == "admin_geral" and body.role == "master":
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para atribuir role master"
            )

    # Se está alterando email, verificar duplicidade
    if body.email and body.email != target_user.get("email"):
        existing = await select(USERS_TABLE, filters={"email": body.email})
        if existing:
            raise HTTPException(status_code=409, detail="Email já cadastrado")

    # Montar dados de atualização
    update_data = {"updated_at": datetime.now().isoformat()}

    if body.email is not None:
        update_data["email"] = body.email
    if body.name is not None:
        update_data["name"] = body.name
    if body.role is not None:
        update_data["role"] = body.role
    if body.avatar_url is not None:
        update_data["avatar_url"] = body.avatar_url
    if body.is_active is not None:
        update_data["is_active"] = body.is_active
    if body.password is not None:
        update_data["password_hash"] = pwd_context.hash(body.password)

    await update(USERS_TABLE, update_data, filters={"id": user_id})

    # Buscar dados atualizados
    updated_rows = await select(USERS_TABLE, filters={"id": user_id})
    updated_user = updated_rows[0] if updated_rows else target_user

    logger.info(
        f"Usuário atualizado: {user_id} por {current_user['email']}"
    )

    return {
        "status": "ok",
        "user": _sanitize_user(updated_user),
    }


@router.delete("/users/{user_id}")
async def delete_user(request: Request, user_id: str):
    """
    Desativa (soft delete) ou remove um usuário.
    Master: pode desativar qualquer um.
    Admin_geral: pode desativar qualquer um exceto master.
    Admin_contas/agent: não podem desativar.
    """
    current_user = await _get_current_user(request)
    _ensure_supabase()

    # Buscar usuário alvo
    rows = await select(USERS_TABLE, filters={"id": user_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    target_user = rows[0]
    target_role = target_user.get("role", "agent")

    # Verificar permissão
    if not await _can_modify_user(current_user, target_role):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para excluir este usuário"
        )

    # Não permitir que o próprio usuário se desative via DELETE
    if current_user["id"] == user_id:
        raise HTTPException(
            status_code=400,
            detail="Não é possível excluir seu próprio usuário"
        )

    # Soft delete: desativar ao invés de remover
    await update(
        USERS_TABLE,
        {
            "is_active": False,
            "updated_at": datetime.now().isoformat(),
        },
        filters={"id": user_id}
    )

    logger.info(
        f"Usuário desativado: {target_user.get('email')} "
        f"por {current_user['email']}"
    )

    return {
        "status": "ok",
        "message": "Usuário desativado",
        "user_id": user_id,
    }


# ── Organization Assignment Endpoints ────────────────────────────

@router.get("/users/{user_id}/organizations")
async def list_user_organizations(request: Request, user_id: str):
    """
    Lista organizações vinculadas a um usuário.
    """
    current_user = await _get_current_user(request)
    _ensure_supabase()

    # Buscar usuário alvo
    rows = await select(USERS_TABLE, filters={"id": user_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    target_user = rows[0]

    # Verificar acesso
    if not await _can_access_user(current_user, target_user):
        raise HTTPException(status_code=403, detail="Sem permissão para acessar este usuário")

    orgs = await _get_user_organizations(user_id)

    return {
        "user_id": user_id,
        "organizations": orgs,
    }


@router.post("/users/{user_id}/organizations")
async def assign_organization(request: Request, user_id: str, body: OrgAssignment):
    """
    Atribui organização a um usuário.
    Apenas master e admin_geral podem atribuir.
    """
    current_user = await _get_current_user(request)
    current_role = current_user.get("role", "agent")

    if current_role not in ("master", "admin_geral"):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para atribuir organizações"
        )

    _ensure_supabase()

    # Verificar se usuário existe
    rows = await select(USERS_TABLE, filters={"id": user_id})
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Verificar se já existe a vinculação
    existing = await select(
        USER_ORGS_TABLE,
        filters={"user_id": user_id, "organization_id": body.organization_id}
    )
    if existing:
        # Atualizar role_override se informado
        if body.role_override is not None:
            await update(
                USER_ORGS_TABLE,
                {"role_override": body.role_override},
                filters={
                    "user_id": user_id,
                    "organization_id": body.organization_id,
                }
            )
        return {
            "status": "ok",
            "message": "Vinculação já existente" + (
                " (role_override atualizado)" if body.role_override else ""
            ),
        }

    # Criar vinculação
    assignment = {
        "user_id": user_id,
        "organization_id": body.organization_id,
        "role_override": body.role_override,
    }
    await insert(USER_ORGS_TABLE, assignment)

    logger.info(
        f"Organização {body.organization_id} atribuída a {user_id} "
        f"por {current_user['email']}"
    )

    return {
        "status": "ok",
        "assignment": assignment,
    }


@router.delete("/users/{user_id}/organizations/{organization_id}")
async def remove_organization(request: Request, user_id: str, organization_id: str):
    """
    Remove vinculação de organização de um usuário.
    Apenas master e admin_geral podem remover.
    """
    current_user = await _get_current_user(request)
    current_role = current_user.get("role", "agent")

    if current_role not in ("master", "admin_geral"):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para remover organizações"
        )

    _ensure_supabase()

    # Verificar se a vinculação existe
    existing = await select(
        USER_ORGS_TABLE,
        filters={"user_id": user_id, "organization_id": organization_id}
    )
    if not existing:
        raise HTTPException(
            status_code=404,
            detail="Vinculação não encontrada"
        )

    await delete(
        USER_ORGS_TABLE,
        filters={"user_id": user_id, "organization_id": organization_id}
    )

    logger.info(
        f"Organização {organization_id} removida de {user_id} "
        f"por {current_user['email']}"
    )

    return {
        "status": "ok",
        "message": "Organização removida do usuário",
    }
