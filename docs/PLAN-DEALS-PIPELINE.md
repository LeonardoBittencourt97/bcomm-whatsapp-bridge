# Plano: Vincular Deals a Pipelines

**Data:** 2026-09-02
**Status:** Planejamento

---

## 📊 Situação Atual

### Estrutura do Banco

```
┌─────────────────────┐      ┌─────────────────────┐
│      PIPELINES      │      │       STAGES        │
├─────────────────────┤      ├─────────────────────┤
│ id (PK)             │◄─────│ pipeline_id (FK)    │
│ name                │      │ id (PK)             │
│ organization_id     │      │ name                │
│ is_default          │      │ position            │
└─────────────────────┘      │ color               │
                             │ organization_id     │
                             └─────────────────────┘
                                      │
                                      │ (não vinculado)
                                      ▼
                             ┌─────────────────────┐
                             │       DEALS         │
                             ├─────────────────────┤
                             │ id (PK)             │
                             │ title               │
                             │ stage (texto!)      │  ← PROBLEMA
                             │ value               │
                             │ organization_id     │
                             │ pipeline_id (FALTA) │  ← CRIAR
                             └─────────────────────┘
```

### Problema
- Deals têm `stage` como **texto** ("lead", "qualified")
- Deals **NÃO** têm `pipeline_id` para vincular à pipeline
- Deals estão todos em "lead" sem vinculação real

---

## 🎯 Objetivo

```
┌─────────────────────┐
│   ORGANIZATION      │
│   (Org BCOMM)      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     PIPELINE        │
│  (Pipeline Principal)│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│      STAGES         │
│ Lead→Qualif→Proposta│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│       DEALS         │
│  (vinculados)       │
└─────────────────────┘
```

---

## 📋 Plano de Implementação

### Fase 1: Banco de Dados

#### 1.1 Adicionar coluna `pipeline_id` em deals
```sql
ALTER TABLE bcomm_inbox.deals 
ADD COLUMN IF NOT EXISTS pipeline_id UUID 
REFERENCES bcomm_inbox.pipelines(id);
```

#### 1.2 Criar índice
```sql
CREATE INDEX IF NOT EXISTS idx_deals_pipeline 
ON bcomm_inbox.deals(pipeline_id);
```

#### 1.3 Migrar deals existentes
```sql
-- Vincular todos deals sem pipeline_id à "Pipeline Principal" da Org BCOMM
UPDATE bcomm_inbox.deals 
SET pipeline_id = (
    SELECT id FROM bcomm_inbox.pipelines 
    WHERE name = 'Pipeline Principal' 
    AND organization_id = '00000000-0000-0000-0000-000000000001'::uuid
    LIMIT 1
)
WHERE pipeline_id IS NULL;
```

#### 1.4 Atualizar campo `stage` para UUID do stage
```sql
-- Converter "lead" → UUID do stage "Lead" na Pipeline Principal
UPDATE bcomm_inbox.deals d
SET stage = (
    SELECT s.id::text FROM bcomm_inbox.stages s
    WHERE s.pipeline_id = d.pipeline_id
    AND LOWER(s.name) = LOWER(d.stage)
    LIMIT 1
)
WHERE d.pipeline_id IS NOT NULL;
```

---

### Fase 2: Backend

#### 2.1 Atualizar modelo DealCreate
```python
class DealCreate(BaseModel):
    title: str
    pipeline_id: str  # OBRIGATÓRIO
    stage_id: str     # Opcional (senão, usar primeiro stage)
    # ... outros campos
```

#### 2.2 Atualizar endpoint POST /pipelines/deals
- Receber `pipeline_id` no body
- Validar se pipeline existe e pertence à org do usuário
- Se `stage_id` não informado, buscar primeiro stage da pipeline

#### 2.3 Atualizar endpoint GET /pipelines/deals
- Já suporta filtro por `pipeline_id` (feito)
- Adicionar retorno com `stage_name` e `pipeline_name`

#### 2.4 Atualizar endpoint PUT /pipelines/deals/{id}
- Permitir mover deal para outro stage
- Permitir mover deal para outra pipeline

---

### Fase 3: Frontend

#### 3.1 Modal de Criar Deal
- **Adicionar select de Pipeline** (obrigatório)
- **Adicionar select de Estágio** (filtrado pela pipeline selecionada)
- Ao mudar pipeline, atualizar lista de estágios

#### 3.2 Kanban View
- Cards mostram: título, valor, telefone, contato
- Mover card = atualizar `stage_id` do deal
- Filtrar por pipeline selecionada no dropdown

#### 3.3 Dashboard/Stats
- Filtrar stats pela pipeline selecionada
- Mostrar valor total por estágio

---

## 🔧 Arquivos Modificados

### Backend
| Arquivo | Mudança |
|---------|---------|
| `crm_routes.py` | Atualizar DealCreate, GET/POST/PUT deals |
| `routes/routes_pipelines.py` | Adicionar validação de pipeline_id |
| `migrations/004_deals_pipeline.sql` | Adicionar coluna e migrar dados |

### Frontend
| Arquivo | Mudança |
|---------|---------|
| `static/pipelines.html` | Select de pipeline/estágio no modal de deal |

---

## ⚠️ Validações

1. **Pipeline obrigatória:** Deal sem pipeline_id não pode ser criado
2. **Estágio válido:** stage_id deve pertencer à pipeline selecionada
3. **Org correta:** Pipeline deve pertencer à mesma org do deal
4. **Migração:** Deals existentes vão para Pipeline Principal

---

## 📊 Estimativa

| Fase | Tempo |
|------|-------|
| Fase 1: Banco | 20min |
| Fase 2: Backend | 45min |
| Fase 3: Frontend | 45min |
| Testes | 20min |
| **Total** | **~2h** |

---

## ✅ Critérios de Sucesso

- [ ] Deals criados têm pipeline_id
- [ ] Kanban mostra deals da pipeline selecionada
- [ ] Mover card atualiza stage_id
- [ ] Select de pipeline funciona no modal de criar deal
- [ ] Stats filtrados por pipeline
- [ ] Migração preserva dados existentes
