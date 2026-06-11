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
  -F "front=@tests/images/beer_sunset_ale_front.png"

# Two-panel spirits — expect COMPLIANT
curl -X POST https://<URL>/v1/check \
  -H "X-API-Key: <KEY>" \
  -F "front=@tests/images/spirits_front.png" \
  -F "back=@tests/images/spirits_back.png"
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

| Product | Front | Back/GWS | Notes |
|---|---|---|---|
| Henninger Lager (beer, imported DE) | `henninger-real-front.jpg` | `henninger-real-gws.jpg` | GWS face upside-down in photo; importer info on a separate third face (`henninger-real-back.jpg`) |
| Stiegl Radler Grapefruit (malt bev., imported AT) | `stiegl-radler-grapefruit-front.jpg` | `stiegl-radler-grapefruit-back.jpg` | Clean two-panel pair; 2.5% ABV; full importer address on back |

**HEIC rejection test:** `stiegl-radler-grapefruit-front.heic` — submit to verify 415 is returned for iPhone HEIC uploads.

The smoke test (`scripts/smoke-test.sh`) includes real-label calls for both pairs.

### To-do before interviewer submission

- [ ] Run Henninger front + GWS smoke test; document result in `docs/project-log.md`
- [ ] Run Stiegl two-panel smoke test; document result
- [ ] Acquire and test a spirits bottle — front + back panels
- [ ] Acquire and test a wine bottle — front + back panels

---

## 7. Interview submission notes

- `docs/project-log.md` (sanitized) — shows design thinking, iteration, and debugging process.
- `docs/adr/` — shows architectural decision-making with explicit trade-off reasoning.
- `IMPLEMENTATION_STATUS.md` — honest scoping: what is built vs. deliberately deferred.
- The two-layer architecture (AI extraction + deterministic checker) is the core design insight worth explaining in the interview.
