# Plano Revisado: CRM BCOMM - Multi-Tenant + Agentes

**Data:** 2026-09-02
**Status:** Revisado

---

## Contexto

Sistema multi-tenant onde cada organização tem seus próprios agentes (prompts). O usuário quer:
1. **CRUD de Agentes** por organização
2. **Controle de acesso** - Só Admin+ pode gerenciar agentes
3. **Conversas sem org** → Organização BCOMM
4. **Troca de agente** dentro da conversa

---

## 🏗️ Estrutura de Dados

### Tabela: `bcomm_inbox.agents` (NOVA)

```sql
CREATE TABLE bcomm_inbox.agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES bcomm_inbox.organizations(id),
    name VARCHAR(100) NOT NULL,           -- "Ana - Atendimento"
    slug VARCHAR(50) NOT NULL,            -- "atendimento", "agendamento"
    description TEXT,                      -- "Agente para suporte geral"
    system_prompt TEXT NOT NULL,           -- Prompt completo
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,     -- Agente padrão da org
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES bcomm_inbox.users(id),
    
    UNIQUE(organization_id, slug)
);

CREATE INDEX idx_agents_org ON bcomm_inbox.agents(organization_id);
```

### Tabela: `bcomm_inbox.conversations` (ALTERAÇÃO)

```sql
-- Adicionar coluna agent_id (substitui agent_type)
ALTER TABLE bcomm_inbox.conversations 
ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES bcomm_inbox.agents(id);

-- Migrar dados existentes (definir agente padrão)
UPDATE bcomm_inbox.conversations 
SET agent_id = (
    SELECT id FROM bcomm_inbox.agents 
    WHERE organization_id = conversations.organization_id 
    AND is_default = true 
    LIMIT 1
)
WHERE agent_id IS NULL;
```

---

## 📋 Funcionalidades

### 1. Gerenciamento de Agentes (CRUD)

#### 1.1 Listar Agentes
- **Endpoint:** `GET /crm/organizations/{org_id}/agents`
- **Retorna:** Lista de agentes da organização
- **Permissão:** Qualquer usuário autenticado

#### 1.2 Criar Agente
- **Endpoint:** `POST /crm/organizations/{org_id}/agents`
- **Body:**
  ```json
  {
    "name": "Ana - Vendas",
    "slug": "vendas",
    "description": "Agente focado em vendas",
    "system_prompt": "Você é Ana...",
    "is_default": false
  }
  ```
- **Permissão:** Admin+ da organização
- **Validação:** 
  - Slug único por org
  - Nome obrigatório
  - Prompt obrigatório

#### 1.3 Editar Agente
- **Endpoint:** `PUT /crm/organizations/{org_id}/agents/{agent_id}`
- **Body:** Mesmos campos da criação (todos opcionais)
- **Permissão:** Admin+ da organização
- **Regras:**
  - Se alterar `is_default`, desmarcar outros defaults da org
  - Atualizar `updated_at`

#### 1.4 Excluir Agente
- **Endpoint:** `DELETE /crm/organizations/{org_id}/agents/{agent_id}`
- **Permissão:** Admin+ da organização
- **Regras CRÍTICAS:**
  - **NÃO permitir excluir se for o último agente da org**
  - Se houver conversas usando este agente, transferir para o default
  - Retornar erro 400 se tentar excluir último agente

#### 1.5 Definir Agente Padrão
- **Endpoint:** `POST /crm/organizations/{org_id}/agents/{agent_id}/set-default`
- **Permissão:** Admin+ da organização
- **Efeito:** 
  - Marcar `is_default = true` para este agente
  - Desmarcar `is_default = false` para outros da mesma org
  - Novas conversas usarão este agente

### 2. Troca de Agente na Conversa

#### 2.1 Endpoint
- **PUT** `/crm/conversations/{phone}/agent`
- **Body:** `{ "agent_id": "uuid-do-agente" }`
- **Permissão:** Admin+ da organização dona da conversa

#### 2.2 Frontend (crm.html)
- **Local:** Header da conversa, ao lado do nome do contato
- **Componente:** Dropdown estilizado
- **Comportamento:**
  1. Carrega agentes da org da conversa
  2. Mostra agente atual com ícone
  3. Ao selecionar novo agente:
     - Chama endpoint PUT
     - Mostra toast "Agente alterado para [nome]"
     - Atualiza badge no header
     - Próxima mensagem usa novo agente

#### 2.3 Processamento (handlers/messages.py)
```python
# ANTES:
system_prompt = _load_prompt("atendimento")

# DEPOIS:
agent = await get_conversation_agent(phone)
if agent:
    system_prompt = agent["system_prompt"]
else:
    system_prompt = _load_prompt("atendimento")  # fallback
```

### 3. Organização BCOMM

#### 3.1 Criar Organização
- **Nome:** "Org BCOMM"
- **Descrição:** "Organização padrão BCOMM"
- **Dono:** Usuário master atual

#### 3.2 Agentes Padrão da BCOMM
Criar 3 agentes iniciais:

| Nome | Slug | Descrição |
|------|------|-----------|
| Atendimento | atendimento | Suporte geral e dúvidas |
| Agendamento | agendamento | Marcar reuniões e consultas |
| Financeiro | financeiro | Dúvidas sobre pagamentos |

**Obs:** O prompt de cada agente será carregado dos arquivos `.md` existentes em `prompts/`

#### 3.3 Associar Conversas
- Conversas sem `organization_id` → mover para Org BCOMM
- Endpoint: `POST /crm/organizations/bcomm/associate-conversations`
- Executar uma vez na migração

### 4. Status WhatsApp nas Configs da Org

#### 4.1 Página da Organização (organizations.html)
- **Seção "WhatsApp"** no card da organização
- **Status:** Badge verde (conectado) / vermelho (desconectado)
- **Telefone:** Número conectado (se houver)
- **Ações:**
  - Botão "Conectar" → mostra QR Code
  - Botão "Desconectar" → confirma e desconecta
  - Botão "Atualizar Status"

#### 4.2 Endpoints (já existentes)
- `GET /crm/organizations/{org_id}/whatsapp/status`
- `POST /crm/organizations/{org_id}/whatsapp/connect`
- `DELETE /crm/organizations/{org_id}/whatsapp/disconnect`
- `GET /crm/organizations/{org_id}/whatsapp/qr`

---

## 🔐 Controle de Acesso

### Regras de Permissão

| Ação | Master | Admin Geral | Admin Contas | Agent |
|------|--------|-------------|--------------|-------|
| Ver agentes da org | ✅ | ✅ | ✅ | ✅ |
| Criar agente | ✅ | ✅ | ✅ | ❌ |
| Editar agente | ✅ | ✅ | ✅ | ❌ |
| Excluir agente | ✅ | ✅ | ✅ | ❌ |
| Definir padrão | ✅ | ✅ | ✅ | ❌ |
| Trocar agente na conversa | ✅ | ✅ | ✅ | ❌ |

### Verificação no Backend

```python
async def require_admin(user: dict, org_id: str):
    """Verifica se usuário é admin da organização."""
    if user["role"] in ("master", "admin_geral"):
        return True  # Master/Admin geral acessa tudo
    
    if user["role"] == "admin_contas":
        # Verificar se tem acesso à organização
        has_access = await check_user_org_access(user["id"], org_id)
        return has_access
    
    return False  # Agent não pode gerenciar
```

---

## 📁 Arquivos Modificados

### Backend
| Arquivo | Mudança |
|---------|---------|
| `routes/crm_routes.py` | +5 endpoints (CRUD agents) |
| `handlers/messages.py` | Buscar agent_id da conversa |
| `services/hermes.py` | Receber prompt do agente |
| `migrations/003_agents.sql` | Tabela agents + alters |

### Frontend
| Arquivo | Mudança |
|---------|---------|
| `static/crm.html` | Dropdown de agentes no header |
| `static/organizations.html` | Seção WhatsApp + CRUD agentes |
| `static/config.html` | (já tem aba WhatsApp) |

---

## 🗺️ Fluxos

### Fluxo 1: Criar Agente
```
Admin acessa Organizations → Seleciona org → Clica "Novo Agente"
  → Preenche nome, slug, prompt
  → Salva
  → Agente aparece na lista
  → Disponível para seleção nas conversas
```

### Fluxo 2: Trocar Agente na Conversa
```
Operador abre conversa → Clica no dropdown de agente
  → Seleciona "Agendamento"
  → Toast: "Agente alterado para Agendamento"
  → Próxima mensagem do cliente → Usa prompt de agendamento
```

### Fluxo 3: Excluir Último Agente
```
Admin tenta excluir único agente da org
  → Botão "Excluir" desabilitado (tooltip: "Último agente não pode ser excluído")
  → Ou clica → Erro 400: "Não é possível excluir o último agente"
```

---

## ⚠️ Validações Important

1. **Último Agente:** NUNCA permitir excluir
2. **Agente Padrão:** Toda org deve ter pelo menos 1 agente default
3. **Conversa sem Agente:** Usar agente padrão da org
4. **Org sem WhatsApp:** Mostrar "Não conectado", permitir conectar
5. **Prompt Obrigatório:** Agente sem prompt não pode ser salvo

---

## 🚀 Ordem de Implementação

### Fase 1: Infraestrutura (Banco)
1. Criar tabela `bcomm_inbox.agents`
2. Adicionar coluna `agent_id` em conversations
3. Criar organización "Org BCOMM"
4. Criar 3 agentes padrão para BCOMM
5. Migrar conversas existentes

### Fase 2: Backend (API)
1. CRUD de agentes (5 endpoints)
2. Endpoint trocar agente na conversa
3. Middleware de permissão (admin check)
4. Atualizar handlers/messages.py

### Fase 3: Frontend (UI)
1. Página de agentes na organização
2. Dropdown de agentes no crm.html
3. Status WhatsApp na organização
4. Testes de permissão

### Fase 4: Testes
1. Criar org → Criar agente → Enviar msg → Verificar resposta
2. Trocar agente → Enviar msg → Verificar novo comportamento
3. Tentar excluir último agente → Verificar bloqueio
4. Usuário agent tentar criar agente → Verificar negação

---

## 📊 Estimativa

| Fase | Tempo |
|------|-------|
| Fase 1: Banco | 30min |
| Fase 2: Backend | 2h |
| Fase 3: Frontend | 2h |
| Fase 4: Testes | 30min |
| **Total** | **~5h** |

---

## ❓ Perguntas Adicionais

1. **Ordem dos agentes:** Deve ser alfabética ou por data de criação?
2. **Histórico:** Quando trocar agente, mostrar no histórico qual agente respondeu cada mensagem?
3. **Notificação:** Ao criar/editar agente, notificar outros admins da org?
4. **Versão do prompt:** Manter histórico de versões do prompt ou só a versão atual?
