#!/usr/bin/env bash
# ==============================================================================
#  📦 Dual-Track Quay.io Release Tool (Full Production Dumps & Code-Only Patches)
# ==============================================================================
set -euo pipefail

QUAY_USER="souffm0a"
QUAY_TOKEN="${QUAY_TOKEN:-kNC@4P_BAFnVf6!}"
QUAY_REGISTRY="quay.io/${QUAY_USER}"
REGISTRY="${QUAY_REGISTRY}"
TIMESTAMP="$(date +%Y%m%d)"
FULL_TAG="full-v1.2.0-${TIMESTAMP}"
CODE_TAG="code-v1.2.0-${TIMESTAMP}"

echo "================================================================================"
echo " 🚀 DUAL-TRACK RELEASE TO QUAY.IO REGISTRY"
echo "================================================================================"

echo -n "🔑 Authenticating with quay.io ... "
echo "${QUAY_TOKEN}" | podman login -u "${QUAY_USER}" --password-stdin quay.io
echo "✓ Success."

# Ensure reverse proxy is built
podman build -t "localhost/deepagent-proxy:latest" /home/fayez/agent2/deepagent_system/reverse_proxy/ >/dev/null

# 1. Map of Target Quay Repo -> EXACT Distinct Local Image
declare -A FULL_IMAGES=(
    ["deepagent-core"]="localhost/deepagent-core:latest"
    ["deepagent-ansible-mcp"]="localhost/agent2_ansible-mcp:latest"
    ["deepagent-sop-mcp"]="localhost/deepagent_sop-mcp:latest"
    ["deepagent-hitl-db"]="localhost/agent2_hitl-db:latest"
    ["deepagent-mock-aap"]="localhost/local-mock-aap:latest"
    ["deepagent-hitl-web"]="localhost/deepagent-hitl-web:latest"
    ["deepagent-proxy"]="localhost/deepagent-proxy:latest"
)

echo -e "\n🧱 [TRACK 1] PUSHING FULL PRODUCTION IMAGES DUMP"
for img in "${!FULL_IMAGES[@]}"; do
    src="${FULL_IMAGES[$img]}"
    target_tag="${QUAY_REGISTRY}/${img}:${FULL_TAG}"
    target_latest="${QUAY_REGISTRY}/${img}:latest"
    target_latest_full="${QUAY_REGISTRY}/${img}:latest-full"

    echo "  ⚡ Tagging & Pushing: ${img} (from ${src}) ..."
    podman tag "${src}" "${target_tag}"
    podman tag "${src}" "${target_latest}"
    podman tag "${src}" "${target_latest_full}"

    podman push "${target_tag}"
    podman push "${target_latest}"
    podman push "${target_latest_full}"
    echo "  ✓ [${img}] Full image pushed."
done

# 2. Re-export and update offline tarball dump
echo -e "\n💾 Generating Corrected Offline Container Tarball Dump ..."
podman save \
    "${QUAY_REGISTRY}/deepagent-core:latest" \
    "${QUAY_REGISTRY}/deepagent-ansible-mcp:latest" \
    "${QUAY_REGISTRY}/deepagent-sop-mcp:latest" \
    "${QUAY_REGISTRY}/deepagent-hitl-db:latest" \
    "${QUAY_REGISTRY}/deepagent-mock-aap:latest" \
    "${QUAY_REGISTRY}/deepagent-hitl-web:latest" \
    "${QUAY_REGISTRY}/deepagent-proxy:latest" \
    | gzip -c > /home/fayez/agent2/offline_releases/deepagent_full_images_dump_v1.2.0-20260902.tar.gz

cd /home/fayez/agent2/offline_releases
sha256sum deepagent_full_images_dump_v1.2.0-20260902.tar.gz > deepagent_full_images_dump_v1.2.0-20260902.tar.gz.sha256

echo "✓ Tarball refreshed."
/home/fayez/agent2/build_and_push_quay_bundle_carrier.sh
echo "🎉 ALL QUAY REPOSITORIES AND CARRIER BUNDLE RESYNCHRONIZED!"
