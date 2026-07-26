#!/bin/bash
set -e

QUAY_ORG=${1:-"fayez2016"}
TAG=${2:-"staging"}

REGISTRY="quay.io/${QUAY_ORG}"

echo "🏷️ Tagging agent2 containers for Quay.io registry (${REGISTRY})..."

podman tag local-hermes:latest "${REGISTRY}/hermes-agent:${TAG}"
podman tag agent2_ansible-mcp:latest "${REGISTRY}/ansible-mcp:${TAG}"
podman tag agent2_hitl-web:latest "${REGISTRY}/hitl-web:${TAG}"
podman tag agent2_hitl-db:latest "${REGISTRY}/hitl-db:${TAG}"
podman tag agent2_aap-server:latest "${REGISTRY}/aap-server:${TAG}"
podman tag localhost/local-ollama:gemma4-12b "${REGISTRY}/local-ollama:gemma4-12b"

echo "✅ Tagging complete:"
echo "   - ${REGISTRY}/hermes-agent:${TAG}"
echo "   - ${REGISTRY}/ansible-mcp:${TAG}"
echo "   - ${REGISTRY}/hitl-web:${TAG}"
echo "   - ${REGISTRY}/hitl-db:${TAG}"
echo "   - ${REGISTRY}/aap-server:${TAG}"
echo "   - ${REGISTRY}/local-ollama:gemma4-12b"

echo ""
echo "To push to Quay.io, ensure you are logged in ('podman login quay.io') and run:"
echo "  podman push ${REGISTRY}/hermes-agent:${TAG}"
echo "  podman push ${REGISTRY}/ansible-mcp:${TAG}"
echo "  podman push ${REGISTRY}/hitl-web:${TAG}"
echo "  podman push ${REGISTRY}/hitl-db:${TAG}"
echo "  podman push ${REGISTRY}/aap-server:${TAG}"
echo "  podman push ${REGISTRY}/local-ollama:gemma4-12b"
