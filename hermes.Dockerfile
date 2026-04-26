FROM docker.io/nousresearch/hermes-agent:latest

# Minimal Dockerfile as requested - pulling base image only
USER root
RUN /usr/local/bin/uv pip install --python /opt/hermes/.venv/bin/python "mcp[fastmcp]" requests urllib3

# Decouple agent from native tools by replacing core files
COPY local_model_tools.py /opt/hermes/model_tools.py
COPY local_toolsets.py /opt/hermes/toolsets.py
RUN rm -f /opt/hermes/tools/native_ansible_tool.py /opt/hermes/tools/ansible_tool.py

# Use custom entrypoint to avoid chown errors in rootless podman
COPY entrypoint.sh /opt/hermes/docker/entrypoint.sh
RUN chmod +x /opt/hermes/docker/entrypoint.sh

USER hermes
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["gateway", "run"]
