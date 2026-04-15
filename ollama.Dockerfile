FROM docker.io/ollama/ollama:latest

# Start Ollama, pull the model, then kill the server to bake it into the image
# (Note: This might result in a large image, but it's useful for airgapped setups)
RUN ollama serve & \
    sleep 5 && \
    ollama pull qwen2.5:0.5b && \
    pkill ollama

EXPOSE 11434
ENTRYPOINT ["ollama", "serve"]
