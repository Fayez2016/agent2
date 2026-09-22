# Complete End-to-End Test Suite for All AAP Job Templates

This guide provides the complete test matrix for all AAP Job Templates. For each template, the exact user prompt, underlying template name, required parameters, HITL authorization requirements, and expected outcomes are specified.

All identifiers in this guide use generic references (`node-primary`, `cluster-01`, `enterprise.local`). Replace them with your local host or cluster names during testing.

---

## Complete Test Matrix

| # | Operational Category | AAP Job Template Name | HITL Required? | Exact Test Prompt |
|:---:|---|---|:---:|---|
| 1 | Host Visibility | `Get Server Info` | No | `Check server info for node-primary` |
| 2 | Host Reachability | `Check Host Online` | No | `Check if node-primary is online` |
| 3 | Command Execution | `Limited Run Any Command` | **YES** | `Run command 'uptime' on node-primary` |
| 4 | Cluster Health | `PCS Health Check` | No | `Run PCS health check on cluster-01` |
| 5 | Cluster Status | `PCS Status` | No | `Show PCS status for cluster-01` |
| 6 | Cluster Evacuation | `PCS Node Standby` | **YES** | `Put cluster node node-primary into standby` |
| 7 | Cluster Reintegration | `PCS Node Unstandby` | **YES** | `Take cluster node node-primary out of standby` |
| 8 | Cluster Remediation | `Fix PCS Cluster` | **YES** | `Fix PCS cluster failures on node-primary` |
| 9 | Software Maintenance | `Patch Fleet` | **YES** | `Apply security patches to host node-primary` |
| 10 | Single Host Reboot | `Reboot Host` | **YES** | `Reboot server node-primary` |
| 11 | Fleet Reboot | `Reboot Fleet` | **YES** | `Reboot fleet node-primary,node-secondary` |
| 12 | End-to-End Orchestration | `HA Rolling Update` | **YES** | `Execute zero-downtime rolling update on cluster-01` |
| 13 | Notification Relay | `Send Email Notification` | No | `Send an email notification to operator@enterprise.local with subject 'Fleet Maintenance' and body 'Completed.'` |
| 14 | Hardware Recovery | `Console Power On` | No | `Power on console via IPMI for node-primary` |
| 15 | Virtualization Reset | `VMware VM Reset` | **YES** | `Reset virtual machine node-primary on vcenter.enterprise.local` |
| 16 | Cluster Stop | `PCS Cluster Stop` | **YES** | `Stop cluster services on node-primary` |
| 17 | Cluster Start | `PCS Cluster Start` | **YES** | `Start cluster services on node-primary` |
| 18 | Cluster Disable | `PCS Cluster Disable` | **YES** | `Disable cluster services on node-primary` |
| 19 | Cluster Enable` | `PCS Cluster Enable` | **YES** | `Enable cluster services on node-primary` |
| 20 | Cluster Maintenance | `PCS Maintenance Mode` | **YES** | `Enable cluster maintenance mode on cluster-01` |
| 21 | Resource Migration | `PCS Resource Move` | **YES** | `Move resource res_ip to node-secondary` |
| 22 | Constraint Clearing | `PCS Resource Clear` | **YES** | `Clear location constraints for resource res_ip` |
| 23 | CIB Schema Upgrade | `PCS CIB Upgrade` | **YES** | `Upgrade CIB schema on cluster-01` |
| 24 | Constraint Inspection | `PCS Constraint List` | No | `List cluster constraints on cluster-01` |
| 25 | Package Management | `Install Package` | No | `Install package htop on node-primary` |

---

## Detailed Test Procedures

### Test 1: Host Facts Query (`Get Server Info`)
* **Prompt:** `Check server info for node-primary`
* **Triggered Template:** `Get Server Info`
* **Parameters Passed:** `hostlist: node-primary`
* **HITL Approval:** None (Read-only)
* **Expected Outcome:** Returns uptime, kernel release, and reachability.

---

### Test 2: TCP Reachability Probe (`Check Host Online`)
* **Prompt:** `Check if node-primary is online`
* **Triggered Template:** `Check Host Online`
* **Parameters Passed:** `hostlist: node-primary`
* **HITL Approval:** None (Read-only)
* **Expected Outcome:** Tests SSH Port 22 connectivity and returns `STATUS: ONLINE`.

---

### Test 3: Ad-hoc Command Runner (`Limited Run Any Command`)
* **Prompt:** `Run command 'uptime' on node-primary`
* **Triggered Template:** `Limited Run Any Command`
* **Parameters Passed:** `hostlist: node-primary`, `command: uptime`
* **HITL Approval:** **YES** (`Limited Run Any Command`)
* **Execution Steps:**
  1. Agent pauses and posts approval request in the Web UI.
  2. Click **Approve** in the Web UI.
  3. AAP runs `run_shell_command.yml` and outputs the command stdout.

---

### Test 4: Cluster Health & Discovery (`PCS Health Check`)
* **Prompt:** `Run PCS health check on cluster-01`
* **Triggered Template:** `PCS Health Check`
* **Parameters Passed:** `hostlist: cluster-01`
* **HITL Approval:** None (Read-only)
* **Expected Outcome:** Verifies Corosync Quorum state, STONITH configuration, and active node membership.

---

### Test 5: Cluster Live Status (`PCS Status`)
* **Prompt:** `Show PCS status for cluster-01`
* **Triggered Template:** `PCS Status`
* **Parameters Passed:** `hostlist: cluster-01`
* **HITL Approval:** None (Read-only)
* **Expected Outcome:** Displays Pacemaker resource allocations and cluster state.

---

### Test 6: Node Standby Evacuation (`PCS Node Standby`)
* **Prompt:** `Put cluster node node-primary into standby`
* **Triggered Template:** `PCS Node Standby`
* **Parameters Passed:** `hostlist: node-primary`
* **HITL Approval:** **YES** (`PCS Node Standby`)
* **Expected Outcome:** Node enters Standby; active cluster resources migrate to peer node without service disruption.

---

### Test 7: Node Reintegration (`PCS Node Unstandby`)
* **Prompt:** `Take cluster node node-primary out of standby`
* **Triggered Template:** `PCS Node Unstandby`
* **Parameters Passed:** `hostlist: node-primary`
* **HITL Approval:** **YES** (`PCS Node Unstandby`)
* **Expected Outcome:** Node transitions from Standby to Online and re-joins cluster quorum.

---

### Test 8: Cluster Failure Remediation (`Fix PCS Cluster`)
* **Prompt:** `Fix PCS cluster failures on node-primary`
* **Triggered Template:** `Fix PCS Cluster`
* **Parameters Passed:** `hostname: node-primary`
* **HITL Approval:** **YES** (`PCS Maintenance Mode`)
* **Expected Outcome:** Cleans up failed resource states and resets fail counts.

---

### Test 9: Patch Management (`Patch Fleet`)
* **Prompt:** `Apply security patches to host node-primary`
* **Triggered Template:** `Patch Fleet`
* **Parameters Passed:** `hostlist: node-primary`
* **HITL Approval:** **YES** (`Patch Fleet`)
* **Expected Outcome:** Applies available security/kernel updates via DNF without rebooting.

---

### Test 10: Managed Reboot (`Reboot Host`)
* **Prompt:** `Reboot server node-primary`
* **Triggered Template:** `Reboot Host`
* **Parameters Passed:** `hostname: node-primary`
* **HITL Approval:** **YES** (`Reboot Host`)
* **Expected Outcome:** Issues controlled system reboot and verifies SSH port 22 recovery upon boot.

---

### Test 11: Fleet Reboot (`Reboot Fleet`)
* **Prompt:** `Reboot fleet node-primary,node-secondary`
* **Triggered Template:** `Reboot Fleet`
* **Parameters Passed:** `hostlist: node-primary,node-secondary`
* **HITL Approval:** **YES** (`Reboot Fleet`)
* **Expected Outcome:** Reboots multiple hosts sequentially or in batches.

---

### Test 12: Zero-Downtime Rolling SOP (`HA Rolling Update`)
* **Prompt:** `Execute zero-downtime rolling update on cluster-01`
* **Triggered Template:** `HA Rolling Update`
* **Parameters Passed:** `cluster_nodes: node-primary,node-secondary`, `service_name: cluster-svc`
* **HITL Approval:** **YES** (`PCS Maintenance Mode`)
* **Expected Outcome:** Executes complete multi-stage rolling maintenance across Wave 1 and Wave 2 with quorum preservation.

---

### Test 13: Notification Dispatch (`Send Email Notification`)
* **Prompt:** `Send an email notification to operator@enterprise.local with subject 'Fleet Maintenance' and body 'Verification run completed.'`
* **Triggered Template:** `Send Email Notification`
* **Parameters Passed:** `recipient: operator@enterprise.local`, `subject: Fleet Maintenance`, `body: Verification run completed.`
* **HITL Approval:** None
* **Expected Outcome:** Delivers notification via enterprise SMTP relay.

---

### Test 14: Out-of-Band IPMI Recovery (`Console Power On`)
* **Prompt:** `Power on console via IPMI for node-primary`
* **Triggered Template:** `Console Power On`
* **Parameters Passed:** `hostlist: node-primary`
* **HITL Approval:** None (or high-risk depending on mode)
* **Expected Outcome:** Issues out-of-band IPMI chassis power-on command to target BMC.

---

### Test 15: Virtual Machine Hard Reset (`VMware VM Reset`)
* **Prompt:** `Reset virtual machine node-primary on vcenter.enterprise.local`
* **Triggered Template:** `VMware VM Reset`
* **Parameters Passed:** `vm_name: node-primary`, `vcenter_host: vcenter.enterprise.local`
* **HITL Approval:** **YES** (`VMware VM Reset`)
* **Expected Outcome:** Issues hard power reset via VMware vCenter REST API.
