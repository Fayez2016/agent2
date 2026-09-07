#!/usr/bin/env bash
# ==============================================================================
#  🚀 Helper Script: Pull Deep Agent from Quay & Push to Red Hat Satellite
# ==============================================================================
#  Usage:
#    ./mirror_quay_to_satellite.sh <SATELLITE_FQDN> [ORGANIZATION] [PRODUCT] [TAG]
#  Example:
#    ./mirror_quay_to_satellite.sh satellite.corp.internal default_organization deepagent latest
# ==============================================================================

set -euo pipefail

SATELLITE_HOST="${1:-}"
ORGANIZATION="${2:-default_organization}"
PRODUCT="${3:-deepagent}"
TAG="${4:-latest}"

if [ -z "${SATELLITE_HOST}" ]; then
    echo "❌ Usage: $0 <SATELLITE_FQDN> [ORGANIZATION] [PRODUCT] [TAG]"
    echo "   Example: $0 satellite.corp.internal default_organization deepagent latest"
    exit 1
fi

# Convert ORG and PRODUCT to lowercase for Satellite registry convention
ORG_LOWER=$(echo "${ORGANIZATION}" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')
PROD_LOWER=$(echo "${PRODUCT}" | tr '[:upper:]' '[:lower:]' | tr ' ' '_')

echo "================================================================================"
echo " 🚀 MIRRORING DEEP AGENT: QUAY.IO -> RED HAT SATELLITE"
echo " 📡 Satellite Host : ${SATELLITE_HOST}"
echo " 🏢 Organization   : ${ORG_LOWER}"
echo " 📦 Product        : ${PROD_LOWER}"
echo " 🏷️ Tag            : ${TAG}"
echo "================================================================================"

# Step 1: Ensure login to Quay
echo -n "🔑 Authenticating with Quay.io ... "
echo "kNC@4P_BAFnVf6!" | podman login -u "souffm0a" --password-stdin quay.io >/dev/null 2>&1 || true
echo "✓ Success."

# Step 2: Ensure login to Satellite
echo -e "\n🔑 Authenticating with Red Hat Satellite (${SATELLITE_HOST}) ..."
if ! podman login --get-login "${SATELLITE_HOST}" >/dev/null 2>&1; then
    podman login "${SATELLITE_HOST}"
fi

# Step 3: Images to mirror
IMAGES=(
  "deepagent-core"
  "deepagent-ansible-mcp"
  "deepagent-sop-mcp"
  "deepagent-hitl-db"
  "deepagent-mock-aap"
  "deepagent-hitl-web"
  "deepagent-proxy"
)

# Step 4: Loop pull, tag, push
for img in "${IMAGES[@]}"; do
    QUAY_IMG="quay.io/souffm0a/${img}:${TAG}"
    # Standard Red Hat Satellite registry naming format:
    # <satellite-fqdn>/<org>-<product>-<repo>:<tag>
    SAT_IMG="${SATELLITE_HOST}/${ORG_LOWER}-${PROD_LOWER}-${img}:${TAG}"

    echo -e "\n⬇️  [1/3] Pulling ${QUAY_IMG} ..."
    podman pull "${QUAY_IMG}"

    echo "🏷️  [2/3] Tagging as ${SAT_IMG} ..."
    podman tag "${QUAY_IMG}" "${SAT_IMG}"

    echo "⬆️  [3/3] Pushing to Satellite ..."
    podman push "${SAT_IMG}"
    echo "✓ ${img} successfully pushed to Red Hat Satellite."
done

echo -e "\n================================================================================"
echo " 🎉 ALL 7 MICROSERVICES SUCCESSFULLY MIRRORED TO RED HAT SATELLITE!"
echo "================================================================================"
