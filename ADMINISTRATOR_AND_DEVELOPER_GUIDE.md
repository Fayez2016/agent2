# Enterprise Administrator & Developer Guide: Dynamic Multi-Domain Deep Agent Platform

---

## 📖 Executive Summary & Architectural Overview

The **LangGraph Deep Agent Platform** is an enterprise-grade, multi-domain autonomous SRE system designed to execute mission-critical infrastructure operations across diverse environments (Red Hat Linux, Windows Server, VMware vSphere, Kubernetes, and Cloud Databases).

The system operates on a **Declarative Multi-Server FastMCP Architecture** coupled with a **Dynamic Agent Compiler**:
1. **Zero-Code Operation**: Administrators can provision Main Agents, attach Subagents, register FastMCP endpoints, and modify system prompts/SOPs in real time via the Web UI (`:3000`).
2. **Developer Extensibility**: Developers can build standalone FastMCP servers (using Python/FastMCP or any MCP-compliant language) and bind them to the core agent harness via standard network protocols (`streamable_http` or `sse`).

---

## 🏛️ System Architecture Diagram

```
                             ┌───────────────────────────────────┐
                             │    🌐 Web UI / REST Client        │
                             │ (Port :3000 / API Port :8642)     │
                             └─────────────────┬─────────────────┘
                                               │
                                               ▼
                             ┌───────────────────────────────────┐
                             │   🧠 Dynamic Agent Compiler       │
                             │        (agent_engine.py)          │
                             └────────┬─────────────────┬────────┘
                                      │                 │
             ┌────────────────────────┴───────┐         └────────────────────────┐
             ▼                                ▼                                  ▼
┌─────────────────────────┐      ┌─────────────────────────┐        ┌─────────────────────────┐
│   🛡️ Linux SRE Agent    │      │  🪟 Windows Admin Agent │        │   ☁️ VMware Cloud SRE   │
│   - ha_cluster_patcher  │      │  - ad_sync_operator     │        │   - esxi_rolling_patcher│
│   - fleet_patcher       │      │  - winrm_fleet_patcher  │        │   - vmotion_operator    │
│   - rhel_diagnostician  │      │  - iis_service_manager  │        │   - datastore_planner   │
└────────────┬────────────┘      └────────────┬────────────┘        └────────────┬────────────┘
             │                                │                                  │
             ▼                                ▼                                  ▼
┌─────────────────────────┐      ┌─────────────────────────┐        ┌─────────────────────────┐
│ 🔌 Ansible MCP (:8000)  │      │ 🔌 WinRM MCP (:8002)    │        │ 🔌 vSphere MCP (:8003)  │
│ 🔌 SOP FastMCP (:8001)  │      │   (PowerShell Engine)   │        │   (pyVmomi Engine)      │
└─────────────────────────┘      └─────────────────────────┘        └─────────────────────────┘
             │                                │                                  │
             └────────────────────────────────┼──────────────────────────────────┘
                                              ▼
                             ┌───────────────────────────────────┐
                             │   🐘 PostgreSQL State Store       │
                             │   (domain_agents, mcp_servers,    │
                             │    domain_subagents, skills)      │
                             └───────────────────────────────────┘
```

---

## 🛠️ Part 1: Administrator UI Guide (No Code Required)

### 1.1 Managing FastMCP Servers
- **Add Server**:
  1. Open **`⚙️ Agent & MCP Studio`** tab.
  2. In the **FastMCP Servers** card, click **`➕ Add MCP Server`**.
  3. Provide `Server Name` (e.g. `winrm_mcp`), `Domain Scope` (`windows`), and `Endpoint URL` (`http://deepagent-winrm:8002/mcp`).
  4. Click **`Save Server`**.
- **Live Tool Verification**:
  - Click **`⚡ Ping / Live Tools`** on any server card to test network connectivity and inspect all tools exposed by that server in real time.
- **Delete Server**:
  - Click the **`🗑️`** icon on any server card to delete the registration from PostgreSQL.

### 1.2 Creating a New Main Domain Agent
1. In the Studio tab, click **`➕ Create Domain Agent`**.
2. Fill in the parameters:
   - **Agent Key (Unique)**: `windows_admin`
   - **Display Name**: `Windows Enterprise Administrator`
   - **Domain Category**: `windows`
   - **System Prompt**: Core directives defining the agent's identity, responsibilities, and guardrails.
3. Click **`Save Main Agent`**.
4. The agent is immediately available in the top-left sidebar **`ACTIVE DOMAIN AGENT`** selector.

### 1.3 Attaching & Configuring Subagents
1. Select your target agent in the sidebar dropdown.
2. In the **Domain Subagents & Prompts** card, click **`➕ Add Subagent`**.
3. Fill in:
   - **Subagent Name**: `ad_sync_operator`
   - **Tool Bindings**: Comma-separated list of tool names (e.g. `ansible_run_command, ansible_send_email, hitl_request_approval`).
   - **Description**: Summary of the subagent's role.
   - **Subagent System Prompt**: Specialized instructions for the subagent.
4. Click **`Save Subagent`**.

### 1.4 Live Editing of System Prompts & SOP Skills
- **Main Agent Prompt**: Click **`📜 Lead Orchestrator System Prompt`** at the top of the Studio tab to expand the editor, make changes, and click **`Save Prompt Changes`**.
- **Subagent Prompts**: Click **`📜 Subagent System Prompt`** on any subagent card to expand, edit, and click **`Save Subagent Prompt`**.
- **Declarative SOPs**: Under **Declarative SOP Skills**, click **`View & Edit Markdown SOP`**, edit the markdown procedure, and click **`Save SOP Markdown`**.

### 1.5 Managing Scoped API Tokens & Webhook Integrations (Step 9)
- **Generate Token**:
  1. Open **`⚙️ Settings`** tab.
  2. In the **🔑 Scoped API Tokens & Webhook Integrations** card, click **`➕ Generate Token`**.
  3. Specify:
     - **Token Name**: e.g., `Dynatrace SRE Alert Webhook`
     - **Domain Scope**: `all`, `linux`, `windows`, or `vmware`.
     - **Expiration**: `7d`, `30d`, `90d`, `1y`, or `never` (persistent).
  4. Click **`Generate Key`**.
  5. Copy the generated secret (`da_sec_*`).
- **Token Revocation**:
  - Click **`Revoke`** on any active token in the list to immediately invalidate external webhook access.

### 1.6 User Management, Passwords & RBAC
- **Change Password**: In the **👥 Operator Accounts & RBAC Roles** card, click **`🔑 Change Password`**, enter the current and new passwords, and submit.
- **Add Operator**: Click **`➕ Add User`** to create accounts with specific RBAC roles (`operator`, `admin`, `viewer`).
- **Sign Out**: Click the **`🚪 Sign Out`** button in the header or in the Settings tab to terminate your session.

### 1.7 Inbound Webhooks & 5-Minute Event Deduplication (Step 5 & 8.5)
- Access the **`⚡ Alarms`** tab to monitor raw alert storms ingested from third-party monitoring tools (Dynatrace, Prometheus, SolarWinds, Datadog).
- Click **`⚡ Simulate 20-Alarm Storm`** to test high-frequency burst absorption.
- Click **`🚀 Process & Deduplicate Batch Now`** to trigger the 5-minute deduplicator and auto-generate an incident thread.

---

## 💻 Part 2: Developer Implementation Guide (Building New MCP Servers & Tools)

When adding support for a completely new technology domain (e.g., Windows WinRM, VMware vSphere, Kubernetes), you will develop a standalone **FastMCP Server Container**.

---

### 2.1 FastMCP Server Template (`server.py`)

Below is the standard reference implementation for creating a standalone Python FastMCP server using the official `mcp.server.fastmcp` SDK:

```python
#!/usr/bin/env python3
"""
================================================================================
 Enterprise Windows WinRM / PowerShell FastMCP Server
================================================================================
 Provides high-performance, structured RPC tools for managing Windows fleets.
================================================================================
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("WindowsWinRMMCP")

# 1. Initialize FastMCP Server
mcp = FastMCP("WindowsWinRMServer", host="0.0.0.0", port=8002)

# 2. Define High-Value Infrastructure Tools

@mcp.tool()
def winrm_run_powershell(hostname: str, script_block: str) -> Dict[str, Any]:
    """
    Executes a PowerShell script block on a target Windows Server via WinRM.
    
    Args:
        hostname: Target Windows host (e.g. 'win-dc-01.corp.local')
        script_block: Valid PowerShell command or script
    """
    logger.info(f"Executing PowerShell script on {hostname}: {script_block[:60]}...")
    
    # In production, invokes pywinrm / Ansible Windows connection plugin
    return {
        "host": hostname,
        "status": "SUCCESS",
        "exit_code": 0,
        "output": f"Executed on {hostname}: Output OK",
        "changed": True
    }

@mcp.tool()
def winrm_service_manage(hostname: str, service_name: str, state: str) -> Dict[str, Any]:
    """
    Controls Windows Services (start, stop, restart).
    
    Args:
        hostname: Target Windows host
        service_name: Windows service identifier (e.g. 'W3SVC', 'NTDS')
        state: Desired state ('started', 'stopped', 'restarted')
    """
    logger.info(f"Service {service_name} on {hostname} -> state: {state}")
    return {
        "host": hostname,
        "service": service_name,
        "state": state,
        "status": "SUCCESS"
    }

@mcp.tool()
def winrm_check_ad_replication(domain_controller: str) -> Dict[str, Any]:
    """
    Executes repadmin /showrepl across Active Directory domain controllers.
    """
    return {
        "domain_controller": domain_controller,
        "replication_status": "HEALTHY",
        "inbound_neighbors": 4,
        "failed_replications": 0
    }

if __name__ == "__main__":
    logger.info("Starting Windows WinRM FastMCP Server on port 8002...")
    mcp.run(transport="streamable_http")
```

---

### 2.2 Containerizing the New FastMCP Server (`Dockerfile`)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies & pywinrm
RUN pip install --no-cache-dir \
    mcp[cli] \
    fastmcp \
    pywinrm \
    httpx \
    uvicorn

COPY server.py /app/server.py

EXPOSE 8002

CMD ["python", "/app/server.py"]
```

---

### 2.3 Compose & Network Registration (`docker-compose.yml`)

Add the service to your container stack:

```yaml
  deepagent-windows-mcp:
    build:
      context: ./windows_mcp_server
      dockerfile: Dockerfile
    container_name: deepagent-windows-mcp
    restart: unless-stopped
    ports:
      - "8002:8002"
    networks:
      - deepagent_standalone_net
```

---

## 🔒 Part 3: HITL (Human-In-The-Loop) Safety Directives

When writing tools that make changes to live infrastructure, follow the HITL security conventions specified in `AGENTS.md`:

1. **High-Risk Operations**:
   - Node standbys, reboots, service stops, cluster fencing, and schema modifications MUST invoke `hitl_request_approval`.
2. **Approval Names**:
   - Tool names must match the exact action string defined in the governance policy.
3. **Execution Guard**:
   ```python
   if hitl_mode == "enforced":
       approval = await request_approval(action_name="Reboot Host", target=hostname)
       if approval.status != "GRANTED":
           return {"status": "ABORTED", "reason": "HITL Authorization Denied"}
   ```

---

## 📊 Database Schema Reference

The multi-domain platform state is governed by core relational tables in PostgreSQL:

| Table | Purpose | Key Columns |
| :--- | :--- | :--- |
| `domain_agents` | Main Domain Lead Agents | `id, key_name, display_name, domain_category, model_name, system_prompt, is_active` |
| `domain_subagents` | Specialized Worker Agents | `id, parent_agent_id, name, display_name, system_prompt, tool_bindings (JSONB)` |
| `mcp_servers` | FastMCP Endpoint Registry | `id, name, display_name, domain_scope, url, transport, is_active` |
| `domain_skills` | Declarative SOP Procedures | `id, name, display_name, domain_category, description, content_markdown` |
| `users` | Operator Accounts & RBAC | `id, username, password_hash, role, email, created_at, is_active` |
| `api_tokens` | Scoped Webhook Tokens | `id, token_hash, name, scope, domain_category, created_by, expires_at, is_active` |
| `collected_events`| 5-Minute Ingestion Buffer | `id, host_target, alert_type, severity, domain, payload (JSONB), processed` |

---

## 🚀 Quick Reference Commands

- **Run Full Automated Verification Suite**:
  ```bash
  podman exec -it deepagent-service python /app/scripts/run_all_tests.py
  ```
- **Sync & Push Code Changes to GitHub**:
  ```bash
  ./push_to_github.sh
  ```
- **Database Backup Snapshot**:
  ```bash
  podman exec deepagent-hitl-db pg_dump -U hermes -d hitl > backups/$(date +%Y%m%d)/hitl_backup.sql
  ```
