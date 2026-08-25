-- Apply this idempotent migration to an existing InsightOps MySQL database.
SOURCE /docker-entrypoint-initdb.d/10_ga4_json_derivatives.sql;
