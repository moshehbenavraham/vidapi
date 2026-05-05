#!/usr/bin/env bash
# Start the non-Docker local development stack.
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

VENV_DIR="${VENV_DIR:-$PROJECT_ROOT/.venv}"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8005}"
API_BASE="http://${API_HOST}:${API_PORT}"

SERVICE_PIDS=()
SERVICE_NAMES=()
TAIL_PID=""

log() {
  echo "[dev] $(date '+%H:%M:%S') $*"
}

usage() {
  cat <<'EOF'
Usage: scripts/dev.sh [async|sync|test|clean-state] [pytest args...]

Modes:
  async  Start Redis, FastAPI, and the ARQ worker. This is the default.
  sync   Start FastAPI only with RENDER_MODE=sync. No Redis required.
  test   Run pytest through the repo-local virtualenv.
  clean-state
         Remove default local SQLite, durable artifacts, and render workspaces.

Useful environment overrides:
  RENDER_MODE=sync|async       Default mode when no CLI mode is supplied.
  API_HOST=127.0.0.1           Bind host for uvicorn.
  API_PORT=8005                Bind port for uvicorn.
  REDIS_URL=redis://127.0.0.1:6380
                               Redis URL for async mode.
  VIDAPI_SKIP_INSTALL=true     Skip Python dependency installation.
  VIDAPI_FORCE_INSTALL=true    Reinstall Python dependencies into .venv.
  VIDAPI_SKIP_MIGRATIONS=true  Skip alembic upgrade head before server start.
EOF
}

is_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

setup_venv() {
  require_command uv

  if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "Creating virtualenv at ${VENV_DIR#$PROJECT_ROOT/}"
    uv venv "$VENV_DIR"
  fi

  if is_true "${VIDAPI_SKIP_INSTALL:-false}"; then
    log "Skipping Python dependency install because VIDAPI_SKIP_INSTALL=true"
    return
  fi

  if is_true "${VIDAPI_FORCE_INSTALL:-false}" \
    || [ ! -x "$VENV_DIR/bin/uvicorn" ] \
    || [ ! -x "$VENV_DIR/bin/arq" ] \
    || [ ! -x "$VENV_DIR/bin/pytest" ]; then
    log "Installing Python dependencies into ${VENV_DIR#$PROJECT_ROOT/}"
    uv pip install --python "$VENV_DIR/bin/python" -e ".[dev]"
  else
    log "Using existing Python dependencies in ${VENV_DIR#$PROJECT_ROOT/}"
  fi
}

setup_local_env() {
  export ENVIRONMENT="${ENVIRONMENT:-development}"
  export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./data/vidapi.db}"
  export DATABASE_AUTO_CREATE="${DATABASE_AUTO_CREATE:-true}"
  export STORAGE_ROOT="${STORAGE_ROOT:-./data}"
  export RENDER_WORKSPACE_ROOT="${RENDER_WORKSPACE_ROOT:-data/renders}"
  export STORAGE_BACKEND="${STORAGE_BACKEND:-local}"
  export STORAGE_URL_MODE="${STORAGE_URL_MODE:-proxy}"
  export API_KEY_AUTH_ENABLED="${API_KEY_AUTH_ENABLED:-false}"
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6380}"

  mkdir -p "$LOG_DIR" "$STORAGE_ROOT" "$RENDER_WORKSPACE_ROOT"
}

check_runtime_tools() {
  require_command curl
  require_command node
  require_command ffmpeg
  require_command ffprobe

  if [ "$MODE" = "async" ]; then
    require_command redis-server
  fi

  if ! command -v editly >/dev/null 2>&1; then
    log "Warning: editly is not on PATH. Default non-HTML renders use Editly; request renderer=ffmpeg-native or install editly for those tests."
  fi

  if ! command -v hyperframes >/dev/null 2>&1; then
    log "Warning: hyperframes is not on PATH. HTML-backed renders need it."
  fi
}

run_migrations() {
  if is_true "${VIDAPI_SKIP_MIGRATIONS:-false}"; then
    log "Skipping migrations because VIDAPI_SKIP_MIGRATIONS=true"
    return
  fi

  log "Applying local database migrations"
  "$VENV_DIR/bin/alembic" upgrade head
}

api_port_available() {
  "$VENV_DIR/bin/python" - <<PY >/dev/null 2>&1
import socket
import sys

host = "${API_HOST}"
port = int("${API_PORT}")

family = socket.AF_INET6 if ":" in host else socket.AF_INET

try:
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
except OSError:
    sys.exit(1)
PY
}

ensure_api_port_available() {
  if api_port_available; then
    return
  fi

  echo "API port ${API_HOST}:${API_PORT} is already in use." >&2
  echo "Stop the existing process or choose another port, for example: API_PORT=8015 scripts/dev.sh ${MODE}" >&2
  exit 1
}

redis_ping() {
  "$VENV_DIR/bin/python" - <<'PY' >/dev/null 2>&1
import os
import sys

from redis import Redis

try:
    redis = Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379"),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    redis.ping()
except Exception:
    sys.exit(1)
PY
}

redis_server_bind_args() {
  "$VENV_DIR/bin/python" - <<'PY'
import os
import sys
from urllib.parse import urlsplit

parsed = urlsplit(os.environ.get("REDIS_URL", "redis://127.0.0.1:6380"))

if parsed.scheme != "redis" or parsed.username or parsed.password:
    sys.exit(1)

host = parsed.hostname or "127.0.0.1"
if host not in {"localhost", "127.0.0.1", "::1"}:
    sys.exit(1)

bind_host = "::1" if host == "::1" else "127.0.0.1"
print(bind_host)
print(parsed.port or 6379)
PY
}

start_process() {
  local name="$1"
  local log_file="$2"
  shift 2

  : >"$log_file"
  log "Starting ${name}; logs: ${log_file#$PROJECT_ROOT/}"
  "$@" >"$log_file" 2>&1 &
  SERVICE_PIDS+=("$!")
  SERVICE_NAMES+=("$name")
}

start_redis_if_needed() {
  if redis_ping; then
    log "Using existing Redis at ${REDIS_URL}"
    return
  fi

  local redis_bind_host
  local redis_info
  local redis_port

  if ! redis_info="$(redis_server_bind_args)"; then
    echo "Redis is not reachable at ${REDIS_URL}; start it separately or use a local unauthenticated redis://127.0.0.1:<port> URL." >&2
    exit 1
  fi

  redis_bind_host="$(printf '%s\n' "$redis_info" | sed -n '1p')"
  redis_port="$(printf '%s\n' "$redis_info" | sed -n '2p')"

  start_process "redis" "$LOG_DIR/dev-redis.log" redis-server \
    --bind "$redis_bind_host" --port "$redis_port" --save "" --appendonly no

  for _ in $(seq 1 30); do
    if redis_ping; then
      log "Redis is ready at ${REDIS_URL}"
      return
    fi
    sleep 1
  done

  echo "Redis did not become ready. Last log lines:" >&2
  tail -n 80 "$LOG_DIR/dev-redis.log" >&2 || true
  exit 1
}

start_api() {
  start_process "api" "$LOG_DIR/dev-api.log" \
    "$VENV_DIR/bin/uvicorn" app.main:app --reload --host "$API_HOST" --port "$API_PORT"
}

start_worker() {
  start_process "worker" "$LOG_DIR/dev-worker.log" \
    "$VENV_DIR/bin/arq" app.workers.arq_settings.WorkerSettings
}

wait_for_api_health() {
  local health_url="${API_BASE}/v1/health"

  log "Waiting for API health at ${health_url}"
  for _ in $(seq 1 45); do
    if curl -fsS "$health_url" >/dev/null 2>&1; then
      log "API is ready: ${API_BASE}"
      return
    fi
    sleep 1
  done

  echo "API did not become healthy. Last log lines:" >&2
  tail -n 120 "$LOG_DIR/dev-api.log" >&2 || true
  exit 1
}

start_log_tail() {
  local tail_files=("$LOG_DIR/dev-api.log")

  if [ "$MODE" = "async" ]; then
    touch "$LOG_DIR/dev-worker.log" "$LOG_DIR/dev-redis.log"
    tail_files+=("$LOG_DIR/dev-worker.log" "$LOG_DIR/dev-redis.log")
  fi

  log "Streaming logs. Press Ctrl+C to stop the local stack."
  tail -n 0 -F "${tail_files[@]}" &
  TAIL_PID="$!"
}

cleanup() {
  local status=$?

  trap - EXIT INT TERM

  if [ -n "$TAIL_PID" ]; then
    kill "$TAIL_PID" 2>/dev/null || true
    wait "$TAIL_PID" 2>/dev/null || true
  fi

  for pid in "${SERVICE_PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done

  for pid in "${SERVICE_PIDS[@]}"; do
    wait "$pid" 2>/dev/null || true
  done

  exit "$status"
}

watch_processes() {
  local index
  local pid
  local name
  local status

  while true; do
    for index in "${!SERVICE_PIDS[@]}"; do
      pid="${SERVICE_PIDS[$index]}"
      name="${SERVICE_NAMES[$index]}"

      if ! kill -0 "$pid" 2>/dev/null; then
        if wait "$pid"; then
          status=0
        else
          status=$?
        fi
        log "${name} exited with status ${status}"
        return "$status"
      fi
    done
    sleep 1
  done
}

run_test_mode() {
  setup_venv
  export ENVIRONMENT="${ENVIRONMENT:-test}"
  log "Running pytest"
  exec "$VENV_DIR/bin/pytest" "$@"
}

clean_local_state() {
  setup_local_env

  if [ "$DATABASE_URL" = "sqlite+aiosqlite:///./data/vidapi.db" ] \
    || [ "$DATABASE_URL" = "sqlite:///./data/vidapi.db" ]; then
    log "Removing default local SQLite database"
    rm -f data/vidapi.db data/vidapi.db-shm data/vidapi.db-wal
  else
    log "Skipping database cleanup for non-default DATABASE_URL=${DATABASE_URL}"
  fi

  if [ "$STORAGE_ROOT" = "./data" ] || [ "$STORAGE_ROOT" = "data" ]; then
    log "Removing default durable local artifacts"
    rm -rf data/artifacts
  else
    log "Skipping artifact cleanup for non-default STORAGE_ROOT=${STORAGE_ROOT}"
  fi

  if [ "$RENDER_WORKSPACE_ROOT" = "data/renders" ] \
    || [ "$RENDER_WORKSPACE_ROOT" = "./data/renders" ]; then
    log "Removing default render workspaces"
    rm -rf data/renders
  else
    log "Skipping workspace cleanup for non-default RENDER_WORKSPACE_ROOT=${RENDER_WORKSPACE_ROOT}"
  fi

  mkdir -p "$STORAGE_ROOT" "$RENDER_WORKSPACE_ROOT"
  log "Local development state reset"
}

CLI_MODE=""
if [ "$#" -gt 0 ]; then
  case "$1" in
    async|sync|test|clean-state)
      CLI_MODE="$1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
fi

MODE="${CLI_MODE:-${RENDER_MODE:-async}}"
case "$MODE" in
  async|sync|test|clean-state) ;;
  *)
    echo "Unsupported mode: ${MODE}" >&2
    usage >&2
    exit 2
    ;;
esac

if [ "$MODE" = "test" ]; then
  run_test_mode "$@"
fi

if [ "$MODE" = "clean-state" ]; then
  clean_local_state
  exit 0
fi

trap cleanup EXIT INT TERM

setup_venv
setup_local_env
export RENDER_MODE="$MODE"

check_runtime_tools
ensure_api_port_available
run_migrations

if [ "$MODE" = "async" ]; then
  start_redis_if_needed
fi

start_api
wait_for_api_health

if [ "$MODE" = "async" ]; then
  start_worker
fi

log "OpenAPI docs: ${API_BASE}/docs"
log "Health check: curl ${API_BASE}/v1/health"
start_log_tail
watch_processes
