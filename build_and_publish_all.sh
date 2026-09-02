#!/usr/bin/env bash
set -euo pipefail

echo "🧹 Preparing clean initial SQL for PostgreSQL container..."
grep -v '^\\' /home/fayez/agent2/backups/20260901_085231/hitl_db_backup.sql \
  | grep -v 'transaction_timeout' \
  > /home/fayez/agent2/db/init.sql

cat << 'DOCKER_EOF' > /home/fayez/agent2/db/Dockerfile
FROM docker.io/library/postgres:16-alpine

ENV POSTGRES_USER=hermes \
    POSTGRES_PASSWORD=secret456 \
    POSTGRES_DB=hitl

COPY init.sql /docker-entrypoint-initdb.d/init.sql

EXPOSE 5432
DOCKER_EOF

echo "🔨 Building all local microservices..."
podman build -t "localhost/deepagent-hitl-web:latest" -f /home/fayez/agent2/deepagent_system/web_ui.Dockerfile /home/fayez/agent2/deepagent_system/
podman build -t "localhost/deepagent-core:latest" -f /home/fayez/agent2/deepagent_system/deepagent.Dockerfile /home/fayez/agent2/deepagent_system/
podman build -t "localhost/deepagent-proxy:latest" /home/fayez/agent2/deepagent_system/reverse_proxy/
podman build --no-cache -t "localhost/agent2_hitl-db:latest" /home/fayez/agent2/db/

echo "🚀 Pushing microservices and carrier container to Quay.io..."
/home/fayez/agent2/build_and_push_quay_dual.sh
echo "✅ All components built and synchronized."
