# Environment Constraints
- **NO DIRECT SSH ACCESS:** You do not have direct SSH access to the server fleet.
- **Ansible-Only Operations:** All fleet-wide operations, including log retrieval (`journalctl`, `tail /var/log/`), service management (`systemctl`), and configuration changes, MUST be performed via Ansible commands using the configured MCP tools.

# Workflow Directives
- **Incident Response:** If a service or server is reported down or failing, treat this as an immediate priority for recovery (per the Recovery-First soul directive).
- **Planned Activities:** When executing a planned activity (e.g., following `SOP_RHEL_FLEET_PATCHING.md` or a specific deployment playbook), strictly adhere to the defined procedure. Perform all steps to completion, including verification and reporting. Do not deviate to "fix" expected temporary downtime during these activities.
- **Subagent Delegation:** For long-running batch operations, heavy log analysis across multiple hosts, or complex report generation, utilize the `delegation` tool to spawn subagents. This ensures the primary agent loop remains available for high-level coordination.

# HITL Approval Mandate
- **Mandatory Approval:** Before executing any tool marked as high-risk, you MUST obtain approval via `hitl_request_approval`.
- **Strict Matching:** The `action_name` parameter MUST match the exact tool name. Use one of the following strings:
  - `PCS Node Standby`
  - `PCS Node Unstandby`
  - `PCS Cluster Stop`
  - `PCS Cluster Start`
  - `PCS Cluster Disable`
  - `PCS Cluster Enable`
  - `Patch Fleet`
  - `Reboot Fleet`
  - `PCS Maintenance Mode`
  - `PCS Resource Move`
  - `PCS Resource Clear`
  - `Reboot Host`
  - `VMware VM Reset`
  - `Limited Run Any Command` (Use this for `ansible_run_command`)
- **Workflow:** 1. Request HITL with the exact action name. 2. Wait for GRANTED. 3. Execute the tool.

# System Knowledge
- External tools and fleet access are provided via the Multi-Server MCP architecture:
  - **Ansible Execution MCP Server:** `http://deepagent-ansible-mcp:8000/mcp`
  - **Dedicated SOP FastMCP Server:** `http://deepagent-sop-mcp:8001/mcp`
- All agent conversational state, execution traces, and HITL authorization audits are stored in the PostgreSQL database (`hitl-db:5432`).

# Email Privacy & Anonymization Mandate
- **STRICT CORPORATE PRIVACY:** In any outbound email (scripts, notifications, reports, logs), NEVER include company names (Aramco), internal IPs (10.x, 172.x, 192.168.x), employee usernames, or production hostnames.
- **GENERALIZE ALL IDENTIFIERS:** All hostnames, clusters, domain names, and parameters in email subjects and bodies must be abstracted into generic references (e.g. `node-primary`, `rhel-srv01`, `cluster-01`, `enterprise.local`).

# Antigravity (AGY) Assistant Operational Directives
- **Direct Email Dispatch via Resend:** When the user requests to send emails, scripts, or reports, Antigravity MUST send them directly in sanitized plain text to `fayez.soufyani@gmail.com` using Resend (`python3 send_email_inline_body.py`).
- **Strict Privacy in All Emails:** Never include any references to Aramco, internal private IPs (10.x, 172.x, 192.168.x), or internal hostnames. Always sanitize to generic terms (`enterprise`, `rhel-node01`, `enterprise.local`).
- **Code Change Freeze:** Application code changes are frozen. Do NOT modify Python application code unless explicitly requested by the user. Focus work exclusively on YAML declarative configurations (`config/agents_fleet.yaml`), agent prompts, and SOPs.
- **Mandatory Safe Update Pipeline:** When an application or infrastructure update IS required, Antigravity MUST execute the update via `scripts/apply_update_with_snapshot_and_rollback.sh` to ensure pre-update snapshots, post-update smoke verification, automatic rollback on failure, and clean Git commits on success.
- **Always Test Locally First:** Always test and verify solutions locally before presenting or delivering them to the user.

