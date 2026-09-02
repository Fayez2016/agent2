#!/usr/bin/env bash
set -euo pipefail

echo "🔨 Building all local microservices..."
podman build -t "localhost/deepagent-hitl-web:latest" -f /home/fayez/agent2/deepagent_system/web_ui.Dockerfile /home/fayez/agent2/deepagent_system/
podman build -t "localhost/deepagent-core:latest" -f /home/fayez/agent2/deepagent_system/deepagent.Dockerfile /home/fayez/agent2/deepagent_system/
podman build -t "localhost/deepagent-proxy:latest" /home/fayez/agent2/deepagent_system/reverse_proxy/
podman build -t "localhost/agent2_hitl-db:latest" /home/fayez/agent2/db/

echo "🚀 Pushing microservices and carrier container to Quay.io..."
/home/fayez/agent2/build_and_push_quay_dual.sh
echo "✅ All components built and synchronized."
