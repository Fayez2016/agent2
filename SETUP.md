# Project Setup and Configuration

This document outlines the configuration and setup for the Hermes Agent and Enterprise Automation environment.

## Current Environment
- **Container Engine:** Podman (Rootless)
- **Orchestration:** podman-compose
- **Host OS:** Linux

## Critical System Configuration
To handle image loading and volume permissions in an airgapped, rootless Podman environment, ensure `ignore_chown_errors = "true"` is set in the host's `storage.conf`.

## Custom Images

### AAP API Server (`aap-server`)
- **Source:** `mock_aap.Dockerfile`
- **Feature:** Simulates a production Ansible Automation Platform (AAP) API for testing tool integration.
- **Base Image:** `docker.io/python:3.11-slim`

### Hermes Agent (`local-hermes`)
- **Source:** `hermes.Dockerfile`
- `config.yaml` is pre-configured with the Ollama Cloud provider.
- **Base Image:** `docker.io/nousresearch/hermes-agent:latest`

## Build and Deployment

### 1. Build and Start Services
The project uses `podman-compose` for orchestration.

```bash
podman-compose up -d --force-recreate
```

### 2. Service Architecture
The `docker-compose.yml` is configured to run the agent and the AAP server on the same internal network (`agent2_default`).

## Skills Architecture
The agent is equipped with native DevOps skills that communicate with the AAP API Server.

### DevOps Skills (`devops/`)
- `ansible_run_command`: Executes shell commands on remote hosts.
- `ansible_reboot_host`: Reboots remote systems.
- `ansible_install_package`: Installs system packages.
- `ansible_expand_fs`: Expands remote filesystems.
- `ansible_fix_pcs`: Resolves PCS cluster issues.

## Interactive Chat
To access the interactive session with the latest DevOps toolset:
```bash
podman exec -it -u hermes hermes-agent /opt/hermes/.venv/bin/python /opt/hermes/hermes chat -m "qwen3-coder-next"
```
