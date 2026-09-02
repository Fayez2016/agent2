#!/usr/bin/env bash
# ==============================================================================
#  📦 Pack & Push Offline .tar.gz Image Dump to Quay.io as a Carrier Container
# ==============================================================================
#  Repository: quay.io/souffm0a/deepagent-tarball:latest & v1.2.0-20260902
# ==============================================================================

set -euo pipefail

QUAY_USER="souffm0a"
QUAY_TOKEN="${QUAY_TOKEN:-kNC@4P_BAFnVf6!}"
REGISTRY="quay.io/${QUAY_USER}"
TIMESTAMP="$(date +%Y%m%d)"
TARBALL_SRC="/home/fayez/agent2/offline_releases/deepagent_full_images_dump_v1.2.0-20260902.tar.gz"
BUILD_DIR="/tmp/quay_tarball_carrier_build_${TIMESTAMP}"

echo "================================================================================"
echo " 📦 PACKING OFFLINE TARBALL DUMP INTO QUAY.IO CARRIER IMAGE"
echo " 📂 Source Tarball : ${TARBALL_SRC}"
echo " 👤 Quay Target    : ${REGISTRY}/deepagent-tarball:latest"
echo "================================================================================"

if [ ! -f "${TARBALL_SRC}" ]; then
    echo "❌ Error: Tarball source not found at ${TARBALL_SRC}"
    exit 1
fi

rm -rf "${BUILD_DIR}"
mkdir -p "${BUILD_DIR}"

# Copy tarball, checksum, and deploy script into container context
cp "${TARBALL_SRC}" "${BUILD_DIR}/deepagent_full_images_dump.tar.gz"
cp "${TARBALL_SRC}.sha256" "${BUILD_DIR}/deepagent_full_images_dump.tar.gz.sha256"
cp /home/fayez/agent2/deploy_from_offline_bundle.sh "${BUILD_DIR}/deploy_from_offline_bundle.sh"

cat << 'CONTAINER_EOF' > "${BUILD_DIR}/Containerfile"
FROM docker.io/library/alpine:latest
LABEL maintainer="Deep Agent SRE Team"
LABEL version="v1.2.0-tarball"
LABEL description="Offline Container Tarball Dump Carrier for Deep Agent Platform"

WORKDIR /opt/deepagent_offline
COPY deepagent_full_images_dump.tar.gz ./
COPY deepagent_full_images_dump.tar.gz.sha256 ./
COPY deploy_from_offline_bundle.sh ./

RUN chmod +x deploy_from_offline_bundle.sh

CMD ["/bin/sh", "-c", "echo 'Deep Agent Offline Tarball Carrier. Run podman cp to extract tarball.'; ls -lh /opt/deepagent_offline"]
CONTAINER_EOF

echo "  🔨 Building carrier container image ..."
podman build -t "localhost/deepagent-tarball:latest" "${BUILD_DIR}"

echo -n "🔑 Authenticating with quay.io ... "
echo "${QUAY_TOKEN}" | podman login -u "${QUAY_USER}" --password-stdin quay.io
echo "✓ Success."

TARGET_TAG="${REGISTRY}/deepagent-tarball:v1.2.0-${TIMESTAMP}"
TARGET_LATEST="${REGISTRY}/deepagent-tarball:latest"

echo "  🏷️ Tagging -> ${TARGET_TAG}"
podman tag "localhost/deepagent-tarball:latest" "${TARGET_TAG}"
podman tag "localhost/deepagent-tarball:latest" "${TARGET_LATEST}"

echo "  ⬆️ Pushing Tarball Carrier Image to Quay.io ..."
podman push "${TARGET_TAG}"
podman push "${TARGET_LATEST}"
echo "  ✓ [deepagent-tarball] Uploaded to Quay.io successfully."

rm -rf "${BUILD_DIR}"

echo -e "\n================================================================================"
echo " 🎉 OFFLINE TARBALL DUMP CONTAINER PUBLISHED TO QUAY.IO!"
echo " 📦 Image Name: quay.io/souffm0a/deepagent-tarball:latest"
echo " 📦 Image Tag : quay.io/souffm0a/deepagent-tarball:v1.2.0-${TIMESTAMP}"
echo ""
echo " 💡 How to Extract & Deploy on an Air-Gapped / Downstream Server:"
echo "    1. podman pull quay.io/souffm0a/deepagent-tarball:latest"
echo "    2. podman create --name temp-dump quay.io/souffm0a/deepagent-tarball:latest"
echo "    3. podman cp temp-dump:/opt/deepagent_offline/ ."
echo "    4. podman rm temp-dump"
echo "    5. cd deepagent_offline && ./deploy_from_offline_bundle.sh ./deepagent_full_images_dump.tar.gz"
echo "================================================================================"
