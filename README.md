# 🤖 BComm WhatsApp Bridge

Bridge server FastAPI para conectar a **Evolution API** ao **Hermes Agent** — permitindo IA de atendimento, agendamento, CRM e financeiro via WhatsApp.

## 📋 Funcionalidades

- **Receber webhooks** da Evolution API
- **Processar mensagens** com Hermes Agent
- **Responder** via Evolution API
- **Suporte a múltiplos profiles** Hermes
- **Gerenciamento de sessão** por contato
- **Rate limiting** e retry automático

## 🏗️ Arquitetura

```
WhatsApp → Evolution API → BComm Bridge → Hermes Agent → Resposta
```

## 🛠️ Tecnologias

- **Python 3.11+**
- **FastAPI** — Framework web async
- **Evolution API** — WhatsApp API
- **Hermes Agent** — IA de processamento

## 🚀 Setup

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite o .env com suas credenciais
```

### 3. Executar o servidor

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## ⚙️ Variáveis de Ambiente

| Variável | Descrição | Obrigatório |
|----------|-----------|-------------|
| `EVOLUTION_API_URL` | URL da Evolution API | ✅ |
| `EVOLUTION_API_KEY` | Chave da API da Evolution | ✅ |
| `HERMES_API_URL` | URL do Hermes Agent | ✅ |
| `HERMES_API_KEY` | Chave do Hermes Agent | ✅ |
| `HERMES_DEFAULT_PROFILE` | Profile padrão do Hermes | ❌ |
| `WEBHOOK_SECRET` | Segredo para validar webhooks | ❌ |
| `PORT` | Porta do servidor (padrão: 8000) | ❌ |

## 📁 Estrutura do Projeto

```
bcomm-whatsapp-bridge/
├── main.py              # App FastAPI principal
├── config.py            # Configurações
├── webhook.py           # Handler de webhooks
├── hermes_client.py     # Cliente Hermes Agent
├── evolution_client.py  # Cliente Evolution API
├── requirements.txt     # Dependências Python
├── .env.example         # Template de configuração
├── .gitignore           # Arquivos ignorados
└── README.md            # Esta documentação
```

## 📝 Licença

MIT
