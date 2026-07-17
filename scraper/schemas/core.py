"""
Core Pydantic schema shared by all sites.

Every site-specific schema inherits from ProductBase and may add extra fields.
The _field_confidence dict tracks per-field extraction quality:
  - "high"    : field matched exactly by key name
  - "low"     : field inferred via semantic similarity (flagged in red/yellow in reports)
  - "missing" : field not found at all (null value, flagged in red)
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class FieldConfidence(str, Enum):
    HIGH = "high"
    LOW = "low"
    MISSING = "missing"


class ProductBase(BaseModel):
    """Base product record produced by any LLM browser agent extraction."""

    # ── Core fields every site must have ──────────────────────────────────
    product_name: Optional[str] = Field(None, description="Display name of the product")
    category: Optional[str] = Field(None, description="Top-level product category")
    subcategory: Optional[str] = Field(None, description="Sub-category within the site")
    price: Optional[str] = Field(None, description="Price as displayed on the page (string to preserve currency symbol)")
    product_url: Optional[str] = Field(None, description="Canonical URL of the product detail page")
    source_url: Optional[str] = Field(None, description="URL of the listing / entry page used")
    specifications: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Free-form key-value pairs from the product specs section",
    )
    scraped_at: Optional[str] = Field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        description="ISO-8601 UTC timestamp of extraction",
    )

    # ── Confidence tracking (populated by SchemaMapper, not the LLM) ─────
    _field_confidence: Dict[str, FieldConfidence] = {}

    model_config = {"extra": "allow"}

    # ── Helpers ────────────────────────────────────────────────────────────
    def set_confidence(self, field_name: str, confidence: FieldConfidence) -> None:
        self._field_confidence[field_name] = confidence

    def get_confidence(self, field_name: str) -> FieldConfidence:
        return self._field_confidence.get(field_name, FieldConfidence.MISSING)

    def confidence_dict(self) -> Dict[str, str]:
        """Return confidence map as plain strings for serialisation."""
        return {k: v.value for k, v in self._field_confidence.items()}

    def to_flat_dict(self) -> Dict[str, Any]:
        """
        Flatten the record to a dict suitable for CSV rows.
        specifications dict is JSON-serialised as a single string column.
        """
        import json

        data = self.model_dump(exclude_none=False)
        specs = data.pop("specifications", {}) or {}
        data["specifications"] = json.dumps(specs, ensure_ascii=False) if specs else ""
        data["_field_confidence"] = json.dumps(self.confidence_dict(), ensure_ascii=False)
        return data

    @model_validator(mode="before")
    @classmethod
    def _strip_none_strings(cls, values: Any) -> Any:
        """Normalise literal 'null', 'none', 'n/a' strings to Python None."""
        if not isinstance(values, dict):
            return values
        null_strings = {"null", "none", "n/a", "na", ""}
        for key, val in values.items():
            if isinstance(val, str) and val.strip().lower() in null_strings:
                values[key] = None
        return values
