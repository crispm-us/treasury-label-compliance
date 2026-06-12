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
    """
    model_config = ConfigDict(extra="ignore")

    brand_name:    str | None = None
    class_type:    str | None = None
    abv_pct:       float | None = None
    net_contents:  str | None = None
    origin:        str | None = None
    gws_required:  bool | None = None


def provided_field_names(application: ApplicationFields) -> list[str]:
    """Return JSON keys for application fields that were declared (non-null)."""
    return [name for name, value in application.model_dump().items() if value is not None]
