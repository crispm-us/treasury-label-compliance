# ADR-013: Batch Processing — Client-Side PoC

Date: 2026-06-13
Status: Accepted — **partial in prototype**

> **Prototype status:** UI-only batch tab implemented (Stage 2–5 of plan). No new backend endpoint. The existing `POST /v1/check` is called sequentially per product. See [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md).

## Context

ADR-007 accepted a batch-first API design (`POST /v1/labels/check` with a `labels` array) but it was never built. The original rationale — avoid breaking single-label clients — is moot: no external clients exist against the current endpoint shape. The spec noted batch as a "would be huge" feature for large importers.

A full async job queue implementation is out of scope for a prototype. However, a UI-only proof of concept is achievable with zero backend changes: the frontend submits checks sequentially against the existing `POST /v1/check` endpoint and accumulates results into a table.

The PoC constraint is deliberate: up to 10 products (20 images) per batch run. This covers the realistic evaluation use case (a handful of label pairs) without requiring server-side queuing, persistence, or a new API shape.

## Decision

Implement batch as a second tab in the existing React frontend. No new backend endpoint. The frontend:

1. Accepts up to 20 files via a multi-file drop zone
2. Auto-pairs files by the existing naming convention (`*-front.*` + `*-back.*` matched by stem); unpaired files submit as front-only
3. Shows a pairing preview table before submission so the user can verify pairs before running
4. Submits checks sequentially via the existing `POST /v1/check`, one product at a time, with a progress indicator
5. Renders results in-place as each check completes
6. Offers a CSV download of the completed run
7. Fires a single summary ntfy.sh notification at batch completion rather than one per check

```
UI flow:
  drop zone (multi-file) → pairing preview → [Run batch]
    → sequential POST /v1/check × N → live results table → [Download CSV]
```

Sequential (not parallel) submission is intentional: extraction takes 2–3 s per call, so 10 products complete in ~25 s — well within a practical wait time. Parallel submission at 10× would risk hitting Railway's rate limit for larger batches and adds complexity for minimal gain at this scale.

## Consequences

- No backend changes, no new API surface, no new dependencies
- Results are in-memory only — lost on page refresh (acceptable for PoC)
- The 10-product / 20-image cap is enforced client-side only; there is no server-side batch-size guard
- Sequential submission means one model failure (503, timeout) does not block the run — the failed row is marked and the run continues
- The existing `RATE_LIMIT_PER_MIN` setting must be ≥ 10 for a full batch run without 429s; current defaults (60 local, 30 Railway) are sufficient
- ntfy.sh behavior changes: mid-batch per-check notifications are suppressed; a summary fires at completion (e.g. "Batch 10/10: 7 COMPLIANT · 2 NONCOMPLIANT · 1 REVIEW")
- This PoC validates the UX before committing to the server-side design in ADR-007

## Relationship to ADR-007

ADR-007 remains the accepted design for a production batch endpoint. This ADR supersedes ADR-007 only for the prototype scope. When a server-side batch endpoint is built, the UI tab's fetch layer will swap from sequential single-check calls to a single batch request — the results table and CSV export are reusable as-is.

## Alternatives Considered

**New `POST /v1/batch` endpoint (ADR-007 design):** Server fans out to the extraction pipeline with `asyncio.gather()`. Correct production design; adds ~1 day of backend work and requires specifying multipart encoding for multiple file pairs. Deferred — the client-side PoC validates the UX first.

**ZIP upload:** User uploads a ZIP of front/back pairs; server unpacks and processes. Cleaner for large batches but requires server-side ZIP handling and temporary storage. Out of scope for PoC.

**Parallel client-side submission:** Submit all N checks concurrently. Faster but risks 429s at the Railway rate limit and complicates progress tracking. Not worth it at 10-product scale.
