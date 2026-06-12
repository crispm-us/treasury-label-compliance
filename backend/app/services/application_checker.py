"""
Mode A application-matching checker — compares extracted label fields against
declared COLA application values.

Runs after Layer 2 CFR compliance checks when application JSON is supplied.
Rule IDs R-APP-01 through R-APP-05.
"""
from __future__ import annotations

from backend.app.models.application import ApplicationFields
from backend.app.services.compliance_checker import ExtractionFields, FieldValue, Issue

# TTB's exact published tolerance is unverified — ±0.5% is a conservative
# working value; replace when confirmed.
_ABV_TOLERANCE_PCT = 0.5


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _low_conf_suffix(confidence: str) -> str:
    return " (low extraction confidence)" if confidence == "low" else ""


def _usable(fv: FieldValue) -> bool:
    return fv.confidence != "not_found"


def check(extracted: ExtractionFields, application: ApplicationFields) -> list[Issue]:
    """Compare extracted fields against declared application values."""
    issues: list[Issue] = []

    _check_brand_name(extracted, application, issues)
    _check_abv(extracted, application, issues)
    _check_class_type(extracted, application, issues)
    _check_net_contents(extracted, application, issues)
    _check_origin(extracted, application, issues)

    return issues


def _check_brand_name(
    extracted: ExtractionFields,
    application: ApplicationFields,
    issues: list[Issue],
) -> None:
    if application.brand_name is None:
        return
    fv = extracted.brand_name
    if not _usable(fv) or fv.value is None:
        return
    found_norm = _normalize_ws(str(fv.value))
    expected_norm = _normalize_ws(application.brand_name)
    if found_norm.casefold() != expected_norm.casefold():
        issues.append(Issue(
            rule_id="R-APP-01",
            severity="error",
            field="brand_name",
            found=fv.value,
            expected=(
                f"Brand name must match application declaration "
                f"'{application.brand_name}'{_low_conf_suffix(fv.confidence)}"
            ),
        ))


def _check_abv(
    extracted: ExtractionFields,
    application: ApplicationFields,
    issues: list[Issue],
) -> None:
    if application.abv_pct is None:
        return
    fv = extracted.abv_pct
    if not _usable(fv) or fv.value is None:
        return
    if abs(float(fv.value) - application.abv_pct) > _ABV_TOLERANCE_PCT:
        issues.append(Issue(
            rule_id="R-APP-02",
            severity="error",
            field="abv_pct",
            found=fv.value,
            expected=(
                f"ABV must match application declaration "
                f"({application.abv_pct}% ±{_ABV_TOLERANCE_PCT}%){_low_conf_suffix(fv.confidence)}"
            ),
        ))


def _check_class_type(
    extracted: ExtractionFields,
    application: ApplicationFields,
    issues: list[Issue],
) -> None:
    if application.class_type is None:
        return
    fv = extracted.class_type
    if not _usable(fv) or fv.value is None:
        return
    if str(fv.value).casefold() != application.class_type.casefold():
        issues.append(Issue(
            rule_id="R-APP-03",
            severity="error",
            field="class_type",
            found=fv.value,
            expected=(
                f"Class/type must match application declaration "
                f"'{application.class_type}'{_low_conf_suffix(fv.confidence)}"
            ),
        ))


def _net_contents_candidates(
    extracted: ExtractionFields,
) -> list[tuple[FieldValue, str]]:
    out: list[tuple[FieldValue, str]] = []
    for field_name in ("net_contents_metric", "net_contents_us"):
        fv: FieldValue = getattr(extracted, field_name)
        if _usable(fv) and fv.value is not None:
            out.append((fv, field_name))
    return out


def _check_net_contents(
    extracted: ExtractionFields,
    application: ApplicationFields,
    issues: list[Issue],
) -> None:
    if application.net_contents is None:
        return
    candidates = _net_contents_candidates(extracted)
    if not candidates:
        return
    expected_norm = _normalize_ws(application.net_contents)
    for fv, field_name in candidates:
        if _normalize_ws(str(fv.value)).casefold() == expected_norm.casefold():
            return
    fv, field_name = candidates[0]
    issues.append(Issue(
        rule_id="R-APP-04",
        severity="warning",
        field=field_name,
        found=fv.value,
        expected=(
            f"Net contents must match application declaration "
            f"'{application.net_contents}'{_low_conf_suffix(fv.confidence)}"
        ),
    ))


def _check_origin(
    extracted: ExtractionFields,
    application: ApplicationFields,
    issues: list[Issue],
) -> None:
    if application.origin is None:
        return
    fv = extracted.country_of_origin
    if not _usable(fv) or fv.value is None:
        return
    if str(fv.value).casefold() != application.origin.casefold():
        issues.append(Issue(
            rule_id="R-APP-05",
            severity="warning",
            field="country_of_origin",
            found=fv.value,
            expected=(
                f"Origin must match application declaration "
                f"'{application.origin}'{_low_conf_suffix(fv.confidence)}"
            ),
        ))
