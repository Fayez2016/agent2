FROM docker.io/nousresearch/hermes-agent:latest

USER root

# Install dependencies into the agent's venv AND system python for safety
RUN /usr/local/bin/uv pip install --python /opt/hermes/.venv/bin/python "hermes-agent[web,pty]" "mcp[fastmcp]" requests urllib3 flask PyYAML
RUN apt-get update && apt-get install -y python3-yaml python3-requests python3-urllib3 || true

USER hermes
CMD ["gateway", "run"]
