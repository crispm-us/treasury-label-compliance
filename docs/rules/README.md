# TTB Compliance Rules — Reference Files

## Purpose

These files are the **authoritative source of truth** for what the compliance checker code must implement. They are not runtime inputs — they are development-time references that serve three purposes:

1. **Code validation:** Any developer (or adversarial AI reviewer) can compare `compliance_checker.py` against these files to verify that every required check is implemented, correctly, with no rules missing or misinterpreted.
2. **Regression reference:** When TTB regulations change, these files are updated first; the code is then brought into alignment.
3. **Transparency:** Evaluators and auditors can read these files to understand exactly what the system checks and why.

## Validation Workflow

This is not an automated runtime check. It is an ad-hoc development-time review:

```
docs/rules/*.md  ──────────────────────────────────────────┐
    (the law)                                               │
                                                            ▼
backend/app/services/compliance_checker.py  ←──── human or AI review
    (the implementation)                         "Does every rule in the
                                                  .md have corresponding
                                                  code? Is the code correct?"
```

To run an adversarial check, paste the relevant rules file and `compliance_checker.py` to ChatGPT or Gemini with the prompt: *"Does this implementation correctly and completely implement every rule in this reference document? List any rules that are missing or incorrectly implemented."*

## File Index

| File | Scope | CFR Authority |
|---|---|---|
| `government-warning-statement.md` | All alcohol beverages ≥0.5% ABV | 27 CFR Part 16 |
| `distilled-spirits.md` | Spirits (whiskey, vodka, gin, rum, tequila, etc.) | 27 CFR Part 5 |
| `wine.md` | Wine ≥7% ABV | 27 CFR Part 4 |
| `beer-malt.md` | Malt beverages and beer | 27 CFR Part 7 |

These files cover the CFR regulatory rules (`R-GW-*`, `R-DS-*`, `R-MB-*`, `R-WN-*`). The cross-field validation rules (`R-META-*`) and Mode A application-matching rules (`R-APP-*`) are not CFR-derived; they are implemented in `compliance_checker.py` and `application_checker.py` and documented in `IMPLEMENTATION_STATUS.md` and `docs/FAQ.md` rather than here.

## Note on Regulatory Currency

These files were compiled in June 2026. TTB regulations are updated periodically. The authoritative current text is always at:
- [eCFR Title 27](https://www.ecfr.gov/current/title-27/chapter-I/subchapter-A)
- [TTB Labeling Resources](https://www.ttb.gov/regulated-commodities/labeling/labeling-resources)

Before submitting a production system, verify the current CFR text against these files.
