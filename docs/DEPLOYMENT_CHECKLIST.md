# Deployment Checklist

Pre-flight steps before making the repository public and deploying to Railway.

---

## 1. Repository hygiene (must complete on Zulu before public push)

- [ ] **Delete internal dev notes:** `git rm docs/dev-environment-notes.md`
  Contains Tailscale hostnames and internal infrastructure details — must not be public.

- [ ] **Review `docs/project-log.md`:**
  This file documents all work sessions in detail and is intended to demonstrate the development process to interviewers. Read through it and decide which entries to include verbatim and which to redact. The file is ready to sanitize but has not been changed yet.

- [ ] **Verify `.gitignore` covers all sensitive paths:**
  Confirm `audit_logs/`, `.env`, `.env.*` are in `.gitignore` and that no `.env` file or audit log was accidentally committed (`git log --all --full-history -- 'audit_logs/*' '.env'`).

- [ ] **Commit the `uv.lock` file** for reproducible installs (`uv lock` if not already present).

---

## 2. Documentation (complete before public push)

- [ ] **Root `README.md`** — project overview, quick-start instructions, API reference summary, link to ADRs.
- [ ] **`IMPLEMENTATION_STATUS.md`** — maps each ADR to what is built vs. deferred, so reviewers can assess scope honestly.
- [ ] **`LICENSE`** — choose a license (MIT is appropriate for an interview demo).

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

Synthetic labels are sufficient for demonstrating the architecture, but real label scans will reveal edge cases (model hallucinations, OCR ambiguity, non-standard layouts). Test at minimum:

- [ ] Beer can — front + back panels
- [ ] Spirits bottle — front + back panels
- [ ] Wine bottle — front + back panels

Document any new issues found in `docs/project-log.md`.

---

## 6. Interview submission notes

- `docs/project-log.md` (sanitized) — shows design thinking, iteration, and debugging process.
- `docs/adr/` — shows architectural decision-making with explicit trade-off reasoning.
- `IMPLEMENTATION_STATUS.md` — honest scoping: what is built vs. deliberately deferred.
- The two-layer architecture (AI extraction + deterministic checker) is the core design insight worth explaining in the interview.
