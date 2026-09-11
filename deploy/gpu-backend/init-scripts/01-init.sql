-- =============================================================================
-- PostgreSQL Database Initialization Script
-- Automatically executed on first container startup by /docker-entrypoint-initdb.d
-- =============================================================================

-- Ensure required database extensions are enabled
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE main_crowd_ai TO postgres;

-- Log success
DO $$
BEGIN
    RAISE NOTICE 'BYC Crowd AI Database Extensions (uuid-ossp, postgis, pgcrypto) initialized successfully!';
END $$;
