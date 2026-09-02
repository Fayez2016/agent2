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

### **5. Up-to-Date Packages & Component Modernization Matrix (100% Verified)**
- [x] **Action 5.1 (Deep Agent Runtime)**: Verified `deepagents v0.8.2` and `langgraph v1.2.11` for high-throughput streaming updates.
- [x] **Action 5.2 (LangChain Ecosystem)**: Verified `langchain v1.3.17`, `langchain-community v0.4.2`, `langchain-openai v1.6.0`, `langchain-mcp-adapters v0.3.2`.
- [x] **Action 5.3 (API Web Framework)**: Verified `fastapi v0.141.1`, `uvicorn[standard] v0.32.0`, `httpx v0.28.1`.
- [x] **Action 5.4 (Validation & Settings Engine)**: Modernized to `pydantic v2.13.4` and `pydantic-settings v2.15.0` (Rust-backed validation).
- [x] **Action 5.5 (PostgreSQL Driver)**: Verified `psycopg2-binary v2.9.10` with connection pool leak prevention.
- [x] **Action 5.6 (Official Protocol SDK)**: Verified `mcp v1.29.1` (official Model Context Protocol SDK).
- [x] **Action 5.7 (Standard Base Images)**: Standardized on lightweight, up-to-date community base images (`python:3.11-slim`, `postgres:16-alpine`, `nginx:alpine-slim`).
- [x] **Action 5.8 (Automated Maintenance Tool)**: Implemented general-purpose update script (`system_updater.sh`) providing automated discovery, diff inspection, rolling restart, and audit logging.
