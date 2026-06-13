# ADR-013: Batch Processing — Client-Side PoC

Date: 2026-06-13
Status: Accepted — **not yet implemented**

> **Prototype status:** Batch UI tab not yet built. Stage 2–5 (tab restructure, pairing preview, sequential submission, CSV export) are planned for local iteration only; no git push until Stage 6. No new backend endpoint. See [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md).

## Context

ADR-007 accepted a batch-first API design (`POST /v1/labels/check` with a `labels` array) but it was never built. The original rationale — avoid breaking single-label clients — is moot: no external clients exist against the current endpoint shape. The spec noted batch as a "would be huge" feature for large importers.

A full async job queue implementation is out of scope for a prototype. However, a UI-only proof of concept is achievable with zero backend changes: the frontend submits checks sequentially against the existing `POST /v1/check` endpoint and accumulates results into a table.

The PoC constraint is deliberate: up to 10 products (20 images) per batch run. This covers the realistic evaluation use case (a handful of label pairs) without requiring server-side queuing, persistence, or a new API shape.

## Decision

Implement batch as a second tab in the existing React frontend. No new backend endpoint. The frontend:

1. Accepts up to 20 files via a multi-file drop zone (HEIC/HEIF rejected with a client-side error; supported: JPEG, PNG, WEBP — matching `ALLOWED_MEDIA_TYPES` in `backend/app/main.py`)
2. Auto-pairs files by the existing naming convention (`*-front.*` + `*-back.*` matched by stem; see Pairing Algorithm below); the product count after pairing must not exceed 10
3. Shows a pairing preview table before submission so the user can verify pairs before running
4. Submits checks sequentially via the existing `POST /v1/check`, one product at a time, with a progress indicator
5. Renders results in-place as each check completes
6. Offers a CSV download of the completed run

**Scope:** Batch v1 is regulation-only — the `application` field is not exposed in the batch tab; all checks run without a COLA stub. (In ADR-003 terminology, omitting `application` is the default path; application-matching is a separate optional feature not targeted here.)

**ntfy.sh behavior:** The backend fires one ntfy notification per `/v1/check` call — unchanged. A batch of 10 products produces 10 notifications. A batch-end summary notification would require a new backend endpoint and is deferred to ADR-007 scope.

### Pairing algorithm

Pre-check: reject the entire drop if the total file count exceeds 20. This is a hard gate before pairing begins.

1. For each file, derive a **stem** by stripping the literal suffix `-front` or `-back` immediately before the file extension (e.g. `pinotopia-front.png` → stem `pinotopia`). Only exact `-front`/`-back` matches are recognized; suffixes like `-back-a` or `-back-c` are **not** pairable and fall through to rule 5.
2. Pair files with the same stem where one has `-front` and one has `-back`. The front file is panel 1; the back file is panel 2.
3. **Orphan `-back` file** (stem has no matching `-front`): skip with a visible warning row. Do not submit.
4. **Multiple `-back` files for the same stem**: not possible under this rule (suffix must be exactly `-back`). Files with variant suffixes like `-back-a` are treated as unpaired per rule 5.
5. **Files with no `-front`/`-back` suffix** (including `-back-a` style): treat as front-only (single-panel submission).
6. **Product cap:** if the paired row count exceeds 10, reject the entire drop — "Maximum 10 products per batch. Found N. Split into smaller batches." No partial runs.

### CSV schema

| Column | Description |
|---|---|
| `product_id` | Stem derived from filename |
| `front_file` | Filename of the front panel |
| `back_file` | Filename of the back panel, or empty |
| `verdict` | `COMPLIANT`, `NONCOMPLIANT`, `REVIEW`, or `ERROR` |
| `issues` | Pipe-separated issue codes (e.g. `R-GW-01\|R-SP-02`), empty if none |
| `duration_ms` | Extraction + compliance check time in ms |
| `checked_at` | ISO-8601 timestamp (client local time) |

```
UI flow:
  drop zone (multi-file) → pairing preview → [Run batch]
    → sequential POST /v1/check × N → live results table → [Download CSV]
```

Sequential (not parallel) submission is intentional: extraction takes 2–3 s per call, so 10 products complete in ~25 s — well within a practical wait time. Parallel submission at 10× would risk hitting Railway's rate limit for larger batches and adds complexity for minimal gain at this scale.

## Consequences

- No backend changes, no new API surface, no new dependencies
- Results are in-memory only — lost on page refresh (acceptable for PoC)
- The 10-product / 20-file caps are enforced client-side only; there is no server-side batch-size guard
- Sequential submission means one model failure (503, timeout) does not block the run — the failed row is marked `ERROR` and the run continues
- The existing `RATE_LIMIT_PER_MIN` setting must be ≥ 10 for a full batch run without 429s; current defaults (60 local, 30 Railway) are sufficient
- ntfy.sh fires per `/v1/check` call (up to 10 pushes per batch); a batch-end summary is ADR-007 scope
- HEIC files are rejected client-side; users must convert before uploading (same limitation as the single-check tab)
- This PoC validates the UX before committing to the server-side design in ADR-007

## Relationship to ADR-007

ADR-007 remains the accepted design for a production batch endpoint. This ADR supersedes ADR-007 only for the prototype scope. When a server-side batch endpoint is built, the UI tab's fetch layer will swap from sequential single-check calls to a single batch request — the results table and CSV export are reusable as-is.

## Alternatives Considered

**New `POST /v1/labels/check` batch endpoint (ADR-007 design):** Server fans out to the extraction pipeline with `asyncio.gather()`. Correct production design; adds ~1 day of backend work and requires specifying multipart encoding for multiple file pairs. Deferred — the client-side PoC validates the UX first.

**ZIP upload:** User uploads a ZIP of front/back pairs; server unpacks and processes. Cleaner for large batches but requires server-side ZIP handling and temporary storage. Out of scope for PoC.

**Parallel client-side submission:** Submit all N checks concurrently. Faster but risks 429s at the Railway rate limit and complicates progress tracking. Not worth it at 10-product scale.
