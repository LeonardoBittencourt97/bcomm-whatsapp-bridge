-- Performance indexes for bcomm_inbox schema
-- Run this migration in Supabase SQL editor
-- Idempotent: safe to re-run.

-- Conversations
CREATE INDEX IF NOT EXISTS idx_conversations_phone ON bcomm_inbox.conversations(phone);
CREATE INDEX IF NOT EXISTS idx_conversations_org ON bcomm_inbox.conversations(organization_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON bcomm_inbox.conversations(status);

-- Messages
CREATE INDEX IF NOT EXISTS idx_messages_conv ON bcomm_inbox.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON bcomm_inbox.messages(created_at DESC);

-- Deals
CREATE INDEX IF NOT EXISTS idx_deals_pipeline ON bcomm_inbox.deals(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_deals_stage ON bcomm_inbox.deals(stage);
CREATE INDEX IF NOT EXISTS idx_deals_contact ON bcomm_inbox.deals(contact_id);
CREATE INDEX IF NOT EXISTS idx_deals_org ON bcomm_inbox.deals(organization_id);

-- Contacts
CREATE INDEX IF NOT EXISTS idx_contacts_org ON bcomm_inbox.contacts(organization_id);
CREATE INDEX IF NOT EXISTS idx_contacts_phone ON bcomm_inbox.contacts(phone);

-- Activities
CREATE INDEX IF NOT EXISTS idx_activities_entity ON bcomm_inbox.activities(entity_type, entity_id);

-- User organizations
CREATE INDEX IF NOT EXISTS idx_user_orgs_user ON bcomm_inbox.user_organizations(user_id);
CREATE INDEX IF NOT EXISTS idx_user_orgs_org ON bcomm_inbox.user_organizations(organization_id);

-- Stages
CREATE INDEX IF NOT EXISTS idx_stages_pipeline ON bcomm_inbox.stages(pipeline_id);