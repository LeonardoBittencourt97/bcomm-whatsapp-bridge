"""
Comandos de Outreach - Controlar contatos com leads
"""

# Funções de controle de outreach

async def stop_outreach(task_id: str, reason: str = ""):
    """Para o contato com um lead"""
    # Atualizar status da tarefa
    outreach_tasks[task_id]["status"] = "cancelled"
    outreach_tasks[task_id]["cancelled_reason"] = reason
    outreach_tasks[task_id]["updated_at"] = datetime.now().isoformat()
    
    # Pausar a conversa
    contact_phone = outreach_tasks[task_id]["contact_phone"]
    await pause_conversation(contact_phone, reason)
    
    return {"status": "stopped", "reason": reason}

async def pause_conversation(phone: str, reason: str = ""):
    """Pausa uma conversa específica"""
    # Adicionar à lista de contatos pausados
    from config import settings
    paused = [c.strip() for c in settings.paused_contacts.split(",") if c.strip()]
    contact_key = f"BCOMM:{phone}"
    if contact_key not in paused:
        paused.append(contact_key)
    settings.paused_contacts = ",".join(paused)
    
    # Salvar em arquivo
    save_paused_contacts()
    
    return {"status": "paused"}

async def send_agent_command(task_id: str, command: str):
    """Envia comando direto para o agente"""
    # Registrar comando
    outreach_tasks[task_id]["last_command"] = command
    outreach_tasks[task_id]["command_sent_at"] = datetime.now().isoformat()
    outreach_tasks[task_id]["updated_at"] = datetime.now().isoformat()
    
    #TODO: Enviar comando via sistema de mensagens
    # O agente deve processar este comando e ajustar seu comportamento
    
    return {"status": "command_sent", "command": command}

async def update_instructions(task_id: str, new_instructions: str):
    """Atualiza as instruções do agente para um lead"""
    outreach_tasks[task_id]["instructions"] = new_instructions
    outreach_tasks[task_id]["instructions_updated_at"] = datetime.now().isoformat()
    outreach_tasks[task_id]["updated_at"] = datetime.now().isoformat()
    
    return {"status": "instructions_updated"}

