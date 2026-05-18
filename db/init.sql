-- Initialize HITL Database
-- Note: User and Database creation are handled by init_wrapper.sh or these commands if run as superuser

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hitl_requests (
    id SERIAL PRIMARY KEY,
    action_name VARCHAR(100), -- New column for strict matching
    action_summary TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'PENDING', -- PENDING, GRANTED, DENIED
    requested_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by INTEGER REFERENCES users(id)
);

-- Seed admin user (password: admin123)
-- Hash generated via werkzeug.security.generate_password_hash inside the container
INSERT INTO users (username, password_hash) 
VALUES ('admin', 'scrypt:32768:8:1$Cp9hPMQuK27drPui$f27cfbd2677aa90ed0d52978d805b0b5cff6e39f2afd1dabdf7ab0170505b443830450bdaeecd429b4d8ceedf66c9a84c04fbe5678735367b888923e139cdb8a')
ON CONFLICT (username) DO NOTHING;

-- Grant permissions to hermes
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hermes;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO hermes;
