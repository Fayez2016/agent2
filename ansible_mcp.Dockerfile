FROM docker.io/python:3.11-slim

# Install system dependencies and python packages
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install mcp[fastmcp] requests urllib3 flask psycopg2-binary

COPY ansible_mcp_server.py /app/ansible_mcp_server.py
WORKDIR /app

# 8000 for MCP, 5000 for HITL UI
EXPOSE 8000 5000

CMD ["python", "ansible_mcp_server.py"]
