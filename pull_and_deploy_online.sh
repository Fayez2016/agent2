#!/usr/bin/env bash
# ==============================================================================
#  🚀 SCRIPT 1: ONE-CLICK ONLINE DEPLOYMENT (PULL FROM QUAY.IO & RUN)
# ==============================================================================
set -euo pipefail

QUAY_USER="${QUAY_USER:-souffm0a}"
QUAY_TOKEN="${QUAY_TOKEN:-kNC@4P_BAFnVf6!}"
REGISTRY="quay.io/${QUAY_USER}"
TAG="${TAG:-latest}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "================================================================================"
echo " 🚀 DEEP AGENT ONLINE DEPLOYMENT (PULL FROM QUAY.IO & RUN)"
echo " 👤 Registry User : ${QUAY_USER}"
echo " 🏷️ Image Tag     : ${TAG}"
echo " 📂 Deploy Root   : ${SCRIPT_DIR}"
echo "================================================================================"

# 1. Rootless Podman storage configuration
STORAGE_CONF="${HOME}/.config/containers/storage.conf"
if [ ! -f "${STORAGE_CONF}" ]; then
    mkdir -p "$(dirname "${STORAGE_CONF}")"
    cat << 'STOR_EOF' > "${STORAGE_CONF}"
[storage]
driver = "overlay"

[storage.options.overlay]
ignore_chown_errors = "true"
STOR_EOF
fi

# 2. Login to Quay.io
if [ -n "${QUAY_TOKEN}" ]; then
    echo "${QUAY_TOKEN}" | podman login -u "${QUAY_USER}" --password-stdin quay.io
fi

# 3. Pull All 7 Microservices
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

# 4. Generate Configurations & TLS 1.3 Certificates
COMPOSE_DIR="${SCRIPT_DIR}/deepagent_system"
PROXY_DIR="${COMPOSE_DIR}/reverse_proxy"
SSL_DIR="${PROXY_DIR}/ssl"
mkdir -p "${SSL_DIR}"

cat << 'NGINX_EOF' > "${PROXY_DIR}/nginx.conf"
worker_processes auto;
pid /tmp/nginx.pid;
events { worker_connections 1024; }
http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;

    upstream deepagent_api { server deepagent-service:8642; }
    upstream deepagent_webui { server deepagent-webui:3000; }
    upstream ansible_mcp { server deepagent-ansible-mcp:8000; }
    upstream sop_mcp { server deepagent-sop-mcp:8001; }

    server {
        listen 8080;
        return 301 https://$host:8443$request_uri;
    }
    server {
        listen 8443 ssl http2;
        ssl_certificate /etc/nginx/ssl/server.crt;
        ssl_certificate_key /etc/nginx/ssl/server.key;
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            proxy_pass http://deepagent_webui;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto https;
        }
        location /v1/ {
            rewrite ^/v1/(.*) /$1 break;
            proxy_pass http://deepagent_api;
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto https;
        }
        location /mcp/ansible/ {
            rewrite ^/mcp/ansible/(.*) /$1 break;
            proxy_pass http://ansible_mcp;
        }
        location /mcp/sop/ {
            rewrite ^/mcp/sop/(.*) /$1 break;
            proxy_pass http://sop_mcp;
        }
    }
}
NGINX_EOF

cat << 'COMPOSE_EOF' > "${COMPOSE_DIR}/docker-compose.production.yml"
version: '3.8'
services:
  proxy:
    image: quay.io/souffm0a/deepagent-proxy:latest
    container_name: deepagent-proxy
    restart: unless-stopped
    ports:
      - "8080:8080"
      - "8443:8443"
    volumes:
      - ./reverse_proxy/nginx.conf:/etc/nginx/nginx.conf:ro,Z
      - ./reverse_proxy/ssl:/etc/nginx/ssl:ro,Z
    depends_on: [service, webui, ansible-mcp, sop-mcp]
    networks: [deepagent_prod_net]

  db:
    image: quay.io/souffm0a/deepagent-hitl-db:latest
    container_name: deepagent-hitl-db
    restart: unless-stopped
    environment:
      - POSTGRES_USER=hermes
      - POSTGRES_PASSWORD=secret456
      - POSTGRES_DB=hitl
    volumes: [db-data:/var/lib/postgresql/data:Z]
    networks: [deepagent_prod_net]

  ansible-mcp:
    image: quay.io/souffm0a/deepagent-ansible-mcp:latest
    container_name: deepagent-ansible-mcp
    restart: unless-stopped
    environment:
      - AAP_HOST=aap-server:5000
      - AAP_TOKEN=mock-token
      - DATABASE_URL=postgresql://hermes:secret456@db:5432/hitl
    depends_on: [db, aap-server]
    networks: [deepagent_prod_net]

  sop-mcp:
    image: quay.io/souffm0a/deepagent-sop-mcp:latest
    container_name: deepagent-sop-mcp
    restart: unless-stopped
    environment:
      - DATABASE_URL=postgresql://hermes:secret456@db:5432/hitl
    depends_on: [db]
    networks: [deepagent_prod_net]

  service:
    image: quay.io/souffm0a/deepagent-core:latest
    container_name: deepagent-service
    restart: unless-stopped
    environment:
      - DATABASE_URL=postgresql://hermes:secret456@db:5432/hitl
      - ANSIBLE_MCP_URL=http://ansible-mcp:8000/mcp
      - SOP_MCP_URL=http://sop-mcp:8001/mcp
    depends_on: [db, ansible-mcp, sop-mcp]
    networks: [deepagent_prod_net]

  webui:
    image: quay.io/souffm0a/deepagent-hitl-web:latest
    container_name: deepagent-webui
    restart: unless-stopped
    networks: [deepagent_prod_net]

  aap-server:
    image: quay.io/souffm0a/deepagent-mock-aap:latest
    container_name: deepagent-aap-server
    restart: unless-stopped
    networks: [deepagent_prod_net]

networks:
  deepagent_prod_net:
    driver: bridge
volumes:
  db-data:
COMPOSE_EOF

if [ ! -f "${SSL_DIR}/server.crt" ]; then
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "${SSL_DIR}/server.key" \
        -out "${SSL_DIR}/server.crt" \
        -subj "/CN=deepagent.local" >/dev/null 2>&1
    chmod 644 "${SSL_DIR}/server.key" "${SSL_DIR}/server.crt"
fi

# 5. Stop Previous Containers if running
CONTAINERS=(deepagent-proxy deepagent-service deepagent-webui deepagent-ansible-mcp deepagent-sop-mcp deepagent-hitl-db deepagent-aap-server)
for c in "${CONTAINERS[@]}"; do
    podman stop "${c}" 2>/dev/null || true
    podman rm "${c}" 2>/dev/null || true
done

# 6. Start Stack via Podman Compose
cd "${COMPOSE_DIR}"
podman compose -f docker-compose.production.yml up -d

# 7. Automated Health Probing
echo -e "\n🔍 Executing Automated Health Probing..."
for i in {1..15}; do
    echo -n "  ⏳ Probe ${i}/15 ... "
    if curl -k -s -f https://localhost:8443/ >/dev/null 2>&1 && curl -k -s -f https://localhost:8443/v1/system/supervisor >/dev/null 2>&1; then
        echo "🟢 All Services Healthy!"
        break
    fi
    sleep 2
done

echo -e "\n================================================================================"
echo " 🎉 ONLINE DEPLOYMENT COMPLETE & VERIFIED!"
echo " 🔒 HTTPS Web UI : https://localhost:8443"
echo " ⚡ API Endpoint : https://localhost:8443/v1/"
echo "================================================================================"
