# ⚡ Enterprise LangGraph Deep Agent Platform

> **Autonomous Enterprise SRE & Multi-Server FastMCP Orchestration**  
> Dynamic Multi-Agent Reasoning | Red Hat HA Rolling Updates (SOP 2059253) | Zero-Trust Scoped API Tokens | Human-In-The-Loop (HITL) Governance

---

## 📖 Architectural Overview

The **LangGraph Deep Agent Platform** is an enterprise-grade autonomous Site Reliability Engineering (SRE) solution designed for complex multi-node infrastructure maintenance, automated diagnostics, self-healing root cause analysis, and fleet-wide patching.

```
                              ┌───────────────────────────────────┐
                              │  🌐 Third-Party Tools & Clients   │
                              │ (ServiceNow / Prometheus / CI-CD) │
                              └─────────────────┬─────────────────┘
                                                │
                          Bearer da_sec_*       │  High-Frequency Alarms
                       POST /v1/chat/completions│  POST /v1/events/webhook
                                                ▼
                              ┌───────────────────────────────────┐
                              │     ⚡ REST Backend API (:8642)   │
                              │ - Scoped Token Auth Engine        │
                              │ - 5-Min Webhook Sliding Buffer    │
                              │ - Multi-MCP Supervisor Daemon     │
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
 │ (SOP 2059253 HA Waves)  │      │ (Fleet Patch & Reboot)  │        │ (Cluster Log Triage)    │
 └────────────┬────────────┘      └────────────┬────────────┘        └────────────┬────────────┘
              │                                │                                  │
              └────────────────────────────────┼──────────────────────────────────┘
                                               │
                                               ▼
                              ┌───────────────────────────────────┐
                              │   ⚡ Ansible FastMCP Server       │
                              │      (:8000 / :8001 SOP MCP)      │
                              └────────────────┬──────────────────┘
                                               │
                                               ▼
                              ┌───────────────────────────────────┐
                              │     🖥️ Enterprise Server Fleet    │
                              │ (RHEL HA Clusters / App Nodes)    │
                              └───────────────────────────────────┘
```

---

## 🤖 Specialized Subagent Registry

| Subagent Name | Specialized Role | Primary FastMCP Tools | Supported Workflows |
| :--- | :--- | :--- | :--- |
| **`ha_cluster_patcher`** | HA Cluster Rolling Updates (SOP 2059253) | `ansible_pcs_*`, `ansible_patch_fleet`, `ansible_reboot_fleet` | 2-wave sequential HA rolling updates with automatic standby, patch, reboot, quorum verification, and unstandby with zero service downtime. |
| **`fleet_patcher`** | Fleet-Wide Patching & Batch Reboots | `ansible_patch_fleet`, `ansible_reboot_fleet`, `hitl_request_approval` | Staged batch security errata patching and coordinated rolling reboots across standalone application servers. |
| **`rhel_diagnostician`** | Log Triage & Cluster Diagnostics | `ansible_get_server_info`, `ansible_pcs_health_check` | Remote log filtering and systemd journal analysis across dozens of hosts without LLM token context overflow. |
| **`single_host_operator`** | Ad-Hoc Node Maintenance & LVM Expansion | `ansible_expand_fs`, `ansible_install_package`, `ansible_run_command` | Dynamic filesystem volume resizing (`/var/lib/pgsql`), single package installs, and service maintenance. |

---

## 🔌 API Integration Reference

### **1. Universal REST Completions (`POST /v1/chat/completions`)**
External systems (ServiceNow, AWX, CI/CD, custom scripts) can invoke any subagent via standard OpenAI-compatible JSON requests.

#### **cURL Example (HA Rolling Update via `ha_cluster_patcher`)**:
```bash
curl -X POST http://<deepagent-host>:8642/v1/chat/completions \
  -H "Authorization: Bearer <DEDICATED_SCOPED_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepagent",
    "domain": "linux_sre",
    "thread_id": "servicenow_chg_8941",
    "messages": [
      {
        "role": "user",
        "content": "Using ha_cluster_patcher subagent, execute the Red Hat HA Rolling Update (SOP 2059253) on cluster ha_cluster_01."
      }
    ],
    "stream": false
  }'
```

#### **cURL Example (Fleet Patching via `fleet_patcher`)**:
```bash
curl -X POST http://<deepagent-host>:8642/v1/chat/completions \
  -H "Authorization: Bearer <DEDICATED_SCOPED_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "deepagent",
    "domain": "linux_sre",
    "thread_id": "servicenow_chg_fleet_patch_02",
    "messages": [
      {
        "role": "user",
        "content": "Using fleet_patcher subagent, apply security updates and staged reboots on rhel-app-01 to rhel-app-04."
      }
    ],
    "stream": false
  }'
```

---

### **2. Dedicated Inbound Monitoring Webhooks (`POST /v1/events/webhook`)**
Monitoring tools (Prometheus Alertmanager, Dynatrace, Datadog, Nagios) send high-frequency JSON alarms to their dedicated endpoint, isolating telemetry from operational tasks.

```bash
curl -X POST http://<deepagent-host>:8642/v1/events/webhook \
  -H "Authorization: Bearer <DEDICATED_SCOPED_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "host_target": "rhel-db-01",
    "alert_type": "DISK_UTILIZATION_CRITICAL",
    "severity": "critical",
    "domain": "linux",
    "payload": {
      "mount": "/var/lib/pgsql",
      "usage_pct": 98.4
    }
  }'
```

---

## 🔑 Dedicated Zero-Trust Scoped API Tokens

Manage tokens directly in the Web UI (**`⚙️ Settings` $\rightarrow$ `🔑 Scoped API Tokens`**) or via the REST API:

```bash
curl -X POST http://<deepagent-host>:8642/v1/auth/tokens \
  -H "Authorization: Bearer hermes-api-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ServiceNow HA Patching Automation (Dedicated)",
    "scope": "read_write",
    "domain_category": "linux",
    "expiry_option": "30d"
  }'
```
- **Domain-Scoped**: Tokens can be restricted to `linux`, `windows`, `vmware`, or `all`.
- **Instant Revocation**: Revoking a token immediately invalidates access with `HTTP 401 Unauthorized` without affecting other services.

---

## 🚀 Quickstart: Rootless Podman Deployment

```bash
# 1. Clone repository
git clone https://github.com/Fayez2016/agent2.git
cd agent2

# 2. Build container images (airgapped-ready)
podman build -t deepagent-system:latest -f Containerfile deepagent_system/

# 3. Start PostgreSQL, FastMCP Servers, and Deep Agent Runtime
podman-compose up -d

# 4. Access Web UI
open http://localhost:3000
# Default Login: admin / admin123
```

---

## 🧪 Automated Testing & UAT Battery

Execute the complete 14-scenario automated test suite:
```bash
python3 uat_test_suite/test_universal_rest_subagents.py
```
- Test specifications: [`uat_test_suite/UAT_TEST_PLAN.md`](uat_test_suite/UAT_TEST_PLAN.md)
- Consolidated results: [`uat_test_suite/UAT_EXECUTION_REPORT.md`](uat_test_suite/UAT_EXECUTION_REPORT.md)
