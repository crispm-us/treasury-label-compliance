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

# Always run from the repo root regardless of where the script is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

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
    in_tok=$(py  "'' if d.get('input_tokens')  is None else d['input_tokens']")
    out_tok=$(py "'' if d.get('output_tokens') is None else d['output_tokens']")
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
    -F "front=@test-labels/beer/prairie-creek-lager-synth-front.jpg"

check "Beer two panels → UNVERIFIABLE (GWS resolved, ABV absent)" \
    200 UNVERIFIABLE \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/prairie-creek-lager-synth-front.jpg" \
    -F "back=@test-labels/beer/prairie-creek-lager-synth-back.jpg"

check "Spirits two panels → COMPLIANT" \
    200 COMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/spirits/blue-ridge-rye-synth-front.jpg" \
    -F "back=@test-labels/spirits/blue-ridge-rye-synth-back.jpg"

check "Wine two panels → COMPLIANT" \
    200 COMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/wine/silverleaf-chardonnay-synth-front.jpg" \
    -F "back=@test-labels/wine/silverleaf-chardonnay-synth-back.jpg"

check "Unsupported Content-Type → 415" \
    415 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@docs/rules/beer-malt.md;type=application/pdf"

check "Valid Content-Type, wrong magic bytes → 415" \
    415 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@docs/rules/beer-malt.md;type=image/jpeg"

check "HEIC image (unsupported format) → 415" \
    415 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/stiegl-radler-grapefruit-front.heic"

# Oversized test: generate a synthetic JPEG-headed file > 10 MB in-script (no stored blob).
_OVERSIZED=$(mktemp /tmp/oversized-XXXXXX.jpg)
printf '\xff\xd8\xff\xe0\x00\x10JFIF' > "$_OVERSIZED"
dd if=/dev/zero bs=1M count=11 >> "$_OVERSIZED" 2>/dev/null
check "Oversized image (11 MB) → 413" \
    413 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@${_OVERSIZED}"
rm -f "$_OVERSIZED"

# ---------------------------------------------------------------------------
# Real-label tests — make actual model API calls; not counted in synthetic totals
# ---------------------------------------------------------------------------

printf '\n%s\n\n' "--- Real-label tests (live model calls) ---"

check "Henninger real front only → 200 (UNVERIFIABLE expected — GWS on separate face)" \
    200 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/henninger-front.jpg"

check "Henninger real front + GWS face → 200 (GWS upside-down in photo — tests orientation)" \
    200 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/henninger-front.jpg" \
    -F "back=@test-labels/beer/henninger-gws.jpg"

check "Stiegl Radler real two-panel → 200 (flavored malt beverage, imported)" \
    200 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/stiegl-radler-grapefruit-front.jpg" \
    -F "back=@test-labels/beer/stiegl-radler-grapefruit-back.jpg"

# Multi-panel demonstration: front-only failure vs. front+back resolution.
# Heineken: GWS is on back panel — front-only → NONCOMPLIANT; adding back resolves it.
check "Heineken real front only → 200 (NONCOMPLIANT expected — GWS on back panel)" \
    200 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/heineken-original-front.jpg"

check "Heineken real front+back → 200 (expected COMPLIANT or UNVERIFIABLE after GWS resolved)" \
    200 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/heineken-original-front.jpg" \
    -F "back=@test-labels/beer/heineken-original-back.jpg"

# Delirium Tremens can: 3-panel cylinder — front+gws-face is the correct two-panel submission.
check "Delirium Tremens can real front+gws → 200 (3-panel; expected COMPLIANT or UNVERIFIABLE)" \
    200 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/delirium-tremens-can-front.jpg" \
    -F "back=@test-labels/beer/delirium-tremens-can-gws.jpg"

# Ron Ron Sauvignon: GWS header is in mixed case — should trigger R-GW-03 → NONCOMPLIANT.
check "Ron Ron Sauvignon real front+back → 200 (NONCOMPLIANT expected — R-GW-03 mixed-case GWS)" \
    200 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/wine/ron-ron-sauvignon-front.jpg" \
    -F "back=@test-labels/wine/ron-ron-sauvignon-back.jpg"

if [[ -n "$API_KEY" ]]; then
    # Send no key intentionally — expects 401
    response=$(curl -s \
        -w '\n__META__%{http_code}|%{time_total}' \
        -X POST "${BASE_URL}/v1/check" \
        -F "front=@test-labels/beer/prairie-creek-lager-synth-front.jpg" 2>&1)
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
else
    printf '(auth test skipped — export API_KEY=<secret> to run it)\n'
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
