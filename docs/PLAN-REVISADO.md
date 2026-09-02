# Plano Revisado: CRM BCOMM - Próximos Passos

**Data:** 2026-09-02
**Status:** Em andamento

---

## Contexto

O CRM já tem 6 features implementadas mas nem todas estão visíveis no UI. O usuário quer:
1. **Remover outreach** por agora (foco em atendimento)
2. **Trocar agentes** dentro da conversa (ex: usar Ana para público específico)
3. **Organização BCOMM** com conversas existentes
4. **Status WhatsApp** nas configurações da organização

---

## 🔴 Prioridade 1: Organização BCOMM + WhatsApp

### 1.1 Criar Organização "Org BCOMM"

**Backend:**
- Criar org no Supabase: `bcomm_inbox.organizations`
- Nome: "Org BCOMM"
- Configurações padrão

**Frontend:**
- A组织ação aparece no seletor do menu superior
- Usuário pode selecionar para ver apenas conversas dessa org

### 1.2 Associar Conversas Existentes

**Backend:**
- Endpoint: `POST /crm/organizations/{org_id}/associate-conversations`
- Move conversas sem `organization_id` para a Org BCOMM
- Log de auditoria

### 1.3 Status WhatsApp nas Configs da Org

**Backend:**
- Endpoint: `GET /crm/organizations/{org_id}/whatsapp/status` (já existe)
- Endpoint: `POST /crm/organizations/{org_id}/whatsapp/connect` (já existe)
- Endpoint: `DELETE /crm/organizations/{org_id}/whatsapp/disconnect` (já existe)

**Frontend (organizations.html):**
- Seção "WhatsApp" na página da organização
- Status: Conectado/Desconectado
- Botão Conectar (mostra QR Code)
- Botão Desconectar
- Telefone conectado

---

## 🟡 Prioridade 2: Troca de Agentes

### 2.1 Agentes Disponíveis

**Prompts existentes:**
- `atendimento.md` - Atendimento geral
- `agendamento.md` - Agendamento
- `financeiro.md` - Financeiro

**Novo prompt (opcional):**
- `vendas.md` - Vendas/outreach (desativado por agora)

### 2.2 Campo `agent_type` na Conversa

**Backend:**
- Adicionar coluna `agent_type` na tabela `conversations`
- Valores: `atendimento`, `agendamento`, `financeiro`, `manual`
- Default: `atendimento`

**Migração:**
```sql
ALTER TABLE bcomm_inbox.conversations 
ADD COLUMN IF NOT EXISTS agent_type VARCHAR(50) DEFAULT 'atendimento';
```

### 2.3 Endpoint para Trocar Agente

**Backend:**
- `PUT /crm/conversations/{phone}/agent`
- Body: `{ "agent_type": "agendamento" }`
- Valida se o prompt existe
- Atualiza `agent_type` na conversa
- O próximo processamento usa o novo prompt

### 2.4 UI para Trocar Agente

**Frontend (crm.html):**
- Dropdown no header da conversa (ao lado do nome)
- Opções: Atendimento, Agendamento, Financeiro
- Ao selecionar:
  1. Chama `PUT /crm/conversations/{phone}/agent`
  2. Mostra toast confirmando
  3. Próxima mensagem usa o novo agente

**Estilo:**
- Select estilizado seguindo design BCOMM
- Ícone do agente atual (🤖, 📅, 💰)
- Badge mostrando agente ativo

### 2.5 Processamento com Agente Correto

**Backend (handlers/messages.py):**
- Buscar `agent_type` da conversa antes de processar
- Carregar prompt correspondente: `_load_prompt(conversation_agent_type)`
- Se `agent_type = "manual"`, não processar com IA

---

## 🟢 Prioridade 3: Features Não Implementadas no UI

### 3.1 Features JÁ no UI (verificado)

| Feature | Status | Onde |
|---------|--------|------|
| Métricas Dashboard | ✅ | dashboard.html |
| Config Agente | ✅ | config.html (aba Agente) |
| Transferir Humano | ✅ | crm.html (botão) |
| Resumo Conversa | ✅ | crm.html (sidebar) |
| Status Processamento | ✅ | crm.html (badge) |
| WhatsApp QR/Connect | ✅ | config.html (aba WhatsApp) |

### 3.2 Features que FALTA implementar no UI

| Feature | Descrição | Complexidade |
|---------|-----------|--------------|
| **Trocar Agente** | Selecionar agente na conversa | Média |
| **Filtros Avançados** | Filtrar por agente, período, status | Baixa |
| **Export Conversas** | Download CSV/JSON | Baixa |
| **Notas Rápidas** | Adicionar nota na conversa | Baixa |
| **Histórico de Agentes** | Ver qual agente respondeu cada mensagem | Média |

---

## 📋 Ordem de Implementação

### Fase 1: Organização BCOMM (agora)
1. Criar org "Org BCOMM" no banco
2. Associar conversas existentes
3. Adicionar status WhatsApp na página da org
4. Testar seletor de org no menu

### Fase 2: Troca de Agentes (próxima)
1. Criar coluna `agent_type` na tabela
2. Criar endpoint PUT para trocar agente
3. Atualizar handlers/messages.py para usar prompt correto
4. Adicionar dropdown no crm.html
5. Testar troca em tempo real

### Fase 3: Features Extras (depois)
1. Filtros avançados
2. Export de conversas
3. Notas rápidas
4. Histórico de agentes

---

## 🔧 Técnicos

### Tabelas Afetadas
- `bcomm_inbox.organizations` - Nova org
- `bcomm_inbox.conversations` - Nova coluna `agent_type`
- `bcomm_inbox.whatsapp_numbers` - Status da connexão

### Endpoints Novos
- `POST /crm/organizations/{org_id}/associate-conversations`
- `PUT /crm/conversations/{phone}/agent`

### Arquivos Modificados
- `routes/crm_routes.py` - Novos endpoints
- `handlers/messages.py` - Lógica de agent_type
- `static/crm.html` - Dropdown de agentes
- `static/organizations.html` - Status WhatsApp
- `migrations/add_agent_type.sql` - Migração

---

## ❓ Perguntas para o Usuário

1. **Org BCOMM:** Deve ser a org padrão para todas as conversas não asignadas?
2. **Agentes:** Quais prompts devem estar disponíveis? (atendimento, agendamento, financeiro)
3. **Outreach:** Mantemos o prompt `vendas.md` mas desativado, ou removemos?
4. **Permissões:** Todos os usuários podem trocar agentes ou só admins?

---

## ✅ Critérios de Sucesso

- [ ] Org BCOMM criada e visível no seletor
- [ ] Conversas existentes associadas à org
- [ ] Status WhatsApp funcionando nas configs da org
- [ ] Dropdown de agentes no crm.html
- [ ] Troca de agente altera o comportamento do bot
- [ ] Teste end-to-end: enviar msg → verificar qual agente responde
