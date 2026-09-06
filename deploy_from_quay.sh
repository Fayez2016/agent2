#!/usr/bin/env bash
# ==============================================================================
#  🚀 Production Deployment Script: Pull from Quay.io & Launch with Verification
# ==============================================================================
#  Usage:
#    ./deploy_from_quay.sh [--quay-user souffm0a] [--quay-token <token>]
# ==============================================================================

set -euo pipefail

QUAY_USER="${QUAY_USER:-souffm0a}"
QUAY_TOKEN="${QUAY_TOKEN:-kNC@4P_BAFnVf6!}"
REGISTRY="quay.io/${QUAY_USER}"
TAG="${TAG:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================================"
echo " 🚀 DEEP AGENT PRODUCTION DEPLOYMENT (PULL FROM QUAY.IO)"
echo " 👤 Registry User : ${QUAY_USER}"
echo " 🏷️ Image Tag     : ${TAG}"
echo " 📂 Deploy Root   : ${SCRIPT_DIR}"
echo "================================================================================"

# Step 1: Storage Configuration Check for Rootless Podman
echo -n "⚙️ Checking rootless Podman storage configuration ... "
STORAGE_CONF="${HOME}/.config/containers/storage.conf"
if [ ! -f "${STORAGE_CONF}" ]; then
    mkdir -p "$(dirname "${STORAGE_CONF}")"
    cat << 'STOR_EOF' > "${STORAGE_CONF}"
[storage]
driver = "overlay"

[storage.options.overlay]
ignore_chown_errors = "true"
STOR_EOF
    echo "✓ Created ~/.config/containers/storage.conf with ignore_chown_errors=true."
else
    echo "✓ Present."
fi

# Step 2: Authenticate with Quay.io
echo -n "🔑 Authenticating with quay.io ... "
if [ -n "${QUAY_TOKEN}" ]; then
    echo "${QUAY_TOKEN}" | podman login -u "${QUAY_USER}" --password-stdin quay.io
    echo "✓ Success."
else
    echo "ℹ️ No token provided; attempting public image pull."
fi

# Step 3: Pull All Production Microservices
IMAGES=(
    "deepagent-core"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
    "deepagent-hitl-db"
    "deepagent-mock-aap"
    "deepagent-hitl-web"
    "deepagent-proxy"
)

echo -e "\n⬇️ Pulling Microservice Images from Quay.io ..."
for img in "${IMAGES[@]}"; do
    echo "  ⚡ Pulling: ${REGISTRY}/${img}:${TAG} ..."
    podman pull "${REGISTRY}/${img}:${TAG}"
done
echo "✓ All container images pulled successfully."

# Step 4: Ensure Production Compose and Nginx Configurations Exist
COMPOSE_DIR="${SCRIPT_DIR}/deepagent_system"
PROXY_DIR="${COMPOSE_DIR}/reverse_proxy"
SSL_DIR="${PROXY_DIR}/ssl"
mkdir -p "${SSL_DIR}"

if [ ! -f "${PROXY_DIR}/nginx.conf" ]; then
    echo "  📄 Writing embedded Nginx TLS 1.3 configuration ..."
    cat << 'NGINX_EOF' > "${PROXY_DIR}/nginx.conf"
worker_processes auto;
pid /tmp/nginx.pid;
error_log /var/log/nginx/error.log warn;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    keepalive_timeout 65;
    client_max_body_size 50M;

    upstream deepagent_api { server 127.0.0.1:8642; }
    upstream deepagent_webui { server 127.0.0.1:3000; }
    upstream ansible_mcp { server 127.0.0.1:8000; }
    upstream sop_mcp { server 127.0.0.1:8001; }

    server {
        listen 8080;
        listen [::]:8080;
        server_name _;
        return 301 https://$host:8443$request_uri;
    }

    server {
        listen 8443 ssl http2;
        listen [::]:8443 ssl http2;
        server_name _;

        ssl_certificate /etc/nginx/ssl/server.crt;
        ssl_certificate_key /etc/nginx/ssl/server.key;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_prefer_server_ciphers on;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;

        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

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
            rewrite ^/mcp/ansible/(.*) /$1 break;
            proxy_pass http://ansible_mcp;
            proxy_http_version 1.1;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-Proto https;
        }

        location /mcp/sop/ {
            rewrite ^/mcp/sop/(.*) /$1 break;
            proxy_pass http://sop_mcp;
            proxy_http_version 1.1;
            proxy_read_timeout 3600s;
            proxy_send_timeout 3600s;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-Proto https;
        }
    }
}
NGINX_EOF
fi


# Step 5: Generate TLS Certificates for Reverse Proxy
echo -e "\n🔐 Generating TLS Certificates for Reverse Proxy ..."
if [ ! -f "${SSL_DIR}/server.crt" ]; then
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "${SSL_DIR}/server.key" \
        -out "${SSL_DIR}/server.crt" \
        -subj "/C=US/ST=Enterprise/L=Datacenter/O=DeepAgent/OU=SRE/CN=deepagent.local" >/dev/null 2>&1
    chmod 600 "${SSL_DIR}/server.key"
    echo "✓ Created SSL certificate and key in ${SSL_DIR}."
else
    echo "✓ SSL certificate already exists."
fi

# Step 6: Clean up any old containers before start
echo -e "\n🧹 Ensuring clean container state ..."
CONTAINERS=(
    "deepagent-proxy"
    "deepagent-service"
    "deepagent-webui"
    "deepagent-ansible-mcp"
    "deepagent-sop-mcp"
    "deepagent-hitl-db"
    "deepagent-aap-server"
)
for c in "${CONTAINERS[@]}"; do
    podman stop "${c}" 2>/dev/null || true
    podman rm -f "${c}" 2>/dev/null || true
done

# Step 7: Launch Stack via Podman Pod (Eliminating rootless bridge DNS failure modes)
POD_NAME="deepagent-prod-pod"
echo -e "\n🚀 Starting Production Containers in Pod '${POD_NAME}' ..."

podman pod rm -f "${POD_NAME}" 2>/dev/null || true

podman pod create \
    --name "${POD_NAME}" \
    -p 8080:8080 \
    -p 8443:8443 \
    -p 8642:8642

podman run -d --name deepagent-hitl-db --pod "${POD_NAME}" \
    -e POSTGRES_USER=hermes \
    -e POSTGRES_PASSWORD=secret456 \
    -e POSTGRES_DB=hitl \
    -v db-data:/var/lib/postgresql/data:Z \
    ${REGISTRY}/deepagent-hitl-db:${TAG}

podman run -d --name deepagent-aap-server --pod "${POD_NAME}" \
    ${REGISTRY}/deepagent-mock-aap:${TAG}

podman run -d --name deepagent-ansible-mcp --pod "${POD_NAME}" \
    -e AAP_HOST=127.0.0.1:5000 \
    -e AAP_TOKEN=mock-token \
    -e DATABASE_URL=postgresql://hermes:secret456@127.0.0.1:5432/hitl \
    ${REGISTRY}/deepagent-ansible-mcp:${TAG}

podman run -d --name deepagent-sop-mcp --pod "${POD_NAME}" \
    -e DATABASE_URL=postgresql://hermes:secret456@127.0.0.1:5432/hitl \
    ${REGISTRY}/deepagent-sop-mcp:${TAG}

OPENROUTER_KEY="${OPENROUTER_API_KEY:-${OPENAI_API_KEY:-}}"
if [ -z "${OPENROUTER_KEY}" ]; then
    echo "⚠️ Warning: Neither OPENROUTER_API_KEY nor OPENAI_API_KEY is set. Set in environment or .env."
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
    -v "${PROXY_DIR}/nginx.conf:/etc/nginx/nginx.conf:ro,Z" \
    -v "${SSL_DIR}:/etc/nginx/ssl:ro,Z" \
    ${REGISTRY}/deepagent-proxy:${TAG}

# Step 8: Automated Health Probing & Problem Detection Loop
echo -e "\n🔍 Executing Automated Health Probing & Diagnostics..."
MAX_RETRIES=20
RETRY_COUNT=0
HEALTH_OK=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    RETRY_COUNT=$((RETRY_COUNT+1))
    echo -n "  ⏳ Health Probe (Attempt ${RETRY_COUNT}/${MAX_RETRIES}) ... "
    
    # Check if proxy responds
    if curl -k -s -f https://localhost:8443/ >/dev/null 2>&1 && curl -s -f http://localhost:8642/v1/system/supervisor >/dev/null 2>&1; then
        echo "🟢 All Services Responding Healthy!"
        HEALTH_OK=true
        break
    else
        echo "Pending initialization, waiting 3s..."
        sleep 3
    fi
done

echo -e "\n📊 Active Containers:"
podman ps --pod --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.PodName}}"

if [ "${HEALTH_OK}" = false ]; then
    echo -e "\n⚠️ WARNING: Automated health probe timed out. Running diagnostic inspection:"
    for c in "${CONTAINERS[@]}"; do
        echo "--- Logs for ${c} ---"
        podman logs --tail 10 "${c}" 2>&1 || true
    done
    echo "❌ Deployment completed with warnings."
    exit 1
fi

echo -e "\n================================================================================"
echo " 🎉 DEEP AGENT PRODUCTION DEPLOYMENT COMPLETE & VERIFIED!"
echo " 🔒 HTTPS Web UI Entry Point : https://localhost:8443"
echo " ⚡ Secure API Endpoint      : https://localhost:8443/v1/"
echo " ⚙️ Ansible MCP Endpoint     : https://localhost:8443/mcp/ansible/"
echo " ⚙️ SOP MCP Endpoint         : https://localhost:8443/mcp/sop/"
echo "================================================================================"
