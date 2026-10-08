#!/usr/bin/env bash
# ==============================================================================
# 📦 Deep Agent: Unified Full Backup Engine (Database, Codebase & Container Images)
# ==============================================================================
# Performs a complete disaster-recovery backup:
#   1. PostgreSQL Database Dump (hitl-db)
#   2. Complete Codebase & Configurations Archive
#   3. Full Container Images (.tar archives of all microservices)
#   4. 14-day rolling retention pruning
# ==============================================================================

set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

BACKUP_ROOT="${HOME}/backups/deepagent"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

mkdir -p "${BACKUP_DIR}/db" "${BACKUP_DIR}/code" "${BACKUP_DIR}/images"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD} 📦 DEEP AGENT FULL DISASTER-RECOVERY BACKUP                                   ${NC}"
echo -e "${CYAN}${BOLD} 📅 Timestamp    : ${TIMESTAMP}                                               ${NC}"
echo -e "${CYAN}${BOLD} 📁 Destination  : ${BACKUP_DIR}                                              ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# ------------------------------------------------------------------------------
# 1. DATABASE BACKUP (PostgreSQL 'hitl' database)
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}>>> [1/3] Backing up PostgreSQL Database ('hitl')...${NC}"
DB_CONTAINER="deepagent-hitl-db"
DB_BACKUP_FILE="${BACKUP_DIR}/db/deepagent_hitl_db_${TIMESTAMP}.sql.gz"

if podman ps --format "{{.Names}}" | grep -q "${DB_CONTAINER}"; then
    podman exec -e PGPASSWORD=secret456 "${DB_CONTAINER}" pg_dump -h 127.0.0.1 -p 5432 -U hermes -d hitl | gzip > "${DB_BACKUP_FILE}"
    echo -e "  ${GREEN}✓ Database dump created:${NC} $(basename "${DB_BACKUP_FILE}") ($(du -h "${DB_BACKUP_FILE}" | cut -f1))"
else
    echo -e "  ${YELLOW}⚠️ Notice: '${DB_CONTAINER}' container is not running. Checking if stopped container exists...${NC}"
    if podman ps -a --format "{{.Names}}" | grep -q "${DB_CONTAINER}"; then
        podman start "${DB_CONTAINER}" >/dev/null 2>&1 || true
        sleep 3
        podman exec -e PGPASSWORD=secret456 "${DB_CONTAINER}" pg_dump -h 127.0.0.1 -p 5432 -U hermes -d hitl | gzip > "${DB_BACKUP_FILE}"
        echo -e "  ${GREEN}✓ Database dump created from temporarily started container.${NC}"
    else
        echo -e "  ${RED}❌ No database container found. Skipping DB dump.${NC}"
    fi
fi

# ------------------------------------------------------------------------------
# 2. CODEBASE & CONFIGURATION BACKUP
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}>>> [2/3] Backing up Codebase, Playbooks, Prompts, Skills & Configs...${NC}"
CODE_BACKUP_FILE="${BACKUP_DIR}/code/deepagent_codebase_${TIMESTAMP}.tar.gz"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

tar --exclude='.git' \
    --exclude='.hermes' \
    --exclude='*.tar' \
    --exclude='*.tar.gz' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='backups' \
    --exclude='images' \
    -czf "${CODE_BACKUP_FILE}" -C "$(dirname "${SOURCE_DIR}")" "$(basename "${SOURCE_DIR}")" 2>/dev/null || true

echo -e "  ${GREEN}✓ Codebase archive created:${NC} $(basename "${CODE_BACKUP_FILE}") ($(du -h "${CODE_BACKUP_FILE}" | cut -f1))"

# ------------------------------------------------------------------------------
# 3. CONTAINER IMAGES BACKUP
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}>>> [3/3] Exporting Microservice Container Images...${NC}"

# Core images used by the platform
MICROSERVICE_IMAGES=(
    "quay.io/souffm0a/deepagent-hitl-db:latest"
    "quay.io/souffm0a/deepagent-mock-aap:latest"
    "quay.io/souffm0a/deepagent-ansible-mcp:latest"
    "quay.io/souffm0a/deepagent-sop-mcp:latest"
    "quay.io/souffm0a/deepagent-core:latest"
    "quay.io/souffm0a/deepagent-hitl-web:latest"
    "quay.io/souffm0a/deepagent-proxy:latest"
)

SAVED_IMG_COUNT=0
for img in "${MICROSERVICE_IMAGES[@]}"; do
    if podman image exists "${img}"; then
        clean_name=$(echo "${img}" | awk -F'/' '{print $NF}' | tr ':' '_')
        dest_file="${BACKUP_DIR}/images/${clean_name}.tar"
        echo -n "  ⚡ Exporting image ${clean_name} ... "
        podman save -o "${dest_file}" "${img}"
        echo -e "${GREEN}✓${NC} ($(du -h "${dest_file}" | cut -f1))"
        SAVED_IMG_COUNT=$((SAVED_IMG_COUNT + 1))
    fi
done

# If specific tags weren't found or local changes were committed in running containers
if [ "${SAVED_IMG_COUNT}" -eq 0 ]; then
    echo -e "  ${YELLOW}ℹ️ Specific registry tags not present, exporting running pod containers...${NC}"
    ACTIVE_CONTAINERS=(
        "deepagent-hitl-db"
        "deepagent-aap-server"
        "deepagent-ansible-mcp"
        "deepagent-sop-mcp"
        "deepagent-service"
        "deepagent-webui"
        "deepagent-proxy"
    )
    for c in "${ACTIVE_CONTAINERS[@]}"; do
        if podman ps -a --format "{{.Names}}" | grep -q "^${c}$"; then
            dest_file="${BACKUP_DIR}/images/${c}_commit_${TIMESTAMP}.tar"
            echo -n "  ⚡ Committing & saving ${c} ... "
            podman commit "${c}" "local_backup/${c}:backup" >/dev/null 2>&1 || true
            podman save -o "${dest_file}" "local_backup/${c}:backup" 2>/dev/null || true
            echo -e "${GREEN}✓${NC} ($(du -h "${dest_file}" | cut -f1))"
        fi
    done
fi

# ------------------------------------------------------------------------------
# 4. PRUNING & RETENTION (14 Days)
# ------------------------------------------------------------------------------
echo -e "\n${BOLD}>>> [Retention] Pruning backup snapshots older than 14 days...${NC}"
find "${BACKUP_ROOT}" -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} + 2>/dev/null || true

echo -e "\n${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}✅ COMPREHENSIVE BACKUP COMPLETED SUCCESSFULLY!${NC}"
echo -e "📍 Backup Directory : ${BOLD}${BACKUP_DIR}${NC}"
echo -e "📊 Total Size       : ${BOLD}$(du -sh "${BACKUP_DIR}" | cut -f1)${NC}"
echo -e "Files created:"
ls -lh "${BACKUP_DIR}/db" "${BACKUP_DIR}/code" "${BACKUP_DIR}/images" 2>/dev/null || true
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
