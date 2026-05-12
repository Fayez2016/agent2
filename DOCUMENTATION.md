# Hermes Enterprise Automation: Persistent HITL System Documentation

## 1. Implementation Design & Architecture

The system is designed as a microservices architecture orchestrated via Podman Compose. It provides an AI-driven automation layer for enterprise infrastructure (RHEL High Availability clusters) with a strict Human-in-the-Loop (HITL) security gate.

### Application Architecture
- **Hermes Agent (`hermes`):** The primary brain. Handles natural language processing, reasoning, and tool selection.
- **Ansible MCP Server (`ansible-mcp`):** A Model Context Protocol bridge that translates agent requests into Ansible Automation Platform (AAP) API calls.
- **HITL Web Interface (`hitl-web`):** A Flask-based authenticated dashboard for human operators to review and approve high-risk actions.
- **Persistent Database (`db`):** A PostgreSQL instance storing user credentials and a durable audit log of all HITL requests and decisions.
- **Mock AAP Server (`aap-server`):** Simulates the Ansible Automation Platform API for safe end-to-end testing.

## 2. Database Schema

The `hitl` database contains two primary tables:

### `users`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL (PK) | Unique user identifier. |
| `username` | VARCHAR(50) | Unique login name. |
| `password_hash`| TEXT | Scrypt hashed password. |

### `hitl_requests`
| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | SERIAL (PK) | Unique request identifier. |
| `action_summary`| TEXT | Description of the high-risk task requested by the agent. |
| `status` | VARCHAR(20) | Current state: `PENDING`, `GRANTED`, or `DENIED`. |
| `requested_at` | TIMESTAMP | Time the agent initiated the request. |
| `resolved_at` | TIMESTAMP | Time the operator made a decision. |
| `resolved_by` | INTEGER (FK) | Reference to the user who resolved the request. |

## 3. Network Flow (HITL Authorization)

1. **Request:** Agent decides to perform a "High Risk" action (e.g., `ansible_reboot_host`).
2. **Interception:** The MCP server logic detects the high-risk tag and blocks execution.
3. **Approval Flow:**
    - Agent calls `hitl_request_approval` with a summary.
    - MCP server inserts a `PENDING` record into the PostgreSQL DB.
    - MCP server enters a polling loop, checking the DB every 2 seconds.
4. **Resolution:**
    - Operator logs into `hitl-web` (Port 5001).
    - Operator clicks "Approve" or "Reject".
    - Web UI updates the DB record status to `GRANTED` or `DENIED`.
5. **Execution:**
    - MCP server detects the `GRANTED` status.
    - MCP server executes the original Ansible task and returns results to the agent.

## 4. MCP Tools & Security

### High-Risk Tools (Requires HITL)
- `ansible_reboot_host`: Reboots a single node.
- `ansible_reboot_fleet`: Reboots multiple nodes.
- `ansible_pcs_node_standby`: Isolates a node from the cluster.
- `ansible_pcs_maintenance_mode`: Toggles global cluster maintenance.
- `ansible_vmware_reset`: Hard resets a VM.

### Standard Tools (Audit Log Only)
- `ansible_pcs_health_check`: Comprehensive cluster diagnostic.
- `ansible_install_package`: Installs DNF/YUM packages.
- `ansible_expand_fs`: Extends LVM/XFS volumes.
- `ansible_send_email`: Notifications.

## 5. Testing & Validation

The system includes a comprehensive E2E test suite: `test_ansible_full.py`.
- **Automated HITL Bot:** Simulates a human operator by logging into the web UI and approving requests.
- **Dual Interface Testing:** Alternates between calling the Hermes CLI and the Hermes REST API for each test case.
- **Coverage:** 15 test cases covering the entire RHEL HA patching lifecycle.

---

# User Guide: Operating the Hermes HITL System

## 1. Managing Services

### Start the System
```bash
# Clean start (recommended after updates)
podman-compose down -v
podman-compose up -d --build
```

### Stop the System
```bash
podman-compose stop
```

### Check Logs
```bash
# View real-time HITL requests
podman logs -f ansible-mcp

# View web access logs
podman logs -f hitl-web
```

## 2. Accessing the Web Dashboards

### HITL Approval Gate
- **URL:** `http://localhost:5001`
- **Purpose:** Secure authorization for high-risk Ansible tasks.
- **Default Username:** `admin`
- **Default Password:** `admin123`

### Hermes Web Dashboard
- **URL:** `http://localhost:9119`
- **Purpose:** Comprehensive agent management interface.
- **Key Features:**
    - **Status:** Monitor agent version and active sessions.
    - **Chat:** Use the full Hermes TUI directly in your browser.
    - **Config:** Edit `config.yaml` through a web form.
    - **Analytics:** View token usage and costs.

## 3. Using the Agent (CLI)
Execute tasks directly via the `podman exec` command:

```bash
podman exec -u hermes hermes-agent /opt/hermes/.venv/bin/python /opt/hermes/.venv/bin/hermes chat -q "Check the health of the rhel-prod cluster"
```

## 4. Using the Agent (REST API)
The agent listens on port `8642`. You can send requests using `curl`:

```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Authorization: Bearer hermes-api-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "hermes-agent",
    "messages": [{"role": "user", "content": "Reboot host rhel-prod-01"}],
    "stream": false
  }'
```

*Note: The API call will hang while waiting for HITL approval. Go to the web UI to approve it.*

## 5. Troubleshooting
- **Permission Denied (DB):** Ensure `init.sql` ran correctly. Check role permissions with `\du` in psql.
- **API Timeout:** The default REST timeout in `test_ansible_full.py` is 300s. Ensure approvals are granted within this window.
- **Container Health:** Run `podman ps` to ensure all 5 containers are `Up`.
