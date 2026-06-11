# ADR-007: Batch Processing Design

Date: 2026-06-09
Status: Accepted — **not implemented in prototype**

> **Prototype status:** Batch processing was not built. The API implements single-label submission only (`POST /v1/check`). This ADR documents the accepted design for future implementation. See [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md).

## Context

The spec notes batch upload as a "would be huge" feature (Janet from Seattle has been requesting it for years). Large importers submit 200–300 label applications at once. The current one-at-a-time process is a known bottleneck.

Batch processing is not required for the MVP but must be designed in from the start — a retrofit would likely require breaking API changes.

## Decision

Design the API as **batch-first from day one**; expose single-label as the degenerate case of a batch of one. The UI exposes only single-label upload in v1.

```
POST /api/v1/labels/check
{
  "labels": [
    { "mode": "extract", "image_b64": "..." },
    { "mode": "extract", "image_b64": "..." }
  ]
}

→ {
  "results": [
    { "label_id": "...", "compliant": true, "fields": {...}, "issues": [] },
    { "label_id": "...", "compliant": false, "fields": {...}, "issues": [...] }
  ]
}
```

The backend processes batch items concurrently using `asyncio.gather()` — model API calls are async and can run in parallel up to a configurable concurrency limit (`MAX_CONCURRENT_REQUESTS`, default 5).

## Consequences

- Single-label UI just sends a batch of one — no special-casing in the frontend
- Batch UI (future) requires only a new frontend component; the API is already ready
- Concurrency limit prevents runaway costs if a large batch is submitted; adjustable via env var
- Response time for a batch of N is roughly `ceil(N / MAX_CONCURRENT_REQUESTS) × single_label_latency`

## Alternatives Considered

**Single-label API now, batch as a separate endpoint later:** Avoids over-engineering for v1. Rejected — the API shape change would break any clients already built against the single-label endpoint.

**Async job queue (Celery, RQ, etc.):** Appropriate for very large batches (1000+) where HTTP timeout is a concern. Out of scope for a prototype — adds broker infrastructure (Redis/RabbitMQ). Documented as the natural next step if batch sizes exceed ~50 labels.
