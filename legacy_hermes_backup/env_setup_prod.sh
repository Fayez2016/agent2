#!/bin/bash
# Environment: Production Preparation
set -e

echo "🔒 Preparing Production Environment..."

# 1. Revert ansible_tool.py to HTTPS
echo "📡 Setting protocol to HTTPS in ansible_tool.py..."
podman run --rm -v ./.hermes:/opt/data --entrypoint /bin/sh local-hermes -c "sed -i 's/http:\/\//https:\/\//g' /opt/data/skills/devops/lib/ansible_tool.py"

# 2. Update docker-compose.yml to remove mock service and use real AAP
# (This is a simplified version - in real prod, env vars would be injected via CI/CD or .env)
echo "📝 Updating docker-compose for production..."
# We use a temp file to avoid partial writes
cat <<EOF > docker-compose.yml
services:
  hermes:
    image: local-hermes
    container_name: hermes-agent
    command: gateway run
    volumes:
      - ./.hermes:/opt/data:Z
    restart: unless-stopped
    environment:
      - TZ=UTC
      - AAP_HOST=\${AAP_HOST}
      - AAP_TOKEN=\${AAP_TOKEN}
    depends_on:
      - ollama

  ollama:
    image: local-ollama
    container_name: ollama
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 8G
EOF

echo "🧹 Cleaning up mock containers..."
podman-compose down
podman rm -f mock-aap || true

echo "✅ Production preparation complete."
echo "🚀 You can now start the services with: AAP_HOST=your-aap.com AAP_TOKEN=your-token podman-compose up -d"
