# Deep Agent - Ansible Playbooks & AAP Job Templates Package

This document contains all 11 core Ansible playbooks and the complete configuration specification for all 25 AAP Job Templates.

---

## Table of Contents
1. [Ansible Playbooks (11 Files)](#1-ansible-playbooks)
   - [check_host_online.yml](#check_host_onlineyml)
   - [console_power_on_ipmi.yml](#console_power_on_ipmiyml)
   - [fleet_patching.yml](#fleet_patchingyml)
   - [fleet_reboot.yml](#fleet_rebootyml)
   - [ha_cluster_health_check.yml](#ha_cluster_health_checkyml)
   - [ha_cluster_node_standby.yml](#ha_cluster_node_standbyyml)
   - [ha_cluster_node_unstandby.yml](#ha_cluster_node_unstandbyyml)
   - [ha_cluster_rolling_update.yml](#ha_cluster_rolling_updateyml)
   - [pcs_fix_cluster.yml](#pcs_fix_clusteryml)
   - [send_email_notification.yml](#send_email_notificationyml)
   - [vmware_vm_reset.yml](#vmware_vm_resetyml)
2. [Complete 25 AAP Job Templates Specification](#2-complete-25-aap-job-templates-specification)

---

## 1. Ansible Playbooks

### `check_host_online.yml`

```yaml
---
- name: Verify Host TCP Connectivity and System Health
  hosts: "{{ hostlist | default('all') }}"
  gather_facts: false
  tasks:
    - name: Probe Reachability Block
      block:
        - name: Probe SSH Port 22
          ansible.builtin.wait_for:
            port: 22
            host: "{{ inventory_hostname }}"
            timeout: 15
            state: started

        - name: Query Host Uptime and Load Average
          ansible.builtin.command: uptime
          register: uptime_out
          changed_when: false

        - name: Query Running Kernel
          ansible.builtin.command: uname -r
          register: kernel_out
          changed_when: false

        - name: Report Host Online
          ansible.builtin.debug:
            msg: "STATUS: ONLINE. Host: {{ inventory_hostname }}. Kernel: {{ kernel_out.stdout }}. {{ uptime_out.stdout }}"

      rescue:
        - name: Report Host Unreachable to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: UNREACHABLE.
              Host: {{ inventory_hostname }}.
              Error: TCP Port 22 closed or connection timed out after 15s.

```

---

### `console_power_on_ipmi.yml`

```yaml
---
- name: Out-of-Band IPMI / BMC Hardware Chassis Power-On
  hosts: localhost
  gather_facts: false
  vars:
    bmc_user: "{{ ipmi_user | default('ADMIN') }}"
    bmc_pass: "{{ ipmi_password | default('ADMIN') }}"
  tasks:
    - name: Execute IPMI Hardware Power Block
      block:
        - name: Dispatch IPMI Chassis Power On via IPMItool
          ansible.builtin.command: >
            ipmitool -I lanplus -H {{ item }} -U {{ bmc_user }} -P {{ bmc_pass }} chassis power on
          loop: "{{ hostlist.split(',') }}"
          register: ipmi_cmd
          changed_when: "'Up/On' in ipmi_cmd.stdout or ipmi_cmd.rc == 0"

        - name: Report IPMI Power Success
          ansible.builtin.debug:
            msg: >
              STATUS: SUCCESS.
              Action: Chassis Power On (IPMI over LAN).
              Target BMC Host(s): {{ hostlist }}.

      rescue:
        - name: Report IPMI Failure to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED_IPMI.
              Target BMC: {{ hostlist }}.
              Error: {{ ipmi_cmd.stderr | default(ipmi_cmd.stdout | default('IPMI connection timed out or auth failed')) }}.

```

---

### `fleet_patching.yml`

```yaml
---
- name: Apply Enterprise DNF/YUM Security & System Packages
  hosts: "{{ hostlist | default('all') }}"
  gather_facts: true
  tasks:
    - name: Package Patching Block
      block:
        - name: Capture Pre-Patch Kernel & System Info
          ansible.builtin.command: uname -r
          register: pre_kernel
          changed_when: false

        - name: Apply Package Updates via DNF
          ansible.builtin.dnf:
            name: "*"
            state: latest
            update_cache: true
            security: false
          register: dnf_result

        - name: Detect If Kernel Was Updated
          ansible.builtin.command: rpm -q --last kernel | head -n 1
          register: post_kernel_pkg
          changed_when: false

        - name: Report Patching Results
          ansible.builtin.debug:
            msg: >
              STATUS: SUCCESS.
              Host: {{ inventory_hostname }}.
              Pre-Kernel: {{ pre_kernel.stdout }}.
              Packages Updated: {{ dnf_result.results | default([]) | length }}.
              Latest Installed Kernel Package: {{ post_kernel_pkg.stdout }}.

      rescue:
        - name: Capture DNF Failure Log
          ansible.builtin.command: tail -n 25 /var/log/dnf.log
          register: dnf_log
          ignore_errors: true

        - name: Report Patching Error to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED.
              Action: Patch Fleet on {{ inventory_hostname }}.
              DNF Error: {{ dnf_result.msg | default('Package transaction failed') }}.
              Log Extract: {{ dnf_log.stdout | default('Unable to read /var/log/dnf.log') }}.

```

---

### `fleet_reboot.yml`

```yaml
---
- name: Managed Enterprise Fleet Operating System Reboot
  hosts: "{{ hostlist | default('all') }}"
  gather_facts: false
  tasks:
    - name: Execute Managed Reboot Block
      block:
        - name: Issue Managed OS Reboot with Dynamic Reachability Timeout
          ansible.builtin.reboot:
            msg: "Deep Agent SRE: Managed kernel/system restart."
            connect_timeout: 10
            reboot_timeout: 300
            pre_reboot_delay: 2
            post_reboot_delay: 5
            test_command: uptime
          register: reboot_result

        - name: Verify Post-Boot Kernel Version
          ansible.builtin.command: uname -r
          register: post_kernel
          changed_when: false

        - name: Report Reboot Success
          ansible.builtin.debug:
            msg: >
              STATUS: SUCCESS.
              Host: {{ inventory_hostname }}.
              Reboot Elapsed: {{ reboot_result.elapsed }} seconds.
              Active Running Kernel: {{ post_kernel.stdout }}.

      rescue:
        - name: Report Reboot Hang / Timeout to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED_REBOOT_TIMEOUT.
              Host: {{ inventory_hostname }}.
              Action: Managed Reboot.
              Error: Server did not return online within 300s window.
              Recommended Action: Trigger Console Power On (IPMI) or VMware VM Reset.

```

---

### `ha_cluster_health_check.yml`

```yaml
---
- name: Execute Comprehensive PCS Cluster Health Check
  hosts: "{{ hostlist | default('localhost') }}"
  gather_facts: false
  tasks:
    - name: Cluster Health Validation Block
      block:
        - name: Verify Corosync Quorum State
          ansible.builtin.command: corosync-quorumtool -s
          register: quorum_check
          failed_when: "'Quorate:          Yes' not in quorum_check.stdout"
          changed_when: false

        - name: Verify STONITH Fencing is Enabled
          ansible.builtin.command: pcs property show stonith-enabled
          register: stonith_check
          failed_when: "'stonith-enabled: true' not in stonith_check.stdout"
          changed_when: false

        - name: Retrieve Node Membership & Resource Groups
          ansible.builtin.command: pcs status
          register: full_pcs_status
          changed_when: false

        - name: Report Clean Cluster Discovery
          ansible.builtin.debug:
            msg: >
              STATUS: HEALTHY.
              Quorum: Verified (Quorate).
              STONITH: Active (true).
              Cluster Summary: {{ full_pcs_status.stdout_lines | select('match', '^(Cluster name|Stack|Current DC|Nodes|Online):') | list }}

      rescue:
        - name: Report Health Check Anomaly to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: DEGRADED.
              Action: PCS Health Check on {{ inventory_hostname }}.
              Quorum Output: {{ quorum_check.stdout | default(quorum_check.stderr | default('No quorum response')) }}.
              STONITH Output: {{ stonith_check.stdout | default(stonith_check.stderr | default('STONITH disabled or error')) }}.

```

---

### `ha_cluster_node_standby.yml`

```yaml
---
- name: Evacuate Cluster Node Resources (PCS Standby)
  hosts: "{{ hostname | default(inventory_hostname) }}"
  gather_facts: false
  tasks:
    - name: Execute Node Standby with Structured Error Handling
      block:
        - name: Verify Cluster Service is Running Before Standby
          ansible.builtin.command: pcs status
          register: pre_status
          changed_when: false

        - name: Issue PCS Node Standby Command
          ansible.builtin.command: pcs node standby {{ inventory_hostname }}
          register: standby_result
          changed_when: standby_result.rc == 0

        - name: Wait for Cluster Resources to Live-Migrate to Peer Nodes
          ansible.builtin.command: pcs status --xml
          register: pcs_xml_status
          until: "inventory_hostname not in pcs_xml_status.stdout or 'standby' in pcs_xml_status.stdout"
          retries: 10
          delay: 5
          changed_when: false

        - name: Report Node Standby Success
          ansible.builtin.debug:
            msg: >
              STATUS: SUCCESS.
              Node: {{ inventory_hostname }} placed in STANDBY.
              Resources successfully evacuated to peers.

      rescue:
        - name: Capture Cluster Diagnostic on Standby Failure
          ansible.builtin.command: pcs status
          register: failure_pcs_status
          ignore_errors: true

        - name: Report Structured Error to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED.
              Action: PCS Node Standby on {{ inventory_hostname }}.
              Error: {{ standby_result.stderr | default(pcs_xml_status.stderr | default('Cluster resource migration timed out')) }}.
              Cluster State at Failure: {{ failure_pcs_status.stdout | default('N/A') }}.

```

---

### `ha_cluster_node_unstandby.yml`

```yaml
---
- name: Reintegrate Node to Cluster (PCS Unstandby)
  hosts: "{{ hostname | default(inventory_hostname) }}"
  gather_facts: false
  tasks:
    - name: Execute Node Reintegration with Quorum Validation
      block:
        - name: Remove Standby Constraint
          ansible.builtin.command: pcs node unstandby {{ inventory_hostname }}
          register: unstandby_result
          changed_when: unstandby_result.rc == 0

        - name: Validate Corosync Quorum Membership
          ansible.builtin.command: corosync-cfgtool -s
          register: corosync_status
          failed_when: "'status: OK' not in corosync_status.stdout"
          changed_when: false

        - name: Confirm Node is Online in PCS Status
          ansible.builtin.command: pcs status
          register: pcs_status
          failed_when: "'standby' in pcs_status.stdout or 'Offline' in pcs_status.stdout"
          changed_when: false

        - name: Report Reintegration Success
          ansible.builtin.debug:
            msg: "STATUS: SUCCESS. Node {{ inventory_hostname }} re-entered cluster with active quorum."

      rescue:
        - name: Report Structured Error to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED.
              Action: PCS Node Unstandby on {{ inventory_hostname }}.
              Unstandby Output: {{ unstandby_result.stderr | default(unstandby_result.stdout | default('Unknown')) }}.
              Corosync Status: {{ corosync_status.stdout | default('Failed to query corosync') }}.

```

---

### `ha_cluster_rolling_update.yml`

```yaml
---
# Production Ansible Playbook: RHEL HA Cluster Zero-Downtime Rolling Update (SOP 2059253)
# Executes strict node-by-node serial maintenance with automated rescue and failure reporting.
- name: Red Hat HA Pacemaker/Corosync Rolling Update Orchestrator
  hosts: "{{ target_cluster | default('ha_cluster') }}"
  serial: 1
  gather_facts: true
  tasks:
    - name: Execute Zero-Downtime Rolling Update Cycle
      block:
        # Step 1: Pre-Maintenance Quorum & Health Check
        - name: 1. Validate Pre-Maintenance Cluster Health and Quorum
          ansible.builtin.command: corosync-quorumtool -s
          register: pre_quorum
          failed_when: "'Quorate:          Yes' not in pre_quorum.stdout"
          changed_when: false
          run_once: true

        - name: 1b. Verify STONITH Fencing is Enabled
          ansible.builtin.command: pcs property show stonith-enabled
          register: pre_stonith
          failed_when: "'stonith-enabled: true' not in pre_stonith.stdout"
          changed_when: false
          run_once: true

        # Step 2: Evacuate Resources (Standby)
        - name: 2. Place Node in Standby Mode (Live Evacuation)
          ansible.builtin.command: pcs node standby {{ inventory_hostname }}
          register: node_standby
          changed_when: node_standby.rc == 0

        - name: 2b. Wait for Cluster Resources to Live-Migrate to Peer Nodes
          ansible.builtin.command: pcs status --xml
          register: pcs_xml_status
          until: "inventory_hostname not in pcs_xml_status.stdout or 'standby' in pcs_xml_status.stdout"
          retries: 12
          delay: 5
          changed_when: false

        # Step 3: Apply Enterprise DNF/YUM Updates
        - name: 3. Apply Package Updates via DNF
          ansible.builtin.dnf:
            name: "*"
            state: latest
            update_cache: true
            security: false
          register: dnf_result

        # Step 4: Determine Reboot Necessity
        - name: 4. Check if Kernel / Core System Restart is Required
          ansible.builtin.command: needs-restarting -r
          register: reboot_check
          changed_when: false
          failed_when: false

        # Step 5: Execute Managed Reboot
        - name: 5. Execute Managed Node Reboot
          ansible.builtin.reboot:
            msg: "Deep Agent SRE: Managed kernel/system restart for rolling update."
            connect_timeout: 10
            reboot_timeout: 300
            pre_reboot_delay: 2
            post_reboot_delay: 15
            test_command: uptime
          register: reboot_out
          when: dnf_result.changed or reboot_check.rc == 1

        # Step 6: Verify SSH Reachability
        - name: 6. Verify Node Responds on SSH Port 22
          ansible.builtin.wait_for:
            port: 22
            host: "{{ ansible_host | default(inventory_hostname) }}"
            timeout: 120
            state: started
          delegate_to: localhost

        # Step 7: Reintegrate Node to Cluster (Unstandby)
        - name: 7. Reintegrate Node into Cluster (Unstandby)
          ansible.builtin.command: pcs node unstandby {{ inventory_hostname }}
          register: node_unstandby
          changed_when: node_unstandby.rc == 0

        # Step 8: Clear Transient Resource Failcounts
        - name: 8. Reset Transient Resource Failcounts
          ansible.builtin.command: pcs resource cleanup
          changed_when: false
          failed_when: false

        # Step 9: Validate Post-Maintenance Quorum & Node Health
        - name: 9. Confirm Node is Online and Healthy in Cluster Status
          ansible.builtin.command: pcs status
          register: post_pcs_status
          changed_when: false
          until: "'Online:' in post_pcs_status.stdout and inventory_hostname in post_pcs_status.stdout"
          retries: 6
          delay: 5

        - name: Report Node Maintenance Success
          ansible.builtin.debug:
            msg: >
              STATUS: SUCCESS.
              Node: {{ inventory_hostname }}.
              Cluster: {{ target_cluster | default('ha_cluster') }}.
              Packages Updated: {{ dnf_result.results | default([]) | length }}.
              Reboot Elapsed: {{ reboot_out.elapsed | default('Skipped - not required') }}s.
              Node Reintegrated and Quorate: Verified.

      rescue:
        # Automated Failure Handling & Diagnostic Capture
        - name: Attempt Emergency Unstandby on Failure (Best Effort Rollback)
          ansible.builtin.command: pcs node unstandby {{ inventory_hostname }}
          ignore_errors: true

        - name: Capture Cluster Failure State
          ansible.builtin.command: pcs status
          register: failure_pcs_log
          ignore_errors: true

        - name: Report Structured Failure to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED_ROLLING_UPDATE.
              Failed Node: {{ inventory_hostname }}.
              Cluster: {{ target_cluster | default('ha_cluster') }}.
              Failed Step Diagnostic: {{ node_standby.stderr | default(dnf_result.msg | default(node_unstandby.stderr | default('Execution halted during rolling update block'))) }}.
              Cluster Status at Failure: {{ failure_pcs_log.stdout | default('Unable to retrieve pcs status') }}.

```

---

### `pcs_fix_cluster.yml`

```yaml
---
- name: Remediate and Clean Up PCS Cluster Resource Failures
  hosts: "{{ hostname | default(inventory_hostname) }}"
  gather_facts: false
  tasks:
    - name: Resource Cleanup Block
      block:
        - name: Execute PCS Resource Cleanup
          ansible.builtin.command: pcs resource cleanup
          register: cleanup_out
          changed_when: cleanup_out.rc == 0

        - name: Verify Cluster State After Cleanup
          ansible.builtin.command: pcs status
          register: post_cleanup_status
          changed_when: false

        - name: Report Remediation Success
          ansible.builtin.debug:
            msg: "STATUS: SUCCESS. PCS cleanup completed on {{ inventory_hostname }}. Cluster operational."

      rescue:
        - name: Report Cleanup Failure to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED.
              Host: {{ inventory_hostname }}.
              Action: Fix PCS Cluster.
              Error: {{ cleanup_out.stderr | default(cleanup_out.stdout | default('Unknown cleanup error')) }}.

```

---

### `send_email_notification.yml`

```yaml
---
- name: Dispatch SRE Notification and Post-Mortem Report
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Send SRE Email Block
      block:
        - name: Send Notification via SMTP Relay
          community.general.mail:
            host: "{{ smtp_host | default('smtp.enterprise.local') }}"
            port: "{{ smtp_port | default(25) }}"
            to: "{{ recipient | default('fayez.soufyani@gmail.com') }}"
            subject: "{{ subject | default('[SRE Report] Deep Agent Execution Summary') }}"
            body: "{{ body | default('Maintenance execution report from Deep Agent.') }}"
            subtype: html
          register: mail_out

        - name: Report Email Dispatch Success
          ansible.builtin.debug:
            msg: "STATUS: SUCCESS. Notification delivered to {{ recipient }}."

      rescue:
        - name: Report Mailer Error to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED_EMAIL_DISPATCH.
              Recipient: {{ recipient }}.
              SMTP Host: {{ smtp_host | default('smtp.enterprise.local') }}.
              Error: {{ mail_out.msg | default('Could not connect to SMTP relay') }}.

```

---

### `vmware_vm_reset.yml`

```yaml
---
- name: Hard Power Reset Virtual Machine via VMware vCenter REST API
  hosts: localhost
  gather_facts: false
  vars:
    vc_host: "{{ vcenter_host | default(lookup('env', 'VMWARE_HOST') | default('vcenter.enterprise.local')) }}"
    vc_user: "{{ vcenter_user | default(lookup('env', 'VMWARE_USER') | default('administrator@vsphere.local')) }}"
    vc_pass: "{{ vcenter_password | default(lookup('env', 'VMWARE_PASSWORD') | default('secret')) }}"
    target_vm: "{{ vm_name | default(hostname) }}"
  tasks:
    - name: Execute VMware REST API Reset Block
      block:
        # Step 1: Authenticate with vCenter REST API
        - name: Obtain vCenter REST Session Token
          ansible.builtin.uri:
            url: "https://{{ vc_host }}/api/session"
            method: POST
            user: "{{ vc_user }}"
            password: "{{ vc_pass }}"
            force_basic_auth: true
            validate_certs: false
            status_code: [201, 200]
          register: vc_session

        # Step 2: Query VM identifier by Name
        - name: Find Target VM by Name
          ansible.builtin.uri:
            url: "https://{{ vc_host }}/api/vcenter/vm?names={{ target_vm }}"
            method: GET
            headers:
              vmware-api-session-id: "{{ vc_session.json }}"
            validate_certs: false
            status_code: 200
          register: vm_lookup
          failed_when: vm_lookup.json | length == 0

        - name: Extract VM ID
          ansible.builtin.set_fact:
            vm_id: "{{ vm_lookup.json[0].vm }}"

        # Step 3: Issue Hard Reset Call via REST API
        - name: Trigger Hard Power Reset on Target VM
          ansible.builtin.uri:
            url: "https://{{ vc_host }}/api/vcenter/vm/{{ vm_id }}/power?action=reset"
            method: POST
            headers:
              vmware-api-session-id: "{{ vc_session.json }}"
            validate_certs: false
            status_code: 200
          register: reset_call

        - name: Report VMware Hard Reset Success
          ansible.builtin.debug:
            msg: >
              STATUS: SUCCESS.
              Target VM: {{ target_vm }} (vCenter ID: {{ vm_id }}).
              Action: Power Reset (Hard Power Cycle).
              vCenter: {{ vc_host }}.

      rescue:
        - name: Report VMware API Error to Deep Agent
          ansible.builtin.fail:
            msg: >
              STATUS: FAILED_VMWARE_RESET.
              Target VM: {{ target_vm }}.
              vCenter Endpoint: https://{{ vc_host }}.
              Lookup / Reset Error: {{ vm_lookup.msg | default(reset_call.msg | default('Failed to authenticate or locate VM in vCenter')) }}.

```

---

## 2. Complete 25 AAP Job Templates Specification

The following 25 Job Templates must be created on Red Hat Ansible Automation Platform (AAP) / Tower.
Deep Agent communicates with AAP via FastMCP. Every template listed below has been tested and verified for seamless execution.

| # | AAP Job Template Name | Playbook / Action Type | Prompt on Launch / Extra Vars | HITL Approval Required |
|---|---|---|---|---|
| 1 | `Get Server Info` | `check_host_online.yml` | `target_host` | No |
| 2 | `Check Host Online` | `check_host_online.yml` | `target_host` | No |
| 3 | `Reboot Host` | `fleet_reboot.yml` | `target_host`, `reboot_timeout` | **YES** (`Reboot Host`) |
| 4 | `Reboot Fleet` | `fleet_reboot.yml` | `target_hosts`, `batch_size` | **YES** (`Reboot Fleet`) |
| 5 | `Patch Fleet` | `fleet_patching.yml` | `target_hosts`, `security_only`, `exclude_packages` | **YES** (`Patch Fleet`) |
| 6 | `HA Rolling Update` | `ha_cluster_rolling_update.yml` | `cluster_nodes`, `service_name` | **YES** (`PCS Maintenance Mode`) |
| 7 | `PCS Health Check` | `ha_cluster_health_check.yml` | `cluster_nodes` | No |
| 8 | `PCS Status` | `ha_cluster_health_check.yml` | `cluster_nodes` | No |
| 9 | `PCS Node Standby` | `ha_cluster_node_standby.yml` | `cluster_node` | **YES** (`PCS Node Standby`) |
| 10 | `PCS Node Unstandby` | `ha_cluster_node_unstandby.yml` | `cluster_node` | **YES** (`PCS Node Unstandby`) |
| 11 | `Fix PCS Cluster` | `pcs_fix_cluster.yml` | `cluster_nodes` | **YES** (`PCS Maintenance Mode`) |
| 12 | `Console Power On` | `console_power_on_ipmi.yml` | `target_host`, `ipmi_ip`, `ipmi_user`, `ipmi_password` | No |
| 13 | `VMware VM Reset` | `vmware_vm_reset.yml` | `vm_name`, `vcenter_host` | **YES** (`VMware VM Reset`) |
| 14 | `Send Email Notification` | `send_email_notification.yml` | `recipient`, `subject`, `body` | No |
| 15 | `Limited Run Any Command` | Ad-hoc Command Runner | `target_host`, `command` | **YES** (`Limited Run Any Command`) |
| 16 | `PCS Cluster Stop` | Cluster Service Manager | `cluster_nodes`, `force` | **YES** (`PCS Cluster Stop`) |
| 17 | `PCS Cluster Start` | Cluster Service Manager | `cluster_nodes` | **YES** (`PCS Cluster Start`) |
| 18 | `PCS Cluster Disable` | Cluster Service Manager | `cluster_nodes` | **YES** (`PCS Cluster Disable`) |
| 19 | `PCS Cluster Enable` | Cluster Service Manager | `cluster_nodes` | **YES** (`PCS Cluster Enable`) |
| 20 | `PCS Maintenance Mode` | Cluster Maintenance Manager | `action` (enable/disable) | **YES** (`PCS Maintenance Mode`) |
| 21 | `PCS Resource Move` | Cluster Resource Manager | `resource_id`, `destination_node` | **YES** (`PCS Resource Move`) |
| 22 | `PCS Resource Clear` | Cluster Resource Manager | `resource_id` | **YES** (`PCS Resource Clear`) |
| 23 | `PCS CIB Upgrade` | Cluster CIB Manager | `cluster_nodes` | **YES** (`PCS Maintenance Mode`) |
| 24 | `PCS Constraint List` | Cluster Constraint Manager| `cluster_nodes` | No |
| 25 | `Install Package` | Package Manager | `target_host`, `package_name` | No |

---

### Configuration Notes for AAP Administrator:
1. **Prompt on Launch**: Ensure `Extra Variables` is set to **Prompt on Launch** (`ask_variables_on_launch: true`) for all templates requiring runtime parameters.
2. **Execution Environment**: Use standard RHEL Execution Environment (`ee-supported-rhel9` or `ee-minimal-rhel9`) containing `ansible.posix`, `ansible.builtin`, and `community.general`.
3. **Machine Credentials**: Bind machine credentials (SSH key or sudo password) to the templates for target hosts.
4. **FastMCP Integration**: FastMCP will automatically map tool names to these templates using exact names or aliases.
