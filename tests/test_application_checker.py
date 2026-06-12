"""
Unit tests for Mode A application-matching (application_checker.py).

Loads extraction fixtures from tests/fixtures/extraction/ and application
fixtures from test-labels/applications/. No API layer, no model calls.

Run:
    uv run --with pytest pytest tests/test_application_checker.py -v
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from backend.app.models.application import ApplicationFields
from backend.app.services.application_checker import check
from backend.app.services.compliance_checker import ExtractionFields, ExtractionResult

FIXTURES = Path(__file__).parent / "fixtures" / "extraction"
APPLICATIONS = Path(__file__).parent.parent / "test-labels" / "applications"


def _fields(name: str) -> ExtractionFields:
    data = json.loads((FIXTURES / name).read_text())
    return ExtractionResult.from_dict(data).fields


def _app(name: str) -> ApplicationFields:
    return ApplicationFields.model_validate_json((APPLICATIONS / name).read_text())


def _rule_ids(issues) -> set[str]:
    return {i.rule_id for i in issues}


# ---------------------------------------------------------------------------
# brand_name
# ---------------------------------------------------------------------------

def test_brand_name_exact_match():
    issues = check(_fields("beer_mode_a_compliant.json"), _app("harbor-bay-lager-synth-mode-a-compliant.json"))
    assert "R-APP-01" not in _rule_ids(issues)


def test_brand_name_case_insensitive_match():
    application = ApplicationFields(brand_name="harbor bay lager", abv_pct=5.0)
    issues = check(_fields("beer_mode_a_compliant.json"), application)
    assert "R-APP-01" not in _rule_ids(issues)


def test_brand_name_mismatch():
    issues = check(_fields("beer_mode_a_R_APP_01.json"), _app("harbor-bay-lager-synth-mode-a-R-APP-01.json"))
    app_issues = [i for i in issues if i.rule_id == "R-APP-01"]
    assert len(app_issues) == 1
    assert app_issues[0].severity == "error"


# ---------------------------------------------------------------------------
# abv_pct
# ---------------------------------------------------------------------------

def test_abv_within_tolerance():
    application = ApplicationFields(abv_pct=5.4)
    issues = check(_fields("beer_mode_a_compliant.json"), application)
    assert "R-APP-02" not in _rule_ids(issues)


def test_abv_outside_tolerance():
    issues = check(_fields("beer_mode_a_R_APP_02.json"), _app("harbor-bay-lager-synth-mode-a-R-APP-02.json"))
    app_issues = [i for i in issues if i.rule_id == "R-APP-02"]
    assert len(app_issues) == 1
    assert app_issues[0].severity == "error"


def test_abv_low_extraction_confidence_message():
    data = json.loads((FIXTURES / "beer_mode_a_R_APP_02.json").read_text())
    data["fields"]["abv_pct"]["confidence"] = "low"
    fields = ExtractionResult.from_dict(data).fields
    application = ApplicationFields(abv_pct=5.0)
    issues = check(fields, application)
    app_issues = [i for i in issues if i.rule_id == "R-APP-02"]
    assert len(app_issues) == 1
    assert "(low extraction confidence)" in app_issues[0].expected


# ---------------------------------------------------------------------------
# class_type, origin, net_contents
# ---------------------------------------------------------------------------

def test_class_type_mismatch():
    issues = check(_fields("wine_mode_a_R_APP_03.json"), _app("mesa-verde-chardonnay-synth-mode-a-R-APP-03.json"))
    app_issues = [i for i in issues if i.rule_id == "R-APP-03"]
    assert len(app_issues) == 1
    assert app_issues[0].severity == "error"


def test_origin_mismatch():
    issues = check(_fields("wine_mode_a_R_APP_05.json"), _app("mesa-verde-chardonnay-synth-mode-a-R-APP-05.json"))
    app_issues = [i for i in issues if i.rule_id == "R-APP-05"]
    assert len(app_issues) == 1
    assert app_issues[0].severity == "warning"


def test_net_contents_mismatch():
    issues = check(_fields("spirits_mode_a_R_APP_04.json"), _app("canyon-ridge-bourbon-synth-mode-a-R-APP-04.json"))
    app_issues = [i for i in issues if i.rule_id == "R-APP-04"]
    assert len(app_issues) == 1
    assert app_issues[0].severity == "warning"


def test_double_violation_brand_and_abv():
    issues = check(
        _fields("spirits_mode_a_R_APP_01_02.json"),
        _app("canyon-ridge-bourbon-synth-mode-a-R-APP-01-02.json"),
    )
    rules = _rule_ids(issues)
    assert "R-APP-01" in rules
    assert "R-APP-02" in rules


# ---------------------------------------------------------------------------
# skip conditions
# ---------------------------------------------------------------------------

def test_null_application_field_skips_rule():
    application = ApplicationFields.model_validate(
        _app("harbor-bay-lager-synth-mode-a-R-APP-01.json").model_dump() | {"brand_name": None}
    )
    issues = check(_fields("beer_mode_a_R_APP_01.json"), application)
    assert "R-APP-01" not in _rule_ids(issues)


def test_not_found_extraction_skips_rule():
    data = copy.deepcopy(json.loads((FIXTURES / "beer_mode_a_R_APP_01.json").read_text()))
    data["fields"]["brand_name"] = {"value": None, "confidence": "not_found"}
    fields = ExtractionResult.from_dict(data).fields
    issues = check(fields, _app("harbor-bay-lager-synth-mode-a-R-APP-01.json"))
    assert "R-APP-01" not in _rule_ids(issues)
