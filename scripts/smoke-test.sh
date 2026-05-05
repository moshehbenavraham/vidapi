#!/usr/bin/env bash
# End-to-end smoke test for VidAPI Docker Compose stack.
# Verifies: health -> submit render -> poll until terminal -> report pass/fail.
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000}"
HEALTH_URL="${API_BASE}/v1/health"
RENDERS_URL="${API_BASE}/v1/renders"

MAX_HEALTH_WAIT=60
HEALTH_POLL_INTERVAL=3

MAX_RENDER_WAIT=180
RENDER_POLL_INTERVAL=5

PASS=0
FAIL=0
TESTS_RUN=0

log() { echo "[smoke-test] $(date '+%H:%M:%S') $*"; }

fail_test() {
    log "FAIL: $1"
    FAIL=$((FAIL + 1))
    TESTS_RUN=$((TESTS_RUN + 1))
}

pass_test() {
    log "PASS: $1"
    PASS=$((PASS + 1))
    TESTS_RUN=$((TESTS_RUN + 1))
}

# -----------------------------------------------------------------------
# 1. Wait for API health
# -----------------------------------------------------------------------
log "Waiting for API health at ${HEALTH_URL} ..."
elapsed=0
api_healthy=false

while [ "$elapsed" -lt "$MAX_HEALTH_WAIT" ]; do
    status_code=$(curl -sf -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")
    if [ "$status_code" = "200" ]; then
        api_healthy=true
        break
    fi
    sleep "$HEALTH_POLL_INTERVAL"
    elapsed=$((elapsed + HEALTH_POLL_INTERVAL))
    log "  ... waiting (${elapsed}s / ${MAX_HEALTH_WAIT}s, last status: ${status_code})"
done

if [ "$api_healthy" = true ]; then
    pass_test "API health endpoint reachable"
else
    fail_test "API health endpoint not reachable after ${MAX_HEALTH_WAIT}s"
    log "Cannot continue without API. Exiting."
    echo ""
    echo "=== SMOKE TEST RESULT: FAIL (${PASS} passed, ${FAIL} failed) ==="
    exit 1
fi

# -----------------------------------------------------------------------
# 2. Verify health response content
# -----------------------------------------------------------------------
health_body=$(curl -sf "$HEALTH_URL" 2>/dev/null || echo "{}")
overall_status=$(echo "$health_body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
redis_status=$(echo "$health_body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('redis',{}).get('status',''))" 2>/dev/null || echo "")

if [ "$overall_status" = "healthy" ]; then
    pass_test "Health status is healthy"
else
    fail_test "Health status is '${overall_status}', expected 'healthy'"
fi

if [ "$redis_status" = "healthy" ]; then
    pass_test "Redis status is healthy"
else
    fail_test "Redis status is '${redis_status}', expected 'healthy'"
fi

# -----------------------------------------------------------------------
# 3. Submit a minimal render (color asset, 1 second)
# -----------------------------------------------------------------------
log "Submitting minimal render (color asset, 1s) ..."

COMPOSITION='{
  "timeline": {
    "background": "#000000",
    "tracks": [
      {
        "clips": [
          {
            "asset": {"type": "color", "color": "#3366ff"},
            "start": 0,
            "length": 1
          }
        ]
      }
    ]
  },
  "output": {
    "format": "mp4",
    "width": 320,
    "height": 240,
    "fps": 15,
    "quality": "low"
  }
}'

submit_response=$(curl -sf -X POST "$RENDERS_URL" \
    -H "Content-Type: application/json" \
    -d "$COMPOSITION" 2>/dev/null || echo "")

if [ -z "$submit_response" ]; then
    fail_test "POST /v1/renders returned empty response"
    log "Cannot continue without render ID. Exiting."
    echo ""
    echo "=== SMOKE TEST RESULT: FAIL (${PASS} passed, ${FAIL} failed) ==="
    exit 1
fi

render_id=$(echo "$submit_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
submit_status=$(echo "$submit_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")

if [ -n "$render_id" ] && [ "$submit_status" = "queued" ]; then
    pass_test "Render submitted (id=${render_id}, status=queued)"
else
    fail_test "Unexpected submit response: ${submit_response}"
    log "Cannot poll without valid render ID. Exiting."
    echo ""
    echo "=== SMOKE TEST RESULT: FAIL (${PASS} passed, ${FAIL} failed) ==="
    exit 1
fi

# -----------------------------------------------------------------------
# 4. Poll until terminal state
# -----------------------------------------------------------------------
log "Polling render ${render_id} (timeout ${MAX_RENDER_WAIT}s) ..."
elapsed=0
final_status=""

while [ "$elapsed" -lt "$MAX_RENDER_WAIT" ]; do
    poll_response=$(curl -sf "${RENDERS_URL}/${render_id}" 2>/dev/null || echo "")
    current_status=$(echo "$poll_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
    current_progress=$(echo "$poll_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('progress',0))" 2>/dev/null || echo "0")

    if [ "$current_status" = "succeeded" ] || [ "$current_status" = "failed" ] || [ "$current_status" = "cancelled" ]; then
        final_status="$current_status"
        break
    fi

    sleep "$RENDER_POLL_INTERVAL"
    elapsed=$((elapsed + RENDER_POLL_INTERVAL))
    log "  ... status=${current_status}, progress=${current_progress} (${elapsed}s / ${MAX_RENDER_WAIT}s)"
done

if [ "$final_status" = "succeeded" ]; then
    pass_test "Render completed with status=succeeded"
elif [ "$final_status" = "failed" ]; then
    fail_test "Render completed with status=failed"
    error_detail=$(echo "$poll_response" | python3 -c "import sys,json; e=json.load(sys.stdin).get('error',{}); print(f\"{e.get('code','?')}: {e.get('message','?')}\")" 2>/dev/null || echo "unknown")
    log "  Error: ${error_detail}"
elif [ -z "$final_status" ]; then
    fail_test "Render did not reach terminal state within ${MAX_RENDER_WAIT}s (last: ${current_status})"
else
    fail_test "Render ended with unexpected status: ${final_status}"
fi

# -----------------------------------------------------------------------
# 5. Verify output path is populated on success
# -----------------------------------------------------------------------
if [ "$final_status" = "succeeded" ]; then
    output_url=$(echo "$poll_response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('url',''))" 2>/dev/null || echo "")
    if [ -n "$output_url" ]; then
        pass_test "Output URL populated: ${output_url}"
    else
        fail_test "Render succeeded but output URL is empty"
    fi
fi

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
echo ""
echo "======================================="
echo "  SMOKE TEST SUMMARY"
echo "======================================="
echo "  Tests run: ${TESTS_RUN}"
echo "  Passed:    ${PASS}"
echo "  Failed:    ${FAIL}"
echo "======================================="

if [ "$FAIL" -gt 0 ]; then
    echo "  RESULT: FAIL"
    echo "======================================="
    exit 1
else
    echo "  RESULT: PASS"
    echo "======================================="
    exit 0
fi
