"""
Agent Management Routes - BCOMM CRM
CRUD endpoints for managing agents within organizations.
Multi-tenant: each organization has its own agents.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from config import settings
from services.database import select, insert, update, delete, get_client, ensure_supabase
from routes.deps import get_current_user

logger = logging.getLogger("bridge")

router = APIRouter(prefix="/crm", tags=["agents"])

# ── Tables ──────────────────────────────────────────────────────
AGENTS_TABLE = "bcomm_inbox.agents"
CONVERSATIONS_TABLE = "bcomm_inbox.conversations"
USER_ORGS_TABLE = "bcomm_inbox.user_organizations"


# ── Models ──────────────────────────────────────────────────────
class AgentCreate(BaseModel):
    """Request to create an agent"""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    system_prompt: str = Field(..., min_length=1)
    is_default: bool = False


class AgentUpdate(BaseModel):
    """Request to update an agent"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=50, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    system_prompt: Optional[str] = Field(None, min_length=1)
    is_default: Optional[bool] = None


class SwitchAgentRequest(BaseModel):
    """Request to switch agent in conversation"""
    agent_id: str


# ── Helpers ─────────────────────────────────────────────────────
def _ensure_supabase():
    """Initialize Supabase if not connected"""
    if get_client() is None:
        ensure_supabase()


async def _require_admin(user: dict, org_id: str) -> bool:
    """Check if user is admin of the organization"""
    if user.get("role") in ("master", "admin_geral"):
        return True
    
    if user.get("role") == "admin_contas":
        # Check if user has access to this organization
        _ensure_supabase()
        rows = await select(
            USER_ORGS_TABLE,
            filters={"user_id": user["id"], "organization_id": org_id}
        )
        return len(rows) > 0
    
    return False


async def _verify_org_exists(org_id: str) -> bool:
    """Verify organization exists"""
    _ensure_supabase()
    rows = await select("bcomm_inbox.organizations", filters={"id": org_id})
    return len(rows) > 0


# ── Endpoints ───────────────────────────────────────────────────

@router.get("/organizations/{org_id}/agents")
async def list_agents(request: Request, org_id: str):
    """
    List all agents for an organization.
    Accessible by any authenticated user with access to the org.
    """
    try:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        # Verify org exists
        if not await _verify_org_exists(org_id):
            raise HTTPException(status_code=404, detail="Organização não encontrada")
        
        _ensure_supabase()
        
        # List agents
        agents = await select(
            AGENTS_TABLE,
            filters={"organization_id": org_id},
            order="created_at.asc"
        )
        
        # Remove system_prompt from list response (too large)
        safe_agents = []
        for agent in agents:
            safe_agent = {k: v for k, v in agent.items() if k != "system_prompt"}
            safe_agents.append(safe_agent)
        
        return {"agents": safe_agents}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing agents for org {org_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/organizations/{org_id}/agents/{agent_id}")
async def get_agent(request: Request, org_id: str, agent_id: str):
    """
    Get agent details including system_prompt.
    Accessible by any authenticated user with access to the org.
    """
    try:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        # Verify org exists
        if not await _verify_org_exists(org_id):
            raise HTTPException(status_code=404, detail="Organização não encontrada")
        
        _ensure_supabase()
        
        # Get agent
        rows = await select(
            AGENTS_TABLE,
            filters={"id": agent_id, "organization_id": org_id}
        )
        
        if not rows:
            raise HTTPException(status_code=404, detail="Agente não encontrado")
        
        return {"agent": rows[0]}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/organizations/{org_id}/agents")
async def create_agent(request: Request, org_id: str, body: AgentCreate):
    """
    Create a new agent for an organization.
    Requires admin access.
    """
    try:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        # Check admin permission
        if not await _require_admin(user, org_id):
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores podem criar agentes"
            )
        
        # Verify org exists
        if not await _verify_org_exists(org_id):
            raise HTTPException(status_code=404, detail="Organização não encontrada")
        
        _ensure_supabase()
        
        # Check if slug already exists in this org
        existing = await select(
            AGENTS_TABLE,
            filters={"organization_id": org_id, "slug": body.slug}
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe um agente com o slug '{body.slug}' nesta organização"
            )
        
        # If setting as default, unset other defaults
        if body.is_default:
            await update(
                AGENTS_TABLE,
                {"is_default": False},
                filters={"organization_id": org_id, "is_default": True}
            )
        
        # Create agent
        now = __import__("datetime").datetime.utcnow().isoformat()
        agent_data = {
            "organization_id": org_id,
            "name": body.name,
            "slug": body.slug,
            "description": body.description or "",
            "system_prompt": body.system_prompt,
            "is_active": True,
            "is_default": body.is_default,
            "created_at": now,
            "updated_at": now,
            "created_by": user["id"],
        }
        
        result = await insert(AGENTS_TABLE, agent_data)
        created = result[0] if isinstance(result, list) and result else agent_data
        
        logger.info(f"Agent created: {body.name} ({body.slug}) for org {org_id}")
        
        return {"status": "created", "agent": created}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating agent: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.put("/organizations/{org_id}/agents/{agent_id}")
async def update_agent(request: Request, org_id: str, agent_id: str, body: AgentUpdate):
    """
    Update an agent.
    Requires admin access.
    """
    try:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        # Check admin permission
        if not await _require_admin(user, org_id):
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores podem editar agentes"
            )
        
        _ensure_supabase()
        
        # Verify agent exists
        existing = await select(
            AGENTS_TABLE,
            filters={"id": agent_id, "organization_id": org_id}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Agente não encontrado")
        
        # Check if new slug conflicts with another agent
        if body.slug:
            slug_conflict = await select(
                AGENTS_TABLE,
                filters={"organization_id": org_id, "slug": body.slug}
            )
            if slug_conflict and slug_conflict[0]["id"] != agent_id:
                raise HTTPException(
                    status_code=409,
                    detail=f"Já existe um agente com o slug '{body.slug}'"
                )
        
        # Build update data
        update_data = {}
        if body.name is not None:
            update_data["name"] = body.name
        if body.slug is not None:
            update_data["slug"] = body.slug
        if body.description is not None:
            update_data["description"] = body.description
        if body.system_prompt is not None:
            update_data["system_prompt"] = body.system_prompt
        
        # Handle is_default
        if body.is_default is not None:
            if body.is_default:
                # Unset other defaults first
                await update(
                    AGENTS_TABLE,
                    {"is_default": False},
                    filters={"organization_id": org_id, "is_default": True}
                )
            update_data["is_default"] = body.is_default
        
        if not update_data:
            raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
        
        update_data["updated_at"] = __import__("datetime").datetime.utcnow().isoformat()
        
        # Update
        await update(AGENTS_TABLE, update_data, filters={"id": agent_id})
        
        logger.info(f"Agent updated: {agent_id}")
        
        return {"status": "updated", "agent_id": agent_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.delete("/organizations/{org_id}/agents/{agent_id}")
async def delete_agent(request: Request, org_id: str, agent_id: str):
    """
    Delete an agent.
    Requires admin access.
    Cannot delete the last agent in an organization.
    """
    try:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        # Check admin permission
        if not await _require_admin(user, org_id):
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores podem excluir agentes"
            )
        
        _ensure_supabase()
        
        # Verify agent exists
        existing = await select(
            AGENTS_TABLE,
            filters={"id": agent_id, "organization_id": org_id}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Agente não encontrado")
        
        # Check if this is the last agent
        all_agents = await select(
            AGENTS_TABLE,
            filters={"organization_id": org_id}
        )
        if len(all_agents) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Não é possível excluir o último agente da organização"
            )
        
        # Get default agent for reassignment
        default_agent = next(
            (a for a in all_agents if a["is_default"] and a["id"] != agent_id),
            all_agents[0] if all_agents[0]["id"] != agent_id else all_agents[1]
        )
        
        # Reassign conversations using this agent to default
        await update(
            CONVERSATIONS_TABLE,
            {"agent_id": default_agent["id"]},
            filters={"agent_id": agent_id}
        )
        
        # Delete agent
        await delete(AGENTS_TABLE, filters={"id": agent_id})
        
        logger.info(f"Agent deleted: {agent_id}, conversations reassigned to {default_agent['id']}")
        
        return {"status": "deleted", "agent_id": agent_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.post("/organizations/{org_id}/agents/{agent_id}/set-default")
async def set_default_agent(request: Request, org_id: str, agent_id: str):
    """
    Set an agent as the default for the organization.
    Requires admin access.
    """
    try:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        # Check admin permission
        if not await _require_admin(user, org_id):
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores podem definir agente padrão"
            )
        
        _ensure_supabase()
        
        # Verify agent exists
        existing = await select(
            AGENTS_TABLE,
            filters={"id": agent_id, "organization_id": org_id}
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Agente não encontrado")
        
        # Unset other defaults
        await update(
            AGENTS_TABLE,
            {"is_default": False, "updated_at": __import__("datetime").datetime.utcnow().isoformat()},
            filters={"organization_id": org_id, "is_default": True}
        )
        
        # Set this agent as default
        await update(
            AGENTS_TABLE,
            {"is_default": True, "updated_at": __import__("datetime").datetime.utcnow().isoformat()},
            filters={"id": agent_id}
        )
        
        logger.info(f"Agent {agent_id} set as default for org {org_id}")
        
        return {"status": "updated", "agent_id": agent_id}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.put("/conversations/{phone}/agent")
async def switch_conversation_agent(request: Request, phone: str, body: SwitchAgentRequest):
    """
    Switch the agent for a conversation.
    Requires admin access to the conversation's organization.
    """
    try:
        user = await get_current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Não autenticado")
        
        _ensure_supabase()
        
        # Get conversation
        conv_rows = await select(CONVERSATIONS_TABLE, filters={"phone": phone})
        if not conv_rows:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        
        conv = conv_rows[0]
        org_id = conv.get("organization_id")
        
        if not org_id:
            raise HTTPException(
                status_code=400,
                detail="Conversa não está associada a uma organização"
            )
        
        # Check admin permission for this org
        if not await _require_admin(user, org_id):
            raise HTTPException(
                status_code=403,
                detail="Apenas administradores podem trocar agentes"
            )
        
        # Verify agent exists and belongs to this org
        agent_rows = await select(
            AGENTS_TABLE,
            filters={"id": body.agent_id, "organization_id": org_id}
        )
        if not agent_rows:
            raise HTTPException(
                status_code=404,
                detail="Agente não encontrado nesta organização"
            )
        
        # Update conversation
        await update(
            CONVERSATIONS_TABLE,
            {"agent_id": body.agent_id},
            filters={"phone": phone}
        )
        
        agent = agent_rows[0]
        logger.info(f"Conversation {phone} switched to agent {agent['name']}")
        
        return {
            "status": "updated",
            "phone": phone,
            "agent_id": body.agent_id,
            "agent_name": agent["name"]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching agent for {phone}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
