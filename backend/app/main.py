"""
TTB Label Compliance API

POST /v1/check   Submit one or two label images; get a compliance verdict.

Start:
    uv run uvicorn backend.app.main:app --reload

Disable audit logging for local testing:
    AUDIT_ENABLED=false uv run uvicorn backend.app.main:app --reload

Docs (auto-generated):
    http://localhost:8000/docs
"""
from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Security, UploadFile
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from backend.app.config import API_KEY, AUDIT_ENABLED, EXTRACTION_MODEL
from backend.app.services.audit import write_entry
from backend.app.services.compliance_checker import ComplianceResult, check_compliance
from backend.app.services.extractor import ExtractionError, extract

# ---------------------------------------------------------------------------
# Optional API key authentication
# ---------------------------------------------------------------------------
# Set the API_KEY environment variable to require X-API-Key on all requests.
# Leave unset (or empty) for local development — no auth enforced.
# In Railway: add API_KEY to the environment dashboard before sharing the URL.

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TTB Label Compliance API",
    version="0.1.0",
    description=(
        "Prototype — Layer 1 (AI vision extraction) + "
        "Layer 2 (deterministic TTB compliance check)."
    ),
)

# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}

MAX_IMAGE_BYTES: int = 10 * 1024 * 1024  # 10 MB per image

# Magic-byte signatures for supported image formats.
# These are checked against the actual file content, independent of the
# Content-Type header supplied by the client.
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC  = b"\x89PNG\r\n\x1a\n"


def _sniff_media_type(data: bytes) -> str | None:
    """Return the MIME type detected from magic bytes, or None if unrecognized."""
    if data[:3] == _JPEG_MAGIC:
        return "image/jpeg"
    if data[:8] == _PNG_MAGIC:
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _read_validated(upload: UploadFile, field: str) -> bytes:
    """
    Read an uploaded image after validating:
      1. Content-Type header is an allowed MIME type  → 415
      2. File does not exceed MAX_IMAGE_BYTES         → 413
      3. Magic bytes match a supported image format   → 415

    Reading one extra byte lets us detect overflow without buffering the
    entire oversized payload first.
    """
    if upload.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"{field}: unsupported type '{upload.content_type}'. Use JPEG, PNG, or WebP.",
        )
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"{field}: file exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit",
        )
    if _sniff_media_type(data) is None:
        raise HTTPException(
            status_code=415,
            detail=f"{field}: file content is not a recognized image format (JPEG, PNG, or WebP)",
        )
    return data


class IssueOut(BaseModel):
    rule_id:   str
    severity:  str    # "error" | "warning"
    field:     str
    found:     object
    expected:  str
    not_found: bool   # True when field was absent from the submitted image(s)


class CheckResponse(BaseModel):
    request_id:            str
    timestamp:             str
    verdict:               str   # COMPLIANT | NONCOMPLIANT | UNVERIFIABLE | ERROR
    beverage_class:        str | None
    issues:                list[IssueOut]
    extraction_model:      str
    audit_logged:          bool
    partial_verification:  bool  # True when NONCOMPLIANT but some mandatory fields
                                 # were not_found (violation confirmed, full check impossible)
                                 # See ADR-011 §"Partial extraction with high-confidence violation"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.post("/v1/check", response_model=CheckResponse, dependencies=[Security(_require_api_key)])
async def check_label(
    front: Annotated[
        UploadFile,
        File(description="Front panel image — JPEG, PNG, or WebP"),
    ],
    back: Annotated[
        UploadFile | None,
        File(description="Back panel image — optional; improves verification coverage"),
    ] = None,
) -> CheckResponse:
    """
    Run a TTB compliance check on one or two label images.

    **front** is required; **back** is optional.  Submitting both panels
    increases the chance of a COMPLIANT or NONCOMPLIANT verdict (rather than
    UNVERIFIABLE) because mandatory fields may appear on either panel.

    The response includes:
    - **verdict**: `COMPLIANT`, `NONCOMPLIANT`, `UNVERIFIABLE`, or `ERROR`
    - **issues**: list of rule violations / warnings with rule IDs
    - **request_id**: echoed back for audit log correlation
    """
    request_id = str(uuid.uuid4())
    timestamp  = datetime.now(timezone.utc).isoformat()

    # --- Read and validate uploads ----------------------------------------------
    front_bytes = await _read_validated(front, "front")
    back_bytes  = await _read_validated(back, "back") if back else None

    # --- Layer 1: extraction ---------------------------------------------------
    result, model_error, duration_ms = extract(
        front_bytes=front_bytes,
        front_media_type=front.content_type,
        back_bytes=back_bytes,
        back_media_type=back.content_type if back else None,
    )

    # --- Layer 2: compliance check ---------------------------------------------
    if result is not None:
        compliance = check_compliance(result)
        extraction_dict = dataclasses.asdict(result)  # recursively converts nested dataclasses
    else:
        compliance     = ComplianceResult(verdict="ERROR", beverage_class=None, issues=[])
        extraction_dict = None

    # --- partial_verification flag ---------------------------------------------
    partial_verification = (
        compliance.verdict == "NONCOMPLIANT"
        and any(i.not_found for i in compliance.issues)
    )

    # --- Audit -----------------------------------------------------------------
    write_entry({
        "request_id":             request_id,
        "timestamp":              timestamp,
        "extraction_model":       EXTRACTION_MODEL,
        "extraction_duration_ms": round(duration_ms, 1),
        "model_error":            model_error.to_dict() if model_error else None,
        "extraction_result":      extraction_dict,
        "verdict":                compliance.verdict,
        "beverage_class":         compliance.beverage_class,
        "issues": [
            {"rule_id": i.rule_id, "severity": i.severity, "field": i.field}
            for i in compliance.issues
        ],
    })

    # --- Response --------------------------------------------------------------
    return CheckResponse(
        request_id=request_id,
        timestamp=timestamp,
        verdict=compliance.verdict,
        beverage_class=compliance.beverage_class,
        issues=[
            IssueOut(
                rule_id=i.rule_id,
                severity=i.severity,
                field=i.field,
                found=i.found,
                expected=i.expected,
                not_found=i.not_found,
            )
            for i in compliance.issues
        ],
        extraction_model=EXTRACTION_MODEL,
        audit_logged=AUDIT_ENABLED,
        partial_verification=partial_verification,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "audit_enabled": AUDIT_ENABLED}
