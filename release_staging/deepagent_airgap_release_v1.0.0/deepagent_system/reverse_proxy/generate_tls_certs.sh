#!/usr/bin/env bash
# ==============================================================================
#  🔐 Self-Signed / Custom TLS 1.3 Certificate Generator for Reverse Proxy
# ==============================================================================
set -euo pipefail

SSL_DIR="/home/fayez/agent2/deepagent_system/reverse_proxy/ssl"
mkdir -p "${SSL_DIR}"

if [ ! -f "${SSL_DIR}/server.crt" ] || [ ! -f "${SSL_DIR}/server.key" ]; then
    echo "  🔑 Generating default TLS certificate and private key ..."
    openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
        -keyout "${SSL_DIR}/server.key" \
        -out "${SSL_DIR}/server.crt" \
        -subj "/C=US/ST=Enterprise/L=Datacenter/O=DeepAgent/OU=SRE/CN=deepagent.local" >/dev/null 2>&1
    chmod 600 "${SSL_DIR}/server.key"
    chmod 644 "${SSL_DIR}/server.crt"
    echo "  ✓ Generated ${SSL_DIR}/server.crt and ${SSL_DIR}/server.key"
else
    echo "  ✓ TLS certificates already present in ${SSL_DIR}"
fi
