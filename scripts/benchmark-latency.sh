#!/usr/bin/env bash
# benchmark-latency.sh — measure extraction latency per model
#
# Starts and stops a dedicated uvicorn instance for each model so results are
# isolated. Requires uv and the test-labels directory.
#
# Usage:
#   ./scripts/benchmark-latency.sh                        # defaults: 3 runs, Gemini + Haiku
#   ./scripts/benchmark-latency.sh -n 5                   # 5 runs, default models
#   ./scripts/benchmark-latency.sh -n 3 openai/gpt-5.4-nano
#   ./scripts/benchmark-latency.sh -n 5 \
#       gemini/gemini-2.5-flash-lite \
#       anthropic/claude-haiku-4-5-20251001 \
#       openai/gpt-5.4-nano
#
# Optional overrides (match smoke-test.sh convention):
#   API_KEY=secret ./scripts/benchmark-latency.sh

set -euo pipefail

# Always run from the repo root regardless of invocation location.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

# ── Defaults ──────────────────────────────────────────────────────────────────
RUNS=3
API_KEY="${API_KEY:-}"
DEFAULT_MODELS=(
    "gemini/gemini-2.5-flash-lite"
    "anthropic/claude-haiku-4-5-20251001"
)
PORT=8099  # dedicated port — does not collide with the normal dev server on 8000
BASE_URL="http://localhost:${PORT}"

SINGLE_IMAGE="test-labels/beer/prairie-creek-lager-front.jpg"
FRONT_IMAGE="test-labels/spirits/blue-ridge-rye-front.jpg"
BACK_IMAGE="test-labels/spirits/blue-ridge-rye-back.jpg"

# ── Argument parsing ──────────────────────────────────────────────────────────
while getopts "n:" opt; do
    case $opt in
        n) RUNS="$OPTARG" ;;
        *) echo "Usage: $0 [-n RUNS] [model1 model2 ...]"; exit 1 ;;
    esac
done
shift $((OPTIND - 1))

# Validate RUNS is a positive integer
[[ "$RUNS" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: -n must be a positive integer (got: $RUNS)" >&2
    exit 1
}

if [[ $# -gt 0 ]]; then
    MODELS=("$@")
else
    MODELS=("${DEFAULT_MODELS[@]}")
fi

# ── Server lifecycle ──────────────────────────────────────────────────────────
SERVER_PID=""

cleanup() {
    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

start_server() {
    local model="$1"
    EXTRACTION_MODEL="$model" \
    EXTRACTION_FALLBACK_MODELS="" \
    AUDIT_ENABLED=false \
        uv run uvicorn backend.app.main:app --port "$PORT" --log-level error \
        > /tmp/benchmark-uvicorn.log 2>&1 &
    SERVER_PID=$!

    # Wait up to 10s for the server to accept connections.
    local retries=20
    while (( retries-- > 0 )); do
        curl -sf "${BASE_URL}/healthz" >/dev/null 2>&1 && return 0
        sleep 0.5
    done
    echo "  ERROR: server did not start within 10s — check /tmp/benchmark-uvicorn.log" >&2
    return 1
}

stop_server() {
    if [[ -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        sleep 0.3   # brief grace period so the port is released before the next model's server starts
        SERVER_PID=""
    fi
}

# ── Helpers ───────────────────────────────────────────────────────────────────
# Extract a Python expression from a JSON response file.
py_field() { python3 -c "import json; d=json.load(open('$1')); print($2)" 2>/dev/null || echo "?"; }

# ── Scenario runner ───────────────────────────────────────────────────────────
# Runs one untimed warm-up then RUNS timed requests.
# Reports per-run timing, verdict, token counts, and an average over successful (HTTP 200, verdict≠ERROR) runs only.
run_scenario() {
    local label="$1"; shift
    local form_args=("$@")
    local tmpfile times=() bad_runs=0

    printf "  %s\n" "$label"
    tmpfile=$(mktemp)

    # Warm-up: one untimed request to prime the provider connection and any caches.
    # Aligns with the "warm batch" numbers in docs/latency-benchmarks.md.
    if ! curl -s -o /dev/null \
        ${API_KEY:+-H "X-API-Key:${API_KEY}"} \
        -X POST "${BASE_URL}/v1/check" \
        "${form_args[@]}" >/dev/null 2>&1; then
        printf "    ⚠  warm-up request failed — run 1 may reflect cold-start latency\n"
    fi

    for (( i=1; i<=RUNS; i++ )); do
        # Body goes to tmpfile; http_code|time_total is captured from --write-out.
        meta=$(curl -s -o "$tmpfile" \
            ${API_KEY:+-H "X-API-Key:${API_KEY}"} \
            -X POST "${BASE_URL}/v1/check" \
            "${form_args[@]}" \
            --write-out '%{http_code}|%{time_total}')
        http_status="${meta%|*}"
        t="${meta#*|}"

        if [[ "$http_status" != "200" ]]; then
            (( bad_runs++ )) || true
            printf "    run %d: %6.3fs  ✗ HTTP %s" "$i" "$t" "$http_status"
            [[ "$http_status" == "401" ]] && printf "  (set API_KEY=<key> to authenticate)"
            printf "\n"
            continue
        fi

        verdict=$(py_field "$tmpfile" "d.get('verdict','?')")
        in_tok=$(py_field "$tmpfile" "d.get('input_tokens','')")
        out_tok=$(py_field "$tmpfile" "d.get('output_tokens','')")
        tok_info=""
        [[ -n "$in_tok" && "$in_tok" != "?" && -n "$out_tok" && "$out_tok" != "?" ]] \
            && tok_info="  ${in_tok}+${out_tok} tok"

        if [[ "$verdict" == "ERROR" ]]; then
            (( bad_runs++ )) || true
            # Excluded from avg — ERROR indicates model/key failure, not representative latency.
            printf "    run %d: %6.3fs  ⚠  verdict=ERROR (check model string / API key)\n" "$i" "$t"
        else
            times+=("$t")
            printf "    run %d: %6.3fs  [%s]%s\n" "$i" "$t" "$verdict" "$tok_info"
        fi
    done
    rm -f "$tmpfile"

    if [[ ${#times[@]} -eq 0 ]]; then
        printf "    avg:  —  (no successful runs — all returned non-200 or verdict=ERROR)\n\n"
        return
    fi

    avg=$(printf '%s\n' "${times[@]}" | awk '{s+=$1;c++} END{printf "%.3f",s/c}')
    note=""
    (( bad_runs > 0 )) && note="  ⚠ ${bad_runs} failed run(s) excluded from avg" || true
    printf "    avg:  %6.3fs%s\n\n" "$avg" "$note"
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────
for f in "$SINGLE_IMAGE" "$FRONT_IMAGE" "$BACK_IMAGE"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: test image not found: $f" >&2
        exit 1
    fi
done

# ── Main ──────────────────────────────────────────────────────────────────────
echo ""
echo "Latency benchmark — ${RUNS} timed run(s) per scenario + 1 warm-up"
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Models: ${MODELS[*]}"
[[ -n "$API_KEY" ]] && echo "Auth:   X-API-Key header set" || true
echo "════════════════════════════════════════════════════════════"

for model in "${MODELS[@]}"; do
    echo ""
    echo "▶ ${model}"
    echo "────────────────────────────────────────────────────────────"

    if ! start_server "$model"; then
        echo "  Skipping (server failed to start)" >&2
        stop_server
        continue
    fi

    run_scenario "single panel (beer front)" \
        -F "front=@${SINGLE_IMAGE}"

    run_scenario "two panel (spirits front + back)" \
        -F "front=@${FRONT_IMAGE}" \
        -F "back=@${BACK_IMAGE}"

    stop_server
done

echo "════════════════════════════════════════════════════════════"
echo ""
echo "To add a model:  ./scripts/benchmark-latency.sh -n ${RUNS} openai/gpt-5.4-nano"
echo ""
