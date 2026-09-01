# Deep Agent Manual Testing Guide

This guide provides step-by-step instructions for manually testing the **LangGraph Deep Agent (`deepagent_system`)** core API, Human-in-the-Loop (HITL) approval gate, subagents, and React Control Panel Web UI.

---

## 1. Prerequisites & Environment Check

Before initiating manual tests, ensure all container microservices are up and healthy.

### 1.1 Verify Running Containers
Run the following command to check active containers:
```bash
podman ps --filter name=deepagent
```

**Expected Containers:**
| Container Name | Service | Port | Status |
| :--- | :--- | :--- | :--- |
| `deepagent-service` | Deep Agent Core REST API | `8642` | `Up` |
| `deepagent-webui` | React Control Panel UI | `3000` | `Up` |
| `deepagent-ollama` | Local Ollama Model Engine | `11434` | `Up` |
| `deepagent-ansible-mcp` | Ansible MCP Tool Bridge | `8000` | `Up` |
| `deepagent-hitl-web` | HITL Approval Web Portal | `5001` | `Up` |
| `deepagent-hitl-db` | HITL Audit Database (PostgreSQL) | `5432` | `Up` |
| `deepagent-aap-server` | Mock AAP Server (`deepagent_system/mock_aap/`) | `5000` | `Up` |

---

## 2. Ansible Backend Mode Toggle (`mock` vs `prd`)

The system supports dual Ansible execution modes configured in `.env` or `docker-compose.deepagent.yml`:

- **Mock Mode (`ANSIBLE_BACKEND_MODE=mock`) [Default for Testing]:** Routes execution to `aap-server:5000` (`deepagent_system/mock_aap/`). Safe for non-destructive testing without affecting physical hardware.
- **Production Mode (`ANSIBLE_BACKEND_MODE=prd`):** Routes execution to live Production AAP Controller (`AAP_HOST_PRD`, `AAP_TOKEN_PRD`).

To verify current mode:
```bash
podman exec deepagent-service printenv ANSIBLE_BACKEND_MODE
```

---

## 3. Step 1: Health & Connectivity Probes

### 3.1 Test Core API Health (`Port 8642`)
Execute a GET request against the health endpoint:
```bash
curl -v http://localhost:8642/health
```
**Expected Response:**
```json
{"status": "ok", "service": "deepagent-core"}
```

### 3.2 Test HITL Web Portal (`Port 5001`)
Open a browser and navigate to:
```text
http://localhost:5001
```
**Default Admin Credentials:**
- **Username:** `admin`
- **Password:** `admin123`

---

## 4. Step 2: Manual API Testing (REST API Endpoint)

### Test Case A: Low-Risk Diagnostic Query (Read-Only)
Sends a non-destructive cluster health check prompt.

```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "deepagent",
    "messages": [
      {
        "role": "user",
        "content": "Check the Pacemaker cluster health for host rhel-prod-01"
      }
    ]
  }'
```
**Expected Behavior:**
- Agent invokes `ansible_pcs_health_check` via `ansible-mcp`.
- The request completes automatically without requiring manual HITL approval.
- Response contains cluster quorum and resource state summary.

---

### Test Case B: High-Risk Infrastructure Action (HITL Security Gate)
Sends a high-risk operational command (`reboot host`) that triggers the approval workflow.

#### Step 1: Submit Prompt via REST API
```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "deepagent",
    "messages": [
      {
        "role": "user",
        "content": "Reboot the host rhel-prod-01"
      }
    ]
  }'
```

#### Step 2: Approve Action in HITL Web Portal
1. Open browser to `http://localhost:5001` and log in (`admin` / `admin123`).
2. Notice the pending authorization request for tool **`Reboot Host`** on target node `rhel-prod-01`.
3. Click **Approve**.

#### Step 3: Verify Output
The API request thread will resume upon detecting approval state `GRANTED` and return:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Host rhel-prod-01 reboot playbook executed successfully."
      }
    }
  ]
}
```

---

### Test Case C: Subagent Delegation Test (`rhel-diagnostics` / `fleet-patcher`)
Triggers specialized subagents defined in `.deepagents/agents/`.

```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "deepagent",
    "messages": [
      {
        "role": "user",
        "content": "Use the rhel-diagnostics subagent to inspect CIB constraints on rhel-prod-02"
      }
    ]
  }'
```

---

## 5. Step 3: React Web Control Panel UI Testing (`Port 3000`)

1. Open browser to `http://localhost:3000`.
2. Enter prompt in input bar:
   ```text
   Check cluster health for rhel-prod-01
   ```
3. Click **Send**.
4. Verify live assistant streaming transcript and response rendering.

---

## 6. Step 4: Automated End-to-End Verification Suite

To run all automated verification stages in sequence:
```bash
python3 deepagent_system/run_deepagent_tests.py
```

**Test Suite Coverage:**
- `[Test 1/4]`: Core API Health Endpoint Probe (`http://localhost:8642/health`).
- `[Test 2/4]`: Low-Risk MCP Tool Execution (`ansible_pcs_health_check`).
- `[Test 3/4]`: High-Risk HITL Gate Interception & Auto-Approval (`ansible_reboot_host` on Port `5001`).

---

## 7. Troubleshooting & Inspection

### View Real-Time Core Agent Logs:
```bash
podman logs -f deepagent-service
```

### View Ansible MCP Bridge Logs:
```bash
podman logs -f deepagent-ansible-mcp
```

### View Mock AAP Server Logs:
```bash
podman logs -f deepagent-aap-server
```

### Restart Service Stack:
```bash
podman-compose -f deepagent_system/docker-compose.deepagent.yml restart
```
