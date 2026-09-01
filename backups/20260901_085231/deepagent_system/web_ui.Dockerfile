FROM docker.io/python:3.11-slim
WORKDIR /app
COPY web_ui /app
EXPOSE 3000
CMD ["python", "-m", "http.server", "3000"]
