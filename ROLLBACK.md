# Rollback para Estado Funcional

## Estado atual: v1.0-working

### Commit: $(git rev-parse HEAD)
### Data: $(date)

## Para fazer rollback:

### 1. Deploy via Coolify (mais fácil):
1. Acesse Coolify → bcomm-whatsapp-bridge
2. Em "Deploy", selecione a tag `v1.0-working`
3. Clique em Deploy

### 2. Via comando (mais rápido):
```bash
cd /opt/data/bcomm-whatsapp-bridge
git checkout v1.0-working .
git add -A
git commit -m "rollback: voltando para v1.0-working"
git push origin master
```

### 3. Restaurar SOUL.md:
```bash
cp /home/hermes/.hermes/profiles/bcomm-atendente/SOUL.md.backup \
   /home/hermes/.hermes/profiles/bcomm-atendente/SOUL.md
```

### 4. Restaurar docker-compose.yml:
```bash
cp /opt/data/bcomm-whatsapp-bridge/docker-compose.yml.backup \
   /opt/data/bcomm-whatsapp-bridge/docker-compose.yml
```

## O que está funcionando nesta versão:
- ✅ Mensagens de texto
- ✅ Áudio (descriptografia + transcrição)
- ✅ Hermes com memória (sessões)
- ✅ Google Calendar (agendamento)
- ✅ Indicador "digitando..."
- ✅ Delay humanizado
- ✅ Batch de mensagens (10s)
- ✅ Deduplicação de webhooks
- ✅ Tom profissional (SOUL.md)

## Para verificar se está funcionando:
```bash
curl https://wa-bot.agent-bcomm.space/health
```
