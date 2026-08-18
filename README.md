# bcomm-whatsapp-bridge

Bridge server entre Evolution API (WhatsApp) e Hermes/LLM para automação de atendimento.

## Estrutura

```
bcomm-whatsapp-bridge/
├── main.py              # FastAPI app principal
├── config.py            # Configurações (env vars)
├── services/            # Clientes externos
│   ├── evolution.py     # Evolution API
│   ├── hermes.py        # Hermes CLI
│   └── llm.py           # LLM (OpenAI-compatible)
├── handlers/            # Lógica de negócio
│   ├── webhook.py       # Extração de eventos
│   └── messages.py      # Processamento + envio
├── models/              # Schemas Pydantic
├── prompts/             # Prompts por domínio
├── tests/               # Testes
├── Dockerfile
└── docker-compose.yml
```

## Setup

```bash
cp .env.example .env
# Edite .env com suas credenciais

# Local
pip install -r requirements.txt
python main.py

# Docker
docker compose up --build
```

## Endpoints

| Método | Path              | Descrição                    |
|--------|-------------------|------------------------------|
| GET    | `/health`         | Health check                 |
| POST   | `/webhook/evolution` | Recebe webhooks Evolution API |
| POST   | `/send`           | Enviar mensagem manual       |
| GET    | `/docs`           | Swagger UI                   |

## Fluxo

1. Evolution API envia webhook → `/webhook/evolution`
2. Handler extrai mensagem do payload
3. Processa via Hermes CLI ou LLM direto
4. Envia resposta via Evolution API

## Variáveis de Ambiente

Ver `.env.example` para referência completa.
