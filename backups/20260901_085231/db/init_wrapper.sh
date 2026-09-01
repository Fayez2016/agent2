#!/bin/sh
set -e

# Start postgres in background to initialize if needed
if [ ! -f /var/lib/postgresql/data/initialized ]; then
    echo "First run: initializing database..."
    pg_ctl -D /var/lib/postgresql/data -o "-c listen_addresses=''" -w start
    
    # Wait for it to be ready
    until pg_isready; do sleep 1; done
    
    # Run the init script if it exists
    if [ -f /docker-entrypoint-initdb.d/init.sql ]; then
        echo "Creating user and database..."
        psql -d postgres -c "CREATE USER ${POSTGRES_USER} WITH PASSWORD '${POSTGRES_PASSWORD}';" || true
        psql -d postgres -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};" || true
        
        echo "Running init.sql on ${POSTGRES_DB}..."
        psql -d ${POSTGRES_DB} -f /docker-entrypoint-initdb.d/init.sql
    fi
    
    pg_ctl -D /var/lib/postgresql/data -m fast -w stop
    touch /var/lib/postgresql/data/initialized
fi

echo "Starting PostgreSQL..."
exec postgres -D /var/lib/postgresql/data
