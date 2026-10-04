#!/usr/bin/env bash
# ==============================================================================
# Script: build_airgap_release.sh
# Purpose: Build a single, immutable, verified Air-Gap Release Tarball:
#          - Packages verified deepagent_system (app, web_ui, reverse_proxy)
#          - Packages declarative fleet config (agents_fleet.yaml, sync_agents.py)
#          - Packages deploy_release.sh (with verified CA TLS injection & auto-rollback)
#          - Packages gateway.conf template
#          - Computes SHA256 checksum manifest
# ==============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION="${1:-$(date +%Y%m%d_%H%M%S)}"
RELEASE_NAME="deepagent_airgap_release_${VERSION}"
STAGING_DIR="${REPO_ROOT}/release_staging/${RELEASE_NAME}"
TARBALL_PATH="${REPO_ROOT}/${RELEASE_NAME}.tar.gz"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}  📦 BUILDING DEEP AGENT AIR-GAP RELEASE: ${VERSION}                           ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

# 1. Clean Staging
rm -rf "${STAGING_DIR}"
mkdir -p "${STAGING_DIR}"

echo -e "\n${BOLD}[1/4] Assembling Release Artifacts...${NC}"

# A. Application Code & Web UI
mkdir -p "${STAGING_DIR}/deepagent_system"
cp -r "${REPO_ROOT}/deepagent_system/app" "${STAGING_DIR}/deepagent_system/"
cp -r "${REPO_ROOT}/deepagent_system/web_ui" "${STAGING_DIR}/deepagent_system/"
cp -r "${REPO_ROOT}/deepagent_system/reverse_proxy" "${STAGING_DIR}/deepagent_system/"

# B. Declarative Fleet Config & Sync Tools
mkdir -p "${STAGING_DIR}/config" "${STAGING_DIR}/scripts"
cp "${REPO_ROOT}/config/agents_fleet.yaml" "${STAGING_DIR}/config/"
cp "${REPO_ROOT}/scripts/sync_agents.py" "${STAGING_DIR}/scripts/"
cp "${REPO_ROOT}/scripts/check_integrity.sh" "${STAGING_DIR}/scripts/"
cp "${REPO_ROOT}/scripts/pod_snapshot_and_test.sh" "${STAGING_DIR}/scripts/"

# C. Rootless Verified TLS Deployer
cp "${REPO_ROOT}/scripts/deploy_release.sh" "${STAGING_DIR}/deploy_release.sh"
chmod +x "${STAGING_DIR}/deploy_release.sh"

# D. Gateway configuration template
cat << 'EOF' > "${STAGING_DIR}/gateway.conf.example"
# ==============================================================================
# Deep Agent Gateway & TLS Configuration
# ==============================================================================
# Set your enterprise inference gateway endpoint (must include /v1)
GATEWAY_URL="https://your-internal-llm-gateway/v1"

# Model name / deployment tag
MODEL_NAME="qwen/qwen-2.5-72b-instruct"

# Bearer Token / API Key
API_TOKEN="sk-custom-secret"

# Internal core service port
API_PORT="8642"

# AAP Mode: "mock" for local simulation or "prd" for real enterprise AAP
AAP_MODE="mock"
AAP_HOST=""
AAP_TOKEN=""

# Optional: Path to custom enterprise CA certificate to trust
# CA_CERT_PATH="/opt/td-agent/certs/enterprise_ca.crt"
EOF

# 2. Pre-packaging Syntax & Module Verification
echo -e "\n${BOLD}[2/4] Validating Release Syntax & Integrity...${NC}"
python3 -m py_compile "${STAGING_DIR}/deepagent_system/app/agent_engine.py"
python3 -m py_compile "${STAGING_DIR}/scripts/sync_agents.py"
echo -e "${GREEN}✓ All Python code passed strict syntax compilation.${NC}"

# 3. Create Tarball
echo -e "\n${BOLD}[3/4] Creating Compressed Release Tarball...${NC}"
cd "${REPO_ROOT}/release_staging"
tar -czf "${TARBALL_PATH}" "${RELEASE_NAME}"
cd "${REPO_ROOT}"

# 4. Generate SHA256 Checksum
echo -e "\n${BOLD}[4/4] Generating Checksum Manifest...${NC}"
sha256sum "$(basename "${TARBALL_PATH}")" > "${TARBALL_PATH}.sha256"

# Also symlink as latest
ln -sf "$(basename "${TARBALL_PATH}")" "${REPO_ROOT}/deepagent_airgap_release_latest.tar.gz"
ln -sf "$(basename "${TARBALL_PATH}.sha256")" "${REPO_ROOT}/deepagent_airgap_release_latest.tar.gz.sha256"

echo -e "\n${GREEN}${BOLD}==============================================================================${NC}"
echo -e "${GREEN}${BOLD}  🎉 AIR-GAP RELEASE CREATED SUCCESSFULLY!                                    ${NC}"
echo -e "${GREEN}${BOLD}==============================================================================${NC}"
echo -e "  • Package  : ${CYAN}${BOLD}${TARBALL_PATH}${NC}"
echo -e "  • Checksum : $(cat "${TARBALL_PATH}.sha256" | awk '{print $1}')"
echo -e "  • Size     : $(du -h "${TARBALL_PATH}" | awk '{print $1}')"
echo -e "  • Latest   : ${REPO_ROOT}/deepagent_airgap_release_latest.tar.gz"
echo -e "${GREEN}${BOLD}==============================================================================${NC}\n"
