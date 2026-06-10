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

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from backend.app.config import AUDIT_ENABLED, EXTRACTION_MODEL
from backend.app.services.audit import write_entry
from backend.app.services.compliance_checker import ComplianceResult, check_compliance
from backend.app.services.extractor import ExtractionError, extract

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TTB Label Compliance API",
    version="0.1.0",
    description=(
        "Prototype — Layer 1 (Claude vision extraction) + "
        "Layer 2 (deterministic TTB compliance check)."
    ),
)

# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}


class IssueOut(BaseModel):
    rule_id:  str
    severity: str   # "error" | "warning"
    field:    str
    found:    object
    expected: str


class CheckResponse(BaseModel):
    request_id:       str
    timestamp:        str
    verdict:          str   # COMPLIANT | NONCOMPLIANT | UNVERIFIABLE | ERROR
    beverage_class:   str | None
    issues:           list[IssueOut]
    extraction_model: str
    audit_logged:     bool
    # Future (ADR-011 §"Partial extraction with high-confidence violation"):
    #   partial_verification: bool


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.post("/v1/check", response_model=CheckResponse)
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

    # --- Validate content types ------------------------------------------------
    if front.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"front: unsupported type '{front.content_type}'. Use JPEG, PNG, or WebP.",
        )
    if back and back.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"back: unsupported type '{back.content_type}'. Use JPEG, PNG, or WebP.",
        )

    front_bytes = await front.read()
    back_bytes  = await back.read() if back else None

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
            )
            for i in compliance.issues
        ],
        extraction_model=EXTRACTION_MODEL,
        audit_logged=AUDIT_ENABLED,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "audit_enabled": AUDIT_ENABLED}
