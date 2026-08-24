# Deep Agent System Architecture & Operations Runbook

## 1. System Architecture Overview

The **Deep Agent System** is a production-grade, autonomous Site Reliability Engineering (SRE) platform built on official **LangChain Deep Agents**, **LangGraph**, **FastAPI**, and the **Model Context Protocol (MCP)**. It executes automated, high-risk infrastructure lifecycles—such as zero-downtime rolling kernel updates on High Availability (HA) Pacemaker clusters and enterprise standalone fleet patching—with Human-in-the-Loop (HITL) safety guardrails.

```mermaid
graph TD
    UserClient["Web UI (:3000) / REST Client"] --> API["FastAPI API Server (:8642)"]
    
    subgraph APILayer["Modular API Layer (app/api/v1/)"]
        ChatAPI["chat.py (/v1/chat/completions)"]
        HitlAPI["hitl.py (/v1/hitl/pending, resolve)"]
        SettingsAPI["settings.py (/v1/settings/hitl_mode)"]
        ThreadsAPI["threads.py (/v1/threads, messages, export)"]
    end
    API --> APILayer

    subgraph DeepAgentPrism["LangChain Deep Agent Engine (app/agent_engine.py)"]
        RootAgent["Root SRE Deep Agent (create_deep_agent)"]
        Skills["Declarative Skills Directory (skills/*/skill.md)"]
        Planning["Dynamic Planning Tool (write_todos)"]
        Subagents["Specialized Subagents (ha_cluster_patcher, fleet_patcher, etc.)"]
    end
    APILayer --> RootAgent
    RootAgent --> Skills
    RootAgent --> Planning
    RootAgent --> Subagents

    subgraph MultiServerMCP["Multi-Server MCP Architecture (langchain_mcp_adapters)"]
        AnsibleMCP["Ansible Execution MCP Server (:8000) - 25 Infrastructure Tools"]
        SOPMCP["Dedicated SOP FastMCP Server (:8001) - Discoverable Resources & Safety Tools"]
    end
    Subagents --> MultiServerMCP

    subgraph Persistence["Persistence & Audit Layer"]
        PostgreSQL[("PostgreSQL (hitl-db:5432)")]
    end
    APILayer --> PostgreSQL
```

---

## 2. Multi-Server Model Context Protocol (MCP) Topology

The system uses LangChain's `MultiServerMCPClient` to connect to multiple specialized FastMCP servers simultaneously over Streamable HTTP:

### 1. Ansible Execution Server (`deepagent-ansible-mcp:8000`)
- **Role**: The "Hands" of the platform. Interacts with AAP/AWX playbooks, sends SSH commands, modifies cluster nodes, and queries infrastructure state.
- **Key Tools**:
  - `ansible_pcs_node_standby`, `ansible_pcs_node_unstandby`
  - `ansible_patch_fleet`, `ansible_reboot_fleet`
  - `ansible_check_host_online`, `ansible_console_power_on`
  - `ansible_send_email`, `ansible_pcs_health_check`

### 2. Dedicated SOP Knowledge Server (`deepagent-sop-mcp:8001`)
- **Role**: The "Brain & Compliance Guide" of the platform. Hosts operational runbooks and evaluates safety criteria.
- **Exposed FastMCP Resources**:
  - `sop://catalog`: Catalog of all registered enterprise procedures.
  - `sop://rhel/ha/2059253`: Red Hat HA Pacemaker Rolling Update Markdown SOP.
  - `sop://rhel/fleet/patching`: Enterprise Fleet Patching Markdown SOP.
  - `sop://rhel/recovery/console`: Out-of-Band IPMI Recovery Markdown SOP.
- **Exposed FastMCP Tools**:
  - `sop_get_procedure(sop_id)`: Fetches execution stages and checklists.
  - `sop_validate_prerequisites(sop_id, precheck_stdout)`: Evaluates cluster health stdout against quorum and STONITH safety rules.
  - `sop_generate_execution_plan(sop_id, entities, hitl_mode)`: Computes execution graphs and upfront authorization needs.

---

## 3. Configuration Management (`app/config.py`)

Configured centrally using **Pydantic v2 Settings** (`pydantic_settings.BaseSettings`):
- `API_PORT` (default: `8642`)
- `API_SERVER_KEY` (default: `hermes-api-secret`)
- `OLLAMA_HOST` (default: `http://ollama:11434`)
- `ANSIBLE_MCP_URL` (default: `http://deepagent-ansible-mcp:8000/mcp`)
- `SOP_MCP_URL` (default: `http://deepagent-sop-mcp:8001/mcp`)
- `DATABASE_URL` (default: `postgresql://hermes:secret456@db:5432/hitl`)
- `ANSIBLE_BACKEND_MODE` (`mock` or `prd`)

---

## 4. How to Add a New Operational Skill or Subagent

All extensions follow official **LangChain Deep Agents** standards:

1. **Add a Declarative Skill (`deepagent_system/skills/<skill_name>/skill.md`)**:
   Add a standard markdown file with YAML frontmatter specifying `name` and `description`.
2. **Add a Subagent in `app/agent_engine.py`**:
   Add the subagent definition under `subagents=[...]` with its specialized system prompt in `app/prompts.py`.
3. **Run Verification**:
   Execute `python3 tests/run_all_verification_tests.py` to ensure 100% test pass status.

---

## 5. Operations & Verification Runbook

### Starting the Stack
```bash
podman-compose -f docker-compose.deepagent.yml up -d
```

### Running the Master Test Harness (7 Test Suites)
```bash
python3 /home/fayez/agent2/deepagent_system/tests/run_all_verification_tests.py
```
