#!/usr/bin/env bash
# benchmark-latency.sh — measure extraction latency per model
#
# Starts and stops a dedicated uvicorn instance for each model so results are
# isolated. Run from the repo root. Requires uv and the test-labels directory.
#
# Usage:
#   ./scripts/benchmark-latency.sh                        # defaults: 3 runs, Gemini + Haiku
#   ./scripts/benchmark-latency.sh -n 5                   # 5 runs, default models
#   ./scripts/benchmark-latency.sh -n 3 openai/gpt-5.4-nano
#   ./scripts/benchmark-latency.sh -n 5 gemini/gemini-2.5-flash-lite anthropic/claude-haiku-4-5-20251001 openai/gpt-5.4-nano

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
RUNS=3
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

    # wait up to 10s for the server to accept connections
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
        SERVER_PID=""
    fi
}

# ── Timing helpers ────────────────────────────────────────────────────────────
# Runs RUNS requests, prints per-run timing + verdict, prints avg at the end.
run_scenario() {
    local label="$1"; shift
    local form_args=("$@")
    local tmpfile times=() total=0 errors=0

    printf "  %-28s" "$label"
    printf "\n"

    tmpfile=$(mktemp)
    for (( i=1; i<=RUNS; i++ )); do
        t=$(curl -s -o "$tmpfile" -X POST "${BASE_URL}/v1/check" \
            "${form_args[@]}" \
            --write-out "%{time_total}")
        verdict=$(python3 -c \
            "import sys,json; print(json.load(open('$tmpfile')).get('verdict','?'))" \
            2>/dev/null || echo "?")
        [[ "$verdict" == "ERROR" ]] && (( errors++ )) || true
        times+=("$t")
        if [[ "$verdict" == "ERROR" ]]; then
            printf "    run %d: %6.3fs  ⚠  ERROR (check API key / model string)\n" "$i" "$t"
        else
            printf "    run %d: %6.3fs  [%s]\n" "$i" "$t" "$verdict"
        fi
    done
    rm -f "$tmpfile"

    # average (awk handles float arithmetic)
    avg=$(printf '%s\n' "${times[@]}" | awk '{s+=$1;c++} END{printf "%.3f",s/c}')
    if (( errors == RUNS )); then
        printf "    avg:  %6.3fs  ⚠  all runs returned ERROR\n\n" "$avg"
    else
        printf "    avg:  %6.3fs\n\n" "$avg"
    fi
}

# ── Pre-flight checks ─────────────────────────────────────────────────────────
for f in "$SINGLE_IMAGE" "$FRONT_IMAGE" "$BACK_IMAGE"; do
    if [[ ! -f "$f" ]]; then
        echo "ERROR: test image not found: $f" >&2
        echo "Run this script from the repo root." >&2
        exit 1
    fi
done

# ── Main ──────────────────────────────────────────────────────────────────────
echo ""
echo "Latency benchmark — ${RUNS} runs per scenario"
echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Models: ${MODELS[*]}"
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
