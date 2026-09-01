# Design: CRM Features — 6 Melhorias para o Operador

**Data:** 2026-09-01
**Status:** Draft
**Abordagem:** Sequencial (Feature 1 → 6)

---

## Contexto

O CRM do BCOMM (bcomm-whatsapp-bridge) funciona mas falta informações ao operador:
- Não sabe se o agente tá processando ou travado
- Não pode transferir pra humano sem pedir admin
- Não pode reconectar WhatsApp sozinho
- Não pode configurar rate limit/typing sem SSH
- Não tem resumo rápido de conversas
- Dashboard mostra stats básicas sem profundidade

## Features

### 1. Métricas Detalhadas no Dashboard

**O que:** Adicionar 3 cards ao dashboard: Mensagens Hoje, Tempo Médio de Resposta, Taxa de Resolução.

**Backend:**
- Endpoint existente: `GET /crm/stats` (crm_routes.py)
- Adicionar campos: `messages_today`, `avg_response_time`, `resolution_rate`
- `messages_today`: contar mensagens com `created_at` hoje
- `avg_response_time`: diferença entre primeira msg do usuário e primeira resposta do agente
- `resolution_rate`: % de conversas com status "closed" / total

**Frontend (dashboard.html):**
- Adicionar 3 cards na grid de stats
- Polling a cada 30s (já existe `updateStatus()`)

**Arquivos:**
- `crm_routes.py` → endpoint `/crm/stats`
- `static/dashboard.html` → cards + JS

**Complexidade:** Baixa (~30min)

---

### 2. Config do Agente na UI

**O que:** Formulário na página `/config` para configurar rate limit, typing delay e batch.

**Backend:**
- Endpoints existentes: `GET/POST /admin/config` (main.py)
- Settings: `rate_limit_per_minute`, `human_delay_enabled`, `human_delay_min`, `human_delay_max`, `batch_wait_seconds`, `batch_max_wait`

**Frontend (config.html):**
- Adicionar seção "Configurações do Agente" com formulário
- Campos: Rate Limit (input number), Typing Delay Min/Max (inputs), Batch Wait/Max (inputs), Toggle human delay
- Botão Salvar que faz POST para `/admin/config`

**Arquivos:**
- `static/config.html` → formulário + JS
- `main.py` → endpoints já existem

**Complexidade:** Baixa (~45min)

---

### 3. Transferir pra Humano na UI

**O que:** Botão "Transferir" na conversa que pausa o agente e envia mensagem de transferência.

**Backend:**
- Endpoint existente: `POST /admin/transfer-to-human` (main.py)
- Recebe: `phone`, `reason`, `client`
- Pausa o contato e envia mensagem automática

**Frontend (crm.html):**
- Botão "🧑 Transferir" no header da conversa aberta
- Modal pedindo motivo (opcional)
- Chama `/admin/transfer-to-human`
- Feedback visual (toast)

**Arquivos:**
- `static/crm.html` → botão + modal + JS
- `main.py` → endpoint já existe

**Complexidade:** Baixa (~20min)

---

### 4. Resumo de Conversa na UI

**O que:** Resumo automático da conversa visível ao operador.

**Backend:**
- Endpoint existente: `GET /crm/conversations/{phone}/summary` (crm_routes.py)
- Retorna: total_messages, user_messages, agent_messages, manual_messages, unanswered, duration, status

**Frontend (crm.html):**
- Seção "Resumo" no painel lateral da conversa (abaixo das mensagens)
- Mostra: total msgs, msgs do usuário, msgs do agente, não respondidas, duração
- Atualiza ao trocar de conversa

**Arquivos:**
- `static/crm.html` → seção de resumo + JS
- `crm_routes.py` → endpoint já existe

**Complexidade:** Baixa (~30min)

---

### 5. Status de Processamento na UI

**O que:** Indicador visual de quando o agente está processando.

**Backend:**
- Endpoint existente: `GET /crm/status/{phone}` (crm_routes.py)
- Retorna: `{status: "processing", elapsed_seconds: 5.2}` ou `{status: "idle"}`

**Frontend (crm.html):**
- **Sidebar:** Dot animado (pulsante) ao lado do contato quando processando
- **Header:** Badge "Processando..." com tempo decorrido
- Polling a cada 3 segundos (só quando conversa aberta)

**Arquivos:**
- `static/crm.html` → indicadores + JS polling

**Complexidade:** Média (~40min)

---

### 6. WhatsApp QR/Connect na UI

**O que:** Reconectar instância WhatsApp direto da UI.

**Backend:**
- Endpoints existentes em `routes/routes_whatsapp.py`:
  - `POST /crm/organizations/{org_id}/whatsapp/connect` → retorna QR code
  - `GET /crm/organizations/{org_id}/whatsapp/status` → status da conexão
  - `DELETE /crm/organizations/{org_id}/whatsapp/disconnect` → desconecta

**Frontend (config.html):**
- Nova aba "WhatsApp" na seção de configurações
- Status atual da conexão (conectado/desconectado)
- Botão "Conectar" que mostra QR code (imagem)
- Botão "Desconectar"
- Auto-refresh do QR code (expira em ~30s)

**Arquivos:**
- `static/config.html` → aba WhatsApp + QR code + JS
- `routes/routes_whatsapp.py` → endpoints já existem

**Complexidade:** Média (~60min)

---

## Ordem de Implementação

| # | Feature | Dependências | Estimativa |
|---|---------|--------------|------------|
| 1 | Métricas detalhadas | Nenhuma | 30min |
| 2 | Config do agente | Nenhuma | 45min |
| 3 | Transferir pra humano | Nenhuma | 20min |
| 4 | Resumo de conversa | Nenhuma | 30min |
| 5 | Status de processamento | Nenhuma | 40min |
| 6 | WhatsApp QR/Connect | Nenhuma | 60min |
| **Total** | | | **~4h** |

## Padrões a Seguir

- **CSS:** Usar variáveis CSS existentes (`--accent`, `--card`, `--border`)
- **JS:** Seguir padrão `async function api(url, method, body)` existente
- **Toasts:** Usar `showToast(msg, type)` existente
- **Modais:** Usar `showModal(html)` / `hideModal()` existentes
- **Polling:** Usar `setInterval` com cleanup adequado
- **Endpoints:** Seguir padrão REST existente (`/crm/...`)

## Testing

Cada feature será testada:
1. Syntax check (Python: `py_compile`, HTML: manual)
2. Deploy via Coolify
3. Verificação visual no browser
4. Teste de API (curl)
