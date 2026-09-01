#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Enterprise Air-Gapped Release Bundle Generator
# Packages all runtime containers, FastMCP engines, and configs into offline tar.gz
# ==============================================================================

BUNDLE_DIR="/home/fayez/agent2/airgap_release_bundle_$(date +%Y%m%d)"
mkdir -p "${BUNDLE_DIR}/images" "${BUNDLE_DIR}/config" "${BUNDLE_DIR}/scripts"

echo "📦 Creating Air-Gapped Packaging Bundle in ${BUNDLE_DIR}..."

# 1. Export Rootless Podman Storage Configuration
echo "⚙️ Exporting rootless storage configuration with ignore_chown_errors..."
cat << 'STORAGECONF' > "${BUNDLE_DIR}/config/storage.conf"
[storage]
driver = "overlay"
runroot = "/run/user/1000/containers/run"
graphroot = "/home/fayez/.local/share/containers/storage"

[storage.options.overlay]
ignore_chown_errors = "true"
mount_program = "/usr/bin/fuse-overlayfs"
STORAGECONF

# 2. Export Container Images
echo "🐳 Saving Container Images to disk..."
podman save -o "${BUNDLE_DIR}/images/deepagent-hitl-db.tar" localhost/agent2_hitl-db:latest
podman save -o "${BUNDLE_DIR}/images/deepagent-core.tar" localhost/deepagent-core:latest
podman save -o "${BUNDLE_DIR}/images/deepagent-ansible-mcp.tar" localhost/agent2_ansible-mcp:latest
podman save -o "${BUNDLE_DIR}/images/deepagent-sop-mcp.tar" localhost/deepagent_sop-mcp:latest
podman save -o "${BUNDLE_DIR}/images/deepagent-ollama.tar" localhost/local-ollama:gemma4-12b
podman save -o "${BUNDLE_DIR}/images/deepagent-webui.tar" docker.io/library/python:3.11-slim

# 3. Copy Application & UI Source
echo "📂 Copying Web UI and Deep Agent configuration..."
cp -r /home/fayez/agent2/deepagent_system/web_ui "${BUNDLE_DIR}/web_ui"
cp -r /home/fayez/agent2/deepagent_system/skills "${BUNDLE_DIR}/skills"
cp /home/fayez/agent2/deepagent_system/app/config.py "${BUNDLE_DIR}/config/config.py"

# 4. Generate Offline Installation Script
cat << 'INSTALL_SCRIPT' > "${BUNDLE_DIR}/scripts/offline_install.sh"
#!/usr/bin/env bash
set -euo pipefail

echo "=============================================================================="
echo " 🚀 DEEP AGENT AIR-GAPPED OFFLINE INSTALLATION"
echo "=============================================================================="

# Configure rootless storage
mkdir -p ~/.config/containers
cp config/storage.conf ~/.config/containers/storage.conf

# Load Container Images
echo "📥 Loading offline container images into rootless Podman..."
podman load -i images/deepagent-hitl-db.tar
podman load -i images/deepagent-core.tar
podman load -i images/deepagent-ansible-mcp.tar
podman load -i images/deepagent-sop-mcp.tar
podman load -i images/deepagent-ollama.tar
podman load -i images/deepagent-webui.tar

echo "✓ All container images loaded successfully into local registry."
echo "✓ To start system: podman start deepagent-hitl-db deepagent-ansible-mcp deepagent-sop-mcp deepagent-ollama deepagent-service deepagent-webui"
INSTALL_SCRIPT
chmod +x "${BUNDLE_DIR}/scripts/offline_install.sh"

echo "=============================================================================="
echo " 🎉 AIR-GAPPED RELEASE BUNDLE READY: ${BUNDLE_DIR}"
echo "=============================================================================="
