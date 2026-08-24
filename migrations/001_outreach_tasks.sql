-- Migration: Criar tabela de outreach tasks

CREATE SCHEMA IF NOT EXISTS bcomm_inbox;

CREATE TABLE IF NOT EXISTS bcomm_inbox.outreach_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_phone VARCHAR(20) NOT NULL,
    contact_name VARCHAR(255),
    contact_company VARCHAR(255),
    contact_email VARCHAR(255),
    instructions TEXT NOT NULL,
    initial_message TEXT NOT NULL,
    context JSONB DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    conversation_id UUID,
    messages_sent INTEGER DEFAULT 0,
    messages_received INTEGER DEFAULT 0,
    created_by UUID,
    assigned_to UUID,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outreach_status ON bcomm_inbox.outreach_tasks(status);
CREATE INDEX IF NOT EXISTS idx_outreach_phone ON bcomm_inbox.outreach_tasks(contact_phone);
CREATE INDEX IF NOT EXISTS idx_outreach_created ON bcomm_inbox.outreach_tasks(created_at DESC);

