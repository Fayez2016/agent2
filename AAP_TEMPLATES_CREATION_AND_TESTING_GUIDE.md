# AAP Job Templates Creation & Testing Guide

This document details the Ansible Automation Platform (AAP) Job Templates to create, their underlying playbook mappings, and the exact generic testing prompts for each template.

---

## 1. Complete Template Mapping Table

The system utilizes **11 core playbooks** to power the operational templates.

| # | AAP Job Template Name | Underlying Playbook | Prompt on Launch Extra Vars | HITL Approval Required? |
|---|---|---|---|---|
| 1 | **`Get Server Info`** *(Created)* | `check_host_online.yml` | `hostlist` | No |
| 2 | **`Check Host Online`** | `check_host_online.yml` | `hostlist` | No |
| 3 | **`PCS Health Check`** | `ha_cluster_health_check.yml` | `hostlist` | No |
| 4 | **`PCS Status`** | `ha_cluster_health_check.yml` | `hostlist` | No |
| 5 | **`PCS Node Standby`** | `ha_cluster_node_standby.yml` | `hostlist` | **YES** (`PCS Node Standby`) |
| 6 | **`PCS Node Unstandby`** | `ha_cluster_node_unstandby.yml` | `hostlist` | **YES** (`PCS Node Unstandby`) |
| 7 | **`Patch Fleet`** | `fleet_patching.yml` | `hostlist` | **YES** (`Patch Fleet`) |
| 8 | **`Reboot Host`** | `fleet_reboot.yml` | `hostname` (or `hostlist`) | **YES** (`Reboot Host`) |
| 9 | **`Reboot Fleet`** | `fleet_reboot.yml` | `hostlist` | **YES** (`Reboot Fleet`) |
| 10 | **`Fix PCS Cluster`** | `pcs_fix_cluster.yml` | `hostname` | **YES** (`PCS Maintenance Mode`) |
| 11 | **`Limited Run Any Command`** | `check_host_online.yml` *(or command runner)* | `hostlist`, `agent_comand` | **YES** (`Limited Run Any Command`) |
| 12 | **`HA Rolling Update`** | `ha_cluster_rolling_update.yml` | `cluster_nodes`, `service_name` | **YES** (`PCS Maintenance Mode`) |
| 13 | **`Send Email Notification`** | `send_email_notification.yml` | `recipient`, `subject`, `body` | No |
| 14 | **`Console Power On`** | `console_power_on_ipmi.yml` | `hostlist`, `ipmi_user`, `ipmi_password` | No |
| 15 | **`VMware VM Reset`** | `vmware_vm_reset.yml` | `vm_name`, `vcenter_host` | **YES** (`VMware VM Reset`) |

---

## 2. Priority Phase 1: Core Cluster & Fleet (Create These First)

### Template 2: `Check Host Online`
* **Playbook:** `check_host_online.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`
* **HITL Required:** No
* **How to Test with Agent:**
  > *"Check if node-primary is online"*

---

### Template 3: `PCS Health Check`
* **Playbook:** `ha_cluster_health_check.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`
* **HITL Required:** No
* **How to Test with Agent:**
  > *"Run PCS health check on cluster-01"*

---

### Template 4: `PCS Status`
* **Playbook:** `ha_cluster_health_check.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`
* **HITL Required:** No
* **How to Test with Agent:**
  > *"Show PCS cluster status for cluster-01"*

---

### Template 5: `PCS Node Standby`
* **Playbook:** `ha_cluster_node_standby.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`
* **HITL Required:** **YES** (`PCS Node Standby`)
* **How to Test with Agent:**
  > *"Put cluster node node-primary into standby"*
  *(Agent will pause and request HITL authorization -> Click Approve in Web UI -> Standby executes)*

---

### Template 6: `PCS Node Unstandby`
* **Playbook:** `ha_cluster_node_unstandby.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`
* **HITL Required:** **YES** (`PCS Node Unstandby`)
* **How to Test with Agent:**
  > *"Reintegrate cluster node node-primary by unstandbying it"*
  *(Agent will pause and request HITL authorization -> Click Approve in Web UI -> Node is rejoined)*

---

### Template 7: `Patch Fleet`
* **Playbook:** `fleet_patching.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`
* **HITL Required:** **YES** (`Patch Fleet`)
* **How to Test with Agent:**
  > *"Apply security patches to host node-primary"*

---

### Template 8: `Reboot Host`
* **Playbook:** `fleet_reboot.yml`
* **Extra Variables (Prompt on Launch):** `hostname` (or `hostlist`)
* **HITL Required:** **YES** (`Reboot Host`)
* **How to Test with Agent:**
  > *"Reboot server node-primary"*

---

### Template 11: `Limited Run Any Command`
* **Playbook:** Uses ad-hoc command or `check_host_online.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`, `agent_comand`
* **HITL Required:** **YES** (`Limited Run Any Command`)
* **How to Test with Agent:**
  > *"Run command 'uptime' on node-primary"*

---

## 3. Priority Phase 2: Notifications, Recovery & Orchestration

### Template 10: `Fix PCS Cluster`
* **Playbook:** `pcs_fix_cluster.yml`
* **Extra Variables (Prompt on Launch):** `hostname`
* **HITL Required:** **YES** (`PCS Maintenance Mode`)
* **How to Test with Agent:**
  > *"Fix PCS cluster failures on node-primary"*

---

### Template 13: `Send Email Notification`
* **Playbook:** `send_email_notification.yml`
* **Extra Variables (Prompt on Launch):** `recipient`, `subject`, `body`
* **HITL Required:** No
* **How to Test with Agent:**
  > *"Send an email notification to user@enterprise.local with subject 'AAP Test' and body 'Health check completed'"*

---

### Template 14: `Console Power On` (IPMI)
* **Playbook:** `console_power_on_ipmi.yml`
* **Extra Variables (Prompt on Launch):** `hostlist`
* **HITL Required:** No
* **How to Test with Agent:**
  > *"Power on console via IPMI for node-primary"*

---

### Template 15: `VMware VM Reset`
* **Playbook:** `vmware_vm_reset.yml`
* **Extra Variables (Prompt on Launch):** `vm_name`, `vcenter_host`
* **HITL Required:** **YES** (`VMware VM Reset`)
* **How to Test with Agent:**
  > *"Reset virtual machine node-primary on vcenter.enterprise.local"*

---

### Template 12: `HA Rolling Update` (End-to-End SOP)
* **Playbook:** `ha_cluster_rolling_update.yml`
* **Extra Variables (Prompt on Launch):** `cluster_nodes`, `service_name`
* **HITL Required:** **YES** (`PCS Maintenance Mode`)
* **How to Test with Agent:**
  > *"Execute zero-downtime rolling update on cluster-01"*

---

## 4. Key Configuration Rules for AAP Admin

1. **Prompt on Launch**: Ensure **Extra Variables** has `Prompt on launch` enabled (`ask_variables_on_launch: true`) on each template so parameters can be passed dynamically.
2. **Execution Environment**: Attach standard RHEL EE (`ee-supported-rhel9` or `ee-minimal-rhel9`).
3. **Machine Credentials**: Associate the appropriate SSH Machine Credential with sudo privileges to target hosts.
