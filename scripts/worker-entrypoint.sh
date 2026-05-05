#!/usr/bin/env bash
# Worker entrypoint: start Xvfb for headless GL rendering, then launch ARQ.
set -euo pipefail

DISPLAY_NUM="${DISPLAY_NUM:-99}"
export DISPLAY=":${DISPLAY_NUM}"

Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!

cleanup() {
    kill "$XVFB_PID" 2>/dev/null || true
    wait "$XVFB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 1

exec arq app.workers.arq_settings.WorkerSettings
