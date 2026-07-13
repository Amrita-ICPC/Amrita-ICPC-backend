-- Runs automatically on a fresh Postgres volume (docker-entrypoint-initdb.d
-- only executes against an empty data directory). If the db service already
-- has data, run this once by hand instead:
--   docker compose exec db psql -U <user> -d <db> -c "CREATE EXTENSION IF NOT EXISTS pg_stat_statements;"
-- The db service's command also needs shared_preload_libraries=pg_stat_statements
-- (see docker-compose.yml), which requires a Postgres restart to take effect.
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
