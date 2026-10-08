#!/usr/bin/env bash
# ==============================================================================
# ⏰ Deep Agent: Rootless Systemd Daily Backup Timer Setup
# ==============================================================================
# Schedules backup_deepagent_all.sh to run automatically every night at 02:00 AM
# using native systemd user timers (replaces cron, works rootless without sudo).
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="${SCRIPT_DIR}/backup_deepagent_all.sh"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

mkdir -p "${SYSTEMD_USER_DIR}"
chmod +x "${BACKUP_SCRIPT}"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} ⏰ DEEP AGENT DAILY BACKUP SYSTEMD TIMER SETUP                               ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Create the systemd service unit
SERVICE_FILE="${SYSTEMD_USER_DIR}/deepagent-backup.service"
echo -e "\n${BOLD}[1/3] Creating systemd service unit: ${SERVICE_FILE}...${NC}"

cat << SERVICE_EOF > "${SERVICE_FILE}"
[Unit]
Description=Deep Agent Unified Platform Full Backup Service
Documentation=file://${BACKUP_SCRIPT}
After=network.target

[Service]
Type=oneshot
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${BACKUP_SCRIPT}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
SERVICE_EOF

echo -e "${GREEN}✓ Created ${SERVICE_FILE}.${NC}"

# 2. Create the systemd timer unit (Runs daily at 02:00 AM)
TIMER_FILE="${SYSTEMD_USER_DIR}/deepagent-backup.timer"
echo -e "\n${BOLD}[2/3] Creating systemd timer unit: ${TIMER_FILE}...${NC}"

cat << 'TIMER_EOF' > "${TIMER_FILE}"
[Unit]
Description=Run Deep Agent Full Backup Daily at 02:00 AM
Persistent=true

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
TIMER_EOF

echo -e "${GREEN}✓ Created ${TIMER_FILE} (Scheduled for 02:00 AM daily with Persistent=true).${NC}"

# 3. Reload daemon and enable timer
echo -e "\n${BOLD}[3/3] Reloading systemd user daemon and enabling timer...${NC}"

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -S "${XDG_RUNTIME_DIR}/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
fi

if systemctl --user daemon-reload 2>/dev/null; then
    systemctl --user enable --now deepagent-backup.timer
    echo -e "${GREEN}✓ deepagent-backup.timer enabled and started via systemctl --user.${NC}"
else
    mkdir -p "${SYSTEMD_USER_DIR}/timers.target.wants"
    ln -sf "${TIMER_FILE}" "${SYSTEMD_USER_DIR}/timers.target.wants/deepagent-backup.timer"
    echo -e "${GREEN}✓ Created autostart symlink in timers.target.wants.${NC}"
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}✅ DAILY BACKUP TIMER CONFIGURED & ACTIVE!${NC}"
echo -e "You can inspect timer details with:"
echo -e "  • Check next run time : ${BOLD}systemctl --user list-timers deepagent-backup.timer${NC}"
echo -e "  • Trigger manual test : ${BOLD}systemctl --user start deepagent-backup.service${NC}"
echo -e "  • View backup logs    : ${BOLD}journalctl --user -u deepagent-backup.service -n 50 --no-pager${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
