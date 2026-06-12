# Deployment Checklist

Pre-flight steps before making the repository public and deploying to Railway.

---

## 1. Repository hygiene (must complete on Zulu before public push)

- [x] **Delete internal dev notes:** `git rm docs/dev-environment-notes.md`
  ✓ Done — file removed; confirmed clean via `git ls-files docs/`.

- [ ] **Handle `docs/project-log.md` before public push:**
  The file is being committed during development for personal reference. Before making the repo public, decide: (a) include it (sanitize content, then publish), or (b) strip it entirely. If stripping, a plain `git rm` is not sufficient — the file exists in prior commits. Remove it from full history with:
  ```bash
  git filter-repo --path docs/project-log.md --invert-paths
  git push --force
  ```
  `git filter-repo` must be installed (`pip install git-filter-repo` or `brew install git-filter-repo`). Run this on Zulu immediately before making the repo public, not during development.

- [x] **Verify `.gitignore` covers all sensitive paths:**
  ✓ Done — `audit_logs/`, `.env`, `.env.*` confirmed in `.gitignore`; `uv.lock` uncommented and committed.

- [x] **Commit the `uv.lock` file** for reproducible installs.
  ✓ Done — `uv.lock` committed; `.gitignore` entry uncommented.

---

## 2. Documentation (complete before public push)

- [x] **Root `README.md`** — project overview, quick-start, API reference, configuration table, limitations, smoke-test link.
- [x] **`IMPLEMENTATION_STATUS.md`** — maps each ADR to what is built vs. deferred.
- [x] **`LICENSE`** — MIT license present.

**Before each public push:** verify README test count and limitations section match current code. `IMPLEMENTATION_STATUS.md` is the authoritative scope reference; README limitations should not contradict it.

---

## 3. Railway deployment

- [x] **Set `API_KEY` in the Railway environment dashboard** before sharing the deployment URL.
  Any non-empty value requires `X-API-Key: <value>` on every `POST /v1/check` request.
  Share the key only with yourself and the hiring manager/team.
  ✓ Done — 401 returned on missing key (confirmed 2026-06-12).

- [x] **Set all provider API keys** (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) in the Railway environment dashboard.
  ✓ Done.

- [x] **Set `AUDIT_ENABLED=false`** in the Railway environment — Railway has an ephemeral filesystem; audit logs written to `audit_logs/` are lost on every redeploy.
  ✓ Done — confirmed via `healthz`: `{"status":"ok","audit_enabled":false}`.

- [x] **Set `EXTRACTION_MODEL` and `EXTRACTION_FALLBACK_MODELS`** in the Railway environment.
  ✓ Done — Flash-Lite primary, Haiku fallback-1, gpt-5.4-nano fallback-2.

- [x] **Smoke-test the live endpoint.**
  ✓ Done — see §4 below.

### Deployment record

| Field | Value |
|---|---|
| URL | `https://web-production-b6163.up.railway.app` |
| Project | `pleasant-love` / `production` |
| Python | 3.13.14 (Railway Nixpacks auto-detected) |
| Region | US West |
| Deployed | 2026-06-12 |

---

## 4. Live smoke test (run after Railway deployment)

Replace `<URL>` and `<KEY>` with the Railway URL and your `API_KEY` value.

```bash
# Health check
curl https://<URL>/healthz

# Beer label — expect COMPLIANT or NONCOMPLIANT (not ERROR)
curl -X POST https://<URL>/v1/check \
  -H "X-API-Key: <KEY>" \
  -F "front=@test-labels/beer/prairie-creek-lager-synth-front.jpg"

# Two-panel spirits — expect COMPLIANT
curl -X POST https://<URL>/v1/check \
  -H "X-API-Key: <KEY>" \
  -F "front=@test-labels/spirits/blue-ridge-rye-synth-front.jpg" \
  -F "back=@test-labels/spirits/blue-ridge-rye-synth-back.jpg"
```

### Results (2026-06-12)

| Test | Result |
|---|---|
| `GET /healthz` | `{"status":"ok","audit_enabled":false}` ✓ |
| `POST /v1/check` — no API key | 401 ✓ |
| Glenfiddich 12 two-panel (spirits) | UNVERIFIABLE — R-GW-02 warning (rotated GWS; expected) ✓ |

---

## 5. Smoke-test coverage gaps (address before Railway deployment)

- [ ] **WebP upload smoke test** — add a `check` call using a `.webp` test label to confirm the WebP magic-byte path works end-to-end. The upload validation accepts WebP but no smoke test exercises it.

- [ ] **413 oversized file smoke test** — add a `check` call with a temp file exceeding 10 MB to confirm the size limit returns 413 from the live endpoint. Unit tests cover this path; a live check confirms Railway's request size config doesn't interfere.

---

## 6. Real label testing (complete before submitting to interviewers)

Synthetic labels are sufficient for demonstrating the architecture, but real label scans reveal edge cases (model hallucinations, OCR ambiguity, non-standard layouts). Real label images live in `test-labels/`.

### Front/back convention for real photographs

"Front" and "back" are semantic submission slots, not geometric labels. The merger is panel-agnostic — which face goes in which slot does not affect the outcome. Practical guidance:

- **Front:** the face with the brand name and class/type designation.
- **Back:** the face with the most compliance-critical text not already on the front — typically the Government Warning Statement plus bottler/importer name and address.
- If those are on separate faces (e.g. a cylindrical can where the GWS is on a narrow end panel), prefer the GWS face as "back" — that is the highest-stakes compliance content.

**Type (i) — manufacturer-supplied flat images** (our synthetic labels, or a scanned flat label sheet): the convention maps cleanly. Two panels cover 100% of the label content.

**Type (ii) — real photographs of bottles or cans:** works well for standard two-face layouts (most wine/spirits bottles; most US beer cans). Edge cases:

- *Three-face cylindrical cans* (e.g. Henninger, where the GWS is on the end panel): a two-panel submission must choose two of three faces. The missed face produces not_found warnings → UNVERIFIABLE rather than a false NONCOMPLIANT.
- *Upside-down or rotated photos:* the vision model handles orientation — the Henninger GWS images are upside-down in the photo and still readable.
- *Extreme angles, glare, heavy curvature:* produce low-confidence or not_found results → UNVERIFIABLE rather than a false verdict.

### Available real label pairs

#### Spirits

| Product | Front | Back | Notes |
|---|---|---|---|
| Tito's Handmade Vodka (domestic TX, 1L) | `spirits/titos-vodka-front.jpg` | `spirits/titos-vodka-back.jpg` | GWS present on back ✓; 80 Proof / 40% ABV; Distilled from corn |
| Jack Daniel's Old No. 7 — **EU market 70cl** *(front only)* | `spirits/jack-daniels-old-no-7-eu-front.jpg` | — | ⚠ Non-US label: "70cl 40% Vol." format, no GWS; standalone front-only test — verifies checker handles European labels gracefully |
| Jack Daniel's Old No. 7 (domestic TN) | `spirits/jack-daniels-old-no-7-front.jpg` | `spirits/jack-daniels-old-no-7-back.jpg` | 200 ml miniature (front) / 750 ml (back) — different sizes photographed; no GWS visible on either panel |
| Glenfiddich 12 Year Old (imported Scotch, 750ml) | `spirits/glenfiddich-12-front.jpg` | `spirits/glenfiddich-12-back.jpg` | GWS present on back ✓ — rotated 90°; imported by William Grant & Sons, Inc. |
| The Glenlivet 12 Years of Age (imported Scotch, 750ml) | `spirits/glenlivet-12-front.jpg` | `spirits/glenlivet-12-back.jpg` | GWS present on back ✓ — rotated 90°; front shows 40% ABV + 80 Proof; imported by The Glenlivet Distilling Company, NY |

#### Beer

| Product | Front | Back/GWS | Notes |
|---|---|---|---|
| Henninger Lager (imported DE) | `beer/henninger-front.jpg` | `beer/henninger-gws.jpg` | GWS face upside-down in photo; importer info on a third face (`henninger-back.jpg`) |
| Stiegl Radler Grapefruit (malt bev., imported AT) | `beer/stiegl-radler-grapefruit-front.jpg` | `beer/stiegl-radler-grapefruit-back.jpg` | 2.5% ABV; full importer address on back |
| Budweiser (domestic) | `beer/budweiser-front.jpg` | `beer/budweiser-back.jpg` | GWS on side/back panel |
| Delirium Tremens bottle (imported BE, 8.5% ABV) | `beer/delirium-tremens-bottle-front.jpg` | `beer/delirium-tremens-bottle-back.jpg` | BBL Inc, Frederick MD; imported |
| Delirium Tremens can (imported BE, 8.5% ABV) | `beer/delirium-tremens-can-front.jpg` | `beer/delirium-tremens-can-gws.jpg` | 3-panel cylinder; also `delirium-tremens-can-side.jpg` (ABV + net contents) |
| Heineken Original (imported NL) | `beer/heineken-original-front.jpg` | `beer/heineken-original-back.jpg` | Standard two-panel |
| Sierra Nevada Pale Ale (domestic) | `beer/sierra-nevada-pale-ale-front.jpg` | `beer/sierra-nevada-pale-ale-back.jpg` | Standard two-panel |
| Mike's Harder Lemonade — Deadpool 2 Ltd. Ed. (domestic) | `beer/mikes-harder-lemonade-front.jpg` | `beer/mikes-harder-lemonade-back.jpg` | Flavored malt beverage; 8% ABV; GWS vertical on back |

**HEIC rejection test:** `beer/stiegl-radler-grapefruit-front.heic` — submit to verify 415 is returned for iPhone HEIC uploads.

The smoke test (`scripts/smoke-test.sh`) includes real-label calls for Henninger, Stiegl, Heineken, Ron Ron, and Delirium Tremens can.

#### Wine

| Product | Front | Back | Notes |
|---|---|---|---|
| Auchere Sancerre 2024 (imported FR) | `wine/auchere-sancerre-front.jpg` | `wine/auchere-sancerre-back.jpg` | Importer: Planet Wine Inc |
| Baci di Sangiovese 2020, Toscana IGT (imported IT) | `wine/baci-di-sangiovese-front.jpg` | `wine/baci-di-sangiovese-back.jpg` | Importer: Planet Wine Inc |
| Brumes de La Tour Blanche 2021 Sauternes (imported FR) | `wine/brumes-tour-blanche-front.jpg` | `wine/brumes-tour-blanche-back-a.jpg` | 4 shots; `-back-c.jpg` explicitly shows `375 ml` net contents |
| Loic Bulliat Bibine 2023, Beaujolais-Villages (imported FR) | `wine/bulliat-bibine-front.jpg` | `wine/bulliat-bibine-back.jpg` | Standard two-panel |
| The "Ron Ron" Sauvignon 2023, Loire Valley (imported FR) | `wine/ron-ron-sauvignon-front.jpg` | `wine/ron-ron-sauvignon-back.jpg` | ⚠ GWS header in mixed case — R-GW-03 candidate |
| Angry Orchard Iceman Hard Cider (domestic, 10% ABV) | `wine/angry-orchard-iceman-front.jpg` | `wine/angry-orchard-iceman-back.jpg` | Wine category (apple juice concentrate); CONTAINS SULFITES on label; GWS present on back ✓ |

### Multi-panel test matrix

For each product below, the "front-only" submission exercises the path where compliance-critical content (typically the GWS) is absent from the submitted panel; the "front+back" submission is the expected success path. Verdicts marked ✓ are confirmed from a smoke-test run against Gemini Flash Lite (2026-06-11). `unverified*` entries have not been tested against a live model.

| Product | Front-only | Front+back | Notes |
|---|---|---|---|
| **Synthetic labels** | | | |
| Copper Creek Merlot synth (R-WN-09) | — | **COMPLIANT** ✓ | R-WN-09 is warning-only (cannot verify SO₂ level from image); COMPLIANT is correct; schema_violations=9 — notable: high violations but verdict unaffected |
| Silverleaf Chardonnay synth (compliant baseline) | — | **COMPLIANT** ✓ | schema_violations=0 — cleanest extraction in corpus |
| Blue Ridge Rye synth (compliant baseline, reversed panels) | — | **COMPLIANT** ✓ | Panels submitted reversed (back→front slot); schema_violations=11; merge correctly handles wrong slot |
| **Real labels — spirits** | | | |
| Tito's Vodka | NONCOMPLIANT ✓ (R-GW-01, R-DS-04, R-DS-03) | **COMPLIANT** ✓ | GWS on back correctly found; schema_violations=4 (compliant verdict despite violations) |
| JD Old No. 7 EU 70cl | NONCOMPLIANT ✓ (R-GW-01) | — (front only) | Non-US label; no GWS |
| Jack Daniel's Old No. 7 | NONCOMPLIANT ✓ (R-GW-01) | NONCOMPLIANT ✓ (R-GW-01) | ⚠ No GWS visible in either photo — needs a third shot |
| Glenfiddich 12 | NONCOMPLIANT (predicted) | **COMPLIANT** ✓ | GWS on back rotated 90°; EXIF correction allows verbatim body match; ⚠ Inconsistent across runs — prior API run gave NONCOMPLIANT (R-GW-02); reversed-panel submission (back→front slot) → NONCOMPLIANT (R-GW-02) — panel slot affects extraction of rotated images |
| Glenlivet 12 | NONCOMPLIANT (predicted) | UNVERIFIABLE ✓ | GWS rotated 90°; low-confidence reads → all warnings → UNVERIFIABLE; specific warnings vary by run (R-GW-02/03, R-DS-06) — schema_violations=7 observed; verdict UNVERIFIABLE is stable across runs |
| **Real labels — beer** | | | |
| Henninger Lager | NONCOMPLIANT ✓ (R-GW-01, R-MB-04, R-MB-05 ×2) | UNVERIFIABLE ✓ (R-MB-04, R-MB-05 ×2) | Submitted as front+GWS; GWS found ✓; net contents and bottler info on third (importer) face |
| Stiegl Radler | NONCOMPLIANT (predicted) | **COMPLIANT** ✓ | ⚠ Previous prediction was UNVERIFIABLE — model finds 2.5% ABV on label; actual COMPLIANT |
| Budweiser | NONCOMPLIANT (predicted) | UNVERIFIABLE ✓ (R-MB-04) | ⚠ Panels submitted in reversed order (intentional test of panel-agnostic merge) — net contents not visible on either panel |
| Delirium Tremens bottle | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02, R-MB-04) | R-GW-02 body mismatch; schema_violations=8 (model returned 8 bare primitives — notable quality signal) |
| Delirium Tremens can | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02) | Submitted as front+GWS; GWS body text on can fails verbatim check |
| Heineken Original | NONCOMPLIANT ✓ (R-GW-01, R-MB-04, R-MB-05 ×2) | **COMPLIANT** ✓ | |
| Sierra Nevada Pale Ale | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02) | partial_verification; R-MB-04 + R-MB-03 warnings (net contents + ABV not visible); schema_violations=0 |
| **Real labels — wine** | | | |
| Auchere Sancerre | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02, R-WN-05 ×2) | GWS body mismatch; bottler name+address not visible in photos |
| Baci di Sangiovese | NONCOMPLIANT (predicted) | **COMPLIANT** ✓ | ⚠ Unexpected — predicted NONCOMPLIANT; model reads GWS and all required fields correctly; schema_violations=0 |
| Brumes Tour Blanche | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02, partial) | Three back panels tested: back-a → NONCOMPLIANT (R-GW-02 error, R-WN-04 warning, schema_violations=13); back-b → UNVERIFIABLE (R-WN-04 + R-WN-05 warnings, schema_violations=13); back-c → NONCOMPLIANT (R-GW-03 error, R-GW-02 + R-WN-03 warnings, schema_violations=5); GWS body mismatch consistent across panels |
| Bulliat Bibine | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-03) | GWS header not all-caps — mixed case on this French import label |
| Ron Ron Sauvignon | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-03, R-GW-02) | GWS header mixed-case + body mismatch |
| Angry Orchard Iceman | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02) | Wine category; R-GW-03 observed in prior run — model stochastic on header; schema_violations=11 |
| Mike's Harder Lemonade | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-03, R-GW-02) | GWS header missing colon; body mismatch; also: model hallucinated abv_pct=5.0 (label says 8%) |

`unverified*` — not yet run through `smoke-test.sh`; add to script and re-run to confirm.

### To-do before interviewer submission

- [x] Run Henninger front + GWS smoke test — UNVERIFIABLE; GWS found ✓; net contents/bottler on third face
- [x] Run Stiegl two-panel smoke test — COMPLIANT ✓ (model finds 2.5% ABV; earlier UNVERIFIABLE prediction was wrong)
- [x] Run spirits real-label smoke tests — Tito's front+back COMPLIANT ✓; JD front+back NONCOMPLIANT (R-GW-01); Glenfiddich NONCOMPLIANT (R-GW-02); Glenlivet UNVERIFIABLE (low-confidence GWS read, rotated 90°)
- [x] Run remaining `unverified*` rows — Budweiser, Delirium Tremens bottle, Auchere Sancerre, Bulliat Bibine confirmed (2026-06-12 via web UI)
- [x] Run remaining `unverified*` rows: Sierra Nevada, Baci di Sangiovese, Brumes Tour Blanche confirmed (2026-06-12 via web UI) — all unverified* rows complete
- [ ] Photograph GWS panel for Jack Daniel's — neither current image captures it
- [ ] Document smoke-test results and model anomalies (Mike's Harder abv_pct hallucination, Glenlivet UNVERIFIABLE) in `docs/project-log.md`

---

## 7. Interview submission notes

- `docs/project-log.md` (sanitized) — shows design thinking, iteration, and debugging process.
- `docs/adr/` — shows architectural decision-making with explicit trade-off reasoning.
- `IMPLEMENTATION_STATUS.md` — honest scoping: what is built vs. deliberately deferred.
- The two-layer architecture (AI extraction + deterministic checker) is the core design insight worth explaining in the interview.
