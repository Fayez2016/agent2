FROM docker.io/nousresearch/hermes-agent:latest

# Set environment variables
ENV TZ=UTC
ENV HERMES_HOME=/opt/data

# Ensure the data directory exists and has correct permissions
USER root
RUN mkdir -p /opt/data && chown -R hermes:hermes /opt/data
USER hermes

# Pre-seed the configuration file and set context_length to override the 64k requirement
RUN echo 'model:\n  default: "qwen2.5:0.5b"\n  provider: custom\n  base_url: "http://ollama:11434/v1"\n  context_length: 64000' > /opt/data/config.yaml

# Set the entrypoint to the original entrypoint script
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["gateway", "run"]
