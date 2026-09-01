-- ==============================================================================
-- Step 3 Database Migration: Dynamic Agent & Multi-Domain Architecture
-- ==============================================================================

-- 1. MCP Servers Registry
CREATE TABLE IF NOT EXISTS mcp_servers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(150),
    domain_scope VARCHAR(50) DEFAULT 'linux', -- linux, windows, vmware, global
    url TEXT NOT NULL,
    transport VARCHAR(50) DEFAULT 'streamable_http', -- streamable_http, stdio, sse
    is_active BOOLEAN DEFAULT TRUE,
    headers JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Domain Skills Registry
CREATE TABLE IF NOT EXISTS domain_skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(150),
    domain_category VARCHAR(50) DEFAULT 'linux', -- linux, windows, vmware, general
    description TEXT,
    content_markdown TEXT NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Domain Agents (Main Agents)
CREATE TABLE IF NOT EXISTS domain_agents (
    id SERIAL PRIMARY KEY,
    key_name VARCHAR(100) UNIQUE NOT NULL, -- e.g. linux_sre, windows_admin, vmware_cloud
    display_name VARCHAR(150) NOT NULL,
    domain_category VARCHAR(50) NOT NULL,  -- linux, windows, vmware
    description TEXT,
    model_provider VARCHAR(50) DEFAULT 'openrouter',
    model_name VARCHAR(100) DEFAULT 'qwen/qwen-2.5-72b-instruct',
    system_prompt TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Domain Subagents
CREATE TABLE IF NOT EXISTS domain_subagents (
    id SERIAL PRIMARY KEY,
    parent_agent_id INTEGER REFERENCES domain_agents(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL, -- e.g. ha_cluster_patcher, fleet_patcher
    display_name VARCHAR(150),
    description TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    tool_bindings JSONB DEFAULT '[]'::jsonb, -- list of tool name strings or wildcards
    skills_path VARCHAR(255) DEFAULT '/app/skills/',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_subagent_per_parent UNIQUE (parent_agent_id, name)
);

-- Grant full permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hermes;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hermes;
