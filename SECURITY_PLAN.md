# Security Remediation Plan - Phase 1 (Application & Logic Fixes)

## Objective
Address immediate critical and high-severity security vulnerabilities within the application code and local deployment configuration. This phase focuses on securing the Human-in-the-Loop (HITL) system, removing hardcoded secrets, and patching web vulnerabilities. Kubernetes migration and architectural segmentation are explicitly deferred to a later phase.

## Scope & Impact
- **Affected Components:** Ansible MCP Server (`ansible_mcp_server.py`), HITL Web Application (`hitl_web/app.py`), Database Schema (`db/init.sql`), Local Deployment (`docker-compose.yml`, setup scripts).
- **Impact:** Secures the agent's ability to execute commands, ensures approvals are cryptographically bound to specific actions, and prevents credential leakage in source control.

## Implementation Steps

### Step 0: Save Plan for Reference
- Save a copy of this remediation plan as `SECURITY_PLAN.md` in the root of the project directory for future reference.

### Step 1: Fix HITL Authorization Bypass (`ansible_mcp_server.py` & Database)
Currently, approvals are granted based on a fuzzy string match against the action summary.
- **Change:** Modify `hitl_request_approval` to generate and return a unique cryptographic nonce or strictly bind the approval to a specific action template name and execution timestamp.
- **Change:** Update `check_approval` to validate the specific unique identifier or strict payload parameters instead of using `ILIKE %{action_name}%`.
- **Validation:** Run `python3 test_ansible_complete.py` to ensure the new approval logic doesn't break tool execution.
- **Commit & Push:** Run `./push_to_github.sh` to commit and push the changes.

### Step 2: Secure Arbitrary Command Execution (`ansible_mcp_server.py`)
The tool for running arbitrary shell commands bypasses the HITL gate.
- **Change:** Add the `is_high_risk=True` flag to the `ansible_run_command` tool definition. This forces any arbitrary command execution request through the HITL approval workflow.
- **Validation:** Run `python3 test_ansible_complete.py`.
- **Commit & Push:** Run `./push_to_github.sh` to commit and push the changes.

### Step 3: Patch Web Application Vulnerabilities (`hitl_web/app.py`)
The Flask application is vulnerable to CSRF and lacks secure session configurations.
- **Change:** Integrate `Flask-WTF` to implement CSRF tokens on the `/resolve` POST endpoint.
- **Change:** Update Flask configuration to enforce secure session cookies (`SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`).
- **Validation:** Run `python3 test_ansible_complete.py`. The auto-approver in the test script may need updating to handle CSRF tokens.
- **Commit & Push:** Run `./push_to_github.sh` to commit and push the changes.

### Step 4: Remove Hardcoded Secrets
Secrets are currently committed in plaintext across multiple files.
- **Change:** Extract hardcoded credentials (`POSTGRES_PASSWORD`, `API_SERVER_KEY`, Flask `SECRET_KEY`) from `docker-compose.yml`, `db/init.sql`, and `hitl_web/app.py`.
- **Change:** Update these files to read from environment variables.
- **Change:** Create a `.env.example` template and update environment setup scripts (`env_setup_prod.sh`, etc.) to securely source these variables.
- **Change:** Update `test_ansible_complete.py` to source the `API_KEY` and HITL credentials from the environment instead of hardcoding them.
- **Validation:** Run `python3 test_ansible_complete.py`.
- **Commit & Push:** Run `./push_to_github.sh` to commit and push the changes.

### Step 5: Remove Podman Socket Mount
The Hermes agent currently mounts the podman socket, granting it root-level container privileges.
- **Change:** Remove the `- /run/user/1000/podman/podman.sock:/run/user/1000/podman/podman.sock:Z` volume mount from `docker-compose.yml`.
- **Change:** Remove the `- CONTAINER_HOST=unix:///run/user/1000/podman/podman.sock` environment variable from `docker-compose.yml`.
- **Validation:** Run `python3 test_ansible_complete.py`.
- **Commit & Push:** Run `./push_to_github.sh` to commit and push the changes.

## Verification & Testing
1. **HITL Integrity:** Attempt to execute a high-risk Ansible template. Verify it blocks execution without approval. Approve the request and verify it executes. Attempt to execute a *different* high-risk template immediately after; verify it is correctly blocked.
2. **Command Security:** Attempt to run an arbitrary command via `ansible_run_command`; verify it triggers the HITL gate.
3. **Web Security:** Inspect the web dashboard login and resolution flows to ensure CSRF tokens are present and enforced.
4. **Secrets Management:** Verify the application starts successfully when configured solely via environment variables without relying on hardcoded fallbacks.

## Migration & Rollback
- Since these changes modify the database schema (potentially) and application logic, a backup of the local database should be taken before applying. If issues occur, changes can be rolled back via git, and the database container can be recreated from the old schema.
