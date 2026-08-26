"""
Endpoints de Outreach - Contato com Leads
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid
import json
import os

router = APIRouter(prefix="/outreach", tags=["outreach"])

DATA_FILE = "/app/data/outreach_tasks.json"

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

def load_tasks():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_tasks(tasks):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(tasks, f, indent=2)

outreach_tasks = load_tasks()

@router.post("/start")
async def start_outreach(request: OutreachStartRequest):
    """Inicia contato com um lead"""
    task_id = str(uuid.uuid4())
    phone = request.phone.replace("-", "").replace(" ", "").replace("+", "")
    if not phone.startswith("55"):
        phone = "55" + phone
    
    task = {
        "id": task_id,
        "contact_phone": phone,
        "contact_name": request.name,
        "contact_company": request.company,
        "contact_email": request.email,
        "instructions": request.instructions,
        "initial_message": request.initial_message,
        "client_id": request.client_id,
        "status": "sending",
        "created_at": datetime.now().isoformat(),
        "messages_sent": 0,
        "messages_received": 0
    }
    
    outreach_tasks[task_id] = task
    save_tasks(outreach_tasks)
    
    try:
        from services.evolution import EvolutionClient
        evo = EvolutionClient()
        result = await evo.send_text(phone, request.initial_message)
        await evo.close()
        if result.get("success"):
            task["status"] = "active"
            task["messages_sent"] = 1
            task["message_id"] = result.get("message_id")
            task["started_at"] = datetime.now().isoformat()
        else:
            task["status"] = "failed"
            task["error"] = result.get("error")
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
    
    save_tasks(outreach_tasks)
    
    return {
        "status": task["status"],
        "task_id": task_id,
        "message": f"Contato iniciado com {request.name or phone}"
    }

@router.get("/list")
async def list_outreach_tasks(status: Optional[str] = None):
    tasks = list(outreach_tasks.values())
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    return {"tasks": tasks, "total": len(tasks)}

@router.get("/{task_id}")
async def get_outreach_task(task_id: str):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    return outreach_tasks[task_id]

@router.put("/{task_id}")
async def update_outreach_task(task_id: str, request: OutreachUpdateRequest):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    task = outreach_tasks[task_id]
    if request.status:
        task["status"] = request.status
    if request.notes:
        task["notes"] = request.notes
    task["updated_at"] = datetime.now().isoformat()
    save_tasks(outreach_tasks)
    return {"status": "updated", "task": task}

@router.delete("/{task_id}")
async def cancel_outreach_task(task_id: str):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    outreach_tasks[task_id]["status"] = "cancelled"
    outreach_tasks[task_id]["updated_at"] = datetime.now().isoformat()
    save_tasks(outreach_tasks)
    return {"status": "cancelled"}

@router.get("/stats/summary")
async def get_outreach_stats():
    tasks = list(outreach_tasks.values())
    return {
        "total": len(tasks),
        "pending": len([t for t in tasks if t["status"] == "pending"]),
        "active": len([t for t in tasks if t["status"] == "active"]),
        "completed": len([t for t in tasks if t["status"] == "completed"]),
        "failed": len([t for t in tasks if t["status"] == "failed"]),
        "cancelled": len([t for t in tasks if t["status"] == "cancelled"]),
        "paused": len([t for t in tasks if t["status"] == "paused"])
    }

@router.post("/{task_id}/stop")
async def stop_outreach_task(task_id: str, reason: str = ""):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    task = outreach_tasks[task_id]
    task["status"] = "cancelled"
    task["cancelled_reason"] = reason
    task["updated_at"] = datetime.now().isoformat()
    from config import settings
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"BCOMM:{task['contact_phone']}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    save_tasks(outreach_tasks)
    return {"status": "stopped", "task": task}

@router.post("/{task_id}/command")
async def send_command_to_agent(task_id: str, command: str):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    task = outreach_tasks[task_id]
    task["last_command"] = command
    task["command_sent_at"] = datetime.now().isoformat()
    task["updated_at"] = datetime.now().isoformat()
    save_tasks(outreach_tasks)
    return {"status": "command_sent", "command": command}

@router.put("/{task_id}/instructions")
async def update_task_instructions(task_id: str, instructions: str):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    task = outreach_tasks[task_id]
    task["instructions"] = instructions
    task["instructions_updated_at"] = datetime.now().isoformat()
    task["updated_at"] = datetime.now().isoformat()
    save_tasks(outreach_tasks)
    return {"status": "instructions_updated", "task": task}

@router.post("/{task_id}/pause")
async def pause_outreach_task(task_id: str):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    task = outreach_tasks[task_id]
    task["status"] = "paused"
    task["updated_at"] = datetime.now().isoformat()
    from config import settings
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"BCOMM:{task['contact_phone']}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    save_tasks(outreach_tasks)
    return {"status": "paused", "task": task}

@router.post("/{task_id}/resume")
async def resume_outreach_task(task_id: str):
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    task = outreach_tasks[task_id]
    task["status"] = "active"
    task["updated_at"] = datetime.now().isoformat()
    from config import settings
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"BCOMM:{task['contact_phone']}"
    if contact_key in paused:
        paused.remove(contact_key)
    settings.paused_contacts = ",".join(paused)
    save_tasks(outreach_tasks)
    return {"status": "resumed", "task": task}

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

