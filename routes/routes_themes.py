"""
Endpoints para customizacao de tema por organizacao.
Usa a tabela bcomm_inbox.settings (key-value store) para persistencia.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import json
import logging

from routes.deps import get_current_user, is_unrestricted, get_user_org_ids
from services.database import select, upsert, delete

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/crm/themes", tags=["themes"])

SETTINGS_TABLE = "bcomm_inbox.settings"

THEME_KEY_PREFIX = "theme:"

# Variaveis CSS customizaveis com valores padrao
DEFAULT_THEME = {
    "bg": "#0b0b0c",
    "surface": "#0b0e14",
    "card": "#13161a",
    "elevated": "#1a1d21",
    "border": "#292d30",
    "border-hover": "#464a4d",
    "text": "#ffffff",
    "text2": "#a1a4a5",
    "muted": "#6e727a",
    "accent": "#3b9eff",
    "accent2": "#5aadff",
    "green": "#34c759",
    "red": "#ff453a",
    "yellow": "#ffd60a",
    "orange": "#ff9500",
}


def _get_active_org_id(request: Request) -> Optional[str]:
    org_cookie = request.cookies.get("bcomm_org_id")
    if org_cookie:
        return org_cookie if org_cookie != "" else None
    return None


async def _load_theme_from_db(org_id: str) -> dict:
    key = f"{THEME_KEY_PREFIX}{org_id}"
    rows = await select(SETTINGS_TABLE, filters={"key": key})
    if rows and rows[0].get("value"):
        try:
            return json.loads(rows[0]["value"])
        except (json.JSONDecodeError, KeyError, TypeError):
            return {}
    return {}


async def _save_theme_to_db(org_id: str, theme: dict):
    key = f"{THEME_KEY_PREFIX}{org_id}"
    data = {
        "key": key,
        "value": json.dumps(theme),
        "updated_at": "now()",
    }
    await upsert(SETTINGS_TABLE, data, on_conflict="key")


@router.get("/current")
async def get_current_theme(request: Request):
    await get_current_user(request)
    org_id = _get_active_org_id(request)

    if not org_id:
        return {"theme": DEFAULT_THEME, "is_default": True, "organization_id": None}

    saved = await _load_theme_from_db(org_id)
    merged = {**DEFAULT_THEME, **saved}

    return {
        "theme": merged,
        "is_default": len(saved) == 0,
        "organization_id": org_id,
    }


class ThemeUpdate(BaseModel):
    theme: dict


@router.put("/current")
async def update_theme(request: Request, body: ThemeUpdate):
    user = await get_current_user(request)
    org_id = _get_active_org_id(request)

    if not org_id:
        raise HTTPException(status_code=400, detail="Selecione uma organizacao antes de editar o tema")

    if user.get("role") == "agent":
        raise HTTPException(status_code=403, detail="Agentes nao podem editar o tema")

    if not is_unrestricted(user):
        org_ids = await get_user_org_ids(user["id"])
        if org_id not in org_ids:
            raise HTTPException(status_code=403, detail="Sem acesso a esta organizacao")

    merged = {**DEFAULT_THEME, **body.theme}

    for key, value in merged.items():
        if not isinstance(value, str) or not value.startswith("#") or len(value) not in (4, 7):
            raise HTTPException(
                status_code=400,
                detail=f"Cor invalida para {key}: {value}. Use formato hex (#fff ou #ffffff)"
            )

    await _save_theme_to_db(org_id, merged)

    logger.info(f"Tema atualizado para org {org_id} por {user['email']}")
    return {"status": "ok", "theme": merged, "organization_id": org_id}


@router.post("/reset")
async def reset_theme(request: Request):
    user = await get_current_user(request)
    org_id = _get_active_org_id(request)

    if not org_id:
        raise HTTPException(status_code=400, detail="Selecione uma organizacao")

    if user.get("role") == "agent":
        raise HTTPException(status_code=403, detail="Agentes nao podem resetar o tema")

    if not is_unrestricted(user):
        org_ids = await get_user_org_ids(user["id"])
        if org_id not in org_ids:
            raise HTTPException(status_code=403, detail="Sem acesso a esta organizacao")

    key = f"{THEME_KEY_PREFIX}{org_id}"
    await delete(SETTINGS_TABLE, filters={"key": key})

    return {"status": "ok", "theme": DEFAULT_THEME, "organization_id": org_id}
