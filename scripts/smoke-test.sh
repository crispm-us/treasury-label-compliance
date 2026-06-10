#!/usr/bin/env bash
# smoke-test.sh — end-to-end API smoke tests against a running local server.
#
# Tracks per-request timing and token usage; prints a summary at the end.
#
# Usage:
#   uv run uvicorn backend.app.main:app --reload   # terminal 1
#   bash scripts/smoke-test.sh                     # terminal 2
#
# Optional overrides:
#   BASE_URL=https://your-railway-url API_KEY=secret bash scripts/smoke-test.sh

set -uo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-}"
PASS=0
FAIL=0
TOTAL_TIME="0"
TOTAL_IN=0
TOTAL_OUT=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

green()  { printf '\033[32m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }

auth_args() {
    [[ -n "$API_KEY" ]] && printf '%s' "-H X-API-Key:${API_KEY}" || true
}

# py <expr> — evaluate a Python one-liner against $body (set before calling)
py() { printf '%s' "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null || echo ""; }

# check <description> <expected_http_status> <expected_verdict_or_-> [curl args...]
check() {
    local desc="$1"
    local want_status="$2"
    local want_verdict="$3"
    shift 3

    local response http_status time_s body verdict in_tok out_tok tok_info

    # Append timing and status to the response via -w; separate with a sentinel line
    response=$(curl -s \
        -w '\n__META__%{http_code}|%{time_total}' \
        ${API_KEY:+-H "X-API-Key:${API_KEY}"} \
        "$@" 2>&1)

    local meta_line
    meta_line=$(printf '%s' "$response" | grep '__META__' || true)
    http_status=$(printf '%s' "$meta_line" | sed 's/.*__META__//' | cut -d'|' -f1)
    time_s=$(printf '%s' "$meta_line" | sed 's/.*__META__//' | cut -d'|' -f2)
    body=$(printf '%s' "$response" | grep -v '__META__')

    # Accumulate raw time before any rounding
    TOTAL_TIME=$(python3 -c "print(${TOTAL_TIME:-0} + ${time_s:-0})" 2>/dev/null || echo "$TOTAL_TIME")
    time_s=$(printf '%.2f' "$time_s" 2>/dev/null || echo "$time_s")

    if [[ "$http_status" != "$want_status" ]]; then
        red "FAIL  $desc"
        red "      HTTP $http_status (expected $want_status)  [${time_s}s]"
        printf '%s\n' "$body" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$body"
        FAIL=$(( FAIL + 1 ))
        return
    fi

    if [[ "$want_verdict" != "-" ]]; then
        verdict=$(py "d.get('verdict','')")
        if [[ "$verdict" != "$want_verdict" ]]; then
            red "FAIL  $desc"
            red "      verdict=${verdict} (expected ${want_verdict})  [${time_s}s]"
            printf '%s\n' "$body" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$body"
            FAIL=$(( FAIL + 1 ))
            return
        fi
    fi

    # Model and token info (only present on successful extraction calls)
    model_used=$(py "d.get('extraction_model') or ''")
    in_tok=$(py  "d.get('input_tokens')  or ''")
    out_tok=$(py "d.get('output_tokens') or ''")
    if [[ -n "$in_tok" && -n "$out_tok" ]]; then
        tok_info="  ${in_tok}+${out_tok} tok"
        TOTAL_IN=$(( TOTAL_IN + in_tok ))
        TOTAL_OUT=$(( TOTAL_OUT + out_tok ))
    else
        tok_info=""
    fi
    model_info=""
    [[ -n "$model_used" ]] && model_info="  ${model_used}"

    green "PASS  $desc  [${time_s}s${model_info}${tok_info}]"
    PASS=$(( PASS + 1 ))
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

printf '\n%s\n' "=== TTB Label Compliance smoke tests → ${BASE_URL} ==="
echo

check "GET /healthz returns 200" \
    200 - \
    -X GET "${BASE_URL}/healthz"

check "Beer single panel → NONCOMPLIANT (GWS on back, not submitted)" \
    200 NONCOMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/prairie-creek-lager-front.jpg"

check "Beer two panels → UNVERIFIABLE (GWS resolved, ABV absent)" \
    200 UNVERIFIABLE \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/prairie-creek-lager-front.jpg" \
    -F "back=@test-labels/beer/prairie-creek-lager-back.jpg"

check "Spirits two panels → COMPLIANT" \
    200 COMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/spirits/blue-ridge-rye-front.jpg" \
    -F "back=@test-labels/spirits/blue-ridge-rye-back.jpg"

check "Wine two panels → COMPLIANT" \
    200 COMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/wine/silverleaf-chardonnay-front.jpg" \
    -F "back=@test-labels/wine/silverleaf-chardonnay-back.jpg"

check "Unsupported Content-Type → 415" \
    415 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@docs/rules/beer-malt.md;type=application/pdf"

check "Valid Content-Type, wrong magic bytes → 415" \
    415 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@docs/rules/beer-malt.md;type=image/jpeg"

if [[ -n "$API_KEY" ]]; then
    # Override auth_args for this one test — intentionally send no key
    response=$(curl -s \
        -w '\n__META__%{http_code}|%{time_total}' \
        -X POST "${BASE_URL}/v1/check" \
        -F "front=@test-labels/beer/prairie-creek-lager-front.jpg" 2>&1)
    meta_line=$(printf '%s' "$response" | grep '__META__' || true)
    http_status=$(printf '%s' "$meta_line" | sed 's/.*__META__//' | cut -d'|' -f1)
    time_s=$(printf '%s' "$meta_line" | sed 's/.*__META__//' | cut -d'|' -f2)
    TOTAL_TIME=$(python3 -c "print(${TOTAL_TIME:-0} + ${time_s:-0})" 2>/dev/null || echo "$TOTAL_TIME")
    time_s=$(printf '%.2f' "$time_s" 2>/dev/null || echo "$time_s")
    if [[ "$http_status" == "401" ]]; then
        green "PASS  Missing X-API-Key → 401  [${time_s}s]"
        PASS=$(( PASS + 1 ))
    else
        red "FAIL  Missing X-API-Key — got HTTP $http_status (expected 401)"
        FAIL=$(( FAIL + 1 ))
    fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo
total=$(( PASS + FAIL ))
total_tok=$(( TOTAL_IN + TOTAL_OUT ))

if [[ $FAIL -eq 0 ]]; then
    green "All ${total} tests passed."
else
    red "${FAIL} of ${total} tests FAILED."
fi

printf 'Time:   %ss total\n' "$(printf '%.2f' "$TOTAL_TIME" 2>/dev/null || echo "$TOTAL_TIME")"
if [[ $total_tok -gt 0 ]]; then
    printf 'Tokens: %s in + %s out = %s total\n' "$TOTAL_IN" "$TOTAL_OUT" "$total_tok"
fi

[[ $FAIL -eq 0 ]] || exit 1
