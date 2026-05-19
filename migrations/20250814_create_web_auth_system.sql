-- Migration: 20250814_create_web_auth_system.sql
-- Datenschutz-Rechtsprechung API Authentication System
-- Ausführen mit: psql $DATABASE_URL < migrations/20250814_create_web_auth_system.sql

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table for Flask Web-UI authentication
CREATE TABLE IF NOT EXISTS web_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100),
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    -- GDPR-spezifische Felder
    department VARCHAR(100),
    role VARCHAR(50) DEFAULT 'viewer',
    -- Audit fields
    created_by UUID REFERENCES web_users(id),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by UUID REFERENCES web_users(id)
);

-- Performance indices für web_users
CREATE INDEX IF NOT EXISTS idx_web_users_username ON web_users(username);
CREATE INDEX IF NOT EXISTS idx_web_users_email ON web_users(email);
CREATE INDEX IF NOT EXISTS idx_web_users_is_active ON web_users(is_active);

-- Password reset tokens table
CREATE TABLE IF NOT EXISTS web_auth_tokens (
    id SERIAL PRIMARY KEY,
    token VARCHAR(100) UNIQUE NOT NULL,
    user_id UUID NOT NULL REFERENCES web_users(id) ON DELETE CASCADE,
    token_type VARCHAR(20) DEFAULT 'password_reset',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMP,
    ip_address INET,
    user_agent TEXT
);

-- Performance indices für web_auth_tokens
CREATE INDEX IF NOT EXISTS idx_web_auth_tokens_token ON web_auth_tokens(token);
CREATE INDEX IF NOT EXISTS idx_web_auth_tokens_user_id ON web_auth_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_web_auth_tokens_expires ON web_auth_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_web_auth_tokens_type_used ON web_auth_tokens(token_type, used);

-- Default Admin User (Passwort: admin123)
-- Hash generiert mit bcrypt: $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewBqp5Sk3q6x5wxK
INSERT INTO web_users (username, email, first_name, last_name, password_hash, is_admin, role)
VALUES (
    'admin',
    'admin@datenschutz-rechtsprechung-api.local',
    'GDPR',
    'Administrator',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewBqp5Sk3q6x5wxK', -- admin123
    TRUE,
    'admin'
) ON CONFLICT (username) DO NOTHING;

-- Viewer Test User (Passwort: viewer123)
-- Hash generiert mit bcrypt: $2b$12$Q7jUNpV5RVMmQ2YXmOwc3OYdkjM6CQJdD6YJQk8tJJJ8UwrWQGGmC
INSERT INTO web_users (username, email, first_name, last_name, password_hash, is_admin, role)
VALUES (
    'viewer',
    'viewer@datenschutz-rechtsprechung-api.local',
    'GDPR',
    'Viewer',
    '$2b$12$Q7jUNpV5RVMmQ2YXmOwc3OYdkjM6CQJdD6YJQk8tJJJ8UwrWQGGmC', -- viewer123
    FALSE,
    'viewer'
) ON CONFLICT (username) DO NOTHING;

-- Trigger für updated_at Timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_web_users_updated_at 
    BEFORE UPDATE ON web_users 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Verify table creation
SELECT 'web_users table created with ' || COUNT(*) || ' users' FROM web_users;
SELECT 'web_auth_tokens table created' AS status WHERE EXISTS (SELECT FROM web_auth_tokens LIMIT 0);

COMMIT;