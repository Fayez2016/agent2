FROM docker.io/library/alpine:latest
RUN apk add --no-cache postgresql postgresql-contrib

RUN mkdir -p /run/postgresql && chown -R postgres:postgres /run/postgresql
RUN mkdir -p /var/lib/postgresql/data && chown -R postgres:postgres /var/lib/postgresql/data

USER postgres
RUN initdb -D /var/lib/postgresql/data
RUN echo "host all all 0.0.0.0/0 trust" >> /var/lib/postgresql/data/pg_hba.conf
RUN echo "listen_addresses='*'" >> /var/lib/postgresql/data/postgresql.conf

USER root
COPY init_wrapper.sh /usr/local/bin/init_wrapper.sh
RUN chmod +x /usr/local/bin/init_wrapper.sh
USER postgres

EXPOSE 5432
CMD ["/usr/local/bin/init_wrapper.sh"]
