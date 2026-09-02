#!/usr/bin/env bash
# ==============================================================================
#  ✉️ Automated Air-Gapped Code Patch & Gmail Dispatcher
# ==============================================================================
#  Packages lightweight Python code, subagent prompts, and FastMCP tools (< 2MB)
#  and delivers the archive directly to your Gmail inbox.
# ==============================================================================

set -euo pipefail

TO_EMAIL="${1:-fayez.soufyani@gmail.com}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PATCH_NAME="deepagent_code_patch_${TIMESTAMP}"
OUT_DIR="/tmp/${PATCH_NAME}"
TAR_FILE="/tmp/${PATCH_NAME}.tar.gz"

echo "================================================================================"
echo " 📦 PACKAGING LIGHTWEIGHT CODE PATCH FOR AIR-GAPPED ENVIRONMENT"
echo " 📧 Recipient : ${TO_EMAIL}"
echo " 🕒 Timestamp : ${TIMESTAMP}"
echo "================================================================================"

rm -rf "${OUT_DIR}" "${TAR_FILE}"
mkdir -p "${OUT_DIR}/deepagent_system"

# Copy all application code, prompts, and MCP servers (ignoring virtual environments/caches)
echo -n "  📂 Collecting application files and FastMCP tools ... "
rsync -av --exclude '__pycache__' \
          --exclude '*.pyc' \
          --exclude '.git' \
          --exclude 'node_modules' \
          --exclude 'venv' \
          --exclude '.venv' \
          --exclude 'raw_traces' \
          /home/fayez/agent2/deepagent_system/ \
          "${OUT_DIR}/deepagent_system/" >/dev/null

cp /home/fayez/agent2/system_updater.sh "${OUT_DIR}/" 2>/dev/null || true
echo "✓ Done."

# Create archive
echo -n "  🗜️ Compressing code patch archive ... "
tar -czf "${TAR_FILE}" -C /tmp "${PATCH_NAME}"
PATCH_SIZE=$(du -h "${TAR_FILE}" | cut -f1)
echo "✓ Done (${PATCH_SIZE})"

# Generate summary changelog
CHANGELOG_FILE="/tmp/${PATCH_NAME}_changelog.txt"
cat << EOM > "${CHANGELOG_FILE}"
Deep Agent Air-Gapped Code Patch Update
Timestamp: ${TIMESTAMP}
Archive: ${PATCH_NAME}.tar.gz (${PATCH_SIZE})

Contents:
- Core LangGraph Deep Agent API & Orchestration
- Ansible FastMCP Server (Port 8000) with Embedded Python Security Guard
- SOP FastMCP Server (Port 8001) for Declarative HA Patching
- PostgreSQL Database Initialization & Migration Schemas
- General-Purpose System Updater (system_updater.sh)

Installation on Air-Gapped Production Server:
1. Copy ${PATCH_NAME}.tar.gz to /opt/deepagent/
2. Run: ./apply_airgap_patch.sh ${PATCH_NAME}.tar.gz
EOM

# Dispatch via Python SMTP / Mailer script
echo -n "  ✉️ Dispatching patch to ${TO_EMAIL} ... "
python3 - << PYEOF
import os, sys, smtplib, ssl
from email.message import EmailMessage

to_addr = "${TO_EMAIL}"
tar_path = "${TAR_FILE}"
changelog_path = "${CHANGELOG_FILE}"

with open(changelog_path, 'r') as f:
    changelog_text = f.read()

msg = EmailMessage()
msg['Subject'] = f"🚀 [Deep Agent Update] Code Patch ${TIMESTAMP} (${PATCH_SIZE})"
msg['From'] = "deepagent-bot@local.corp"
msg['To'] = to_addr
msg.set_content(changelog_text)

with open(tar_path, 'rb') as f:
    file_data = f.read()
    file_name = os.path.basename(tar_path)
    msg.add_attachment(file_data, maintype='application', subtype='gzip', filename=file_name)

# If system mailer is available or local sendmail:
sent = False
try:
    with smtplib.SMTP('localhost', 25, timeout=5) as s:
        s.send_message(msg)
        sent = True
except Exception:
    pass

if not sent:
    # Save formatted email bundle to outbox
    outbox_dir = "/home/fayez/agent2/patch_outbox"
    os.makedirs(outbox_dir, exist_ok=True)
    out_path = os.path.join(outbox_dir, f"{file_name}.eml")
    with open(out_path, 'wb') as f:
        f.write(msg.as_bytes())
    print(f"\n  ℹ️ SMTP relay offline. EML message with patch attachment saved to: {out_path}")
else:
    print(f"✓ Dispatched successfully to {to_addr}")
PYEOF

echo -e "\n================================================================================"
echo " 🎉 PATCH READY: ${TAR_FILE} (${PATCH_SIZE})"
echo "================================================================================"
