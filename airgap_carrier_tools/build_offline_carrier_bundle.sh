#!/usr/bin/env bash
# ==============================================================================
#  📦 Enterprise Airgap Offline Carrier Packager (Phase 2)
# ==============================================================================
#  Packages all 7 verified production microservices, storage configuration,
#  volume-mounted SOPs, Nginx TLS proxy assets, and offline installer into a
#  single self-contained tarball bundle.
# ==============================================================================

set -euo pipefail

RELEASE_TAG="${TAG:-latest}"
REGISTRY="${REGISTRY:-quay.io/souffm0a}"
BUNDLE_NAME="deepagent-offline-carrier-bundle-$(date +%Y%m%d)"
OUTPUT_DIR="$(pwd)/${BUNDLE_NAME}"
TARBALL_FILE="$(pwd)/${BUNDLE_NAME}.tar.gz"

echo "================================================================================"
echo " 📦 BUILDING DEEP AGENT ENTERPRISE OFFLINE CARRIER BUNDLE"
echo " 🏷️ Release Tag     : ${RELEASE_TAG}"
echo " 📂 Target Dir      : ${OUTPUT_DIR}"
echo " 📦 Final Archive   : ${TARBALL_FILE}"
echo "================================================================================"

rm -rf "${OUTPUT_DIR}" "${TARBALL_FILE}"
mkdir -p "${OUTPUT_DIR}/images" "${OUTPUT_DIR}/config" "${OUTPUT_DIR}/sops" "${OUTPUT_DIR}/scripts"

# 1. Storage Configuration
echo "⚙️  1/6 Packaging rootless Podman storage configuration..."
cat << 'STOR_EOF' > "${OUTPUT_DIR}/config/storage.conf"
[storage]
driver = "overlay"

[storage.options.overlay]
ignore_chown_errors = "true"
STOR_EOF

# 2. Production Environment Template (.env.production)
echo "📄 2/6 Creating .env.production template..."
cat << 'ENV_EOF' > "${OUTPUT_DIR}/.env.production.template"
# ==============================================================================
#  DEEP AGENT 10% SITE-SPECIFIC PRODUCTION CONFIGURATION
# ==============================================================================

# 1. Ansible Automation Platform (AAP)
AAP_HOST=127.0.0.1:5000
AAP_TOKEN=mock-token

# 2. Enterprise OpenAI-Compliant Model Gateway
# (Compatible with vLLM, TGI, OpenShift AI, LiteLLM, or Azure OpenAI)
OPENROUTER_API_KEY=your-openrouter-or-openai-api-key
OPENAI_API_KEY=your-openrouter-or-openai-api-key

# 3. Security & Governance Mode
HITL_MODE=autonomous
NOTIFICATION_EMAIL=sre-team@example.com
ENV_EOF

# 3. Volume-Mounted SOPs & Skills
echo "📂 3/6 Packaging editable SOP workflows and skills..."
if [ -d "deepagent_system/sops" ]; then
    cp -r deepagent_system/sops/* "${OUTPUT_DIR}/sops/"
fi
if [ -d "deepagent_system/skills" ]; then
    cp -r deepagent_system/skills "${OUTPUT_DIR}/skills"
fi

# 4. Reverse Proxy TLS Configurations
echo "🔒 4/6 Packaging Nginx Reverse Proxy templates..."
mkdir -p "${OUTPUT_DIR}/config/nginx"
cat << 'NGINX_EOF' > "${OUTPUT_DIR}/config/nginx/nginx.conf"
worker_processes auto;
pid /tmp/nginx.pid;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;
    client_max_body_size 50M;

    upstream deepagent_api { server 127.0.0.1:8642; }
    upstream deepagent_webui { server 127.0.0.1:3000; }
    upstream ansible_mcp { server 127.0.0.1:8000; }
    upstream sop_mcp { server 127.0.0.1:8001; }

    server {
        listen 8080;
        server_name _;
        return 301 https://$host:8443$request_uri;
    }

    server {
        listen 8443 ssl http2;
        server_name _;
        ssl_certificate /etc/nginx/ssl/server.crt;
        ssl_certificate_key /etc/nginx/ssl/server.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_prefer_server_ciphers on;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;

        location / {
            proxy_pass http://deepagent_webui;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }

        location /v1/ {
            proxy_pass http://deepagent_api;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
        }

        location /mcp/ansible/ {
            proxy_pass http://ansible_mcp/mcp;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
        }

        location /mcp/sop/ {
            proxy_pass http://sop_mcp/mcp;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 3600s;
        }
    }
}
NGINX_EOF

# 5. Offline Installer & Health Prober Scripts
echo "🚀 5/6 Generating offline installer script..."
cat << 'INSTALL_EOF' > "${OUTPUT_DIR}/offline_install.sh"
#!/usr/bin/env bash
# ==============================================================================
#  🚀 Offline Deployment Runner: 100% Airgap Execution
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

echo "================================================================================"
echo " 🚀 DEEP AGENT AIR-GAPPED OFFLINE INSTALLATION"
echo " 📂 Target Root: ${SCRIPT_DIR}"
echo "================================================================================"

# Step 1: Storage Configuration
echo -n "⚙️ 1/5 Configuring rootless Podman storage ... "
STORAGE_CONF="${HOME}/.config/containers/storage.conf"
if [ ! -f "${STORAGE_CONF}" ]; then
    mkdir -p "$(dirname "${STORAGE_CONF}")"
    cp config/storage.conf "${STORAGE_CONF}"
    echo "✓ Installed ignore_chown_errors."
else
    echo "✓ Already configured."
fi

# Step 2: Load Offline Container Images
echo -e "\n📥 2/5 Loading Container Images from Offline Bundle ..."
for img_tar in images/*.tar; do
    if [ -f "${img_tar}" ]; then
        echo "  ⚡ Loading $(basename "${img_tar}") ..."
        podman load -i "${img_tar}"
    fi
done
echo "✓ All container images loaded into local store."

# Step 3: Ensure Production Environment Configuration Exists
echo -e "\n📄 3/5 Checking environment configuration ..."
if [ ! -f .env.production ]; then
    echo "  Creating .env.production from template..."
    cp .env.production.template .env.production
    echo "✓ Created .env.production. Please update with production AAP and LLM credentials if needed."
else
    echo "✓ Existing .env.production found."
fi
source .env.production

# Step 4: Ensure SSL Certificates Exist
echo -e "\n🔐 4/5 Generating TLS 1.3 Certificates for Reverse Proxy ..."
SSL_DIR="${SCRIPT_DIR}/config/nginx/ssl"
mkdir -p "${SSL_DIR}"
if [ ! -f "${SSL_DIR}/server.crt" ]; then
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "${SSL_DIR}/server.key" \
        -out "${SSL_DIR}/server.crt" \
        -subj "/C=US/ST=Enterprise/L=Datacenter/O=DeepAgent/OU=SRE/CN=deepagent.local" >/dev/null 2>&1
    chmod 644 "${SSL_DIR}/server.key"
    chmod 644 "${SSL_DIR}/server.crt"
    echo "✓ Created TLS certificates."
else
    echo "✓ TLS certificates present."
fi

# Step 5: Clean Up and Launch Unified Pod
echo -e "\n🚀 5/5 Launching Production Containers in Pod 'deepagent-prod-pod' ..."
POD_NAME="deepagent-prod-pod"
podman pod rm -f "${POD_NAME}" 2>/dev/null || true

podman pod create \
    --name "${POD_NAME}" \
    -p 8080:8080 \
    -p 8443:8443 \
    -p 8642:8642

REGISTRY="quay.io/souffm0a"
TAG="latest"

podman run -d --name deepagent-hitl-db --pod "${POD_NAME}" \
    -e POSTGRES_USER=hermes \
    -e POSTGRES_PASSWORD=secret456 \
    -e POSTGRES_DB=hitl \
    -v db-data:/var/lib/postgresql/data:Z \
    ${REGISTRY}/deepagent-hitl-db:${TAG}

podman run -d --name deepagent-aap-server --pod "${POD_NAME}" \
    ${REGISTRY}/deepagent-mock-aap:${TAG}

podman run -d --name deepagent-ansible-mcp --pod "${POD_NAME}" \
    -e AAP_HOST="${AAP_HOST:-127.0.0.1:5000}" \
    -e AAP_TOKEN="${AAP_TOKEN:-mock-token}" \
    -e DATABASE_URL=postgresql://hermes:secret456@127.0.0.1:5432/hitl \
    ${REGISTRY}/deepagent-ansible-mcp:${TAG}

podman run -d --name deepagent-sop-mcp --pod "${POD_NAME}" \
    -e DATABASE_URL=postgresql://hermes:secret456@127.0.0.1:5432/hitl \
    -v "${SCRIPT_DIR}/sops:/app/sops:ro,Z" \
    ${REGISTRY}/deepagent-sop-mcp:${TAG}

OPENROUTER_KEY="${OPENROUTER_API_KEY:-${OPENAI_API_KEY:-}}"
if [ -z "${OPENROUTER_KEY}" ]; then
    echo "⚠️ Warning: Neither OPENROUTER_API_KEY nor OPENAI_API_KEY is set in .env.production."
fi

podman run -d --name deepagent-service --pod "${POD_NAME}" \
    -e DATABASE_URL=postgresql://hermes:secret456@127.0.0.1:5432/hitl \
    -e ANSIBLE_MCP_URL=http://127.0.0.1:8000/mcp \
    -e SOP_MCP_URL=http://127.0.0.1:8001/mcp \
    -e OPENROUTER_API_KEY="${OPENROUTER_KEY}" \
    -e OPENAI_API_KEY="${OPENROUTER_KEY}" \
    ${REGISTRY}/deepagent-core:${TAG}

podman run -d --name deepagent-webui --pod "${POD_NAME}" \
    ${REGISTRY}/deepagent-hitl-web:${TAG}

podman run -d --name deepagent-proxy --pod "${POD_NAME}" \
    -v "${SCRIPT_DIR}/config/nginx/nginx.conf:/etc/nginx/nginx.conf:ro,Z" \
    -v "${SSL_DIR}:/etc/nginx/ssl:ro,Z" \
    ${REGISTRY}/deepagent-proxy:${TAG}

# Diagnostic verification probe
echo -e "\n🔍 Running automated verification probe..."
RETRY=0
while [ $RETRY -lt 20 ]; do
    RETRY=$((RETRY+1))
    echo -n "  ⏳ Health Probe (Attempt ${RETRY}/20) ... "
    if curl -k -s -f https://localhost:8443/ >/dev/null 2>&1 && curl -s -f http://localhost:8642/v1/system/supervisor >/dev/null 2>&1; then
        echo "🟢 All Services Responding Healthy!"
        break
    fi
    sleep 3
done

echo -e "\n================================================================================"
echo " 🎉 AIR-GAPPED DEPLOYMENT COMPLETE!"
echo " 🔒 Web UI (HTTPS)      : https://localhost:8443"
echo " ⚡ API Endpoint        : https://localhost:8443/v1/"
echo " ⚙️ Ansible MCP Engine  : https://localhost:8443/mcp/ansible/"
echo " ⚙️ SOP MCP Engine      : https://localhost:8443/mcp/sop/"
echo "================================================================================"
INSTALL_EOF
chmod +x "${OUTPUT_DIR}/offline_install.sh"

# 6. Export Verified Production Container Images
echo "🐳 6/6 Saving verified production container images..."
IMAGES=(
    "deepagent-core"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
    "deepagent-hitl-db"
    "deepagent-mock-aap"
    "deepagent-hitl-web"
    "deepagent-proxy"
)

for img in "${IMAGES[@]}"; do
    echo "  ⚡ Exporting: ${REGISTRY}/${img}:${RELEASE_TAG} -> images/${img}.tar ..."
    podman save -o "${OUTPUT_DIR}/images/${img}.tar" "${REGISTRY}/${img}:${RELEASE_TAG}"
done

# Create SHA256 Checksums
echo "🔏 Generating SHA256 checksums..."
(cd "${OUTPUT_DIR}" && find images/ -type f -exec sha256sum {} + > SHA256SUMS)

# Compress final tarball
echo "📦 Compressing carrier bundle into ${TARBALL_FILE} ..."
tar -czf "${TARBALL_FILE}" -C "$(dirname "${OUTPUT_DIR}")" "$(basename "${OUTPUT_DIR}")"

echo "================================================================================"
echo " ✅ AIR-GAPPED CARRIER BUNDLE SUCCESSFULLY GENERATED!"
echo " 📂 Extracted Dir : ${OUTPUT_DIR}"
echo " 📦 Tarball Bundle: ${TARBALL_FILE} ($(du -h "${TARBALL_FILE}" | cut -f1))"
echo "================================================================================"
