#!/usr/bin/env bash
# ==============================================================================
#  📦 Enterprise Quay.io Container Registry Release & Full Dump Tool
# ==============================================================================
#  Target Registry : quay.io/souffm0a/*
# ==============================================================================

set -euo pipefail

QUAY_USER="souffm0a"
QUAY_TOKEN="${QUAY_TOKEN:-kNC@4P_BAFnVf6!}"
QUAY_REGISTRY="quay.io/${QUAY_USER}"
VERSION_TAG="v1.2.0-$(date +%Y%m%d)"
SAVE_TARBALL=false

for arg in "$@"; do
    case "$arg" in
        --save-tarball)
            SAVE_TARBALL=true
            ;;
        --help|-h)
            echo "Usage: ./push_to_quay.sh [--save-tarball]"
            exit 0
            ;;
    esac
done

echo "================================================================================"
echo " 🚀 INITIATING DEEP AGENT ENTERPRISE RELEASE TO QUAY.IO"
echo " 👤 Registry User : ${QUAY_USER}"
echo " 🏷️ Version Tag    : ${VERSION_TAG}"
echo "================================================================================"

# 1. Authenticate with Quay.io
echo -n "🔑 Authenticating with quay.io ... "
echo "${QUAY_TOKEN}" | podman login -u "${QUAY_USER}" --password-stdin quay.io
echo "✓ SUCCESS"

# Map of Target Quay Repo -> Actual Local Image Name
declare -A IMAGES=(
    ["deepagent-core"]="localhost/deepagent-core:latest"
    ["deepagent-ansible-mcp"]="localhost/agent2_ansible-mcp:latest"
    ["deepagent-sop-mcp"]="localhost/deepagent_sop-mcp:latest"
    ["deepagent-hitl-db"]="localhost/agent2_hitl-db:latest"
    ["deepagent-mock-aap"]="localhost/deepagent_mock-aap:latest"
    ["deepagent-hitl-web"]="localhost/agent2_hitl-web:latest"
    ["deepagent-proxy"]="localhost/deepagent-proxy:latest"
)

# 2. Tag and Push Images
echo -e "\n📦 Tagging and Pushing Microservices to quay.io/${QUAY_USER}/..."
for img in "${!IMAGES[@]}"; do
    local_src="${IMAGES[$img]}"
    quay_target_latest="${QUAY_REGISTRY}/${img}:latest"
    quay_target_ver="${QUAY_REGISTRY}/${img}:${VERSION_TAG}"

    echo "  ⚡ Processing [${img}] from [${local_src}] ..."

    echo "    🏷️ Tagging -> ${quay_target_latest}"
    podman tag "${local_src}" "${quay_target_latest}"
    podman tag "${local_src}" "${quay_target_ver}"

    echo "    ⬆️ Pushing -> ${quay_target_latest} ..."
    podman push "${quay_target_latest}"
    
    echo "    ⬆️ Pushing -> ${quay_target_ver} ..."
    podman push "${quay_target_ver}"
    echo "    ✓ [${img}] pushed successfully."
done

# 3. Full Offline Container Tarball Dump Export
if [ "${SAVE_TARBALL}" = true ]; then
    BUNDLE_FILE="/tmp/deepagent_full_images_dump_${VERSION_TAG}.tar.gz"
    echo -e "\n💾 Generating Full Offline Container Tarball Dump ..."

    podman save \
        "${QUAY_REGISTRY}/deepagent-core:latest" \
        "${QUAY_REGISTRY}/deepagent-ansible-mcp:latest" \
        "${QUAY_REGISTRY}/deepagent-sop-mcp:latest" \
        "${QUAY_REGISTRY}/deepagent-hitl-db:latest" \
        "${QUAY_REGISTRY}/deepagent-mock-aap:latest" \
        "${QUAY_REGISTRY}/deepagent-hitl-web:latest" \
        "${QUAY_REGISTRY}/deepagent-proxy:latest" \
        | gzip -c > "${BUNDLE_FILE}"

    cd /tmp && sha256sum "$(basename "${BUNDLE_FILE}")" > "${BUNDLE_FILE}.sha256"
    BUNDLE_SIZE=$(du -h "${BUNDLE_FILE}" | cut -f1)
    echo "✓ Full offline container dump saved to: ${BUNDLE_FILE} (${BUNDLE_SIZE})"
    echo "✓ Checksum saved to                   : ${BUNDLE_FILE}.sha256"
fi

echo -e "\n================================================================================"
echo " 🎉 FULL RELEASE COMPLETE: All images published to Quay.io & Dumped to Disk!"
echo " 🌐 Repository: https://quay.io/organization/${QUAY_USER}"
echo "================================================================================"
