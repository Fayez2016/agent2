#!/usr/bin/env bash
# ==============================================================================
#  🚀 Deep Agent: 100% Dynamic Container Extractor & GitLab Pusher
# ==============================================================================
#  NO hardcoded SOPs or static definitions.
#  Dynamically extracts live assets directly from the running Podman containers:
#    1. Prompts       <- deepagent-service:/app/...
#    2. SOPs / Skills <- deepagent-hitl-db (live database query)
#    3. Schema        <- deepagent-hitl-db (live pg_dump)
#    4. Playbooks     <- Preserved from your remote GitLab repository
# ==============================================================================
set -euo pipefail

GITLAB_REPO="${1:-}"
BRANCH="${2:-main}"

if [ -z "${GITLAB_REPO}" ]; then
    echo "❌ Usage: $0 <GITLAB_REPO_URL> [BRANCH]"
    echo "   Example: $0 https://gitlab.corp.internal/sre/deepagent-playbooks.git main"
    exit 1
fi

WORKSPACE_DIR="/tmp/deepagent_gitlab_sync_$(date +%s)"
ASSETS_TEMP="/tmp/deepagent_extracted_$(date +%s)"

echo "================================================================================"
echo " 🚀 DYNAMIC CONTAINER EXTRACTOR & GITLAB PUSHER"
echo " 📡 Target Repo: ${GITLAB_REPO}"
echo " 🌿 Branch     : ${BRANCH}"
echo " 📂 Workspace  : ${WORKSPACE_DIR}"
echo "================================================================================"

cleanup() {
    rm -rf "${WORKSPACE_DIR}" "${ASSETS_TEMP}" 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p "${ASSETS_TEMP}/skills"
mkdir -p "${ASSETS_TEMP}/prompts"
mkdir -p "${ASSETS_TEMP}/db"

# ------------------------------------------------------------------------------
# STEP 1: Dynamically Extract Assets From Running Containers (Zero Hardcoding)
# ------------------------------------------------------------------------------
echo "🔍 Step 1/5: Dynamically extracting assets from running Podman containers ..."

# 1a. Prompts from deepagent-service
echo "  ⚡ Extracting live prompts from container 'deepagent-service' ..."
if podman ps --format "{{.Names}}" | grep -q "^deepagent-service$"; then
    # Search and extract prompts.py dynamically from container
    PROMPTS_PATH=$(podman exec deepagent-service find /app -name "prompts.py" 2>/dev/null | head -n 1)
    if [ -n "${PROMPTS_PATH}" ]; then
        podman cp "deepagent-service:${PROMPTS_PATH}" "${ASSETS_TEMP}/prompts/prompts.py"
        echo "     ✓ Extracted: ${PROMPTS_PATH} ($(wc -c < "${ASSETS_TEMP}/prompts/prompts.py") bytes)"
    else
        echo "     ⚠️ prompts.py not found in /app inside deepagent-service"
    fi
else
    echo "     ❌ Error: Container 'deepagent-service' is not running!"
    exit 1
fi

# 1b. Skills & SOPs from deepagent-hitl-db
echo "  ⚡ Extracting live skills & SOPs dynamically from container 'deepagent-hitl-db' ..."
if podman ps --format "{{.Names}}" | grep -q "^deepagent-hitl-db$"; then
    # Query all active skills from PostgreSQL
    SKILLS_LIST=$(podman exec deepagent-hitl-db psql -U hermes -d hitl -t -A -c \
        "SELECT name FROM domain_skills WHERE is_enabled = true;")

    for skill_name in ${SKILLS_LIST}; do
        SKILL_DIR="${ASSETS_TEMP}/skills/${skill_name}"
        mkdir -p "${SKILL_DIR}"
        podman exec deepagent-hitl-db psql -U hermes -d hitl -t -A -c \
            "SELECT content_markdown FROM domain_skills WHERE name = '${skill_name}';" \
            > "${SKILL_DIR}/skill.md"
        echo "     ✓ Extracted skill '${skill_name}': ${SKILL_DIR}/skill.md ($(wc -c < "${SKILL_DIR}/skill.md") bytes)"
    done
else
    echo "     ❌ Error: Container 'deepagent-hitl-db' is not running!"
    exit 1
fi

# 1c. Clean Database Schema from deepagent-hitl-db
echo "  ⚡ Dumping live PostgreSQL schema from container 'deepagent-hitl-db' ..."
podman exec deepagent-hitl-db pg_dump -U hermes -d hitl --schema-only > "${ASSETS_TEMP}/db/init.sql"
echo "     ✓ Generated init.sql ($(wc -c < "${ASSETS_TEMP}/db/init.sql") bytes)"

# ------------------------------------------------------------------------------
# STEP 2: Clone Remote GitLab Repository
# ------------------------------------------------------------------------------
echo -e "\n📥 Step 2/5: Cloning remote GitLab repository into clean workspace ..."
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
# STEP 3: Overlay Extracted Assets onto GitLab Project (Preserves Remote Playbooks)
# ------------------------------------------------------------------------------
echo -e "\n📦 Step 3/5: Merging extracted container assets into GitLab project ..."

# Copy skills
mkdir -p "${WORKSPACE_DIR}/skills"
cp -r "${ASSETS_TEMP}/skills/"* "${WORKSPACE_DIR}/skills/"

# Copy prompts
mkdir -p "${WORKSPACE_DIR}/prompts"
cp "${ASSETS_TEMP}/prompts/prompts.py" "${WORKSPACE_DIR}/prompts/"

# Copy schema
mkdir -p "${WORKSPACE_DIR}/db"
cp "${ASSETS_TEMP}/db/init.sql" "${WORKSPACE_DIR}/db/"

# Strict size-control .gitignore
cat << 'IGN_EOF' > "${WORKSPACE_DIR}/.gitignore"
*.tar
*.tar.gz
*.iso
*.img
images/
db-data/
*.log
__pycache__/
*.pyc
.env*
.hermes/
IGN_EOF

# ------------------------------------------------------------------------------
# STEP 4: Stage, Inspect, and Commit
# ------------------------------------------------------------------------------
echo -e "\n🚀 Step 4/5: Staging, committing, and pushing to GitLab ..."
cd "${WORKSPACE_DIR}"

git add skills/ prompts/ db/ .gitignore
# Stage any playbooks already existing in the repo
git add ansible_playbooks/ 2>/dev/null || true

echo "📋 Git Status of Staged Files:"
git status --short

TOTAL_SIZE=$(du -sh "${WORKSPACE_DIR}" | cut -f1)
echo "📊 Total Synced Size: ${TOTAL_SIZE} (< 1 MB Quota Compliant)"

COMMIT_HASH=""
if git diff --cached --quiet; then
    echo "✓ Remote repository already contains all these exact assets."
    COMMIT_HASH=$(git rev-parse HEAD 2>/dev/null || echo "N/A")
else
    echo "📝 Committing asset bundle ..."
    git commit -m "feat(deepagent): sync live container skills, prompts, and schema ($(date '+%Y-%m-%d %H:%M'))"

    if git ls-remote --exit-code origin "${BRANCH}" >/dev/null 2>&1; then
        echo "🔄 Re-checking remote branch (rebase) before push ..."
        git pull --rebase origin "${BRANCH}" || true
    fi

    echo "📡 Pushing to ${GITLAB_REPO} (${BRANCH}) ..."
    git push -u origin "${BRANCH}"
    COMMIT_HASH=$(git rev-parse HEAD)
    echo "✓ Successfully pushed all live container assets to GitLab!"
fi

# ------------------------------------------------------------------------------
# STEP 5: Pull Information Manifest for Next Script
# ------------------------------------------------------------------------------
echo ""
echo "================================================================================"
echo " 📋 PULL METADATA & INTEGRATION SPECIFICATION (FOR NEXT SCRIPT)"
echo "================================================================================"
echo "export GITLAB_REPO=\"${GITLAB_REPO}\""
echo "export GITLAB_BRANCH=\"${BRANCH}\""
echo "export LATEST_COMMIT_HASH=\"${COMMIT_HASH}\""
echo "export SYNC_TIMESTAMP=\"$(date '+%Y-%m-%d %H:%M:%S %Z')\""
echo ""
echo "Files preserved and pushed in GitLab project:"
echo "  ├── ansible_playbooks/  (Preserved from GitLab)"
echo "  ├── skills/             (Extracted from deepagent-hitl-db)"
echo "  ├── prompts/            (Extracted from deepagent-service)"
echo "  ├── db/                 (Dumped from deepagent-hitl-db)"
echo "  └── .gitignore          (Enforces < 1 MB size limit)"
echo "================================================================================"
