# Architecture & Refactoring Plan: Migrating `deepagent_system/` to Official LangChain Deep Agents Primitives (Updated)

## 1. Executive Summary & Goals
We are refactoring the **Deep Agent** Linux operations system inside `deepagent_system/` to fully align with the official **LangChain Deep Agents** specification (`deepagents` package, `create_deep_agent`).

### Key Adjustments (Per User Directive):
1. **No Fallback Tools for Legacy Code**:
   - Legacy workflow orchestrators are **NOT** added as agent tools.
   - All legacy orchestrators (`fleet_patcher.py`, `ha_rolling_update.py`, `rhel_diagnostics.py`, `single_host_ops.py`, `workflow_dispatcher.py`) are cleanly preserved and archived into a dedicated directory: `deepagent_system/legacy_orchestrators_backup/` for reference and rollback purposes.
2. **Pure Deep Agents Architecture**:
   - The root agent and subagents operate 100% via LLM reasoning, FastMCP tools (`:8000` execution & `:8001` knowledge), declarative skills (`skills/*/skill.md`), and built-in planning (`write_todos`).

---

## 2. Target Project & Directory Structure

```text
deepagent_system/
├── skills/                                  # Declarative Deep Agent Skills (Progressive Disclosure)
│   ├── rhel_ha_patching/
│   │   └── skill.md                         # YAML frontmatter + SOP 2059253 instructions
│   ├── fleet_patching/
│   │   └── skill.md                         # YAML frontmatter + batch fleet patching SOP
│   ├── rhel_diagnostics/
│   │   └── skill.md                         # YAML frontmatter + cluster triage SOP
│   └── single_host_ops/
│       └── skill.md                         # YAML frontmatter + single-host operations SOP
│
├── legacy_orchestrators_backup/             # <-- PRESERVED LEGACY CODE (Archived, not in agent tools)
│   ├── fleet_patcher.py
│   │── ha_rolling_update.py
│   │── rhel_diagnostics.py
│   │── single_host_ops.py
│   └── workflow_dispatcher.py
│
├── app/
│   ├── api/v1/                              # Modular FastAPI routers
│   │   ├── chat.py                          # SSE streaming & completions using deep agent invoke
│   │   ├── hitl.py                          # /v1/hitl/pending & /v1/hitl/resolve
│   │   ├── settings.py                      # /v1/settings/hitl_mode
│   │   └── threads.py                       # Session CRUD & SRE post-mortem export
│   │
│   ├── infrastructure/db/                   # Database & Repository layer
│   │   ├── database.py                      # PostgreSQL connection pool context manager
│   │   ├── hitl_repository.py               # Strongly-typed HITL queries & resolution
│   │   └── thread_repository.py             # Thread/Message CRUD with JSONB execution traces
│   │
│   ├── domain/
│   │   └── services/
│   │       ├── entity_extractor.py          # Entity & range token parser utility
│   │       └── report_generator.py          # SRE Markdown summary & incident log generator
│   │
│   ├── config.py                            # Centralized Pydantic v2 Settings
│   ├── mcp_client.py                        # MultiServerMCPClient (:8000 & :8001)
│   ├── prompts.py                           # System prompts for root agent & subagents
│   ├── agent_engine.py                      # create_deep_agent setup with skills, subagents, and tools
│   └── main.py                              # Clean FastAPI ASGI entrypoint
│
├── sop_mcp_server/                          # FastMCP SOP Knowledge Server (:8001)
├── ansible_mcp_server/                      # FastMCP Ansible Execution Server (:8000)
├── mock_aap/                                # AAP Simulation Engine (:5000)
├── web_ui/                                  # SRE Dashboard (:3000)
└── tests/                                   # Master verification test harness (7 suites)
```

---

## 3. Implementation Phases

### Phase 1: Archive Legacy Orchestrators to Backup Directory
1. Create `deepagent_system/legacy_orchestrators_backup/`.
2. Copy all files from `app/domain/orchestrators/` into `deepagent_system/legacy_orchestrators_backup/`:
   - `fleet_patcher.py`
   - `ha_rolling_update.py`
   - `rhel_diagnostics.py`
   - `single_host_ops.py`
   - `workflow_dispatcher.py`
3. Ensure no references to these legacy orchestrators remain in the active agent tool registry.

---

### Phase 2: Create Declarative Skills Directory (`skills/*/skill.md`)
Create markdown skill files with standard YAML frontmatter (`name`, `description`) for progressive disclosure:

1. **`skills/rhel_ha_patching/skill.md`**:
   - **Name**: `rhel-ha-patching`
   - **Description**: "Standard Operating Procedure for zero-downtime rolling updates on Red Hat HA Pacemaker/Corosync clusters (SOP 2059253)."
   - **Content**: Detailed SOP procedure including:
     - Pre-checks with `ansible_pcs_health_check`.
     - Evacuating Node 1 with `ansible_pcs_node_standby`.
     - Applying patches with `ansible_patch_fleet` and rebooting with `ansible_reboot_fleet`.
     - Probing uptime with `ansible_check_host_online` and triggering out-of-band IPMI recovery with `ansible_console_power_on` if timed out.
     - Reintegrating Node 1 with `ansible_pcs_node_unstandby`.
     - Repeating the rolling cycle for Node 2.
     - Verifying final cluster quorum with `ansible_pcs_status` and dispatching notification with `ansible_send_email`.

2. **`skills/fleet_patching/skill.md`**:
   - **Name**: `fleet-patching`
   - **Description**: "Standard Operating Procedure for batch patching standalone Linux fleets with managed reboots and IPMI recovery."
   - **Content**: Detailed SOP procedure for batch DNF package updates, fleet reboots, TCP port 22 online verification, IPMI console power-on for hung nodes, and email reporting.

3. **`skills/rhel_diagnostics/skill.md`**:
   - **Name**: `rhel-diagnostics`
   - **Description**: "SOP for diagnosing cluster quorum, resource failcounts, journalctl errors, and kernel crash dumps."

4. **`skills/single_host_ops/skill.md`**:
   - **Name**: `single-host-ops`
   - **Description**: "SOP for targeted single-host remediations, package installs, filesystem expansions, and service lifecycle management."

---

### Phase 3: Refactor `agent_engine.py` with Declarative Deep Agent Primitives
Update [`app/agent_engine.py`](file:///home/fayez/agent2/deepagent_system/app/agent_engine.py):

1. **Root Agent Configuration (`create_deep_agent`)**:
   - **Model**: `ChatOpenAI` pointing to local Ollama.
   - **Tools**: MCP tools from Ansible Execution Server (`:8000`) and SOP Knowledge Server (`:8001`).
   - **Skills**: `skills=["./skills/"]` (enables progressive disclosure of skills).
   - **Built-in Planning**: Root agent instructed to use `write_todos` to plan, break down, and track complex user requests.

2. **Specialized Subagents (`subagents=[...]`)**:
   - **`ha_cluster_patcher`**:
     - Description: "Specialized subagent for Red Hat HA Pacemaker/Corosync cluster rolling updates per SOP 2059253."
     - Instructions: Mandatory use of `write_todos` to track: Pre-check ➔ Node 1 Standby ➔ Node 1 Patch & Reboot ➔ Node 1 Online Verify/IPMI ➔ Node 1 Unstandby ➔ Node 2 Cycle ➔ Cluster Post-check ➔ Email SRE Report.
   - **`fleet_patcher`**:
     - Description: "Specialized subagent for enterprise fleet package updates, managed reboots, and out-of-band IPMI console recovery."
     - Instructions: Mandatory use of `write_todos` to track: Host Discovery ➔ Batch DNF Patch ➔ Batch Reboot ➔ Port 22 Verify ➔ IPMI Console Power-On (if hung) ➔ Email SRE Report.
   - **`rhel_diagnostician`**:
     - Description: "Specialized subagent for cluster health pre-checks, node diagnostics, and log triage."
   - **`single_host_operator`**:
     - Description: "Specialized subagent for single-node package installs, service restarts, and filesystem expansions."

3. **Pure Agent Execution Function**:
   - Refactor `execute_subagent_workflow_orchestrator(user_query)` (or replace with direct `agent.ainvoke(...)` / `agent.astream(...)`) so that all operations execute dynamically through the LangGraph Deep Agent harness.

---

### Phase 4: Update Chat API & SSE Streaming
Update [`app/api/v1/chat.py`](file:///home/fayez/agent2/deepagent_system/app/api/v1/chat.py):
1. Invoke the native Deep Agent harness via `agent.astream(...)` / `agent.ainvoke(...)`.
2. Map LangGraph execution stream events (subagent delegation, tool calls, `write_todos` updates, and final markdown synthesis) to SSE events (`event: "step"`, `event: "status"`, `event: "token"`, `event: "done"`).
3. Preserve the 1.2s step pacing for human visual tracking in the Web UI.
4. Ensure full database message persistence with JSONB intermediate steps.

---

### Phase 5: Verification & Test Harness Execution
1. Sync all refactored code and skills into the rootless Podman containers (`deepagent-service`, `deepagent-webui`).
2. Run the complete Master Test Harness:
   ```bash
   python3 /home/fayez/agent2/deepagent_system/tests/run_all_verification_tests.py
   ```
3. Ensure all 7 verification test suites pass with a **100% success rate**.
4. Update documentation in `docs/` to reflect the pure Deep Agents architecture and skills structure.
5. Commit and push the changes to GitHub.
