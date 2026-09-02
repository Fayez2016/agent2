#!/bin/sh
set -e

# Fix permissions on runtime directories as root before running postgres
mkdir -p /run/postgresql /var/lib/postgresql/data
chown -R postgres:postgres /run/postgresql /var/lib/postgresql/data
chmod 700 /var/lib/postgresql/data

# Start postgres in background to initialize if needed
if [ ! -f /var/lib/postgresql/data/initialized ]; then
    echo "First run: initializing database..."
    su-exec postgres pg_ctl -D /var/lib/postgresql/data -o "-c listen_addresses=''" -w start
    
    # Wait for it to be ready
    until su-exec postgres pg_isready; do sleep 1; done
    
    # Run the init script if it exists
    if [ -f /docker-entrypoint-initdb.d/init.sql ]; then
        echo "Creating user and database..."
        su-exec postgres psql -d postgres -c "CREATE USER ${POSTGRES_USER} WITH PASSWORD '${POSTGRES_PASSWORD}';" || true
        su-exec postgres psql -d postgres -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};" || true
        
        echo "Running init.sql on ${POSTGRES_DB}..."
        su-exec postgres psql -d ${POSTGRES_DB} -f /docker-entrypoint-initdb.d/init.sql
    fi
    
    su-exec postgres pg_ctl -D /var/lib/postgresql/data -m fast -w stop
    touch /var/lib/postgresql/data/initialized
fi

echo "Starting PostgreSQL..."
exec su-exec postgres postgres -D /var/lib/postgresql/data
