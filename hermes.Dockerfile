FROM docker.io/nousresearch/hermes-agent:latest

# Minimal Dockerfile as requested - pulling base image only
USER root
RUN /opt/hermes/.venv/bin/pip install "mcp[fastmcp]" requests urllib3
USER hermes
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["gateway", "run"]
