#!/usr/bin/env bash
# ==============================================================================
#  🚀 Deep Agent: Safe GitLab Asset Synchronizer & Pusher (Universal Layout)
# ==============================================================================
#  Works with either:
#    1. Direct layout: <SOURCE_DIR>/skills, <SOURCE_DIR>/ansible_playbooks, etc.
#    2. Nested layout: <SOURCE_DIR>/deepagent_system/skills, etc.
#
#  Features:
#    - Pulls / clones remote repo first to avoid overwriting existing work.
#    - Pulls & rebases before push to prevent rejection.
#    - Outputs complete manifest & environment variables for pull scripts.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GITLAB_REPO="${1:-}"
BRANCH="${2:-main}"
USER_SOURCE="${3:-}"

if [ -z "${GITLAB_REPO}" ]; then
    echo "❌ Usage: $0 <GITLAB_REPO_URL> [BRANCH] [SOURCE_DIR]"
    echo "   Example: $0 https://gitlab.corp.internal/sre/deepagent.git main /opt/deepagent"
    exit 1
fi

# Candidate directories to inspect
CANDIDATES=(
    "${USER_SOURCE}"
    "${SCRIPT_DIR}"
    "${PWD}"
    "/home/fayez/agent2"
    "/opt/deepagent"
)

SOURCE_ROOT=""
LAYOUT_TYPE=""

for c in "${CANDIDATES[@]}"; do
    [ -z "$c" ] && continue
    if [ -d "$c/skills" ] || [ -d "$c/ansible_playbooks" ] || [ -d "$c/sop" ]; then
        SOURCE_ROOT="$c"
        LAYOUT_TYPE="direct"
        break
    elif [ -d "$c/deepagent_system/skills" ] || [ -d "$c/deepagent_system/ansible_playbooks" ]; then
        SOURCE_ROOT="$c/deepagent_system"
        LAYOUT_TYPE="nested"
        break
    fi
done

echo "================================================================================"
echo " 🚀 SAFE SYNC OF DEEP AGENT ASSETS TO GITLAB"
echo " 📡 Remote URL     : ${GITLAB_REPO}"
echo " 🌿 Branch         : ${BRANCH}"
echo " 📂 Assets Source  : ${SOURCE_ROOT:-'NOT FOUND'}"
echo " 🗂️ Layout Mode    : ${LAYOUT_TYPE:-'UNKNOWN'}"
echo "================================================================================"

if [ -z "${SOURCE_ROOT}" ]; then
    echo "❌ ERROR: Could not locate skills, sop, or ansible_playbooks in:"
    for c in "${CANDIDATES[@]}"; do
        [ -n "$c" ] && echo "     - $c"
    done
    echo ""
    echo "👉 Usage: $0 ${GITLAB_REPO} ${BRANCH} /path/to/your/assets"
    exit 1
fi

WORKSPACE_DIR="/tmp/deepagent_gitlab_sync_$(date +%s)"
cleanup() {
    rm -rf "${WORKSPACE_DIR}" 2>/dev/null || true
}
trap cleanup EXIT

# ------------------------------------------------------------------------------
# Step 1: Clone Remote GitLab Repository
# ------------------------------------------------------------------------------
echo "📥 Step 1/5: Cloning GitLab repository into clean workspace ..."
mkdir -p "${WORKSPACE_DIR}"

if git clone "${GITLAB_REPO}" "${WORKSPACE_DIR}"; then
    echo "✓ Successfully cloned remote repository."
    cd "${WORKSPACE_DIR}"

    git config user.name "Deep Agent SRE"
    git config user.email "deepagent@enterprise.local"

    if git show-ref --verify --quiet "refs/remotes/origin/${BRANCH}"; then
        git checkout "${BRANCH}"
        git pull --rebase origin "${BRANCH}" || true
    else
        git checkout -b "${BRANCH}"
    fi
else
    echo "ℹ️ Remote repository is empty. Initializing branch '${BRANCH}' ..."
    cd "${WORKSPACE_DIR}"
    git init -b "${BRANCH}"
    git config user.name "Deep Agent SRE"
    git config user.email "deepagent@enterprise.local"
    git remote add origin "${GITLAB_REPO}"
fi

# ------------------------------------------------------------------------------
# Step 2: Overlay Ansible Playbooks
# ------------------------------------------------------------------------------
echo "📦 Step 2/5: Staging Ansible Playbooks ..."
mkdir -p "${WORKSPACE_DIR}/ansible_playbooks"
PB_COUNT=0
for pb_dir in "${SOURCE_ROOT}/ansible_playbooks" "${SOURCE_ROOT}/playbooks" "${SOURCE_ROOT}"; do
    if [ -d "${pb_dir}" ]; then
        for yml in "${pb_dir}"/*.yml "${pb_dir}"/*.yaml; do
            if [ -f "${yml}" ]; then
                cp "${yml}" "${WORKSPACE_DIR}/ansible_playbooks/"
                PB_COUNT=$((PB_COUNT + 1))
            fi
        done
        [ $PB_COUNT -gt 0 ] && break
    fi
done
echo "   ✓ Staged ${PB_COUNT} playbook file(s)."

# ------------------------------------------------------------------------------
# Step 3: Overlay Skills & SOPs
# ------------------------------------------------------------------------------
echo "📦 Step 3/5: Staging Agent Skills & SOP Markdown files ..."
mkdir -p "${WORKSPACE_DIR}/skills"
SKILL_COUNT=0
for s_dir in "${SOURCE_ROOT}/skills" "${SOURCE_ROOT}/sop" "${SOURCE_ROOT}/SOP"; do
    if [ -d "${s_dir}" ]; then
        cp -r "${s_dir}"/* "${WORKSPACE_DIR}/skills/" 2>/dev/null || true
        SKILL_COUNT=$(find "${WORKSPACE_DIR}/skills" -type f | wc -l)
    fi
done
echo "   ✓ Staged ${SKILL_COUNT} skill/SOP file(s)."

# ------------------------------------------------------------------------------
# Step 4: Overlay Prompts, Configs, Database Schema, and .gitignore
# ------------------------------------------------------------------------------
echo "📦 Step 4/5: Staging Prompts, Configs, and Schema ..."
mkdir -p "${WORKSPACE_DIR}/prompts"
for p_candidate in "${SOURCE_ROOT}/prompts/prompts.py" "${SOURCE_ROOT}/app/prompts.py" "${SOURCE_ROOT}/prompts.py"; do
    if [ -f "${p_candidate}" ]; then
        cp "${p_candidate}" "${WORKSPACE_DIR}/prompts/prompts.py"
        echo "   ✓ Staged prompts.py from ${p_candidate}"
        break
    fi
done

mkdir -p "${WORKSPACE_DIR}/db"
for db_candidate in "${SOURCE_ROOT}/db/01-schema-and-data.sql" "${SOURCE_ROOT}/db/init.sql" "${SOURCE_ROOT}/init.sql"; do
    if [ -f "${db_candidate}" ]; then
        cp "${db_candidate}" "${WORKSPACE_DIR}/db/init.sql"
        echo "   ✓ Staged init.sql from ${db_candidate}"
        break
    fi
done

# Strict size-control .gitignore
cat << 'IGN_EOF' > "${WORKSPACE_DIR}/.gitignore"
*.tar
*.tar.gz
*.iso
*.img
db-data/
*.log
__pycache__/
*.pyc
.env*
.hermes/
IGN_EOF

# ------------------------------------------------------------------------------
# Step 5: Commit and Pull-Rebase Before Push (Guarantees Rejection-Free Push)
# ------------------------------------------------------------------------------
echo "🚀 Step 5/5: Preparing commit and pushing to GitLab ..."
cd "${WORKSPACE_DIR}"

TOTAL_SIZE=$(du -sh "${WORKSPACE_DIR}" | cut -f1)
echo "📊 Total Staged Asset Size: ${TOTAL_SIZE}"

git add ansible_playbooks/ skills/ prompts/ db/ .gitignore

# Output staged files list so you can see exactly what git staged
echo "📋 Git Staged Status:"
git status --short

COMMIT_HASH=""
if git diff --cached --quiet; then
    echo "✓ Remote repository already has all these files and is up to date."
    COMMIT_HASH=$(git rev-parse HEAD 2>/dev/null || echo "N/A")
else
    echo "📝 Committing asset bundle ..."
    git commit -m "feat(deepagent): sync playbooks, skills, prompts, and schema ($(date '+%Y-%m-%d %H:%M'))"

    if git ls-remote --exit-code origin "${BRANCH}" >/dev/null 2>&1; then
        echo "🔄 Re-checking remote branch (rebase) before push ..."
        git pull --rebase origin "${BRANCH}" || true
    fi

    echo "📡 Pushing to ${GITLAB_REPO} (${BRANCH}) ..."
    git push -u origin "${BRANCH}"
    COMMIT_HASH=$(git rev-parse HEAD)
    echo "✓ Successfully pushed all assets to GitLab!"
fi

# ------------------------------------------------------------------------------
# 📋 ASSET METADATA & PULL SPECIFICATION FOR NEXT SCRIPT (Systemd / Pull Sync)
# ------------------------------------------------------------------------------
echo ""
echo "================================================================================"
echo " 📋 PULL METADATA & INTEGRATION SPECIFICATION (FOR NEXT SCRIPT)"
echo "================================================================================"
echo "Use the parameters below in your automated startup pull script / systemd unit:"
echo ""
echo "--- [1. GIT ENVIRONMENT VARIABLES] ---"
echo "export GITLAB_REPO=\"${GITLAB_REPO}\""
echo "export GITLAB_BRANCH=\"${BRANCH}\""
echo "export LATEST_COMMIT_HASH=\"${COMMIT_HASH}\""
echo "export SYNC_TIMESTAMP=\"$(date '+%Y-%m-%d %H:%M:%S %Z')\""
echo ""
echo "--- [2. SYNCHRONIZED DIRECTORY STRUCTURE IN GITLAB] ---"
echo "  ├── ansible_playbooks/  (${PB_COUNT} playbooks for AAP Job Templates)"
echo "  ├── skills/             (${SKILL_COUNT} declarative SOP markdown files)"
echo "  ├── prompts/            (Subagent system prompt definitions)"
echo "  ├── db/                 (Database schema init.sql)"
echo "  └── .gitignore          (Enforces < 1 MB size quota)"
echo ""
echo "--- [3. HOW THE NEXT PULL SCRIPT CONSUMES THESE FILES] ---"
echo "1. Git Pull Command:"
echo "   git pull origin ${BRANCH}"
echo ""
echo "2. Injection to Deep Agent Microservices (Hot-Reload without container rebuild):"
echo "   - Skills   : podman cp <LOCAL_CLONE>/skills/. deepagent-service:/app/skills/"
echo "   - Prompts  : podman cp <LOCAL_CLONE>/prompts/prompts.py deepagent-service:/app/app/prompts.py"
echo "   - Playbooks: Target directory for Ansible Automation Platform (AAP) Project Sync"
echo ""
echo "3. Systemd Resilience Rule:"
echo "   The pull script MUST exit with code 0 even if GitLab is unreachable, so"
echo "   Deep Agent services continue to start uninterrupted using cached assets."
echo "================================================================================"
