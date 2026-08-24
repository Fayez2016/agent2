---
name: single-host-ops
description: Standard Operating Procedure for targeted single-host operations, package installations, filesystem expansions, service management, and single server reboots.
---

# Single-Host Remediation & Operations Procedure

This skill provides step-by-step guidance for ad-hoc administrative actions targeting individual enterprise servers.

## Execution Rules & Planning
1. **Track Progress**: Use `write_todos` to track pre-checks, execution, and verification steps.
2. **Post-Action Verification**: Always verify service health or filesystem metrics immediately following any modification.

## Available Procedures

### Package Installation
- Tool: `ansible_install_package`
- Arguments: `{"hostname": "<server>", "package_name": "<pkg>"}`

### Filesystem & Volume Expansion
- Tool: `ansible_expand_fs`
- Arguments: `{"hostname": "<server>", "mount_point": "/var", "size_gb": 50}`

### Managed Single Host Reboot
- Tool: `ansible_reboot_host`
- Arguments: `{"hostname": "<server>"}`

### Direct Shell Command Execution
- Tool: `ansible_run_command`
- Arguments: `{"hostname": "<server>", "command": "<cmd>"}`
