# 🛠️ Security Actions, Hardening Tasks & Implementation Controls

This document details the concrete implementation tasks, configuration actions, and controls enforced across the LangGraph Deep Agent platform.

---

## 📋 Security Implementation Checklist

### **1. FastMCP Server Hardening (`ansible_mcp_server.py`)**
- [x] **Action 1.1**: Embed `sanitize_command()` inside `ansible_mcp_server.py`.
- [x] **Action 1.2**: Intercept `ansible_run_command` and block catastrophic wildcard deletions (`rm -rf /`, `mkfs.`, `chmod -R 777 /`).
- [x] **Action 1.3**: Log all blocked violation attempts into PostgreSQL audit table (`hitl_requests` / `audit_logs`).
- [x] **Action 1.4**: Return structured error response to the caller without crashing the FastMCP RPC loop.

### **2. Prompt Encapsulation & LLM Boundary (`chat.py`)**
- [x] **Action 2.1**: Encapsulate user queries inside `<user_operational_directive>` in `app/api/v1/chat.py`.
- [x] **Action 2.2**: Update system prompt to enforce strict cognitive boundaries on user parameters.

### **3. Zero-Trust Scoped Token Governance (`auth.py` / `auth_repository.py`)**
- [x] **Action 3.1**: Support dedicated scoped tokens (`da_sec_*`) restricted by domain category (`linux`, `windows`, `all`).
- [x] **Action 3.2**: Enable instant token revocation with real-time `HTTP 401 Unauthorized` enforcement.
- [x] **Action 3.3**: Support persistent session tokens in PostgreSQL with 30-minute idle inactivity timeout.

### **4. Secrets & Container Hardening**
- [x] **Action 4.1**: Store sensitive credentials (AAP tokens, SMTP passwords) securely.
- [x] **Action 4.2**: Configure rootless Podman execution with `ignore_chown_errors = "true"` in `storage.conf`.
- [x] **Action 4.3**: Drop unneeded Linux capabilities (`--cap-drop=ALL`).

### **5. Up-to-Date Packages & Component Modernization Matrix**
- [ ] **Action 5.1 (Deep Agent Runtime)**: Upgrade `deepagents >= 0.8.2` and `langgraph >= 0.2.28` for high-throughput streaming updates.
- [ ] **Action 5.2 (LangChain Ecosystem)**: Upgrade `langchain >= 0.3.7`, `langchain-community >= 0.3.5`, `langchain-openai >= 0.2.5`, `langchain-mcp-adapters >= 0.1.2`.
- [ ] **Action 5.3 (API Web Framework)**: Upgrade `fastapi >= 0.115.4`, `uvicorn[standard] >= 0.32.0`, `httpx >= 0.27.2`.
- [ ] **Action 5.4 (Validation & Settings Engine)**: Modernize to `pydantic >= 2.9.2` and `pydantic-settings >= 2.6.0` (Rust-backed validation).
- [ ] **Action 5.5 (PostgreSQL Driver)**: Upgrade `psycopg2-binary >= 2.9.10` with connection pool leak prevention.
- [ ] **Action 5.6 (Official Protocol SDK)**: Upgrade `mcp >= 1.1.0` (official Model Context Protocol SDK).
- [ ] **Action 5.7 (Standard Base Images)**: Modernize base images to latest patch releases (`python:3.11-slim`, `postgres:16-alpine`, `nginx:alpine-slim`).
