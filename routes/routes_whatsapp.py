"""
WhatsApp Connection Routes - BCOMM CRM
Endpoints para conectar/desconectar organizações ao WhatsApp via Evolution API.
Gerencia instâncias, QR codes e status de conexão.
"""
import re
import uuid
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from config import settings
from services.database import select, insert, delete, get_client, get_supabase

logger = logging.getLogger("bridge")

router = APIRouter(prefix="/crm", tags=["whatsapp"])

# ── Tables ──────────────────────────────────────────────────────
WHATSAPP_TABLE = "bcomm_inbox.whatsapp_numbers"
ORGS_TABLE = "bcomm_inbox.organizations"

# ── Helpers ─────────────────────────────────────────────────────


def _ensure_supabase():
    """Inicializa Supabase se ainda não estiver conectado."""
    if get_client() is None:
        get_supabase(settings.supabase_url, settings.supabase_service_key)


async def _get_current_user(request: Request) -> dict:
    """Extrai usuário do cookie JWT da request.
    Levanta HTTPException 401 se não autenticado.
    """
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
    rows = await select("bcomm_inbox.users", filters={"id": supabase_user_id})
    if not rows:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    return rows[0]


async def _evolution_request(method: str, path: str, data: dict = None) -> dict:
    """Make authenticated request to Evolution API."""
    async with httpx.AsyncClient() as client:
        url = f"{settings.evolution_api_url.rstrip('/')}{path}"
        headers = {
            "apikey": settings.evolution_api_key,
            "Content-Type": "application/json",
        }
        if method == "GET":
            resp = await client.get(url, headers=headers, timeout=30)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=data, timeout=30)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers, timeout=30)
        else:
            raise ValueError(f"Unsupported method: {method}")
        resp.raise_for_status()
        return resp.json()


def _slugify(name: str) -> str:
    """Gera slug a partir do nome: lowercase, apenas alphanumericos e hifens."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


# ── Endpoints ───────────────────────────────────────────────────


@router.post("/organizations/{org_id}/whatsapp/connect")
async def connect_whatsapp(request: Request, org_id: str):
    """
    Cria uma instância Evolution API para a organização e retorna QR code.
    """
    try:
        # 1. Verificar autenticação
        user = await _get_current_user(request)

        _ensure_supabase()

        # 2. Verificar se organização existe
        org_rows = await select(ORGS_TABLE, filters={"id": org_id})
        if not org_rows:
            raise HTTPException(status_code=404, detail="Organização não encontrada")
        org = org_rows[0]

        # 3. Verificar se já está conectada
        existing = await select(
            WHATSAPP_TABLE, filters={"organization_id": org_id}
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Organização já possui WhatsApp conectado. "
                       "Desconecte antes de criar uma nova instância.",
            )

        # 4. Gerar nome da instância: slug(org_name) + "-" + short_uuid
        org_name = org.get("name", "org")
        slug = _slugify(org_name)
        short_id = uuid.uuid4().hex[:8]
        instance_name = f"{slug}-{short_id}"

        # 5. Chamar Evolution API para criar instância
        try:
            evo_response = await _evolution_request(
                "POST",
                "/instance/create",
                {
                    "instanceName": instance_name,
                    "integration": "WHATSAPP-BAILEYS",
                },
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Evolution API error creating instance: {e.response.status_code} "
                f"{e.response.text}"
            )
            raise HTTPException(
                status_code=502,
                detail=f"Erro ao criar instância na Evolution API: {e.response.status_code}",
            )
        except Exception as e:
            logger.error(f"Failed to reach Evolution API: {e}")
            raise HTTPException(
                status_code=502,
                detail="Não foi possível conectar ao Evolution API",
            )

        # 6. Salvar no banco de dados
        now = __import__("datetime").datetime.utcnow().isoformat()
        wa_record = {
            "evolution_instance": instance_name,
            "organization_id": org_id,
            "phone_number": "",
            "created_at": now,
        }
        result = await insert(WHATSAPP_TABLE, wa_record)

        logger.info(
            f"WhatsApp instance created: {instance_name} for org {org_id} "
            f"by user {user.get('email', 'unknown')}"
        )

        # 7. Retornar resposta
        return {
            "instance": instance_name,
            "status": "connecting",
            "message": "Instância criada. Escaneie o QR Code.",
            "evo_response": evo_response,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting WhatsApp for org {org_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/organizations/{org_id}/whatsapp/status")
async def whatsapp_status(request: Request, org_id: str):
    """
    Retorna status de conexão do WhatsApp da organização.
    """
    try:
        # 1. Verificar autenticação
        user = await _get_current_user(request)

        _ensure_supabase()

        # 2. Buscar WhatsApp numbers da organização
        rows = await select(WHATSAPP_TABLE, filters={"organization_id": org_id})
        if not rows:
            return {
                "connected": False,
                "instance": None,
                "phone": None,
                "status": "not_connected",
                "message": "Nenhum WhatsApp conectado",
            }

        wa = rows[0]
        instance = wa.get("evolution_instance", "")

        # 3. Chamar Evolution API para verificar estado da conexão
        try:
            evo_response = await _evolution_request(
                "GET",
                f"/instance/connectionState/{instance}",
            )
            state = evo_response.get("state", "unknown")
            connected = state == "open"
        except Exception as e:
            logger.warning(f"Failed to check Evolution API state for {instance}: {e}")
            connected = False
            state = "error"

        phone = wa.get("phone_number", "") or None

        return {
            "connected": connected,
            "instance": instance,
            "phone": phone,
            "status": state,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking WhatsApp status for org {org_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.delete("/organizations/{org_id}/whatsapp/disconnect")
async def disconnect_whatsapp(request: Request, org_id: str):
    """
    Desconecta e remove a instância WhatsApp da organização.
    """
    try:
        # 1. Verificar autenticação
        user = await _get_current_user(request)

        _ensure_supabase()

        # 2. Buscar WhatsApp da organização
        rows = await select(WHATSAPP_TABLE, filters={"organization_id": org_id})
        if not rows:
            raise HTTPException(
                status_code=404, detail="Nenhum WhatsApp conectado para esta organização"
            )

        wa = rows[0]
        instance = wa.get("evolution_instance", "")
        wa_id = wa.get("id", "")

        # 3. Chamar Evolution API para deletar instância
        try:
            await _evolution_request("DELETE", f"/instance/delete/{instance}")
        except httpx.HTTPStatusError as e:
            # 404 = instância já removida, tratar como sucesso
            if e.response.status_code == 404:
                logger.warning(
                    f"Evolution instance {instance} not found (already deleted?)"
                )
            else:
                logger.error(
                    f"Evolution API error deleting instance: {e.response.status_code} "
                    f"{e.response.text}"
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Erro ao deletar instância na Evolution API: {e.response.status_code}",
                )
        except Exception as e:
            logger.error(f"Failed to reach Evolution API for deletion: {e}")
            raise HTTPException(
                status_code=502,
                detail="Não foi possível conectar ao Evolution API para deletar instância",
            )

        # 4. Deletar do banco de dados
        await delete(WHATSAPP_TABLE, filters={"id": wa_id})

        logger.info(
            f"WhatsApp instance deleted: {instance} for org {org_id} "
            f"by user {user.get('email', 'unknown')}"
        )

        return {"status": "ok", "message": "WhatsApp desconectado com sucesso"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting WhatsApp for org {org_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@router.get("/organizations/{org_id}/whatsapp/qr")
async def get_qr(request: Request, org_id: str):
    """
    Retorna QR code atual para escaneamento.
    """
    try:
        # 1. Verificar autenticação
        user = await _get_current_user(request)

        _ensure_supabase()

        # 2. Buscar instância da organização
        rows = await select(WHATSAPP_TABLE, filters={"organization_id": org_id})
        if not rows:
            raise HTTPException(
                status_code=404, detail="Nenhum WhatsApp conectado para esta organização"
            )

        instance = rows[0].get("evolution_instance", "")

        # 3. Chamar Evolution API para obter QR code
        try:
            evo_response = await _evolution_request(
                "GET",
                f"/instance/connect/{instance}",
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Evolution API error getting QR: {e.response.status_code} "
                f"{e.response.text}"
            )
            raise HTTPException(
                status_code=502,
                detail=f"Erro ao obter QR code da Evolution API: {e.response.status_code}",
            )
        except Exception as e:
            logger.error(f"Failed to reach Evolution API for QR: {e}")
            raise HTTPException(
                status_code=502,
                detail="Não foi possível conectar ao Evolution API",
            )

        # Extrair QR code da resposta
        qrcode = evo_response.get("base64", "") or evo_response.get("qrcode", "")

        if not qrcode:
            # Se não há QR, pode estar já conectado
            state = evo_response.get("state", "unknown")
            if state == "open":
                return {
                    "qrcode": None,
                    "status": "connected",
                    "message": "WhatsApp já conectado. Não é necessário escanear QR code.",
                }
            return {
                "qrcode": None,
                "status": "connecting",
                "message": "Aguardando QR code... Tente novamente em alguns segundos.",
            }

        logger.info(f"QR code retrieved for instance {instance} (org {org_id})")

        return {
            "qrcode": qrcode,
            "status": "connecting",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting QR for org {org_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")
