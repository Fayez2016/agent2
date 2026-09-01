FROM docker.io/python:3.11-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install mcp==1.28.1 requests urllib3

WORKDIR /app
COPY server.py /app/server.py

EXPOSE 8001

CMD ["python", "server.py"]
