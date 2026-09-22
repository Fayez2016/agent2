# Deep Agent — Lightweight GitLab Sync & Resilient Systemd Service Guide

This guide explains how to:
1. **Push your frequently changed operational assets** (Playbooks, Skills, Prompts, and Schema) to your enterprise GitLab repository under strict repository size limits (< 500 KB total).
2. **Deploy the automated systemd startup service** that pulls the latest operational changes on server boot or service restart, with a **guaranteed non-blocking failsafe** if GitLab is unreachable.

---

## 1. Size Constraints & Asset Packaging (Under 500 KB Total!)

To strictly avoid exceeding repository size quotas or slow clone times:
* **Excluded**: All `.tar`, `.tar.gz`, ISOs, container images, virtual environments, and database data files.
* **Included**: Only text-based operational assets:
  - `ansible_playbooks/*.yml` (All 11 production playbooks)
  - `skills/**/*.md` (All declarative SOPs & operational guidelines)
  - `prompts/prompts.py` (Subagent prompts & system directives)
  - `db/init.sql` (Clean schema definition)
* **Total Staged Size**: **~360 KB** (tested and verified!).

---

## 2. Script 1: Push Assets to GitLab (`push_deepagent_assets_to_gitlab.sh`)

### How to Use It:
Run this script whenever you make updates to prompts, SOPs, or playbooks:

```bash
./push_deepagent_assets_to_gitlab.sh <GITLAB_REPO_URL> [BRANCH]
```

### Example:
```bash
./push_deepagent_assets_to_gitlab.sh https://gitlab.corp.internal/sre/deepagent-playbooks.git main
```

### What It Does Automatically:
1. Staging only the `.yml`, `.md`, and `.py` operational files.
2. Injects a strict `.gitignore` to prevent any large tarballs from ever being pushed.
3. Commits and pushes the clean updates to GitLab.

---

## 3. Script 2: Resilient Startup Sync (`deepagent_git_sync.sh`)

### Failsafe Architecture (Learned from `offline_install.sh`):
* **No Blocking on Failure**: If GitLab is offline, internal DNS fails, or credentials expire, the script logs:
  `⚠️ Warning: Could not connect to GitLab. Retaining existing assets.`
  and **exits with return code 0**. It will **NEVER** abort systemd or stop the agent from running!
* **Hot Asset Injection**: If updates are pulled while the container is already running, it copies the new skills and prompts into the container dynamically without container recreation.

---

## 4. Systemd Unit Service (`deepagent.service`)

This service manages Deep Agent on RHEL / CentOS as a system service.

### Service File Definition (`deepagent.service`):
```ini
[Unit]
Description=Deep Agent Autonomous SRE Orchestration Platform
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=%h/agent2
EnvironmentFile=-%h/agent2/.env.production

# 1. Non-blocking Pre-Execution: Sync latest playbooks/prompts from GitLab (failsafe: exit 0 on offline)
ExecStartPre=-%h/agent2/deepagent_git_sync.sh

# 2. Main Execution: Launch unified 7-microservice pod with self-healing DB & TLS
ExecStart=%h/agent2/offline_install.sh

# 3. Clean Stop: Gracefully remove pod and containers on systemd stop
ExecStop=/usr/bin/podman pod stop deepagent-prod-pod
ExecStopPost=/usr/bin/podman pod rm -f deepagent-prod-pod

TimeoutStartSec=180
TimeoutStopSec=30
Restart=no

[Install]
WantedBy=default.target
```

### Installation on Target Server (`ps501484.aramco.com`):

To install as a **user service** in rootless Podman:
```bash
# 1. Copy unit file to user systemd directory:
mkdir -p ~/.config/systemd/user/
cp deepagent.service ~/.config/systemd/user/

# 2. Enable lingering (so agent stays running after logout):
loginctl enable-linger $(whoami)

# 3. Reload systemd daemon:
systemctl --user daemon-reload

# 4. Enable and start Deep Agent:
systemctl --user enable --now deepagent.service
```

### Verification & Management Commands:
```bash
# Check status:
systemctl --user status deepagent.service

# Restart agent (triggers GitLab sync check then boots pod):
systemctl --user restart deepagent.service

# View systemd logs:
journalctl --user -u deepagent.service -f
```
