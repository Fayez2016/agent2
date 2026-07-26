#!/bin/bash
set -e

MODEL_NAME=${1:-"gemma4:12b"}
TARGET_IMAGE="localhost/local-ollama:gemma4-12b"

echo "🚀 Starting Ollama prep container to build offline image with model: ${MODEL_NAME}..."

# Remove previous prep container if exists
podman rm -f ollama-prep 2>/dev/null || true

# Run Ollama prep container
podman run -d --name ollama-prep -p 11434:11434 docker.io/ollama/ollama:latest

echo "⏳ Waiting for Ollama initialization..."
sleep 5

echo "📥 Pulling ${MODEL_NAME} into container storage..."
podman exec -it ollama-prep ollama pull "${MODEL_NAME}"

echo "📦 Committing container to local image: ${TARGET_IMAGE}..."
podman commit ollama-prep "${TARGET_IMAGE}"

echo "🧹 Cleaning up temporary prep container..."
podman stop ollama-prep && podman rm ollama-prep

echo "✅ Image ${TARGET_IMAGE} successfully built and ready for offline airgapped use!"
