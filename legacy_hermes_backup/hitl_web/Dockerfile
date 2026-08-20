FROM docker.io/python:3.11-slim

RUN pip install flask flask-sqlalchemy flask-login psycopg2-binary werkzeug flask-wtf

COPY . /app
WORKDIR /app

EXPOSE 5000

CMD ["python", "app.py"]
