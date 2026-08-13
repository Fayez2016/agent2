FROM docker.io/python:3.11-slim
RUN pip install flask requests
COPY mock_aap.py /app/mock_aap.py
WORKDIR /app
EXPOSE 5000
CMD ["python", "mock_aap.py"]
