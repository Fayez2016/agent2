#!/bin/bash

# Exit on error
set -e

echo "🚀 Building Mock AAP image..."
podman build -t local-mock-aap -f mock_aap.Dockerfile .

echo "📦 Starting services with podman-compose..."
podman-compose up -d

echo "⏳ Waiting for services to initialize (10s)..."
sleep 10

echo "🧪 Running Test Command: '/ansible-run-command command=\"uptime\" hostname=\"test-server\"'"
echo "--------------------------------------------------------------------------------"

# Run the hermes chat command with a pre-defined input
# Note: Since the chat is interactive, we pipe the command to it.
# If the agent is configured to auto-exit or handle single commands, this works best.
# We use a simple echo here to simulate the interaction.
# We'll also use 'hermes skills list' first to verify skills are loaded.

podman exec -u hermes hermes-agent bash -c "source /opt/hermes/.venv/bin/activate && /opt/hermes/hermes skills list"

echo "--------------------------------------------------------------------------------"
echo "Sending command to agent..."
# We use a small timeout or specific command to avoid hanging if the chat is too interactive
podman exec -u hermes hermes-agent bash -c "source /opt/hermes/.venv/bin/activate && echo '/ansible-run-command command=\"uptime\" hostname=\"test-server\"' | /opt/hermes/hermes chat"

echo "--------------------------------------------------------------------------------"
echo "✅ Test script completed. Check the output above to verify if the agent reacted to the Mock AAP."
echo "You can check mock-aap logs with: podman logs mock-aap"
