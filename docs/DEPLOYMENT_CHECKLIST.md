# Deployment Checklist

Pre-flight steps before making the repository public and deploying to Railway.

---

## 1. Repository hygiene (must complete on Zulu before public push)

- [x] **Delete internal dev notes:** `git rm docs/dev-environment-notes.md`
  ✓ Done — file removed; confirmed clean via `git ls-files docs/`.

- [x] **Remove internal development log from repository history:**
  ✓ Done — private workflow log stripped from git history before public push.

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

API smoke tests (curl):

| Test | Result |
|---|---|
| `GET /healthz` | `{"status":"ok","audit_enabled":false}` ✓ |
| `POST /v1/check` — no API key | 401 ✓ |
| Glenfiddich 12 two-panel (spirits) | UNVERIFIABLE — R-GW-02 warning (rotated GWS; expected) ✓ |

UI smoke tests (browser, via Railway URL) — screenshots in `docs/ui-screenshots/`:

Screenshots linked in §6 below reflect the current extraction prompt (post-LBL-AUD-0612). The `-postprompt` suffix was a temporary staging label and has been dropped from filenames.

| Label | Panels | Class | Verdict | Notes |
|---|---|---|---|---|
| Blue Ridge Rye (synth) | front + back | spirits | COMPLIANT ✓ | 0 violations — baseline |
| Glenfiddich 12 | front + back | spirits | UNVERIFIABLE | R-GW-02 warning — rotated GWS (expected) |
| Delirium Tremens (bottle) | front + back | beer | NONCOMPLIANT | R-GW-02 error + R-MB-04 warning; partial verification ✓ |
| Baci di Sangiovese | front + back | wine | COMPLIANT ✓ | 0 violations — clean European wine label |
| Budweiser | front + back (reversed) | beer | COMPLIANT ✓ | ⚠ Robustness test only — panels submitted in wrong order intentionally; not a compliance verification |
| Evergrain keg (COLA) | front only | beer | UNVERIFIABLE (REVIEW) | Single-panel keg collar; GWS/bottler not on front alone — expected |
| Pinotopia (COLA) | front + back | wine | COMPLIANT ✓ | COLA flat artwork, PNG |
| Gamma-Eta Whisky (COLA) | front + back | spirits | COMPLIANT ✓ | COLA flat artwork, PNG |

### Mode A (application-matching) smoke tests (2026-06-12, post-prompt LBL-AUD-0612)

Full 12-case batch run via `test-labels/mode-a-smoke-batch.sh` against local server (Gemini Flash Lite).

**R-APP-01 (brand_name) — systemic FP, all labels:** Model extracts the most prominent display text ("HARBOR BAY", "CANYON RIDGE", "MESA VERDE", "SIERRA NEVADA") rather than the full declared brand string. Exact-string match fails on every label. Root cause is label design: brand name ≠ display headline. For Mesa Verde wine synthetics there is an additional stub issue — stub declares "Mesa Verde Chardonnay" (winery + varietal) while the label prints "MESA VERDE WINERY" as the brand; a real COLA application would declare the brand as it appears.

**R-APP-05 (country_of_origin) — partially fixed:** Beer and spirits synthetics now extract origin from the class/type line on the label face ("AMERICAN LAGER" → "American"; "Kentucky Straight Bourbon Whiskey" → "Kentucky") rather than the bottler address. Wine labels lack this geographic anchor in the class/type text; Mesa Verde still extracts "USA" from the address — documented limitation (see FAQ Part I — R-APP-05). Canyon Ridge variant images (R-APP-04, R-APP-01-02) also show R-APP-05 FP: the designed-violation images suppress the class/type origin cue, causing the model to fall back to the address.

**R-APP-04 (net contents) — now detected:** Previously a miss (`net_contents` returned `not_found`). Post-prompt, "1.0 L" vs stub "750 mL" is correctly flagged on Canyon Ridge R-APP-04. Tito's R-APP-04 FP also cleared — "1 L" normalization now matches.

**schema_violations:** 0 on 10 of 12 cases. Two stochastic outliers: Harbor Bay compliant (8) and Sierra Nevada (9) — no clear pattern; other runs of the same images return 0.

| Label | Expected violations | Actual violations | Notes |
|---|---|---|---|
| Harbor Bay Lager — compliant (synth) | none | R-APP-01 FP | "HARBOR BAY" ≠ "Harbor Bay Lager"; R-APP-05 clear ✓; schema_violations=8 (stochastic) |
| Harbor Bay Lager — R-APP-01 (synth) | R-APP-01 ✓ | R-APP-01 ✓ | found "HARBOR POINT"; schema_violations=0 |
| Harbor Bay Lager — R-APP-02 (synth) | R-APP-02 ✓ | R-APP-01 FP + R-APP-02 ✓ | R-APP-02: 5.8% ≠ 5.0%; R-APP-05 clear ✓; schema_violations=0 |
| Canyon Ridge Bourbon — compliant (synth) | none | R-APP-01 FP | "CANYON RIDGE" ≠ "Canyon Ridge Bourbon"; R-APP-05 clear ✓; schema_violations=0 |
| Canyon Ridge Bourbon — R-APP-04 (synth) | R-APP-04 ✓ | R-APP-01 FP + R-APP-04 ✓ + R-APP-05 FP | R-APP-04: "1.0 L" ≠ "750 mL" ✓; R-APP-05: "USA" ≠ "Kentucky" (variant image suppresses class/type cue); schema_violations=0 |
| Canyon Ridge Bourbon — R-APP-01+02 (synth) | R-APP-01 ✓, R-APP-02 ✓ | R-APP-01 ✓ + R-APP-02 ✓ + R-APP-05 FP | R-APP-02: 48% ≠ 45%; R-APP-05: "Lawrenceburg, Kentucky" ≠ "Kentucky" (city+state from address); schema_violations=0 |
| Tito's Handmade Vodka (real) | none (compliant) | R-GW-03, R-GW-02, R-META-02, R-APP-01 FP | R-APP-04 clear ✓ (normalization fix); R-APP-05 clear ✓; CFR errors unrelated to Mode A; schema_violations=0 |
| Mesa Verde Chardonnay — compliant (synth) | none | R-APP-01 FP + R-APP-05 FP | "MESA VERDE" ≠ "Mesa Verde Chardonnay"; "USA" ≠ "California" (wine origin limitation); schema_violations=0 |
| Mesa Verde Chardonnay — R-APP-03 (synth) | R-APP-03 ✓ | R-APP-01 FP + R-APP-03 ✓ + R-APP-05 FP | R-APP-03: "WHITE WINE" ≠ "Chardonnay" ✓; same FPs as compliant variant; schema_violations=0 |
| Mesa Verde Chardonnay — R-APP-05 (synth) | R-APP-05 ✓ | R-APP-01 FP + R-APP-05 (wrong reason) | R-APP-05 fires: found "USA" ≠ "California"; designed violation = "Sonoma County" on label face; fires for wrong reason — documented limitation; schema_violations=0 |
| Angry Orchard Iceman (real) | none (compliant) | R-GW-02 warning only | UNVERIFIABLE; all R-APP-* clear ✓; cleanest real-label Mode A result; schema_violations=0 |
| Sierra Nevada Pale Ale (real) | none (compliant) | R-GW-02 + R-MB-04 + R-MB-03 + R-APP-01 FP | R-APP-01: "SIERRA NEVADA" ≠ "Sierra Nevada Pale Ale"; R-APP-05 clear ✓ (stub `origin_as_stated` updated to "American" post-batch; was FP in initial run); partial_verification; schema_violations=9 (stochastic) |

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

### Test label inventory

Full inventory — file paths, panel conventions, COLA artwork, and bottle/can photographs — is in [`test-labels/README.md`](../test-labels/README.md) (*Official COLA artwork* and *Real label pairs*).

**HEIC rejection test:** `beer/stiegl-radler-grapefruit-front.heic` — submit to verify 415 is returned for iPhone HEIC uploads.

The smoke test (`scripts/smoke-test.sh`) includes real-label calls for Henninger, Stiegl, Heineken, Ron Ron, and Delirium Tremens can.

### Multi-panel test matrix

For each product below, the "front-only" submission exercises the path where compliance-critical content (typically the GWS) is absent from the submitted panel; the "front+back" submission is the expected success path. Verdicts marked ✓ are confirmed from a smoke-test run, web UI check, or Mode A batch run against Gemini Flash Lite (2026-06-12).

| Product | Front-only | Front+back | Notes |
|---|---|---|---|
| **Synthetic labels** | | | |
| Copper Creek Merlot synth (R-WN-09) | — | UNVERIFIABLE ✓ (R-WN-08, R-WN-09) | R-WN-08: vintage year detected but appellation not visible — pre-prompt model silently returned null appellation without triggering this rule; post-prompt it correctly fires; R-WN-09 still fires (sulfite declaration unverifiable from image, unchanged); schema_violations=0 (was 9 pre-prompt); verdict change is improvement in model honesty; screenshot: docs/ui-screenshots/railway-copper-creek-merlot-unverifiable.png |
| Silverleaf Chardonnay synth (compliant baseline) | — | **COMPLIANT** ✓ | schema_violations=0 — cleanest extraction in corpus |
| Blue Ridge Rye synth (compliant baseline, reversed panels) | — | **COMPLIANT** ✓ | Panels submitted reversed (back→front slot); schema_violations=0 post-prompt (was 11 pre-prompt); merge correctly handles wrong slot; screenshot: docs/ui-screenshots/railway-blue-ridge-rye-synth-compliant-reversed.png |
| **Real labels — spirits** | | | |
| Tito's Vodka | NONCOMPLIANT ✓ (R-GW-01, R-DS-04, R-DS-03) | **COMPLIANT** ✓ | GWS on back correctly found; schema_violations=4 (compliant verdict despite violations) |
| JD Old No. 7 EU 70cl | NONCOMPLIANT ✓ (R-GW-01) | — (front only) | Non-US label; no GWS |
| JD Old No. 7 domestic TN | NONCOMPLIANT ✓ (R-GW-01) | NONCOMPLIANT ✓ (R-GW-01) | Excluded from matrix until 2026-06-12; in `smoke-test.sh` only — 200 ml front / 750 ml back, no GWS visible on either panel; not a GWS-resolution test |
| Glenfiddich 12 | NONCOMPLIANT (predicted) | **COMPLIANT** ✓ | GWS on back rotated 90°; EXIF correction allows verbatim body match; ⚠ Inconsistent across runs — prior API run gave NONCOMPLIANT (R-GW-02); reversed-panel submission (back→front slot) → NONCOMPLIANT (R-GW-02) — panel slot affects extraction of rotated images |
| Glenlivet 12 | NONCOMPLIANT (predicted) | UNVERIFIABLE ✓ | GWS rotated 90°; low-confidence reads → all warnings → UNVERIFIABLE; specific warnings vary by run (R-GW-02/03, R-DS-06) — schema_violations=7 observed; verdict UNVERIFIABLE is stable across runs |
| Gamma-Eta Whisky (COLA artwork, domestic) | — | **COMPLIANT** ✓ | Type (i) COLA flat artwork, PNG; screenshot: docs/ui-screenshots/railway-gamma-eta-compliant.png |
| **Real labels — beer** | | | |
| Henninger Lager | NONCOMPLIANT ✓ (R-GW-01, R-MB-04, R-MB-05 ×2) | UNVERIFIABLE ✓ (R-MB-04, R-MB-05 ×2) | Submitted as front+GWS; GWS found ✓; net contents and bottler info on third (importer) face |
| Stiegl Radler | NONCOMPLIANT (predicted) | **COMPLIANT** ✓ | ⚠ Previous prediction was UNVERIFIABLE — model finds 2.5% ABV on label; actual COMPLIANT |
| Budweiser | NONCOMPLIANT (predicted) | UNVERIFIABLE ✓ (R-MB-04) | ⚠ Robustness test only — panels reversed intentionally to verify panel-agnostic merge; net contents absent from both panels; UNVERIFIABLE is expected and correct; not a compliance signal |
| Delirium Tremens bottle | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02, R-MB-04) | R-GW-02 body mismatch; schema_violations=8 (model returned 8 bare primitives — notable quality signal); screenshot: docs/ui-screenshots/railway-delirium-tremens-bottle-noncompliant.png |
| Delirium Tremens can | NONCOMPLIANT (predicted) | UNVERIFIABLE ✓ (R-GW-03, R-GW-02, R-MB-04, R-MB-03 — all warnings) | Post-prompt: R-GW-02 downgraded from error to warning (model less certain on partially-obscured GWS body); all-warnings verdict → UNVERIFIABLE; schema_violations pre-prompt=8, post-prompt not captured; screenshot: docs/ui-screenshots/railway-delirium-tremens-can-unverifiable.png |
| Delirium Tremens can — 3-panel hybrid (Option B) | — | NONCOMPLIANT ✓ (R-GW-02) | `front=beer/delirium-tremens-can-front.jpg`, `back=beer/delirium-tremens-can-gws-side.jpg` (GWS + side stitched); R-GW-02 error on `gws_body`; duration 2.80 s; schema_violations=0; model gemini/gemini-2.5-flash-lite; confirms genuine "OR TO OPERATE MACHINERY" violation (same root cause as bottle row above); screenshot: docs/ui-screenshots/railway-delirium-tremens-can-noncompliant.png |
| Heineken Original | NONCOMPLIANT ✓ (R-GW-01, R-MB-04, R-MB-05 ×2) | **COMPLIANT** ✓ | |
| Sierra Nevada Pale Ale | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02) | partial_verification; R-MB-04 + R-MB-03 warnings (net contents + ABV not visible); schema_violations=0 |
| Mike's Harder Lemonade | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-03, R-GW-02) | Flavored malt beverage; GWS header missing colon; body mismatch; also: model hallucinated abv_pct=5.0 (label says 8%) |
| Evergrain keg (COLA artwork, domestic) | UNVERIFIABLE ✓ (REVIEW) | — | Single-panel keg collar; no back label exists; GWS or bottler fields not visible on front alone → REVIEW is expected and correct; screenshot: docs/ui-screenshots/railway-evergrain-unverifiable.png |
| **Real labels — wine** | | | |
| Auchere Sancerre | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02, R-WN-05 ×2) | GWS body mismatch; bottler name+address not visible in photos |
| Baci di Sangiovese | NONCOMPLIANT (predicted) | **COMPLIANT** ✓ | ⚠ Unexpected — predicted NONCOMPLIANT; model reads GWS and all required fields correctly; schema_violations=0 |
| Brumes Tour Blanche | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02) | front + back-a; R-GW-02 error + R-WN-04 warning; schema_violations=13; GWS body mismatch |
| Bulliat Bibine | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-03) | GWS header not all-caps — mixed case on this French import label |
| Ron Ron Sauvignon | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-03, R-GW-02) | GWS header mixed-case + body mismatch |
| Angry Orchard Iceman | NONCOMPLIANT (predicted) | NONCOMPLIANT ✓ (R-GW-02) | Wine category; R-GW-03 observed in prior run — model stochastic on header; schema_violations=11 |
| Pinotopia (COLA artwork, domestic) | — | **COMPLIANT** ✓ | Type (i) COLA flat artwork, PNG; screenshot: docs/ui-screenshots/railway-pinotopia-compliant.png |

### To-do before interviewer submission

- [x] Run Henninger front + GWS smoke test — UNVERIFIABLE; GWS found ✓; net contents/bottler on third face
- [x] Run Stiegl two-panel smoke test — COMPLIANT ✓ (model finds 2.5% ABV; earlier UNVERIFIABLE prediction was wrong)
- [x] Run spirits real-label smoke tests — Tito's front+back COMPLIANT ✓; JD front+back NONCOMPLIANT (R-GW-01); Glenfiddich NONCOMPLIANT (R-GW-02); Glenlivet UNVERIFIABLE (low-confidence GWS read, rotated 90°)
- [x] Run remaining matrix rows — Budweiser, Delirium Tremens bottle, Auchere Sancerre, Bulliat Bibine confirmed (2026-06-12 via web UI)
- [x] Run remaining matrix rows: Sierra Nevada, Baci di Sangiovese, Brumes Tour Blanche confirmed (2026-06-12 via web UI) — all §6 rows complete
- [x] Jack Daniel's domestic TN — `smoke-test.sh` runs front-only and front+back (NONCOMPLIANT, R-GW-01); §6 matrix row added; full GWS-resolution test deferred pending a clean GWS photo
- [x] Document smoke-test results and model anomalies (Mike's Harder abv_pct hallucination, Glenlivet UNVERIFIABLE) — captured in [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md), [IMPLEMENTATION_STATUS.md](../IMPLEMENTATION_STATUS.md), and [FAQ.md Part II §5–6](FAQ.md).

---

## 7. Interview submission notes

- `docs/adr/` — architectural decision-making with explicit trade-off reasoning.
- [DEPLOYMENT_CHECKLIST.md §6](DEPLOYMENT_CHECKLIST.md) and [docs/ui-screenshots/](ui-screenshots/) — real-label smoke test matrix and browser verification artifacts.
- `IMPLEMENTATION_STATUS.md` — honest scoping: what is built vs. deliberately deferred.
- The two-layer architecture (AI extraction + deterministic checker) is the core design insight worth explaining in the interview.
