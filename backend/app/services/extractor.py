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
in parallel (ThreadPoolExecutor) so wall-clock latency is ~one model call rather
than two sequential ones.  The same prompt is used for both panels (panel_hint
is advisory — written to the prompt so the model can orient itself, but not used
in any branching logic).  The two dicts are then merged field-by-field: highest
confidence wins; ties go to the non-null value.  This tolerates flipped
submissions naturally.  See ADR-011.

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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import litellm

from backend.app.config import EXTRACTION_FALLBACK_MODELS, EXTRACTION_MODEL, EXTRACTION_SCHEMA_STRICT, MODEL_TIMEOUT_SECONDS
from backend.app.prompts.extraction import SYSTEM as _SYSTEM, USER_TEMPLATE as _USER_TEMPLATE
from backend.app.services.compliance_checker import ExtractionResult

# Suppress LiteLLM's verbose success logging; keep errors.
litellm.success_callback = []
litellm.set_verbose = False


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
# Schema violation tracking
# ---------------------------------------------------------------------------

_not_found_field: dict = {"value": None, "confidence": "not_found"}


def _collect_schema_violations(fields_dict: dict, model: str) -> list[dict]:
    """
    Scan raw extraction fields for non-dict values (Layer 1 schema violations).

    The extraction prompt specifies every field must be a
    {"value": ..., "confidence": ...} object.  A model returning a bare
    primitive (null, bool, string, number) instead of a field object has
    violated the schema.

    These are surfaced as quality metrics in the audit log and API response.
    They do not cause hard failures in loose mode (default).
    Set EXTRACTION_SCHEMA_STRICT=true to treat them as ExtractionErrors.
    """
    violations: list[dict] = []
    if not isinstance(fields_dict, dict):
        return violations
    for fname, fval in fields_dict.items():
        if not isinstance(fval, dict):
            violations.append({
                "field": fname,
                "type_got": type(fval).__name__,
                "value_preview": repr(fval)[:80],
                "model": model,
            })
    return violations


def _sanitize_fields(raw_dict: dict) -> dict:
    """
    Convert non-dict field values to not_found before ExtractionResult.from_dict.

    Guards the single-panel path (where _merge_panels is not called).
    _merge_panels has its own equivalent guard for defense-in-depth.
    Non-dict values that reach from_dict would raise TypeError; this
    converts them to _not_found so loose mode can still produce a result.
    """
    if not isinstance(raw_dict, dict):
        return raw_dict
    fields = raw_dict.get("fields")
    if not isinstance(fields, dict):
        return raw_dict
    sanitized = dict(raw_dict)
    sanitized["fields"] = {
        k: (v if isinstance(v, dict) else _not_found_field)
        for k, v in fields.items()
    }
    return sanitized


# ---------------------------------------------------------------------------
# Panel merger
# ---------------------------------------------------------------------------

_CONF_RANK = {"high": 2, "low": 1, "not_found": 0}
_VALID_CONF = frozenset({"high", "low", "not_found"})


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

    _not_found: dict[str, Any] = {"value": None, "confidence": "not_found"}
    merged_fields: dict[str, Any] = {}
    for name in set(front_fields) | set(back_fields):
        # Guard: model may return a non-dict value for a field instead of the
        # expected {"value": ..., "confidence": ...} object.  Observed cases:
        #   JSON null  → None  (e.g. "gws_present": null)
        #   JSON bool  → True/False (e.g. "gws_present": true)
        # The previous `or _not_found` guard handled null (falsy) but not True
        # (truthy), causing `True["confidence"]` → TypeError.  isinstance is
        # the correct check: only a dict is a valid field object.
        _raw_fv = front_fields.get(name)
        _raw_bv = back_fields.get(name)
        fv = _raw_fv if isinstance(_raw_fv, dict) else _not_found
        bv = _raw_bv if isinstance(_raw_bv, dict) else _not_found
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
            timeout=MODEL_TIMEOUT_SECONDS,
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

    # Guard against empty or malformed response structure (empty choices list,
    # missing message attribute, or None content).
    try:
        raw = response.choices[0].message.content
    except (IndexError, AttributeError):
        return None, ExtractionError(
            status_code=None,
            message="Model returned empty or malformed response structure (no content in choices)",
        ), input_tokens, output_tokens
    if not raw:
        return None, ExtractionError(
            status_code=None,
            message="Model returned empty content in response",
        ), input_tokens, output_tokens
    raw = raw.strip()
    # Strip markdown code fences if the model wraps the JSON despite the instruction
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        snippet = raw[:400].replace("\n", " ")
        # Return the real token counts: the API call succeeded and those tokens
        # were billed even though the response is unparseable.
        return None, ExtractionError(
            status_code=None,
            message=f"JSON parse error: {exc} — raw response begins: {snippet}",
        ), input_tokens, output_tokens

    if not isinstance(parsed, dict):
        # Same rationale: tokens were consumed; preserve them in the audit record.
        return None, ExtractionError(
            status_code=None,
            message=f"Model returned non-object JSON ({type(parsed).__name__}): {raw[:200]}",
        ), input_tokens, output_tokens

    # Validate confidence enum values and the not_found→null invariant for all fields.
    # Invalid confidence strings currently rank as 0 in _CONF_RANK (silently treated
    # as not_found); catching them here surfaces model/prompt drift early.
    _fields = parsed.get("fields")
    if isinstance(_fields, dict):
        for _fname, _fobj in _fields.items():
            if not isinstance(_fobj, dict):
                continue
            _conf = _fobj.get("confidence")
            if _conf not in _VALID_CONF:
                return None, ExtractionError(
                    status_code=None,
                    message=(
                        f"Field '{_fname}' has invalid confidence {_conf!r} — "
                        f"must be one of {sorted(_VALID_CONF)}"
                    ),
                ), input_tokens, output_tokens
            if _conf == "not_found" and _fobj.get("value") is not None:
                return None, ExtractionError(
                    status_code=None,
                    message=(
                        f"Field '{_fname}' has confidence 'not_found' but non-null value "
                        f"{_fobj['value']!r} — 'not_found' requires value: null"
                    ),
                ), input_tokens, output_tokens

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
) -> tuple[ExtractionResult | None, ExtractionError | None, float, dict | None, list[dict]]:
    """
    Run Layer 1 extraction on one or two panel images.

    Tries `model` first; on retryable errors iterates through `fallback_models`
    in order.  Auth errors (401) and bad-request errors (400) are not retried.

    Returns (result, error, duration_ms, usage, schema_violations).
    Exactly one of result/error will be non-None.
    duration_ms covers total wall-clock time across all API calls.
    usage is {"input_tokens": int, "output_tokens": int}, accumulated across
    all successful panel calls, or None on error.
    schema_violations is a list of dicts describing non-dict field values
    returned by the model (Layer 1 prompt non-compliance).  Always [] on error.
    When EXTRACTION_SCHEMA_STRICT=true and violations are found, an
    ExtractionError is returned instead of a result.
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

    if back_bytes and back_media_type:
        # Per-call executor is fine at prototype scale; a module-level pool would
        # be the production upgrade path under sustained concurrent load.
        with ThreadPoolExecutor(max_workers=2) as pool:
            front_fut = pool.submit(
                _extract_with_fallback, front_bytes, front_media_type, "front"
            )
            back_fut = pool.submit(
                _extract_with_fallback, back_bytes, back_media_type, "back"
            )
            # Join both futures before error handling — never return while a
            # thread is still running.
            front_dict, front_err, front_in, front_out = front_fut.result()
            back_dict, back_err, back_in, back_out = back_fut.result()

        if front_err:
            # Both threads were started concurrently; we do not cancel the back
            # thread on front hard-fail — in-flight HTTP calls cannot be aborted
            # cleanly, and back may have already billed tokens.  Front error wins.
            return None, front_err, (time.monotonic() - t0) * 1000, None, []

        if back_err:
            partial_usage = {"input_tokens": front_in, "output_tokens": front_out}
            return None, back_err, (time.monotonic() - t0) * 1000, partial_usage, []

        total_in, total_out = front_in + back_in, front_out + back_out
        front_model = front_dict.get("extraction_model", model)
        all_violations: list[dict] = _collect_schema_violations(
            front_dict.get("fields", {}), front_model
        )
        front_dict = _sanitize_fields(front_dict)
        back_model = back_dict.get("extraction_model", model)
        all_violations += _collect_schema_violations(back_dict.get("fields", {}), back_model)
        back_dict = _sanitize_fields(back_dict)
        merged = _merge_panels(front_dict, back_dict)
    else:
        front_dict, err, front_in, front_out = _extract_with_fallback(
            front_bytes, front_media_type, "front"
        )
        if err:
            return None, err, (time.monotonic() - t0) * 1000, None, []

        total_in, total_out = front_in, front_out
        front_model = front_dict.get("extraction_model", model)
        all_violations = _collect_schema_violations(front_dict.get("fields", {}), front_model)
        front_dict = _sanitize_fields(front_dict)
        merged = front_dict

    duration_ms = (time.monotonic() - t0) * 1000
    usage = {"input_tokens": total_in, "output_tokens": total_out}

    # Strict mode: treat schema violations as an extraction failure
    if EXTRACTION_SCHEMA_STRICT and all_violations:
        fields_named = [v["field"] for v in all_violations]
        return None, ExtractionError(
            status_code=None,
            message=(
                f"Layer 1 schema violations in {len(all_violations)} field(s): {fields_named}. "
                "Model returned non-dict field values. "
                "Set EXTRACTION_SCHEMA_STRICT=false to allow partial extraction."
            ),
        ), duration_ms, usage, []

    try:
        result = ExtractionResult.from_dict(merged)
    except Exception as exc:
        return None, ExtractionError(
            status_code=None, message=f"Schema parse error: {exc}"
        ), duration_ms, usage, all_violations

    return result, None, duration_ms, usage, all_violations
