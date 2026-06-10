"""
Tests for the deterministic TTB compliance checker (Layer 2).

All tests load a fixture from tests/fixtures/extraction/*.json, parse it into
an ExtractionResult, run check_compliance(), and assert the expected verdict
and specific rule IDs in errors/warnings.

No model calls. No network. Pure Python + pytest.

Run:
    uv run --with pytest pytest tests/test_compliance_checker.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.compliance_checker import (
    ExtractionResult,
    ComplianceResult,
    check_compliance,
)

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"


def _load(name: str) -> ComplianceResult:
    data = json.loads((FIXTURES / name).read_text())
    return check_compliance(ExtractionResult.from_dict(data))


# ---------------------------------------------------------------------------
# Compliant cases — expect COMPLIANT, zero issues
# ---------------------------------------------------------------------------

def test_beer_compliant():
    r = _load("beer_compliant.json")
    assert r.verdict == "COMPLIANT"
    assert r.errors == []
    assert r.warnings == []


def test_spirits_compliant():
    r = _load("spirits_compliant.json")
    assert r.verdict == "COMPLIANT"
    assert r.errors == []
    assert r.warnings == []


def test_wine_compliant():
    r = _load("wine_compliant.json")
    assert r.verdict == "COMPLIANT"
    assert r.errors == []
    assert r.warnings == []


# ---------------------------------------------------------------------------
# Single-violation noncompliant cases
# ---------------------------------------------------------------------------

def test_beer_R_GW_01_missing_gws():
    """GWS definitively absent (high confidence) → NONCOMPLIANT / R-GW-01 error."""
    r = _load("beer_R-GW-01.json")
    assert r.verdict == "NONCOMPLIANT"
    error_rules = {i.rule_id for i in r.errors}
    assert "R-GW-01" in error_rules


def test_spirits_R_GW_03_titlecase_header():
    """GWS header 'Government Warning:' (title case) → NONCOMPLIANT / R-GW-03 error."""
    r = _load("spirits_R-GW-03.json")
    assert r.verdict == "NONCOMPLIANT"
    error_rules = {i.rule_id for i in r.errors}
    assert "R-GW-03" in error_rules
    # Body text is correct — no R-GW-02 error expected
    assert "R-GW-02" not in error_rules


def test_wine_R_WN_09_sulfite_missing():
    """
    Sulfite declaration not found (not_found confidence).
    R-WN-09 is always a warning (cannot verify SO₂ level from image).
    Expected verdict: UNVERIFIABLE.
    """
    r = _load("wine_R-WN-09.json")
    assert r.verdict == "UNVERIFIABLE"
    assert r.errors == []
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-WN-09" in warning_rules


# ---------------------------------------------------------------------------
# Two simultaneous violations
# ---------------------------------------------------------------------------

def test_spirits_two_violations():
    """
    R-GW-03 (title-case header) + R-DS-03 (ABV confirmed absent).
    Both are high-confidence errors. Verdict: NONCOMPLIANT.
    Both rule IDs must appear in errors.
    """
    r = _load("spirits_two_violations.json")
    assert r.verdict == "NONCOMPLIANT"
    error_rules = {i.rule_id for i in r.errors}
    assert "R-GW-03" in error_rules
    assert "R-DS-03" in error_rules
    assert len(r.errors) >= 2


# ---------------------------------------------------------------------------
# Low-confidence path
# ---------------------------------------------------------------------------

def test_beer_low_confidence_gws_body():
    """
    GWS body read at low confidence with wrong text ('can' vs 'may').
    R-GW-02 fires as warning (not error) because confidence is low.
    Verdict: UNVERIFIABLE (has warnings, no errors).
    """
    r = _load("beer_low_confidence_gws.json")
    assert r.verdict == "UNVERIFIABLE"
    assert r.errors == []
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-GW-02" in warning_rules


# ---------------------------------------------------------------------------
# Partial extraction — unverifiable mandatory fields
# ---------------------------------------------------------------------------

def test_beer_partial_front_only():
    """
    Front panel only — bottler fields and GWS not found.
    Verdict: UNVERIFIABLE (mandatory fields absent from image).
    No errors — no definitive violations.
    """
    r = _load("beer_partial_unverifiable.json")
    assert r.verdict == "UNVERIFIABLE"
    assert r.errors == []
    warning_rules = {i.rule_id for i in r.warnings}
    # GWS not found → R-GW-01 warning
    assert "R-GW-01" in warning_rules
    # Bottler name + address not found → R-MB-05 warning(s)
    assert "R-MB-05" in warning_rules


# ---------------------------------------------------------------------------
# gws_present flag contradicts text evidence  (regression — 2026-06-10)
# ---------------------------------------------------------------------------

def test_beer_gws_flag_contradiction():
    """
    Model returned gws_present=false (high confidence) but also extracted the
    correct GWS header and body text.  Text evidence must override the flag:
    R-GW-01 must NOT fire, and the correct header/body must pass R-GW-02/03.
    All other beer fields are present and correct → COMPLIANT.
    """
    r = _load("beer_gws_flag_contradiction.json")
    assert r.verdict == "COMPLIANT", f"Expected COMPLIANT, got {r.verdict}; issues: {r.issues}"
    rule_ids = {i.rule_id for i in r.issues}
    assert "R-GW-01" not in rule_ids, "R-GW-01 must not fire when GWS text is present"
    assert "R-GW-02" not in rule_ids
    assert "R-GW-03" not in rule_ids
    assert r.errors == []
    assert r.warnings == []


# ---------------------------------------------------------------------------
# Cannot read
# ---------------------------------------------------------------------------

def test_cannot_read():
    """readable=false → ERROR verdict, no rules applied, issues list empty."""
    r = _load("cannot_read.json")
    assert r.verdict == "ERROR"
    assert r.issues == []


# ---------------------------------------------------------------------------
# Proof / ABV consistency
# ---------------------------------------------------------------------------

def test_spirits_proof_mismatch():
    """
    50% ABV stated but 92 Proof on label (should be 100 Proof).
    R-DS-03 proof-consistency check → NONCOMPLIANT.
    """
    r = _load("spirits_proof_mismatch.json")
    assert r.verdict == "NONCOMPLIANT"
    error_rules = {i.rule_id for i in r.errors}
    assert "R-DS-03" in error_rules
    # Find the specific proof issue
    proof_issues = [i for i in r.errors if i.field == "proof"]
    assert proof_issues, "Expected an R-DS-03 issue on the 'proof' field"


# ---------------------------------------------------------------------------
# Partial extraction + high-confidence violation  (DOCUMENTED — see ADR-011)
# ---------------------------------------------------------------------------

def test_spirits_partial_noncompliant_documented():
    """
    Partial extraction (ABV and bottler address not found) co-exists with a
    definitive R-GW-03 error (GWS header title-case, high confidence).

    Current behavior: verdict is NONCOMPLIANT (error present) and the
    not_found warnings are also in issues.  The caller is responsible for
    surfacing both the violation AND the warnings.

    KNOWN LIMITATION — production handling of this mixed verdict is deferred.
    See ADR-011 §"Partial extraction with high-confidence violation" for the
    design note on how a future version should handle this case explicitly
    (e.g., a NONCOMPLIANT_PARTIAL verdict or a mandatory warning banner).
    """
    r = _load("spirits_partial_noncompliant.json")

    # The definitive violation must be reported
    assert r.verdict == "NONCOMPLIANT"
    error_rules = {i.rule_id for i in r.errors}
    assert "R-GW-03" in error_rules

    # The not_found warnings must ALSO be present so the caller can surface them
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-DS-03" in warning_rules   # ABV not found
    assert "R-DS-06" in warning_rules   # bottler address not found

    # Document the limitation inline
    # TODO (production): when errors and not_found warnings co-exist, the API
    # response should include a top-level flag  partial_verification: true  so
    # the UI can display: "Violation found AND some fields could not be verified —
    # submit a complete label image to check all mandatory fields."
