-- Migration: Create agents table for multi-tenant agent management
-- Date: 2026-09-02

-- 1. Create agents table
CREATE TABLE IF NOT EXISTS bcomm_inbox.agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES bcomm_inbox.organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) NOT NULL,
    description TEXT,
    system_prompt TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    is_default BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID,
    UNIQUE(organization_id, slug)
);

-- 2. Create indexes
CREATE INDEX IF NOT EXISTS idx_agents_organization ON bcomm_inbox.agents(organization_id);
CREATE INDEX IF NOT EXISTS idx_agents_slug ON bcomm_inbox.agents(organization_id, slug);

-- 3. Add agent_id column to conversations
ALTER TABLE bcomm_inbox.conversations 
ADD COLUMN IF NOT EXISTS agent_id UUID REFERENCES bcomm_inbox.agents(id);

-- 4. Create index for conversations.agent_id
CREATE INDEX IF NOT EXISTS idx_conversations_agent ON bcomm_inbox.conversations(agent_id);

-- 5. Insert default organization "Org BCOMM" if not exists
INSERT INTO bcomm_inbox.organizations (id, name, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Org BCOMM',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO NOTHING;

-- 6. Insert default agents for Org BCOMM
-- Agent: Atendimento
INSERT INTO bcomm_inbox.agents (organization_id, name, slug, description, system_prompt, is_default, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Atendimento',
    'atendimento',
    'Agente para suporte geral e dúvidas',
    'Carregar do arquivo prompts/atendimento.md',
    true,
    NOW(),
    NOW()
)
ON CONFLICT (organization_id, slug) DO NOTHING;

-- Agent: Agendamento
INSERT INTO bcomm_inbox.agents (organization_id, name, slug, description, system_prompt, is_default, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Agendamento',
    'agendamento',
    'Agente para marcação de reuniões e consultas',
    'Carregar do arquivo prompts/agendamento.md',
    false,
    NOW(),
    NOW()
)
ON CONFLICT (organization_id, slug) DO NOTHING;

-- Agent: Financeiro
INSERT INTO bcomm_inbox.agents (organization_id, name, slug, description, system_prompt, is_default, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000001'::uuid,
    'Financeiro',
    'financeiro',
    'Agente para dúvidas sobre pagamentos e financeiro',
    'Carregar do arquivo prompts/financeiro.md',
    false,
    NOW(),
    NOW()
)
ON CONFLICT (organization_id, slug) DO NOTHING;
