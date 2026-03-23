-- Read-only role for Grafana (local dev defaults; rotate in real deployments)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
    CREATE ROLE grafana_ro WITH LOGIN PASSWORD 'grafana';
  END IF;
END
$$;

DO $$
DECLARE
  db text := current_database();
BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO grafana_ro', db);
END
$$;

GRANT USAGE ON SCHEMA mart, dim, meta TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA mart, dim, meta TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA dim GRANT SELECT ON TABLES TO grafana_ro;
