#!/usr/bin/env bash
# ==============================================================================
# 💾 Deep Agent: Automated PostgreSQL Database Backup Script
# ==============================================================================
# Backs up the hitl database (HITL requests, system_settings, domain_subagents)
# Compresses backup using gzip and enforces a 14-day retention policy.
# ==============================================================================

set -euo pipefail

BACKUP_DIR="${HOME}/backups/deepagent"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/deepagent_hitl_db_${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Starting PostgreSQL backup of 'hitl' database..."

if podman ps --format "{{.Names}}" | grep -q "deepagent-hitl-db"; then
    podman exec deepagent-hitl-db pg_dump -U hermes -d hitl | gzip > "${BACKUP_FILE}"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup successfully created: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️ Warning: Container 'deepagent-hitl-db' is not running. Backup skipped."
    exit 1
fi

# Clean up backups older than 14 days
echo "[$(date +'%Y-%m-%d %H:%M:%S')] Pruning backups older than 14 days..."
find "${BACKUP_DIR}" -type f -name "deepagent_hitl_db_*.sql.gz" -mtime +14 -delete

echo "[$(date +'%Y-%m-%d %H:%M:%S')] Backup maintenance complete."
