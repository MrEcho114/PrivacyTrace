-- Run once with a cluster administrator on the intended new database.
-- No credentials are stored here. Set each LOGIN password through the operator's
-- secret provisioning or interactive psql \password, never a committed SQL file.
CREATE ROLE privacytrace_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE privacytrace_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE DATABASE privacytrace OWNER privacytrace_migrator;
\connect privacytrace
REVOKE ALL ON DATABASE privacytrace FROM PUBLIC;
GRANT CONNECT ON DATABASE privacytrace TO privacytrace_migrator, privacytrace_runtime;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
