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


# ---------------------------------------------------------------------------
# Empty-string bypass fix  (regression — 2026-06-10)
# ---------------------------------------------------------------------------

def test_empty_string_mandatory_field_is_treated_as_absent():
    """
    _check_mandatory must treat an empty-string value as absent, not present.
    A model that returns {"value": "", "confidence": "high"} for brand_name
    should produce the same R-MB-01 error as {"value": null, "confidence": "high"}.
    """
    import copy
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["fields"]["brand_name"] = {"value": "", "confidence": "high"}
    r = check_compliance(ExtractionResult.from_dict(data))
    assert r.verdict == "NONCOMPLIANT"
    error_rules = {i.rule_id for i in r.errors}
    assert "R-MB-01" in error_rules, (
        "Empty-string brand_name with high confidence must raise R-MB-01 error"
    )


def test_whitespace_only_mandatory_field_is_treated_as_absent():
    """Same as above but with a whitespace-only value."""
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["fields"]["brand_name"] = {"value": "   ", "confidence": "high"}
    r = check_compliance(ExtractionResult.from_dict(data))
    assert r.verdict == "NONCOMPLIANT"
    error_rules = {i.rule_id for i in r.errors}
    assert "R-MB-01" in error_rules


# ---------------------------------------------------------------------------
# Low-confidence ABV range checks (R-DS-03, R-WN-03)
# ---------------------------------------------------------------------------

def test_spirits_low_confidence_abv_out_of_range():
    """
    R-DS-03 range check runs at low confidence — clearly impossible ABV should
    not pass silently.  Low confidence → warning (not error), since the reading
    is uncertain.

    Proof is set to not_found to avoid triggering the proof-consistency check
    (which would also fire R-DS-03 as an error and obscure the result).
    """
    data = json.loads((FIXTURES / "spirits_compliant.json").read_text())
    data["fields"]["abv_pct"] = {"value": 150.0, "confidence": "low"}
    data["fields"]["proof"] = {"value": None, "confidence": "not_found"}
    r = check_compliance(ExtractionResult.from_dict(data))
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-DS-03" in warning_rules, "Low-confidence out-of-range ABV must fire R-DS-03 as warning"
    # Must NOT be an error — evidence is uncertain
    assert "R-DS-03" not in {i.rule_id for i in r.errors}


def test_gws_body_all_caps_passes_r_gw_02():
    """
    Real labels print the GWS body in all-caps (required by 27 CFR §16.22(a)(2)).
    R-GW-02 checks content, not case; an all-caps body matching the canonical
    text must not fire R-GW-02.
    """
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["fields"]["gws_body"]["value"] = (
        "(1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC "
        "BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. "
        "(2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A "
        "CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
    )
    data["fields"]["gws_body"]["confidence"] = "high"
    r = check_compliance(ExtractionResult.from_dict(data))
    gws_issues = [i for i in r.issues if i.rule_id == "R-GW-02"]
    assert not gws_issues, (
        "All-caps GWS body matching canonical content must pass R-GW-02 — "
        "real labels always print all-caps per 27 CFR §16.22(a)(2)"
    )


def test_wine_low_confidence_abv_out_of_range():
    """
    R-WN-03 range check runs at low confidence.
    50.0% ABV is outside wine range (0.5%–24.0%); low confidence → warning.
    """
    data = json.loads((FIXTURES / "wine_compliant.json").read_text())
    data["fields"]["abv_pct"] = {"value": 50.0, "confidence": "low"}
    r = check_compliance(ExtractionResult.from_dict(data))
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-WN-03" in warning_rules, "Low-confidence out-of-range wine ABV must fire R-WN-03 as warning"
    assert "R-WN-03" not in {i.rule_id for i in r.errors}


# ---------------------------------------------------------------------------
# P2 gap coverage (identified in second Cursor audit, 2026-06-10)
# ---------------------------------------------------------------------------

def test_null_beverage_class_r_meta_01():
    """
    beverage_class=null → R-META-01 warning; no class-specific rules applied.
    Verdict: UNVERIFIABLE (GWS rules still run; if GWS present and correct, only
    the R-META-01 warning fires).
    """
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["beverage_class"] = None
    r = check_compliance(ExtractionResult.from_dict(data))
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-META-01" in warning_rules, "Null beverage_class must fire R-META-01 warning"
    assert r.verdict == "UNVERIFIABLE"


def test_gws_body_high_confidence_wrong_text_is_error():
    """
    R-GW-02 at high confidence with wrong body text must fire as error → NONCOMPLIANT.
    Regression: a previous fixture only tested the low-confidence (warning) path.
    """
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["fields"]["gws_body"] = {
        "value": "(1) According to the Surgeon General, drinking is fine. (2) No problems.",
        "confidence": "high",
    }
    r = check_compliance(ExtractionResult.from_dict(data))
    assert r.verdict == "NONCOMPLIANT", (
        "High-confidence wrong GWS body text must produce NONCOMPLIANT"
    )
    error_rules = {i.rule_id for i in r.errors}
    assert "R-GW-02" in error_rules


def test_wine_vintage_empty_appellation_r_wn_08():
    """
    Vintage stated but appellation is an empty string (not None, not not_found).
    R-WN-08 must fire — empty string is treated as absent.
    """
    data = json.loads((FIXTURES / "wine_compliant.json").read_text())
    data["fields"]["appellation"] = {"value": "", "confidence": "high"}
    r = check_compliance(ExtractionResult.from_dict(data))
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-WN-08" in warning_rules, (
        "Empty-string appellation with a stated vintage must fire R-WN-08 warning"
    )


def test_spirits_low_confidence_proof_mismatch_is_warning():
    """
    Proof mismatch at low confidence must produce a warning, not an error.
    A blurry proof reading should not force NONCOMPLIANT.
    """
    data = json.loads((FIXTURES / "spirits_compliant.json").read_text())
    # Set ABV to 40% (compliant) and proof to 94 (mismatch: expected 80.0)
    # at low confidence — should be a warning, not an error
    data["fields"]["abv_pct"] = {"value": 40.0, "confidence": "high"}
    data["fields"]["proof"]   = {"value": 94.0, "confidence": "low"}
    r = check_compliance(ExtractionResult.from_dict(data))
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-DS-03" in warning_rules, (
        "Low-confidence proof mismatch must fire R-DS-03 as warning"
    )
    assert "R-DS-03" not in {i.rule_id for i in r.errors}, (
        "Low-confidence proof mismatch must NOT be an error"
    )


def test_gws_present_true_no_text_r_gw_01_warning():
    """
    gws_present=true (high confidence) but both gws_header and gws_body are not_found.
    The boolean is unverifiable without supporting text evidence.
    Expected: R-GW-01 not_found warning → UNVERIFIABLE.

    Design rationale: a boolean True with zero extractable text is the same
    evidentiary state as not_found. Emitting R-GW-01 explicitly is preferable
    to silently falling through to R-GW-02/03 not_found warnings (which would
    produce three separate warnings for one 'GWS unreadable' condition).
    See compliance_checker.py _check_gws for the documented alternative.
    """
    data = json.loads((FIXTURES / "beer_compliant.json").read_text())
    data["fields"]["gws_present"] = {"value": True,  "confidence": "high"}
    data["fields"]["gws_header"]  = {"value": None,  "confidence": "not_found"}
    data["fields"]["gws_body"]    = {"value": None,  "confidence": "not_found"}
    r = check_compliance(ExtractionResult.from_dict(data))
    warning_rules = {i.rule_id for i in r.warnings}
    assert "R-GW-01" in warning_rules, (
        "gws_present=true with no extractable text must fire R-GW-01 not_found warning"
    )
    assert r.verdict == "UNVERIFIABLE"
    # Must NOT also produce R-GW-02/03 (we return early after the R-GW-01 warning)
    assert "R-GW-02" not in warning_rules
    assert "R-GW-03" not in warning_rules
