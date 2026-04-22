---
name: ansible-expand-fs
description: Expands a filesystem on a remote host (VMware/Physical) using Ansible Automation Platform (AAP).
version: 1.2.0
metadata:
  hermes:
    tags: [ansible, storage, devops, linux]
---

# Ansible: Expand Filesystem

## Workflow
### Phase 1: Execution
Use the `terminal` tool to execute the Python runner script.

**Example:**
```json
terminal(command="python /opt/data/skills/devops/ansible-expand-fs/scripts/run.py --hostname \"test-server\" --mount_point \"/var\" --size_gb 10")
```
