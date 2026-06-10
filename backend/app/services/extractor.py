"""
Layer 1 — AI extraction.

Sends one or two label images to the Claude vision API and returns a parsed
ExtractionResult ready for the Layer 2 compliance checker.

Errors from the model API (auth, rate-limit, server, JSON parse failure) are
returned as ExtractionError rather than raised, so the caller always has
something to audit-log and can decide independently whether to retry.

Two-panel strategy
------------------
When both front and back images are provided, each is extracted independently
with the same prompt (the panel_hint is advisory — written to the prompt so the
model can orient itself, but not used in any branching logic).  The two dicts
are then merged field-by-field: highest confidence wins; ties go to the
non-null value.  This tolerates flipped submissions naturally.  See ADR-011.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import anthropic

from backend.app.config import ANTHROPIC_API_KEY, EXTRACTION_MODEL
from backend.app.services.compliance_checker import ExtractionResult

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are an expert at reading alcoholic beverage labels for TTB regulatory \
compliance. Extract the requested fields from the label image and return a \
single JSON object. Do not explain or add commentary — return only the JSON \
object, with no markdown code fences.
"""

_USER_TEMPLATE = """\
Extract all fields from this alcoholic beverage label image.{panel_note}

Return a JSON object with this exact structure (no extra keys, no omitted keys):

{{
  "schema_version": "1.0",
  "readable": <true if you can interpret the image, false otherwise>,
  "beverage_class": <"beer" | "spirits" | "wine" | null>,
  "panels_provided": [<list containing "front" and/or "back" based on visible panels>],
  "extraction_model": "{model}",
  "fields": {{
    "brand_name":          {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "class_type":          {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "abv_pct":             {{"value": <number|null>, "confidence": <"high"|"low"|"not_found">}},
    "abv_text":            {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "proof":               {{"value": <number|null>, "confidence": <"high"|"low"|"not_found">}},
    "net_contents_metric": {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "net_contents_us":     {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "bottler_name":        {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "bottler_address":     {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "country_of_origin":   {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_present":         {{"value": <true|false|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_header":          {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_body":            {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_header_bold":     {{"value": <true|false|null>, "confidence": <"high"|"low"|"not_found">}},
    "gws_body_bold":       {{"value": <true|false|null>, "confidence": <"high"|"low"|"not_found">}},
    "sulfite_declaration": {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "vintage":             {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}},
    "appellation":         {{"value": <string|null>, "confidence": <"high"|"low"|"not_found">}}
  }}
}}

Confidence rules (apply to every field):
  "high"      — you can read the value clearly, OR you are certain the field
                is absent from this image (value must be null in that case).
  "low"       — the field appears to exist but text is partially obscured,
                small, in an unusual font, or otherwise ambiguous.
  "not_found" — the field does not appear anywhere in this image.  It may be
                on another panel.  value MUST be null.

Additional extraction rules:
  gws_header / gws_body : transcribe verbatim, exactly as printed including
                          punctuation and capitalisation.
  abv_pct               : numeric only, no % sign  (e.g. 5.2 not "5.2%").
  proof                 : numeric only, no "Proof" word  (e.g. 94.0).
  gws_header_bold / gws_body_bold : true if the text visually appears bold,
                          false if it does not, null if you cannot tell.
"""


# ---------------------------------------------------------------------------
# ExtractionError
# ---------------------------------------------------------------------------

@dataclass
class ExtractionError:
    """
    Non-fatal model API or parse error.

    status_code is the HTTP status from the provider when available.
    See audit.py for production action recommendations per status code.
    """
    status_code: int | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"status_code": self.status_code, "message": self.message}


# ---------------------------------------------------------------------------
# Panel merger
# ---------------------------------------------------------------------------

_CONF_RANK = {"high": 2, "low": 1, "not_found": 0}


def _merge_panels(front: dict, back: dict) -> dict:
    """
    Merge two single-panel extraction dicts into one.

    Per ADR-011: for each field take the value with the higher confidence;
    ties go to the non-null value.  Top-level metadata comes from front.
    panels_provided is the union of both.
    """
    merged = dict(front)
    merged["panels_provided"] = sorted(
        set(front.get("panels_provided", []) + back.get("panels_provided", []))
    )

    front_fields: dict = front.get("fields", {})
    back_fields: dict  = back.get("fields", {})

    merged_fields: dict[str, Any] = {}
    for name in set(front_fields) | set(back_fields):
        fv = front_fields.get(name, {"value": None, "confidence": "not_found"})
        bv = back_fields.get(name, {"value": None, "confidence": "not_found"})
        fr, br = _CONF_RANK.get(fv["confidence"], 0), _CONF_RANK.get(bv["confidence"], 0)
        if fr > br:
            chosen = fv
        elif br > fr:
            chosen = bv
        else:
            # Same confidence — prefer the non-null value
            chosen = fv if fv["value"] is not None else bv
        merged_fields[name] = chosen

    merged["fields"] = merged_fields
    return merged


# ---------------------------------------------------------------------------
# Single-panel extraction
# ---------------------------------------------------------------------------

def _extract_single(
    image_bytes: bytes,
    media_type: str,
    panel_hint: str | None,
    client: anthropic.Anthropic,
    model: str,
) -> tuple[dict | None, ExtractionError | None]:
    """Call the model for one panel image. Returns (raw_dict, error)."""
    image_b64 = base64.standard_b64encode(image_bytes).decode()
    panel_note = f"  (This appears to be the {panel_hint} panel.)" if panel_hint else ""
    prompt = _USER_TEMPLATE.format(panel_note=panel_note, model=model)

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=_SYSTEM,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError as exc:
        return None, ExtractionError(status_code=401, message=str(exc))
    except anthropic.RateLimitError as exc:
        return None, ExtractionError(status_code=429, message=str(exc))
    except anthropic.APIStatusError as exc:
        return None, ExtractionError(status_code=exc.status_code, message=str(exc))
    except Exception as exc:  # network errors, etc.
        return None, ExtractionError(status_code=None, message=str(exc))

    raw = response.content[0].text.strip()
    # Strip markdown code fences if the model wraps the JSON despite the instruction
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(raw), None
    except json.JSONDecodeError as exc:
        snippet = raw[:400].replace("\n", " ")
        return None, ExtractionError(
            status_code=None,
            message=f"JSON parse error: {exc} — raw response begins: {snippet}",
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(
    front_bytes: bytes,
    front_media_type: str,
    back_bytes: bytes | None = None,
    back_media_type: str | None = None,
    model: str | None = None,
) -> tuple[ExtractionResult | None, ExtractionError | None, float]:
    """
    Run Layer 1 extraction on one or two panel images.

    Returns (result, error, duration_ms).
    Exactly one of result/error will be non-None.
    duration_ms covers the total wall-clock time for all API calls.
    """
    model = model or EXTRACTION_MODEL
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    t0 = time.monotonic()

    front_dict, err = _extract_single(front_bytes, front_media_type, "front", client, model)
    if err:
        return None, err, (time.monotonic() - t0) * 1000

    if back_bytes and back_media_type:
        back_dict, err = _extract_single(back_bytes, back_media_type, "back", client, model)
        if err:
            return None, err, (time.monotonic() - t0) * 1000
        merged = _merge_panels(front_dict, back_dict)
    else:
        merged = front_dict

    duration_ms = (time.monotonic() - t0) * 1000

    try:
        result = ExtractionResult.from_dict(merged)
    except Exception as exc:
        return None, ExtractionError(status_code=None, message=f"Schema parse error: {exc}"), duration_ms

    return result, None, duration_ms
