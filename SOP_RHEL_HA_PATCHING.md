# SOP: RHEL High Availability Cluster Patching (Rolling Update)

## 1. Purpose
To define a systematic, low-risk process for applying software updates to RHEL High Availability or Resilient Storage clusters, ensuring service continuity and preventing accidental node fencing or cluster split-brain scenarios.

## 2. Scope
This procedure applies to all RHEL 7, 8, and 9 clusters managed via `pacemaker` and `pcs`, specifically focusing on **Rolling Updates** where one node is updated at a time.

## 3. Roles and Responsibilities
- **Automation Agent:** Responsible for orchestration, health validation, and execution of Ansible job templates via MCP.
- **System Administrator:** Responsible for final review of health reports and handling any "Failed" status exceptions via HITL approval gate.

## 4. Pre-Patching Phase (Fleet Wide)
1. **Backup:** Take a snapshot or backup of all cluster nodes (e.g., via VMware snapshot).
2. **Initial Status Check:** 
   - Use `ansible_pcs_prepatch_check` to verify all nodes are online and resources are healthy.
   - Run `pcs status` and `pcs constraint list` to document current state.
3. **Fencing Verification:** Ensure STONITH/Fencing is functional.
4. **Maintenance Mode (Optional but Recommended):** Put the cluster into maintenance mode to prevent unexpected cluster actions during service stops.
   - `pcs property set maintenance-mode=true`
5. **Notification:** Use `ansible_send_email` to notify stakeholders of the start of the patching window.
6. **Download Patches:** Use `ansible_patch_fleet` (with no-reboot) to stage updates across the fleet.

## 5. Execution Phase (Per-Node Rolling Update)
*Note: Perform these steps for each node sequentially (e.g., node-01, then node-02).*

### Step A: Node Isolation
1. **Disable Boot Start:** Run `ansible_pcs_cluster_disable` for the target node. This prevents the cluster from starting automatically if the node reboots prematurely.
2. **Enter Standby:** Run `ansible_pcs_node_standby`. Monitor until all resources have migrated to active peers.
3. **Stop Cluster Services:** Run `ansible_pcs_cluster_stop` to gracefully shut down `pacemaker` and `corosync`.

### Step B: Update & Verification
1. **Apply Updates:** Confirm all packages are updated (DNF/YUM update).
2. **Reboot Node:** Run `ansible_reboot_host`.
3. **Post-Reboot Health Check:** Run `ansible_pcs_health_check` locally on the node (it should report as offline/not running, but system services should be healthy).

### Step C: Cluster Re-Integration
1. **Start Cluster Services:** Run `ansible_pcs_cluster_start`.
2. **Exit Standby:** Run `ansible_pcs_node_unstandby`.
3. **Enable Boot Start:** Run `ansible_pcs_cluster_enable`.
4. **Validation:** Run `ansible_pcs_health_check`. Ensure the node has rejoined and resources are balanced.

## 6. Post-Patching Phase (Fleet Wide)
1. **Disable Maintenance Mode:** Turn off maintenance mode if enabled.
   - `pcs property set maintenance-mode=false`
2. **Resource Rebalance:** If resources did not fail back to preferred nodes, move them manually.
   - `pcs resource move <resource_id> <node_name>`
   - `pcs resource clear <resource_id>` (to remove the temporary constraint)
3. **Final Validation:** Run `ansible_pcs_postpatch_check` to confirm the entire fleet is synchronized.
4. **CIB Upgrade:** Once all cluster nodes are updated, run `ansible_pcs_cib_upgrade` on one of the nodes to ensure the Cluster Information Base is at the latest version.
5. **Completion Report:** Use `ansible_send_email` to distribute the final success/failure summary.

## 7. Contingency Plan
- **Pre-check Failure:** Do not proceed if `ansible_pcs_prepatch_check` fails.
- **Resource Migration Failure:** If a node stays in "Standby" but resources don't move, use `ansible_fix_pcs` before stopping the cluster.
- **VM Failure:** If a node fails to respond after reboot, use `ansible_vmware_reset` to perform a hard reset.
- **Quorum:** Never shut down more nodes than the cluster can handle while maintaining quorum.
