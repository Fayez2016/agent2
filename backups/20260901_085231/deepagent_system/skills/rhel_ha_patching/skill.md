---
name: rhel-ha-patching
description: Standard Operating Procedure for executing zero-downtime rolling updates on Red Hat Enterprise Linux High Availability (Pacemaker/Corosync) clusters per Red Hat Solution SOP 2059253.
---

# Red Hat HA Cluster Rolling Update Procedure (SOP 2059253)

This skill provides step-by-step guidance for performing a zero-downtime rolling update (DNF packages, kernel updates, system reboots) across multi-cluster Red Hat HA Pacemaker/Corosync environments.

## Execution Rules & Dynamic Discovery
1. **Dynamic Topology Discovery**: DO NOT assume or hardcode node names. Call `ansible_pcs_health_check` on the cluster targets. Parse the stdout to extract the active members and resource locations (e.g. `Active members: nodeA, nodeB`).
2. **Dynamic Wave Partitioning**:
   - **Wave 1 (Active Nodes)**: All primary members hosting active resource groups.
   - **Wave 2 (Peer Nodes)**: All secondary peer members.
3. **Quorum Preservation**: NEVER patch or reboot Wave 1 and Wave 2 simultaneously. Complete Wave 1 across all clusters first, ensure full reintegration and quorum balance, and only then proceed to Wave 2.
4. **Planning & Live Tracking**: Call `write_todos` to create the operational checklist tracking both waves and update each stage as it progresses.
5. **Handling Anomalies**: If any node fails SSH connection check (`online: false`), invoke `ansible_console_power_on` (IPMI recovery) and re-verify before proceeding.

## Step-by-Step SOP Stages

### Stage 1: Pre-Maintenance Health Check & Dynamic Topology Discovery
- Tool: `ansible_pcs_health_check`
- Arguments: `{"hostlist": "<cluster-names>"}`
- Description: Validate that all clusters are QUORATE, STONITH is enabled, and discover all member node names. Initialize `write_todos` with discovered targets.

### Stage 2: Evacuate Node 1 (Standby)
- Tool: `ansible_pcs_node_standby`
- Arguments: `{"hostlist": "<comma-separated-node1-names>"}`
- Description: Place Node 1 into standby. Cluster resources will live-migrate cleanly to Node 2 without service disruption.

### Stage 3: Apply DNF Package Updates on Node 1
- Tool: `ansible_patch_fleet`
- Arguments: `{"hostlist": "<comma-separated-node1-names>"}`
- Description: Apply security, kernel, and enhancement packages via DNF. Check output for any package conflict errors.

### Stage 4: Issue Managed Reboot on Node 1
- Tool: `ansible_reboot_fleet`
- Arguments: `{"hostlist": "<comma-separated-node1-names>"}`
- Description: Issue managed operating system reboots across all Node 1 targets.

### Stage 5: Verify Node 1 Online & Uptime
- Tool: `ansible_check_host_online`
- Arguments: `{"hostlist": "<comma-separated-node1-names>"}`
- Description: Probe SSH TCP Port 22 and validate kernel uptime.

### Stage 6: Out-of-Band IPMI Recovery (Conditional)
- Tool: `ansible_console_power_on`
- Arguments: `{"hostlist": "<comma-separated-hung-node-names>"}`
- Description: If any node timed out or encountered a soft-hang during reboot, immediately trigger out-of-band IPMI hardware power cycling, followed by `ansible_check_host_online` re-verification.

### Stage 7: Reintegrate Node 1 (Unstandby)
- Tool: `ansible_pcs_node_unstandby`
- Arguments: `{"hostlist": "<comma-separated-node1-names>"}`
- Description: Bring Node 1 back online in the cluster. Validate quorum stability.

### Stage 8: Repeat Rolling Cycle for Node 2
- Repeat Stages 2 through 7 for Node 2 targets across all clusters:
  1. `ansible_pcs_node_standby` on Node 2.
  2. `ansible_patch_fleet` on Node 2.
  3. `ansible_reboot_fleet` on Node 2.
  4. `ansible_check_host_online` on Node 2.
  5. `ansible_console_power_on` if any Node 2 experienced reboot soft-hang.
  6. `ansible_pcs_node_unstandby` on Node 2.

### Stage 9: Final Post-Maintenance Cluster Health Verification
- Tool: `ansible_pcs_status`
- Arguments: `{"hostlist": "<comma-separated-cluster-names>"}`
- Description: Confirm all nodes are unstandby, quorum is healthy, and resource groups are balanced.

### Stage 10: Dispatch Automated SRE Report Email
- Tool: `ansible_send_email`
- Arguments: `{"recipient": "admin@enterprise.local", "subject": "[SRE Report] HA Multi-Cluster Rolling Update Completed", "body": "<summary>"}`
- Description: Send final post-mortem report to the SRE admin team.
