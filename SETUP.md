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
    - **Fleet simulation:** Provides realistic multi-server outputs for patching jobs.
    - **RHEL HA simulation:** Models cluster node states (standby, disabled, stopped).
    - **Error injection:** Randomized failures for robust agent testing.
- **Port:** 5000

### Ansible MCP Server (`ansible-mcp`)
- **Source:** `ansible_mcp_server.py`
- **Features:** Bridge between Hermes Agent and AAP API, including RHEL HA Best Practices tools.
- **Port:** 8000 (HTTP Transport)

## Available Infrastructure Tools (via MCP)

### RHEL High Availability (Best Practices)
| Tool | Action (Orchestration Step) |
| :--- | :--- |
| `ansible_pcs_cluster_disable` | 1. Disable cluster services from starting at boot. |
| `ansible_pcs_node_standby` | 2. Put node in standby to migrate resources. |
| `ansible_pcs_cluster_stop` | 3. Stop the cluster software on the node. |
| `ansible_pcs_health_check` | 4. Retrieve comprehensive cluster health status. |
| `ansible_pcs_cluster_start` | 5. Rejoin node into the cluster after updates. |
| `ansible_pcs_node_unstandby` | 6. Take node out of standby. |
| `ansible_pcs_cluster_enable` | 7. Re-enable cluster start at boot. |

### Fleet & Infrastructure
| Tool | Action |
| :--- | :--- |
| `ansible_patch_fleet` | Apply patches to a fleet (Simulates 20 servers). |
| `ansible_reboot_fleet` | Reboot a fleet of servers. |
| `ansible_run_command` | Execute shell commands on remote hosts. |
| `ansible_reboot_host` | Reboot a single remote host. |
| `ansible_vmware_reset` | Hard reset a VM via VMware API. |
| `ansible_install_package` | Install system packages via DNF/YUM. |
| `ansible_expand_fs` | Expand remote filesystems (LVM/XFS). |
| `ansible_pcs_status` | Get basic PCS Cluster health status. |
| `ansible_fix_pcs` | Fix/Cleanup PCS cluster resources. |
| `ansible_send_email` | Send automated email notifications. |

## Build and Deployment

```bash
# Start all services
podman-compose up -d --build
```

## Testing
Use the provided `test_ansible_full.py` script to validate end-to-end communication between the agent, the MCP bridge, and the simulated AAP infrastructure.
