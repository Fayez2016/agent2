#!/usr/bin/env bash
# ==============================================================================
# 🛠️ Deep Agent: Unified Platform Management (Systemd & Backup Suite)
# ==============================================================================
# Turnkey operations manager:
#   --setup-systemd : Installs and enables user systemd service with auto-restart
#   --backup-all    : Runs full backup (Database + Code + Container images)
#   --backup-db     : Runs lightweight PostgreSQL database backup
#   --schedule-cron : Configures daily automatic backup in user crontab
#   --status        : Inspects status of systemd service and Podman containers
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="deepagent.service"

usage() {
    cat << EOF
Usage: $0 [OPTION]

Options:
  --setup-systemd   Install and enable systemd user service with auto-restart
  --backup-all      Execute comprehensive backup (DB, code, playbooks, images)
  --backup-db       Execute PostgreSQL database dump only
  --schedule-cron   Add automated daily backup to crontab (runs at 02:00 AM)
  --status          Show systemd service status and Podman container state
  --help            Display this help message

EOF
    exit 1
}

case "${1:-}" in
    --setup-systemd)
        echo ">>> [1/3] Enabling systemd user lingering for user $(whoami)..."
        loginctl enable-linger "$(whoami)" 2>/dev/null || echo "Note: Lingering may require sudo or already active."

        echo ">>> [2/3] Installing ${SERVICE_NAME} into ${SYSTEMD_USER_DIR}..."
        mkdir -p "${SYSTEMD_USER_DIR}"
        cp "${SCRIPT_DIR}/${SERVICE_NAME}" "${SYSTEMD_USER_DIR}/${SERVICE_NAME}"

        echo ">>> [3/3] Reloading systemd daemon and enabling service..."
        systemctl --user daemon-reload
        systemctl --user enable --now "${SERVICE_NAME}"
        echo "✅ Systemd auto-restart service successfully configured and started!"
        systemctl --user status "${SERVICE_NAME}" --no-pager || true
        ;;

    --backup-all)
        echo ">>> Executing comprehensive platform backup..."
        "${SCRIPT_DIR}/backup_deepagent_all.sh"
        ;;

    --backup-db)
        echo ">>> Executing PostgreSQL database backup..."
        "${SCRIPT_DIR}/backup_deepagent_db.sh"
        ;;

    --schedule-cron)
        CRON_CMD="${SCRIPT_DIR}/backup_deepagent_all.sh >> ${HOME}/backups/deepagent/backup.log 2>&1"
        CRON_ENTRY="0 2 * * * ${CRON_CMD}"
        
        echo ">>> Scheduling daily comprehensive backup at 02:00 AM in crontab..."
        mkdir -p "${HOME}/backups/deepagent"
        (crontab -l 2>/dev/null | grep -v "backup_deepagent" || true; echo "${CRON_ENTRY}") | crontab -
        echo "✅ Crontab successfully updated:"
        crontab -l | grep "backup_deepagent"
        ;;

    --status)
        echo "================================================================================"
        echo "🔍 DEEP AGENT PLATFORM HEALTH & STATUS"
        echo "================================================================================"
        echo -e "\n--- SYSTEMD SERVICE STATUS ---"
        systemctl --user status "${SERVICE_NAME}" --no-pager 2>/dev/null || echo "Systemd service not active or installed."
        
        echo -e "\n--- RUNNING PODMAN CONTAINERS ---"
        podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "Podman not running."
        
        echo -e "\n--- RECENT BACKUPS ---"
        if [ -d "${HOME}/backups/deepagent" ]; then
            ls -ldh "${HOME}/backups/deepagent"/* 2>/dev/null || echo "No backups found."
        else
            echo "No backup directory exists yet."
        fi
        ;;

    *)
        usage
        ;;
esac
