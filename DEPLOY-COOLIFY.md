# Deploy bcomm-whatsapp-bridge no Coolify

## Pré-requisitos

1. **DNS configurado**: Criar registro A para `wa-bot.agent-bcomm.space` apontando para o IP da VPS (`agent-bcomm.space`)
2. **Coolify acessível**: https://coolify.agent-bcomm.space
3. **Repositório GitHub**: https://github.com/LeonardoBittencourt97/bcomm-whatsapp-bridge

---

## Opção A: Deploy Automatizado (API)

```bash
# 1. Gerar token da API no Coolify:
#    → https://coolify.agent-bcomm.space → Settings → API Tokens → Generate

# 2. Executar o script:
COOLIFY_TOKEN="seu-token-aqui" ./deploy-coolify.sh
```

---

## Opção B: Deploy Manual (Web UI)

### Passo 1: Criar Domínio DNS

Criar registro DNS:
```
Tipo: A
Nome: wa-bot
Valor: <IP da VPS agent-bcomm.space>
TTL: 300
```

### Passo 2: Acessar Coolify

1. Acesse: https://coolify.agent-bcomm.space
2. Login com suas credenciais

### Passo 3: Criar Projeto

1. Menu lateral → **Projects**
2. Clique em **+ New**
3. Nome: `bcomm`
4. Descrição: `BCOMM communication platform services`
5. Clique em **Create**

### Passo 4: Criar Aplicação

1. Dentro do projeto `bcomm`, clique em **+ New**
2. Selecione: **Docker Compose** (ou "Application" se disponível)
3. Preencha:
   - **Name**: `bcomm-whatsapp-bridge`
   - **Git Repository**: `https://github.com/LeonardoBittencourt97/bcomm-whatsapp-bridge`
   - **Git Branch**: `main`

### Passo 5: Configurar Variáveis de Ambiente

Na aba **Environment Variables** ou **Env**, adicione:

| Variável | Valor |
|----------|-------|
| `EVOLUTION_API_URL` | `https://evolution-api.agent-bcomm.space` |
| `EVOLUTION_API_KEY` | `1F0C0840D74A-4EFF-B413-AF2DE616B30E` |
| `EVOLUTION_INSTANCE` | `BCOMM` |
| `HERMES_PROFILE` | `bcomm-atendente` |
| `OPENCODE_API_KEY` | *(preencher com chave real)* |
| `OPENCODE_API_URL` | `https://opencode.ai/zen/go/v1` |
| `OPENCODE_MODEL` | `mimo-v2.5` |
| `PORT` | `8000` |
| `DEBUG` | `false` |
| `LOG_LEVEL` | `INFO` |
| `RATE_LIMIT_PER_MINUTE` | `20` |

### Passo 6: Configurar Domínio

1. Na aba **Networking** ou **Domains**:
2. Adicione: `https://wa-bot.agent-bcomm.space`
3. Port: `8000`
4. O Coolify configurará automaticamente:
   - SSL/TLS (Let's Encrypt)
   - Reverse proxy (Caddy/Traefik)

### Passo 7: Build & Deploy

1. Clique em **Deploy** ou **Start**
2. Aguarde o build (1-3 minutos)
3. Verifique os logs em **Logs**

---

## Verificação Pós-Deploy

```bash
# Testar endpoint de saúde
curl -I https://wa-bot.agent-bcomm.space/health

# Testar endpoint principal
curl https://wa-bot.agent-bcomm.space/
```

---

## Variáveis de Ambiente (Referência)

| Variável | Descrição | Valor Padrão |
|----------|-----------|--------------|
| `EVOLUTION_API_URL` | URL da Evolution API | `http://localhost:8080` |
| `EVOLUTION_API_KEY` | Chave da API Evolution | - |
| `EVOLUTION_INSTANCE` | Nome da instância | `bcomm-main` |
| `HERMES_PROFILE` | Perfil do Hermes | `default` |
| `OPENCODE_API_KEY` | Chave API OpenCode | - |
| `OPENCODE_API_URL` | URL do OpenCode | `http://localhost:11434/v1` |
| `OPENCODE_MODEL` | Modelo LLM | `mimo-v2.5` |
| `PORT` | Porta do servidor | `8000` |
| `DEBUG` | Modo debug | `false` |
| `LOG_LEVEL` | Nível de log | `INFO` |
| `RATE_LIMIT_PER_MINUTE` | Rate limit | `20` |

---

## Troubleshooting

### Build falhou
- Verifique se o repositório está público ou se o Coolify tem acesso ao GitHub
- Verifique os logs do build

### SSL não funciona
- Aguarde 2-3 minutos para o Let's Encrypt provisionar o certificado
- Verifique se o DNS está apontando corretamente

### Container não inicia
- Verifique as variáveis de ambiente
- Verifique os logs em Coolify → Logs

### 502 Bad Gateway
- O container pode ainda estar buildando
- Verifique se a porta 8000 está exposta corretamente
- Verifique se o healthcheck passa: `curl http://localhost:8000/health`
