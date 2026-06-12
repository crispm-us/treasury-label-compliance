# ADR-003: Dual-Mode Input Design

Date: 2026-06-09
Status: Accepted — **partial in prototype**

> **Prototype status:** Mode A application-matching is implemented end-to-end: optional `application` JSON on `POST /v1/check` compares extracted label fields against declared application values (`application_checker.py`, R-APP-01–R-APP-05). The UI exposes Mode A via a collapsible toggle with a catalog dropdown (`GET /v1/applications`). Application stubs live in `test-labels/applications/` (9 synthetic + 3 real-label). Full COLA on-file integration is deferred. Mode B remains the default when `application` is omitted. See [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md).

## Context

The spec describes a workflow where an agent uploads a label image and the system checks it for compliance. Two interpretations are possible:

- **Mode B (production):** Agent uploads only the label image. The system extracts all fields via vision model and checks them against TTB regulatory requirements.
- **Mode A (test harness):** Agent submits claimed field values (brand name, ABV, etc.) alongside the image. The system checks that the image matches the claimed values — bypassing the vision model for field extraction.

Mode A is not in the spec but is valuable for development: it allows testing the compliance rules and UI without incurring model API costs on every test run.

## Decision

Implement both modes. They share a single compliance-checking service; the difference is upstream:

```
Mode B (production):
  image → vision model → extracted fields → compliance_checker → result

Mode A (test harness):
  claimed fields + image → compliance_checker → result
  (vision model skipped; image is stored but not analyzed)
```

The API exposes both as a single endpoint; a request body field (`mode: "extract" | "verify"`) selects the path. The UI exposes Mode B by default and Mode A behind a clearly labeled "Developer / Test Mode" toggle.

## Consequences

- Unit tests for compliance rules run entirely in Mode A — zero model API calls, fast CI
- Integration tests use Mode B with a real model call, tagged `@integration` and opt-in
- Mode A is honest about what it does: it does not verify that the submitted field values match the image; it only checks that the submitted values are TTB-compliant. This is clearly documented.
- The spec evaluators can test compliance logic exhaustively in Mode A without needing API keys

## Alternatives Considered

**Mode B only:** Simpler. Every test would require a model call. Rejected — makes CI expensive and slow, and makes it hard to test edge cases in compliance rules.

**Separate endpoints for each mode:** Cleaner separation but requires maintaining two API surfaces. Rejected in favor of a single endpoint with a mode discriminator.
