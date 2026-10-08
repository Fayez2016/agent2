#!/usr/bin/env bash
# ==============================================================================
# 🔧 Deep Agent: RHEL Systemd User Bus & Journal Permissions Fix (Run as Root)
# ==============================================================================
# Resolves:
#   1. "Failed to connect to bus" / "No medium found"
#   2. "No journal files were opened due to insufficient permissions"
#   3. Enables systemd lingering so rootless containers start at boot & survive logout
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 🔧 RHEL ROOTLESS SYSTEMD & JOURNAL PERMISSIONS SETUP                         ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Enforce direct root execution (no sudo needed)
if [ "$(id -u)" -ne 0 ]; then
    echo -e "\n${RED}❌ Error: This script must be executed directly as root.${NC}"
    echo -e "Please switch to root first: ${BOLD}su -${NC} and re-run this script."
    exit 1
fi

# 2. Prompt for Target Username (or accept via argument $1)
TARGET_USER="${1:-}"

if [ -z "${TARGET_USER}" ]; then
    echo -e ""
    read -r -p "Enter the target username running Deep Agent: " TARGET_USER
fi

TARGET_USER=$(echo "${TARGET_USER}" | xargs)

# 3. Validate user exists on the system
if ! id "${TARGET_USER}" >/dev/null 2>&1; then
    echo -e "\n${RED}❌ Error: User '${TARGET_USER}' does not exist on this system.${NC}"
    exit 1
fi

USER_UID=$(id -u "${TARGET_USER}")
USER_HOME=$(eval echo "~${TARGET_USER}")

echo -e "\n${CYAN}Configuring permissions for user:${NC} ${BOLD}${TARGET_USER}${NC} (UID: ${USER_UID}, Home: ${USER_HOME})"

# 4. Add user to systemd-journal and adm groups for passwordless journal reading
echo -e "\n${BOLD}[1/4] Adding '${TARGET_USER}' to 'systemd-journal' and 'adm' groups...${NC}"
groupadd -f systemd-journal
groupadd -f adm
usermod -aG systemd-journal "${TARGET_USER}"
usermod -aG adm "${TARGET_USER}"
echo -e "${GREEN}✓ User '${TARGET_USER}' successfully added to systemd-journal and adm groups.${NC}"

# 5. Enable User Lingering
echo -e "\n${BOLD}[2/4] Enabling systemd user lingering for '${TARGET_USER}'...${NC}"
loginctl enable-linger "${TARGET_USER}"
echo -e "${GREEN}✓ Lingering enabled (rootless Podman units will auto-start at boot and persist after logout).${NC}"

# 6. Verify and set runtime directory permissions
echo -e "\n${BOLD}[3/4] Ensuring runtime directory /run/user/${USER_UID} exists...${NC}"
RUNTIME_DIR="/run/user/${USER_UID}"
if [ ! -d "${RUNTIME_DIR}" ]; then
    mkdir -p "${RUNTIME_DIR}"
fi
chown "${TARGET_USER}:${TARGET_USER}" "${RUNTIME_DIR}"
chmod 700 "${RUNTIME_DIR}"
echo -e "${GREEN}✓ Runtime directory verified: ${RUNTIME_DIR} (700 owned by ${TARGET_USER}).${NC}"

# 7. Inject automatic D-Bus exports into the target user's ~/.bashrc
echo -e "\n${BOLD}[4/4] Configuring automatic D-Bus session variables in ${USER_HOME}/.bashrc...${NC}"
BASHRC="${USER_HOME}/.bashrc"

BASH_SNIPPET=$(cat << 'EOF'

# --- Deep Agent Systemd User Session Exports ---
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
fi
if [ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ] && [ -S "${XDG_RUNTIME_DIR}/bus" ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=${XDG_RUNTIME_DIR}/bus"
fi
# -----------------------------------------------
EOF
)

if [ -f "${BASHRC}" ]; then
    if ! grep -q "Deep Agent Systemd User Session Exports" "${BASHRC}"; then
        echo "${BASH_SNIPPET}" >> "${BASHRC}"
        chown "${TARGET_USER}:${TARGET_USER}" "${BASHRC}"
        echo -e "${GREEN}✓ Session environment exports appended to ${BASHRC}.${NC}"
    else
        echo -e "${GREEN}✓ Session environment exports already present in ${BASHRC}.${NC}"
    fi
else
    echo "${BASH_SNIPPET}" > "${BASHRC}"
    chown "${TARGET_USER}:${TARGET_USER}" "${BASHRC}"
    echo -e "${GREEN}✓ Created ${BASHRC} with session environment exports.${NC}"
fi

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}✅ CONFIGURATION COMPLETED SUCCESSFULLY!${NC}"
echo -e "You can now exit root (${BOLD}exit${NC}) and switch back to '${TARGET_USER}'."
echo -e ""
echo -e "As user '${TARGET_USER}':"
echo -e "  1. Apply new group membership in your active terminal:"
echo -e "     ${BOLD}newgrp systemd-journal${NC}  (or close and reopen your SSH terminal)"
echo -e "  2. Test systemd restart:"
echo -e "     ${BOLD}systemctl --user restart pod-deepagent-prod-pod.service${NC}"
echo -e "  3. Test journal inspection without root:"
echo -e "     ${BOLD}journalctl --user -u pod-deepagent-prod-pod.service -f${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
