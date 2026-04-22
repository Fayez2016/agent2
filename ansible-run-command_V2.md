---
name: ansible-run-command
description: Executes a shell command on a specific remote Linux system via Ansible Automation Platform (AAP).
version: 1.2.0
metadata:
  hermes:
    tags: [ansible, remote-execution, devops, linux]
    related_skills: [ansible-reboot-host, ansible-install-package]
---

# Ansible: Run Remote Command

## Overview
This skill allows you to execute any shell command on a remote RHEL/CentOS system using the Ansible Automation Platform.

## Prerequisites
- The `terminal` toolset must be available.
- Environment variables `AAP_HOST` and `AAP_TOKEN` must be configured.

## Workflow

### Phase 1: Preparation
1. Identify the **command** to run (e.g., `uptime`, `df -h`).
2. Identify the **target hostname**.

### Phase 2: Execution
Use the `terminal` tool to execute the Python runner script with the required arguments.

**Command Template:**
```bash
python /opt/data/skills/devops/ansible-run-command/scripts/run.py --command "<command>" --hostname "<hostname>"
```

**Example:**
To check uptime on `test-server`, call:
```json
terminal(command="python /opt/data/skills/devops/ansible-run-command/scripts/run.py --command \"uptime\" --hostname \"test-server\"")
```

## Tips
- **DO NOT** try to call `skill_view` with the hostname.
- **DO NOT** use the local `uptime` command; always use this script for remote hosts.
- Always provide the full absolute path to the script as shown above.
