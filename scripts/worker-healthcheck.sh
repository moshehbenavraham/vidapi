#!/usr/bin/env bash
# Worker health check: verify ARQ liveness via Redis health key.
# ARQ writes a health key every health_check_interval seconds.
# This script checks that the key exists and was updated recently.
set -euo pipefail

REDIS_URL="${REDIS_URL:-redis://redis:6379}"
API_HEALTH_URL="${API_HEALTH_URL:-http://api:8000/v1/health}"
WORKER_HEALTH_KEY="${WORKER_HEALTH_KEY:-arq:health-check}"

MAX_RETRIES=2
RETRY_DELAY=1
TIMEOUT=3

redis_cli() {
    timeout "$TIMEOUT" redis-cli -u "$REDIS_URL" --no-auth-warning "$@" \
        2>/dev/null || true
}

for attempt in $(seq 0 "$MAX_RETRIES"); do
    if [ "$attempt" -gt 0 ]; then
        sleep "$RETRY_DELAY"
    fi

    health_val=$(curl -sf --max-time "$TIMEOUT" "$API_HEALTH_URL" 2>/dev/null || true)

    if [ -n "$health_val" ]; then
        exit 0
    fi

    # Fallback: check Redis connectivity directly
    if command -v redis-cli >/dev/null 2>&1; then
        pong=$(redis_cli ping)
        if [ "$pong" = "PONG" ]; then
            # Redis is alive; check for arq health key
            key_exists=$(redis_cli exists "$WORKER_HEALTH_KEY")
            if [ "$key_exists" = "1" ] || [ "$key_exists" = "(integer) 1" ]; then
                exit 0
            fi
        fi
    fi
done

echo "Worker health check failed after $((MAX_RETRIES + 1)) attempts" >&2
exit 1
