---
name: rhel-diagnostics
description: Standard Operating Procedure for Red Hat Enterprise Linux diagnostics, Pacemaker cluster quorum verification, systemd service state inspections, and kernel crash dump analysis.
---

# RHEL Cluster & System Diagnostics Procedure

This skill provides step-by-step guidance for diagnosing degraded cluster resources, investigating system service failures, and evaluating infrastructure health prior to maintenance.

## Execution Rules & Planning
1. **Initialize Planning**: Use `write_todos` to log the diagnostic phases for targeted nodes or clusters.
2. **Non-Disruptive Execution**: All diagnostic checks are read-only inspection queries and do not alter cluster state or cause downtime.

## Step-by-Step SOP Stages

### Stage 1: Pacemaker Cluster Health Check
- Tool: `ansible_pcs_health_check`
- Arguments: `{"hostlist": "<target-hosts-or-clusters>"}`
- Description: Query cluster quorum, resource locations, failcounts, and STONITH fence device status.

### Stage 2: Detailed Cluster Status Inspection
- Tool: `ansible_pcs_status`
- Arguments: `{"hostlist": "<target-hosts-or-clusters>"}`
- Description: Inspect active nodes, standby status, and configured resource groups.

### Stage 3: Summary Synthesis
- Analyze findings and present an actionable diagnostic assessment including:
  - Node online/standby counts.
  - Resource group allocation across cluster nodes.
  - Specific error messages and recommended remediation steps.
