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
from unittest.mock import call, patch

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

def _ok(name: str) -> tuple[dict, None]:
    return (_fixture_dict(name), None)


def _err(status: int | None, msg: str = "error") -> tuple[None, ExtractionError]:
    return (None, ExtractionError(status_code=status, message=msg))


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
        result, error, _ = extract(
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
        result, error, _ = extract(
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
        result, error, _ = extract(
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
        result, error, _ = extract(
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
        result, error, _ = extract(
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
        result, error, _ = extract(
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
        result, error, _ = extract(
            front_bytes=_JPEG,
            front_media_type="image/jpeg",
            model="only-model",
            fallback_models=[],
        )

    assert error is None
    assert result is not None
    assert result.beverage_class == "spirits"
