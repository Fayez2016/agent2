---
name: ansible-reboot-host
description: Reboots a specific remote host using Ansible Automation Platform (AAP).
version: 1.2.0
metadata:
  hermes:
    tags: [ansible, reboot, devops, linux]
    related_skills: [ansible-run-command]
---

# Ansible: Reboot Host

## Workflow
### Phase 1: Execution
Use the `terminal` tool to execute the Python runner script.

**Example:**
```json
terminal(command="python /opt/data/skills/devops/ansible-reboot-host/scripts/run.py --hostname \"test-server\"")
```
