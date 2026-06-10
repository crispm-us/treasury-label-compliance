# ADR-009: Two-Layer Architecture — AI Extraction + Deterministic Compliance

Date: 2026-06-09
Status: Accepted

## Context

A compliance system has two fundamentally different tasks:

1. **Reading the label:** Extracting text and visual properties from an image. This is inherently uncertain — images vary in quality, angle, lighting, and format. An AI model is the right tool.
2. **Applying the rules:** Checking whether the extracted fields meet TTB regulations. This is deterministic — the rules are fixed by law, and a given set of field values either satisfies them or does not. An AI model is the wrong tool here.

Mixing these tasks (asking an LLM to "check if this label is compliant") produces a system that is:
- Hard to test (LLM outputs are non-deterministic)
- Hard to audit (reasoning is opaque)
- Easy to hallucinate toward a false positive or false negative
- Impossible to validate against the rules files in `docs/rules/`

## Decision

The system is strictly two layers with no overlap:

```
Layer 1 — AI Extraction (non-deterministic, vision model)
  Input:  label image
  Output: structured JSON of extracted fields, with per-field confidence

Layer 2 — Compliance Check (deterministic, pure Python)
  Input:  structured JSON from Layer 1 (or from Mode A form submission)
  Output: compliant: bool, issues: list[Issue]

No AI component in Layer 2. No rule-checking in Layer 1.
```

### Layer 1: Extraction schema

The model returns a fixed JSON schema for every label:

```json
{
  "beverage_type": "spirits | wine | beer | unknown",
  "brand_name": { "value": "OLD TOM DISTILLERY", "confidence": "high | medium | low | not_found" },
  "class_type": { "value": "Kentucky Straight Bourbon Whiskey", "confidence": "high" },
  "alcohol_content": { "value": "45% Alc./Vol.", "confidence": "high" },
  "net_contents": { "value": "750 mL", "confidence": "high" },
  "bottler_name_address": { "value": "Old Tom Distillery, Louisville, KY", "confidence": "medium" },
  "country_of_origin": { "value": null, "confidence": "not_found" },
  "government_warning": {
    "present": true,
    "text": "GOVERNMENT WARNING: (1) According...",
    "government_warning_bold": true,
    "body_bold": false,
    "confidence": "high"
  },
  "vintage_date": { "value": null, "confidence": "not_found" },
  "sulfite_declaration": { "value": null, "confidence": "not_found" },
  "same_field_of_vision": { "value": "yes | no | cannot_determine", "confidence": "medium" },
  "additional_notes": "..."
}
```

### Layer 2: Compliance checker

Pure Python function — no imports of LLM libraries, no API calls:

```python
def check_compliance(fields: ExtractedFields, rules: RuleSet) -> ComplianceResult:
    issues = []
    # Each rule is an explicit conditional, referencing a specific rule ID
    if not fields.brand_name.value:
        issues.append(Issue(field="brand_name", rule="R-DS-01", severity="error",
                            found=None, expected="Brand name must be present"))
    # ... etc.
    return ComplianceResult(compliant=len(errors) == 0, issues=issues)
```

Every `Issue` object includes: `field`, `rule` (maps to a rule ID in `docs/rules/`), `severity` (error/warning), `found` (what was extracted), `expected` (what the rule requires).

### Prompt design for Layer 1 (precision requirement)

The model prompt for extraction must be explicit about not guessing:

```
You are extracting information from an alcohol beverage label image.

CRITICAL INSTRUCTIONS:
- Extract ONLY text that is explicitly and clearly visible on the label.
- Do NOT infer, interpolate, complete partial text, or guess any field value.
- If a field is not clearly visible or is absent, set its value to null and confidence to "not_found".
- If text is partially visible (e.g., obscured, cut off, or blurry), set confidence to "low" and include only the portion that is certain.
- Do NOT assume standard or typical values for any field (e.g., do not assume "750 mL" if you cannot read the net contents clearly).
- For the government warning statement: copy the exact text visible, character by character. Do not reproduce it from memory.

Return your response as valid JSON matching the schema below. No prose before or after the JSON.
[schema follows]
```

The "do not reproduce from memory" instruction for the warning statement is critical — models know the standard warning text and may auto-complete it even when it is absent, truncated, or altered on the label.

## Consequences

- Layer 2 is fully unit-testable without any model calls (Mode A test harness is the direct path for this)
- Every compliance failure maps to a specific rule ID in `docs/rules/` — auditors can trace any verdict to its legal basis
- The rules files in `docs/rules/` can be compared against `compliance_checker.py` as a validation step (see `docs/rules/README.md`)
- Non-determinism is entirely contained in Layer 1; Layer 2 is reproducible given the same input
- Confidence thresholds: fields with confidence "low" or "not_found" that are mandatory produce warnings, not hard errors, since the field may be present but unreadable — a human reviewer should verify

## Alternatives Considered

**Single-pass: ask the LLM to check compliance directly.** "Look at this label and tell me if it is TTB-compliant." Fast to implement, but: non-deterministic, untestable, unauditable, prone to hallucination in both directions, and cannot be validated against the rules files. Rejected.

**Use a structured LLM output parser for compliance too.** Still LLM-based; non-determinism problem remains. Rejected.
