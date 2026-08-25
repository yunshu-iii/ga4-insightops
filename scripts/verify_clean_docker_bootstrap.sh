#!/usr/bin/env bash
set -euo pipefail

readonly CLEAN_PROJECT="insightops-clean-bootstrap"
readonly CLEAN_CONTAINER="insightops-clean-bootstrap-mysql"
readonly CLEAN_PORT="${CLEAN_MYSQL_PORT:-3307}"
readonly CLEAN_PASSWORD="${CLEAN_MYSQL_ROOT_PASSWORD:-insightops-clean-bootstrap-only}"
readonly COMPOSE=(docker compose -p "$CLEAN_PROJECT" -f compose.yaml -f compose.clean.yml)

cleanup() {
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}

trap cleanup EXIT
cleanup

export CLEAN_MYSQL_PORT="$CLEAN_PORT"
export CLEAN_MYSQL_ROOT_PASSWORD="$CLEAN_PASSWORD"
export MYSQL_PORT="$CLEAN_PORT"
"${COMPOSE[@]}" up -d

for _ in $(seq 1 30); do
  if docker exec "$CLEAN_CONTAINER" mysqladmin ping -h localhost -u root -p"$CLEAN_PASSWORD" --silent; then
    break
  fi
  sleep 2
done

docker exec "$CLEAN_CONTAINER" mysqladmin ping -h localhost -u root -p"$CLEAN_PASSWORD" --silent
database_count="$(
  docker exec "$CLEAN_CONTAINER" mysql -N -u root -p"$CLEAN_PASSWORD" -e \
    "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name IN ('insightops_raw', 'insightops_dw', 'insightops_ops', 'insightops_mart');"
)"
table_count="$(
  docker exec "$CLEAN_CONTAINER" mysql -N -u root -p"$CLEAN_PASSWORD" -e \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('insightops_raw', 'insightops_dw', 'insightops_ops', 'insightops_mart');"
)"

if [[ "$database_count" != "4" ]]; then
  echo "Expected four InsightOps schemas, found $database_count" >&2
  exit 1
fi
if [[ "$table_count" -lt "10" ]]; then
  echo "Expected at least ten initialized tables, found $table_count" >&2
  exit 1
fi

echo "Clean Docker bootstrap passed: schemas=$database_count tables=$table_count port=$CLEAN_PORT"
