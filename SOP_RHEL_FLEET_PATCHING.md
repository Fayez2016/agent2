# SOP: RHEL Fleet Patching (HA and Non-HA)

## 1. Purpose
To define a systematic, low-risk process for applying software updates to a fleet of RHEL servers, including High Availability (HA) clusters and standalone (Non-HA) nodes, ensuring service continuity and operational stability.

## 2. Scope
This procedure applies to all RHEL 7, 8, and 9 servers.
- **HA Nodes:** Managed via `pacemaker` and `pcs`, requiring sequential rolling updates.
- **Non-HA Nodes:** Standalone servers that can be updated in batches with planned reboots.

## 3. Roles and Responsibilities
- **Automation Agent:** Responsible for orchestration, fleet segregation, health validation, and execution of Ansible job templates via MCP.
  - **Subagent Delegation:** The Lead Orchestrator agent MUST delegate Non-HA batch operations to the `fleet_patcher` subagent and HA cluster operations to `pcs_cluster_specialist`.
- **System Administrator:** Responsible for final review of health reports and handling any "Failed" status exceptions.

## 4. Phase 1: Pre-Patching & Inventory
1. **Target Hosts Determination:**
   - **Explicit User Host List (Priority):** If the user specifies specific hosts in their prompt (e.g. `cs-popcorn` or a comma-separated list), target those hosts directly.
   - **Automated Discovery (Fallback):** If no hosts are explicitly specified, run `ansible_get_maintenance_hosts` to discover all servers scheduled for the active maintenance window.
2. **Fleet Segregation:**
   - Standalone servers -> Handed off to `fleet_patcher`.
   - PCS Cluster nodes -> Handed off to `pcs_cluster_specialist`.
3. **Backup / Snapshot:** Take snapshots or backups of all critical nodes if applicable.

## 5. Phase 2: Execution - Non-HA Fleet Patching (`fleet_patcher`)
*Note: Standalone nodes are patched in batches to minimize overall maintenance window duration.*
1. **Apply Updates:** Run `ansible_patch_fleet` for the list of Non-HA nodes.
2. **Reboot Evaluation:**
   - If `planned_reboot: true`, OR
   - If the patching task reports `need_to_restart: true` / `reboot_required: true`.
   - If `need_to_restart: false`, SKIP reboot for that node and proceed to final summary.
3. **Execute Reboot:** Run `ansible_reboot_host` or `ansible_reboot_fleet` for nodes requiring restart.
4. **Health Check:** Run `ansible_check_host_online` to verify SSH port 22 connectivity and kernel uptime.
5. **Strict SOP Completion Boundary:**
   - Once `ansible_check_host_online` returns `online: true`, the patching lifecycle for that host is **100% COMPLETE**.
   - **PROHIBITION:** The agent MUST NOT execute ad-hoc grubby, bootloader edits, `dnf remove`, or `dnf reinstall` commands.
   - Any minor kernel version or BLS entry discrepancy must be logged as an `INFO/WARNING` in the final summary report for human review, NOT modified via shell commands.
6. **Final Summary:** Emit the structured execution summary report to conclude the session.

## 6. Phase 3: Execution - HA Rolling Update (`pcs_cluster_specialist`)
*Note: Perform these steps for each HA node sequentially to maintain cluster quorum per Red Hat SOP 2059253.*

### Step A: Node Isolation
1. **Disable Boot Start:** Run `ansible_pcs_cluster_disable` for the target node.
2. **Enter Standby:** Run `ansible_pcs_node_standby`. Verify resources migrated to peers.
3. **Stop Cluster Services:** Run `ansible_pcs_cluster_stop`.

### Step B: Update & Verification
1. **Apply Updates:** Run `ansible_patch_fleet` (filtered for the single node).
2. **Reboot Evaluation:** Follow the same logic as Non-HA (`need_to_restart: true`).
3. **Execute Reboot:** Run `ansible_reboot_host`.
4. **Post-Reboot Health Check:** Verify the system is up on SSH port 22.

### Step C: Cluster Re-Integration
1. **Start Cluster Services:** Run `ansible_pcs_cluster_start`.
2. **Exit Standby:** Run `ansible_pcs_node_unstandby`.
3. **Enable Boot Start:** Run `ansible_pcs_cluster_enable`.
4. **Validation:** Run `ansible_pcs_health_check`. Ensure the node rejoins and resources balance.

## 7. Phase 4: Post-Patching & Reporting
1. **Final Fleet Check:** Verify all nodes (HA and Non-HA) are reachable and healthy.
2. **Completion Report:** Distribute the final success/failure summary table in chat, including kernel versions and execution status.

## 8. Contingency Plan
- **HA Quorum Loss:** If an HA node fails to rejoin, HALT the rolling update immediately.
- **Boot Failure:** Use `ansible_vmware_reset` to perform a hard reset if a node fails to respond to SSH after reboot.
- **Resource Failure:** Use `ansible_fix_pcs` or manual intervention.
