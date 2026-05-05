#!/usr/bin/env bash
set -Eeuo pipefail

DATABASE_URL="${DATABASE_URL:-}"
TIMEOUT_SECONDS="${POSTGRES_MIGRATION_SMOKE_TIMEOUT_SECONDS:-45}"
MAX_ATTEMPTS="${POSTGRES_MIGRATION_SMOKE_RETRIES:-3}"
BACKOFF_SECONDS="${POSTGRES_MIGRATION_SMOKE_BACKOFF_SECONDS:-2}"

is_postgres_url() {
  case "$DATABASE_URL" in
    postgres://*|postgres+asyncpg://*|postgresql://*|postgresql+asyncpg://*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

run_with_retry() {
  local label="$1"
  shift
  local attempt=1
  local delay="$BACKOFF_SECONDS"

  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    echo "postgres migration smoke: ${label} attempt ${attempt}/${MAX_ATTEMPTS}"
    if timeout "$TIMEOUT_SECONDS" "$@"; then
      return 0
    fi

    local status=$?
    if [ "$attempt" -eq "$MAX_ATTEMPTS" ]; then
      echo "postgres migration smoke: ${label} failed after ${MAX_ATTEMPTS} attempts" >&2
      return "$status"
    fi

    sleep "$delay"
    delay=$((delay * 2))
    attempt=$((attempt + 1))
  done
}

if [ -z "$DATABASE_URL" ]; then
  echo "postgres migration smoke: skipping because DATABASE_URL is not set"
  exit 0
fi

if ! is_postgres_url; then
  echo "postgres migration smoke: skipping because DATABASE_URL is not PostgreSQL"
  exit 0
fi

run_with_retry "upgrade head" uv run alembic upgrade head
run_with_retry "current revision" uv run alembic current

if [ "${POSTGRES_MIGRATION_SMOKE_DISPOSABLE:-false}" = "true" ]; then
  run_with_retry "downgrade base" uv run alembic downgrade base
  run_with_retry "upgrade head after downgrade" uv run alembic upgrade head
else
  echo "postgres migration smoke: skipping downgrade; set POSTGRES_MIGRATION_SMOKE_DISPOSABLE=true for disposable databases"
fi
