# 🛡️ Enterprise Security Architecture & FastMCP Embedded Guard Plan

**Version**: 2.0.0  
**Status**: Approved Architecture  
**Target**: Enterprise Air-Gapped RHEL / OpenShift Deep Agent Platform  
**Component Placement**: Embedded inside Ansible FastMCP Server Container (`:8000`)

---

## 🎯 Executive Overview & Security Goals
This document establishes the **Production Security Architecture** for the LangGraph Deep Agent platform. It focuses on a clean, low-maintenance, defense-in-depth model that guarantees:
1. **Physical Protection Against Destructive Commands**: Enforced by deterministic Python code directly inside the Ansible FastMCP Server (`ansible_mcp_server.py`) before touching AAP or the target server fleet.
2. **Zero Maintenance Overhead**: Eliminates complex, fragile regex engines and replaces them with strict JSON parameter schemas and structural prompt boundaries.
3. **100% Hands-Free Autonomous Mode**: Allows safe autonomous operations (HA rolling updates, disk volume expansions, security patching, log diagnostics) to run to completion without operator interruption.
4. **Zero False Positives**: Ensures normal SRE commands (`grep`, `journalctl`, `cat`, `df -h`, `systemctl`) execute smoothly without false alarms.

---

## 🏛️ System Architecture Diagram

```
                              ┌───────────────────────────────────┐
                              │  🌐 Third-Party Tools & Clients   │
                              │ (ServiceNow / Prometheus / Web UI)│
                              └─────────────────┬─────────────────┘
                                                │
                               Bearer da_sec_*  │  
                                                ▼
                              ┌───────────────────────────────────┐
                              │     ⚡ REST Backend API (:8642)   │
                              │  - Scoped Token Auth Engine       │
                              │  - Structural Prompt Encapsulation│
                              │    (<user_operational_directive>) │
                              └─────────────────┬─────────────────┘
                                                │
                                                ▼
                              ┌───────────────────────────────────┐
                              │   🧠 Lead SRE Agent Orchestrator  │
                              │       (Dynamic LangGraph Core)    │
                              └────────┬─────────────────┬────────┘
                                       │                 │
              ┌────────────────────────┴───────┐         └────────────────────────┐
              ▼                                ▼                                  ▼
 ┌─────────────────────────┐      ┌─────────────────────────┐        ┌─────────────────────────┐
 │ 🤖 ha_cluster_patcher   │      │ 🤖 fleet_patcher        │        │ 🤖 rhel_diagnostician   │
 └────────────┬────────────┘      └────────────┬────────────┘        └────────────┬────────────┘
              │                                │                                  │
              └────────────────────────────────┼──────────────────────────────────┘
                                               │ Streamable HTTP RPC
                                               ▼
                              ┌───────────────────────────────────┐
                              │   ⚡ Ansible FastMCP Server       │
                              │      Container (:8000/mcp)        │
                              │                                   │
                              │  ┌─────────────────────────────┐  │
                              │  │ 🛡️ Embedded Security Guard  │  │
                              │  │  - Command Inspector        │  │
                              │  │  - JSON Schema Validator    │  │
                              │  │  - PostgreSQL Audit Logger  │  │
                              │  └──────────────┬──────────────┘  │
                              └─────────────────┼─────────────────┘
                                                │
                         ┌──────────────────────┴──────────────────────┐
                         │                                             │
               🚨 Catastrophic Command                       🟢 Safe SRE Command
                         │                                             │
                         ▼                                             ▼
            ┌───────────────────────────┐                ┌───────────────────────────┐
            │   ❌ Physical Block       │                │  🚀 Launch AAP Playbook   │
            │ (AAP/SSH NEVER contacted) │                │     on Server Fleet       │
            └───────────────────────────┘                └───────────────────────────┘
```

---

## 🔒 3-Tier Defense-in-Depth Breakdown

### **Tier 1: Pre-LLM Structural Prompt Encapsulation (API Layer)**
- In `app/api/v1/chat.py`, all inbound user queries and external inputs are transparently wrapped:
  ```python
  wrapped_query = f"<user_operational_directive>\n{user_query}\n</user_operational_directive>"
  ```
- **Cognitive Boundary**: The system prompt instructs the model that content inside `<user_operational_directive>` represents operational parameters, preventing system prompt overrides.

### **Tier 2: FastMCP Structured Parameter Contracts (Tool Boundary)**
- FastMCP tools (`ansible_expand_fs`, `ansible_patch_fleet`, `ansible_pcs_node_standby`) enforce strict JSON schemas (`size_gb: int`, `cluster_name: str`, `hostlist: str`).
- Raw shell strings cannot be passed into structured arguments.

### **Tier 3: Embedded Deterministic Security Guard (FastMCP Server Layer)**
- Embedded directly inside `ansible_mcp_server.py`.
- Evaluates raw command arguments in `ansible_run_command` prior to executing any REST call to Ansible Automation Platform (AAP):
  ```python
  CATASTROPHIC_PATTERNS = [
      "rm -rf /",
      "rm -rf /*",
      "mkfs.",
      "dd if=/dev/zero",
      ":(){ :|:& };:",
      "chmod -R 777 /",
      "chmod 777 /",
      "shutdown -h now",
      "init 0"
  ]
  ```
- If a pattern is matched, execution is **immediately rejected in Python code**. Zero network packets are sent to AAP or SSH.

---

## 📊 Security & Action Governance Matrix

| Operation Category | Specific Tools | Enforced Mode | Autonomous Mode | Safety Gate Mechanism |
| :--- | :--- | :---: | :---: | :--- |
| **Telemetry & Diagnostics** | `ansible_get_server_info`, `ansible_ping`, `journalctl`, `grep` | 🟢 Auto | 🟢 Auto | Read-only telemetry (zero operational risk). |
| **Automated Remediation** | `ansible_expand_fs`, `ansible_pcs_node_standby`, `ansible_patch_fleet` | 🛑 HITL Prompt | 🟢 Auto | Pre-defined AAP playbooks with strictly typed parameters. |
| **Raw Shell Execution** | `ansible_run_command("ps aux | grep nginx")` | 🛑 HITL Prompt | 🟢 Auto | Inspected by Embedded FastMCP Security Guard. |
| **Destructive Command** | `ansible_run_command("rm -rf /")` | ❌ **HARD BLOCKED** | ❌ **HARD BLOCKED** | **Deterministic Physical Block**: Python code in MCP server aborts execution immediately. |
| **Filesystem Wipe** | `ansible_run_command("mkfs.ext4 /dev/sda1")` | ❌ **HARD BLOCKED** | ❌ **HARD BLOCKED** | **Deterministic Physical Block**: Python code in MCP server aborts execution immediately. |
