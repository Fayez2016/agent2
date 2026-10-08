#!/usr/bin/env bash
# ==============================================================================
# 🚀 Deep Agent: Refresh Studio Subagents in PostgreSQL
# ==============================================================================
# This script directly updates the PostgreSQL database (`hitl-db`) to replace
# legacy subagents with the 4 canonical, streamlined subagents:
#   1. pcs_cluster_specialist
#   2. fleet_patcher
#   3. rhel_diagnostician
#   4. event_batcher
#
# Usage:
#   chmod +x update_studio_subagents.sh
#   ./update_studio_subagents.sh
# ==============================================================================

set -euo pipefail

echo "=============================================================================="
echo " 🔄 Updating Studio Subagents in PostgreSQL (deepagent-hitl-db)..."
echo "=============================================================================="

TMP_DIR="$(mktemp -d /tmp/deepagent_sql_XXXXXX)"
trap 'rm -rf "${TMP_DIR}"' EXIT

cat << 'SQL_EOF' > "${TMP_DIR}/update_subagents.sql"
-- 1. Remove legacy subagents for parent_agent_id = 1 (linux_sre)
DELETE FROM domain_subagents WHERE parent_agent_id = 1;

-- 2. Insert canonical subagents with exact schema matching
INSERT INTO domain_subagents (
    parent_agent_id,
    name,
    display_name,
    description,
    system_prompt,
    tool_bindings,
    skills_path,
    is_active
) VALUES
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

-- 3. Display verification summary
SELECT name, display_name, jsonb_array_length(tool_bindings) AS tools_count, is_active FROM domain_subagents WHERE parent_agent_id = 1;
SQL_EOF

echo ">>> Applying SQL migration to database container..."
if podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl < "${TMP_DIR}/update_subagents.sql"; then
    echo "✓ Subagents successfully updated via 'hermes' user."
elif podman exec -i deepagent-hitl-db psql -U deepagent -d deepagent < "${TMP_DIR}/update_subagents.sql" 2>/dev/null; then
    echo "✓ Subagents successfully updated via 'deepagent' user."
else
    echo "❌ Error: Failed to execute SQL against deepagent-hitl-db."
    exit 1
fi

echo ">>> Restarting deepagent-service container..."
podman restart deepagent-service

echo "=============================================================================="
echo " 🎉 SUCCESS: Studio subagents updated in PostgreSQL!"
echo " Refresh your browser on the Studio tab to view the updated subagents."
echo "=============================================================================="
