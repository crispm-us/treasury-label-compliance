"""
Deterministic TTB label compliance checker — Layer 2 of the two-layer architecture.

Input:  ExtractionResult (parsed from Layer 1 AI extraction JSON, schema in ADR-011)
Output: ComplianceResult — verdict + list of Issues, each mapped to a rule ID

No AI/ML imports. No external API calls. Pure Python.
Every Issue.rule_id corresponds to a rule entry in docs/rules/*.md.

Usage:
    from backend.app.services.compliance_checker import ExtractionResult, check_compliance
    result = ExtractionResult.from_dict(json.loads(payload))
    verdict = check_compliance(result)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Canonical reference values  (27 CFR §16.21)
# ---------------------------------------------------------------------------

GWS_CANONICAL_HEADER = "GOVERNMENT WARNING:"

GWS_CANONICAL_BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a "
    "car or operate machinery, and may cause health problems."
)

# ---------------------------------------------------------------------------
# Schema types   (mirror extraction JSON; see ADR-011)
# ---------------------------------------------------------------------------

Confidence = Literal["high", "low", "not_found"]
Verdict    = Literal["COMPLIANT", "NONCOMPLIANT", "UNVERIFIABLE", "ERROR"]


@dataclass
class FieldValue:
    value:      Any          # str | float | bool | None
    confidence: Confidence

    @classmethod
    def from_dict(cls, d: dict) -> FieldValue:
        return cls(value=d["value"], confidence=d["confidence"])


@dataclass
class ExtractionFields:
    brand_name:          FieldValue
    class_type:          FieldValue
    abv_pct:             FieldValue   # float | None  — numeric ABV e.g. 45.0
    abv_text:            FieldValue   # str   | None  — original string e.g. "45% Alc/Vol"
    proof:               FieldValue   # float | None  — stated proof value
    net_contents_metric: FieldValue   # str   | None  — e.g. "750 mL"
    net_contents_us:     FieldValue   # str   | None  — e.g. "12 FL OZ" (beer)
    bottler_name:        FieldValue
    bottler_address:     FieldValue
    country_of_origin:   FieldValue
    gws_present:         FieldValue   # bool  | None
    gws_header:          FieldValue   # str   | None  — exact header text
    gws_body:            FieldValue   # str   | None  — exact verbatim body
    gws_header_bold:     FieldValue   # bool  | None  — visual bold detection (deferred R-GW-04)
    gws_body_bold:       FieldValue   # bool  | None  — visual bold detection (deferred R-GW-04)
    sulfite_declaration: FieldValue   # str   | None  — e.g. "CONTAINS SULFITES"
    vintage:             FieldValue   # str   | None  — wine vintage year
    appellation:         FieldValue   # str   | None  — wine appellation

    @classmethod
    def from_dict(cls, d: dict) -> ExtractionFields:
        return cls(**{k: FieldValue.from_dict(v) for k, v in d.items()})


@dataclass
class ExtractionResult:
    schema_version:   str
    readable:         bool
    beverage_class:   str | None   # "beer" | "spirits" | "wine" | "unknown" | None
    panels_provided:  list[str]    # e.g. ["front", "back"] or ["combined"]
    extraction_model: str
    fields:           ExtractionFields

    @classmethod
    def from_dict(cls, d: dict) -> ExtractionResult:
        return cls(
            schema_version   = d["schema_version"],
            readable         = d["readable"],
            beverage_class   = d.get("beverage_class"),
            panels_provided  = d.get("panels_provided", []),
            extraction_model = d.get("extraction_model", "unknown"),
            fields           = ExtractionFields.from_dict(d["fields"]),
        )


# ---------------------------------------------------------------------------
# Issue / Result
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    rule_id:  str                          # e.g. "R-GW-01"
    severity: Literal["error", "warning"]
    field:    str                          # JSON field name from ExtractionFields
    found:    Any                          # extracted value (or None)
    expected: str                          # human-readable expectation / CFR citation
    not_found: bool = False                # True when field was absent from the image
                                           # (confidence="not_found"); used to set the
                                           # partial_verification flag in API responses


@dataclass
class ComplianceResult:
    verdict:        Verdict
    beverage_class: str | None
    issues:         list[Issue] = field(default_factory=list)

    @property
    def compliant(self) -> bool:
        return self.verdict == "COMPLIANT"

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ABV cross-validation helper
# ---------------------------------------------------------------------------

_ABV_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def _parse_abv_from_text(abv_text: str) -> float | None:
    """
    Extract the first 'XX.X%' numeric value from an ABV text string.

    Handles common label formats:
      "8% ALC. BY VOL."  → 8.0
      "45% Alc/Vol"      → 45.0
      "ALC. 5.2% VOL."   → 5.2
    Returns None if no percentage value is found.
    """
    m = _ABV_PCT_RE.search(str(abv_text))
    return float(m.group(1)) if m else None


def _normalize(text: str | None) -> str:
    """Collapse all whitespace runs to a single space for text comparison."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


_PAREN_SPACE_RE      = re.compile(r"\)(\w)")
_HYPHEN_BREAK_RE     = re.compile(r"-\s+")
_GWS_HEADER_PREFIX_RE = re.compile(r"^GOVERNMENT\s+WARNING\s*:\s*", re.IGNORECASE)


def _strip_gws_header_prefix(text: str) -> str:
    """
    Remove a leading 'GOVERNMENT WARNING:' prefix from GWS body text.

    Some vision models concatenate the header into the body field rather than
    returning them separately.  Without this strip, a compliant label whose
    body was returned as 'GOVERNMENT WARNING: (1) According to...' would fail
    the verbatim comparison and produce a false-positive R-GW-02.

    Applied symmetrically to both extracted and canonical text so the
    normalization cannot mask substantive body differences.
    """
    return _GWS_HEADER_PREFIX_RE.sub("", text)


def _normalize_gws_header(text: str | None) -> str:
    """
    Normalize GWS header text for verbatim comparison.

    Extends _normalize() with a colon-space fix: strips any whitespace
    that appears immediately before a colon.  This corrects an OCR artifact
    where the vision model reads "GOVERNMENT WARNING :" (space before colon)
    instead of "GOVERNMENT WARNING:".

    Applied symmetrically to both extracted text and the canonical constant.
    """
    return re.sub(r"\s+:", ":", _normalize(text))


def _normalize_gws_body(text: str | None) -> str:
    """
    Normalize GWS body text for verbatim comparison.

    Extends _normalize() with three OCR-artifact corrections, applied in order:

    1. Hyphen-break join: removes "- " sequences produced when the vision model
       reads a word that is hyphenated across a line on a narrow-column label:
           'BE- CAUSE'     →  'BECAUSE'
           'CON- SUMPTION' →  'CONSUMPTION'
           'MA- CHINERY'   →  'MACHINERY'

    2. Period-paren space: inserts a space between a sentence-ending period and
       an opening parenthesis, e.g. when the model reads "(2)" flush against the
       preceding sentence with no gap:
           'BIRTH DEFECTS.(2) Consumption'  →  'BIRTH DEFECTS. (2) Consumption'

    3. Paren-word space: inserts a space between a closing parenthesis and the
       immediately following word character:
           '(1)According to…'  →  '(1) According to…'
           '(2)Consumption…'   →  '(2) Consumption…'

    Applied symmetrically to both extracted text and the canonical constant so
    these normalizations cannot mask substantive text differences.
    """
    t = _normalize(text)
    t = _HYPHEN_BREAK_RE.sub("", t)           # join hyphenated line-breaks
    t = re.sub(r"\.\(", ". (", t)             # space between period and opening paren
    t = _PAREN_SPACE_RE.sub(r") \1", t)       # space between closing paren and word
    return t


def _check_mandatory(
    fv: FieldValue,
    rule_id: str,
    field_name: str,
    label: str,
    issues: list[Issue],
) -> bool:
    """
    Assert a mandatory field is present and usable.

    Confidence semantics:
      not_found              → field absent from image (may be on another panel) → WARNING
      high | low, value None → model searched and confirmed the field is absent  → ERROR (high) / WARNING (low)
      high | low, value set  → field is present and readable                     → True (no issue added)

    Returns True if the field has a usable value; False if an issue was appended.
    """
    if fv.confidence == "not_found":
        issues.append(Issue(
            rule_id=rule_id, severity="warning", field=field_name, found=None,
            expected=f"{label} not visible in provided images — verify field is present on label",
            not_found=True,
        ))
        return False
    # Treat empty / whitespace-only strings as absent (model sometimes returns "" instead of null)
    value_absent = fv.value is None or (isinstance(fv.value, str) and not fv.value.strip())
    if value_absent:
        sev: Literal["error", "warning"] = "error" if fv.confidence == "high" else "warning"
        issues.append(Issue(
            rule_id=rule_id, severity=sev, field=field_name, found=fv.value,
            expected=f"{label} must be present on label",
        ))
        return False
    return True


# ---------------------------------------------------------------------------
# GWS rules — apply to all beverage classes (27 CFR Part 16)
# ---------------------------------------------------------------------------

def _check_gws(f: ExtractionFields, issues: list[Issue]) -> None:
    """R-GW-01, R-GW-02, R-GW-03.  R-GW-04 deferred (bold detection unreliable in v1)."""

    # Determine whether the GWS is effectively present.
    # The model occasionally produces contradictory output: gws_present=false while
    # still extracting header/body text.  Text evidence takes precedence — if either
    # text field has a value the GWS is present regardless of the flag.
    header_found = f.gws_header.confidence != "not_found" and f.gws_header.value is not None
    body_found   = f.gws_body.confidence   != "not_found" and f.gws_body.value   is not None
    gws_text_present = header_found or body_found

    # Coerce gws_present.value: some models emit the JSON string "true"/"false"
    # instead of a JSON boolean, which falls through all `is True`/`is False`
    # identity checks and is misclassified as None (no signal → R-GW-01 warning).
    _gws_present_val = f.gws_present.value
    if isinstance(_gws_present_val, str):
        _gws_present_val = {"true": True, "false": False, "yes": True, "no": False}.get(
            _gws_present_val.strip().lower(), _gws_present_val
        )

    if gws_text_present:
        gws_effectively_present: bool | None = True
    elif _gws_present_val is True:
        # Boolean claims present but no header or body text could be extracted.
        #
        # Design choice: emit R-GW-01 as a not_found warning and return early.
        # The GWS cannot be verified from available evidence — an unverifiable boolean
        # True is the same evidentiary state as not_found, and surfacing it explicitly
        # gives callers a clear signal to request a clearer image.
        #
        # Alternative considered and rejected: trust the boolean, skip R-GW-01,
        # and fall through to R-GW-02/03 (which would both fire as not_found warnings).
        # Rejected because three separate warnings for what is essentially one
        # "GWS text unreadable" condition is confusing; a single R-GW-01 not_found
        # warning at the right level of abstraction communicates the same information.
        issues.append(Issue(
            rule_id="R-GW-01", severity="warning",
            field="gws_present", found=True,
            expected=(
                "GWS boolean indicates present but no header or body text could be extracted — "
                "cannot verify content. Submit a clearer image of the Government Warning "
                "Statement (27 CFR §16.21)"
            ),
            not_found=True,
        ))
        return  # Cannot verify R-GW-02/03 without text
    elif _gws_present_val is False:
        gws_effectively_present = False
    else:
        gws_effectively_present = None  # not_found / no signal

    # R-GW-01: GWS must be present
    if gws_effectively_present is None:
        issues.append(Issue(
            rule_id="R-GW-01", severity="warning",
            field="gws_present", found=None,
            expected=(
                "Government Warning Statement not visible in provided images — "
                "verify it appears on label (27 CFR §16.21)"
            ),
            not_found=True,
        ))
        return  # Cannot check R-GW-02/03 without text

    if not gws_effectively_present:
        sev = "error" if f.gws_present.confidence == "high" else "warning"
        issues.append(Issue(
            rule_id="R-GW-01", severity=sev,
            field="gws_present", found=False,
            expected=(
                "Government Warning Statement must appear on every alcoholic beverage "
                "label ≥0.5% ABV (27 CFR §16.21)"
            ),
        ))
        if sev == "error":
            return  # Definitively absent — no point checking header/body

    # R-GW-03: header must be exactly "GOVERNMENT WARNING:" (all-caps)
    if f.gws_header.confidence != "not_found" and f.gws_header.value is not None:
        header = _normalize_gws_header(f.gws_header.value)
        if header != GWS_CANONICAL_HEADER:
            sev = "error" if f.gws_header.confidence == "high" else "warning"
            issues.append(Issue(
                rule_id="R-GW-03", severity=sev,
                field="gws_header", found=f.gws_header.value,
                expected=(
                    f'Header must be exactly "{GWS_CANONICAL_HEADER}" '
                    "in all-caps (27 CFR §16.22(a)(2))"
                ),
            ))
    else:
        issues.append(Issue(
            rule_id="R-GW-03", severity="warning",
            field="gws_header", found=None,
            expected="GWS header text not visible — cannot verify all-caps formatting",
            not_found=True,
        ))

    # R-GW-02: body must match verbatim canonical text
    # The canonical text (27 CFR §16.21) uses American English spelling.
    # Production note: labels from Canadian, UK, Australian, or other non-US
    # production facilities sometimes use Commonwealth spellings (e.g.
    # "impairs your ability" is fine, but hypothetical variants like "programme"
    # or "organisation" in the warning would be non-compliant).  The TTB has not
    # issued guidance permitting alternate spellings; the verbatim requirement
    # means any deviation — including non-American English spelling — is a
    # violation.  A future version may want to distinguish spelling-only deviations
    # from substantive text changes, both for human review triage and for any
    # waiver process.  For now, the check is strictly verbatim.
    if f.gws_body.confidence != "not_found" and f.gws_body.value is not None:
        # Comparison is case-insensitive: the CFR canonical text is mixed-case but
        # TTB regulations (27 CFR §16.22(a)(2)) require the statement to be printed
        # in capital letters.  Real labels therefore always print all-caps.  We
        # verify content correctness here; the all-caps printing requirement is a
        # separate concern (not independently checked in v1).
        body_normalized    = _normalize_gws_body(_strip_gws_header_prefix(f.gws_body.value)).upper()
        canon_normalized   = _normalize_gws_body(_strip_gws_header_prefix(GWS_CANONICAL_BODY)).upper()
        if body_normalized != canon_normalized:
            sev = "error" if f.gws_body.confidence == "high" else "warning"
            preview = f.gws_body.value[:120] + ("…" if len(f.gws_body.value) > 120 else "")
            issues.append(Issue(
                rule_id="R-GW-02", severity=sev,
                field="gws_body", found=preview,
                expected="GWS body must match verbatim text per 27 CFR §16.21",
            ))
    else:
        issues.append(Issue(
            rule_id="R-GW-02", severity="warning",
            field="gws_body", found=None,
            expected="GWS body text not fully visible — cannot verify verbatim compliance",
            not_found=True,
        ))

    # R-GW-04: header bold, body NOT bold — DEFERRED
    # gws_header_bold / gws_body_bold captured in schema but not checked in v1.
    # Vision-model bold detection is unreliable without a calibration baseline.
    # Activate after evaluating bold-detection accuracy on real labels.


# ---------------------------------------------------------------------------
# Beer rules (27 CFR Part 7)
# ---------------------------------------------------------------------------

def _check_beer(f: ExtractionFields, issues: list[Issue]) -> None:
    _check_mandatory(f.brand_name,         "R-MB-01", "brand_name",         "Brand name",            issues)
    _check_mandatory(f.class_type,          "R-MB-02", "class_type",          "Class/type designation", issues)
    _check_mandatory(f.net_contents_metric, "R-MB-04", "net_contents_metric", "Net contents (metric)",  issues)
    _check_mandatory(f.bottler_name,        "R-MB-05", "bottler_name",        "Brewer/bottler name",    issues)
    _check_mandatory(f.bottler_address,     "R-MB-05", "bottler_address",     "Brewer/bottler address", issues)

    # R-MB-03: ABV not universally mandatory for malt beverages — warn if absent
    if f.abv_pct.confidence == "not_found" or f.abv_pct.value is None:
        issues.append(Issue(
            rule_id="R-MB-03", severity="warning",
            field="abv_pct", found=None,
            expected=(
                "Alcohol content not visible. Required if product is a flavored malt beverage "
                "or contains flavor-derived alcohol (27 CFR §7.63(a)(3)). "
                "Not required for traditional beer/ale/lager/stout."
            ),
            not_found=f.abv_pct.confidence == "not_found",
        ))


# ---------------------------------------------------------------------------
# Spirits rules (27 CFR Part 5)
# ---------------------------------------------------------------------------

def _check_spirits(f: ExtractionFields, issues: list[Issue]) -> None:
    _check_mandatory(f.brand_name,         "R-DS-01", "brand_name",         "Brand name",                issues)
    _check_mandatory(f.class_type,          "R-DS-02", "class_type",          "Class/type designation",    issues)
    _check_mandatory(f.net_contents_metric, "R-DS-04", "net_contents_metric", "Net contents (metric)",     issues)
    _check_mandatory(f.bottler_name,        "R-DS-06", "bottler_name",        "Distiller/bottler name",    issues)
    _check_mandatory(f.bottler_address,     "R-DS-06", "bottler_address",     "Distiller/bottler address", issues)

    # R-DS-03: ABV is mandatory for spirits
    abv_present = _check_mandatory(f.abv_pct, "R-DS-03", "abv_pct", "Alcohol content (ABV)", issues)
    if abv_present and f.abv_pct.confidence in ("high", "low"):
        try:
            abv = float(f.abv_pct.value)
            if not (20.0 <= abv <= 95.0):
                # low confidence → warning (uncertain reading); high → definitive error
                sev: Literal["error", "warning"] = "error" if f.abv_pct.confidence == "high" else "warning"
                issues.append(Issue(
                    rule_id="R-DS-03", severity=sev,
                    field="abv_pct", found=f.abv_pct.value,
                    expected="ABV must be within 20%–95% for distilled spirits (27 CFR §5.36)",
                ))
        except (TypeError, ValueError):
            issues.append(Issue(
                rule_id="R-DS-03", severity="error",
                field="abv_pct", found=f.abv_pct.value,
                expected="ABV must be a numeric value (e.g. 45.0 for 45%)",
            ))

    # R-DS-03 proof consistency: proof must equal 2 × ABV (tolerance ±0.3 proof)
    # Severity follows proof confidence: a blurry proof reading at low confidence
    # should not force NONCOMPLIANT on an otherwise clean label.
    if (abv_present
            and f.proof.confidence != "not_found"
            and f.proof.value is not None
            and f.abv_pct.value is not None):
        try:
            proof    = float(f.proof.value)
            abv      = float(f.abv_pct.value)
            expected_proof = round(abv * 2, 1)
            if abs(proof - expected_proof) > 0.3:
                sev_proof: Literal["error", "warning"] = (
                    "error" if f.proof.confidence == "high" else "warning"
                )
                issues.append(Issue(
                    rule_id="R-DS-03", severity=sev_proof,
                    field="proof", found=proof,
                    expected=(
                        f"Proof must equal 2 × ABV; expected {expected_proof} proof "
                        f"for {abv}% ABV (27 CFR §5.35)"
                    ),
                ))
        except (TypeError, ValueError):
            pass  # non-numeric proof value — ignore here, ABV check already covers format


# ---------------------------------------------------------------------------
# Wine rules (27 CFR Part 4)
# ---------------------------------------------------------------------------

def _check_wine(f: ExtractionFields, issues: list[Issue]) -> None:
    _check_mandatory(f.brand_name,         "R-WN-01", "brand_name",         "Brand name",             issues)
    _check_mandatory(f.class_type,          "R-WN-02", "class_type",          "Class/type designation", issues)
    _check_mandatory(f.net_contents_metric, "R-WN-04", "net_contents_metric", "Net contents (metric)",  issues)
    _check_mandatory(f.bottler_name,        "R-WN-05", "bottler_name",        "Winery/bottler name",    issues)
    _check_mandatory(f.bottler_address,     "R-WN-05", "bottler_address",     "Winery/bottler address", issues)

    # R-WN-03: ABV mandatory for wine
    abv_present = _check_mandatory(f.abv_pct, "R-WN-03", "abv_pct", "Alcohol content (ABV)", issues)
    if abv_present and f.abv_pct.confidence in ("high", "low"):
        try:
            abv = float(f.abv_pct.value)
            if not (0.5 <= abv <= 24.0):
                # low confidence → warning (uncertain reading); high → definitive error
                sev = "error" if f.abv_pct.confidence == "high" else "warning"
                issues.append(Issue(
                    rule_id="R-WN-03", severity=sev,
                    field="abv_pct", found=f.abv_pct.value,
                    expected="ABV must be within 0.5%–24.0% for wine (27 CFR §4.36)",
                ))
        except (TypeError, ValueError):
            issues.append(Issue(
                rule_id="R-WN-03", severity="error",
                field="abv_pct", found=f.abv_pct.value,
                expected="ABV must be a numeric value",
            ))

    # R-WN-09: sulfite declaration — warning only; SO₂ level cannot be verified from image
    if f.sulfite_declaration.confidence == "not_found" or f.sulfite_declaration.value is None:
        issues.append(Issue(
            rule_id="R-WN-09", severity="warning",
            field="sulfite_declaration", found=None,
            expected=(
                "'Contains Sulfites' declaration not visible. Required if SO₂ ≥ 10 ppm "
                "(27 CFR §4.32(b)(3)). Virtually all commercially produced wine contains "
                "measurable sulfites — verify SO₂ level before release."
            ),
            not_found=f.sulfite_declaration.confidence == "not_found",
        ))

    # R-WN-08: vintage requires appellation
    # Use the same empty/whitespace guard as _check_mandatory — a model that
    # returns {"value": "", "confidence": "high"} for appellation while a vintage
    # is stated should still fire this rule.
    if f.vintage.confidence != "not_found" and f.vintage.value is not None:
        appellation_absent = (
            f.appellation.confidence == "not_found"
            or f.appellation.value is None
            or (isinstance(f.appellation.value, str) and not f.appellation.value.strip())
        )
        if appellation_absent:
            issues.append(Issue(
                rule_id="R-WN-08", severity="warning",
                field="appellation", found=f.appellation.value,
                expected=(
                    "Vintage date detected but appellation of origin not visible — "
                    "appellation required when vintage is stated (27 CFR §4.27)"
                ),
                not_found=f.appellation.confidence == "not_found",
            ))


# ---------------------------------------------------------------------------
# Cross-field validation — applies to all beverage classes
# ---------------------------------------------------------------------------

def _check_abv_cross_validation(f: ExtractionFields, issues: list[Issue]) -> None:
    """
    R-META-02: Cross-validate abv_pct against the numeric value in abv_text.

    Motivation: the model can hallucinate an internally consistent wrong ABV.
    Example observed on Mike's Harder: abv_pct=5.0, abv_text="8% ALC. BY VOL."
    both at high confidence. The range check passes (5% is valid for a beer-type
    product); only cross-referencing the two fields exposes the contradiction.

    Always fires at warning severity: the mismatch is a quality signal that
    requires human review to resolve — either field could be the incorrect one.
    """
    # Need both fields present with usable values
    if f.abv_pct.confidence not in ("high", "low") or f.abv_pct.value is None:
        return
    if f.abv_text.confidence not in ("high", "low") or f.abv_text.value is None:
        return

    try:
        abv_pct_num = float(f.abv_pct.value)
    except (TypeError, ValueError):
        return  # Non-numeric abv_pct already flagged by class-specific rule

    abv_text_num = _parse_abv_from_text(str(f.abv_text.value))
    if abv_text_num is None:
        issues.append(Issue(
            rule_id="R-META-02", severity="warning",
            field="abv_text", found=f.abv_text.value,
            expected=(
                "Could not parse a numeric ABV from abv_text for cross-validation "
                "with abv_pct — expected a value like '8% ALC. BY VOL.'"
            ),
        ))
        return

    if abs(abv_pct_num - abv_text_num) > 0.2:
        issues.append(Issue(
            rule_id="R-META-02", severity="warning",
            field="abv_pct", found=f.abv_pct.value,
            expected=(
                f"abv_pct ({abv_pct_num}%) does not match the value parsed from "
                f"abv_text ({abv_text_num}% from '{f.abv_text.value}'). "
                "One value may be a hallucination — verify on physical label."
            ),
        ))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_compliance(result: ExtractionResult) -> ComplianceResult:
    """
    Apply all applicable TTB compliance rules to an ExtractionResult.

    Verdict logic
    -------------
    ERROR        — image was not readable; no rules applied
    NONCOMPLIANT — ≥1 error-severity issue (definitive violation found)
    UNVERIFIABLE — no errors but ≥1 warning-severity issue
                   (field absent from image, low-confidence reading, or
                    conditional check that cannot be resolved from image alone)
    COMPLIANT    — no issues of any kind

    Known limitation (see ADR-011 §"Partial extraction with high-confidence violation"):
    When a partial extraction (some fields not_found) co-exists with a definitive
    high-confidence violation, the verdict is NONCOMPLIANT and the not_found warnings
    are also present in issues.  The caller should surface both the violation AND the
    warnings to the user, making clear that the full label could not be verified.
    Production handling of this mixed case is deferred — see ADR-011.
    """
    if not result.readable:
        return ComplianceResult(verdict="ERROR", beverage_class=result.beverage_class)

    issues: list[Issue] = []
    f = result.fields

    _check_gws(f, issues)

    bev = (result.beverage_class or "").lower()
    if bev == "beer":
        _check_beer(f, issues)
    elif bev == "spirits":
        _check_spirits(f, issues)
    elif bev == "wine":
        _check_wine(f, issues)
    else:
        issues.append(Issue(
            rule_id="R-META-01", severity="warning",
            field="beverage_class", found=result.beverage_class,
            expected="beverage_class must be 'beer', 'spirits', or 'wine' to apply class-specific rules",
        ))

    # Cross-field validation — applies regardless of beverage class
    _check_abv_cross_validation(f, issues)

    if any(i.severity == "error" for i in issues):
        verdict: Verdict = "NONCOMPLIANT"
    elif issues:
        verdict = "UNVERIFIABLE"
    else:
        verdict = "COMPLIANT"

    return ComplianceResult(verdict=verdict, beverage_class=result.beverage_class, issues=issues)
