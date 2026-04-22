---
name: ansible-install-package
description: Installs a package on a remote host using DNF/YUM via Ansible Automation Platform (AAP).
version: 1.2.0
metadata:
  hermes:
    tags: [ansible, packages, devops, linux]
---

# Ansible: Install Package

## Workflow
### Phase 1: Execution
Use the `terminal` tool to execute the Python runner script.

**Example:**
```json
terminal(command="python /opt/data/skills/devops/ansible-install-package/scripts/run.py --hostname \"test-server\" --package_name \"vim\"")
```
