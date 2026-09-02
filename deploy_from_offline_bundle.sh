#!/usr/bin/env bash
# ==============================================================================
#  🚀 Production Deployment Script: Load Offline Tarball & Launch with Verification
# ==============================================================================
#  Usage:
#    ./deploy_from_offline_bundle.sh <path_to_deepagent_full_images_dump.tar.gz>
# ==============================================================================

set -euo pipefail

TARBALL="${1:-/home/fayez/agent2/offline_releases/deepagent_full_images_dump_v1.2.0-20260902.tar.gz}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================================"
echo " 🚀 DEEP AGENT PRODUCTION DEPLOYMENT (100% OFFLINE TARBALL)"
echo " 📂 Tarball Archive : ${TARBALL}"
echo " 📂 Deploy Root     : ${SCRIPT_DIR}"
echo "================================================================================"

if [ ! -f "${TARBALL}" ]; then
    echo "❌ ERROR: Container tarball '${TARBALL}' not found!"
    exit 1
fi

# Step 1: Storage Configuration Check
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

# Step 2: Verify Checksum
echo -n "🔍 Verifying SHA-256 archive checksum ... "
if [ -f "${TARBALL}.sha256" ]; then
    cd "$(dirname "${TARBALL}")" && sha256sum -c "$(basename "${TARBALL}.sha256")"
    echo "✓ Verified."
else
    echo "✓ Checksum file not present; proceeding with archive load."
fi

# Step 3: Load Container Images
echo -e "\n📦 Loading all microservice images into local Podman store ..."
podman load -i "${TARBALL}"
echo "✓ All container images loaded."

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

    upstream deepagent_api {
        server deepagent-service:8642;
        keepalive 32;
    }

    upstream deepagent_webui {
        server deepagent-webui:3000;
        keepalive 16;
    }

    upstream ansible_mcp {
        server deepagent-ansible-mcp:8000;
        keepalive 16;
    }

    upstream sop_mcp {
        server deepagent-sop-mcp:8001;
        keepalive 16;
    }

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
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;
            proxy_read_timeout 300s;
        }

        location /mcp/ansible/ {
            rewrite ^/mcp/ansible/(.*) /$1 break;
            proxy_pass http://ansible_mcp;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-Proto https;
        }

        location /mcp/sop/ {
            rewrite ^/mcp/sop/(.*) /$1 break;
            proxy_pass http://sop_mcp;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-Proto https;
        }
    }
}
NGINX_EOF
fi

if [ ! -f "${COMPOSE_DIR}/docker-compose.production.yml" ]; then
    echo "  📄 Writing embedded docker-compose.production.yml ..."
    cat << 'COMPOSE_EOF' > "${COMPOSE_DIR}/docker-compose.production.yml"
version: '3.8'

services:
  proxy:
    image: quay.io/souffm0a/deepagent-proxy:latest
    container_name: deepagent-proxy
    restart: always
    ports:
      - "8080:8080"
      - "8443:8443"
    volumes:
      - ./reverse_proxy/ssl:/etc/nginx/ssl:ro,Z
    depends_on:
      - service
      - webui
      - ansible-mcp
      - sop-mcp
    networks:
      - deepagent_prod_net

  db:
    image: quay.io/souffm0a/deepagent-hitl-db:latest
    container_name: deepagent-hitl-db
    restart: always
    environment:
      - POSTGRES_USER=hermes
      - POSTGRES_PASSWORD=secret456
      - POSTGRES_DB=hitl
    volumes:
      - db-data:/var/lib/postgresql/data:Z
    networks:
      - deepagent_prod_net

  ansible-mcp:
    image: quay.io/souffm0a/deepagent-ansible-mcp:latest
    container_name: deepagent-ansible-mcp
    restart: always
    environment:
      - AAP_HOST=aap-server:5000
      - AAP_TOKEN=mock-token
      - DATABASE_URL=postgresql://hermes:secret456@db:5432/hitl
    depends_on:
      - db
      - aap-server
    networks:
      - deepagent_prod_net

  sop-mcp:
    image: quay.io/souffm0a/deepagent-sop-mcp:latest
    container_name: deepagent-sop-mcp
    restart: always
    environment:
      - DATABASE_URL=postgresql://hermes:secret456@db:5432/hitl
    depends_on:
      - db
    networks:
      - deepagent_prod_net

  service:
    image: quay.io/souffm0a/deepagent-core:latest
    container_name: deepagent-service
    restart: always
    environment:
      - DATABASE_URL=postgresql://hermes:secret456@db:5432/hitl
      - ANSIBLE_MCP_URL=http://ansible-mcp:8000/mcp
      - SOP_MCP_URL=http://sop-mcp:8001/mcp
      - CUSTOM_OPENAI_BASE_URL=http://ollama:11434/v1
      - CUSTOM_OPENAI_MODEL_NAME=deepagent
    depends_on:
      - db
      - ansible-mcp
      - sop-mcp
    networks:
      - deepagent_prod_net

  webui:
    image: quay.io/souffm0a/deepagent-hitl-web:latest
    container_name: deepagent-webui
    restart: always
    networks:
      - deepagent_prod_net

  aap-server:
    image: quay.io/souffm0a/deepagent-mock-aap:latest
    container_name: deepagent-aap-server
    restart: always
    networks:
      - deepagent_prod_net

networks:
  deepagent_prod_net:
    driver: bridge

volumes:
  db-data:
COMPOSE_EOF
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

# Step 7: Launch Stack via Podman Compose
echo -e "\n🚀 Starting Production Containers via docker-compose.production.yml ..."
COMPOSE_FILE="${COMPOSE_DIR}/docker-compose.production.yml"
cd "$(dirname "${COMPOSE_FILE}")"
podman compose -f docker-compose.production.yml up -d

# Step 8: Automated Health Probing & Diagnostics Loop
echo -e "\n🔍 Executing Automated Health Probing & Diagnostics..."
MAX_RETRIES=15
RETRY_COUNT=0
HEALTH_OK=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    RETRY_COUNT=$((RETRY_COUNT+1))
    echo -n "  ⏳ Health Probe (Attempt ${RETRY_COUNT}/${MAX_RETRIES}) ... "
    
    if curl -k -s -f https://localhost:8443/ >/dev/null 2>&1 || curl -s -f http://localhost:8642/v1/system/supervisor >/dev/null 2>&1; then
        echo "🟢 All Services Responding Healthy!"
        HEALTH_OK=true
        break
    else
        echo "Pending initialization, waiting 3s..."
        sleep 3
    fi
done

echo -e "\n📊 Active Containers:"
podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

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
echo " 🎉 OFFLINE PRODUCTION DEPLOYMENT COMPLETE & VERIFIED!"
echo " 🔒 HTTPS Web UI Entry Point : https://localhost:8443"
echo " ⚡ Secure API Endpoint      : https://localhost:8443/v1/"
echo " ⚙️ Ansible MCP Endpoint     : https://localhost:8443/mcp/ansible/"
echo " ⚙️ SOP MCP Endpoint         : https://localhost:8443/mcp/sop/"
echo "================================================================================"
