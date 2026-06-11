# ADR-010: Audit Logging

Date: 2026-06-09
Updated: 2026-06-10
Status: Accepted (implementation diverges from original design — see §Implementation vs. design below)

## Context

When the system produces a compliance verdict — especially a false positive (compliant label flagged as non-compliant) or a false negative (non-compliant label passed) — it must be possible to reconstruct exactly what was evaluated: which image, with what model, producing which verdict. Without this, errors cannot be diagnosed or appealed.

## Decision

Every label evaluation event writes one log record. The log is **append-only** and stored as JSON Lines (`.jsonl`) with per-day rotation, written by `backend/app/audit.py`. Files live in `audit_logs/` which is gitignored and never committed.

## Implementation vs. design (important)

The original ADR specified **Level A (minimal/SHA)** logging — see §Audit log sensitivity levels below. The current implementation writes **Level C (full extraction)**, logging the complete `ExtractionResult` including all extracted field values. The README correctly warns that `audit_logs/` contains sensitive data.

**Reason for divergence:** logging the full extraction was pragmatically simpler during prototype development and is more useful for debugging during active iteration. For a public-facing or production deployment, Level A or Level B should be preferred.

**This is an open decision for the owner** — see §Audit log sensitivity levels for the full analysis and trade-offs.

## Actual log record (Level C — current implementation)

Each line is a JSON object written by `audit.py`:

```json
{
  "request_id":        "uuid4",
  "timestamp":         "ISO 8601 UTC",
  "verdict":           "COMPLIANT | NONCOMPLIANT | UNVERIFIABLE | ERROR",
  "beverage_class":    "beer | spirits | wine | null",
  "extraction_model":  "anthropic/claude-haiku-4-5-20251001",
  "panels_provided":   ["front", "back"],
  "input_tokens":      2634,
  "output_tokens":     478,
  "duration_ms":       6240,
  "issues": [
    {"rule_id": "R-GW-01", "severity": "warning", "field": "gws_present"}
  ],
  "extraction_result": { ... full ExtractionResult dict including all field values ... },
  "model_error":       null
}
```

**Notes on current implementation gaps vs. original ADR-010:**
- No `image_id` (SHA-256 of upload bytes) — cannot correlate a specific image to its log entry without timestamps
- No original filename or image metadata (dimensions, bytes)
- No preprocessing record (preprocessing not implemented — ADR-008)
- No fallback model tracking in the log record (the `extraction_model` field records which model was ultimately used, but not whether fallback was triggered)
- `issues` in the log are truncated vs. the API response: `found`, `expected`, and `not_found` fields are omitted

---

## Audit log sensitivity levels

Three strategies are available. The choice depends on the deployment context and the privacy requirements for label content.

### Level A — Minimal / SHA (original design intent)

**What is logged:** `request_id`, `timestamp`, `image_sha256` (SHA-256 hex of original upload bytes), `model`, `panels_provided`, `verdict`, rule IDs and severities (no `found`/`expected` values), `input_tokens`, `output_tokens`, `duration_ms`.

**What is NOT logged:** extracted field values, bottler addresses, brand names, GWS text, or any label content.

**Reproduction:** a dispute can be investigated by re-submitting the original image (identified by SHA-256) with the same model. The SHA confirms the verdict was made on the same bytes.

**Trade-offs:**
- ✅ No sensitive label content persisted beyond the request lifecycle
- ✅ Satisfies the original NFR-06 (no persistent storage of sensitive data)
- ✅ Smallest log volume (~300 bytes/record)
- ❌ Cannot diagnose model hallucinations or extraction errors without the original image
- ❌ More work to implement: requires computing SHA-256 of upload bytes and restructuring `audit.py`

### Level B — Schema-only / confidence map (intermediate)

**What is logged:** Everything in Level A, plus per-field confidence levels (`high | low | not_found`) but not field values.

**Example:**
```json
"field_confidence": {
  "brand_name": "high", "gws_present": "high", "gws_body": "low",
  "bottler_address": "not_found", ...
}
```

**Trade-offs:**
- ✅ Supports field-coverage analysis and diagnosing why a verdict was reached
- ✅ No label text content is persisted
- ✅ Sufficient to reproduce the verdict given the same image — if `gws_body` was `low` you know why R-GW-02 fired as a warning
- ❌ Cannot detect model hallucinations in specific field values (you know GWS was read at low confidence, but not what text was returned)

### Level C — Full extraction (current implementation)

**What is logged:** Everything above, plus the complete `ExtractionResult` dict including all extracted field values.

**Trade-offs:**
- ✅ Enables full post-hoc analysis: can detect hallucinations, reproduce the extraction, diagnose any issue without the original image
- ✅ Easiest to implement (just serialize the result dict)
- ❌ Logs label content that may be confidential or regulated: brand names, bottler addresses, GWS text, country of origin
- ❌ On Railway, log content is accessible via the Railway log stream — treat as sensitive
- ❌ Larger log volume (~2–5 KB/record)

### Recommendation

For the current **local prototype**: Level C is acceptable. `audit_logs/` is gitignored and stays on the developer machine.

For **Railway deployment with the prototype key**: Level C is borderline. The Railway log stream is accessible to anyone with Railway project access. If only the developer and interviewer have access, it is acceptable. If the URL is shared more broadly, upgrade to Level B.

For **any production or multi-tenant deployment**: Level A or Level B. The SHA-based approach in Level A was the correct original design; implementing it is a one-day task (add `hashlib.sha256(image_bytes).hexdigest()` at the upload boundary, thread it through to the audit record, restructure `audit.py` to separate the sensitivity layers).

---

## Original design elements not yet built

The following elements from the original ADR-010 have not been implemented and are deferred:

- `image_id` (SHA-256) field in the log and API receipt
- `receipt` object in the API response (linking log entry to response for dispute resolution)
- Image metadata (dimensions, bytes) in the log
- Preprocessing record (depends on ADR-008 preprocessing pipeline, also not built)
- Fallback trigger flag

These are the production hardening items; the prototype is functional without them.

---

## Threading and process model

The current `audit.py` is **thread-safe within a single process** (uses `threading.Lock()`). It is **not safe across multiple worker processes** (e.g. `uvicorn --workers 4`). For single-worker Railway deployment this is acceptable. For multi-worker deployments, replace with a structured log sink (Cloud Logging, Datadog, etc.) rather than attempting cross-process file locking.

---

## Storage

For the prototype: log to `audit_logs/YYYY-MM-DD.jsonl` in the repo root (gitignored). Files are not persisted across Railway deployments (acceptable for a prototype). For production: ship to structured logging using the same JSON schema.

## Access

The audit log is not exposed via the public API in v1. It is accessible to operators via Railway's log stream or by exec into the container.
