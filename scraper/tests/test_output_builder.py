"""Tests for OutputBuilder (pytest version)."""
import csv
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from output.output_builder import OutputBuilder, _esc, _serialise_value, save_outputs
from schemas.core import FieldConfidence, ProductBase
from schemas.sites import BambulabProduct, FormlabsProduct


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _bambu(name: str, price: str | None, price_conf: FieldConfidence) -> BambulabProduct:
    p = BambulabProduct(
        product_name=name,
        category="3D Printers",
        price=price,
        product_url=f"https://bambulab.com/{name.lower().replace(' ', '-')}",
    )
    p.set_confidence("product_name", FieldConfidence.HIGH)
    p.set_confidence("category", FieldConfidence.HIGH)
    p.set_confidence("price", price_conf)
    p.set_confidence("product_url", FieldConfidence.HIGH)
    return p


@pytest.fixture()
def three_products():
    return [
        _bambu("X1 Carbon", "$1,449", FieldConfidence.HIGH),
        _bambu("P1S", "$699", FieldConfidence.LOW),
        _bambu("A1 Mini", None, FieldConfidence.MISSING),
    ]


@pytest.fixture()
def outdir(tmp_path):
    return tmp_path


# ── File creation ─────────────────────────────────────────────────────────────

class TestFileCreation:
    def test_all_three_files_created(self, three_products, outdir):
        paths = save_outputs(
            three_products, site="bambulab",
            output_prefix="test_bambu", outputs_dir=outdir,
        )
        assert paths["json"].exists()
        assert paths["csv"].exists()
        assert paths["html"].exists()

    def test_outputs_dir_created_if_missing(self, three_products, tmp_path):
        new_dir = tmp_path / "deep" / "nested"
        paths = save_outputs(
            three_products, site="bambulab",
            output_prefix="test", outputs_dir=new_dir,
        )
        assert new_dir.exists()
        assert paths["json"].exists()


# ── JSON ──────────────────────────────────────────────────────────────────────

class TestJSON:
    def test_record_count(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        records = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert len(records) == 3

    def test_confidence_dict_present(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        records = json.loads(paths["json"].read_text(encoding="utf-8"))
        for r in records:
            assert "_field_confidence" in r

    def test_confidence_values(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        records = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert records[0]["_field_confidence"]["price"] == "high"
        assert records[1]["_field_confidence"]["price"] == "low"
        assert records[2]["_field_confidence"]["price"] == "missing"

    def test_empty_products(self, outdir):
        paths = save_outputs([], site="bambulab",
                             output_prefix="empty", outputs_dir=outdir)
        records = json.loads(paths["json"].read_text(encoding="utf-8"))
        assert records == []


# ── CSV ───────────────────────────────────────────────────────────────────────

class TestCSV:
    def _read_csv(self, path: Path):
        with path.open(encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))

    def test_row_count(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        rows = self._read_csv(paths["csv"])
        assert len(rows) == 3

    def test_high_field_no_suffix(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        rows = self._read_csv(paths["csv"])
        assert rows[0]["price"] == "$1,449"

    def test_low_field_star_suffix(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        rows = self._read_csv(paths["csv"])
        assert rows[1]["price"] == "$699 *"

    def test_missing_field_na(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        rows = self._read_csv(paths["csv"])
        assert rows[2]["price"] == "N/A"


# ── HTML ──────────────────────────────────────────────────────────────────────

class TestHTML:
    def test_valid_html_structure(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert "<table>" in html
        assert "</table>" in html

    def test_colour_classes_present(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "#d4edda" in html   # green HIGH
        assert "#fff3cd" in html   # yellow LOW
        assert "#f8d7da" in html   # red MISSING

    def test_badge_classes_present(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "badge-low" in html
        assert "badge-missing" in html

    def test_product_names_in_table(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "X1 Carbon" in html
        assert "P1S" in html
        assert "A1 Mini" in html

    def test_legend_present(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "legend" in html

    def test_stats_present(self, three_products, outdir):
        paths = save_outputs(three_products, site="bambulab",
                             output_prefix="t", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "products" in html

    def test_empty_products_message(self, outdir):
        paths = save_outputs([], site="bambulab",
                             output_prefix="empty", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "No products extracted" in html

    def test_html_escaping(self, outdir):
        p = BambulabProduct(product_name='<script>alert("xss")</script>', category="Test")
        p.set_confidence("product_name", FieldConfidence.HIGH)
        paths = save_outputs([p], site="bambulab",
                             output_prefix="xss_test", outputs_dir=outdir)
        html = paths["html"].read_text(encoding="utf-8")
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ── Helpers ───────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_esc_ampersand(self):
        assert _esc("A & B") == "A &amp; B"

    def test_esc_tags(self):
        assert _esc("<b>") == "&lt;b&gt;"

    def test_esc_none(self):
        assert _esc(None) == ""

    def test_serialise_list(self):
        assert _serialise_value(["a", "b", "c"]) == "a | b | c"

    def test_serialise_none(self):
        assert _serialise_value(None) == ""

    def test_serialise_dict(self):
        result = _serialise_value({"k": "v"})
        assert "k" in result and "v" in result
