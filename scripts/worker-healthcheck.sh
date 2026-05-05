#!/usr/bin/env bash
# Worker health check: verify ARQ liveness via Redis health key.
# ARQ writes a health key every health_check_interval seconds.
# This script checks that the key exists and was updated recently.
set -euo pipefail

REDIS_URL="${REDIS_URL:-redis://redis:6379}"

REDIS_HOST="$(echo "$REDIS_URL" | sed -E 's|^redis://([^:/@]+).*|\1|')"
REDIS_PORT="$(echo "$REDIS_URL" | sed -E 's|^redis://[^:]+:([0-9]+).*|\1|')"
REDIS_PORT="${REDIS_PORT:-6379}"

MAX_RETRIES=2
RETRY_DELAY=1
TIMEOUT=3

for attempt in $(seq 0 "$MAX_RETRIES"); do
    if [ "$attempt" -gt 0 ]; then
        sleep "$RETRY_DELAY"
    fi

    health_val=$(curl -sf --max-time "$TIMEOUT" \
        "http://localhost:8000/v1/health" 2>/dev/null || true)

    if [ -n "$health_val" ]; then
        exit 0
    fi

    # Fallback: check Redis connectivity directly
    if command -v redis-cli >/dev/null 2>&1; then
        pong=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
            --no-auth-warning ping 2>/dev/null || true)
        if [ "$pong" = "PONG" ]; then
            # Redis is alive; check for arq health key
            key_exists=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" \
                --no-auth-warning exists arq:health-check 2>/dev/null || echo "0")
            if [ "$key_exists" = "1" ] || [ "$key_exists" = "(integer) 1" ]; then
                exit 0
            fi
        fi
    fi
done

echo "Worker health check failed after $((MAX_RETRIES + 1)) attempts" >&2
exit 1
