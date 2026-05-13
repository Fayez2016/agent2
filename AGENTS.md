# Environment Constraints
- **NO DIRECT SSH ACCESS:** You do not have direct SSH access to the server fleet.
- **Ansible-Only Operations:** All fleet-wide operations, including log retrieval (`journalctl`, `tail /var/log/`), service management (`systemctl`), and configuration changes, MUST be performed via Ansible commands using the configured MCP tools.

# Workflow Directives
- **Incident Response:** If a service or server is reported down or failing, treat this as an immediate priority for recovery (per the Recovery-First soul directive).
- **Planned Activities:** When executing a planned activity (e.g., following `SOP_RHEL_FLEET_PATCHING.md` or a specific deployment playbook), strictly adhere to the defined procedure. Perform all steps to completion, including verification and reporting. Do not deviate to "fix" expected temporary downtime during these activities.
- **Subagent Delegation:** For long-running batch operations, heavy log analysis across multiple hosts, or complex report generation, utilize the `delegation` tool to spawn subagents. This ensures the primary agent loop remains available for high-level coordination.

# System Knowledge
- External tools and fleet access are provided via the `ansible` MCP server at `http://ansible-mcp:8000/mcp`.
- All agent state and persistent configuration are stored in the `/opt/data` directory (mapped to `./.hermes/` on the host).
