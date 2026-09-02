FROM docker.io/library/postgres:16-alpine

COPY init.sql /docker-entrypoint-initdb.d/init.sql

ENV POSTGRES_USER=hermes \
    POSTGRES_PASSWORD=secret456 \
    POSTGRES_DB=hitl

EXPOSE 5432
