"""Tests for SchemaMapper."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mapper.schema_mapper import SchemaMapper, map_to_schema, _best_raw_key, _normalise_key
from schemas.core import FieldConfidence, ProductBase
from schemas.sites import BambulabProduct, FormlabsProduct, UltimakerProduct, ActiveFloorProduct


# ── _normalise_key ───────────────────────────────────────────────────────────
class TestNormaliseKey:
    def test_lowercases(self):
        assert _normalise_key("ProductName") == "productname"

    def test_replaces_underscores(self):
        assert _normalise_key("product_name") == "product name"

    def test_replaces_hyphens(self):
        assert _normalise_key("product-name") == "product name"

    def test_strips_whitespace(self):
        assert _normalise_key("  price  ") == "price"

    def test_collapses_spaces(self):
        assert _normalise_key("product   name") == "product name"


# ── _best_raw_key ─────────────────────────────────────────────────────────────
class TestBestRawKey:
    def test_exact_match_returns_high(self):
        raw_keys = ["product_name", "price", "category"]
        key, conf = _best_raw_key("product_name", raw_keys)
        assert key == "product_name"
        assert conf == FieldConfidence.HIGH

    def test_case_insensitive_exact(self):
        raw_keys = ["Product Name", "Price"]
        key, conf = _best_raw_key("product_name", raw_keys)
        assert key == "Product Name"
        assert conf == FieldConfidence.HIGH

    def test_alias_match_returns_high(self):
        # "cost" is an alias for "price"
        raw_keys = ["Cost", "Model"]
        key, conf = _best_raw_key("price", raw_keys)
        assert key == "Cost"
        assert conf == FieldConfidence.HIGH

    def test_fuzzy_match_returns_low(self):
        # "Prise" is close to "price" but not exact or alias
        raw_keys = ["Prise"]
        key, conf = _best_raw_key("price", raw_keys)
        assert key == "Prise"
        assert conf == FieldConfidence.LOW

    def test_no_match_returns_missing(self):
        raw_keys = ["color", "brand"]
        key, conf = _best_raw_key("price", raw_keys)
        assert key is None
        assert conf == FieldConfidence.MISSING

    def test_alias_title_returns_high(self):
        # "title" is an alias for "product_name"
        raw_keys = ["title", "url"]
        key, conf = _best_raw_key("product_name", raw_keys)
        assert key == "title"
        assert conf == FieldConfidence.HIGH

    def test_fuzzy_dimensions_alias(self):
        # "Dimensions" close to "specifications" alias "specs"? No —
        # but "technical specifications" is an alias for technical_specifications
        raw_keys = ["Technical Specifications"]
        key, conf = _best_raw_key("technical_specifications", raw_keys)
        assert key == "Technical Specifications"
        assert conf == FieldConfidence.HIGH


# ── SchemaMapper ──────────────────────────────────────────────────────────────
class TestSchemaMapper:
    def test_exact_key_mapping(self):
        raw = {
            "product_name": "X1 Carbon",
            "category": "3D Printers",
            "price": "$1,449",
            "product_url": "https://bambulab.com/x1c",
        }
        mapper = SchemaMapper(BambulabProduct)
        product = mapper.map(raw)

        assert product.product_name == "X1 Carbon"
        assert product.price == "$1,449"
        assert product.get_confidence("product_name") == FieldConfidence.HIGH
        assert product.get_confidence("price") == FieldConfidence.HIGH

    def test_alias_key_mapping(self):
        # LLM returns "title" and "Cost" instead of "product_name" / "price"
        raw = {"title": "P1S", "Cost": "$699"}
        mapper = SchemaMapper(BambulabProduct)
        product = mapper.map(raw)

        assert product.product_name == "P1S"
        assert product.price == "$699"
        assert product.get_confidence("product_name") == FieldConfidence.HIGH
        assert product.get_confidence("price") == FieldConfidence.HIGH

    def test_missing_field_confidence(self):
        raw = {"product_name": "A1 Mini"}
        mapper = SchemaMapper(BambulabProduct)
        product = mapper.map(raw)

        assert product.price is None
        assert product.get_confidence("price") == FieldConfidence.MISSING

    def test_fuzzy_inference_marked_low(self):
        # "Prise" → should match "price" with low confidence
        raw = {"product_name": "Widget", "Prise": "$200"}
        mapper = SchemaMapper(BambulabProduct)
        product = mapper.map(raw)

        assert product.price == "$200"
        assert product.get_confidence("price") == FieldConfidence.LOW

    def test_extra_raw_keys_pass_through(self):
        raw = {"product_name": "X1C", "weird_custom_field": "hello"}
        mapper = SchemaMapper(BambulabProduct)
        product = mapper.map(raw)

        # Pydantic extra="allow" stores the extra field
        assert getattr(product, "weird_custom_field", None) == "hello"

    def test_map_many(self):
        raw_list = [
            {"product_name": "A1", "price": "$299"},
            {"product_name": "P1P", "price": "$599"},
        ]
        mapper = SchemaMapper(BambulabProduct)
        products = mapper.map_many(raw_list)

        assert len(products) == 2
        assert products[0].product_name == "A1"
        assert products[1].price == "$599"

    def test_formlabs_product_details_alias(self):
        # "description" is an alias for "product_details" in FormlabsProduct
        raw = {"product_name": "Form 4", "description": "Next-gen SLA printer"}
        mapper = SchemaMapper(FormlabsProduct)
        product = mapper.map(raw)

        assert product.product_details == "Next-gen SLA printer"
        assert product.get_confidence("product_details") == FieldConfidence.HIGH

    def test_ultimaker_specs_field(self):
        specs = [{"spec_name": "Dimensions", "type": "Build volume", "spec_value": "330mm"}]
        raw = {"product_name": "S7", "specs": specs}
        mapper = SchemaMapper(UltimakerProduct)
        product = mapper.map(raw)

        assert product.specs == specs
        assert product.get_confidence("specs") == FieldConfidence.HIGH

    def test_active_floor_height_metric(self):
        raw = {
            "product_name": "Floor 55",
            "category": "Floor",
            "height_metric": "60cm",
            "Height (imperial)": '24"',
        }
        mapper = SchemaMapper(ActiveFloorProduct)
        product = mapper.map(raw)

        assert product.height_metric == "60cm"
        assert product.get_confidence("height_metric") == FieldConfidence.HIGH


# ── map_to_schema convenience function ────────────────────────────────────────
class TestMapToSchema:
    def test_single_dict(self):
        raw = {"product_name": "Form 3+", "price": "$3,749"}
        result = map_to_schema(raw, FormlabsProduct)
        assert isinstance(result, FormlabsProduct)
        assert result.product_name == "Form 3+"

    def test_list_of_dicts(self):
        raw_list = [
            {"product_name": "Form 4", "price": "$4,999"},
            {"product_name": "Form 3L", "price": "$9,999"},
        ]
        results = map_to_schema(raw_list, FormlabsProduct)
        assert isinstance(results, list)
        assert len(results) == 2

    def test_null_string_mapped_to_none(self):
        raw = {"product_name": "Widget", "price": "N/A"}
        result = map_to_schema(raw, BambulabProduct)
        assert result.price is None

    def test_confidence_accessible_after_map(self):
        raw = {"product_name": "Lü Move", "Cost": "$5,000"}
        result = map_to_schema(raw, BambulabProduct)
        assert result.get_confidence("product_name") == FieldConfidence.HIGH
        assert result.get_confidence("price") == FieldConfidence.HIGH  # alias match
