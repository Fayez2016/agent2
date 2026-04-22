#!/bin/bash
set -e
echo "Starting Ollama prep container with GPU passthrough..."
podman run -d --name ollama-prep -p 11434:11434 docker.io/ollama/ollama:latest
echo "Waiting for initialization..."
sleep 5
echo "Pulling qwen3:1.7b into System RAM..."
podman exec -it ollama-prep ollama pull qwen3:1.7b
echo "Committing container to image..."
podman commit ollama-prep localhost/local-ollama:latest
echo "Cleaning up..."
podman stop ollama-prep && podman rm ollama-prep
echo "Image localhost/local-ollama:latest successfully built for air-gapped use!"
