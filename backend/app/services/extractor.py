"""
Layer 1 — AI extraction via LiteLLM.

Sends one or two label images to the configured vision model and returns a
parsed ExtractionResult ready for the Layer 2 compliance checker.

LiteLLM provides a single interface across providers (Anthropic, Gemini,
OpenAI, etc.).  The active model is set by the EXTRACTION_MODEL environment
variable (default: anthropic/claude-haiku-4-5-20251001).  Fallback models
can be configured with EXTRACTION_FALLBACK_MODELS (comma-separated list).

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

Fallback strategy
-----------------
On a retryable error (anything except 400 and 401), the extractor tries each
model in EXTRACTION_FALLBACK_MODELS in order before giving up.  Auth errors
(401) and bad-request errors (400) are not retried — a different model will
not fix a malformed payload or an invalid key.  See ADR-001 and ADR-008.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

import litellm

from backend.app.config import EXTRACTION_FALLBACK_MODELS, EXTRACTION_MODEL
from backend.app.services.compliance_checker import ExtractionResult

# Suppress LiteLLM's verbose success logging; keep errors.
litellm.success_callback = []
litellm.set_verbose = False

# ---------------------------------------------------------------------------
# Extraction prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are an expert at reading alcoholic beverage labels for TTB regulatory \
compliance. Extract the requested fields from the label image and return a \
single JSON object. Do not explain or add commentary — return only the JSON \
object, with no markdown code fences.

Critical accuracy rules:
- Only transcribe text that is visually present and legible in the image.
- Do NOT reproduce text from memory or training data, especially the Government \
Warning Statement. If the GWS text is partially obscured or cut off, use \
confidence "low" — do not complete it from memory.
- Do NOT infer or guess field values. If a field is not clearly visible, use \
"not_found" or "low" confidence as appropriate.
- If you are uncertain whether text you see is the GWS or something else, \
transcribe exactly what is printed and use confidence "low".
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
                          punctuation and capitalization. Do NOT complete
                          from memory if text is cut off — use confidence "low".
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

    Recommended production action by status code (see ADR-008):
      401  — invalid or expired API key; do NOT retry or fall back to same provider
      400  — bad request (malformed payload, spending cap); do NOT retry
      429  — rate limited; exponential backoff with jitter before retry
      500  — provider server error; retry with jitter
      529  — provider overloaded (Anthropic-specific); retry with jitter
      None — network error or unexpected exception; retry with jitter
    """
    status_code: int | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"status_code": self.status_code, "message": self.message}


# ---------------------------------------------------------------------------
# Fallback policy
# ---------------------------------------------------------------------------

# Errors where retrying — even with a different provider — will not help.
_NO_RETRY_STATUS_CODES: frozenset[int] = frozenset({400, 401})

# ---------------------------------------------------------------------------
# Panel merger
# ---------------------------------------------------------------------------

_CONF_RANK = {"high": 2, "low": 1, "not_found": 0}


def _merge_panels(front: dict, back: dict) -> dict:
    """
    Merge two single-panel extraction dicts into one.

    Per ADR-011: for each field take the value with the higher confidence;
    ties go to the non-null value.

    Top-level metadata:
      readable        — True if EITHER panel is readable (fix: front=unreadable,
                        back=legible must not produce an ERROR verdict).
      beverage_class  — non-null value wins; front preferred on tie.
      panels_provided — union of both.
      extraction_model / schema_version — taken from front.
    """
    merged = dict(front)
    merged["panels_provided"] = sorted(
        set(front.get("panels_provided", []) + back.get("panels_provided", []))
    )
    # readable: True if either panel is readable
    merged["readable"] = front.get("readable", False) or back.get("readable", False)
    # beverage_class: prefer non-null
    merged["beverage_class"] = front.get("beverage_class") or back.get("beverage_class")

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
    model: str,
) -> tuple[dict | None, ExtractionError | None, int, int]:
    """
    Call the vision model for one panel image via LiteLLM.

    Uses the OpenAI messages format (system + user with image_url content).
    LiteLLM translates this to the appropriate wire format for each provider.

    Returns (raw_dict, error, input_tokens, output_tokens).
    Exactly one of raw_dict/error will be non-None; token counts are 0 on error.
    """
    image_b64 = base64.standard_b64encode(image_bytes).decode()
    panel_note = f"  (This appears to be the {panel_hint} panel.)" if panel_hint else ""
    prompt = _USER_TEMPLATE.format(panel_note=panel_note, model=model)

    try:
        response = litellm.completion(
            model=model,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_b64}"
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                },
            ],
        )
    except litellm.AuthenticationError as exc:
        return None, ExtractionError(status_code=401, message=str(exc)), 0, 0
    except litellm.RateLimitError as exc:
        return None, ExtractionError(status_code=429, message=str(exc)), 0, 0
    except litellm.BadRequestError as exc:
        return None, ExtractionError(status_code=400, message=str(exc)), 0, 0
    except litellm.APIError as exc:
        status = getattr(exc, "status_code", None)
        return None, ExtractionError(status_code=status, message=str(exc)), 0, 0
    except Exception as exc:
        return None, ExtractionError(status_code=None, message=str(exc)), 0, 0

    usage = getattr(response, "usage", None)
    input_tokens  = int(getattr(usage, "prompt_tokens",     0) or 0)
    output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

    raw = response.choices[0].message.content.strip()
    # Strip markdown code fences if the model wraps the JSON despite the instruction
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:400].replace("\n", " ")
        return None, ExtractionError(
            status_code=None,
            message=f"JSON parse error: {exc} — raw response begins: {snippet}",
        ), 0, 0

    if not isinstance(parsed, dict):
        return None, ExtractionError(
            status_code=None,
            message=f"Model returned non-object JSON ({type(parsed).__name__}): {raw[:200]}",
        ), 0, 0

    return parsed, None, input_tokens, output_tokens


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract(
    front_bytes: bytes,
    front_media_type: str,
    back_bytes: bytes | None = None,
    back_media_type: str | None = None,
    model: str | None = None,
    fallback_models: list[str] | None = None,
) -> tuple[ExtractionResult | None, ExtractionError | None, float, dict | None]:
    """
    Run Layer 1 extraction on one or two panel images.

    Tries `model` first; on retryable errors iterates through `fallback_models`
    in order.  Auth errors (401) and bad-request errors (400) are not retried.

    Returns (result, error, duration_ms, usage).
    Exactly one of result/error will be non-None.
    duration_ms covers total wall-clock time across all API calls.
    usage is {"input_tokens": int, "output_tokens": int}, accumulated across
    all successful panel calls, or None on error.
    """
    model = model or EXTRACTION_MODEL
    fallback_models = fallback_models if fallback_models is not None else EXTRACTION_FALLBACK_MODELS
    all_models = [model] + fallback_models
    t0 = time.monotonic()

    def _extract_with_fallback(
        img_bytes: bytes,
        media_type: str,
        panel_hint: str | None,
    ) -> tuple[dict | None, ExtractionError | None, int, int]:
        last_error: ExtractionError | None = None
        for m in all_models:
            raw_dict, err, in_tok, out_tok = _extract_single(img_bytes, media_type, panel_hint, m)
            if err is None:
                return raw_dict, None, in_tok, out_tok
            if err.status_code in _NO_RETRY_STATUS_CODES:
                return None, err, 0, 0  # auth / bad-request: don't try fallbacks
            last_error = err
        return None, last_error, 0, 0

    front_dict, err, front_in, front_out = _extract_with_fallback(
        front_bytes, front_media_type, "front"
    )
    if err:
        return None, err, (time.monotonic() - t0) * 1000, None

    total_in, total_out = front_in, front_out

    if back_bytes and back_media_type:
        back_dict, err, back_in, back_out = _extract_with_fallback(
            back_bytes, back_media_type, "back"
        )
        if err:
            return None, err, (time.monotonic() - t0) * 1000, None
        total_in  += back_in
        total_out += back_out
        merged = _merge_panels(front_dict, back_dict)
    else:
        merged = front_dict

    duration_ms = (time.monotonic() - t0) * 1000
    usage = {"input_tokens": total_in, "output_tokens": total_out}

    try:
        result = ExtractionResult.from_dict(merged)
    except Exception as exc:
        return None, ExtractionError(
            status_code=None, message=f"Schema parse error: {exc}"
        ), duration_ms, None

    return result, None, duration_ms, usage
