# ADR-003: Dual-Mode Input Design

Date: 2026-06-09
Status: Accepted — **partial in prototype**

> **Prototype status:** Mode A application-matching is implemented end-to-end: optional `application` JSON on `POST /v1/check` compares extracted label fields against declared application values (`application_checker.py`, R-APP-01–R-APP-05 — origin checked as declared string via `origin_as_stated`; ISO country code carried as metadata in `origin_iso2_country`, not validated at runtime). The UI exposes Mode A via a collapsible toggle with a catalog dropdown (`GET /v1/applications`). Application stubs live in `test-labels/applications/` (9 synthetic + 3 real-label). Full COLA on-file integration is deferred. Mode B remains the default when `application` is omitted. See [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md).

## Context

The spec describes a workflow where an agent uploads a label image and the system checks it for compliance. Two interpretations are possible:

- **Mode B (production):** Agent uploads only the label image. The system extracts all fields via vision model and checks them against TTB regulatory requirements.
- **Mode A (test harness):** Agent submits claimed field values (brand name, ABV, etc.) alongside the image. The system checks that the image matches the claimed values — bypassing the vision model for field extraction.

Mode A is not in the spec but is valuable for development: it allows testing the compliance rules and UI without incurring model API costs on every test run.

## Decision

Implement both modes as a single endpoint with an optional `application` JSON field. When `application` is absent the request runs Mode B (regulation-only); when present it runs Mode A (application-matching) after the same vision extraction step.

```
Mode B (default — regulation only):
  image → vision model → extracted fields → compliance_checker → result
  Response: mode = "regulation_only"

Mode A (application-matching):
  image → vision model → extracted fields → compliance_checker
                                          → application_checker (R-APP-01–R-APP-05) → result
  Response: mode = "application_match"
```

Mode A does **not** skip the vision model. It adds a second deterministic checker after Layer 2 that compares extracted field values against the declared values in the `application` JSON. The `mode` discriminator is implicit (presence/absence of `application`), not an explicit request field.

The UI exposes Mode A via a collapsible toggle with an application catalog dropdown populated from `GET /v1/applications`.

## Consequences

- Unit tests for compliance rules run entirely in Mode A — zero model API calls, fast CI
- Integration tests use Mode B with a real model call, tagged `@integration` and opt-in
- Mode A is honest about what it does: it does not verify that the submitted field values match the image; it only checks that the submitted values are TTB-compliant. This is clearly documented.
- The spec evaluators can test compliance logic exhaustively in Mode A without needing API keys

## Alternatives Considered

**Mode B only:** Simpler. Every test would require a model call. Rejected — makes CI expensive and slow, and makes it hard to test edge cases in compliance rules.

**Separate endpoints for each mode:** Cleaner separation but requires maintaining two API surfaces. Rejected in favor of a single endpoint with a mode discriminator.
