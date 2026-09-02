#!/usr/bin/env bash
# ==============================================================================
#  📦 Dual-Track Quay.io Release Tool (Full Production Dumps & Code-Only Patches)
# ==============================================================================
#  Quay Namespace : quay.io/souffm0a/
#  Track 1 (Full Images Dump) : Complete standalone microservice images + TLS Proxy
#  Track 2 (Code-Only Version): Lightweight runtime layer / code distribution
# ==============================================================================

set -euo pipefail

QUAY_USER="souffm0a"
QUAY_TOKEN="${QUAY_TOKEN:-kNC@4P_BAFnVf6!}"
QUAY_REGISTRY="quay.io/${QUAY_USER}"
TIMESTAMP="$(date +%Y%m%d)"
FULL_TAG="full-v1.2.0-${TIMESTAMP}"
CODE_TAG="code-v1.2.0-${TIMESTAMP}"

echo "================================================================================"
echo " 🚀 DUAL-TRACK RELEASE TO QUAY.IO REGISTRY"
echo " 👤 User / Namespace : ${QUAY_USER}"
echo " 📦 Track 1 Tag       : ${FULL_TAG} & latest-full"
echo " 📦 Track 2 Tag       : ${CODE_TAG} & latest-code"
echo "================================================================================"

# 1. Authenticate with Quay.io
echo -n "🔑 Authenticating with quay.io ... "
echo "${QUAY_TOKEN}" | podman login -u "${QUAY_USER}" --password-stdin quay.io
echo "✓ Success."

# Ensure reverse proxy is built
if [ -d "/home/fayez/agent2/deepagent_system/reverse_proxy" ]; then
    echo "  🔨 Re-verifying reverse proxy container build ..."
    podman build -t "localhost/deepagent-proxy:latest" /home/fayez/agent2/deepagent_system/reverse_proxy/ >/dev/null
fi

# ==============================================================================
# TRACK 1: FULL IMAGES DUMP
# ==============================================================================
echo -e "\n================================================================================"
echo " 🧱 [TRACK 1] PUSHING FULL PRODUCTION IMAGES DUMP"
echo "================================================================================"

declare -A FULL_IMAGES=(
    ["deepagent-core"]="localhost/deepagent-core:latest"
    ["deepagent-ansible-mcp"]="localhost/agent2_ansible-mcp:latest"
    ["deepagent-sop-mcp"]="localhost/deepagent_sop-mcp:latest"
    ["deepagent-hitl-db"]="localhost/agent2_hitl-db:latest"
    ["deepagent-mock-aap"]="localhost/deepagent_mock-aap:latest"
    ["deepagent-hitl-web"]="localhost/agent2_hitl-web:latest"
    ["deepagent-proxy"]="localhost/deepagent-proxy:latest"
)

for img in "${!FULL_IMAGES[@]}"; do
    src="${FULL_IMAGES[$img]}"
    target_tag="${QUAY_REGISTRY}/${img}:${FULL_TAG}"
    target_latest="${QUAY_REGISTRY}/${img}:latest"
    target_latest_full="${QUAY_REGISTRY}/${img}:latest-full"

    echo "  ⚡ Tagging & Pushing Full Image: ${img} ..."
    podman tag "${src}" "${target_tag}"
    podman tag "${src}" "${target_latest}"
    podman tag "${src}" "${target_latest_full}"

    podman push "${target_tag}"
    podman push "${target_latest}"
    podman push "${target_latest_full}"
    echo "  ✓ [${img}] Full image pushed."
done

# ==============================================================================
# TRACK 2: CODE-ONLY VERSION (Lightweight Application Code Layer)
# ==============================================================================
echo -e "\n================================================================================"
echo " 📜 [TRACK 2] BUILDING & PUSHING CODE-ONLY CONTAINER IMAGE"
echo "================================================================================"

CODE_BUILD_DIR="/tmp/quay_code_build_${TIMESTAMP}"
rm -rf "${CODE_BUILD_DIR}"
mkdir -p "${CODE_BUILD_DIR}/deepagent_system" "${CODE_BUILD_DIR}/deployment_tools"

# Copy clean source code and deployment scripts
rsync -av --exclude '__pycache__' \
          --exclude '*.pyc' \
          --exclude '.git' \
          --exclude 'node_modules' \
          --exclude 'venv' \
          --exclude 'raw_traces' \
          /home/fayez/agent2/deepagent_system/ \
          "${CODE_BUILD_DIR}/deepagent_system/" >/dev/null

cp /home/fayez/agent2/satellite_import_and_publish.sh "${CODE_BUILD_DIR}/deployment_tools/"
cp /home/fayez/agent2/apply_airgap_patch.sh "${CODE_BUILD_DIR}/deployment_tools/"
cp /home/fayez/agent2/system_updater.sh "${CODE_BUILD_DIR}/deployment_tools/"
cp /home/fayez/agent2/push_to_quay.sh "${CODE_BUILD_DIR}/deployment_tools/"

# Create lightweight Containerfile for Code Version
cat << 'DOCKERFILE_EOF' > "${CODE_BUILD_DIR}/Containerfile"
FROM docker.io/library/alpine:latest
LABEL maintainer="Deep Agent SRE Team"
LABEL version="v1.2.0-code"
LABEL description="Deep Agent Pure Code, Reverse Proxy, FastMCP Servers & Deployment Tools Distribution"

WORKDIR /opt/deepagent
COPY deepagent_system/ ./deepagent_system/
COPY deployment_tools/ ./deployment_tools/

CMD ["/bin/sh", "-c", "echo 'Deep Agent Code Package v1.2.0 (with TLS Reverse Proxy)'; ls -la /opt/deepagent"]
DOCKERFILE_EOF

echo "  🔨 Building lightweight code image ..."
podman build -t "localhost/deepagent-code-release:latest" "${CODE_BUILD_DIR}"

CODE_TARGET_TAG="${QUAY_REGISTRY}/deepagent-code:${CODE_TAG}"
CODE_TARGET_LATEST="${QUAY_REGISTRY}/deepagent-code:latest"
CODE_TARGET_LATEST_CODE="${QUAY_REGISTRY}/deepagent-code:latest-code"

echo "  🏷️ Tagging Code Image -> ${CODE_TARGET_TAG}"
podman tag "localhost/deepagent-code-release:latest" "${CODE_TARGET_TAG}"
podman tag "localhost/deepagent-code-release:latest" "${CODE_TARGET_LATEST}"
podman tag "localhost/deepagent-code-release:latest" "${CODE_TARGET_LATEST_CODE}"

echo "  ⬆️ Pushing Code Image to Quay.io ..."
podman push "${CODE_TARGET_TAG}"
podman push "${CODE_TARGET_LATEST}"
podman push "${CODE_TARGET_LATEST_CODE}"
echo "  ✓ [deepagent-code] Code-only release pushed successfully."

rm -rf "${CODE_BUILD_DIR}"

echo -e "\n================================================================================"
echo " 🎉 DUAL-TRACK RELEASE TO QUAY.IO COMPLETE (WITH TLS REVERSE PROXY)!"
echo "================================================================================"
echo " 📦 Track 1 (Full Images Dump):"
echo "    - quay.io/souffm0a/deepagent-core:latest-full"
echo "    - quay.io/souffm0a/deepagent-ansible-mcp:latest-full"
echo "    - quay.io/souffm0a/deepagent-sop-mcp:latest-full"
echo "    - quay.io/souffm0a/deepagent-hitl-db:latest-full"
echo "    - quay.io/souffm0a/deepagent-mock-aap:latest-full"
echo "    - quay.io/souffm0a/deepagent-hitl-web:latest-full"
echo "    - quay.io/souffm0a/deepagent-proxy:latest-full (TLS 1.3 Reverse Proxy)"
echo ""
echo " 📜 Track 2 (Code-Only Release):"
echo "    - quay.io/souffm0a/deepagent-code:latest-code"
echo "    - quay.io/souffm0a/deepagent-code:${CODE_TAG}"
echo "================================================================================"
