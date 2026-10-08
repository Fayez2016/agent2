---
name: fleet-patching
description: Standard Operating Procedure for batch OS package patching, managed reboot sequencing, port 22 uptime validation, and final summary reporting across standalone RHEL Linux fleets.
---

# Enterprise Standalone Fleet Patching Procedure

This skill provides step-by-step guidance for executing batch maintenance, kernel updates, managed reboots, and verification across standalone enterprise Linux servers.

## Execution Rules & Planning
1. **Always Use Planning Tool**: Immediately call `write_todos` to initialize and track the fleet patching stages across all targeted hosts.
2. **Batch Execution**: Execute patch and reboot commands across the entire hostlist in batch mode for maximum efficiency.
3. **Smart Rebooting**: Only issue reboots to hosts that returned `need_to_restart: true` or `reboot_required: true` during the patching task.
4. **Strict Completion Boundary**: Once `ansible_check_host_online` confirms SSH connectivity on port 22, the procedure is **100% COMPLETE**.
5. **PROHIBITION ON AD-HOC KERNEL / BOOTLOADER COMMANDS**:
   - NEVER execute ad-hoc grubby, bootloader edits, `dnf remove kernel`, or `dnf reinstall kernel` commands via `ansible_run_command`.
   - If a minor kernel version mismatch or BLS warning is observed, log it as an `INFO/WARNING` in the final summary report for system administrator review.
   - Do NOT attempt destructive package modifications on a live running system.

## Step-by-Step SOP Stages

### Stage 1: Target Host Discovery & Extraction
- Identify all target standalone hosts from user query or maintenance window manifest.

### Stage 2: Batch DNF Package Updates
- Tool: `ansible_patch_fleet`
- Arguments: `{"hostlist": "<comma-separated-target-hosts>"}`
- Description: Apply security errata and software updates via DNF. Inspect response for `need_to_restart` flag.

### Stage 3: Managed Reboot (Conditional)
- Tool: `ansible_reboot_fleet` or `ansible_reboot_host`
- Arguments: `{"hostlist": "<comma-separated-hosts-needing-reboot>"}`
- Description: Initiate coordinated reboots ONLY for hosts that require restart (`need_to_restart: true`). Skip reboot for hosts that do not need it.

### Stage 4: Verify Port 22 Online & Boot Uptime
- Tool: `ansible_check_host_online`
- Arguments: `{"hostlist": "<comma-separated-rebooted-hosts>"}`
- Description: Validate SSH availability on TCP port 22 and record server boot times.

### Stage 5: Out-of-Band IPMI Recovery (Only if Node Hangs)
- Tool: `ansible_console_power_on`
- Arguments: `{"hostlist": "<comma-separated-hung-hosts>"}`
- Description: If any host returns a reboot timeout or connection failure, trigger out-of-band IPMI hardware power-on, followed by re-probe via `ansible_check_host_online`.

### Stage 6: Final SRE Summary Report
- Synthesize the final execution matrix and present the structured markdown table to the user.
