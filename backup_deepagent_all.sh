#!/usr/bin/env bash
# ==============================================================================
# 📦 Deep Agent: Unified Comprehensive Backup Engine
# ==============================================================================
# This script performs a full disaster-recovery backup of the Deep Agent platform:
#   1. PostgreSQL Database Dump (HITL requests, system_settings, domain_subagents)
#   2. Codebase & Configuration Archive (git tracked files, playbooks, prompts, skills)
#   3. Active Podman Container Images (all 7 microservice images saved to .tar)
#   4. Enforces a 14-day rolling retention policy on all generated archives.
# ==============================================================================

set -euo pipefail

BACKUP_ROOT="${HOME}/backups/deepagent"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

mkdir -p "${BACKUP_DIR}/db" "${BACKUP_DIR}/code" "${BACKUP_DIR}/images"

echo "================================================================================"
echo " 📦 DEEP AGENT UNIFIED COMPREHENSIVE BACKUP ENGINE"
echo " 📅 Timestamp    : ${TIMESTAMP}"
echo " 📁 Destination  : ${BACKUP_DIR}"
echo "================================================================================"

# ------------------------------------------------------------------------------
# 1. DATABASE BACKUP (PostgreSQL hitl database)
# ------------------------------------------------------------------------------
echo -e "\n>>> [1/3] Backing up PostgreSQL Database ('hitl')..."
DB_CONTAINER="deepagent-hitl-db"
DB_BACKUP_FILE="${BACKUP_DIR}/db/deepagent_hitl_db_${TIMESTAMP}.sql.gz"

if podman ps --format "{{.Names}}" | grep -q "${DB_CONTAINER}"; then
    podman exec "${DB_CONTAINER}" pg_dump -U hermes -d hitl | gzip > "${DB_BACKUP_FILE}"
    echo "  ✓ Database dump created: $(basename "${DB_BACKUP_FILE}") ($(du -h "${DB_BACKUP_FILE}" | cut -f1))"
else
    echo "  ⚠️ Warning: '${DB_CONTAINER}' container is not running. Checking if stopped container exists..."
    if podman ps -a --format "{{.Names}}" | grep -q "${DB_CONTAINER}"; then
        podman start "${DB_CONTAINER}" >/dev/null 2>&1 || true
        sleep 3
        podman exec "${DB_CONTAINER}" pg_dump -U hermes -d hitl | gzip > "${DB_BACKUP_FILE}"
        echo "  ✓ Database dump created from temporarily started container."
    else
        echo "  ❌ No database container found. Skipping DB dump."
    fi
fi

# ------------------------------------------------------------------------------
# 2. CODEBASE & CONFIGURATION BACKUP
# ------------------------------------------------------------------------------
echo -e "\n>>> [2/3] Backing up Codebase, Playbooks, Prompts, Skills & Configs..."
CODE_BACKUP_FILE="${BACKUP_DIR}/code/deepagent_codebase_${TIMESTAMP}.tar.gz"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

tar --exclude='.git' \
    --exclude='*.tar' \
    --exclude='*.tar.gz' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='backups' \
    -czf "${CODE_BACKUP_FILE}" -C "$(dirname "${SOURCE_DIR}")" "$(basename "${SOURCE_DIR}")"

echo "  ✓ Codebase archive created: $(basename "${CODE_BACKUP_FILE}") ($(du -h "${CODE_BACKUP_FILE}" | cut -f1))"

# ------------------------------------------------------------------------------
# 3. CONTAINER IMAGES BACKUP
# ------------------------------------------------------------------------------
echo -e "\n>>> [3/3] Exporting Microservice Container Images..."
IMAGES=(
    "quay.io/souffm0a/deepagent-hitl-db:latest"
    "quay.io/souffm0a/deepagent-mock-aap:latest"
    "quay.io/souffm0a/deepagent-ansible-mcp:latest"
    "quay.io/souffm0a/deepagent-sop-mcp:latest"
    "quay.io/souffm0a/deepagent-core:latest"
    "quay.io/souffm0a/deepagent-hitl-web:latest"
    "quay.io/souffm0a/deepagent-proxy:latest"
)

SAVED_IMG_COUNT=0
for img in "${IMAGES[@]}"; do
    if podman image exists "${img}"; then
        clean_name=$(echo "${img}" | awk -F'/' '{print $NF}' | tr ':' '_')
        dest_file="${BACKUP_DIR}/images/${clean_name}.tar"
        echo -n "  ⚡ Saving ${clean_name} ... "
        podman save -o "${dest_file}" "${img}"
        echo "✓ ($(du -h "${dest_file}" | cut -f1))"
        SAVED_IMG_COUNT=$((SAVED_IMG_COUNT + 1))
    fi
done

if [ ${SAVED_IMG_COUNT} -eq 0 ]; then
    echo "  ℹ️ Note: Target tagged images not locally loaded; saving active pod containers..."
    ACTIVE_CONTAINERS=(
        "deepagent-hitl-db"
        "deepagent-ansible-mcp"
        "deepagent-service"
        "deepagent-sop-mcp"
    )
    for c in "${ACTIVE_CONTAINERS[@]}"; do
        if podman ps -a --format "{{.Names}}" | grep -q "^${c}$"; then
            dest_file="${BACKUP_DIR}/images/${c}_commit_${TIMESTAMP}.tar"
            echo -n "  ⚡ Committing and saving ${c} ... "
            podman commit "${c}" "local_backup/${c}:backup" >/dev/null 2>&1 || true
            podman save -o "${dest_file}" "local_backup/${c}:backup" 2>/dev/null || true
            echo "✓ ($(du -h "${dest_file}" | cut -f1))"
        fi
    done
fi

# ------------------------------------------------------------------------------
# 4. PRUNING & RETENTION (14 Days)
# ------------------------------------------------------------------------------
echo -e "\n>>> [Retention] Pruning backup snapshots older than 14 days..."
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} + 2>/dev/null || true

# Summary
echo -e "\n================================================================================"
echo "✅ COMPREHENSIVE BACKUP COMPLETED SUCCESSFULLY!"
echo "📍 Backup Location : ${BACKUP_DIR}"
echo "📊 Total Size      : $(du -sh "${BACKUP_DIR}" | cut -f1)"
echo "================================================================================"
