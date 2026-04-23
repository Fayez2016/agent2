FROM docker.io/python:3.11-slim

RUN pip install mcp[fastmcp] requests urllib3

COPY ansible_mcp_server.py /app/ansible_mcp_server.py
WORKDIR /app

# The MCP server runs via stdio, but we can also use HTTP if needed later.
# For now, it will be started by the agent via podman exec or ssh.
# To host it as a persistent service, we'd use a different transport.

CMD ["python", "ansible_mcp_server.py"]
