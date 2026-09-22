#!/usr/bin/env bash
# ==============================================================================
#  🔄 Deep Agent: Startup Asset Sync & Dynamic Injector
# ==============================================================================
#  Invoked by Systemd before or during container startup:
#    1. Attempts to pull latest playbooks, skills, and prompts from GitLab.
#    2. Resilient: If GitLab is unreachable, network is down, or auth fails,
#       it LOGS A WARNING and EXITS CLEANLY (code 0) so the agent is NEVER blocked.
#    3. Injects updated skills into the running container or host mount.
# ==============================================================================
set -u

GITLAB_REPO="${GITLAB_REPO:-}"
GITLAB_BRANCH="${GITLAB_BRANCH:-main}"
LOCAL_REPO_DIR="${LOCAL_REPO_DIR:-/opt/deepagent_assets}"
CONTAINER_NAME="deepagent-service"

echo "================================================================================"
echo " 🔄 DEEP AGENT ASSET SYNC (STARTUP CHECK)"
echo " 📂 Target Directory : ${LOCAL_REPO_DIR}"
echo "================================================================================"

if [ -z "${GITLAB_REPO}" ]; then
    echo "ℹ️ No GITLAB_REPO environment variable set. Skipping sync."
    exit 0
fi

# Step 1: Ensure directory exists
mkdir -p "${LOCAL_REPO_DIR}"

# Step 2: Attempt Git Pull / Clone with strict timeout
SYNC_SUCCESS=0
if [ ! -d "${LOCAL_REPO_DIR}/.git" ]; then
    echo "⚡ Cloning repository from ${GITLAB_REPO} ..."
    if git clone --depth 1 -b "${GITLAB_BRANCH}" "${GITLAB_REPO}" "${LOCAL_REPO_DIR}" 2>/dev/null; then
        SYNC_SUCCESS=1
    fi
else
    echo "⚡ Pulling latest updates from ${GITLAB_REPO} ..."
    cd "${LOCAL_REPO_DIR}"
    git remote set-url origin "${GITLAB_REPO}" 2>/dev/null || git remote add origin "${GITLAB_REPO}" 2>/dev/null || true
    if git pull --ff-only origin "${GITLAB_BRANCH}" 2>/dev/null; then
        SYNC_SUCCESS=1
    fi
fi

if [ ${SYNC_SUCCESS} -eq 1 ]; then
    echo "✓ Successfully synchronized latest assets from GitLab."
    
    # Step 3: Hot-update skills and prompts in running container if active
    if podman ps --format "{{.Names}}" 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
        echo "🔄 Hot-reloading skills and prompts into ${CONTAINER_NAME} ..."
        if [ -d "${LOCAL_REPO_DIR}/skills" ]; then
            podman cp "${LOCAL_REPO_DIR}/skills/." "${CONTAINER_NAME}:/app/skills/" 2>/dev/null || true
        fi
        if [ -f "${LOCAL_REPO_DIR}/prompts/prompts.py" ]; then
            podman cp "${LOCAL_REPO_DIR}/prompts/prompts.py" "${CONTAINER_NAME}:/app/app/prompts.py" 2>/dev/null || true
        fi
        echo "✓ Assets injected into ${CONTAINER_NAME}."
    fi
else
    echo "⚠️ Warning: Could not connect to GitLab (${GITLAB_REPO})."
    echo "ℹ️ Retaining existing local/baked-in assets. Agent execution will NOT be interrupted."
fi

# Always exit 0 to guarantee systemd continues and starts the agent
exit 0
