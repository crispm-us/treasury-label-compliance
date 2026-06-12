"""
Tests for the Layer 1 extractor — fallback logic and panel merging.

_extract_single is patched to avoid real LiteLLM / network calls.
The public extract() function is tested end-to-end via the patched internal.

Run:
    uv run --with pytest pytest tests/test_extractor.py -v
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from backend.app.services.extractor import (
    ExtractionError,
    _merge_panels,
    extract,
)

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"

# Minimal valid JPEG bytes (SOI marker)
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _fixture_dict(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# Helpers — _extract_single mock return values
# ---------------------------------------------------------------------------

def _ok(name: str) -> tuple[dict, None, int, int]:
    return (_fixture_dict(name), None, 100, 50)


def _err(status: int | None, msg: str = "error") -> tuple[None, ExtractionError, int, int]:
    return (None, ExtractionError(status_code=status, message=msg), 0, 0)


# ---------------------------------------------------------------------------
# Fallback: retryable error (429) → try next model
# ---------------------------------------------------------------------------

def test_fallback_tried_on_rate_limit():
    """Primary returns 429; fallback model succeeds."""
    calls: list[str] = []

    def mock_single(img_bytes, media_type, panel_hint, model):
        calls.append(model)
        if model == "primary-model":
            return _err(429, "rate limited")
        return _ok("beer_compliant.json")

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="primary-model",
            fallback_models=["fallback-model"],
        )

    assert error is None
    assert result is not None
    assert calls == ["primary-model", "fallback-model"]


def test_fallback_tried_on_server_error():
    """Primary returns 500; fallback model succeeds."""
    calls: list[str] = []

    def mock_single(img_bytes, media_type, panel_hint, model):
        calls.append(model)
        if model == "primary-model":
            return _err(500, "server error")
        return _ok("beer_compliant.json")

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="primary-model",
            fallback_models=["fallback-model"],
        )

    assert error is None
    assert calls == ["primary-model", "fallback-model"]


def test_all_fallbacks_exhausted_returns_last_error():
    """All models fail with retryable errors — return the last error."""
    def mock_single(img_bytes, media_type, panel_hint, model):
        return _err(429, f"{model} rate limited")

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="model-a",
            fallback_models=["model-b", "model-c"],
        )

    assert result is None
    assert error is not None
    assert "model-c" in error.message


# ---------------------------------------------------------------------------
# Fallback: non-retryable errors (400, 401) → stop immediately
# ---------------------------------------------------------------------------

def test_no_fallback_on_auth_error():
    """401 must not trigger fallback — key is invalid for this provider."""
    calls: list[str] = []

    def mock_single(img_bytes, media_type, panel_hint, model):
        calls.append(model)
        return _err(401, "invalid key")

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="primary-model",
            fallback_models=["fallback-model"],
        )

    assert error is not None
    assert error.status_code == 401
    assert calls == ["primary-model"]  # fallback NOT tried


def test_no_fallback_on_bad_request():
    """400 must not trigger fallback — payload is malformed."""
    calls: list[str] = []

    def mock_single(img_bytes, media_type, panel_hint, model):
        calls.append(model)
        return _err(400, "bad request")

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="primary-model",
            fallback_models=["fallback-model"],
        )

    assert error is not None
    assert error.status_code == 400
    assert calls == ["primary-model"]


# ---------------------------------------------------------------------------
# No fallbacks configured
# ---------------------------------------------------------------------------

def test_no_fallback_configured_returns_error_on_failure():
    """With no fallback models, an error on the primary is returned directly."""
    def mock_single(img_bytes, media_type, panel_hint, model):
        return _err(429, "rate limited")

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="only-model",
            fallback_models=[],
        )

    assert result is None
    assert error is not None


def test_success_with_no_fallback():
    """Happy path — single model, no fallback needed."""
    def mock_single(img_bytes, media_type, panel_hint, model):
        return _ok("spirits_compliant.json")

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="only-model",
            fallback_models=[],
        )

    assert error is None
    assert result is not None
    assert result.beverage_class == "spirits"


# ---------------------------------------------------------------------------
# Two-panel: token summation and partial-usage on back-panel failure
# ---------------------------------------------------------------------------

def test_two_panel_tokens_are_summed():
    """
    Two-panel extraction makes two _extract_single calls.
    The returned usage must be the sum of both calls' token counts.
    """
    FRONT_IN, FRONT_OUT = 200, 80
    BACK_IN,  BACK_OUT  = 150, 60

    call_count = 0

    def mock_single(img_bytes, media_type, panel_hint, model):
        nonlocal call_count
        call_count += 1
        if panel_hint == "front":
            return (_fixture_dict("beer_compliant.json"), None, FRONT_IN, FRONT_OUT)
        return (_fixture_dict("beer_compliant.json"), None, BACK_IN, BACK_OUT)

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            back_bytes=_JPEG,
            back_media_type="image/jpeg",
            model="test-model",
            fallback_models=[],
        )

    assert error is None
    assert result is not None
    assert call_count == 2  # both panels invoked; order is non-deterministic with threads
    assert usage is not None
    assert usage["input_tokens"]  == FRONT_IN  + BACK_IN
    assert usage["output_tokens"] == FRONT_OUT + BACK_OUT


def test_back_panel_failure_returns_partial_usage():
    """
    When the front panel succeeds but the back panel fails, the front panel's
    tokens were already billed.  extract() must return them in usage rather
    than None, so the audit log reflects actual spend.
    """
    FRONT_IN, FRONT_OUT = 200, 80

    def mock_single(img_bytes, media_type, panel_hint, model):
        if panel_hint == "front":
            return (_fixture_dict("beer_compliant.json"), None, FRONT_IN, FRONT_OUT)
        return (None, ExtractionError(status_code=429, message="rate limited"), 0, 0)

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            back_bytes=_JPEG,
            back_media_type="image/jpeg",
            model="test-model",
            fallback_models=[],
        )

    assert result is None
    assert error is not None
    assert error.status_code == 429
    assert usage is not None, "front tokens must not be discarded on back-panel failure"
    assert usage["input_tokens"]  == FRONT_IN
    assert usage["output_tokens"] == FRONT_OUT


def test_two_panel_extracts_run_concurrently():
    """Two-panel extraction must run both panels in parallel, not sequentially."""
    _SLEEP = 0.1

    def mock_single(img_bytes, media_type, panel_hint, model):
        time.sleep(_SLEEP)
        return (_fixture_dict("beer_compliant.json"), None, 10, 5)

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        _result, error, duration_ms, _usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            back_bytes=_JPEG,
            back_media_type="image/jpeg",
            model="test-model",
            fallback_models=[],
        )

    assert error is None
    # Sequential would be ~200ms+; parallel should finish in ~100ms + overhead.
    assert duration_ms < 180, f"expected parallel execution, got {duration_ms:.0f}ms"


def test_front_failure_returns_front_error():
    """When front fails, front error is returned even if back succeeds."""
    def mock_single(img_bytes, media_type, panel_hint, model):
        if panel_hint == "front":
            return (None, ExtractionError(status_code=401, message="invalid key"), 0, 0)
        return (_fixture_dict("beer_compliant.json"), None, 100, 50)

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, usage, _violations = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            back_bytes=_JPEG,
            back_media_type="image/jpeg",
            model="test-model",
            fallback_models=[],
        )

    assert result is None
    assert error is not None
    assert error.status_code == 401
    assert usage is None


# ---------------------------------------------------------------------------
# Non-dict JSON response (e.g. model returns JSON null or array)
# ---------------------------------------------------------------------------

def test_non_dict_json_returns_extraction_error():
    """
    _extract_single must treat a non-object JSON response (null, array, string)
    as an error rather than returning (None, None, ...) which violates the
    exactly-one-of-result/error invariant.
    """
    import litellm

    mock_response = MagicMock()
    mock_response.choices[0].message.content = "null"
    mock_response.usage = None

    with patch("litellm.completion", return_value=mock_response):
        from backend.app.services.extractor import _extract_single
        raw_dict, err, in_tok, out_tok = _extract_single(
            _JPEG, "image/jpeg", "front", "test-model"
        )

    assert raw_dict is None
    assert err is not None
    assert "NoneType" in err.message or "non-object" in err.message
    assert in_tok == 0
    assert out_tok == 0


# ---------------------------------------------------------------------------
# Empty / malformed response content (crash guard)
# ---------------------------------------------------------------------------

def test_empty_choices_returns_extraction_error():
    """
    Empty choices list must produce ExtractionError, not IndexError.
    Some model providers can return a response with an empty choices array
    under certain error conditions.
    """
    mock_response = MagicMock()
    mock_response.choices = []
    mock_response.usage = None

    with patch("litellm.completion", return_value=mock_response):
        from backend.app.services.extractor import _extract_single
        raw_dict, err, in_tok, out_tok = _extract_single(
            _JPEG, "image/jpeg", "front", "test-model"
        )

    assert raw_dict is None
    assert err is not None
    assert "empty" in err.message.lower() or "malformed" in err.message.lower()


def test_none_content_returns_extraction_error():
    """
    choices[0].message.content = None must produce ExtractionError, not
    AttributeError on the .strip() call.
    """
    mock_response = MagicMock()
    mock_response.choices[0].message.content = None
    mock_response.usage = None

    with patch("litellm.completion", return_value=mock_response):
        from backend.app.services.extractor import _extract_single
        raw_dict, err, in_tok, out_tok = _extract_single(
            _JPEG, "image/jpeg", "front", "test-model"
        )

    assert raw_dict is None
    assert err is not None
    assert "empty" in err.message.lower()


# ---------------------------------------------------------------------------
# Confidence string validation and not_found→null invariant
# ---------------------------------------------------------------------------

def test_invalid_confidence_returns_extraction_error():
    """
    A field with an unrecognized confidence string must be rejected.
    Invalid confidence values would otherwise silently rank as 0 (same as
    not_found) via _CONF_RANK.get(..., 0) — this surfaces the model drift early.
    """
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["fields"]["brand_name"]["confidence"] = "medium"  # not in {high, low, not_found}

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(data)
    mock_response.usage = None

    with patch("litellm.completion", return_value=mock_response):
        from backend.app.services.extractor import _extract_single
        raw_dict, err, in_tok, out_tok = _extract_single(
            _JPEG, "image/jpeg", "front", "test-model"
        )

    assert raw_dict is None
    assert err is not None
    assert "medium" in err.message or "confidence" in err.message.lower()


def test_not_found_with_non_null_value_returns_extraction_error():
    """
    A field with confidence='not_found' and a non-null value violates ADR-011 schema.
    The invariant is currently prompt-only; this test covers the post-parse enforcement.
    """
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["fields"]["brand_name"] = {"value": "Sunset Ale", "confidence": "not_found"}

    mock_response = MagicMock()
    mock_response.choices[0].message.content = json.dumps(data)
    mock_response.usage = None

    with patch("litellm.completion", return_value=mock_response):
        from backend.app.services.extractor import _extract_single
        raw_dict, err, in_tok, out_tok = _extract_single(
            _JPEG, "image/jpeg", "front", "test-model"
        )

    assert raw_dict is None
    assert err is not None
    assert "not_found" in err.message


# ---------------------------------------------------------------------------
# _merge_panels: null field values from model
# ---------------------------------------------------------------------------

def test_merge_panels_null_field_value_does_not_crash():
    """
    Regression for TypeError: 'NoneType' object is not subscriptable.

    The model occasionally returns JSON null for a whole field object instead
    of the expected {"value": null, "confidence": "not_found"} dict.
    _merge_panels must treat a null field value as not_found rather than
    crashing when it tries to subscript None.
    """
    base = _fixture_dict("beer_compliant.json")

    # Simulate the back panel returning null for two fields
    back = dict(base)
    back["fields"] = dict(base["fields"])
    back["fields"]["brand_name"] = None        # null field object
    back["fields"]["net_contents_us"] = None   # null field object
    back["panels_provided"] = ["back"]

    front = dict(base)
    front["panels_provided"] = ["front"]

    merged = _merge_panels(front, back)

    # Fields that were null on back should fall back to the front panel value
    assert merged["fields"]["brand_name"] is not None
    assert merged["fields"]["brand_name"]["confidence"] != "not_found"
    # net_contents_us: front fixture has a value; back null must not override it
    assert merged["fields"]["net_contents_us"] is not None


def test_merge_panels_bool_field_value_does_not_crash():
    """
    Regression for TypeError: 'bool' object is not subscriptable.

    The model occasionally returns a bare JSON boolean for a field (e.g.
    "gws_present": true) instead of {"value": true, "confidence": "high"}.
    Unlike the null case, True is truthy so the previous `or _not_found`
    guard did not catch it — True["confidence"] raised TypeError.
    _merge_panels must treat any non-dict field value as not_found.
    """
    base = _fixture_dict("beer_compliant.json")

    back = dict(base)
    back["fields"] = dict(base["fields"])
    back["fields"]["gws_present"] = True   # bare boolean — model skipped the wrapper
    back["panels_provided"] = ["back"]

    front = dict(base)
    front["panels_provided"] = ["front"]

    # Must not raise; front value should win since back is treated as not_found
    merged = _merge_panels(front, back)
    assert merged["fields"]["gws_present"] is not None
    assert isinstance(merged["fields"]["gws_present"], dict)
