---
name: fleet-patching
description: Standard Operating Procedure for batch OS package patching, managed reboot sequencing, port 22 uptime validation, and out-of-band IPMI recovery across standalone RHEL Linux fleets.
---

# Enterprise Standalone Fleet Patching Procedure

This skill provides step-by-step guidance for executing batch maintenance, kernel updates, managed reboots, and out-of-band recovery across standalone enterprise Linux servers.

## Execution Rules & Planning
1. **Always Use Planning Tool**: Immediately call `write_todos` to initialize and track the fleet patching stages across all targeted hosts.
2. **Batch Execution**: Execute patch and reboot commands across the entire hostlist in batch mode for maximum efficiency.
3. **Out-of-Band Resilience**: Automatically detect SSH timeouts or kernel soft-hangs and execute hardware console cycles via IPMI without requiring operator intervention.

## Step-by-Step SOP Stages

### Stage 1: Target Host Discovery & Extraction
- Identify all target standalone hosts from user query (handling comma-separated lists, range syntax e.g., `rhel-prod-01 to rhel-prod-10`, and arbitrary server names).

### Stage 2: Batch DNF Package Updates
- Tool: `ansible_patch_fleet`
- Arguments: `{"hostlist": "<comma-separated-target-hosts>"}`
- Description: Apply security errata and software updates via DNF. Log any package dependency or GPG key validation errors per host.

### Stage 3: Batch Managed Reboot
- Tool: `ansible_reboot_fleet`
- Arguments: `{"hostlist": "<comma-separated-target-hosts>"}`
- Description: Initiate coordinated operating system reboots across all target hosts.

### Stage 4: Verify Port 22 Online & Boot Uptime
- Tool: `ansible_check_host_online`
- Arguments: `{"hostlist": "<comma-separated-target-hosts>"}`
- Description: Validate SSH availability on TCP port 22 and record server boot times.

### Stage 5: Out-of-Band IPMI Recovery (For Hung Nodes)
- Tool: `ansible_console_power_on`
- Arguments: `{"hostlist": "<comma-separated-hung-hosts>"}`
- Description: If any host returns a reboot timeout or connection failure, immediately dispatch an out-of-band IPMI hardware power-on signal, followed by a re-probe via `ansible_check_host_online`.

### Stage 6: Dispatch SRE Summary Email Notification
- Tool: `ansible_send_email`
- Arguments: `{"recipient": "admin@enterprise.local", "subject": "[SRE Report] Fleet Patching Completed Across X Hosts", "body": "<summary>"}`
- Description: Send the finalized patch execution matrix and incident post-mortem to the system administrator.
