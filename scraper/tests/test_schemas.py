"""Tests for Pydantic schemas."""
import json
import sys
from pathlib import Path

import pytest

# Make the scraper package importable when running from repo root or tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas.core import FieldConfidence, ProductBase
from schemas.sites import (
    SITE_SCHEMA_MAP,
    ActiveFloorProduct,
    BambulabProduct,
    FormlabsProduct,
    MakerbotProduct,
    PlayLuProduct,
    SmartTechProduct,
    UltimakerProduct,
)


# ── ProductBase ─────────────────────────────────────────────────────────────
class TestProductBase:
    def test_instantiate_empty(self):
        p = ProductBase()
        assert p.product_name is None
        assert p.specifications == {}

    def test_instantiate_with_core_fields(self):
        p = ProductBase(
            product_name="Widget Pro",
            category="Gadgets",
            price="$299",
            product_url="https://example.com/widget-pro",
        )
        assert p.product_name == "Widget Pro"
        assert p.price == "$299"

    def test_scraped_at_auto_populated(self):
        p = ProductBase()
        assert p.scraped_at is not None
        assert "T" in p.scraped_at  # ISO format

    def test_null_strings_normalised(self):
        p = ProductBase(product_name="null", price="N/A", category="none")
        assert p.product_name is None
        assert p.price is None
        assert p.category is None

    def test_set_and_get_confidence(self):
        p = ProductBase(product_name="Test")
        p.set_confidence("product_name", FieldConfidence.HIGH)
        p.set_confidence("price", FieldConfidence.LOW)
        assert p.get_confidence("product_name") == FieldConfidence.HIGH
        assert p.get_confidence("price") == FieldConfidence.LOW
        assert p.get_confidence("category") == FieldConfidence.MISSING  # default

    def test_confidence_dict_returns_strings(self):
        p = ProductBase(product_name="Test")
        p.set_confidence("product_name", FieldConfidence.HIGH)
        d = p.confidence_dict()
        assert d["product_name"] == "high"

    def test_to_flat_dict_serialises_specs(self):
        p = ProductBase(
            product_name="Widget",
            specifications={"weight": "1kg", "color": "blue"},
        )
        flat = p.to_flat_dict()
        assert "specifications" in flat
        specs = json.loads(flat["specifications"])
        assert specs["weight"] == "1kg"

    def test_to_flat_dict_includes_confidence(self):
        p = ProductBase(product_name="Widget")
        p.set_confidence("product_name", FieldConfidence.HIGH)
        flat = p.to_flat_dict()
        conf = json.loads(flat["_field_confidence"])
        assert conf["product_name"] == "high"

    def test_extra_fields_allowed(self):
        """Extra fields from site schemas should not raise."""
        p = ProductBase(product_name="X", custom_field="hello")
        assert p.custom_field == "hello"  # type: ignore[attr-defined]


# ── Site schemas ────────────────────────────────────────────────────────────
class TestSiteSchemas:
    def test_bambulab_inherits_base(self):
        b = BambulabProduct(
            product_name="X1 Carbon",
            category="3D Printers",
            price="$1,449",
            details="Multi-material | 256mm³ build volume",
        )
        assert b.product_name == "X1 Carbon"
        assert b.details is not None

    def test_formlabs_extra_field(self):
        f = FormlabsProduct(
            product_name="Form 4",
            product_details="Includes wash and cure station",
        )
        assert f.product_details == "Includes wash and cure station"

    def test_play_lu_list_field(self):
        p = PlayLuProduct(
            product_name="Lü Move",
            item_type="configuration",
            technical_specifications=["Sensor A", "Processor B"],
        )
        assert len(p.technical_specifications) == 2

    def test_ultimaker_specs_list(self):
        u = UltimakerProduct(
            product_name="S7 Pro Bundle",
            specs=[{"spec_name": "Dimensions", "type": "Build volume", "spec_value": "330x240x300mm"}],
        )
        assert u.specs[0]["spec_value"] == "330x240x300mm"

    def test_active_floor_dual_units(self):
        a = ActiveFloorProduct(
            product_name="ActiveFloor Floor 55",
            category="Floor",
            height_metric="60cm",
            height_imperial='24"',
        )
        assert a.height_metric == "60cm"
        assert a.height_imperial == '24"'

    def test_all_sites_in_registry(self):
        expected = {"active_floor", "smart_tech", "play_lu", "ultimaker", "makerbot", "bambulab", "formlabs"}
        assert set(SITE_SCHEMA_MAP.keys()) == expected

    def test_registry_returns_correct_types(self):
        assert SITE_SCHEMA_MAP["bambulab"] is BambulabProduct
        assert SITE_SCHEMA_MAP["formlabs"] is FormlabsProduct
        assert SITE_SCHEMA_MAP["ultimaker"] is UltimakerProduct


# ── FieldConfidence enum ────────────────────────────────────────────────────
class TestFieldConfidence:
    def test_values(self):
        assert FieldConfidence.HIGH.value == "high"
        assert FieldConfidence.LOW.value == "low"
        assert FieldConfidence.MISSING.value == "missing"

    def test_from_string(self):
        assert FieldConfidence("high") == FieldConfidence.HIGH
