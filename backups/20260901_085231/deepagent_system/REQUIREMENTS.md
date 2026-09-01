# Deep Agent System Requirements Specification

## 1. Overview
This document specifies the operational, environment, container, and security requirements for the **LangGraph Deep Agent (`deepagent_system`)**.

---

## 2. Environment & Containerization Requirements

### 2.1 Rootless Podman Execution
- **Rootless Engine**: All microservices MUST run under rootless Podman without root/sudo privileges.
- **Storage Configuration**: Podman storage MUST configure `ignore_chown_errors = "true"` in `storage.conf` to prevent permission issues during container image layer unpacking.
- **Port Binding**: Service container ports MUST bind to high unprivileged ports ($>1024$):
  - Deep Agent REST API: `8642`
  - React Web UI: `3000`
  - Ollama Engine: `11434`
  - Ansible MCP Server: `8000`
  - HITL Approval Gateway: `5001`
  - Mock AAP Server: `5000`

### 2.2 Component Separation & Microservice Independence
Each component MUST be decoupled into a separate container image and service definition for independent updates and maintenance:
1. `ollama-service`: Independent container serving local LLMs (`gemma4:12b` / `qwen3:1.7b`).
2. `deepagent-core`: Decoupled Python service executing official `deepagents` harness and MCP client logic.
3. `deepagent-webui`: Decoupled React frontend UI (`@langchain/react` + Vite).
4. `ansible-mcp`: Decoupled MCP tool translation bridge.
5. `hitl-web` & `hitl-db`: PostgreSQL-backed security approval gate.
6. `aap-server`: Reusable mock Ansible Automation Platform server located in `deepagent_system/mock_aap/`.

---

## 3. Dual Ansible Execution Mode (Mock vs Production AAP)

### 3.1 Mode Configuration (`ANSIBLE_BACKEND_MODE`)
The system MUST support seamless switching between a **Mock Ansible Backend** (for testing/staging) and a **Production AAP Controller (PRD)**:

| Variable Name | Values | Description |
| :--- | :--- | :--- |
| `ANSIBLE_BACKEND_MODE` | `mock` / `prd` | Selects whether to execute against Mock AAP (`mock`) or Production AAP (`prd`) |
| `AAP_HOST` | Hostname / IP:Port | URL of target AAP server (Mock: `aap-server:5000`, PRD: `https://aap.prd.enterprise.local`) |
| `AAP_TOKEN` | Bearer Token String | Authentication token for AAP REST API |
| `AAP_VERIFY_SSL` | `true` / `false` | Enable/disable SSL certificate verification for production AAP |

### 3.2 Reusable Mock Ansible Server (`mock_aap/`)
- In `mock` mode (`ANSIBLE_BACKEND_MODE=mock`), `ansible-mcp` routes all cluster playbooks and job templates to `aap-server:5000` (`deepagent_system/mock_aap/mock_aap.py`), returning simulated RHEL cluster status and job execution outputs without risk to physical hosts.
- In `prd` mode (`ANSIBLE_BACKEND_MODE=prd`), `ansible-mcp` connects to the Production AAP Controller REST API using production credentials.

---

## 4. Functional Requirements

### 4.1 LLM Engine & Subagents
- **Air-Gapped Operation**: System MUST run offline using local Ollama container (`http://ollama:11434`).
- **Deep Agent Harness**: MUST use official `create_deep_agent` initialization with `ChatOllama` / `ChatOpenAI` wrapper.
- **Memory & Governance**: MUST automatically load persistent memory from `/home/fayez/agent2/AGENTS.md`.
- **Custom Subagents**: MUST support custom subagents defined in `.deepagents/agents/` (`rhel-diagnostics` and `fleet-patcher`).

### 4.2 Security & HITL Approval Mandate
- **No Direct SSH**: No direct SSH connections are permitted. All fleet actions MUST use `ansible-mcp`.
- **HITL Gate Interception**: High-risk infrastructure commands (`ansible_reboot_host`, `ansible_pcs_node_standby`, `ansible_vmware_reset`) MUST halt execution and create a `PENDING` request in PostgreSQL until approved on Port `5001`.

### 4.3 REST API Compatibility
- **OpenAI-Compatible Endpoint**: MUST expose `POST /v1/chat/completions` on Port `8642` so existing verification test suites (`test_ansible_full.py`) run unmodified.
