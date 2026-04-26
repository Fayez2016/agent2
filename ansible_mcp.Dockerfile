FROM docker.io/python:3.11-slim

RUN pip install mcp[fastmcp] requests urllib3

COPY ansible_mcp_server.py /app/ansible_mcp_server.py
WORKDIR /app

# The MCP server runs as a persistent HTTP service on port 8000.
# It is accessed by the agent via the internal network.

CMD ["python", "ansible_mcp_server.py"]
