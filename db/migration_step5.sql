-- Step 5: Alert Deduplication Buffer & Subagent Registration

CREATE TABLE IF NOT EXISTS collected_events (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(64) NOT NULL DEFAULT 'linux',
    host_target VARCHAR(128) NOT NULL,
    alert_type VARCHAR(128) NOT NULL,
    severity VARCHAR(32) NOT NULL DEFAULT 'warning',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    batch_id VARCHAR(128),
    processed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) DEFAULT 'PENDING'
);

CREATE INDEX IF NOT EXISTS idx_collected_events_status ON collected_events(status, received_at);
CREATE INDEX IF NOT EXISTS idx_collected_events_host ON collected_events(host_target);

-- Register Event Batcher Subagent for Linux SRE Domain
INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings)
SELECT 
    id,
    'event_batcher',
    'SRE Alert Event Deduplicator',
    'Ingests, buffers, and deduplicates high-frequency alert storms across host targets over rolling 5-minute windows into single consolidated execution runs.',
    'You are the SRE Alert Event Batcher & Deduplication Subagent. Your mission is to analyze buffered incident alarms from Prometheus/SolarWinds/Dynatrace, group redundant host failures, eliminate transient flapping alerts, and construct a deduplicated target manifest for the primary SRE Orchestrator.',
    '["ansible_pcs_status", "ansible_check_host_online", "ansible_get_server_info"]'::jsonb
FROM domain_agents 
WHERE key_name = 'linux_sre'
ON CONFLICT (parent_agent_id, name) DO UPDATE SET
    description = EXCLUDED.description,
    system_prompt = EXCLUDED.system_prompt,
    tool_bindings = EXCLUDED.tool_bindings;
