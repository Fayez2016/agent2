# Project Setup and Configuration

This document outlines the configuration and setup for the Hermes Agent and Ollama environment.

## Current Environment
- **Container Engine:** Podman (Rootless)
- **Orchestration:** podman-compose
- **Host OS:** Linux

## Critical System Configuration
To handle image loading and volume permissions in an airgapped, rootless Podman environment, ensure `ignore_chown_errors = "true"` is set in the host's `storage.conf`.

## Custom Images

### Ollama (`local-ollama`)
- **Source:** `ollama.Dockerfile`
- **Feature:** Pre-loads `qwen2.5:0.5b` during the build process to ensure availability in airgapped environments.
- **Base Image:** `docker.io/ollama/ollama:latest`

### Hermes Agent (`local-hermes`)
- **Source:** `hermes.Dockerfile`
- **Feature:** Pre-configures `config.yaml` with the local Ollama provider and overrides the minimum context window requirement.
- **Base Image:** `docker.io/nousresearch/hermes-agent:latest`

## Build and Deployment

### 1. Build Custom Images
```bash
podman build -t local-ollama -f ollama.Dockerfile .
podman build -t local-hermes -f hermes.Dockerfile .
```

### 2. Service Orchestration
The `docker-compose.yml` is configured to use these local images and maps `./.hermes` to `/opt/data`.

```yaml
services:
  hermes:
    image: local-hermes
    # ... (other config)
  ollama:
    image: local-ollama
    # ... (other config)
```

## Active Model Configuration
The agent uses **qwen2.5:0.5b** via the local Ollama instance. The `context_length` is explicitly set to **64000** in `config.yaml` to bypass the agent's internal minimum requirements.

## Usage
To access the interactive chat session reliably:
```bash
podman exec -it -u hermes hermes-agent /opt/hermes/.venv/bin/python /opt/hermes/hermes chat
```
