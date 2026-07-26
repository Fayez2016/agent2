#!/bin/bash
set -e

OUTPUT_DIR="./staging/bundle"
BUNDLE_FILE="${OUTPUT_DIR}/agent2_airgap_bundle.tar"

mkdir -p "${OUTPUT_DIR}"

echo "📦 Exporting all 6 service container images to offline tar archive..."
echo "📄 Destination: ${BUNDLE_FILE}"

podman save -o "${BUNDLE_FILE}" \
  local-hermes:latest \
  agent2_ansible-mcp:latest \
  agent2_hitl-web:latest \
  agent2_hitl-db:latest \
  agent2_aap-server:latest \
  localhost/local-ollama:gemma4-12b

echo "✅ Image bundle successfully exported!"
echo "Size: $(du -h "${BUNDLE_FILE}" | cut -f1)"
echo "You can transfer this tarball via physical media/USB and import it on the target airgapped machine using:"
echo "  podman load -i ${BUNDLE_FILE}"
