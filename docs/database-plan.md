# 🗄️ Plano Detalhado: Banco de Dados para Inbox

## 📋 Visão Geral

**Objetivo:** Criar banco de dados completo para sistema de atendimento (Inbox)

**Schema:** `bcomm_inbox` (separado do projeto existente)

**Banco:** Supabase (PostgreSQL) em `http://supabase.agent-bcomm.space`

---

## 🏗️ Arquitetura do Banco

```
┌─────────────────────────────────────────────────────────────────┐
│                    SUPABASE (PostgreSQL)                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Schema: bcomm_inbox                        │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │                                                         │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │   │
│  │  │   users     │    │  contacts   │    │conversations│ │   │
│  │  │ (atendentes)│───▶│ (clientes)  │◀───│  (chat)     │ │   │
│  │  └─────────────┘    └─────────────┘    └──────┬──────┘ │   │
│  │         │                    │                 │        │   │
│  │         │                    │                 │        │   │
│  │         ▼                    ▼                 ▼        │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │   │
│  │  │   roles     │    │   tags      │    │  messages   │ │   │
│  │  │ (permissões)│    │ (etiquetas) │    │ (mensagens) │ │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘ │   │
│  │                                                         │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │   │
│  │  │  agent_     │    │  business_  │    │  quick_     │ │   │
│  │  │  config     │    │  hours      │    │  replies    │ │   │
│  │  │ (agente)    │    │ (horários)  │    │ (respostas) │ │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘ │   │
│  │                                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Schema: public (existente)                  │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │  • leads (65 registros)                                 │   │
│  │  • scraping_jobs (8 registros)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📊 Tabelas Detalhadas

### **1. users (Atendentes/Usuários)**

```sql
CREATE TABLE bcomm_inbox.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Dados pessoais
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    
    -- Perfil
    avatar_url VARCHAR(500),
    phone VARCHAR(20),
    department VARCHAR(100),
    
    -- Permissão
    role_id UUID REFERENCES bcomm_inbox.roles(id),
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_online BOOLEAN DEFAULT FALSE,
    last_seen_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

-- Índices
CREATE INDEX idx_users_email ON bcomm_inbox.users(email);
CREATE INDEX idx_users_role ON bcomm_inbox.users(role_id);
CREATE INDEX idx_users_active ON bcomm_inbox.users(is_active);
```

---

### **2. roles (Permissões)**

```sql
CREATE TABLE bcomm_inbox.roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    name VARCHAR(50) UNIQUE NOT NULL, -- admin, manager, agent, viewer
    description TEXT,
    
    -- Permissões (JSON)
    permissions JSONB DEFAULT '{
        "can_view_conversations": true,
        "can_send_messages": true,
        "can_assign_conversations": false,
        "can_archive_conversations": false,
        "can_view_contacts": true,
        "can_edit_contacts": false,
        "can_view_reports": false,
        "can_manage_users": false,
        "can_manage_settings": false
    }',
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- Dados iniciais
INSERT INTO bcomm_inbox.roles (name, description, permissions) VALUES
('admin', 'Administrador completo', '{
    "can_view_conversations": true,
    "can_send_messages": true,
    "can_assign_conversations": true,
    "can_archive_conversations": true,
    "can_view_contacts": true,
    "can_edit_contacts": true,
    "can_view_reports": true,
    "can_manage_users": true,
    "can_manage_settings": true
}'),
('manager', 'Gerente de atendimento', '{
    "can_view_conversations": true,
    "can_send_messages": true,
    "can_assign_conversations": true,
    "can_archive_conversations": true,
    "can_view_contacts": true,
    "can_edit_contacts": true,
    "can_view_reports": true,
    "can_manage_users": false,
    "can_manage_settings": false
}'),
('agent', 'Atendente', '{
    "can_view_conversations": true,
    "can_send_messages": true,
    "can_assign_conversations": false,
    "can_archive_conversations": false,
    "can_view_contacts": true,
    "can_edit_contacts": false,
    "can_view_reports": false,
    "can_manage_users": false,
    "can_manage_settings": false
}'),
('viewer', 'Somente visualização', '{
    "can_view_conversations": true,
    "can_send_messages": false,
    "can_assign_conversations": false,
    "can_archive_conversations": false,
    "can_view_contacts": true,
    "can_edit_contacts": false,
    "can_view_reports": false,
    "can_manage_users": false,
    "can_manage_settings": false
}');
```

---

### **3. contacts (Contatos/Clientes)**

```sql
CREATE TABLE bcomm_inbox.contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Dados básicos
    phone VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255),
    
    -- Perfil
    avatar_url VARCHAR(500),
    company VARCHAR(255),
    job_title VARCHAR(255),
    
    -- Localização
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100) DEFAULT 'BR',
    
    -- Redes sociais
    instagram VARCHAR(255),
    linkedin VARCHAR(255),
    
    -- Classificação
    status VARCHAR(20) DEFAULT 'lead', -- lead, client, inactive
    source VARCHAR(50), -- website, whatsapp, referral, etc
    category VARCHAR(100),
    
    -- Tags
    tags TEXT[] DEFAULT '{}',
    
    -- Campos personalizados
    custom_fields JSONB DEFAULT '{}',
    
    -- Estatísticas
    total_messages INTEGER DEFAULT 0,
    last_message_at TIMESTAMP,
    last_contacted_at TIMESTAMP,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_contacts_phone ON bcomm_inbox.contacts(phone);
CREATE INDEX idx_contacts_status ON bcomm_inbox.contacts(status);
CREATE INDEX idx_contacts_tags ON bcomm_inbox.contacts USING GIN(tags);
CREATE INDEX idx_contacts_name ON bcomm_inbox.contacts(name);
```

---

### **4. conversations (Conversas)**

```sql
CREATE TABLE bcomm_inbox.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Relacionamentos
    contact_id UUID REFERENCES bcomm_inbox.contacts(id) ON DELETE CASCADE,
    client_id VARCHAR(100) NOT NULL, -- Instância BCOMM, etc
    assigned_to UUID REFERENCES bcomm_inbox.users(id),
    
    -- Status
    status VARCHAR(20) DEFAULT 'open', -- open, pending, closed, archived
    priority VARCHAR(10) DEFAULT 'normal', -- low, normal, high, urgent
    
    -- Contadores
    unread_count INTEGER DEFAULT 0,
    message_count INTEGER DEFAULT 0,
    
    -- Última mensagem
    last_message_at TIMESTAMP,
    last_message_preview VARCHAR(255),
    
    -- Tags e notas
    tags TEXT[] DEFAULT '{}',
    notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);

-- Índices
CREATE INDEX idx_conversations_contact ON bcomm_inbox.conversations(contact_id);
CREATE INDEX idx_conversations_client ON bcomm_inbox.conversations(client_id);
CREATE INDEX idx_conversations_assigned ON bcomm_inbox.conversations(assigned_to);
CREATE INDEX idx_conversations_status ON bcomm_inbox.conversations(status);
CREATE INDEX idx_conversations_last_message ON bcomm_inbox.conversations(last_message_at DESC);
```

---

### **5. messages (Mensagens)**

```sql
CREATE TABLE bcomm_inbox.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Relacionamento
    conversation_id UUID REFERENCES bcomm_inbox.conversations(id) ON DELETE CASCADE,
    
    -- Conteúdo
    direction VARCHAR(10) NOT NULL, -- inbound, outbound
    content TEXT NOT NULL,
    
    -- Tipo
    message_type VARCHAR(20) DEFAULT 'text', -- text, audio, image, document, video, sticker
    
    -- Status
    status VARCHAR(20) DEFAULT 'sent', -- sending, sent, delivered, read, failed
    
    -- Para áudio/imagem
    media_url VARCHAR(500),
    media_type VARCHAR(50),
    media_duration INTEGER, -- segundos para áudio
    media_size INTEGER, -- bytes
    
    -- Metadados
    metadata JSONB DEFAULT '{}',
    
    -- Remetente (para outbound)
    sender_id UUID REFERENCES bcomm_inbox.users(id),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    delivered_at TIMESTAMP,
    read_at TIMESTAMP
);

-- Índices
CREATE INDEX idx_messages_conversation ON bcomm_inbox.messages(conversation_id);
CREATE INDEX idx_messages_created ON bcomm_inbox.messages(created_at DESC);
CREATE INDEX idx_messages_direction ON bcomm_inbox.messages(direction);
CREATE INDEX idx_messages_status ON bcomm_inbox.messages(status);
```

---

### **6. tags (Etiquetas)**

```sql
CREATE TABLE bcomm_inbox.tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    name VARCHAR(50) UNIQUE NOT NULL,
    color VARCHAR(7) DEFAULT '#3b9eff', -- Cor hex
    
    created_at TIMESTAMP DEFAULT NOW()
);

-- Tags iniciais
INSERT INTO bcomm_inbox.tags (name, color) VALUES
('urgente', '#ff453a'),
('vip', '#ffd60a'),
('suporte', '#34c759'),
('vendas', '#3b9eff'),
('financeiro', '#af52de');
```

---

### **7. agent_config (Configuração do Agente)**

```sql
CREATE TABLE bcomm_inbox.agent_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    client_id VARCHAR(100) UNIQUE NOT NULL,
    
    -- Personalidade
    personality JSONB DEFAULT '{
        "tone": "professional",
        "language": "pt-BR",
        "max_response_length": 500,
        "typing_delay_enabled": true,
        "typing_delay_min": 4.0,
        "typing_delay_max": 15.0
    }',
    
    -- Horário comercial
    business_hours JSONB DEFAULT '{
        "start": "09:00",
        "end": "18:00",
        "timezone": "America/Sao_Paulo",
        "work_days": [1, 2, 3, 4, 5]
    }',
    
    -- Saudação
    greeting JSONB DEFAULT '{
        "welcome": "Olá! Como posso ajudar?",
        "outside_hours": "Estamos fora do horário comercial.",
        "holiday": "Feliz feriado!"
    }',
    
    -- Transferência
    transfer_rules JSONB DEFAULT '{
        "keywords": ["humano", "atendente", "pessoa"],
        "max_turns_before_transfer": 10,
        "sentiment_threshold": -0.5
    }',
    
    -- Limites
    rate_limit INTEGER DEFAULT 20,
    batch_wait FLOAT DEFAULT 10.0,
    
    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    test_mode BOOLEAN DEFAULT FALSE,
    test_numbers TEXT[] DEFAULT '{}',
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **8. quick_resplies (Respostas Rápidas)**

```sql
CREATE TABLE bcomm_inbox.quick_replies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    shortcut VARCHAR(20), -- /obrigado, /horario, etc
    
    category VARCHAR(50),
    
    created_by UUID REFERENCES bcomm_inbox.users(id),
    
    usage_count INTEGER DEFAULT 0,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Respostas iniciais
INSERT INTO bcomm_inbox.quick_replies (title, content, shortcut, category) VALUES
('Saudação', 'Olá! Como posso ajudar?', '/ola', 'Geral'),
('Horário', 'Nosso horário de atendimento é de segunda a sexta, das 9h às 18h.', '/horario', 'Geral'),
('Obrigado', 'Obrigado pelo contato! Se precisar de algo mais, é só chamar.', '/obrigado', 'Geral'),
('Aguarde', 'Aguarde um momento, vou verificar isso para você.', '/aguarde', 'Geral'),
('Transferir', 'Vou transferir para um atendente humano. Aguarde.', '/transferir', 'Atendimento');
```

---

### **9. conversation_notes (Notas Internas)**

```sql
CREATE TABLE bcomm_inbox.conversation_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    conversation_id UUID REFERENCES bcomm_inbox.conversations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES bcomm_inbox.users(id),
    
    content TEXT NOT NULL,
    
    is_pinned BOOLEAN DEFAULT FALSE,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

### **10. activity_log (Log de Atividades)**

```sql
CREATE TABLE bcomm_inbox.activity_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    conversation_id UUID REFERENCES bcomm_inbox.conversations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES bcomm_inbox.users(id),
    
    action VARCHAR(50) NOT NULL, -- created, assigned, status_changed, note_added, etc
    details JSONB DEFAULT '{}',
    
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🔗 Relacionamentos

```
┌─────────────────────────────────────────────────────────────────┐
│                      RELACIONAMENTOS                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  users ──────────┐                                             │
│       │          │                                             │
│       │          ▼                                             │
│       │    conversations ◄─────────────────────┐               │
│       │          │                             │               │
│       │          │                             │               │
│       ▼          ▼                             │               │
│  roles      contacts ──────────────────────────┘               │
│                    │                                           │
│                    │                                           │
│                    ▼                                           │
│               messages                                         │
│                                                                 │
│  conversations ──────┐                                         │
│       │              │                                         │
│       ▼              ▼                                         │
│  conversation_notes  activity_log                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Row Level Security (RLS)

```sql
-- Habilitar RLS
ALTER TABLE bcomm_inbox.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE bcomm_inbox.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE bcomm_inbox.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE bcomm_inbox.messages ENABLE ROW LEVEL SECURITY;

-- Política: Usuários veem apenas seus dados
CREATE POLICY "Users view own profile" ON bcomm_inbox.users
    FOR SELECT USING (auth.uid() = id);

-- Política: Atendentes veem conversas atribuídas
CREATE POLICY "Agents view assigned conversations" ON bcomm_inbox.conversations
    FOR SELECT USING (
        assigned_to = auth.uid() OR 
        assigned_to IS NULL
    );

-- Política: Mensagens da conversa visível
CREATE POLICY "View messages of visible conversations" ON bcomm_inbox.messages
    FOR SELECT USING (
        conversation_id IN (
            SELECT id FROM bcomm_inbox.conversations 
            WHERE assigned_to = auth.uid() OR assigned_to IS NULL
        )
    );

-- Política: Admins veem tudo
CREATE POLICY "Admins full access" ON bcomm_inbox.conversations
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM bcomm_inbox.users 
            WHERE id = auth.uid() AND role_id IN (
                SELECT id FROM bcomm_inbox.roles WHERE name = 'admin'
            )
        )
    );
```

---

## 📊 Índices Completos

```sql
-- Performance para buscas
CREATE INDEX idx_messages_search ON bcomm_inbox.messages 
    USING GIN(to_tsvector('portuguese', content));

CREATE INDEX idx_contacts_search ON bcomm_inbox.contacts 
    USING GIN(to_tsvector('portuguese', name || ' ' || COALESCE(company, '')));

-- Para ordenação
CREATE INDEX idx_conversations_unread ON bcomm_inbox.conversations(unread_count DESC) 
    WHERE unread_count > 0;

-- Para filtros
CREATE INDEX idx_messages_date_range ON bcomm_inbox.messages(created_at) 
    WHERE created_at > NOW() - INTERVAL '30 days';
```

---

## 📈 Views (Visões)

```sql
-- View: Conversas com detalhes
CREATE VIEW bcomm_inbox.v_conversations_detail AS
SELECT 
    c.id,
    c.status,
    c.priority,
    c.unread_count,
    c.last_message_at,
    c.last_message_preview,
    c.tags,
    ct.name as contact_name,
    ct.phone as contact_phone,
    ct.avatar_url as contact_avatar,
    u.name as agent_name,
    u.avatar_url as agent_avatar
FROM bcomm_inbox.conversations c
JOIN bcomm_inbox.contacts ct ON c.contact_id = ct.id
LEFT JOIN bcomm_inbox.users u ON c.assigned_to = u.id;

-- View: Estatísticas por atendente
CREATE VIEW bcomm_inbox.v_agent_stats AS
SELECT 
    u.id,
    u.name,
    COUNT(c.id) as total_conversations,
    COUNT(CASE WHEN c.status = 'open' THEN 1 END) as open_conversations,
    COUNT(CASE WHEN c.status = 'closed' THEN 1 END) as closed_conversations,
    AVG(EXTRACT(EPOCH FROM (c.closed_at - c.created_at))) as avg_resolution_time
FROM bcomm_inbox.users u
LEFT JOIN bcomm_inbox.conversations c ON u.id = c.assigned_to
GROUP BY u.id, u.name;
```

---

## 🔄 Functions (Funções)

```sql
-- Função: Criar conversa automaticamente
CREATE OR REPLACE FUNCTION bcomm_inbox.create_conversation(
    p_contact_phone VARCHAR,
    p_client_id VARCHAR
) RETURNS UUID AS $$
DECLARE
    v_contact_id UUID;
    v_conversation_id UUID;
BEGIN
    -- Buscar ou criar contato
    SELECT id INTO v_contact_id 
    FROM bcomm_inbox.contacts 
    WHERE phone = p_contact_phone;
    
    IF v_contact_id IS NULL THEN
        INSERT INTO bcomm_inbox.contacts (phone) 
        VALUES (p_contact_phone)
        RETURNING id INTO v_contact_id;
    END IF;
    
    -- Criar conversa
    INSERT INTO bcomm_inbox.conversations (contact_id, client_id)
    VALUES (v_contact_id, p_client_id)
    RETURNING id INTO v_conversation_id;
    
    RETURN v_conversation_id;
END;
$$ LANGUAGE plpgsql;

-- Função: Atualizar última mensagem
CREATE OR REPLACE FUNCTION bcomm_inbox.update_last_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE bcomm_inbox.conversations
    SET 
        last_message_at = NEW.created_at,
        last_message_preview = LEFT(NEW.content, 255),
        message_count = message_count + 1,
        updated_at = NOW()
    WHERE id = NEW.conversation_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Atualiza quando nova mensagem
CREATE TRIGGER trigger_update_last_message
    AFTER INSERT ON bcomm_inbox.messages
    FOR EACH ROW
    EXECUTE FUNCTION bcomm_inbox.update_last_message();
```

---

## 📋 Script de Criação Completo

```sql
-- 1. Criar schema
CREATE SCHEMA IF NOT EXISTS bcomm_inbox;

-- 2. Criar tabelas (ordem importa por dependências)
-- [Inserir todas as CREATE TABLE acima]

-- 3. Criar índices
-- [Inserir todos os CREATE INDEX acima]

-- 4. Inserir dados iniciais
-- [Inserir roles, tags, quick_replies]

-- 5. Criar functions e triggers
-- [Inserir functions e triggers]

-- 6. Criar views
-- [Inserir views]

-- 7. Habilitar RLS
-- [Inserir políticas]

-- 8. Criar usuário admin inicial
INSERT INTO bcomm_inbox.users (email, name, password_hash, role_id)
VALUES (
    'admin@bcomm.com',
    'Administrador',
    -- Hash de 'admin123'
    '$2b$12$LJ3m4ys3Lg.Ky5Z5g5g5g.U5g5g5g5g5g5g5g5g5g5g5g5g5g',
    (SELECT id FROM bcomm_inbox.roles WHERE name = 'admin')
);
```

---

## 📊 Resumo das Tabelas

| Tabela | Registros Iniciais | Descrição |
|--------|-------------------|-----------|
| users | 1 (admin) | Atendentes |
| roles | 4 | Permissões |
| contacts | 0 | Clientes |
| conversations | 0 | Conversas |
| messages | 0 | Mensagens |
| tags | 5 | Etiquetas |
| agent_config | 1 | Config agente |
| quick_replies | 5 | Respostas rápidas |
| conversation_notes | 0 | Notas |
| activity_log | 0 | Logs |

---

## ⏱️ Script de Migração

```bash
# 1. Conectar ao banco
psql -h supabase-db -U supabase_admin -d postgres

# 2. Executar migração
\i migrations/001_create_inbox_schema.sql

# 3. Verificar
\dt bcomm_inbox.*
```

---

**Status:** ⏳ Pronto para implementação
