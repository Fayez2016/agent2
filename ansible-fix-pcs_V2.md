---
name: ansible-fix-pcs
description: Fixes PCS cluster issues on a specific host using Ansible Automation Platform (AAP).
version: 1.2.0
metadata:
  hermes:
    tags: [ansible, pcs, cluster, devops]
---

# Ansible: Fix PCS Cluster

## Workflow
### Phase 1: Execution
Use the `terminal` tool to execute the Python runner script.

**Example:**
```json
terminal(command="python /opt/data/skills/devops/ansible-fix-pcs/scripts/run.py --hostname \"test-server\" --action \"cleanup\" --resource \"p_fs_app\"")
```
