# Project Setup and Configuration

This document outlines the configuration and setup for the Hermes Agent and Enterprise Automation environment.

## Current Environment
- **Container Engine:** Podman (Rootless)
- **Orchestration:** podman-compose
- **Host OS:** Linux
- **Agent Version:** v0.10.0

## Critical System Configuration
To handle image loading and volume permissions in an airgapped, rootless Podman environment, ensure `ignore_chown_errors = "true"` is set in the host's `storage.conf`.

## Custom Images

### AAP API Server (`aap-server`)
- **Source:** `mock_aap.py`
- **Features:**
    - Simulates production Ansible Automation Platform (AAP) API.
    - Fleet simulation: Provides realistic multi-server outputs for patching jobs.
    - Error injection: Randomized failures (SSH unreachable, DNF timeouts) for robust agent testing.
- **Port:** 5000

### Ansible MCP Server (`ansible-mcp`)
- **Source:** `ansible_mcp_server.py`
- **Features:** Bridge between Hermes Agent and AAP API.
- **Port:** 8000 (HTTP Transport)

### Hermes Agent (`hermes-agent`)
- **Source:** `hermes.Dockerfile` (NousResearch/hermes-agent:latest)
- **Features:** Decoupled architecture using MCP for infrastructure automation.

## Available Infrastructure Tools (via MCP)

| Tool | Action |
| :--- | :--- |
| `ansible_patch_fleet` | Apply patches and reboot a fleet (Simulates 20 servers). |
| `ansible_run_command` | Execute shell commands on remote hosts. |
| `ansible_reboot_host` | Reboot a remote host. |
| `ansible_vmware_reset` | Hard reset a VM via VMware API. |
| `ansible_install_package` | Install system packages via DNF/YUM. |
| `ansible_expand_fs` | Expand remote filesystems (LVM/XFS). |
| `ansible_pcs_status` | Get PCS Cluster health status. |
| `ansible_fix_pcs` | Fix/Cleanup PCS cluster resources. |
| `ansible_send_email` | Send automated email notifications. |

## Build and Deployment

```bash
# Start all services
podman-compose up -d --build
```

## Testing
Use the provided `test_ansible_full.py` script to validate end-to-end communication between the agent, the MCP bridge, and the simulated AAP infrastructure.
