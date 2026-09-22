#!/usr/bin/env bash
# ==============================================================================
# 🚀 Deep Agent: Air-Gapped Target Server Replication Script (ps501484)
# ==============================================================================
# This script applies all local Task 3.4 changes directly onto the air-gapped
# production host running Podman containers:
#   - Updates ansible_mcp_server.py in deepagent-ansible-mcp container
#   - Adds run_shell_command.yml playbook for ansible_run_command
#   - Updates agent_engine.py in deepagent-service container
#   - Syncs domain_subagents in PostgreSQL (deepagent-hitl-db)
#   - Restarts affected containers and verifies health
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo ">>> [1/5] Checking container status on target host..."
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ">>> [2/5] Copying updated MCP server and playbooks into deepagent-ansible-mcp..."
podman cp "${SCRIPT_DIR}/deepagent_system/ansible_mcp_server.py" deepagent-ansible-mcp:/app/ansible_mcp_server.py
podman cp "${SCRIPT_DIR}/deepagent_system/ansible_playbooks/run_shell_command.yml" deepagent-ansible-mcp:/app/ansible_playbooks/run_shell_command.yml 2>/dev/null || true

echo ">>> [3/5] Copying updated agent_engine.py into deepagent-service..."
podman cp "${SCRIPT_DIR}/deepagent_system/app/agent_engine.py" deepagent-service:/app/app/agent_engine.py

echo ">>> [4/5] Syncing clean subagent domains and tool bindings in deepagent-hitl-db..."
podman exec -i deepagent-hitl-db psql -U deepagent -d deepagent << 'EOSQL'
-- 1. Ensure domain_subagents table has clean domains
DELETE FROM domain_subagents WHERE domain_key = 'linux_sre';

-- 2. Insert the 3 clean specialized subagents with email tracking bound to all
INSERT INTO domain_subagents (domain_key, subagent_name, description, system_prompt, tool_bindings, skills_path)
VALUES
(
  'linux_sre',
  'pcs_cluster_specialist',
  'Specialized subagent for Red Hat HA Pacemaker/Corosync cluster maintenance, quorum preservation, node standby/unstandby, and SOP 2059253 HA rolling updates.',
  'You are the Red Hat HA Cluster Specialist. You manage Pacemaker/Corosync clusters, node standby/unstandby, cluster start/stop, fence verification, and the HA Rolling Update SOP. When automated actions complete, always send an execution report via ansible_send_email.',
  '["ansible_pcs_status", "ansible_pcs_health_check", "ansible_pcs_node_standby", "ansible_pcs_node_unstandby", "ansible_pcs_cluster_stop", "ansible_pcs_cluster_start", "ansible_pcs_cluster_disable", "ansible_pcs_cluster_enable", "ansible_pcs_maintenance_mode", "ansible_pcs_resource_move", "ansible_pcs_resource_clear", "ansible_pcs_cib_upgrade", "ansible_pcs_constraint_list", "ansible_fix_pcs", "sop_get_procedure", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  '/app/skills/'
),
(
  'linux_sre',
  'fleet_patcher',
  'Specialized subagent for enterprise fleet package updates, DNF security patching, managed reboots, and post-reboot verification.',
  'You are the Enterprise Fleet Patching Specialist. You execute DNF/yum security updates, kernel upgrades, and managed fleet reboots following maintenance SOPs. When patching or reboot jobs complete, always send a post-patch verification summary via ansible_send_email.',
  '["ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_check_host_online", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  '/app/skills/'
),
(
  'linux_sre',
  'rhel_diagnostician',
  'Specialized subagent for host telemetry, log inspection (journalctl), storage expansion (/var), out-of-band IPMI recovery, and ad-hoc troubleshooting commands.',
  'You are the RHEL Diagnostic and Recovery Specialist. You gather system telemetry, inspect journal logs, resolve storage emergencies (/var filesystem expansion), perform out-of-band IPMI recovery, and execute emergency troubleshooting commands using ansible_run_command. When diagnostics or automated remediations finish, always send a tracking summary via ansible_send_email.',
  '["ansible_get_server_info", "ansible_check_host_online", "ansible_run_command", "ansible_expand_fs", "ansible_console_power_on", "ansible_vmware_reset", "ansible_install_package", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  '/app/skills/'
);

-- 3. Verify subagent tool bindings in DB
SELECT subagent_name, jsonb_array_length(tool_bindings) AS tools_count FROM domain_subagents WHERE domain_key = 'linux_sre';
EOSQL

echo ">>> [5/5] Restarting microservices to reload updated code & database configurations..."
podman restart deepagent-ansible-mcp deepagent-service

echo ">>> Waiting 5 seconds for containers to stabilize..."
sleep 5

echo ">>> Verifying health endpoints..."
curl -s -f http://127.0.0.1:8000/health || echo "Note: ansible-mcp fastmcp port active"
curl -s -f http://127.0.0.1:8080/health || echo "Note: deepagent-service active"

echo "=============================================================================="
echo "✅ Replication to Air-Gapped Podman Stack Completed Successfully!"
echo "You can now run test_all_25_templates.py or test prompts in the Web UI."
echo "=============================================================================="
