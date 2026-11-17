-- Initialize AegisOps PostgreSQL databases and extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Separate logical database for Langfuse self-hosted server
SELECT 'CREATE DATABASE aegisops_langfuse'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'aegisops_langfuse')\gexec
