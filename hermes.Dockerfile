FROM docker.io/nousresearch/hermes-agent:latest

USER root

# Install dependencies into the agent's venv AND system python for safety
RUN /usr/local/bin/uv pip install --python /opt/hermes/.venv/bin/python "mcp[fastmcp]" requests urllib3 flask PyYAML
RUN apt-get update && apt-get install -y python3-yaml python3-requests python3-urllib3 || true

# Decouple agent from native tools by replacing core files
COPY local_model_tools.py /opt/hermes/model_tools.py
COPY local_toolsets.py /opt/hermes/toolsets.py
RUN rm -f /opt/hermes/tools/native_ansible_tool.py /opt/hermes/tools/ansible_tool.py

# Ensure venv is preferred in PATH
ENV PATH="/opt/hermes/.venv/bin:$PATH"

# Use custom entrypoint to avoid chown errors in rootless podman
COPY entrypoint.sh /opt/hermes/docker/entrypoint.sh
RUN chmod +x /opt/hermes/docker/entrypoint.sh

USER hermes
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["gateway", "run"]
