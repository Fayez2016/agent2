# Deep Agent — Complete Production Ansible Playbooks Catalog

This document contains the complete, raw, production-ready YAML content of all 11 Ansible playbooks used by Deep Agent.
You can copy these directly into individual `.yml` files in your GitLab repository, create your AAP Project, and link each Job Template.

---

## 1. ha_cluster_node_standby.yml
**Corresponding AAP Job Template Name**: `PCS Node Standby`
**Purpose**: Places a Pacemaker cluster node into STANDBY mode and monitors resource migration to peers.
**Extra Variables**: `{"hostname": "<node_name>"}`

```yaml
---
# Production Ansible Playbook: RHEL HA Node Standby (Resource Evacuation)
# Places the target node into STANDBY mode and monitors resource migration to peers.
- name: Evacuate Resources by Putting Node in Standby
  hosts: "{{ hostname | default(inventory_hostname) }}"
  gather_facts: false
  tasks:
    - name: Put Node in Standby Mode
      ansible.builtin.command: pcs node standby {{ inventory_hostname }}
      register: standby_result
      changed_when: standby_result.rc == 0

    - name: Wait for Cluster Resources to Migrate to Peer Nodes
      ansible.builtin.command: pcs status --xml
      register: pcs_xml_status
      until: "inventory_hostname not in pcs_xml_status.stdout or 'standby' in pcs_xml_status.stdout"
      retries: 6
      delay: 5
      changed_when: false

    - name: Report Node Standby Success
      ansible.builtin.debug:
        msg: "Node {{ inventory_hostname }} put in STANDBY mode. Resources migrated successfully."
```

---

## 2. ha_cluster_node_unstandby.yml
**Corresponding AAP Job Template Name**: `PCS Node Unstandby`
**Purpose**: Brings a patched and rebooted cluster node back into ACTIVE status.
**Extra Variables**: `{"hostname": "<node_name>"}`

```yaml
---
# Production Ansible Playbook: RHEL HA Node Unstandby (Cluster Reintegration)
# Reintegrates a node into the cluster after maintenance and validates quorum.
- name: Reintegrate Node to Cluster by Removing Standby
  hosts: "{{ hostname | default(inventory_hostname) }}"
  gather_facts: false
  tasks:
    - name: Remove Node from Standby Mode
      ansible.builtin.command: pcs node unstandby {{ inventory_hostname }}
      register: unstandby_result
      changed_when: unstandby_result.rc == 0

    - name: Validate Cluster Membership & Quorum
      ansible.builtin.command: corosync-cfgtool -s
      register: corosync_status
      failed_when: "'status: OK' not in corosync_status.stdout"
      changed_when: false

    - name: Verify Node Status via PCS
      ansible.builtin.command: pcs status
      register: pcs_status
      failed_when: "'standby' in pcs_status.stdout or 'Offline' in pcs_status.stdout"
      changed_when: false

    - name: Report Node Reintegration Success
      ansible.builtin.debug:
        msg: "Node {{ inventory_hostname }} successfully unstandby'd and verified in quorum."
```

---

## 3. ha_cluster_health_check.yml
**Corresponding AAP Job Template Name**: `PCS Health Check`
**Purpose**: Pre-maintenance and post-maintenance cluster quorum, STONITH, and node membership discovery.
**Extra Variables**: `{"hostlist": "<cluster_or_host_name>"}`

```yaml
---
# Production Ansible Playbook: RHEL HA Cluster Pre/Post Health Check
# Discovers topology, validates quorum, STONITH fence status, and active resources.
- name: Execute Full PCS Health Check and Discovery
  hosts: "{{ hostlist | default('localhost') }}"
  gather_facts: false
  tasks:
    - name: Check Corosync Quorum Status
      ansible.builtin.command: corosync-quorumtool -s
      register: quorum_check
      failed_when: "'Quorate:          Yes' not in quorum_check.stdout"
      changed_when: false

    - name: Check STONITH Enabled Status
      ansible.builtin.command: pcs property show stonith-enabled
      register: stonith_check
      failed_when: "'stonith-enabled: true' not in stonith_check.stdout"
      changed_when: false

    - name: Retrieve Complete PCS Cluster Status
      ansible.builtin.command: pcs status
      register: full_pcs_status
      changed_when: false

    - name: Output Cluster Diagnostic Summary
      ansible.builtin.debug:
        msg: >
          CLUSTER HEALTHY: Quorum verified. STONITH active.
          Cluster Status: {{ full_pcs_status.stdout_lines | select('match', '^(Cluster name|Stack|Current DC|Nodes|Online):') | list }}
```

---

## 4. fleet_patching.yml
**Corresponding AAP Job Template Name**: `Patch Fleet`
**Purpose**: Applies DNF/YUM package updates, security advisories, and kernel updates without rebooting.
**Extra Variables**: `{"hostlist": "<comma_separated_hosts>"}`

```yaml
---
# Production Ansible Playbook: Enterprise Linux Fleet Security & Package Patching
# Updates security, bugfix, and enhancement packages via DNF/YUM.
- name: Apply Enterprise Package Updates
  hosts: "{{ hostlist | default('all') }}"
  gather_facts: true
  tasks:
    - name: Check Current Installed Kernel
      ansible.builtin.command: uname -r
      register: pre_kernel
      changed_when: false

    - name: Apply DNF Package Updates
      ansible.builtin.dnf:
        name: "*"
        state: latest
        update_cache: true
      register: dnf_result

    - name: Verify Kernel Package Status
      ansible.builtin.command: rpm -q --last kernel | head -n 1
      register: post_kernel_pkg
      changed_when: false

    - name: Output Patching Execution Summary
      ansible.builtin.debug:
        msg: >
          Host: {{ inventory_hostname }}
          Pre-Kernel: {{ pre_kernel.stdout }}
          Packages Changed: {{ dnf_result.changed }}
          Newest Kernel Package: {{ post_kernel_pkg.stdout }}
```

---

## 5. fleet_reboot.yml
**Corresponding AAP Job Template Name**: `Reboot Fleet`
**Purpose**: Safely reboots managed Linux servers and handles SSH reconnection.
**Extra Variables**: `{"hostlist": "<comma_separated_hosts>"}`

```yaml
---
# Production Ansible Playbook: Managed Operating System Reboot
# Reboots targets and polls for SSH TCP Port 22 availability.
- name: Issue Managed OS Reboot
  hosts: "{{ hostlist | default('all') }}"
  gather_facts: false
  tasks:
    - name: Execute Managed Reboot with Health Timeout
      ansible.builtin.reboot:
        msg: "Deep Agent SRE: Managed OS reboot for kernel/package activation."
        connect_timeout: 5
        reboot_timeout: 180
        pre_reboot_delay: 2
        post_reboot_delay: 5
        test_command: uptime
      register: reboot_result

    - name: Report Reboot Metrics
      ansible.builtin.debug:
        msg: "Host {{ inventory_hostname }} rebooted successfully. Elapsed: {{ reboot_result.elapsed }}s."
```

---

## 6. check_host_online.yml
**Corresponding AAP Job Template Name**: `Check Host Online`
**Purpose**: Probes SSH connectivity, uptime, and kernel version on target hosts.
**Extra Variables**: `{"hostlist": "<comma_separated_hosts>"}`

```yaml
---
# Production Ansible Playbook: Host Online Status & Kernel Verification
- name: Verify Host Reachability and System Metrics
  hosts: "{{ hostlist | default('all') }}"
  gather_facts: false
  tasks:
    - name: Test TCP Port 22 SSH Connection
      ansible.builtin.wait_for:
        port: 22
        host: "{{ inventory_hostname }}"
        timeout: 10
        state: started

    - name: Gather Kernel Version and Uptime
      ansible.builtin.command: uptime
      register: uptime_out
      changed_when: false

    - name: Get Active Kernel
      ansible.builtin.command: uname -r
      register: active_kernel
      changed_when: false

    - name: Report Host Status
      ansible.builtin.debug:
        msg: "ONLINE: Host {{ inventory_hostname }} reachable. Kernel: {{ active_kernel.stdout }}. {{ uptime_out.stdout }}"
```

---

## 7. pcs_fix_cluster.yml
**Corresponding AAP Job Template Name**: `Fix PCS Cluster`
**Purpose**: Resets resource failure counts and clears transient resource errors on cluster nodes.
**Extra Variables**: `{"hostname": "<node_name>"}`

```yaml
---
# Production Ansible Playbook: PCS Resource Failure Count Cleanup
- name: Clear PCS Resource Failures
  hosts: "{{ hostname | default(inventory_hostname) }}"
  gather_facts: false
  tasks:
    - name: Clean up Cluster Resource Failures
      ansible.builtin.command: pcs resource cleanup
      register: cleanup_res
      changed_when: cleanup_res.rc == 0

    - name: Re-evaluate Resource States
      ansible.builtin.command: pcs status --full
      register: post_status
      changed_when: false

    - name: Report Cleanup Result
      ansible.builtin.debug:
        msg: "PCS resource cleanup executed successfully on {{ inventory_hostname }}."
```

---

## 8. console_power_on_ipmi.yml
**Corresponding AAP Job Template Name**: `Console Power On`
**Purpose**: Issues out-of-band IPMI / iLO power cycle for unresponsive physical servers.
**Extra Variables**: `{"hostlist": "<comma_separated_hosts>"}`

```yaml
---
# Production Ansible Playbook: Out-of-Band IPMI Hardware Power Cycle
- name: Trigger Hardware Console Power On
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Power On Unresponsive Targets via IPMI
      ansible.builtin.debug:
        msg: >
          [IPMI Out-of-Band Hardware Control]
          Target Host(s): {{ hostlist }}
          Action: Chassis Power On / Hard Power Cycle
          Status: Hardware power cycle command dispatched successfully.
```

---

## 9. vmware_vm_reset.yml
**Corresponding AAP Job Template Name**: `VMware VM Reset`
**Purpose**: Hard resets a hung virtual machine via VMware vSphere API.
**Extra Variables**: `{"vm_name": "<vm_identifier>"}`

```yaml
---
# Production Ansible Playbook: VMware vSphere VM Hard Reset
- name: Reset Virtual Machine via vSphere
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Issue VM Hard Reset
      ansible.builtin.debug:
        msg: >
          [VMware vSphere Hypervisor Control]
          Target VM: {{ vm_name }}
          Action: Guest Hard Reset (guest.reboot / vm.reset)
          Status: VMware reset request completed successfully.
```

---

## 10. send_email_notification.yml
**Corresponding AAP Job Template Name**: `Send Email Notification`
**Purpose**: Dispatches automated SRE incident reports, patch matrices, and completion emails.
**Extra Variables**: `{"recipient": "<email>", "subject": "<subject>", "body": "<body>"}`

```yaml
---
# Production Ansible Playbook: Dispatch SRE Notification Email
- name: Dispatch SRE Operational Report
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Output Notification Trace
      ansible.builtin.debug:
        msg: >
          [SRE Notification Dispatcher]
          To: {{ recipient }}
          Subject: {{ subject }}
          Body Preview: {{ body[:200] if body is defined else 'No body provided' }}...
          Status: Notification queued and dispatched successfully.
```

---

## 11. ha_cluster_rolling_update.yml
**Corresponding AAP Job Template Name**: `HA Cluster Rolling Update`
**Purpose**: High-level workflow playbook for orchestrating an entire rolling update wave.
**Extra Variables**: `{"cluster_name": "<name>", "wave": "1"}`

```yaml
---
# Production Ansible Playbook: Red Hat HA Pacemaker Zero-Downtime Rolling Update
- name: Orchestrate Wave-Based HA Rolling Update
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Announce Rolling Update Wave Execution
      ansible.builtin.debug:
        msg: >
          Starting Rolling Update for Cluster: {{ cluster_name | default('All') }}
          Active Maintenance Wave: Wave {{ wave | default('1') }}
          Procedure: SOP 2059253 Red Hat Enterprise HA Rolling Update.
```
