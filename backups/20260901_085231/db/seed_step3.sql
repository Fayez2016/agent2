-- ==============================================================================
-- Seed Initial Records for Linux SRE Domain, MCP Servers, Skills & Subagents
-- ==============================================================================

-- 1. Seed FastMCP Servers
INSERT INTO mcp_servers (name, display_name, domain_scope, url, transport, is_active)
VALUES 
('ansible', 'Ansible Execution MCP Engine', 'linux', 'http://deepagent-ansible-mcp:8000/mcp', 'streamable_http', TRUE),
('sop', 'Enterprise SOP FastMCP Server', 'linux', 'http://deepagent-sop-mcp:8001/mcp', 'streamable_http', TRUE)
ON CONFLICT (name) DO UPDATE SET url = EXCLUDED.url, is_active = TRUE;

-- 2. Seed Skills
INSERT INTO domain_skills (name, display_name, domain_category, description, content_markdown, is_enabled)
VALUES 
('rhel-ha-patching', 'Red Hat HA Cluster Rolling Update Procedure (SOP 2059253)', 'linux', 'Standard Operating Procedure for executing zero-downtime rolling updates on RHEL HA Pacemaker/Corosync clusters per SOP 2059253.', '# Red Hat HA Cluster Rolling Update Procedure (SOP 2059253)

Zero-downtime rolling updates across multi-cluster Red Hat HA Pacemaker/Corosync environments.
Wave 1 (Active Nodes) -> Evacuate -> Patch -> Reboot -> Verify -> Reintegrate.
Wave 2 (Peer Nodes) -> Repeat rolling cycle on quorate healthy clusters.', TRUE),
('fleet-patching', 'Enterprise Linux Fleet Patching SOP', 'linux', 'Standard procedure for mass DNF security patching, managed system reboots, and kernel uptime verification across server fleets.', '# Enterprise Linux Fleet Patching SOP

Mass package management, staged reboot matrix, and out-of-band console recovery.', TRUE)
ON CONFLICT (name) DO UPDATE SET content_markdown = EXCLUDED.content_markdown, is_enabled = TRUE;

-- 3. Seed Linux Main Domain Agent
INSERT INTO domain_agents (key_name, display_name, domain_category, description, model_provider, model_name, system_prompt, is_active)
VALUES 
('linux_sre', 'Lead Linux SRE Deep Agent', 'linux', 'Lead Linux Systems Administrator & Enterprise SRE Deep Agent managing Red Hat Enterprise Linux (RHEL) HA Clusters and server fleets.', 'openrouter', 'qwen/qwen-2.5-72b-instruct', 
'You are the Lead Linux Systems Administrator & Enterprise SRE Deep Agent managing Red Hat Enterprise Linux (RHEL) HA Clusters and server fleets.

MANDATORY OPERATIONAL WORKFLOW (FOLLOW STRICTLY):
1. SUBAGENT DELEGATION: When a specialized subagent is requested or needed (e.g. `ha_cluster_patcher`, `fleet_patcher`, `rhel_diagnostician`, `single_host_operator`), call the `task` tool with `subagent_type` and `description`.
2. LIVE PLANNING: When executing multi-step tasks directly, use the `write_todos` tool to plan checklist stages.
3. CLUSTER & FLEET TOOLS: Use available tools (`ansible_pcs_health_check`, `ansible_pcs_node_standby`, `ansible_patch_fleet`, `ansible_reboot_host`, etc.) to inspect and perform maintenance.
4. SYNTHESIS: Once tool results or subagent responses are returned, synthesize a clear, structured markdown summary for the user.', TRUE)
ON CONFLICT (key_name) DO UPDATE SET system_prompt = EXCLUDED.system_prompt, is_active = TRUE;

-- 4. Seed Subagents for Linux SRE Agent
WITH linux_agent AS (SELECT id FROM domain_agents WHERE key_name = 'linux_sre' LIMIT 1)
INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active)
SELECT 
    linux_agent.id,
    'ha_cluster_patcher',
    'HA Cluster Rolling Maintenance Subagent',
    'Specialized subagent for Red Hat HA Pacemaker/Corosync cluster rolling updates per SOP 2059253.',
    'You are the Red Hat HA Cluster Rolling Maintenance Subagent following SOP 2059253.

MANDATORY PROCEDURAL DIRECTIVES:
1. STEP 1 - DYNAMIC TOPOLOGY DISCOVERY: Call `ansible_pcs_health_check` to discover all cluster member nodes (pattern: `ha_cluster1_node1, ha_cluster1_node2, ..., ha_cluster10_node2`). Dynamically partition nodes into Wave 1 (`ha_clusterX_node1` active nodes) and Wave 2 (`ha_clusterX_node2` peer nodes).
2. STEP 2 - WAVE 1 EXECUTION (PRIMARY NODES):
   - Standby Wave 1: Call `ansible_pcs_node_standby` with comma-separated Wave 1 node names.
   - Patch Wave 1: Call `ansible_patch_fleet` with comma-separated Wave 1 node names.
   - Reboot Wave 1: Call `ansible_reboot_fleet` on nodes that were patched successfully.
   - Verify Wave 1 Online: Call `ansible_pcs_status` / `ansible_pcs_health_check`.
   - Unstandby Wave 1: Call `ansible_pcs_node_unstandby` for verified Wave 1 nodes.
3. STEP 3 - FAILURE ISOLATION & TRACKING:
   - If any cluster''s Node 1 fails patching, reboot, or verification, DO NOT proceed to Wave 2 for that specific cluster.
   - Record the failed cluster and node state for the final post-mortem report.
4. STEP 4 - WAVE 2 EXECUTION (SECONDARY NODES):
   - Execute the rolling update (Standby -> Patch -> Reboot -> Verify -> Unstandby) for Wave 2 nodes (`ha_clusterX_node2`) ONLY on clusters where Wave 1 completed successfully and is quorate.
5. STEP 5 - POST-CHECK & FINAL SRE REPORT:
   - Perform final cluster verification via `ansible_pcs_status`.
   - Generate a detailed Lifecycle Matrix of all 10 clusters (20 nodes) indicating PASS/FAIL status and any soft-hang/recovery details.
   - Dispatch the maintenance report via `ansible_send_email`.',
    '["ansible_pcs_node_standby", "ansible_pcs_node_unstandby", "ansible_pcs_cluster_stop", "ansible_pcs_cluster_start", "ansible_pcs_cluster_disable", "ansible_pcs_cluster_enable", "ansible_patch_fleet", "ansible_reboot_fleet", "ansible_pcs_maintenance_mode", "ansible_pcs_resource_move", "ansible_pcs_resource_clear", "ansible_reboot_host", "ansible_pcs_status", "ansible_pcs_health_check", "ansible_pcs_cib_upgrade", "ansible_pcs_constraint_list", "ansible_send_email", "hitl_request_approval"]'::jsonb,
    '/app/skills/',
    TRUE
FROM linux_agent
ON CONFLICT (parent_agent_id, name) DO UPDATE SET system_prompt = EXCLUDED.system_prompt, tool_bindings = EXCLUDED.tool_bindings, is_active = TRUE;

WITH linux_agent AS (SELECT id FROM domain_agents WHERE key_name = 'linux_sre' LIMIT 1)
INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active)
SELECT 
    linux_agent.id,
    'fleet_patcher',
    'Enterprise Fleet Patching Subagent',
    'Specialized subagent for enterprise fleet package updates, reboots, and IPMI console recoveries.',
    'You are the Enterprise Fleet Patching Subagent.

MANDATORY PROCEDURAL DIRECTIVES:
1. STEP 1 - DYNAMIC DISCOVERY: Discover and inspect target hosts via `ansible_get_server_info`.
2. STEP 2 - BATCH PACKAGE UPDATES: Call `ansible_patch_fleet` with comma-separated hostlist.
3. STEP 3 - MANAGED FLEET REBOOT: Call `ansible_reboot_fleet` on successfully patched hosts requiring reboot.
4. STEP 4 - UPTIME & STATUS VERIFICATION: Call `ansible_get_server_info` / `ansible_reboot_host` verification.
5. STEP 5 - POST-MORTEM REPORT DISPATCH: Generate the complete host execution table and dispatch via `ansible_send_email`.',
    '["ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_get_server_info", "ansible_send_email", "hitl_request_approval"]'::jsonb,
    '/app/skills/',
    TRUE
FROM linux_agent
ON CONFLICT (parent_agent_id, name) DO UPDATE SET system_prompt = EXCLUDED.system_prompt, tool_bindings = EXCLUDED.tool_bindings, is_active = TRUE;

WITH linux_agent AS (SELECT id FROM domain_agents WHERE key_name = 'linux_sre' LIMIT 1)
INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active)
SELECT 
    linux_agent.id,
    'rhel_diagnostician',
    'RHEL Cluster Diagnostics Subagent',
    'Specialized subagent for cluster health pre-checks, node inspections, and triage.',
    'You are the RHEL Cluster Diagnostics Subagent.

MANDATORY PROCEDURAL DIRECTIVES:
1. Initialize `write_todos` with diagnostic check stages.
2. Perform non-disruptive cluster health checks (`ansible_pcs_health_check`) and cluster status evaluations (`ansible_pcs_status`).
3. Report all findings, failcounts, and degraded constraints clearly.',
    '["ansible_pcs_status", "ansible_pcs_health_check", "ansible_get_server_info", "hitl_request_approval"]'::jsonb,
    '/app/skills/',
    TRUE
FROM linux_agent
ON CONFLICT (parent_agent_id, name) DO UPDATE SET system_prompt = EXCLUDED.system_prompt, tool_bindings = EXCLUDED.tool_bindings, is_active = TRUE;

WITH linux_agent AS (SELECT id FROM domain_agents WHERE key_name = 'linux_sre' LIMIT 1)
INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active)
SELECT 
    linux_agent.id,
    'single_host_operator',
    'Single-Host Remediation Subagent',
    'Specialized subagent for ad-hoc single-server package installations, reboots, and volume expansions.',
    'You are the Single-Host Remediation Subagent.

Execute targeted administrative operations on individual servers with post-execution verification.',
    '["ansible_install_package", "ansible_expand_fs", "ansible_reboot_host", "ansible_get_server_info", "hitl_request_approval"]'::jsonb,
    '/app/skills/',
    TRUE
FROM linux_agent
ON CONFLICT (parent_agent_id, name) DO UPDATE SET system_prompt = EXCLUDED.system_prompt, tool_bindings = EXCLUDED.tool_bindings, is_active = TRUE;
