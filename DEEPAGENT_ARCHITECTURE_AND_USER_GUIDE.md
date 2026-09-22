# Deep Agent — System Architecture, Design & User Guide

An enterprise-grade, air-gapped autonomous Site Reliability Engineering (SRE) multi-agent platform running on Red Hat Enterprise Linux 9 with Rootless Podman, Human-in-the-Loop (HITL) safety gates, and Model Context Protocol (MCP) tool integration.

---

## 1. Executive Overview

Deep Agent is an autonomous operations platform designed specifically for air-gapped, high-security enterprise environments (such as critical industrial or energy infrastructure). It bridges Large Language Models (LLMs) with enterprise infrastructure execution engines like Red Hat Ansible Automation Platform (AAP) and Pacemaker High Availability (HA) clustering.

### Key Pillars:
1. **Air-Gapped & Self-Contained**: Operates with zero public internet connectivity using local/on-premise LLMs (Ollama / vLLM) and container images loaded from offline bundles or Red Hat Satellite.
2. **Human-in-the-Loop (HITL) Safety Gates**: Destructive actions (reboots, node evacuations, cluster stops, package patching) are intercepted before execution and require cryptographic operator approval.
3. **Multi-Server MCP Architecture**: Adheres to Anthropic's Model Context Protocol (MCP) to decouple LLM reasoning from tool execution.
4. **Resilient 90/10 Architecture**: 90% of operational changes (SOPs, skills, playbooks, prompts) are modified at runtime without rebuilding container images.

---

## 2. System Architecture

```
                  ┌───────────────────────────────────────────────┐
                  │                 USER BROWSER                  │
                  │        (HTTPS TLS 1.3 / Port 8443)            │
                  └───────────────────────┬───────────────────────┘
                                          │
                                          ▼
                  ┌───────────────────────────────────────────────┐
                  │            deepagent-proxy (Nginx)            │
                  │   - Reverse Proxy & SSL Termination           │
                  │   - Unified UI & API routing                  │
                  └───────┬───────────────┬───────────────┬───────┘
                          │               │               │
            /api /ws      │               │ /mcp/ansible  │ /mcp/sop
                          ▼               │               │
  ┌───────────────────────────────┐       │               │
  │     deepagent-service         │       │               │
  │ (LangGraph Multi-Agent Core)  │       │               │
  │   - Supervisor Agent          │       │               │
  │   - HA Patcher Subagent       │       │               │
  │   - Fleet Patcher Subagent    │       │               │
  └───────┬───────────────┬───────┘       │               │
          │               │               │               │
          │ LLM Requests  │ State / Audit │               │
          ▼               ▼               ▼               ▼
  ┌───────────────┐ ┌───────────┐ ┌───────────────┐ ┌───────────┐
  │ Local LLM     │ │ PostgreSQL│ │ Ansible MCP   │ │ SOP MCP   │
  │ (Ollama/vLLM) │ │ (hitl-db) │ │ Server (:8000)│ │ (:8001)   │
  └───────────────┘ └───────────┘ └───────┬───────┘ └───────────┘
                                          │
                                          ▼
                          ┌───────────────────────────────┐
                          │   Ansible Automation Platform │
                          │        (AAP / Tower)          │
                          │   - Production Playbooks      │
                          │   - RHEL Server Fleet         │
                          └───────────────────────────────┘
```

---

## 3. Container Pod Microservices (7 Containers)

All microservices run in a unified Podman pod (`deepagent-prod-pod`) sharing an internal loopback network:

| Container Name | Service | Function | Port |
| :--- | :--- | :--- | :--- |
| `deepagent-proxy` | Nginx 1.22 | TLS 1.3 reverse proxy, path routing, and WebUI delivery | `8443` (host) |
| `deepagent-service` | FastAPI + LangGraph | Primary multi-agent cognitive loop & supervisor orchestration | `8000` (internal) |
| `deepagent-hitl-db` | PostgreSQL 16 | Storage for conversations, HITL audits, agent skills, and settings | `5432` (internal) |
| `deepagent-ansible-mcp` | FastMCP Server | Safe execution proxy for Ansible AAP job templates | `8000` (internal) |
| `deepagent-sop-mcp` | FastMCP Server | Exposes standard operating procedures (SOPs) as LLM tools | `8001` (internal) |
| `deepagent-aap-server` | Mock AAP Engine | Enterprise mock AAP simulator for disconnected testing | `8080` (internal) |
| `deepagent-webui` | SPA Studio | Operator console for live monitoring and HITL approvals | `80` (internal) |

---

## 4. Operational Workflows & SOPs

### A. Zero-Downtime HA Cluster Rolling Update (SOP 2059253)
Deep Agent coordinates rolling updates across two-node or multi-node Pacemaker/Corosync clusters:
1. **Pre-Check**: Validates cluster health (`pcs status`) and STONITH fence agents.
2. **Node Evacuation**: Intercepted by HITL approval; executes `pcs node standby <node>`.
3. **Errata Application**: Applies security and bugfix updates via DNF.
4. **Managed Reboot**: Reboots the target node and monitors kernel uptime.
5. **Reintegration**: Executes `pcs node unstandby <node>` and verifies resource migration.
6. **Next Node**: Advances to the remaining cluster nodes sequentially (`serial: 1`).

### B. Fleet DNF Security Patching
For standalone, non-clustered application servers:
1. Dispatches parallel or batch DNF patching across inventory groups.
2. Triggers phased reboots while respecting maximum concurrency limits.
3. Automatically triggers out-of-band IPMI chassis power cycles if any host encounters a soft hang during reboot.

---

## 5. Human-in-the-Loop (HITL) Safety Architecture

To prevent unauthorized or accidental infrastructure modifications, Deep Agent enforces strict HITL policies:

```
[Agent identifies need to Reboot Host]
                 │
                 ▼
[Action matches High-Risk Policy Rule]
                 │
                 ▼
[System creates pending record in hitl_requests]
                 │
                 ▼
[WebUI displays Action Details, Risk Level, & Target Host]
                 │
      ┌──────────┴──────────┐
      ▼                     ▼
[Operator Approves]   [Operator Rejects]
      │                     │
      ▼                     ▼
[Action Executes]     [Execution Aborted & Logged]
```

### High-Risk Actions Requiring Approval:
* `PCS Node Standby` / `PCS Node Unstandby`
* `PCS Cluster Stop` / `PCS Cluster Start`
* `Patch Fleet` / `Reboot Fleet`
* `Reboot Host` / `Limited Run Any Command`
* `VMware VM Reset`

---

## 6. How to Use Deep Agent

### A. Accessing the Web Studio
Open your browser and navigate to:
```
https://<SERVER_IP_OR_HOSTNAME>:8443
```
Accept the self-signed certificate. You will be greeted by the Deep Agent Operations Studio.

### B. Triggering an Activity
In the chat interface, enter your command in natural language:
- *"Execute rolling update on ha_cluster_01 per SOP 2059253"*
- *"Check online status for web fleet and apply security patches"*
- *"Inspect cluster health across all database nodes"*

### C. Approving HITL Actions
When a high-risk operation is queued:
1. The **Pending Approvals** drawer will alert the operator.
2. Review the command arguments, target hostname, and playbook name.
3. Click **Grant** to allow execution or **Deny** to abort.

### D. Managing Sync with GitLab
Operational assets are synced to/from GitLab:
- **Pushing Updates**: Run `./push_deepagent_assets_to_gitlab.sh <REPO_URL> main`
- **Boot Pull Service**: The `deepagent.service` systemd unit automatically attempts to pull updates on server boot without ever blocking startup if GitLab is unreachable.

---

## 7. Troubleshooting & Common Commands

| Task | Command |
| :--- | :--- |
| **Check Pod Status** | `podman pod ps` |
| **View Container Logs** | `podman logs -f deepagent-service` |
| **Inspect DB Health** | `podman exec deepagent-hitl-db psql -U hermes -d hitl -c "\dt"` |
| **Test Nginx TLS** | `curl -k https://127.0.0.1:8443/api/v1/health` |
| **Restart Service** | `systemctl restart deepagent.service` |

---
*Deep Agent — Enterprise Autonomous Infrastructure Operations*
