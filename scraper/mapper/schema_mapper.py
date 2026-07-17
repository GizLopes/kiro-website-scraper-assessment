"""
Schema Mapper

Takes raw dict(s) returned by the LLM runner and maps them to the
target Pydantic schema, tracking per-field extraction confidence:

  high    → key found with exact (case-insensitive) match
  low     → key inferred via string-similarity (flagged yellow/red in report)
  missing → field expected by schema but not present in LLM output (null, flagged red)

Similarity engine: difflib.SequenceMatcher (no extra deps).
Threshold to accept a fuzzy match: SIMILARITY_THRESHOLD (default 0.72).
"""
from __future__ import annotations

import difflib
import re
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from schemas.core import FieldConfidence, ProductBase


# ── Config ────────────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.72   # 0–1; below this we consider the field missing

# Aliases help the matcher recognise common synonym pairs without needing
# high similarity scores (e.g. LLM says "Cost" but schema expects "price").
FIELD_ALIASES: Dict[str, List[str]] = {
    "price":              ["cost", "msrp", "retail price", "selling price", "sale price", "usd", "eur"],
    "product_name":       ["name", "title", "product title", "model", "model name", "item name"],
    "category":           ["type", "product type", "kind", "group"],
    "subcategory":        ["sub category", "sub-category", "sub type", "collection"],
    "product_url":        ["url", "link", "product link", "product page", "page url", "href"],
    "source_url":         ["listing url", "category url", "origin url"],
    "specifications":     ["specs", "technical specs", "tech specs", "spec table", "technical specifications"],
    "details":            ["description", "product description", "features", "product features", "overview"],
    "product_details":    ["description", "product description", "what's included", "whats included", "contents"],
    "display_size":       ["screen size", "size", "diagonal", "screen diagonal"],
    "resolution":         ["display resolution", "screen resolution", "pixel"],
    "touch_points":       ["touch", "multi-touch", "simultaneous touch"],
    "height_metric":      ["height", "h metric", "installation height"],
    "width_metric":       ["width", "w metric", "installation width"],
    "weight_metric":      ["weight", "mass", "net weight"],
    "target_age":         ["age", "age range", "recommended age", "age group"],
    "technical_specifications": ["key elements", "tech specs", "specifications list"],
    "price_current":      ["current price", "price now", "sale price", "discounted price"],
}


def _normalise_key(key: str) -> str:
    """Lower-case, replace separators with spaces, strip extra whitespace."""
    key = key.lower().strip()
    key = re.sub(r"[_\-/\\]", " ", key)
    key = re.sub(r"\s+", " ", key)
    return key


def _similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio between two normalised strings."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def _best_raw_key(
    target_field: str,
    raw_keys: List[str],
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> Tuple[Optional[str], FieldConfidence]:
    """
    Find the best matching key in raw_keys for target_field.

    Returns (matched_raw_key, confidence) or (None, missing).
    """
    norm_target = _normalise_key(target_field)
    norm_aliases = [_normalise_key(a) for a in FIELD_ALIASES.get(target_field, [])]
    norm_raw = {k: _normalise_key(k) for k in raw_keys}

    # 1) Exact match on normalised key or alias
    for raw_key, norm_raw_key in norm_raw.items():
        if norm_raw_key == norm_target or norm_raw_key in norm_aliases:
            return raw_key, FieldConfidence.HIGH

    # 2) Fuzzy match against field name
    best_score = 0.0
    best_key: Optional[str] = None
    for raw_key, norm_raw_key in norm_raw.items():
        score = _similarity(norm_raw_key, norm_target)
        # also try against each alias
        for alias in norm_aliases:
            alias_score = _similarity(norm_raw_key, alias)
            if alias_score > score:
                score = alias_score
        if score > best_score:
            best_score = score
            best_key = raw_key

    if best_score >= threshold:
        return best_key, FieldConfidence.LOW

    return None, FieldConfidence.MISSING


class SchemaMapper:
    """
    Maps a raw dict (LLM output) to a typed ProductBase subclass,
    annotating each field with extraction confidence.

    Usage:
        mapper = SchemaMapper(BambulabProduct)
        product = mapper.map(raw_dict)
        # product._field_confidence holds per-field confidence
    """

    def __init__(
        self,
        schema_class: Type[ProductBase],
        *,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> None:
        self.schema_class = schema_class
        self.threshold = threshold

    # ── Public API ────────────────────────────────────────────────────────

    def map(self, raw: Dict[str, Any]) -> ProductBase:
        """
        Map a single raw dict to the schema.
        Returns a populated schema instance with confidence metadata.
        """
        raw_keys = list(raw.keys())
        mapped: Dict[str, Any] = {}
        confidence: Dict[str, FieldConfidence] = {}

        # Collect the declared fields from the schema (including inherited)
        schema_fields = list(self.schema_class.model_fields.keys())

        for field_name in schema_fields:
            # Skip internal/private helpers
            if field_name.startswith("_"):
                continue

            raw_key, conf = _best_raw_key(field_name, raw_keys, threshold=self.threshold)

            if conf == FieldConfidence.MISSING or raw_key is None:
                mapped[field_name] = None
                confidence[field_name] = FieldConfidence.MISSING
            else:
                mapped[field_name] = raw[raw_key]
                confidence[field_name] = conf

        # Pass any extra raw keys that didn't match declared fields through as-is
        # (Pydantic extra="allow" will absorb them)
        declared_raw_keys_used = set()
        for field_name in schema_fields:
            rk, _ = _best_raw_key(field_name, raw_keys, threshold=self.threshold)
            if rk:
                declared_raw_keys_used.add(rk)

        for rk in raw_keys:
            if rk not in declared_raw_keys_used:
                mapped[rk] = raw[rk]

        product = self.schema_class(**mapped)

        # Attach confidence metadata (bypasses Pydantic validation intentionally)
        object.__setattr__(product, "_field_confidence", confidence)

        return product

    def map_many(self, raw_list: List[Dict[str, Any]]) -> List[ProductBase]:
        """Map a list of raw dicts to schema instances."""
        return [self.map(item) for item in raw_list]


# ── Convenience function ──────────────────────────────────────────────────────

def map_to_schema(
    raw: Union[Dict[str, Any], List[Dict[str, Any]]],
    schema_class: Type[ProductBase],
    *,
    threshold: float = SIMILARITY_THRESHOLD,
) -> Union[ProductBase, List[ProductBase]]:
    """
    Convenience wrapper around SchemaMapper.

    Examples:
        product  = map_to_schema({"Cost": "$499", "Size": "300mm"}, BambulabProduct)
        products = map_to_schema([...], BambulabProduct)
    """
    mapper = SchemaMapper(schema_class, threshold=threshold)
    if isinstance(raw, list):
        return mapper.map_many(raw)
    return mapper.map(raw)
