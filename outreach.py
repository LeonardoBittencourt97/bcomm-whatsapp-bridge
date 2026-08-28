"""
Endpoints de Outreach - Contato com Leads
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import json
import logging

from services.database import get_supabase, select, upsert, update, insert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outreach", tags=["outreach"])

TABLE_OUTREACH = "outreach_tasks"


class OutreachStartRequest(BaseModel):
    phone: str
    name: Optional[str] = ""
    company: Optional[str] = ""
    email: Optional[str] = ""
    instructions: str
    initial_message: str
    client_id: str = "BCOMM"


class OutreachUpdateRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@router.post("/start")
async def start_outreach(request: OutreachStartRequest):
    """Inicia contato com um lead"""
    task_id = str(uuid.uuid4())
    phone = request.phone.replace("-", "").replace(" ", "").replace("+", "")
    if not phone.startswith("55"):
        phone = "55" + phone

    now = datetime.now().isoformat()

    task = {
        "id": task_id,
        "contact_phone": phone,
        "contact_name": request.name,
        "contact_company": request.company,
        "contact_email": request.email,
        "instructions": request.instructions,
        "initial_message": request.initial_message,
        "created_by": request.client_id,
        "status": "sending",
        "created_at": now,
        "updated_at": now,
        "messages_sent": 0,
        "messages_received": 0,
    }

    # Insert task into Supabase
    result = await insert(TABLE_OUTREACH, task)
    if result is None:
        raise HTTPException(status_code=500, detail="Erro ao salvar tarefa no Supabase")

    try:
        from services.evolution import EvolutionClient
        evo = EvolutionClient()
        send_result = await evo.send_text(phone, request.initial_message)
        await evo.close()
        if send_result.get("success"):
            update_data = {
                "status": "active",
                "messages_sent": 1,
                "updated_at": datetime.now().isoformat(),
                "started_at": datetime.now().isoformat(),
            }
            await update(TABLE_OUTREACH, update_data, {"id": task_id})
            task.update(update_data)
        else:
            update_data = {
                "status": "failed",
                "error_message": send_result.get("error"),
                "updated_at": datetime.now().isoformat(),
            }
            await update(TABLE_OUTREACH, update_data, {"id": task_id})
            task.update(update_data)
    except Exception as e:
        update_data = {
            "status": "failed",
            "error_message": str(e),
            "updated_at": datetime.now().isoformat(),
        }
        await update(TABLE_OUTREACH, update_data, {"id": task_id})
        task.update(update_data)

    return {
        "status": task["status"],
        "task_id": task_id,
        "message": f"Contato iniciado com {request.name or phone}"
    }


@router.get("/list")
async def list_outreach_tasks(status: Optional[str] = None):
    if status:
        tasks = await select(TABLE_OUTREACH, filters={"status": status}, order="created_at.desc")
    else:
        tasks = await select(TABLE_OUTREACH, order="created_at.desc")
    return {"tasks": tasks, "total": len(tasks)}


@router.get("/stats/summary")
async def get_outreach_stats():
    all_tasks = await select(TABLE_OUTREACH, columns="status")
    statuses = [t["status"] for t in all_tasks]
    return {
        "total": len(statuses),
        "pending": statuses.count("pending"),
        "active": statuses.count("active"),
        "completed": statuses.count("completed"),
        "failed": statuses.count("failed"),
        "cancelled": statuses.count("cancelled"),
        "paused": statuses.count("paused"),
        "sending": statuses.count("sending"),
    }


@router.get("/{task_id}")
async def get_outreach_task(task_id: str):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return tasks[0]


@router.put("/{task_id}")
async def update_outreach_task(task_id: str, request: OutreachUpdateRequest):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    update_data = {"updated_at": datetime.now().isoformat()}
    if request.status:
        update_data["status"] = request.status
    if request.notes:
        update_data["context"] = {"notes": request.notes}

    await update(TABLE_OUTREACH, update_data, {"id": task_id})
    return {"status": "updated", "task_id": task_id}


@router.delete("/{task_id}")
async def cancel_outreach_task(task_id: str):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    update_data = {
        "status": "cancelled",
        "updated_at": datetime.now().isoformat(),
    }
    await update(TABLE_OUTREACH, update_data, {"id": task_id})
    return {"status": "cancelled"}


@router.post("/{task_id}/stop")
async def stop_outreach_task(task_id: str, reason: str = ""):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    task = tasks[0]
    now = datetime.now().isoformat()
    update_data = {
        "status": "cancelled",
        "updated_at": now,
        "completed_at": now,
        "context": {"cancelled_reason": reason},
    }
    await update(TABLE_OUTREACH, update_data, {"id": task_id})

    # Also pause the contact
    from services.database import get_client
    client = get_client()
    if client:
        try:
            contact_key = f"BCOMM:{task['contact_phone']}"
            settings_row = await select("settings", filters={"key": "paused_contacts"})
            paused = settings_row[0]["value"].get("paused", []) if settings_row else []
            if contact_key not in paused:
                paused.append(contact_key)
            await upsert("settings", {
                "key": "paused_contacts",
                "value": {"paused": paused},
                "updated_at": now,
            }, on_conflict="key")
        except Exception as e:
            logger.error(f"Erro ao pausar contato: {e}")

    return {"status": "stopped", "task_id": task_id}


@router.post("/{task_id}/command")
async def send_command_to_agent(task_id: str, command: str):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    now = datetime.now().isoformat()
    update_data = {
        "last_command": command,
        "command_sent_at": now,
        "updated_at": now,
    }
    await update(TABLE_OUTREACH, update_data, {"id": task_id})
    return {"status": "command_sent", "command": command}


@router.put("/{task_id}/instructions")
async def update_task_instructions(task_id: str, instructions: str):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    now = datetime.now().isoformat()
    update_data = {
        "instructions": instructions,
        "updated_at": now,
    }
    await update(TABLE_OUTREACH, update_data, {"id": task_id})
    return {"status": "instructions_updated", "task_id": task_id}


@router.post("/{task_id}/pause")
async def pause_outreach_task(task_id: str):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    task = tasks[0]
    now = datetime.now().isoformat()

    # Update task status
    await update(TABLE_OUTREACH, {"status": "paused", "updated_at": now}, {"id": task_id})

    # Also pause the contact
    from services.database import get_client
    client = get_client()
    if client:
        try:
            contact_key = f"BCOMM:{task['contact_phone']}"
            settings_row = await select("settings", filters={"key": "paused_contacts"})
            paused = settings_row[0]["value"].get("paused", []) if settings_row else []
            if contact_key not in paused:
                paused.append(contact_key)
            await upsert("settings", {
                "key": "paused_contacts",
                "value": {"paused": paused},
                "updated_at": now,
            }, on_conflict="key")
        except Exception as e:
            logger.error(f"Erro ao pausar contato: {e}")

    return {"status": "paused", "task_id": task_id}


@router.post("/{task_id}/resume")
async def resume_outreach_task(task_id: str):
    tasks = await select(TABLE_OUTREACH, filters={"id": task_id})
    if not tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")

    task = tasks[0]
    now = datetime.now().isoformat()

    # Update task status
    await update(TABLE_OUTREACH, {"status": "active", "updated_at": now}, {"id": task_id})

    # Also resume the contact
    from services.database import get_client
    client = get_client()
    if client:
        try:
            contact_key = f"BCOMM:{task['contact_phone']}"
            settings_row = await select("settings", filters={"key": "paused_contacts"})
            paused = settings_row[0]["value"].get("paused", []) if settings_row else []
            if contact_key in paused:
                paused.remove(contact_key)
            await upsert("settings", {
                "key": "paused_contacts",
                "value": {"paused": paused},
                "updated_at": now,
            }, on_conflict="key")
        except Exception as e:
            logger.error(f"Erro ao retomar contato: {e}")

    return {"status": "resumed", "task_id": task_id}


@router.post("/send")
async def send_direct_message(phone: str, message: str, client_id: str = "BCOMM"):
    """Envia mensagem direta"""
    phone = phone.replace("-", "").replace(" ", "").replace("+", "")
    if not phone.startswith("55"):
        phone = "55" + phone

    try:
        from services.evolution import EvolutionClient
        evo = EvolutionClient()
        result = await evo.send_text(phone, message)
        await evo.close()
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}
