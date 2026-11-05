#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
readonly CLEAN_PROJECT="insightops-clean-${RANDOM}-${RANDOM}-$$"
readonly CLEAN_PASSWORD="${CLEAN_MYSQL_ROOT_PASSWORD:-$(openssl rand -hex 32)}"
readonly COMPOSE=(docker compose -p "$CLEAN_PROJECT" -f compose.clean.yml)

cleanup() {
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}

trap cleanup EXIT
export CLEAN_MYSQL_ROOT_PASSWORD="$CLEAN_PASSWORD"
"${COMPOSE[@]}" up -d

for _ in $(seq 1 30); do
  if "${COMPOSE[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -N -u root -e "SELECT 1"' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

"${COMPOSE[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -N -u root -e "SELECT 1"' >/dev/null
database_count="$(
  "${COMPOSE[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -N -u root' <<'SQL'
SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name IN ('insightops_raw', 'insightops_dw', 'insightops_ops', 'insightops_mart');
SQL
)"
table_count="$(
  "${COMPOSE[@]}" exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -N -u root' <<'SQL'
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('insightops_raw', 'insightops_dw', 'insightops_ops', 'insightops_mart');
SQL
)"

if [[ "$database_count" != "4" ]]; then
  echo "Expected four InsightOps schemas, found $database_count" >&2
  exit 1
fi
if [[ "$table_count" -lt "10" ]]; then
  echo "Expected at least ten initialized tables, found $table_count" >&2
  exit 1
fi

echo "Clean Docker bootstrap passed: schemas=$database_count tables=$table_count host_ports=none"
