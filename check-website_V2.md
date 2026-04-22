---
name: check-website
description: Checks the HTTP status code of a given URL to verify connectivity.
version: 1.2.0
metadata:
  hermes:
    tags: [network, http, connectivity]
---

# Network: Check Website

## Workflow
### Phase 1: Execution
Use the `terminal` tool to execute the Python runner script.

**Example:**
```json
terminal(command="python /opt/data/skills/network/check-website/scripts/run.py --url \"https://google.com\"")
```
