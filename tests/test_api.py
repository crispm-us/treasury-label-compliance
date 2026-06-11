"""
API-layer tests for POST /v1/check and GET /healthz.

All extraction calls are mocked — no API key required, no network calls.
extract() is replaced with a factory that returns a pre-built ExtractionResult
loaded from the fixture JSON files.

Run:
    uv run --with pytest pytest tests/test_api.py -v
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.services.compliance_checker import ExtractionResult
from backend.app.services.extractor import ExtractionError

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"

# Minimal valid JPEG bytes (SOI marker — enough to pass content-type check)
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _result(name: str) -> ExtractionResult:
    return ExtractionResult.from_dict(json.loads((FIXTURES / name).read_text()))


def _ok(name: str) -> tuple:
    """Mock return value for a successful extraction."""
    return (_result(name), None, 42.0, {"input_tokens": 100, "output_tokens": 50})


def _err(status_code: int | None, message: str) -> tuple:
    """Mock return value for a model API failure."""
    return (None, ExtractionError(status_code=status_code, message=message), 50.0, None)


@pytest.fixture(autouse=True)
def _no_audit(monkeypatch):
    """Disable audit writes for all tests in this module."""
    monkeypatch.setattr("backend.app.main.write_entry", lambda *a, **kw: None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "audit_enabled" in body


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

def test_response_has_all_required_fields(client):
    """Every response must include all documented fields."""
    with patch("backend.app.main.extract", return_value=_ok("beer_compliant.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    assert r.status_code == 200
    body = r.json()
    for f in ("request_id", "timestamp", "verdict", "beverage_class",
              "issues", "extraction_model", "audit_logged", "partial_verification",
              "input_tokens", "output_tokens"):
        assert f in body, f"response missing field: {f!r}"
    assert body["input_tokens"] == 100
    assert body["output_tokens"] == 50


def test_issue_shape(client):
    """Each issue must include rule_id, severity, field, found, expected, not_found."""
    with patch("backend.app.main.extract", return_value=_ok("beer_R-GW-01.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    issues = r.json()["issues"]
    assert issues, "expected at least one issue"
    for issue in issues:
        for f in ("rule_id", "severity", "field", "found", "expected", "not_found"):
            assert f in issue, f"issue missing field: {f!r}"


# ---------------------------------------------------------------------------
# Compliant
# ---------------------------------------------------------------------------

def test_beer_compliant_single_panel(client):
    with patch("backend.app.main.extract", return_value=_ok("beer_compliant.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "COMPLIANT"
    assert body["issues"] == []
    assert body["partial_verification"] is False


def test_wine_compliant_two_panels(client):
    with patch("backend.app.main.extract", return_value=_ok("wine_compliant.json")):
        r = client.post(
            "/v1/check",
            files={
                "front": ("front.jpg", _JPEG, "image/jpeg"),
                "back":  ("back.jpg",  _JPEG, "image/jpeg"),
            },
        )
    body = r.json()
    assert body["verdict"] == "COMPLIANT"
    assert body["partial_verification"] is False


def test_spirits_compliant(client):
    with patch("backend.app.main.extract", return_value=_ok("spirits_compliant.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "COMPLIANT"
    assert body["issues"] == []


# ---------------------------------------------------------------------------
# Noncompliant
# ---------------------------------------------------------------------------

def test_noncompliant_beer_R_GW_01(client):
    with patch("backend.app.main.extract", return_value=_ok("beer_R-GW-01.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "NONCOMPLIANT"
    error_rules = [i["rule_id"] for i in body["issues"] if i["severity"] == "error"]
    assert "R-GW-01" in error_rules
    # partial_verification=True because the fixture also has abv_pct=not_found (R-MB-03 warning)
    assert body["partial_verification"] is True


def test_noncompliant_spirits_R_GW_03(client):
    with patch("backend.app.main.extract", return_value=_ok("spirits_R-GW-03.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "NONCOMPLIANT"
    assert any(i["rule_id"] == "R-GW-03" for i in body["issues"])


# ---------------------------------------------------------------------------
# Unverifiable
# ---------------------------------------------------------------------------

def test_unverifiable_wine_R_WN_09(client):
    with patch("backend.app.main.extract", return_value=_ok("wine_R-WN-09.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "UNVERIFIABLE"
    assert any(i["rule_id"] == "R-WN-09" for i in body["issues"])
    assert body["partial_verification"] is False


def test_unverifiable_partial_front_only(client):
    with patch("backend.app.main.extract", return_value=_ok("beer_partial_unverifiable.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "UNVERIFIABLE"
    assert body["partial_verification"] is False  # UNVERIFIABLE, not NONCOMPLIANT


# ---------------------------------------------------------------------------
# ERROR — unreadable image
# ---------------------------------------------------------------------------

def test_cannot_read_returns_error_verdict(client):
    with patch("backend.app.main.extract", return_value=_ok("cannot_read.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert r.status_code == 200
    assert body["verdict"] == "ERROR"
    assert body["issues"] == []
    assert body["partial_verification"] is False


# ---------------------------------------------------------------------------
# ERROR — model API failures
# ---------------------------------------------------------------------------

def test_model_rate_limit_returns_error(client):
    with patch("backend.app.main.extract", return_value=_err(429, "rate limited")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert r.status_code == 200
    assert body["verdict"] == "ERROR"
    assert body["issues"] == []
    assert body["beverage_class"] is None
    assert body["partial_verification"] is False


def test_model_auth_error_returns_error(client):
    with patch("backend.app.main.extract", return_value=_err(401, "invalid key")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert r.status_code == 200
    assert body["verdict"] == "ERROR"
    assert body["issues"] == []
    assert body["beverage_class"] is None
    assert body["partial_verification"] is False


# ---------------------------------------------------------------------------
# partial_verification flag
# ---------------------------------------------------------------------------

def test_partial_verification_true_when_noncompliant_with_not_found_warnings(client):
    """
    spirits_partial_noncompliant: R-GW-03 error (definitive) + ABV/bottler
    not_found (unverifiable).  partial_verification must be True so callers
    can surface: "Violation found AND some fields could not be verified."
    """
    with patch("backend.app.main.extract", return_value=_ok("spirits_partial_noncompliant.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "NONCOMPLIANT"
    assert body["partial_verification"] is True
    # The not_found issues must have not_found=True in the response
    not_found_issues = [i for i in body["issues"] if i["not_found"]]
    assert not_found_issues, "expected at least one issue with not_found=True"


def test_partial_verification_false_when_all_mandatory_fields_present(client):
    """
    spirits_two_violations: two definitive errors, all mandatory fields
    present or confirmed absent — no not_found warnings → False.
    """
    with patch("backend.app.main.extract", return_value=_ok("spirits_two_violations.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    body = r.json()
    assert body["verdict"] == "NONCOMPLIANT"
    assert body["partial_verification"] is False


# ---------------------------------------------------------------------------
# Input validation — unsupported media type
# ---------------------------------------------------------------------------

def test_unsupported_front_media_type_returns_415(client):
    r = client.post(
        "/v1/check",
        files={"front": ("label.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 415


def test_unsupported_back_media_type_returns_415(client):
    r = client.post(
        "/v1/check",
        files={
            "front": ("front.jpg", _JPEG,  "image/jpeg"),
            "back":  ("back.pdf",  b"%PDF", "application/pdf"),
        },
    )
    assert r.status_code == 415


def test_oversized_front_returns_413(client, monkeypatch):
    """File larger than MAX_IMAGE_BYTES must return 413."""
    monkeypatch.setattr("backend.app.main.MAX_IMAGE_BYTES", 100)
    r = client.post(
        "/v1/check",
        files={"front": ("big.jpg", b"x" * 101, "image/jpeg")},
    )
    assert r.status_code == 413


def test_oversized_back_returns_413(client, monkeypatch):
    """Oversized back panel must also return 413."""
    monkeypatch.setattr("backend.app.main.MAX_IMAGE_BYTES", 100)
    r = client.post(
        "/v1/check",
        files={
            "front": ("front.jpg", _JPEG,      "image/jpeg"),
            "back":  ("big.jpg",   b"x" * 101, "image/jpeg"),
        },
    )
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# Audit write failure — must not surface as HTTP 500
# ---------------------------------------------------------------------------

def test_audit_write_failure_returns_200_with_audit_logged_false(client, monkeypatch):
    """
    A disk-full or permission error in write_entry must not 500.
    The compliance result is already computed and the caller deserves a response.
    audit_logged must be False to signal that the entry was not persisted.

    The _no_audit autouse fixture patches write_entry to a no-op; we override
    it here to raise OSError so the error-handling path is exercised.
    """
    monkeypatch.setattr("backend.app.main.write_entry", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    with patch("backend.app.main.extract", return_value=_ok("beer_compliant.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    assert r.status_code == 200, "audit failure must not produce HTTP 500"
    assert r.json()["audit_logged"] is False


def test_invalid_magic_bytes_returns_415(client):
    """Correct Content-Type header but wrong file content must return 415."""
    r = client.post(
        "/v1/check",
        files={"front": ("label.jpg", b"%PDF-1.4 fake content", "image/jpeg")},
    )
    assert r.status_code == 415


# ---------------------------------------------------------------------------
# API key authentication
# ---------------------------------------------------------------------------

def test_api_key_required_when_configured(client, monkeypatch):
    """When API_KEY is set, a request without X-API-Key must get 401."""
    monkeypatch.setattr("backend.app.main.API_KEY", "test-secret-key")
    with patch("backend.app.main.extract", return_value=_ok("beer_compliant.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    assert r.status_code == 401


def test_api_key_accepted_when_correct(client, monkeypatch):
    """Correct X-API-Key must pass through to a 200 response."""
    monkeypatch.setattr("backend.app.main.API_KEY", "test-secret-key")
    with patch("backend.app.main.extract", return_value=_ok("beer_compliant.json")):
        r = client.post(
            "/v1/check",
            headers={"X-API-Key": "test-secret-key"},
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    assert r.status_code == 200


def test_api_key_not_required_when_unset(client, monkeypatch):
    """When API_KEY is empty (local dev), requests without the header must succeed."""
    monkeypatch.setattr("backend.app.main.API_KEY", "")
    with patch("backend.app.main.extract", return_value=_ok("beer_compliant.json")):
        r = client.post(
            "/v1/check",
            files={"front": ("front.jpg", _JPEG, "image/jpeg")},
        )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Two-panel readable merge  (regression — 2026-06-10)
# ---------------------------------------------------------------------------

def test_readable_merge_uses_either_panel(client):
    """
    _merge_panels must mark the result readable=True when the back panel is
    readable even if the front panel is not.  This is tested end-to-end via
    a beer_compliant fixture that was modified to have readable=False on the
    front dict, with the merge already applied in the extractor.  We test the
    pure merge function directly here.
    """
    from backend.app.services.extractor import _merge_panels

    front = {
        "schema_version": "1.0", "readable": False, "beverage_class": None,
        "panels_provided": ["front"], "extraction_model": "test",
        "fields": {}
    }
    back = {
        "schema_version": "1.0", "readable": True, "beverage_class": "beer",
        "panels_provided": ["back"], "extraction_model": "test",
        "fields": {}
    }
    merged = _merge_panels(front, back)
    assert merged["readable"] is True, (
        "readable must be True when back panel is readable, even if front is not"
    )
    assert merged["panels_provided"] == ["back", "front"]
    assert merged["beverage_class"] == "beer"
