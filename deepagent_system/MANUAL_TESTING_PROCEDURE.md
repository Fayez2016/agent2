# Standard Operating Procedure: Manual Testing Runbook

**Document ID:** SOP-DEEPAGENT-TEST-001  
**Target System:** LangGraph Deep Agent (`deepagent_system`)  
**Scope:** Manual Verification of REST API, Subagents, MCP Bridge, HITL Approval Gate, and Web UI.

---

## Operational Overview

This procedure provides a step-by-step execution runbook for manually validating all core capabilities of the Deep Agent system. Follow each phase sequentially and record pass/fail results in the verification matrix at the end of this document.

---

## Phase 0: Pre-Flight Check & Service Initialization

### Step 0.1: Check Container Service Status
Run the container status check:
```bash
podman ps --filter name=deepagent --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

**Pass Criteria:**
All 7 microservices must show status `Up`:
- `deepagent-service` (`8642`)
- `deepagent-webui` (`3000`)
- `deepagent-ollama` (`11434`)
- `deepagent-ansible-mcp` (`8000`)
- `deepagent-hitl-web` (`5001`)
- `deepagent-hitl-db` (`5432`)
- `deepagent-aap-server` (`5000`)

---

### Step 0.2: Verify REST API Health Endpoint
Run the curl health probe:
```bash
curl -i http://localhost:8642/health
```

**Pass Criteria:**
HTTP status `200 OK` with JSON body:
```json
{"status":"ok","service":"deepagent-core"}
```

---

### Step 0.3: Verify HITL Web Portal Login Page
Open a web browser or run curl against the approval portal:
```bash
curl -i http://localhost:5001
```

**Pass Criteria:**
HTTP status `200 OK` rendering the HITL portal login screen.

---

## Phase 1: Low-Risk Diagnostic Operation (Auto-Execution)

Low-risk operational queries (e.g., status checks, quorum diagnostics) must execute automatically without requiring human approval.

### Step 1.1: Submit Low-Risk Query via cURL
Run the following request in your terminal:
```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "deepagent",
    "messages": [
      {
        "role": "user",
        "content": "Check the Pacemaker cluster health for host rhel-prod-01"
      }
    ]
  }'
```

### Step 1.2: Verify Response & Auto-Execution
Inspect the terminal output.

**Pass Criteria:**
1. HTTP Response status is `200 OK`.
2. Response content includes cluster status details from `ansible_pcs_health_check`.
3. No pending request was created in `hitl-web` (no approval prompt required).

---

## Phase 2: High-Risk Action & HITL Approval Gate Verification

High-risk infrastructure operations (e.g., host reboot, cluster standby, VM reset) MUST be intercepted by the HITL gate and hold execution until manually approved on Port `5001`.

### Step 2.1: Submit High-Risk Reboot Command (Terminal 1)
In Terminal 1, execute:
```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "deepagent",
    "messages": [
      {
        "role": "user",
        "content": "Reboot the host rhel-prod-01"
      }
    ]
  }'
```
*Note: Terminal 1 will pause waiting for authorization.*

---

### Step 2.2: Perform HITL Approval in Browser
1. Open web browser to: `http://localhost:5001`
2. Log in using administrator credentials:
   - **Username:** `admin`
   - **Password:** `admin123`
3. Locate the `PENDING` request table.
4. Verify request details:
   - **Tool Name:** `Reboot Host` (`ansible_reboot_host`)
   - **Target Host:** `rhel-prod-01`
   - **Status:** `PENDING`
5. Click **Approve**.

---

### Step 2.3: Verify Completion in Terminal 1
Return to Terminal 1.

**Pass Criteria:**
1. Within 2-4 seconds of clicking **Approve**, Terminal 1 receives the completion payload.
2. HTTP status is `200 OK`.
3. Response confirms `Reboot Host` playbook execution against `rhel-prod-01`.

---

## Phase 3: Custom Subagents Delegation Verification

Verify that specialized subagents in `.deepagents/agents/` (`rhel-diagnostics` and `fleet-patcher`) are invoked correctly.

### Step 3.1: Test Diagnostic Subagent (`rhel-diagnostics`)
Run:
```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "deepagent",
    "messages": [
      {
        "role": "user",
        "content": "Delegate to rhel-diagnostics subagent to inspect CIB constraints on node rhel-prod-02"
      }
    ]
  }'
```

**Pass Criteria:**
Response confirms delegation to subagent `rhel-diagnostics` and provides CIB constraint results.

---

### Step 3.2: Test Fleet Patching Subagent (`fleet-patcher`)
Run:
```bash
curl -X POST http://localhost:8642/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer hermes-api-secret" \
  -d '{
    "model": "deepagent",
    "messages": [
      {
        "role": "user",
        "content": "Delegate to fleet-patcher subagent to check security updates on rhel-prod-01"
      }
    ]
  }'
```

**Pass Criteria:**
Response confirms delegation to subagent `fleet-patcher` and returns DNF update status.

---

## Phase 4: Control Panel Web UI Testing (`Port 3000`)

### Step 4.1: Access Web UI Dashboard
1. Open web browser to `http://localhost:3000`.
2. Verify rendering of the **LangGraph Deep Agent Control Panel** header.

### Step 4.2: Execute UI Operational Prompt
1. Type into the message prompt bar:
   ```text
   Check the Pacemaker cluster health for host rhel-prod-01
   ```
2. Click **Send** (or press Enter).

**Pass Criteria:**
1. UI displays user message bubble.
2. UI displays status indicator `"Deep Agent reasoning & executing tools..."`.
3. UI renders the assistant response bubble with cluster health results.

---

## Phase 5: Automated Verification Test Run

Run the automated test runner to validate all assertions programmatically:
```bash
python3 deepagent_system/run_deepagent_tests.py
```

**Pass Criteria:**
Output must finish with:
```text
==========================================================================
 ALL TESTS PASSED SUCCESSFULLY! Deep Agent & HITL Gate Verified.
==========================================================================
```

---

## Manual Test Verification Sign-Off Matrix

| Phase | Test Description | Execution Method | Expected Result | Pass / Fail |
| :--- | :--- | :--- | :--- | :---: |
| **Phase 0** | Core API Health Check | `curl http://localhost:8642/health` | Status `200 OK` | `[ ]` |
| **Phase 1** | Low-Risk Auto Execution | `curl -X POST .../v1/chat/completions` | Instant response, no HITL | `[ ]` |
| **Phase 2** | High-Risk HITL Interception | Submit reboot + Approve on `:5001` | Execution pauses until approved | `[ ]` |
| **Phase 3** | Diagnostic Subagent | Submit query targeting `rhel-diagnostics` | Subagent invoked & results returned | `[ ]` |
| **Phase 3** | Fleet Patching Subagent | Submit query targeting `fleet-patcher` | Subagent invoked & results returned | `[ ]` |
| **Phase 4** | Web Control Panel UI | Access `http://localhost:3000` | UI streams chat completion | `[ ]` |
| **Phase 5** | Automated Test Suite | `python3 run_deepagent_tests.py` | All 4 stages pass | `[ ]` |
