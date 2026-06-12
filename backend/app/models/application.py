"""
COLA application field declarations for Mode A (application-matching).

Application JSON is assumed complete and authoritative: null means the field
was not declared for this product; non-null values are ground truth for
comparison against extracted label fields.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApplicationFields(BaseModel):
    """
    Declared values from the COLA application for this label.
    All fields are Optional: null means 'not declared for this product',
    not 'data missing'. Non-null values are authoritative — they are
    accepted as ground truth and compared directly against extracted
    label fields. The checker never validates application values.

    origin_as_stated: The exact origin string as declared in the COLA application.
    This is the string expected to appear on the label. R-APP-05 compares the
    extracted label country_of_origin against this value using normalized string
    comparison (case-insensitive, collapsed whitespace, stripped punctuation).
    Examples: "California", "Lawrenceburg, Kentucky", "American", "Scotland".

    origin_iso2_country: ISO 3166-1 alpha-2 country code asserted in the
    application (e.g. "US", "GB", "DE"). Not compared against the label by the
    compliance checker — asserts country-level identity of the declared origin
    (e.g. that "California" is "US"). Consistency between origin_as_stated and
    origin_iso2_country is assumed correct by declaration; validated by the COLA
    submission process, not this application. No ISO country list is maintained
    here. str | None with no runtime format validation.
    """
    model_config = ConfigDict(extra="ignore")

    brand_name:          str | None = None
    class_type:          str | None = None
    abv_pct:             float | None = None
    net_contents:        str | None = None
    origin_as_stated:    str | None = None
    origin_iso2_country: str | None = None
    gws_required:        bool | None = None


def provided_field_names(application: ApplicationFields) -> list[str]:
    """Return JSON keys for application fields declared for label comparison."""
    return [
        name for name, value in application.model_dump().items()
        if value is not None and name != "origin_iso2_country"
    ]
