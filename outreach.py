"""
Endpoints de Outreach - Contato com Leads
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import uuid

router = APIRouter(prefix="/outreach", tags=["outreach"])

# Schema de entrada
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

# Armazenamento temporário (em produção usar banco)
outreach_tasks = {}

@router.post("/start")
async def start_outreach(request: OutreachStartRequest):
    """Inicia contato com um lead"""
    
    # Criar tarefa
    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "contact_phone": request.phone,
        "contact_name": request.name,
        "contact_company": request.company,
        "contact_email": request.email,
        "instructions": request.instructions,
        "initial_message": request.initial_message,
        "client_id": request.client_id,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "messages_sent": 0,
        "messages_received": 0
    }
    
    outreach_tasks[task_id] = task
    
    #TODO: Enviar mensagem inicial via Evolution API
    # await send_initial_message(task)
    
    #TODO: Criar conversa no inbox
    # await create_conversation(task)
    
    return {
        "status": "started",
        "task_id": task_id,
        "message": f"Contato iniciado com {request.name or request.phone}"
    }

@router.get("/list")
async def list_outreach_tasks(status: Optional[str] = None):
    """Lista tarefas de outreach"""
    tasks = list(outreach_tasks.values())
    
    if status:
        tasks = [t for t in tasks if t["status"] == status]
    
    return {"tasks": tasks, "total": len(tasks)}

@router.get("/{task_id}")
async def get_outreach_task(task_id: str):
    """Busca tarefa de outreach"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    return outreach_tasks[task_id]

@router.put("/{task_id}")
async def update_outreach_task(task_id: str, request: OutreachUpdateRequest):
    """Atualiza tarefa de outreach"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    task = outreach_tasks[task_id]
    
    if request.status:
        task["status"] = request.status
    if request.notes:
        task["notes"] = request.notes
    
    task["updated_at"] = datetime.now().isoformat()
    
    return {"status": "updated", "task": task}

@router.delete("/{task_id}")
async def cancel_outreach_task(task_id: str):
    """Cancela tarefa de outreach"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    outreach_tasks[task_id]["status"] = "cancelled"
    outreach_tasks[task_id]["updated_at"] = datetime.now().isoformat()
    
    return {"status": "cancelled"}

@router.get("/stats/summary")
async def get_outreach_stats():
    """Retorna estatísticas de outreach"""
    tasks = list(outreach_tasks.values())
    
    stats = {
        "total": len(tasks),
        "pending": len([t for t in tasks if t["status"] == "pending"]),
        "active": len([t for t in tasks if t["status"] == "active"]),
        "completed": len([t for t in tasks if t["status"] == "completed"]),
        "failed": len([t for t in tasks if t["status"] == "failed"]),
        "cancelled": len([t for t in tasks if t["status"] == "cancelled"])
    }
    
    return stats


# ── Novos endpoints de controle ──────────────────────────────────

@router.post("/{task_id}/stop")
async def stop_outreach_task(task_id: str, reason: str = ""):
    """Para o contato com um lead"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    task = outreach_tasks[task_id]
    task["status"] = "cancelled"
    task["cancelled_reason"] = reason
    task["updated_at"] = datetime.now().isoformat()
    
    # Pausar conversa
    from config import settings
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"BCOMM:{task['contact_phone']}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    
    return {"status": "stopped", "task": task}

@router.post("/{task_id}/command")
async def send_command_to_agent(task_id: str, command: str):
    """Envia comando direto para o agente"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    task = outreach_tasks[task_id]
    task["last_command"] = command
    task["command_sent_at"] = datetime.now().isoformat()
    task["updated_at"] = datetime.now().isoformat()
    
    return {"status": "command_sent", "command": command}

@router.put("/{task_id}/instructions")
async def update_task_instructions(task_id: str, instructions: str):
    """Atualiza as instruções do agente"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    task = outreach_tasks[task_id]
    task["instructions"] = instructions
    task["instructions_updated_at"] = datetime.now().isoformat()
    task["updated_at"] = datetime.now().isoformat()
    
    return {"status": "instructions_updated", "task": task}

@router.post("/{task_id}/pause")
async def pause_outreach_task(task_id: str):
    """Pausa o contato (agente para de responder)"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    task = outreach_tasks[task_id]
    task["status"] = "paused"
    task["updated_at"] = datetime.now().isoformat()
    
    # Pausar conversa
    from config import settings
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"BCOMM:{task['contact_phone']}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    
    return {"status": "paused", "task": task}

@router.post("/{task_id}/resume")
async def resume_outreach_task(task_id: str):
    """Retoma o contato"""
    if task_id not in outreach_tasks:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada")
    
    task = outreach_tasks[task_id]
    task["status"] = "active"
    task["updated_at"] = datetime.now().isoformat()
    
    # Retomar conversa
    from config import settings
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"BCOMM:{task['contact_phone']}"
    if contact_key in paused:
        paused.remove(contact_key)
    settings.paused_contacts = ",".join(paused)
    
    return {"status": "resumed", "task": task}

