# SOP: RHEL Fleet Patching (HA and Non-HA)

## 1. Purpose
To define a systematic, low-risk process for applying software updates to a fleet of RHEL servers, including High Availability (HA) clusters and standalone (Non-HA) nodes, ensuring service continuity and operational stability.

## 2. Scope
This procedure applies to all RHEL 7, 8, and 9 servers.
- **HA Nodes:** Managed via `pacemaker` and `pcs`, requiring sequential rolling updates.
- **Non-HA Nodes:** Standalone servers that can be updated in batches with planned reboots.

## 3. Roles and Responsibilities
- **Automation Agent:** Responsible for orchestration, fleet segregation, health validation, and execution of Ansible job templates via MCP.
- **System Administrator:** Responsible for final review of health reports and handling any "Failed" status exceptions.

## 4. Phase 1: Pre-Patching & Inventory
1. **Inventory Discovery:** The agent runs `ansible_get_server_info` to identify HA vs. Non-HA nodes and check for planned reboots.
2. **Backup:** Take snapshots or backups of all nodes (e.g., via VMware snapshot).
3. **Notification:** Use `ansible_send_email` to notify stakeholders of the maintenance window.

## 5. Phase 2: Execution - Non-HA Batch Patching
*Note: These nodes are patched in parallel or large batches to minimize downtime.*
1. **Apply Updates:** Run `ansible_patch_fleet` for the list of Non-HA nodes.
2. **Reboot Evaluation:**
   - If `planned_reboot` was requested in the inventory phase, OR
   - If the patching task reports `reboot_required: true`.
3. **Execute Reboot:** Run `ansible_reboot_host` for nodes requiring a restart.
4. **Health Check:** Verify system connectivity and core services.

## 6. Phase 3: Execution - HA Rolling Update
*Note: Perform these steps for each HA node sequentially to maintain cluster quorum.*

### Step A: Node Isolation
1. **Maintenance Mode:** Put the cluster into maintenance mode (`pcs property set maintenance-mode=true`).
2. **Disable Boot Start:** Run `ansible_pcs_cluster_disable` for the target node.
3. **Enter Standby:** Run `ansible_pcs_node_standby`. Verify resources migrated to peers.
4. **Stop Cluster Services:** Run `ansible_pcs_cluster_stop`.

### Step B: Update & Verification
1. **Apply Updates:** Run `ansible_patch_fleet` (filtered for the single node).
2. **Reboot Evaluation:** Follow the same logic as Non-HA (Planned or Required).
3. **Execute Reboot:** Run `ansible_reboot_host`.
4. **Post-Reboot Health Check:** Verify the system is up but cluster services remain stopped.

### Step C: Cluster Re-Integration
1. **Start Cluster Services:** Run `ansible_pcs_cluster_start`.
2. **Exit Standby:** Run `ansible_pcs_node_unstandby`.
3. **Enable Boot Start:** Run `ansible_pcs_cluster_enable`.
4. **Validation:** Run `ansible_pcs_health_check`. Ensure the node rejoins and resources balance.

## 7. Phase 4: Post-Patching & Reporting
1. **Maintenance Mode:** Disable maintenance mode (`pcs property set maintenance-mode=false`).
2. **CIB Upgrade:** If HA nodes were updated, run `ansible_pcs_cib_upgrade`.
3. **Final Fleet Check:** Verify all nodes (HA and Non-HA) are reachable and healthy.
4. **Completion Report:** Use `ansible_send_email` to distribute the final success/failure summary, including raw logs for any failures.

## 8. Contingency Plan
- **HA Quorum Loss:** If an HA node fails to rejoin, HALT the rolling update immediately.
- **Boot Failure:** Use `ansible_vmware_reset` to perform a hard reset if a node fails to respond after reboot.
- **Resource Failure:** If a resource fails to start, use `ansible_fix_pcs` or manual intervention.
