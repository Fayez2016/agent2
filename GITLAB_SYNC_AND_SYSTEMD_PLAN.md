# Architecture & Implementation Plan: Lightweight GitLab Sync & Resilient Systemd Agent Service

This plan defines the strategy to package and sync frequently changed Deep Agent assets (prompts, skills, SOPs, and agent configs) to your enterprise GitLab repository, paired with an automated, resilient systemd service that updates assets on startup without ever blocking or failing the agent.

---

## 1. Size Constraints & Asset Selection Analysis

To comply with enterprise repository size quotas:
- **Total Payload Size**: ~650 KB (less than 1 MB total!).
- **Zero Heavy Binaries**: No container image tarballs (`.tar` / `.tar.gz`) or virtual environments (`.venv`).
- **Files to Sync**:
  1. `ansible_playbooks/`: All 11 production YAML playbooks.
  2. `skills/`: Declarative Markdown SOPs (`fleet_patching`, `rhel_ha_patching`, `rhel_diagnostics`, `single_host_ops`).
  3. `prompts/`: Python prompt definitions and subagent directives (`prompts.py`).
  4. `configs/`: Non-sensitive baseline configurations and supervisor settings.

---

## 2. Component 1: `push_deepagent_assets_to_gitlab.sh`

### Objectives:
- Assembles only the lightweight, frequently updated operational files into a clean workspace.
- Enforces strict `.gitignore` to prevent accidental inclusion of tarballs, logs, and database dumps.
- Commits and pushes the updates to the target GitLab repository.
- Non-interactive and idempotent.

---

## 3. Component 2: `deepagent-sync.service` & `deepagent.service` (Systemd)

### Resilience Architecture (Learned from `offline_install.sh`):
1. **Never Block Agent Startup**:
   - If GitLab is offline, DNS is unreachable, or authentication fails, the sync step logs a warning and **exits with code 0**. The agent continues running using its current local/baked-in assets.
2. **Graceful Mount / Copy**:
   - When updates are pulled from GitLab, the service syncs them into `/opt/deepagent/live_assets/` (or copies them into the running container / persistent host volume).
3. **Automated Pod Management**:
   - Executes the proven startup sequence from `offline_install.sh` (storage tuning, database health verification, TCP-only PostgreSQL, reverse proxy TLS, and granular health matrix).

---

## 4. Execution & Testing Stages

1. **Stage 1**: Create `push_deepagent_assets_to_gitlab.sh` and test locally on simulated repository.
2. **Stage 2**: Create `deepagent-git-sync.sh` (the startup sync script) and test failure modes (offline, DNS failure, merge conflict).
3. **Stage 3**: Create `deepagent.service` systemd unit file with rootless Podman execution parameters.
4. **Stage 4**: Verify that neither script introduces volume mount or permission bugs previously resolved in `offline_install.sh`.
