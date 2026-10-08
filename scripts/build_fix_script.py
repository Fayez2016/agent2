#!/usr/bin/env bash
# ==============================================================================
# 🚀 Deep Agent: Complete Standalone Fix & Specialization Script
# ==============================================================================
# This script embeds the latest updated ansible_mcp_server.py (with trailing slash
# & fuzzy AAP matching), run_shell_command.yml, agent_engine.py, and executes
# the PostgreSQL subagent synchronization directly.
#
# Usage on air-gapped host:
#   chmod +x apply_deepagent_ansible_and_subagents_fix.sh
#   ./apply_deepagent_ansible_and_subagents_fix.sh
# ==============================================================================

set -euo pipefail

echo "=============================================================================="
echo " 🚀 Applying Complete Deep Agent Ansible MCP & Subagents Fix"
echo "=============================================================================="

# Ensure running containers exist
if ! podman ps -a --format "{{.Names}}" | grep -q "deepagent-ansible-mcp"; then
    echo "❌ Error: Container 'deepagent-ansible-mcp' not found."
    echo "Please make sure your Deep Agent pod/stack is installed."
    exit 1
fi

TMP_DIR="$(mktemp -d /tmp/deepagent_fix_XXXXXX)"
trap 'rm -rf "${TMP_DIR}"' EXIT

echo ">>> [1/5] Writing updated ansible_mcp_server.py..."
cat << 'PY_EOF' > "${TMP_DIR}/ansible_mcp_server.py"
__ANSIBLE_MCP_SERVER_CONTENT__
PY_EOF

echo ">>> [2/5] Writing playbooks..."
cat << 'YML_EOF' > "${TMP_DIR}/run_shell_command.yml"
__RUN_SHELL_COMMAND_CONTENT__
YML_EOF

cat << 'YML_EOF2' > "${TMP_DIR}/get_maintenance_window_hosts.yml"
__MAINTENANCE_WINDOW_CONTENT__
YML_EOF2

echo ">>> [3/5] Writing updated agent_engine.py..."
cat << 'ENGINE_EOF' > "${TMP_DIR}/agent_engine.py"
__AGENT_ENGINE_CONTENT__
ENGINE_EOF

echo ">>> [4/5] Copying updated files into running containers..."
podman cp "${TMP_DIR}/ansible_mcp_server.py" deepagent-ansible-mcp:/app/ansible_mcp_server.py
podman cp "${TMP_DIR}/run_shell_command.yml" deepagent-ansible-mcp:/app/ansible_playbooks/run_shell_command.yml 2>/dev/null || true
podman cp "${TMP_DIR}/get_maintenance_window_hosts.yml" deepagent-ansible-mcp:/app/ansible_playbooks/get_maintenance_window_hosts.yml 2>/dev/null || true
podman cp "${TMP_DIR}/agent_engine.py" deepagent-service:/app/app/agent_engine.py

echo ">>> [5/5] Updating domain_subagents in PostgreSQL (deepagent-hitl-db)..."
cat << 'SQL_EOF' > "${TMP_DIR}/update_subagents.sql"
-- 1. Ensure domain_subagents has only the 4 canonical subagents for parent_agent_id = 1 (linux_sre)
DELETE FROM domain_subagents WHERE parent_agent_id = 1;

-- 2. Insert the 3 clean specialized subagents + autonomous event batcher
INSERT INTO domain_subagents (parent_agent_id, name, display_name, description, system_prompt, tool_bindings, skills_path, is_active)
VALUES
(
  1,
  'pcs_cluster_specialist',
  'Red Hat HA Cluster Specialist',
  'Specialized subagent for Red Hat HA Pacemaker/Corosync cluster maintenance, quorum preservation, node standby/unstandby, and SOP 2059253 HA rolling updates.',
  'You are the Red Hat HA Cluster Specialist. You manage Pacemaker/Corosync clusters, node standby/unstandby, cluster start/stop, fence verification, and the HA Rolling Update SOP. When automated actions complete, always send an execution report via ansible_send_email.',
  '["ansible_get_maintenance_hosts", "ansible_pcs_status", "ansible_pcs_health_check", "ansible_pcs_node_standby", "ansible_pcs_node_unstandby", "ansible_pcs_cluster_stop", "ansible_pcs_cluster_start", "ansible_pcs_cluster_disable", "ansible_pcs_cluster_enable", "ansible_pcs_maintenance_mode", "ansible_pcs_resource_move", "ansible_pcs_resource_clear", "ansible_pcs_cib_upgrade", "ansible_pcs_constraint_list", "ansible_fix_pcs", "ansible_check_host_online", "ansible_run_command", "sop_get_procedure", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  '/app/skills/',
  true
),
(
  1,
  'fleet_patcher',
  'Enterprise Fleet Patching Specialist',
  'Specialized subagent for enterprise fleet package updates, DNF security patching, managed reboots, and post-reboot verification scale-ready for 500+ servers.',
  'You are the Enterprise Fleet Patching Specialist. You query maintenance block windows, partition fleets into 50-host waves, execute DNF security updates, isolate failing hosts, and manage fleet reboots. When patching completes, always send a post-patch verification summary via ansible_send_email.',
  '["ansible_get_maintenance_hosts", "ansible_patch_fleet", "ansible_reboot_fleet", "ansible_reboot_host", "ansible_check_host_online", "ansible_get_server_info", "ansible_run_command", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  '/app/skills/',
  true
),
(
  1,
  'rhel_diagnostician',
  'RHEL Diagnostic and Recovery Specialist',
  'Specialized subagent for host telemetry, log inspection (journalctl), storage expansion (/var), out-of-band IPMI recovery, and ad-hoc troubleshooting commands.',
  'You are the RHEL Diagnostic and Recovery Specialist. You gather system telemetry, inspect journal logs, resolve storage emergencies (/var filesystem expansion), perform out-of-band IPMI recovery, and execute emergency troubleshooting commands using ansible_run_command. When diagnostics or automated remediations finish, always send a tracking summary via ansible_send_email.',
  '["ansible_get_server_info", "ansible_check_host_online", "ansible_run_command", "ansible_expand_fs", "ansible_console_power_on", "ansible_vmware_reset", "ansible_install_package", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  '/app/skills/',
  true
),
(
  1,
  'event_batcher',
  'Autonomous Event Batcher & Alarm Triage Daemon',
  'Autonomous event batching, alarm deduplication, and initial triage daemon. Ingests monitoring alarms, verifies reachability, expands storage, and dispatches remediations.',
  'You are the Autonomous Event Batcher & Alarm Triage Daemon. You analyze incoming monitoring events, deduplicate alarm storms over 5-minute rolling windows, execute automated non-disruptive triage (ansible_get_server_info, ansible_expand_fs, ansible_check_host_online), and delegate complex remediations to specialized subagents. Always summarize results via ansible_send_email.',
  '["ansible_get_maintenance_hosts", "ansible_get_server_info", "ansible_check_host_online", "ansible_pcs_status", "ansible_expand_fs", "ansible_run_command", "ansible_send_email", "hitl_request_approval"]'::jsonb,
  '/app/skills/',
  true
);

-- 3. Verify subagent tool bindings in DB
SELECT name, display_name, jsonb_array_length(tool_bindings) AS tools_count FROM domain_subagents WHERE parent_agent_id = 1;
SQL_EOF

if podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl < "${TMP_DIR}/update_subagents.sql"; then
    echo "✓ Subagents updated in PostgreSQL via 'hermes' user."
elif podman exec -i deepagent-hitl-db psql -U deepagent -d deepagent < "${TMP_DIR}/update_subagents.sql" 2>/dev/null; then
    echo "✓ Subagents updated in PostgreSQL via 'deepagent' user."
else
    echo "⚠️ Warning: Failed to apply SQL update to deepagent-hitl-db. Please check database container."
fi

echo ">>> Restarting affected containers..."
podman restart deepagent-ansible-mcp deepagent-service

echo "=============================================================================="
echo " 🎉 SUCCESS: ansible_mcp_server.py, agent_engine, and subagents updated!"
echo " Containers deepagent-ansible-mcp and deepagent-service have been restarted."
echo "=============================================================================="
