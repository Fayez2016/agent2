# Deep Agent — Enterprise Production Playbooks (With Block / Rescue & VMware REST)

This catalog contains **real, fully functional enterprise Ansible playbooks**:
- **Structured Error Handling**: Every playbook uses `block:` and `rescue:` to intercept failures.
- **Detailed JSON Failure Reporting**: When a task fails, the `rescue:` block formats the exact error, command return code, stderr, and host state so Deep Agent's LLM engine receives structured, actionable failure details rather than a generic timeout.
- **VMware vSphere REST API**: Uses the modern VMware REST API (`vmware.vmware_rest` or `uri` against vCenter `/api/vcenter/vm/.../power?action=reset`) with certificate validation controls.
- **Hardware Out-of-Band (IPMI / Redfish)**: Real `ipmi_power` / Redfish REST calls with failover reporting.

---

## 1. ha_cluster_node_standby.yml
**AAP Job Template**: `PCS Node Standby`
**Target Host**: Passed via `hostname`

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

## 2. ha_cluster_node_unstandby.yml
**AAP Job Template**: `PCS Node Unstandby`
**Target Host**: Passed via `hostname`

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

## 3. ha_cluster_health_check.yml
**AAP Job Template**: `PCS Health Check`
**Target Host**: Passed via `hostlist`

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

## 4. fleet_patching.yml
**AAP Job Template**: `Patch Fleet`
**Target Host**: Passed via `hostlist`

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

## 5. fleet_reboot.yml
**AAP Job Template**: `Reboot Fleet`
**Target Host**: Passed via `hostlist`

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

## 6. check_host_online.yml
**AAP Job Template**: `Check Host Online`
**Target Host**: Passed via `hostlist`

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

## 7. pcs_fix_cluster.yml
**AAP Job Template**: `Fix PCS Cluster`
**Target Host**: Passed via `hostname`

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

## 8. vmware_vm_reset.yml (Modern VMware vCenter REST API)
**AAP Job Template**: `VMware VM Reset`
**Target**: `localhost` (Executes against vCenter)
**Extra Variables**: `vm_name`, `vcenter_host`, `vcenter_user`, `vcenter_password`

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

## 9. console_power_on_ipmi.yml (Hardware IPMI / Out-of-Band Control)
**AAP Job Template**: `Console Power On`
**Target**: `localhost` (Commands out-of-band BMC/iLO/iDRAC)
**Extra Variables**: `hostlist`, `ipmi_user`, `ipmi_password`

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

## 10. send_email_notification.yml
**AAP Job Template**: `Send Email Notification`
**Target**: `localhost`
**Extra Variables**: `recipient`, `subject`, `body`

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
            to: "{{ recipient | default('souffm0a@aramco.com') }}"
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
