"""
Tests for the Layer 1 extractor — fallback logic and panel merging.

_extract_single is patched to avoid real LiteLLM / network calls.
The public extract() function is tested end-to-end via the patched internal.

Run:
    uv run --with pytest pytest tests/test_extractor.py -v
"""
from __future__ import annotations

import json
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
        result, error, _, _usage = extract(
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
        result, error, _, _usage = extract(
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
        result, error, _, _usage = extract(
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
        result, error, _, _usage = extract(
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
        result, error, _, _usage = extract(
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
        result, error, _, _usage = extract(
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
        result, error, _, _usage = extract(
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
        if call_count == 1:   # front
            return (_fixture_dict("beer_compliant.json"), None, FRONT_IN, FRONT_OUT)
        else:                  # back
            return (_fixture_dict("beer_compliant.json"), None, BACK_IN, BACK_OUT)

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, usage = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            back_bytes=_JPEG,
            back_media_type="image/jpeg",
            model="test-model",
            fallback_models=[],
        )

    assert error is None
    assert result is not None
    assert call_count == 2
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

    call_count = 0

    def mock_single(img_bytes, media_type, panel_hint, model):
        nonlocal call_count
        call_count += 1
        if call_count == 1:   # front succeeds
            return (_fixture_dict("beer_compliant.json"), None, FRONT_IN, FRONT_OUT)
        else:                  # back fails
            return (None, ExtractionError(status_code=429, message="rate limited"), 0, 0)

    with patch("backend.app.services.extractor._extract_single", side_effect=mock_single):
        result, error, _, usage = extract(
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
