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
import secrets
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Annotated

from PIL import Image, ImageOps

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
    if API_KEY and (not key or not secrets.compare_digest(key, API_KEY)):
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
    beverage_class:        str | None
    issues:                list[IssueOut]
    extraction_model:      str
    audit_logged:          bool
    partial_verification:  bool  # True when NONCOMPLIANT and any issue has not_found=True
                                 # (violation confirmed but at least one field was not visible,
                                 # so the full picture may differ). See ADR-011.
    input_tokens:          int | None   # prompt tokens charged by the model API (None on error)
    output_tokens:         int | None   # completion tokens charged by the model API (None on error)


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
    front_bytes, front_media_type = await _read_validated(front, "front")
    front_bytes, front_media_type = _apply_exif_rotation(front_bytes, front_media_type)
    if back:
        back_bytes, back_media_type = await _read_validated(back, "back")
        back_bytes, back_media_type = _apply_exif_rotation(back_bytes, back_media_type)
    else:
        back_bytes, back_media_type = None, None

    # --- Layer 1: extraction ---------------------------------------------------
    result, model_error, duration_ms, usage = extract(
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

    # --- partial_verification flag ---------------------------------------------
    partial_verification = (
        compliance.verdict == "NONCOMPLIANT"
        and any(i.not_found for i in compliance.issues)
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
            "verdict":                compliance.verdict,
            "beverage_class":         compliance.beverage_class,
            "issues": [
                {"rule_id": i.rule_id, "severity": i.severity, "field": i.field}
                for i in compliance.issues
            ],
        })
    except Exception:
        audit_logged_ok = False

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
        extraction_model=result.extraction_model if result is not None else EXTRACTION_MODEL,
        audit_logged=audit_logged_ok,
        partial_verification=partial_verification,
        input_tokens=usage.get("input_tokens")  if usage else None,
        output_tokens=usage.get("output_tokens") if usage else None,
    )


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "audit_enabled": AUDIT_ENABLED}
