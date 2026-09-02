#!/usr/bin/env bash
# ==============================================================================
#  🛰️ Red Hat Satellite 6 Container Repository Import & Publish Tool
# ==============================================================================
#  Purpose:
#    Loads the offline Deep Agent container tarball on the Red Hat Satellite server,
#    creates container repositories in Satellite (via Hammer CLI or crane/skopeo),
#    tags, and pushes them to Satellite's internal Container Registry (Pulp/Crane)
#    so target RHEL servers can pull them directly via `podman pull`.
# ==============================================================================

set -euo pipefail

# ------------------------------------------------------------------------------
# Configuration Variables (Adjust as needed for your Satellite environment)
# ------------------------------------------------------------------------------
SATELLITE_FQDN="${SATELLITE_FQDN:-$(hostname -f)}"
SATELLITE_ORG="${SATELLITE_ORG:-Default_Organization}"
SATELLITE_PRODUCT="${SATELLITE_PRODUCT:-DeepAgent_Platform}"
SATELLITE_USER="${SATELLITE_USER:-admin}"
SATELLITE_PASS="${SATELLITE_PASS:-}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"

# Tarball file path passed as first argument, or default location
TARBALL_PATH="${1:-/home/fayez/agent2/offline_releases/deepagent_full_images_dump_v1.2.0-20260902.tar.gz}"

# Core images to import and publish
IMAGES=(
    "deepagent-core"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
    "deepagent-hitl-db"
    "deepagent-mock-aap"
    "deepagent-hitl-web"
    "deepagent-proxy"
)
TAG="latest"

echo "================================================================================"
echo " 🛰️ RED HAT SATELLITE CONTAINER REPOSITORY IMPORT & PUBLISH"
echo " 🏢 Satellite FQDN  : ${SATELLITE_FQDN}:${REGISTRY_PORT}"
echo " 🏢 Organization    : ${SATELLITE_ORG}"
echo " 📦 Product Name    : ${SATELLITE_PRODUCT}"
echo " 📂 Archive File    : ${TARBALL_PATH}"
echo "================================================================================"

# Step 1: Verify Tarball and Checksum
if [ ! -f "${TARBALL_PATH}" ]; then
    echo "❌ ERROR: Container archive '${TARBALL_PATH}' not found!"
    exit 1
fi

echo -n "🔍 Checking tarball integrity ... "
if [ -f "${TARBALL_PATH}.sha256" ]; then
    cd "$(dirname "${TARBALL_PATH}")" && sha256sum -c "$(basename "${TARBALL_PATH}.sha256")"
    echo "✓ SHA-256 Checksum Verified."
else
    echo "✓ Archive present (${TARBALL_PATH})."
fi

# Step 2: Load Images into Local Podman Store on Satellite Server
echo -e "\n📦 Loading container images from tarball into Podman ..."
podman load -i "${TARBALL_PATH}"
echo "✓ Images loaded successfully into local Podman store."

# Step 3: Ensure Satellite Product Exists (Using Hammer CLI if available)
if command -v hammer >/dev/null 2>&1; then
    echo -e "\n🔨 Configuring Red Hat Satellite Product & Container Repositories via Hammer CLI..."
    
    HAMMER_AUTH=""
    if [ -n "${SATELLITE_PASS}" ]; then
        HAMMER_AUTH="-u ${SATELLITE_USER} -p ${SATELLITE_PASS}"
    fi

    # Check/Create Product
    if ! hammer ${HAMMER_AUTH} product info --name "${SATELLITE_PRODUCT}" --organization "${SATELLITE_ORG}" >/dev/null 2>&1; then
        echo "  ➕ Creating Product: ${SATELLITE_PRODUCT} ..."
        hammer ${HAMMER_AUTH} product create \
            --name "${SATELLITE_PRODUCT}" \
            --organization "${SATELLITE_ORG}" \
            --description "Deep Agent SRE Microservices Container Product"
    else
        echo "  ✓ Product ${SATELLITE_PRODUCT} already exists."
    fi

    # Create Docker Repositories inside Satellite Product
    for img in "${IMAGES[@]}"; do
        if ! hammer ${HAMMER_AUTH} repository info --name "${img}" --product "${SATELLITE_PRODUCT}" --organization "${SATELLITE_ORG}" >/dev/null 2>&1; then
            echo "  ➕ Creating Container Repository: ${img} ..."
            hammer ${HAMMER_AUTH} repository create \
                --name "${img}" \
                --product "${SATELLITE_PRODUCT}" \
                --organization "${SATELLITE_ORG}" \
                --content-type "docker" \
                --url ""
        else
            echo "  ✓ Repository ${img} already exists."
        fi
    done
else
    echo "ℹ️ Hammer CLI not detected on current host. Proceeding with direct Skopeo/Podman push to Satellite Registry."
fi

# Step 4: Tag & Push to Satellite Container Registry (Pulp/Crane)
SATELLITE_REGISTRY="${SATELLITE_FQDN}:${REGISTRY_PORT}"

echo -e "\n⬆️ Tagging and Pushing Containers to Satellite Internal Registry (${SATELLITE_REGISTRY}) ..."

# Log into Satellite Registry if credentials supplied
if [ -n "${SATELLITE_PASS}" ]; then
    echo -n "🔑 Authenticating with Satellite Registry ... "
    echo "${SATELLITE_PASS}" | podman login -u "${SATELLITE_USER}" --password-stdin --tls-verify=false "${SATELLITE_REGISTRY}"
    echo "✓ Success."
fi

# Push each image to Satellite
for img in "${IMAGES[@]}"; do
    SRC_IMAGE="quay.io/souffm0a/${img}:${TAG}"
    TARGET_IMAGE="${SATELLITE_REGISTRY}/${SATELLITE_ORG,,}-${SATELLITE_PRODUCT,,}-${img}:${TAG}"
    
    # Fallback to alternate local tag if needed
    if ! podman image exists "${SRC_IMAGE}"; then
        if podman image exists "localhost/${img}:${TAG}"; then
            SRC_IMAGE="localhost/${img}:${TAG}"
        fi
    fi

    echo "  🏷️ Tagging: ${SRC_IMAGE} -> ${TARGET_IMAGE}"
    podman tag "${SRC_IMAGE}" "${TARGET_IMAGE}"

    echo "  ⬆️ Pushing: ${TARGET_IMAGE} ..."
    podman push --tls-verify=false "${TARGET_IMAGE}"
    echo "  ✓ ${img} published to Satellite."
done

echo -e "\n================================================================================"
echo " 🎉 ALL IMAGES PUBLISHED TO RED HAT SATELLITE!"
echo "================================================================================"
echo " 📋 How Target Fleet Servers Can Pull from Satellite:"
echo "--------------------------------------------------------------------------------"
for img in "${IMAGES[@]}"; do
    echo "  podman pull ${SATELLITE_REGISTRY}/${SATELLITE_ORG,,}-${SATELLITE_PRODUCT,,}-${img}:${TAG}"
done
echo "================================================================================"
