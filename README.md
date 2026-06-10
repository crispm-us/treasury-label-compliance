# TTB Label Compliance — Prototype

A REST API that checks alcoholic beverage labels for compliance with US Alcohol and Tobacco Tax and Trade Bureau (TTB) labeling regulations (27 CFR Parts 4, 5, 7, and 16).

---

## Architecture

The system uses a deliberate two-layer design (see [ADR-009](docs/adr/009-two-layer-architecture.md)):

```
POST /v1/check  ──►  Layer 1: AI extraction  ──►  Layer 2: Deterministic checker
                     (Claude vision API)           (Pure Python, no AI)
                     Returns ExtractionResult      Returns ComplianceResult
                     JSON schema (ADR-011)         Verdict + rule-mapped Issues
```

**Layer 1** sends the label image to the Claude vision API with a structured extraction prompt. It returns a typed JSON object with 18 fields (brand name, ABV, Government Warning Statement text, etc.), each with a confidence level (`high | low | not_found`). This layer never makes a compliance judgment.

**Layer 2** applies deterministic rules against the extracted fields. Every issue maps to a rule ID (e.g. `R-GW-01`, `R-DS-03`) documented in [`docs/rules/`](docs/rules/). This layer contains no AI calls and is fully unit-testable with fixture JSON.

This separation means the compliance logic can be audited, version-controlled, and tested independently of the model — important for a regulatory context.

---

## Two-panel support

Submit both front and back images for higher coverage. The extractor runs the same prompt on each panel independently and merges the results field-by-field, taking the highest-confidence value. A `panels_provided` field in every response records which panels were used.

---

## Verdicts

| Verdict | Meaning |
|---|---|
| `COMPLIANT` | All checked rules pass; no issues of any kind |
| `NONCOMPLIANT` | At least one definitive rule violation (error severity) |
| `UNVERIFIABLE` | No errors, but one or more fields could not be verified (low confidence or not visible in submitted image) |
| `ERROR` | Image could not be read, or model API failure |

When `verdict=NONCOMPLIANT` and some mandatory fields were not visible in the submitted images, `partial_verification=true` signals that the violation is confirmed but the full label could not be checked.

---

## Quick start

Requires Python ≥ 3.10 and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/crispm-us/treasury-label-compliance
cd treasury-label-compliance

cp .env.example .env
# edit .env — set ANTHROPIC_API_KEY

uv run uvicorn backend.app.main:app --reload
```

The API is now running at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## Usage

### Health check

```bash
curl http://localhost:8000/healthz
```

### Single panel

```bash
curl -X POST http://localhost:8000/v1/check \
  -F "front=@test-labels/beer/sunset-ale-R-GW-01-front.jpg"
```

### Two panels

```bash
curl -X POST http://localhost:8000/v1/check \
  -F "front=@test-labels/spirits/blue-ridge-rye-front.jpg" \
  -F "back=@test-labels/spirits/blue-ridge-rye-back.jpg"
```

### With API key (Railway deployment)

```bash
curl -X POST https://<your-railway-url>/v1/check \
  -H "X-API-Key: <your-key>" \
  -F "front=@label-front.jpg"
```

---

## API reference

### `POST /v1/check`

**Input** (multipart/form-data)

| Field | Type | Required | Description |
|---|---|---|---|
| `front` | image/jpeg, image/png, or image/webp | Yes | Front panel |
| `back` | image/jpeg, image/png, or image/webp | No | Back panel |

**Response** (200 OK)

```json
{
  "request_id": "uuid",
  "timestamp": "2026-01-01T00:00:00+00:00",
  "verdict": "NONCOMPLIANT",
  "beverage_class": "beer",
  "issues": [
    {
      "rule_id": "R-GW-01",
      "severity": "error",
      "field": "gws_present",
      "found": false,
      "expected": "Government Warning Statement must appear on every alcoholic beverage label ≥0.5% ABV (27 CFR §16.21)",
      "not_found": false
    }
  ],
  "extraction_model": "claude-haiku-4-5-20251001",
  "audit_logged": true,
  "partial_verification": false
}
```

**Error responses**

| Status | Condition |
|---|---|
| 401 | `API_KEY` is configured and `X-API-Key` header is missing or wrong |
| 415 | Unsupported image format (not JPEG, PNG, or WebP) |

### `GET /healthz`

Returns `{"status": "ok", "audit_enabled": true}`.

---

## Running tests

All tests mock the extraction layer — no API key or network required.

```bash
uv run --with pytest pytest tests/ -v
```

36 tests covering: verdict paths (compliant, noncompliant, unverifiable, error), rule-specific cases (R-GW-01/02/03, R-DS-03, R-WN-09, R-MB-03), model API failure modes (401, 429), partial verification flag, API key auth, two-panel merge, and input validation.

---

## Configuration

See [`.env.example`](.env.example) for all environment variables. Key settings:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required. Claude API key. |
| `EXTRACTION_MODEL` | `claude-haiku-4-5-20251001` | Model used for Layer 1 extraction. |
| `API_KEY` | _(empty)_ | When set, requires `X-API-Key` header on all requests. Use for Railway deployment. |
| `AUDIT_ENABLED` | `true` | Set to `false` to disable JSONL audit log writes. |

---

## Project documentation

- [`docs/adr/`](docs/adr/) — Architecture Decision Records (ADR-001 through ADR-011)
- [`docs/rules/`](docs/rules/) — TTB rule reference by beverage class
- [`docs/requirements-analysis.md`](docs/requirements-analysis.md) — Regulatory scope and rule mapping
- [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) — What is built vs. deliberately deferred
- [`docs/DEPLOYMENT_CHECKLIST.md`](docs/DEPLOYMENT_CHECKLIST.md) — Pre-push and Railway deployment steps

---

## Scope and limitations

This is a working prototype, not a production compliance tool. See [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) for a full inventory of what is implemented and what is deferred.

Notable limitations:

- **Model hallucination**: The vision model can fabricate field values (particularly Government Warning Statement text) on low-quality or synthetic images. Production use requires real label scans and systematic hallucination evaluation.
- **R-GW-04 deferred**: Bold-type requirement for the GWS header is captured in the schema but not enforced — vision-model bold detection is not reliable enough without a calibration baseline.
- **No retry/backoff**: Layer 1 makes a single model call per panel with no retry on transient failures (see ADR-008).
- **No image preprocessing**: No size limits beyond what the model API enforces, no magic-byte MIME validation, no orientation correction.
- **Audit log**: Written to local JSONL files. Contains extracted label text — treat as sensitive and do not commit.
