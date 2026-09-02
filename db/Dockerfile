FROM docker.io/library/postgres:16-alpine

ENV POSTGRES_USER=hermes \
    POSTGRES_PASSWORD=secret456 \
    POSTGRES_DB=hitl

COPY init.sql /docker-entrypoint-initdb.d/init.sql

EXPOSE 5432
