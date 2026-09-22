# Deep Agent Multi-Model Architecture & Operations Guide

This guide details how to switch between your available enterprise models and how multi-model orchestration works across the Deep Agent harness.

---

## 1. What You Have: Model Characteristics

All three models share the **same API Token and Enterprise Gateway Endpoint**:

| Model Identifier | Primary Strength | Best Used For |
| :--- | :--- | :--- |
| **`Qwen/Qwen3.8-27B`** | Balanced Generalist | Routine fleet maintenance, general SRE conversations, single-node reboots and updates. |
| **`zai-org/GLM-5.3 Flash`** | High Throughput & Ultra-Low Latency | Rapid monitoring, alarm storm triage (`event_batcher`), quick connectivity/uptime checks. |
| **`deepseek-v4`** | Advanced Multi-Step Reasoning | Complex HA split-brain diagnosis, multi-cluster rolling update planning, tricky kernel post-mortems. |

---

## 2. Can You Use 2 or 3 Models at the Same Time?

### **Yes! Here is how it works:**

The Deep Agent architecture is a **Hierarchical Multi-Agent Swarm** powered by LangGraph. Because domain agents and subagents are stored in PostgreSQL, you are **not restricted to a single model globally**:

### Architecture Pattern: Hierarchical Model Specialization
1. **Primary Supervisor Agent (e.g. `deepseek-v4`)**:
   - Handles high-level reasoning, user intent, safety analysis, and decomposing complex incidents into sub-tasks.
2. **Fast Subagents (e.g. `zai-org/GLM-5.3 Flash`)**:
   - Execute fast repetitive tasks such as `Check Host Online`, log retrieval, or polling cluster statuses.
3. **Execution Patcher (e.g. `Qwen/Qwen3.8-27B`)**:
   - Manages standard package upgrades and reboot playbooks.

---

## 3. How to Switch the Active Model

### Method A: Instant SQL Switch (Zero Downtime, 1 Second)
You do not need to restart any containers. Run this command on host `ps501484` to instantly switch the model for all future conversations:

#### Switch to GLM-5.3 Flash:
```bash
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "
UPDATE domain_agents SET model_name = 'zai-org/GLM-5.3 Flash', updated_at = NOW() WHERE key_name = 'linux_sre';
UPDATE system_settings SET value = 'zai-org/GLM-5.3 Flash', updated_at = NOW() WHERE key = 'custom_openai_model';
"
```

#### Switch to DeepSeek-v4:
```bash
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "
UPDATE domain_agents SET model_name = 'deepseek-v4', updated_at = NOW() WHERE key_name = 'linux_sre';
UPDATE system_settings SET value = 'deepseek-v4', updated_at = NOW() WHERE key = 'custom_openai_model';
"
```

#### Switch back to Qwen-27B:
```bash
podman exec -i -e PGPASSWORD=secret456 deepagent-hitl-db psql -h 127.0.0.1 -U hermes -d hitl -c "
UPDATE domain_agents SET model_name = 'Qwen/Qwen3.8-27B', updated_at = NOW() WHERE key_name = 'linux_sre';
UPDATE system_settings SET value = 'Qwen/Qwen3.8-27B', updated_at = NOW() WHERE key = 'custom_openai_model';
"
```

---

### Method B: Via `gateway.conf` Configuration File
Edit `gateway.conf`:
```bash
GATEWAY_URL="https://<your_gateway>/v1"
MODEL_NAME="deepseek-v4"   # Set to desired model name
API_TOKEN="<your_token>"
API_PORT="8642"
```
And run `./restore_and_setup_service_tls.sh`. The script will detect the change, apply it to the database, and run a live test.

---

## 4. How to Assign Different Models to Different Subagents Simultaneously

In `deepagent-hitl-db`, the `domain_agents` table holds subagent definitions in the `subagents` JSON column. You can specify a dedicated `model_name` for specific subagents:

```sql
UPDATE domain_agents
SET subagents = jsonb_set(
    subagents,
    '{0,model_name}',
    '"zai-org/GLM-5.3 Flash"'
)
WHERE key_name = 'linux_sre';
```
This enables heterogeneous model swarms where light fast models handle telemetry and heavy reasoning models handle complex planning.

---

## 5. Next Planned Milestone: Multi-Model Swarm Investigation Task

- [ ] **Task: Investigate & Benchmark Heterogeneous Multi-Model Implementation**
  - **Objective**: Formulate an optimal routing matrix across `deepseek-v4`, `zai-org/GLM-5.3 Flash`, and `Qwen/Qwen3.8-27B`.
  - **Scope & Items to Evaluate**:
    1. **Primary Supervisor Delegation**: Test routing primary orchestrator loop through `deepseek-v4` for enhanced planning, safety assertions, and complex SOP reasoning.
    2. **Fast Telemetry Subagents**: Test binding `zai-org/GLM-5.3 Flash` to `event_batcher`, `rhel_diagnostician`, and `Check Host Online` loops to minimize latency and token overhead.
    3. **Operational Workhorse**: Retain `Qwen/Qwen3.8-27B` for standard playbook invocations (`Patch Fleet`, `Reboot Fleet`).
    4. **Failure Fallback Matrix**: Implement automatic failover logic (e.g., if one model encounters rate limits or latency spikes, automatically fallback to secondary model).
    5. **Database Schema Support**: Validate that `subagents` JSON schema in PostgreSQL passes distinct `model_name` and `model_provider` parameters into `create_deep_agent(...)` dynamically.
