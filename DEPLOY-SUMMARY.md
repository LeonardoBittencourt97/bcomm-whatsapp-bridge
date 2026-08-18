# Deploy bcomm-whatsapp-bridge no Coolify - Resumo

## Status Atual

| Item | Status |
|------|--------|
| Repositório GitHub | ✅ https://github.com/LeonardoBittencourt97/bcomm-whatsapp-bridge |
| Coolify acessível | ✅ https://coolify.agent-bcomm.space (HTTP 302) |
| Dockerfile | ✅ Presente no repo |
| docker-compose.yml | ✅ Presente no repo |
| .env.example | ✅ Presente no repo |
| .env criado | ✅ Com variáveis de produção |
| Script de deploy | ✅ deploy-coolify.sh |
| Documentação | ✅ DEPLOY-COOLIFY.md |
| DNS wa-bot.agent-bcomm.space | ❌ **NÃO CONFIGURADO** |
| Token API Coolify | ❌ **NÃO DISPONÍVEL** |

---

## Ações Necessárias

### 1. Criar registro DNS

Criar registro A:
```
Tipo:   A
Nome:   wa-bot
Valor:  187.77.241.36  (IP do Coolify)
TTL:    300
```

### 2. Gerar token da API Coolify

1. Acesse: https://coolify.agent-bcomm.space
2. Login → Settings → API Tokens
3. Clique em "Generate New Token"
4. Copie o token

### 3. Executar deploy

**Opção A - Automatizado (recomendado):**
```bash
cd /opt/data/bcomm-whatsapp-bridge
COOLIFY_TOKEN="seu-token-aqui" ./deploy-coolify.sh
```

**Opção B - Manual:**
1. Acesse https://coolify.agent-bcomm.space
2. Projects → New → Nome: "bcomm"
3. Dentro do projeto → New → Docker Compose
4. Git Repository: https://github.com/LeonardoBittencourt97/bcomm-whatsapp-bridge
5. Branch: master
6. Configure as variáveis de ambiente (ver DEPLOY-COOLIFY.md)
7. Domain: https://wa-bot.agent-bcomm.space
8. Port: 8000
9. Deploy

### 4. Configurar OPENCODE_API_KEY

A variável `OPENCODE_API_KEY` está vazia. Obter em:
- https://opencode.ai → Settings → API Keys
- Ou usar chave existente do Hermes

---

## Arquivos Criados/Modificados

- `/opt/data/bcomm-whatsapp-bridge/.env` - Variáveis de ambiente
- `/opt/data/bcomm-whatsapp-bridge/deploy-coolify.sh` - Script de deploy automático
- `/opt/data/bcomm-whatsapp-bridge/DEPLOY-COOLIFY.md` - Guia completo de deploy

---

## URLs de Referência

- Coolify: https://coolify.agent-bcomm.space
- App (após deploy): https://wa-bot.agent-bcomm.space
- Health check: https://wa-bot.agent-bcomm.space/health
- Evolution API: https://evolution-api.agent-bcomm.space
