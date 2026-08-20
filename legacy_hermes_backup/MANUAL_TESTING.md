# Manual Testing Procedure for Hermes Skills

This guide walks you through validating the agent's reasoning and its integration with the Ansible Automation Platform.

---

## 1. Monitor AAP Logs
In a separate terminal, watch the AAP server logs to verify incoming requests:
```bash
podman logs -f aap-server
```

## 2. Execute Test Query
Run a natural language command that triggers an Ansible operation:

```bash
podman exec -it -u hermes hermes-agent /opt/hermes/.venv/bin/python /opt/hermes/hermes chat -q "check uptime on test-host-01" -m "qwen3-coder-next"
```

### Expected Results
- **Tool Selection:** Agent should choose `ansible_run_command`.
- **API Call:** The `aap-server` should log a `GET` for templates followed by a `POST` to launch the job.
- **Agent Output:** Hermes should report the uptime result (default: 12 days, 4 hours).

## 3. Toolset Verification
Verify that all 5 Ansible tools are registered:
```bash
podman exec -u hermes hermes-agent /opt/hermes/.venv/bin/python -c "from tools.registry import registry; print(registry.get_tool_names_for_toolset('devops'))"
```

---

## 4. API Server Testing
Verify the OpenAI-compatible API server is listening and responding correctly.

### Run Diagnostic Script
Run the automated health check script from your host machine:
```bash
python3 test_api_server_health.py
```

### Manual Verification (CURL)
If you prefer manual testing, use the following commands:

**Health Check:**
```bash
curl -i http://localhost:8642/health
```

**Model List (Authenticated):**
```bash
curl http://localhost:8642/v1/models -H "Authorization: Bearer hermes-api-secret"
```

**Chat Completion (Authenticated):**
```bash
curl http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "hermes-agent",
    "messages": [{"role": "user", "content": "Hello"}],
    "stream": false
  }'
```
