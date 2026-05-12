# Hermes Agent Configuration Guide

This document details the configuration layers for the Hermes Agent, including the REST API server, model selection, MCP connections, and subagent delegation.

## 1. Core Configuration (`config.yaml`)

The primary configuration file is located at `/opt/data/config.yaml` inside the container (mapped to `./.hermes/config.yaml` on the host).

### Model Selection
Hermes is configured to use a custom provider (Ollama) by default.
```yaml
model:
  provider: custom
  base_url: https://ollama.com/v1
  model: qwen3-coder-next
context_length: 65536
```
- **provider:** `custom` allows connecting to any OpenAI-compatible API.
- **base_url:** The endpoint for the inference server.
- **model:** The specific model identifier (e.g., `qwen3-coder-next`, `llama3`).

### MCP Server Connections
External tools are integrated via the Model Context Protocol (MCP).
```yaml
mcp_servers:
  ansible:
    url: "http://ansible-mcp:8000/mcp"
```
- **ansible:** The local alias for the server.
- **url:** The HTTP/SSE endpoint of the MCP bridge. Adding new entries here allows Hermes to discover more tools dynamically.

### Toolset Exposure
Controls which tools are available via different interfaces.
```yaml
agent:
  toolsets:
    - all
platform_toolsets:
  cli:
    - all
  api_server:
    - all
```

## 2. Environment Variables (`docker-compose.yml`)

The agent's behavior and system integration are controlled via environment variables.

### API Server & Dashboard Settings
- `API_SERVER_ENABLED=true`: Activates the OpenAI-compatible REST listener.
- `API_SERVER_HOST=0.0.0.0`: Binds the server to all interfaces.
- `API_SERVER_KEY=hermes-api-secret`: The Bearer token required for authentication.
- `API_SERVER_PORT=8642`: (Internal) Port the agent listens on.
- `HERMES_DASHBOARD_TUI=1`: Enables the embedded terminal TUI within the web dashboard.

### Dashboard Startup
The dashboard is launched via the command:
`hermes dashboard --host 0.0.0.0 --insecure --no-open`
- `--host 0.0.0.0`: Allows external access to the dashboard container.
- `--insecure`: Required for binding to non-localhost addresses.
- `--no-open`: Prevents the agent from attempting to open a browser window inside the container.

### System Integration
- `CONTAINER_HOST=unix:///run/user/1000/podman/podman.sock`: Allows Hermes to manage other containers (e.g., for the `code_execution` sandbox).
- `GATEWAY_ALLOW_ALL_USERS=true`: Simplifies access for local development/simulation.
- `DEBUG=1`: Enables verbose logging for troubleshooting agent reasoning.

## 3. Subagent Delegation

Hermes supports complex task decomposition through the `delegation` toolset.

### How it Works
1. **Tool:** `delegate_task(task_description, context)`
2. **Logic:** When a task is too large or requires a specialized context, the primary agent spawns a "Subagent".
3. **Execution:** The subagent receives its own model parameters and a focused subset of tools.
4. **Resolution:** The subagent completes the task and returns a summarized result to the primary agent.

### Configuration
Subagents inherit the model settings from the primary agent but operate in a isolated session. This is particularly useful for:
- Long-running code generation.
- Recursive infrastructure checks.
- Batch processing of fleet logs.

## 4. REST API Usage Example

The API server provides a `/v1/chat/completions` endpoint compatible with the OpenAI SDK.

**Request:**
```bash
curl http://localhost:8642/v1/chat/completions \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "hermes-agent",
    "messages": [{"role": "user", "content": "list cluster status"}]
  }'
```

**Response Structure:**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "Cluster is healthy. Nodes: rhel-prod-01 (Online), rhel-prod-02 (Online)."
    }
  }]
}
```

## 5. Persistent Data
All agent state (sessions, memory, skills) is stored in `/opt/data`. Ensure the host volume mapping in `docker-compose.yml` is preserved to maintain continuity across restarts.
