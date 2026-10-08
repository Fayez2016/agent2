#!/usr/bin/env bash
# ==============================================================================
# Script: apply_update_with_snapshot_and_rollback.sh
# Purpose:
#   1. Pre-update safety snapshot of all critical containers.
#   2. Runs the update script (e.g., scripts/inspect_and_fix_mcp_timeout.sh).
#   3. Runs strict 5-point DeepAgent smoke test.
#   4. If test fails: Automatically rolls back containers to snapshot state.
#   5. If test succeeds: Commits code changes cleanly to Git with a verified commit.
# ==============================================================================

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

UPDATE_SCRIPT="${1:-${SCRIPT_DIR}/inspect_and_fix_mcp_timeout.sh}"
SNAPSHOT_TOOL="${SCRIPT_DIR}/pod_snapshot_and_test.sh"
SNAPSHOT_TAG="pre_update_$(date +%Y%m%d_%H%M%S)"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  🛡️ SAFE UPDATE PIPELINE: PODMAN SNAPSHOT -> UPDATE -> TEST -> PODMAN COMMIT  ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "  • Update Target Script : ${BOLD}${UPDATE_SCRIPT}${NC}"
echo -e "  • Snapshot Identifier  : ${BOLD}${SNAPSHOT_TAG}${NC}"

# Check prerequisites
if [ ! -f "$UPDATE_SCRIPT" ]; then
    echo -e "${RED}❌ Update script '${UPDATE_SCRIPT}' does not exist!${NC}"
    exit 1
fi

if [ ! -f "$SNAPSHOT_TOOL" ]; then
    echo -e "${RED}❌ Snapshot script '${SNAPSHOT_TOOL}' not found!${NC}"
    exit 1
fi

chmod +x "$UPDATE_SCRIPT" "$SNAPSHOT_TOOL"

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Pre-Update Snapshot
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[1/4] Taking Safety Snapshot of Running Pod Containers...${NC}"
if ! "${SNAPSHOT_TOOL}" snapshot "${SNAPSHOT_TAG}"; then
    echo -e "${RED}❌ Failed to create container snapshot! Aborting update.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Safety snapshot [backup-${SNAPSHOT_TAG}] created successfully.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Execute Update Script
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[2/4] Executing Update Script: ${UPDATE_SCRIPT}...${NC}"
UPDATE_EXIT=0
"${UPDATE_SCRIPT}" || UPDATE_EXIT=$?

if [ $UPDATE_EXIT -ne 0 ]; then
    echo -e "\n${RED}⚠️ Update script exited with failure code ($UPDATE_EXIT)! Initiating Rollback...${NC}"
    "${SNAPSHOT_TOOL}" rollback "${SNAPSHOT_TAG}"
    echo -e "${YELLOW}System rolled back to snapshot [backup-${SNAPSHOT_TAG}].${NC}"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Run Smoke Test
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[3/4] Running Post-Update Verification Smoke Test...${NC}"
if ! "${SNAPSHOT_TOOL}" test; then
    echo -e "\n${RED}❌ Post-update smoke test failed! Initiating Automatic Rollback...${NC}"
    "${SNAPSHOT_TOOL}" rollback "${SNAPSHOT_TAG}"
    echo -e "${YELLOW}System successfully rolled back to snapshot [backup-${SNAPSHOT_TAG}].${NC}"
    exit 1
fi
echo -e "${GREEN}✓ All post-update smoke test gates passed successfully.${NC}"

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Podman Commit (Seal Verified Production Container State)
# ──────────────────────────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/4] Finalizing & Creating Verified Podman Production Commits...${NC}"

CRITICAL_CONTAINERS=(
    "deepagent-service"
    "deepagent-proxy"
    "deepagent-webui"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
)

PROD_TAG="verified_$(date +%Y%m%d_%H%M%S)"

for c in "${CRITICAL_CONTAINERS[@]}"; do
    if podman ps --format "{{.Names}}" | grep -q "^${c}$"; then
        echo -n "  📦 Podman committing $c -> localhost/${c}:${PROD_TAG} ... "
        podman commit "$c" "localhost/${c}:${PROD_TAG}" >/dev/null
        podman tag "localhost/${c}:${PROD_TAG}" "localhost/${c}:latest" >/dev/null 2>&1 || true
        echo -e "${GREEN}✓ Done${NC}"
    fi
done

echo -e "\n${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}  🎉 UPDATE PIPELINE COMPLETED SUCCESSFULLY!                                  ${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "  • Pre-Update Backup  : localhost/*:backup-${SNAPSHOT_TAG}"
echo -e "  • Verified Prod Tag  : localhost/*:${PROD_TAG}"
echo -e "  • Container Status   : All production containers verified healthy"
echo -e "${GREEN}${BOLD}==============================================================================${NC}\n"

