# Plano: Gestão de Contatos com Origem

**Data:** 2026-09-02
**Status:** Planejamento

---

## 📊 Situação Atual

### Estrutura Existente

```
┌─────────────────────────┐
│     CONTACTS            │
├─────────────────────────┤
│ id (PK)                 │
│ name                    │
│ phone                   │
│ email                   │
│ organization_id (FK)    │
│ owner_id (FK)           │
│ lifecycle_stage         │
│ notes                   │
│ tags                    │
│ custom_fields           │
│ created_at              │
│ updated_at              │
└─────────────────────────┘
         │
         │ (sem vinculação)
         ▼
┌─────────────────────────┐
│       DEALS             │
├─────────────────────────┤
│ id (PK)                 │
│ contact_id (FALTA)      │  ← Precisa adicionar
│ phone                   │
│ contact_name            │
│ ...                     │
└─────────────────────────┘

┌─────────────────────────┐
│  WHATSAPP_NUMBERS       │
├─────────────────────────┤
│ id (PK)                 │
│ phone_number            │
│ evolution_instance      │
│ organization_id (FK)    │
│ created_at              │
└─────────────────────────┘
         │
         │ (sem vinculação com contacts)
         ▼
         ❌
```

### Problemas
1. **Sem origem** - Não saber de qual WhatsApp o contato veio
2. **Sem vinculação** - Deals não têm `contact_id`
3. **Duplicatas** - Mesmo contato pode aparecer de múltiplas fontes
4. **Sem sync** - Contatos do WhatsApp não são puxados automaticamente

---

## 🎯 Objetivo

```
┌─────────────────────────┐
│  WHATSAPP_NUMBERS       │
│  (números conectados)   │
└──────────┬──────────────┘
           │ sync
           ▼
┌─────────────────────────┐
│       CONTACTS          │
│  (com source_id)        │
└──────────┬──────────────┘
           │ vinculado
           ▼
┌─────────────────────────┐
│       DEALS             │
│  (com contact_id)       │
└─────────────────────────┘
```

---

## 📋 Plano de Implementação

### Fase 1: Banco de Dados

#### 1.1 Adicionar coluna `source_id` em contacts
```sql
ALTER TABLE bcomm_inbox.contacts 
ADD COLUMN IF NOT EXISTS source_id UUID 
REFERENCES bcomm_inbox.whatsapp_numbers(id);

ALTER TABLE bcomm_inbox.contacts 
ADD COLUMN IF NOT EXISTS source_type VARCHAR(50) DEFAULT 'manual';
-- Valores: 'manual', 'whatsapp', 'import', 'api'
```

#### 1.2 Adicionar coluna `contact_id` em deals
```sql
ALTER TABLE bcomm_inbox.deals 
ADD COLUMN IF NOT EXISTS contact_id UUID 
REFERENCES bcomm_inbox.contacts(id);
```

#### 1.3 Criar índices
```sql
CREATE INDEX IF NOT EXISTS idx_contacts_source 
ON bcomm_inbox.contacts(source_id);

CREATE INDEX IF NOT EXISTS idx_contacts_phone 
ON bcomm_inbox.contacts(phone);

CREATE INDEX IF NOT EXISTS idx_deals_contact 
ON bcomm_inbox.deals(contact_id);
```

#### 1.4 Função de upsert (evitar duplicatas)
```sql
-- Função para inserir ou atualizar contato por phone
CREATE OR REPLACE FUNCTION upsert_contact_by_phone(
    p_phone TEXT,
    p_name TEXT,
    p_source_id UUID,
    p_source_type TEXT DEFAULT 'whatsapp'
) RETURNS UUID AS $$
DECLARE
    v_contact_id UUID;
BEGIN
    -- Buscar contato existente pelo phone
    SELECT id INTO v_contact_id 
    FROM bcomm_inbox.contacts 
    WHERE phone = p_phone;
    
    IF v_contact_id IS NOT NULL THEN
        -- Atualizar nome se vazio
        UPDATE bcomm_inbox.contacts 
        SET name = COALESCE(NULLIF(p_name, ''), name),
            updated_at = NOW()
        WHERE id = v_contact_id;
        RETURN v_contact_id;
    ELSE
        -- Criar novo contato
        INSERT INTO bcomm_inbox.contacts (phone, name, source_id, source_type, created_at, updated_at)
        VALUES (p_phone, p_name, p_source_id, p_source_type, NOW(), NOW())
        RETURNING id INTO v_contact_id;
        RETURN v_contact_id;
    END IF;
END;
$$ LANGUAGE plpgsql;
```

---

### Fase 2: Backend - Sync de Contatos

#### 2.1 Endpoint para sync de contatos
```
POST /crm/whatsapp/{instance}/sync-contacts
```

**Lógica:**
1. Buscar instância WhatsApp no banco
2. Chamar Evolution API para obter contatos
3. Para cada contato:
   - Verificar se já existe pelo phone
   - Se existe: atualizar nome se vazio
   - Se não existe: criar com source_id
4. Retornar estatísticas (novos, atualizados, duplicatas)

#### 2.2 Endpoint para listar contatos com origem
```
GET /crm/contacts?source_id=xxx&organization_id=yyy
```

**Retorna:**
```json
{
  "contacts": [
    {
      "id": "uuid",
      "name": "João Silva",
      "phone": "+554199999999",
      "source_type": "whatsapp",
      "source_name": "BCOMM (554199999999)",
      "organization_id": "uuid",
      "lifecycle_stage": "lead",
      "deals_count": 2,
      "last_contact": "2026-09-01T10:00:00Z"
    }
  ]
}
```

#### 2.3 Atualizar endpoint de deals
- Retornar `contact_name` do contato vinculado
- Permitir vincular/desvincular contato ao deal

---

### Fase 3: Frontend - Página de Contatos

#### 3.1 Filtros na página de contatos
- **Por Origem:** Select com WhatsApp numbers conectados
- **Por Organização:** Filtro existente
- **Por Estágio:** Lead, Qualified, etc.
- **Busca:** Nome ou telefone

#### 3.2 Tabela de contatos
| Coluna | Descrição |
|--------|-----------|
| Nome | Nome do contato |
| Telefone | Número com DDD |
| Origem | De qual WhatsApp veio |
| Organização | Org vinculada |
| Estágio | Lifecycle stage |
| Negócios | Quantidade de deals |
| Último Contato | Data da última interação |
| Ações | Editar, Ver deals |

#### 3.3 Modal de criar/editar contato
- Nome
- Telefone (com validação)
- Email
- Origem (select com WhatsApp numbers)
- Organização
- Estágio
- Tags
- Notas

---

### Fase 4: Vincular Contatos a Deals

#### 4.1 Atualizar modal de criar/editar deal
- **Adicionar select de Contato** (busca por nome/telefone)
- Ao selecionar contato:
  - Preencher telefone automaticamente
  - Preencher nome do contato
  - Salvar `contact_id` no deal

#### 4.2 Atualizar kanban/lista
- Mostrar nome do contato vinculado
- Link para ver detalhes do contato

---

### Fase 5: Criar Contatos de Teste

#### 5.1 Contatos para Org BCOMM
```sql
-- Contatos de exemplo
INSERT INTO bcomm_inbox.contacts (name, phone, email, organization_id, source_type, lifecycle_stage)
VALUES 
('Ana Souza', '+5541999990001', 'ana@teste.com', '00000000-0000-0000-0000-000000000001', 'manual', 'lead'),
('Carlos Lima', '+5541999990002', 'carlos@teste.com', '00000000-0000-0000-0000-000000000001', 'manual', 'qualified'),
('Maria Oliveira', '+5541999990003', 'maria@teste.com', '00000000-0000-0000-0000-000000000001', 'manual', 'lead'),
('Pedro Santos', '+5541999990004', '', '00000000-0000-0000-0000-000000000001', 'manual', 'lead'),
('Julia Ferreira', '+5541999990005', 'julia@teste.com', '00000000-0000-0000-0000-000000000001', 'manual', 'proposal');
```

#### 5.2 Vincular deals existentes a contatos
```sql
-- Vincular deals a contatos
UPDATE bcomm_inbox.deals 
SET contact_id = (
    SELECT id FROM bcomm_inbox.contacts 
    WHERE phone = deals.phone 
    LIMIT 1
)
WHERE contact_id IS NULL AND phone IS NOT NULL;
```

---

## 🔧 Arquivos Modificados

### Banco de Dados
| Arquivo | Mudança |
|---------|---------|
| `migrations/005_contacts_source.sql` | Colunas source_id, source_type, contact_id |

### Backend
| Arquivo | Mudança |
|---------|---------|
| `crm_routes.py` | Endpoints de contatos, sync, vinculação |
| `routes/routes_whatsapp.py` | Endpoint de sync de contatos |

### Frontend
| Arquivo | Mudança |
|---------|---------|
| `static/contacts.html` | Filtros, tabela, modal |
| `static/pipelines.html` | Select de contato no modal de deal |

---

## 📊 Fluxos

### Fluxo 1: Sync de Contatos
```
1. Usuário conecta WhatsApp (número X)
2. Clica em "Sincronizar Contatos"
3. Sistema busca contatos na Evolution API
4. Para cada contato:
   - Se phone já existe → atualiza nome
   - Se phone não existe → cria com source_id = X
5. Retorna: "10 novos, 5 atualizados, 2 duplicatas"
```

### Fluxo 2: Criar Deal com Contato
```
1. Usuário clica "+ Novo Deal"
2. Seleciona Pipeline e Estágio
3. Busca contato por nome/telefone
4. Ao selecionar:
   - Telefone preenche automaticamente
   - Nome preenche automaticamente
   - contact_id salvo no deal
5. Deal aparece com nome do contato
```

### Fluxo 3: Ver Contatos por Origem
```
1. Usuário vai para /contacts
2. Filtra por "Origem: BCOMMM (554199999999)"
3. Lista mostra apenas contatos daquela conexão
4. Pode ver deals vinculados a cada contato
```

---

## ⚠️ Validações

1. **Phone único por organização** - Mesmo phone pode existir em orgs diferentes
2. **Source obrigatório** - Contato criado via WhatsApp deve ter source_id
3. **Sync idempotente** - Rodar sync múltiplas vezes não cria duplicatas
4. **Deal precisa de contato** - Opcional mas recomendado

---

## 📊 Estimativa

| Fase | Tempo |
|------|-------|
| Fase 1: Banco | 30min |
| Fase 2: Backend | 1h30 |
| Fase 3: Frontend | 1h30 |
| Fase 4: Vinculação | 45min |
| Fase 5: Testes | 30min |
| **Total** | **~5h** |

---

## ✅ Critérios de Sucesso

- [ ] Contatos têm campo `source_id` e `source_type`
- [ ] Deals têm campo `contact_id`
- [ ] Página de contatos mostra origem
- [ ] Filtro por origem funciona
- [ ] Modal de deal permite selecionar contato
- [ ] Sync de contatos funciona (quando WhatsApp conectado)
- [ ] Contatos de teste criados e vinculados
- [ ] Sem duplicatas após sync
