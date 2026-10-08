#!/usr/bin/env bash
# ==============================================================================
# 🧪 Deep Agent: Email Notification & VMware vCenter VM Reset Test Harness
# ==============================================================================
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 🧪 TESTING EMAIL NOTIFICATION & VMWARE VCENTER VM RESET TEMPLATES            ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# Run inside deepagent-ansible-mcp container where AAP MCP tools and dependencies live
podman exec -i deepagent-ansible-mcp python3 - << 'PY_EOF'
import sys
import json
import time

try:
    from ansible_mcp_server import ansible_send_email, ansible_vmware_reset
except ImportError:
    import os
    sys.path.insert(0, "/app")
    sys.path.insert(0, "/home/hermes")
    from ansible_mcp_server import ansible_send_email, ansible_vmware_reset

print("\n" + "="*76)
print(" 1. TESTING EMAIL NOTIFICATION TEMPLATE ('Send Email Notification')")
print("="*76)

recipient = "fayez.soufyani@gmail.com"
subject = "[SRE Pre-Flight Test] Automated Deep Agent Notification"
body = "Automated test notification from Deep Agent. Validating AAP SMTP dispatch."

print(f"Target Recipient : {recipient}")
print(f"Subject          : {subject}")
print("Executing tool   : ansible_send_email ...")

email_raw = ansible_send_email(recipient=recipient, subject=subject, body=body)
try:
    email_data = json.loads(email_raw)
    status = email_data.get("status", "unknown")
    print(f"Status           : {status.upper()}")
    print("Output Snippet   :\n" + "\n".join(email_data.get("output", "").strip().split("\n")[:10]))
    if status == "successful":
        print("✓ Email Notification Template PASSED!")
    else:
        print(f"⚠️ Email template returned status: {status}")
except Exception as e:
    print(f"Raw Output: {email_raw}")

print("\n" + "="*76)
print(" 2. TESTING VMWARE VCENTER VM RESET TEMPLATE ('VMware VM Reset')")
print("="*76)

target_vm = "rhel-app01.enterprise.local"
print(f"Target VM Name   : {target_vm}")
print("Executing tool   : ansible_vmware_reset (Hard Power Reset) ...")

vm_raw = ansible_vmware_reset(vm_name=target_vm)
try:
    vm_data = json.loads(vm_raw)
    status = vm_data.get("status", "unknown")
    print(f"Status           : {status.upper()}")
    print("Output Snippet   :\n" + "\n".join(vm_data.get("output", "").strip().split("\n")[:10]))
    if status == "successful":
        print("✓ VMware vCenter VM Reset Template PASSED!")
    else:
        print(f"⚠️ VMware reset template returned status: {status}")
except Exception as e:
    print(f"Raw Output: {vm_raw}")

print("\n" + "="*76)
print(" 🏁 TEST SUMMARY COMPLETE")
print("="*76)
PY_EOF
