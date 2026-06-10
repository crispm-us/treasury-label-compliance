#!/usr/bin/env bash
# smoke-test.sh — end-to-end API smoke tests against a running local server.
#
# Usage:
#   uv run uvicorn backend.app.main:app --reload   # terminal 1
#   bash scripts/smoke-test.sh                     # terminal 2
#
# Optional overrides:
#   BASE_URL=https://your-railway-url API_KEY=secret bash scripts/smoke-test.sh

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-}"
PASS=0
FAIL=0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

green()  { printf '\033[32m%s\033[0m\n' "$*"; }
red()    { printf '\033[31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

auth_header() {
    if [[ -n "$API_KEY" ]]; then
        echo "-H" "X-API-Key: ${API_KEY}"
    fi
}

# check <description> <expected_http_status> <expected_verdict_or_-> [curl args...]
check() {
    local desc="$1"
    local want_status="$2"
    local want_verdict="$3"
    shift 3

    local response http_status body verdict

    response=$(curl -s -w '\n__STATUS__%{http_code}' \
        $(auth_header) \
        "$@" 2>&1)

    http_status=$(printf '%s' "$response" | grep '__STATUS__' | sed 's/__STATUS__//')
    body=$(printf '%s' "$response" | grep -v '__STATUS__')

    if [[ "$http_status" != "$want_status" ]]; then
        red "FAIL  $desc"
        red "      HTTP $http_status (expected $want_status)"
        printf '%s\n' "$body" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$body"
        (( FAIL++ ))
        return
    fi

    if [[ "$want_verdict" != "-" ]]; then
        verdict=$(printf '%s' "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('verdict',''))" 2>/dev/null || echo "")
        if [[ "$verdict" != "$want_verdict" ]]; then
            red "FAIL  $desc"
            red "      verdict=${verdict} (expected ${want_verdict})"
            printf '%s\n' "$body" | python3 -m json.tool 2>/dev/null || printf '%s\n' "$body"
            (( FAIL++ ))
            return
        fi
    fi

    green "PASS  $desc"
    (( PASS++ ))
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

printf '\n%s\n' "=== TTB Label Compliance smoke tests → ${BASE_URL} ==="
echo

# Health
check "GET /healthz returns 200" \
    200 - \
    -X GET "${BASE_URL}/healthz"

# Beer — single panel (GWS on back only → NONCOMPLIANT)
check "Beer single panel → NONCOMPLIANT (GWS on back, not submitted)" \
    200 NONCOMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/prairie-creek-lager-front.jpg"

# Beer — two panels (GWS found on back → UNVERIFIABLE, ABV missing)
check "Beer two panels → UNVERIFIABLE (GWS resolved, ABV absent)" \
    200 UNVERIFIABLE \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/beer/prairie-creek-lager-front.jpg" \
    -F "back=@test-labels/beer/prairie-creek-lager-back.jpg"

# Spirits — two panels (expect COMPLIANT)
check "Spirits two panels → COMPLIANT" \
    200 COMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/spirits/blue-ridge-rye-front.jpg" \
    -F "back=@test-labels/spirits/blue-ridge-rye-back.jpg"

# Wine — two panels (expect COMPLIANT)
check "Wine two panels → COMPLIANT" \
    200 COMPLIANT \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@test-labels/wine/silverleaf-chardonnay-front.jpg" \
    -F "back=@test-labels/wine/silverleaf-chardonnay-back.jpg"

# Input validation — unsupported MIME type → 415
check "Unsupported Content-Type → 415" \
    415 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@docs/rules/beer-malt.md;type=application/pdf"

# Input validation — valid Content-Type but wrong magic bytes → 415
check "Valid Content-Type, wrong magic bytes → 415" \
    415 - \
    -X POST "${BASE_URL}/v1/check" \
    -F "front=@docs/rules/beer-malt.md;type=image/jpeg"

# Auth — if API_KEY is set, missing header should return 401
if [[ -n "$API_KEY" ]]; then
    check "Missing X-API-Key → 401" \
        401 - \
        -X POST "${BASE_URL}/v1/check" \
        -F "front=@test-labels/beer/prairie-creek-lager-front.jpg"
        # intentionally no auth_header here
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo
total=$(( PASS + FAIL ))
if [[ $FAIL -eq 0 ]]; then
    green "All ${total} tests passed."
else
    red "${FAIL} of ${total} tests FAILED."
    exit 1
fi
