#!/usr/bin/env bash
# ==============================================================================
# 🚀 Deep Agent Rootless Podman Systemd Generator & Setup
# ==============================================================================
# Generates systemd user service units to manage the deepagent-prod-pod and all
# microservice containers across host reboots (without requiring root/sudo).
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

POD_NAME="deepagent-prod-pod"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"
mkdir -p "${SYSTEMD_USER_DIR}"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 🚀 DEEP AGENT ROOTLESS SYSTEMD SERVICE SETUP                                 ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Verify Pod Existence
echo -e "\n${BOLD}[1/4] Verifying Podman pod status...${NC}"
if ! podman pod exists "${POD_NAME}"; then
    echo -e "${RED}❌ Error: Pod '${POD_NAME}' does not exist.${NC}"
    echo "Please ensure the Deep Agent pod is running or created before generating units."
    exit 1
fi
echo -e "${GREEN}✓ Pod '${POD_NAME}' found.${NC}"

# 2. Generate Systemd Unit Files
echo -e "\n${BOLD}[2/4] Generating systemd unit files in ${SYSTEMD_USER_DIR}...${NC}"
cd "${SYSTEMD_USER_DIR}"

# Generate systemd files directly into user systemd directory
podman generate systemd --name --files "${POD_NAME}" 2>/dev/null

echo -e "${GREEN}✓ Generated unit files:${NC}"
ls -1 "${SYSTEMD_USER_DIR}"/pod-"${POD_NAME}".service "${SYSTEMD_USER_DIR}"/container-*.service 2>/dev/null || true

# 3. Reload and Enable Systemd User Units
echo -e "\n${BOLD}[3/4] Enabling systemd user service...${NC}"

# Ensure standard DBus environment variables if available
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
if [ -S "${XDG_RUNTIME_DIR}/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
fi

if systemctl --user daemon-reload 2>/dev/null; then
    systemctl --user enable pod-"${POD_NAME}".service
    echo -e "${GREEN}✓ pod-${POD_NAME}.service enabled via systemctl --user.${NC}"
else
    echo -e "${YELLOW}⚠️ Notice: Active interactive systemd user session bus not directly accessible in current shell.${NC}"
    echo -e "Creating auto-enable symlink in ${SYSTEMD_USER_DIR}/default.target.wants/ ..."
    mkdir -p "${SYSTEMD_USER_DIR}/default.target.wants"
    ln -sf "${SYSTEMD_USER_DIR}/pod-${POD_NAME}".service "${SYSTEMD_USER_DIR}/default.target.wants/pod-${POD_NAME}.service"
    echo -e "${GREEN}✓ Symlink created in default.target.wants.${NC}"
    echo -e "When logging in via interactive shell, you can run:"
    echo -e "  ${BOLD}systemctl --user daemon-reload && systemctl --user enable pod-${POD_NAME}.service${NC}"
fi

# 4. Check Linger Status (Ensures service runs at boot without active user login)
echo -e "\n${BOLD}[4/4] Checking linger status for user $(whoami)...${NC}"
CURRENT_USER=$(whoami)
LINGER_STATUS=$(loginctl show-user "${CURRENT_USER}" --property=Linger 2>/dev/null | cut -d= -f2 || echo "unknown")

if [ "${LINGER_STATUS}" = "yes" ]; then
    echo -e "${GREEN}✓ Linger is ENABLED for ${CURRENT_USER} (services will start on boot and stay alive).${NC}"
else
    echo -e "${YELLOW}⚠️ Warning: Linger is not enabled for ${CURRENT_USER}.${NC}"
    echo -e "To ensure services start at host boot without logging in, run once:"
    echo -e "   ${BOLD}loginctl enable-linger ${CURRENT_USER}${NC} (or ask your sysadmin)"
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}✅ SYSTEMD CONFIGURATION COMPLETED SUCCESSFULLY!${NC}"
echo -e "Manage Deep Agent using standard systemctl commands:"
echo -e "  • Status  : ${BOLD}systemctl --user status pod-${POD_NAME}.service${NC}"
echo -e "  • Start   : ${BOLD}systemctl --user start pod-${POD_NAME}.service${NC}"
echo -e "  • Restart : ${BOLD}systemctl --user restart pod-${POD_NAME}.service${NC}"
echo -e "  • Stop    : ${BOLD}systemctl --user stop pod-${POD_NAME}.service${NC}"
echo -e "  • Logs    : ${BOLD}journalctl --user -u pod-${POD_NAME}.service -f${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
