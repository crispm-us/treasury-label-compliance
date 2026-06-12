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

import asyncio
import dataclasses
import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

from PIL import Image, ImageOps

from fastapi import FastAPI, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from backend.app.config import API_KEY, AUDIT_ENABLED, EXTRACTION_MODEL
from backend.app.models.application import ApplicationFields, provided_field_names
from backend.app.services.application_checker import check as check_application
from backend.app.services.audit import write_entry
from backend.app.services.compliance_checker import ComplianceResult, Issue, Verdict, check_compliance
from backend.app.services.extractor import ExtractionError, extract

# ---------------------------------------------------------------------------
# Optional API key authentication
# ---------------------------------------------------------------------------
# Set the API_KEY environment variable to require X-API-Key on all requests.
# Leave unset (or empty) for local development — no auth enforced.
# In Railway: add API_KEY to the environment dashboard before sharing the URL.

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def _require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if API_KEY and (not key or not secrets.compare_digest(key, API_KEY)):
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key header.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

# NFR-05 specified 10 req/min; 20/min chosen to allow comfortable evaluator access.
# Upgrade path: replace get_remote_address with a key_func reading X-Forwarded-For
# for accurate per-client limiting behind Railway's reverse proxy.
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="TTB Label Compliance API",
    version="0.1.0",
    description=(
        "Prototype — Layer 1 (AI vision extraction) + "
        "Layer 2 (deterministic TTB compliance check)."
    ),
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

MAX_IMAGE_BYTES: int = 10 * 1024 * 1024  # 10 MB per image

# Magic-byte signatures for supported image formats.
# These are checked against the actual file content, independent of the
# Content-Type header supplied by the client.
_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC  = b"\x89PNG\r\n\x1a\n"


def _apply_exif_rotation(data: bytes, media_type: str) -> tuple[bytes, str]:
    """
    Correct image orientation using EXIF metadata before model ingestion.

    Phone cameras embed orientation in EXIF rather than rotating pixels, so the
    raw bytes can be 90° (or 180°) off from what a human sees on screen.
    Sending a rotated image to the vision model causes GWS transcription errors:
    the model can read the short all-caps header but produces garbled or
    hallucinated body text for the long paragraph read sideways.

    Pillow's exif_transpose() applies the EXIF rotation to pixel data and strips
    the orientation tag so the model always receives an upright image.

    Returns (corrected_bytes, new_media_type).  If no EXIF rotation is needed
    the original bytes and media_type are returned unchanged (zero cost).  On any
    Pillow error the originals are returned so the request still reaches the model.
    """
    try:
        img = Image.open(BytesIO(data))
        rotated = ImageOps.exif_transpose(img)
        if rotated is img:
            return data, media_type          # No rotation needed — return original
        if rotated.mode not in ("RGB", "L"):
            rotated = rotated.convert("RGB") # JPEG requires RGB (not RGBA / P)
        buf = BytesIO()
        rotated.save(buf, format="JPEG", quality=90)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return data, media_type              # Fallback: send original to model


def _make_label_ref(filename: str | None, ts_compact: str) -> str | None:
    """
    Construct a human-readable unique reference for an uploaded label image.

    Format: {stem}-{YYYYMMDDTHHmmss}Z  (e.g. IMG_091-20260611T143022Z)

    The stem preserves the user's original filename for manual correlation;
    the compact UTC timestamp makes the reference unique to the second.
    Both components appear in the audit log entry (front_label_ref / back_label_ref),
    fulfilling FR-07 (receipt data for label submissions).
    """
    if not filename:
        return None
    stem = Path(filename).stem
    return f"{stem}-{ts_compact}Z"


def _sniff_media_type(data: bytes) -> str | None:
    """Return the MIME type detected from magic bytes, or None if unrecognized."""
    if data[:3] == _JPEG_MAGIC:
        return "image/jpeg"
    if data[:8] == _PNG_MAGIC:
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


async def _read_validated(upload: UploadFile, field: str) -> tuple[bytes, str]:
    """
    Read an uploaded image after validating:
      1. Content-Type header is an allowed MIME type  → 415
      2. File does not exceed MAX_IMAGE_BYTES         → 413
      3. Magic bytes match a supported image format   → 415

    Returns (data, sniffed_mime_type).  The sniffed type is used for the
    LiteLLM data URI rather than the client-declared Content-Type, so a
    client sending PNG bytes with Content-Type: image/jpeg still works.
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
    sniffed = _sniff_media_type(data)
    if sniffed is None:
        raise HTTPException(
            status_code=415,
            detail=f"{field}: file content is not a recognized image format (JPEG, PNG, or WebP)",
        )
    return data, sniffed


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
    mode:                  Literal["regulation_only", "application_match"]
    application_fields_provided: list[str]
    beverage_class:        str | None
    issues:                list[IssueOut]
    extraction_model:      str
    audit_logged:          bool
    partial_verification:  bool  # True when NONCOMPLIANT and any issue has not_found=True
                                 # (violation confirmed but at least one field was not visible,
                                 # so the full picture may differ). See ADR-011.
    input_tokens:          int | None   # prompt tokens charged by the model API (None on error)
    output_tokens:         int | None   # completion tokens charged by the model API (None on error)
    # --- Receipt fields (FR-07) -------------------------------------------
    # Provide the caller with stable references to correlate the API response
    # with the audit log entry without a separate database.
    front_filename:        str | None   # original filename supplied by the client
    front_label_ref:       str | None   # {stem}-{UTC}Z — human-readable unique reference
    front_sha256:          str | None   # SHA-256 hex of received bytes (pre-EXIF-rotation)
    back_filename:         str | None
    back_label_ref:        str | None
    back_sha256:           str | None
    schema_violations:     int          # count of Layer 1 non-dict field values (model prompt non-compliance)
    duration_ms:           float | None # server-side extraction wall time in milliseconds


def _verdict_from_issues(issues: list[Issue]) -> Verdict:
    if any(i.severity == "error" for i in issues):
        return "NONCOMPLIANT"
    if issues:
        return "UNVERIFIABLE"
    return "COMPLIANT"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@app.post("/v1/check", response_model=CheckResponse, dependencies=[Security(_require_api_key)])
@limiter.limit("20/minute")
async def check_label(
    request: Request,
    front: Annotated[
        UploadFile,
        File(description="Front panel image — JPEG, PNG, or WebP"),
    ],
    back: Annotated[
        UploadFile | None,
        File(description="Back panel image — optional; improves verification coverage"),
    ] = None,
    application: Annotated[
        str | None,
        Form(description="Optional COLA application JSON for Mode A application-matching"),
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
    now        = datetime.now(timezone.utc)
    timestamp  = now.isoformat()
    ts_compact = now.strftime("%Y%m%dT%H%M%S")  # for label_ref: 20260611T143022

    # --- Mode A: optional application JSON --------------------------------------
    mode: Literal["regulation_only", "application_match"] = "regulation_only"
    application_fields: ApplicationFields | None = None
    application_fields_provided: list[str] = []
    if application is not None and application.strip():
        try:
            application_fields = ApplicationFields.model_validate_json(application)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=f"application: invalid JSON or schema — {exc}",
            ) from exc
        mode = "application_match"
        application_fields_provided = provided_field_names(application_fields)

    # --- Read and validate uploads ----------------------------------------------
    front_bytes, front_media_type = await _read_validated(front, "front")
    front_sha256   = hashlib.sha256(front_bytes).hexdigest()   # hash pre-rotation bytes (FR-07)
    front_label_ref = _make_label_ref(front.filename, ts_compact)
    front_bytes, front_media_type = _apply_exif_rotation(front_bytes, front_media_type)

    if back:
        back_bytes, back_media_type = await _read_validated(back, "back")
        back_sha256    = hashlib.sha256(back_bytes).hexdigest()
        back_label_ref = _make_label_ref(back.filename, ts_compact)
        back_bytes, back_media_type = _apply_exif_rotation(back_bytes, back_media_type)
    else:
        back_bytes, back_media_type = None, None
        back_sha256    = None
        back_label_ref = None

    # --- Layer 1: extraction ---------------------------------------------------
    result, model_error, duration_ms, usage, schema_violations = await asyncio.to_thread(
        extract,
        front_bytes=front_bytes,
        front_media_type=front_media_type,
        back_bytes=back_bytes,
        back_media_type=back_media_type,
    )

    # --- Layer 2: compliance check ---------------------------------------------
    if result is not None:
        compliance = check_compliance(result)
        extraction_dict = dataclasses.asdict(result)  # recursively converts nested dataclasses
    else:
        compliance     = ComplianceResult(verdict="ERROR", beverage_class=None, issues=[])
        extraction_dict = None

    issues = list(compliance.issues)
    verdict = compliance.verdict

    # --- Mode A: application-matching (after Layer 2) --------------------------
    if application_fields is not None and result is not None and verdict != "ERROR":
        issues.extend(check_application(result.fields, application_fields))
        verdict = _verdict_from_issues(issues)

    # --- partial_verification flag ---------------------------------------------
    partial_verification = (
        verdict == "NONCOMPLIANT"
        and any(i.not_found for i in issues)
    )

    # --- Audit -----------------------------------------------------------------
    # Audit failure must not surface as HTTP 500 — the compliance result is
    # already computed and the caller deserves a response.  Log the failure
    # internally and set audit_logged=False so callers know the entry was lost.
    audit_logged_ok = AUDIT_ENABLED
    try:
        write_entry({
            "request_id":             request_id,
            "timestamp":              timestamp,
            "extraction_model":       result.extraction_model if result is not None else EXTRACTION_MODEL,
            "extraction_duration_ms": round(duration_ms, 1),
            "usage":                  usage,
            "model_error":            model_error.to_dict() if model_error else None,
            "extraction_result":      extraction_dict,
            "verdict":                verdict,
            "beverage_class":         compliance.beverage_class,
            "issues": [
                {"rule_id": i.rule_id, "severity": i.severity, "field": i.field}
                for i in issues
            ],
            # Receipt fields (FR-07)
            "front_filename":    front.filename,
            "front_label_ref":   front_label_ref,
            "front_sha256":      front_sha256,
            "back_filename":     back.filename if back else None,
            "back_label_ref":    back_label_ref,
            "back_sha256":       back_sha256,
            # Layer 1 quality metrics
            "schema_violations": schema_violations,
        })
    except Exception:
        audit_logged_ok = False

    # --- Response --------------------------------------------------------------
    return CheckResponse(
        request_id=request_id,
        timestamp=timestamp,
        verdict=verdict,
        mode=mode,
        application_fields_provided=application_fields_provided,
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
            for i in issues
        ],
        extraction_model=result.extraction_model if result is not None else EXTRACTION_MODEL,
        audit_logged=audit_logged_ok,
        partial_verification=partial_verification,
        input_tokens=usage.get("input_tokens")  if usage else None,
        output_tokens=usage.get("output_tokens") if usage else None,
        front_filename=front.filename,
        front_label_ref=front_label_ref,
        front_sha256=front_sha256,
        back_filename=back.filename if back else None,
        back_label_ref=back_label_ref,
        back_sha256=back_sha256,
        schema_violations=len(schema_violations),
        duration_ms=round(duration_ms, 1),
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "audit_enabled": AUDIT_ENABLED}


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

@app.get("/version")
async def version() -> dict:
    """Return deployment metadata. Useful for UI display and debugging."""
    import os
    return {
        "commit":      os.getenv("RAILWAY_GIT_COMMIT_SHA", "dev")[:7],
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", "dev"),
        "branch":      os.getenv("RAILWAY_GIT_BRANCH", ""),
    }


# ---------------------------------------------------------------------------
# Frontend — serve React app from frontend/dist/
# ---------------------------------------------------------------------------
# Mounted last so all API routes take precedence.
# Conditional on the dist directory existing so the server still starts
# during development before `npm run build` has been run.

_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
