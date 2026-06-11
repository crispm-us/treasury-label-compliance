# Deployment Checklist

Pre-flight steps before making the repository public and deploying to Railway.

---

## 1. Repository hygiene (must complete on Zulu before public push)

- [x] **Delete internal dev notes:** `git rm docs/dev-environment-notes.md`
  ✓ Done — file removed; confirmed clean via `git ls-files docs/`.

- [ ] **Review `docs/project-log.md`:**
  This file documents all work sessions in detail and is intended to demonstrate the development process to interviewers. Read through it and decide which entries to include verbatim and which to redact. The file is ready to sanitize but has not been changed yet.

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

- [ ] **Set `API_KEY` in the Railway environment dashboard** before sharing the deployment URL.
  Any non-empty value requires `X-API-Key: <value>` on every `POST /v1/check` request.
  Share the key only with yourself and the hiring manager/team.

- [ ] **Set `ANTHROPIC_API_KEY`** in the Railway environment dashboard.

- [ ] **Confirm `AUDIT_ENABLED=true`** in the Railway environment (default; no action needed unless overridden).

- [ ] **Smoke-test the live endpoint** using the commands in §4 below before sharing the URL.

---

## 4. Live smoke test (run after Railway deployment)

Replace `<URL>` and `<KEY>` with the Railway URL and your `API_KEY` value.

```bash
# Health check
curl https://<URL>/healthz

# Beer label — expect COMPLIANT or NONCOMPLIANT (not ERROR)
curl -X POST https://<URL>/v1/check \
  -H "X-API-Key: <KEY>" \
  -F "front=@test-labels/beer/prairie-creek-lager-front.jpg"

# Two-panel spirits — expect COMPLIANT
curl -X POST https://<URL>/v1/check \
  -H "X-API-Key: <KEY>" \
  -F "front=@test-labels/spirits/blue-ridge-rye-front.jpg" \
  -F "back=@test-labels/spirits/blue-ridge-rye-back.jpg"
```

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

#### Beer

| Product | Front | Back/GWS | Notes |
|---|---|---|---|
| Henninger Lager (imported DE) | `beer/henninger-real-front.jpg` | `beer/henninger-real-gws.jpg` | GWS face upside-down in photo; importer info on a third face (`henninger-real-back.jpg`) |
| Stiegl Radler Grapefruit (malt bev., imported AT) | `beer/stiegl-radler-grapefruit-front.jpg` | `beer/stiegl-radler-grapefruit-back.jpg` | 2.5% ABV; full importer address on back |
| Budweiser (domestic) | `beer/budweiser-real-front.jpg` | `beer/budweiser-real-back.jpg` | GWS on side/back panel |
| Delirium Tremens bottle (imported BE, 8.5% ABV) | `beer/delirium-tremens-bottle-real-front.jpg` | `beer/delirium-tremens-bottle-real-back.jpg` | BBL Inc, Frederick MD; imported |
| Delirium Tremens can (imported BE, 8.5% ABV) | `beer/delirium-tremens-can-real-front.jpg` | `beer/delirium-tremens-can-real-gws.jpg` | 3-panel cylinder; also `delirium-tremens-can-real-side.jpg` (ABV + net contents) |
| Heineken Original (imported NL) | `beer/heineken-original-real-front.jpg` | `beer/heineken-original-real-back.jpg` | Standard two-panel |
| Sierra Nevada Pale Ale (domestic) | `beer/sierra-nevada-pale-ale-real-front.jpg` | `beer/sierra-nevada-pale-ale-real-back.jpg` | Standard two-panel |

**HEIC rejection test:** `beer/stiegl-radler-grapefruit-front.heic` — submit to verify 415 is returned for iPhone HEIC uploads.

The smoke test (`scripts/smoke-test.sh`) includes real-label calls for Henninger, Stiegl, Heineken, Ron Ron, and Delirium Tremens can.

#### Wine

| Product | Front | Back | Notes |
|---|---|---|---|
| Auchere Sancerre 2024 (imported FR) | `wine/auchere-sancerre-real-front.jpg` | `wine/auchere-sancerre-real-back.jpg` | Importer: Planet Wine Inc |
| Baci di Sangiovese 2020, Toscana IGT (imported IT) | `wine/baci-di-sangiovese-real-front.jpg` | `wine/baci-di-sangiovese-real-back.jpg` | Importer: Planet Wine Inc |
| Brumes de La Tour Blanche 2021 Sauternes (imported FR) | `wine/brumes-tour-blanche-real-front.jpg` | `wine/brumes-tour-blanche-real-back-a.jpg` | 4 shots; `-back-c.jpg` explicitly shows `375 ml` net contents |
| Loic Bulliat Bibine 2023, Beaujolais-Villages (imported FR) | `wine/bulliat-bibine-real-front.jpg` | `wine/bulliat-bibine-real-back.jpg` | Standard two-panel |
| The "Ron Ron" Sauvignon 2023, Loire Valley (imported FR) | `wine/ron-ron-sauvignon-real-front.jpg` | `wine/ron-ron-sauvignon-real-back.jpg` | ⚠ GWS header in mixed case — R-GW-03 candidate |

### Multi-panel test matrix

For each product below, the "front-only" submission is the **failure case** — it exercises the path where compliance-critical content (typically the GWS) is absent from the submitted panel. The "front+back" submission is the **expected success path**. Verdicts marked `unverified*` are predictions based on label content; update after first run.

| Product | Front-only expected | Front+back expected | Notes |
|---|---|---|---|
| Henninger Lager | UNVERIFIABLE (GWS on separate GWS face) | — (use front + gws face) | ✓ smoke tested |
| Stiegl Radler | NONCOMPLIANT (GWS absent front) | UNVERIFIABLE (ABV absent on both panels) | ✓ smoke tested |
| Budweiser | NONCOMPLIANT (GWS absent front) | unverified* | GWS on side/back panel |
| Delirium Tremens bottle | NONCOMPLIANT (GWS absent front) | unverified* | |
| Delirium Tremens can | NONCOMPLIANT (GWS absent front) | unverified* | Use front + gws face; side face has ABV/net contents only |
| Heineken Original | NONCOMPLIANT (GWS absent front) | unverified* | ✓ front-only smoke tested |
| Sierra Nevada Pale Ale | NONCOMPLIANT (GWS absent front) | unverified* | |
| Auchere Sancerre | NONCOMPLIANT (GWS absent front) | unverified* | |
| Baci di Sangiovese | NONCOMPLIANT (GWS absent front) | unverified* | |
| Brumes Tour Blanche | NONCOMPLIANT (GWS absent front) | unverified* | Use front + back-a; back-c confirms 375 ml |
| Bulliat Bibine | NONCOMPLIANT (GWS absent front) | unverified* | |
| Ron Ron Sauvignon | NONCOMPLIANT (GWS absent front) | **NONCOMPLIANT** (R-GW-03: mixed-case header) | ✓ front+back smoke tested; GWS header reads "Government Warning:" not all-caps |

`unverified*` — run `bash scripts/smoke-test.sh` with a live model to confirm; then update this table.

### To-do before interviewer submission

- [ ] Run Henninger front + GWS smoke test; document result in `docs/project-log.md`
- [ ] Run Stiegl two-panel smoke test; document result
- [ ] Run all `unverified*` rows through `smoke-test.sh`; update table with confirmed verdicts
- [ ] Acquire and test a spirits bottle — front + back panels

---

## 7. Interview submission notes

- `docs/project-log.md` (sanitized) — shows design thinking, iteration, and debugging process.
- `docs/adr/` — shows architectural decision-making with explicit trade-off reasoning.
- `IMPLEMENTATION_STATUS.md` — honest scoping: what is built vs. deliberately deferred.
- The two-layer architecture (AI extraction + deterministic checker) is the core design insight worth explaining in the interview.
