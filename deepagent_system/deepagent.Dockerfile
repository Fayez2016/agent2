FROM docker.io/python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application source code & official MCP config
COPY app /app/app
COPY .deepagents /app/.deepagents
COPY .mcp.json /app/.mcp.json

# Expose API port
EXPOSE 8642

# Run FastAPI server via app.main
CMD ["python", "-m", "app.main"]
