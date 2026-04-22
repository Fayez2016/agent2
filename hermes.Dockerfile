FROM docker.io/nousresearch/hermes-agent:latest

# Minimal Dockerfile as requested - pulling base image only
USER hermes
ENTRYPOINT ["/opt/hermes/docker/entrypoint.sh"]
CMD ["gateway", "run"]
