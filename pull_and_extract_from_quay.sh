#!/usr/bin/env bash
# ==============================================================================
#  📥 Pull Offline Carrier Bundle from Quay & Extract (Phase 2 OCI Artifact)
# ==============================================================================
#  Usage:
#    ./pull_and_extract_from_quay.sh [--quay-user souffm0a] [--dest-dir /target]
# ==============================================================================

set -euo pipefail

QUAY_USER="${QUAY_USER:-souffm0a}"
REGISTRY="quay.io/${QUAY_USER}/deepagent-offline-bundle:latest"
DEST_DIR="${1:-$(pwd)/offline_extracted}"

echo "================================================================================"
echo " 📥 PULLING AIRGAP CARRIER BUNDLE FROM QUAY REGISTRY"
echo " 🏷️ Image Source : ${REGISTRY}"
echo " 📂 Target Dir   : ${DEST_DIR}"
echo "================================================================================"

mkdir -p "${DEST_DIR}"

echo -e "\n⚡ Pulling carrier bundle container from Quay.io ..."
podman pull "${REGISTRY}"

echo -e "\n📦 Extracting carrier tarball from OCI image layer ..."
CONTAINER_ID=$(podman create "${REGISTRY}")
podman cp "${CONTAINER_ID}:/bundle/deepagent-offline-carrier-bundle.tar.gz" "${DEST_DIR}/deepagent-offline-carrier-bundle.tar.gz"
podman rm -f "${CONTAINER_ID}" >/dev/null

echo -e "\n📂 Unpacking airgap release package ..."
tar -xzf "${DEST_DIR}/deepagent-offline-carrier-bundle.tar.gz" -C "${DEST_DIR}"

echo "================================================================================"
echo " 🎉 CARRIER BUNDLE READY FOR AIRGAP PROMOTION!"
echo " 📂 Extracted Location: ${DEST_DIR}"
echo " 🚀 Run Installer     : cd ${DEST_DIR}/deepagent-offline-carrier-bundle-* && ./offline_install.sh"
echo "================================================================================"
