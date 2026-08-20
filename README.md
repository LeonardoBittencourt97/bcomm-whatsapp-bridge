# bcomm-whatsapp-bridge

Bridge entre Evolution API (WhatsApp) e Hermes/LLM para atendimento inteligente.

## Arquitetura

```
WhatsApp → Evolution API → Bridge (FastAPI) → Hermes/LLM → Resposta
                              ↓
                    STT (faster-whisper) → Transcrição
```

## Funcionalidades

- ✅ Atendimento via WhatsApp
- ✅ Transcrição de áudio (faster-whisper)
- ✅ Descriptografia de áudio WhatsApp (HKDF-SHA256)
- ✅ Hermes Agent com memória de conversação
- ✅ Google Calendar para agendamento
- ✅ Multi-tenant (múltiplos clientes)

## Setup

### 1. Clone o repositório
```bash
git clone https://github.com/LeonardoBittencourt97/bcomm-whatsapp-bridge.git
cd bcomm-whatsapp-bridge
```

### 2. Configure as variáveis de ambiente
```bash
cp .env.example .env
# Edite .env com suas credenciais
```

### 3. Deploy no Coolify
- Crie um novo serviço Docker Compose
- Adicione as variáveis de ambiente
- Configure os domínios

## Multi-Tenant

Para adicionar um novo cliente:

1. **Edite `config/clients.yaml`:**
```yaml
clients:
  NOVO_CLIENTE:
    name: "Nome do Cliente"
    hermes_profile: "perfil-hermes"
    prompt_file: "prompts/novo_cliente/atendimento.md"
    timezone: "America/Sao_Paulo"
    business_hours:
      start: "09:00"
      end: "18:00"
      days: [mon, tue, wed, thu, fri]
    meeting_duration: 30
    welcome_message: "Olá! Bem-vindo à empresa."
```

2. **Crie o diretório de prompts:**
```bash
mkdir -p prompts/novo_cliente
# Crie atendimento.md com o prompt do cliente
```

3. **Crie a instância Evolution API** para o número WhatsApp do cliente

4. **Deploy** — o bridge identifica o cliente pela instância

## Endpoints

- `GET /health` — Health check
- `GET /clients` — Lista clientes configurados
- `POST /webhook/evolution` — Webhook da Evolution API
- `POST /send` — Enviar mensagem manual

## Desenvolvimento

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar localmente
python main.py

# Testes
pytest tests/
```

## Licença

MIT
