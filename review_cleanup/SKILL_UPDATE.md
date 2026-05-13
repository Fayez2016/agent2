---
name: ansible-run-command
description: Executes a shell command on a specific remote Linux system via Ansible. MANDATORY for remote tasks.
version: 1.1.0
---
# ansible-run-command

Executes a shell command on a remote Linux system via Ansible Automation Platform.

## Usage
`python scripts/run.py --command "<command>" --hostname "<hostname>"`

## Arguments
- `command`: The shell command to execute.
- `hostname`: The target hostname or IP address.

## Examples
- Prompt: "Check uptime on host1" -> Use this skill.
- Prompt: "df -h on webserver" -> Use this skill.
