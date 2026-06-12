#!/usr/bin/env bash
# Mode A smoke test — full batch, post-prompt LBL-AUD-0612
# Run from: ~/Projects/treasury-label-compliance
# Requires: server on port 8000, API_KEY env var set
#
# Usage:
#   chmod +x test-labels/mode-a-smoke-batch.sh
#   ./test-labels/mode-a-smoke-batch.sh 2>&1 | tee /tmp/mode-a-batch.json
#
# Expected outcomes per case are noted in the header lines.
# Key: ✓ = designed violation expected to fire
#      FP = known false positive (documented limitation)
#      ? = uncertain post-prompt

set -euo pipefail

BASE="http://localhost:8000/v1/check"
APPS="test-labels/applications"
BEER="test-labels/beer"
SPIRITS="test-labels/spirits"
WINE="test-labels/wine"

# Strip _comment from stub JSON before posting
app_json() {
  python3 -c "import json; d=json.load(open('$1')); d.pop('_comment',''); print(json.dumps(d))"
}

run_check() {
  local label="$1"
  local app_file="$2"
  local front="$3"
  local back="$4"

  echo ""
  echo "══════════════════════════════════════════════════════"
  printf "  %s\n" "$label"
  echo "══════════════════════════════════════════════════════"

  curl -s -X POST "$BASE" \
    -H "X-API-Key: $API_KEY" \
    -F "front=@${front}" \
    -F "back=@${back}" \
    -F "application=$(app_json "$app_file")" \
    | python3 -m json.tool
}

# ── BEER ──────────────────────────────────────────────────────────────────────

run_check \
  "1/12  Harbor Bay — Mode A COMPLIANT
         expect: NONCOMPLIANT; R-APP-01 FP ('HARBOR BAY' not 'Harbor Bay Lager')
                 R-APP-05 should be CLEAR (stub='American', model reads from face)" \
  "$APPS/harbor-bay-lager-synth-mode-a-compliant.json" \
  "$BEER/harbor-bay-lager-synth-mode-a-compliant-front.jpg" \
  "$BEER/harbor-bay-lager-synth-mode-a-compliant-back.jpg"

run_check \
  "2/12  Harbor Bay — R-APP-01 (brand mismatch)
         expect: NONCOMPLIANT; R-APP-01 ✓ (wrong brand on image)" \
  "$APPS/harbor-bay-lager-synth-mode-a-R-APP-01.json" \
  "$BEER/harbor-bay-lager-synth-mode-a-R-APP-01-front.jpg" \
  "$BEER/harbor-bay-lager-synth-mode-a-R-APP-01-back.jpg"

run_check \
  "3/12  Harbor Bay — R-APP-02 (ABV mismatch)
         expect: NONCOMPLIANT; R-APP-02 ✓ (image ABV ~5.8% vs declared 5.0%)" \
  "$APPS/harbor-bay-lager-synth-mode-a-R-APP-02.json" \
  "$BEER/harbor-bay-lager-synth-mode-a-R-APP-02-front.jpg" \
  "$BEER/harbor-bay-lager-synth-mode-a-R-APP-02-back.jpg"

# ── SPIRITS ───────────────────────────────────────────────────────────────────

run_check \
  "4/12  Canyon Ridge — Mode A COMPLIANT
         expect: NONCOMPLIANT; R-APP-01 FP ('CANYON RIDGE' not 'Canyon Ridge Bourbon')
                 R-APP-05 should be CLEAR (stub='Kentucky', model reads from face)" \
  "$APPS/canyon-ridge-bourbon-synth-mode-a-compliant.json" \
  "$SPIRITS/canyon-ridge-bourbon-synth-mode-a-compliant-front.jpg" \
  "$SPIRITS/canyon-ridge-bourbon-synth-mode-a-compliant-back.jpg"

run_check \
  "5/12  Canyon Ridge — R-APP-04 (net contents mismatch: 1.0 L vs 750 mL)
         expect: NONCOMPLIANT; R-APP-04 ✓ (if model finds net contents on image)
                 known miss risk: net_contents not_found → R-APP-04 skipped" \
  "$APPS/canyon-ridge-bourbon-synth-mode-a-R-APP-04.json" \
  "$SPIRITS/canyon-ridge-bourbon-synth-mode-a-R-APP-04-front.jpg" \
  "$SPIRITS/canyon-ridge-bourbon-synth-mode-a-R-APP-04-back.jpg"

run_check \
  "6/12  Canyon Ridge — R-APP-01+02 (brand + ABV both wrong)
         expect: NONCOMPLIANT; R-APP-01 ✓, R-APP-02 ✓
                 R-APP-05 should be CLEAR" \
  "$APPS/canyon-ridge-bourbon-synth-mode-a-R-APP-01-02.json" \
  "$SPIRITS/canyon-ridge-bourbon-synth-mode-a-R-APP-01-02-front.jpg" \
  "$SPIRITS/canyon-ridge-bourbon-synth-mode-a-R-APP-01-02-back.jpg"

run_check \
  "7/12  Tito's Vodka (real label)
         expect: R-APP-05 CLEAR (stub='American', matches label face)
                 R-APP-01 ? ('Tito's' vs 'Tito's Handmade Vodka')
                 R-APP-04 ? ('1L' vs '1 L' — net_contents normalization)" \
  "$APPS/titos-vodka.json" \
  "$SPIRITS/titos-vodka-front.jpg" \
  "$SPIRITS/titos-vodka-back.jpg"

# ── WINE ──────────────────────────────────────────────────────────────────────

run_check \
  "8/12  Mesa Verde — Mode A COMPLIANT
         expect: NONCOMPLIANT; R-APP-01 FP (entity name vs brand)
                 R-APP-05 FP (model reads 'USA' from address — wine origin broken)" \
  "$APPS/mesa-verde-chardonnay-synth-mode-a-compliant.json" \
  "$WINE/mesa-verde-chardonnay-synth-mode-a-compliant-front.jpg" \
  "$WINE/mesa-verde-chardonnay-synth-mode-a-compliant-back.jpg"

run_check \
  "9/12  Mesa Verde — R-APP-03 (class/type: label='White Wine', declared='Chardonnay')
         expect: NONCOMPLIANT; R-APP-03 ✓; R-APP-01 FP likely" \
  "$APPS/mesa-verde-chardonnay-synth-mode-a-R-APP-03.json" \
  "$WINE/mesa-verde-chardonnay-synth-mode-a-R-APP-03-front.jpg" \
  "$WINE/mesa-verde-chardonnay-synth-mode-a-R-APP-03-back.jpg"

run_check \
  "10/12  Mesa Verde — R-APP-05 (origin: label='Sonoma County', declared='California')
          expect: NONCOMPLIANT; R-APP-05 fires but found='USA' not 'Sonoma County'
                  (designed violation fires for wrong reason — documented limitation)" \
  "$APPS/mesa-verde-chardonnay-synth-mode-a-R-APP-05.json" \
  "$WINE/mesa-verde-chardonnay-synth-mode-a-R-APP-05-front.jpg" \
  "$WINE/mesa-verde-chardonnay-synth-mode-a-R-APP-05-back.jpg"

run_check \
  "11/12  Angry Orchard Iceman (real label — hard cider)
          expect: R-GW-02 from CFR layer; Mode A R-APP-* should be largely clean
                  (cleanest Mode A real-label result pre-prompt)" \
  "$APPS/angry-orchard-iceman.json" \
  "$WINE/angry-orchard-iceman-front.jpg" \
  "$WINE/angry-orchard-iceman-back.jpg"

run_check \
  "12/12  Sierra Nevada Pale Ale (real label)
          expect: R-GW-02 from CFR layer; R-APP-01 ? (brand extraction)
                  R-APP-05 ? (stub='United States' — model may read 'United States' or abbrev)" \
  "$APPS/sierra-nevada-pale-ale.json" \
  "$BEER/sierra-nevada-pale-ale-front.jpg" \
  "$BEER/sierra-nevada-pale-ale-back.jpg"

echo ""
echo "══════════════════════════════════════════════════════"
echo "  Mode A batch complete — 12 cases"
echo "══════════════════════════════════════════════════════"
