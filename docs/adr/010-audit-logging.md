# ADR-010: Audit Logging

Date: 2026-06-09
Status: Accepted

## Context

When the system produces a compliance verdict — especially a false positive (compliant label flagged as non-compliant) or a false negative (non-compliant label passed) — it must be possible to reconstruct exactly what was evaluated: which image, at what resolution, with what preprocessing, by which model. Without this, errors cannot be diagnosed or appealed.

Additionally, the image preprocessing pipeline (ADR-008) may have compressed or resized the image before sending it to the model. If a verdict was made on a degraded version of the image, that must be recorded.

## Decision

Every label evaluation event writes one log record. The log is **append-only** and stored as JSON Lines (`.jsonl`) — one JSON object per line.

### Log record schema

```json
{
  "event_id":           "uuid4 — unique identifier for this evaluation event",
  "timestamp":          "ISO 8601 UTC — when the evaluation was performed",
  "image_id":           "SHA-256 hex digest of the original image bytes — stable identifier",
  "original_filename":  "string or null — if provided by the client",
  "image_metadata": {
    "format":           "JPEG | PNG | WebP | HEIC | TIFF | GIF | PDF | unknown",
    "original_width_px":  "integer",
    "original_height_px": "integer",
    "original_size_bytes": "integer"
  },
  "preprocessing": {
    "was_preprocessed": "boolean — true if any resize/convert/compress was applied",
    "steps": [
      "converted HEIC→JPEG",
      "resized 4032×3024 → 1200×900",
      "JPEG quality 85"
    ],
    "sent_width_px":  "integer — dimensions of image actually sent to model",
    "sent_height_px": "integer",
    "sent_size_bytes": "integer",
    "backoff_attempt": "integer — 0 for normal path, 1+ for retries at higher resolution"
  },
  "model_config": {
    "primary_model":  "gemini/gemini-2.0-flash",
    "model_used":     "claude-haiku-4-5-20251001 — actual model that returned the response (may differ from primary if fallback triggered)",
    "fallback_triggered": "boolean",
    "timeout_seconds": 4.5
  },
  "mode":               "extract | verify — Mode B or Mode A",
  "extraction_result": {
    "beverage_type":  "spirits | wine | beer | unknown",
    "fields_found":   ["brand_name", "class_type", "alcohol_content", "net_contents", "government_warning"],
    "fields_low_confidence": ["bottler_name_address"],
    "fields_not_found": ["country_of_origin"]
  },
  "compliance_result": {
    "compliant":    "boolean",
    "error_count":  "integer",
    "warning_count": "integer",
    "issue_rule_ids": ["R-GW-03", "R-DS-04"]
  },
  "duration_ms": "integer — total wall-clock time for the evaluation"
}
```

### What is NOT logged

- The image itself (images are not persisted per NFR-06 / R-MS-05)
- The full extracted text or field values (may contain label content that is sensitive in a production context)
- The full compliance issue descriptions (available in the API response; not duplicated in the audit log)

The `image_id` (SHA-256 of original bytes) allows the original image to be re-submitted if investigation is needed — provided the submitter retained it.

### Storage

For the prototype: log to a rotating file (`audit.jsonl`) in the app's working directory. The file is not persisted across Railway deployments (acceptable for a prototype). For production: ship to structured logging (e.g., Cloud Logging, Datadog) using the same JSON schema.

### Access

The audit log is not exposed via the public API in v1. It is accessible to operators via Railway's log stream or by exec into the container.

## Consequences

- Every evaluation is traceable: `event_id` links the log record to the API response returned to the client
- False positives and false negatives can be investigated by re-submitting the original image (identified by `image_id`) and comparing against the logged `preprocessing` and `model_config`
- The `backoff_attempt` field specifically records whether a verdict was made on a compressed/resized image vs. the original
- No sensitive data is persisted beyond the request lifecycle; the log contains only metadata
- Log volume: one record per label evaluation, ~500 bytes/record — negligible at prototype scale

## Alternatives Considered

**No audit logging:** Acceptable for a toy demo; insufficient for a compliance tool where verdicts may be contested. Rejected.

**Log full images:** Violates NFR-06 (no persistent storage of sensitive data) and creates storage and privacy concerns. Rejected.

**Use a database (SQLite, PostgreSQL):** Adds infrastructure for no benefit at prototype scale. JSONL is portable, appendable, and trivially parseable. Rejected for v1; natural upgrade path for production.
