---
name: rhel-ha-patching
description: Standard Operating Procedure for executing zero-downtime rolling updates on Red Hat Enterprise Linux High Availability (Pacemaker/Corosync) clusters per Red Hat Solution SOP 2059253.
---

# Red Hat HA Cluster Rolling Update Procedure (SOP 2059253)

This skill provides step-by-step guidance for performing a zero-downtime rolling update (DNF packages, kernel updates, system reboots) across multi-cluster Red Hat HA Pacemaker/Corosync environments.

## Execution Rules & Planning
1. **Always Use Planning Tool**: Immediately call `write_todos` to initialize and track the SOP checklist across all target clusters.
2. **Batch Processing**: When multiple clusters are targeted, execute each stage in batches across all clusters simultaneously to optimize maintenance windows.
3. **Quorum Preservation**: NEVER reboot or patch Node 1 and Node 2 simultaneously. Complete Node 1 across all clusters first, ensure full cluster reintegration, and only then proceed to Node 2.

## Step-by-Step SOP Stages

### Stage 1: Pre-Maintenance Health Check & Resource Discovery
- Tool: `ansible_pcs_health_check`
- Arguments: `{"hostlist": "<comma-separated-cluster-or-host-names>"}`
- Description: Validate that all cluster nodes are online, Corosync quorum is balanced, and STONITH fence devices are operational. Record any existing resource failures.

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
