# Multi-Tenant Bridge Design

## Overview

Transform the single-tenant bridge into a multi-tenant system serving 5-20 clients. A single bridge instance routes messages to the correct client configuration, Hermes profile, and Evolution API instance.

## Goals

1. Add new clients without code changes or redeployment
2. Each client has isolated config, prompts, and calendar
3. Web dashboard for client management
4. Maintain backward compatibility with existing BCOMM client

## Architecture

```
Evolution API (multi-instance) → Bridge (single) → Hermes (multi-profile)
                                      ↓
                              /data/clients/
                              ├── bcomm/
                              │   ├── config.yaml
                              │   └── credentials/
                              ├── client_b/
                              │   ├── config.yaml
                              │   └── credentials/
                              └── ...
```

## Components

### 1. Config Manager
- Reads client configs from `/data/clients/{name}/config.yaml`
- Hot-reload without deployment
- Validates config on load

### 2. Router
- Maps `instanceName` → client config
- Routes to correct Hermes profile
- Handles unknown instances gracefully

### 3. Dashboard (Web UI)
- CRUD for clients
- Real-time logs
- Session management (pause/resume)

### 4. Hermes Multi-Profile
- Creates profiles per client
- Manages SOUL.md per client
- Isolates sessions per client

## Client Config Schema

```yaml
name: "Client Name"
instance: "EVOLUTION_INSTANCE_NAME"
hermes_profile: "client-profile-name"
timezone: "America/Sao_Paulo"
business_hours:
  start: "09:00"
  end: "18:00"
  days: [mon, tue, wed, thu, fri]
meeting_duration: 30
welcome_message: "Olá! Sou a Ana..."
google_calendar:
  enabled: true
  credentials_path: "/data/clients/client/credentials/"
```

## File Structure

```
/opt/data/bcomm-whatsapp-bridge/
├── config/
│   ├── __init__.py
│   ├── settings.py          # Global settings (env vars)
│   ├── client_loader.py     # Loads client configs
│   └── router.py            # Routes messages to clients
├── handlers/
│   ├── webhook.py           # Receives webhooks
│   └── messages.py          # Processes messages
├── services/
│   ├── evolution.py         # Evolution API client
│   ├── hermes.py            # Hermes CLI client
│   ├── llm.py               # LLM client
│   └── stt.py               # STT client
├── dashboard/
│   ├── __init__.py
│   ├── app.py               # Dashboard FastAPI app
│   ├── static/              # CSS/JS
│   └── templates/           # HTML templates
├── models/
│   └── schemas.py           # Pydantic models
├── data/
│   └── hermes_sessions.json # Session persistence
└── main.py                  # Main FastAPI app
```

## Deployment

- Single Docker container via Coolify
- Volume mount: `/data/clients:/data/clients`
- Volume mount: `/app/data:/app/data` (sessions)
- Traefik labels for routing

## Migration Plan

1. Create `/data/clients/bcomm/` with current config
2. Update bridge to read from client config
3. Test with existing BCOMM client
4. Add new clients via dashboard
5. Decommission old config

## Risks

1. **Session cache** — Old sessions may use stale config
   - Mitigation: Clear sessions on config change

2. **Evolution API instances** — Need to create instances per client
   - Mitigation: Document process, add to dashboard

3. **Hermes profiles** — Need to create profiles per client
   - Mitigation: Auto-create on first message

## Success Criteria

1. Add new client in < 5 minutes via dashboard
2. No deployment needed for new clients
3. Existing BCOMM client works unchanged
4. Dashboard shows real-time status
