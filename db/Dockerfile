FROM docker.io/library/postgres:16-alpine

ENV POSTGRES_USER=hermes \
    POSTGRES_PASSWORD=secret456 \
    POSTGRES_DB=hitl \
    PGDATA=/var/lib/postgresql/data/pgdata

COPY 01-schema-and-data.sql /docker-entrypoint-initdb.d/01-schema-and-data.sql

EXPOSE 5432
