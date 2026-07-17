"""Tests for Pipeline (integration tests)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.pipeline import (
    ALL_SITE_IDS,
    DEFAULT_OUTPUTS_DIR,
    DESCRIPTORS_DIR,
    FIXTURES_DIR,
    SITE_OUTPUT_PREFIXES,
    Pipeline,
    PipelineResult,
    run_site,
)
from runner.base_runner import RunnerResult
from runner.mock_runner import MockRunner
from schemas.core import FieldConfidence, ProductBase
from schemas.sites import SITE_SCHEMA_MAP


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_pipeline(tmp_path: Path, **kwargs) -> Pipeline:
    """Return a MockRunner pipeline that writes to a temp directory."""
    return Pipeline(
        runner_name="mock",
        outputs_dir=tmp_path,
        skip_output=kwargs.pop("skip_output", False),
        **kwargs,
    )


ALL_SITES = list(SITE_OUTPUT_PREFIXES.keys())


# ── PipelineResult dataclass ──────────────────────────────────────────────────

class TestPipelineResult:
    def test_success_when_no_errors(self):
        r = PipelineResult(site="bambulab", products=[], errors=[])
        assert r.success is True

    def test_failure_when_errors_present(self):
        r = PipelineResult(site="bambulab", errors=["stage failed"])
        assert r.success is False

    def test_product_count(self):
        from schemas.sites import BambulabProduct
        products = [BambulabProduct(product_name=f"P{i}") for i in range(4)]
        r = PipelineResult(site="bambulab", products=products)
        assert r.product_count == 4

    def test_product_count_empty(self):
        r = PipelineResult(site="test")
        assert r.product_count == 0

    def test_repr_ok(self):
        r = PipelineResult(site="bambulab", products=[], duration_s=1.5)
        text = repr(r)
        assert "bambulab" in text
        assert "ok" in text

    def test_repr_error(self):
        r = PipelineResult(site="test", errors=["boom"])
        assert "errors=" in repr(r)

    def test_duration_stored(self):
        r = PipelineResult(site="test", duration_s=3.14)
        assert r.duration_s == pytest.approx(3.14)

    def test_output_paths_default_empty(self):
        r = PipelineResult(site="test")
        assert r.output_paths == {}


# ── Pipeline construction ─────────────────────────────────────────────────────

class TestPipelineConstruction:
    def test_default_runner_is_mock(self, tmp_path):
        pl = Pipeline(outputs_dir=tmp_path)
        assert pl.runner_name == "mock"

    def test_custom_runner_name_stored(self, tmp_path):
        pl = Pipeline(runner_name="mock", outputs_dir=tmp_path)
        assert pl.runner_name == "mock"

    def test_site_ids_list_matches_registry(self):
        assert set(Pipeline.SITE_IDS) == set(SITE_OUTPUT_PREFIXES.keys())

    def test_seven_sites_registered(self):
        assert len(Pipeline.SITE_IDS) == 7

    def test_unknown_runner_raises(self, tmp_path):
        with pytest.raises(ValueError, match="Unknown runner"):
            Pipeline(runner_name="nonexistent", outputs_dir=tmp_path)

    def test_context_manager_closes_runner(self, tmp_path):
        closed = []

        class TrackingMock(MockRunner):
            def close(self):
                closed.append(True)
                super().close()

        pl = Pipeline(outputs_dir=tmp_path)
        pl._runner = TrackingMock(fixtures_dir=FIXTURES_DIR)
        with pl:
            pass
        assert closed == [True]

    def test_mock_runner_gets_fixtures_dir_injected(self, tmp_path):
        pl = Pipeline(runner_name="mock", outputs_dir=tmp_path)
        assert isinstance(pl._runner, MockRunner)
        assert pl._runner._fixtures_dir == FIXTURES_DIR


# ── Pipeline.run_site — structure ─────────────────────────────────────────────

class TestRunSiteStructure:
    @pytest.mark.parametrize("site", ALL_SITES)
    def test_returns_pipeline_result(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        assert isinstance(result, PipelineResult)

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_site_id_on_result(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        assert result.site == site

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_success_for_all_sites(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        assert result.success, f"site={site} errors={result.errors}"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_at_least_one_product(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        assert result.product_count >= 1, f"site={site} returned 0 products"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_products_are_product_base_instances(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        for p in result.products:
            assert isinstance(p, ProductBase), \
                f"site={site}: item {p!r} is not a ProductBase"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_products_have_correct_schema_type(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        expected_cls = SITE_SCHEMA_MAP[site]
        for p in result.products:
            assert isinstance(p, expected_cls), \
                f"site={site}: expected {expected_cls.__name__}, got {type(p).__name__}"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_duration_non_negative(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        assert result.duration_s >= 0.0

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_runner_result_attached(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        assert isinstance(result.runner_result, RunnerResult)

    def test_unknown_site_captured_as_error(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site("nonexistent_site_xyz")
        assert result.success is False
        assert any("nonexistent_site_xyz" in e or "schema" in e.lower() or "No schema" in e
                   for e in result.errors)


# ── Pipeline.run_site — output files ─────────────────────────────────────────

class TestRunSiteOutputFiles:
    @pytest.mark.parametrize("site", ALL_SITES)
    def test_output_files_created(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site(site)
        assert result.output_paths.get("json", Path()).exists(), \
            f"JSON missing for {site}"
        assert result.output_paths.get("csv",  Path()).exists(), \
            f"CSV missing for {site}"
        assert result.output_paths.get("html", Path()).exists(), \
            f"HTML missing for {site}"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_json_has_expected_prefix(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site(site)
        expected_prefix = SITE_OUTPUT_PREFIXES[site]
        json_path = result.output_paths["json"]
        assert json_path.name.startswith(expected_prefix), \
            f"site={site}: expected prefix '{expected_prefix}', got '{json_path.name}'"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_json_is_valid_and_non_empty(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site(site)
        records = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
        assert isinstance(records, list)
        assert len(records) >= 1

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_json_has_confidence_metadata(self, site, tmp_path):
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site(site)
        records = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
        for rec in records:
            assert "_field_confidence" in rec, \
                f"site={site}: record missing _field_confidence: {rec.get('product_name')}"

    def test_skip_output_no_files_written(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site("bambulab")
        assert result.output_paths == {}
        assert not any(tmp_path.iterdir())  # nothing written

    def test_outputs_dir_created_if_missing(self, tmp_path):
        deep_dir = tmp_path / "a" / "b" / "c"
        pl = Pipeline(runner_name="mock", outputs_dir=deep_dir)
        pl.run_site("bambulab")
        assert deep_dir.exists()


# ── Pipeline.run_all ──────────────────────────────────────────────────────────

class TestRunAll:
    def test_run_all_returns_7_results(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        results = pl.run_all(verbose=False)
        assert len(results) == 7

    def test_run_all_all_success(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        results = pl.run_all(verbose=False)
        failures = [r for r in results if not r.success]
        assert failures == [], f"Failed sites: {[r.site for r in failures]}"

    def test_run_all_subset(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        results = pl.run_all(["bambulab", "formlabs"], verbose=False)
        assert len(results) == 2
        assert {r.site for r in results} == {"bambulab", "formlabs"}

    def test_run_all_order_preserved(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        order = ["formlabs", "bambulab", "ultimaker"]
        results = pl.run_all(order, verbose=False)
        assert [r.site for r in results] == order

    def test_run_all_total_products(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        results = pl.run_all(verbose=False)
        total = sum(r.product_count for r in results)
        assert total >= 7  # at least 1 per site


# ── run_site convenience function ─────────────────────────────────────────────

class TestRunSiteFunction:
    def test_returns_pipeline_result(self, tmp_path):
        result = run_site("bambulab", outputs_dir=tmp_path, skip_output=True)
        assert isinstance(result, PipelineResult)

    def test_success(self, tmp_path):
        result = run_site("bambulab", outputs_dir=tmp_path, skip_output=True)
        assert result.success

    def test_products_mapped(self, tmp_path):
        result = run_site("bambulab", outputs_dir=tmp_path, skip_output=True)
        assert result.product_count >= 1

    def test_output_files_written(self, tmp_path):
        result = run_site("bambulab", outputs_dir=tmp_path)
        assert result.output_paths["json"].exists()

    def test_skip_output_honoured(self, tmp_path):
        result = run_site("bambulab", outputs_dir=tmp_path, skip_output=True)
        assert result.output_paths == {}

    def test_all_sites_via_convenience_fn(self, tmp_path):
        for site in ALL_SITES:
            result = run_site(site, outputs_dir=tmp_path, skip_output=True)
            assert result.success, f"run_site('{site}') failed: {result.errors}"


# ── Stage 1 error isolation ───────────────────────────────────────────────────

class TestStageErrorIsolation:
    def test_runner_error_captured_not_raised(self, tmp_path):
        pl = _mock_pipeline(tmp_path, runner_kwargs={"force_error": "deliberate"}, skip_output=True)
        result = pl.run_site("bambulab")
        assert result.success is False
        assert any("deliberate" in e for e in result.errors)

    def test_runner_error_still_produces_empty_products(self, tmp_path):
        pl = _mock_pipeline(tmp_path, runner_kwargs={"force_error": "boom"}, skip_output=True)
        result = pl.run_site("bambulab")
        assert result.product_count == 0

    def test_runner_error_still_writes_empty_output_files(self, tmp_path):
        """Even on runner failure, Stage 3 should attempt to write (empty) files."""
        pl = _mock_pipeline(tmp_path, runner_kwargs={"force_error": "boom"})
        result = pl.run_site("bambulab")
        # Output files are still created (with 0 records)
        assert result.output_paths.get("json", Path()).exists()

    def test_mapper_receives_stub_items_on_no_fixture(self, tmp_path):
        """When MockRunner returns a stub, the mapper should still produce 1 product."""
        import tempfile
        with tempfile.TemporaryDirectory() as empty_dir:
            pl = Pipeline(
                runner_name="mock",
                runner_kwargs={"fixtures_dir": empty_dir},
                outputs_dir=tmp_path,
                skip_output=True,
            )
            result = pl.run_site("bambulab")
        assert result.success
        assert result.product_count == 1  # the stub record


# ── Integration: confidence metadata flows through to JSON output ─────────────

class TestConfidenceInOutput:
    def test_high_confidence_fields_present(self, tmp_path):
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site("bambulab")
        records = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
        for rec in records:
            conf = rec["_field_confidence"]
            # product_name must exist in the fixture → should be HIGH
            assert conf.get("product_name") == FieldConfidence.HIGH.value, \
                f"Expected product_name=high, got {conf.get('product_name')} for {rec.get('product_name')}"

    def test_confidence_values_are_valid_strings(self, tmp_path):
        valid = {v.value for v in FieldConfidence}
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site("bambulab")
        records = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
        for rec in records:
            for field_name, conf_val in rec["_field_confidence"].items():
                assert conf_val in valid, \
                    f"Invalid confidence value '{conf_val}' for field '{field_name}'"


# ── Integration: mapped schema types match site registry ─────────────────────

class TestSiteSchemaMapping:
    @pytest.mark.parametrize("site,expected_cls_name", [
        ("active_floor", "ActiveFloorProduct"),
        ("smart_tech",   "SmartTechProduct"),
        ("play_lu",      "PlayLuProduct"),
        ("ultimaker",    "UltimakerProduct"),
        ("makerbot",     "MakerbotProduct"),
        ("bambulab",     "BambulabProduct"),
        ("formlabs",     "FormlabsProduct"),
    ])
    def test_schema_class_matches(self, site, expected_cls_name, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site(site)
        for p in result.products:
            assert type(p).__name__ == expected_cls_name, \
                f"site={site}: expected {expected_cls_name}, got {type(p).__name__}"

    def test_ultimaker_products_have_specs_list(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site("ultimaker")
        from schemas.sites import UltimakerProduct
        for p in result.products:
            assert isinstance(p, UltimakerProduct)
            assert isinstance(p.specs, list), f"specs should be a list, got {type(p.specs)}"

    def test_makerbot_products_have_price_current(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site("makerbot")
        # At least one makerbot product should have price_current set
        has_price_current = any(
            getattr(p, "price_current", None) is not None for p in result.products
        )
        assert has_price_current, "No makerbot products have price_current set"

    def test_play_lu_technical_specifications_is_list(self, tmp_path):
        pl = _mock_pipeline(tmp_path, skip_output=True)
        result = pl.run_site("play_lu")
        from schemas.sites import PlayLuProduct
        for p in result.products:
            assert isinstance(p, PlayLuProduct)
            # technical_specifications can be None or a list
            assert p.technical_specifications is None or \
                   isinstance(p.technical_specifications, list)


# ── Integration: output file content sanity ───────────────────────────────────

class TestOutputFileContent:
    def test_csv_row_count_matches_product_count(self, tmp_path):
        import csv
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site("bambulab")
        with result.output_paths["csv"].open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == result.product_count

    def test_html_contains_product_names(self, tmp_path):
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site("bambulab")
        html = result.output_paths["html"].read_text(encoding="utf-8")
        for p in result.products:
            if p.product_name:
                assert p.product_name in html, \
                    f"product_name '{p.product_name}' not found in HTML"

    def test_html_has_colour_coded_cells(self, tmp_path):
        pl = _mock_pipeline(tmp_path)
        result = pl.run_site("bambulab")
        html = result.output_paths["html"].read_text(encoding="utf-8")
        # At least the HIGH confidence colour must appear
        assert "#d4edda" in html  # green = HIGH

    def test_all_sites_produce_valid_json(self, tmp_path):
        pl = _mock_pipeline(tmp_path)
        for site in ALL_SITES:
            result = pl.run_site(site)
            text = result.output_paths["json"].read_text(encoding="utf-8")
            records = json.loads(text)
            assert isinstance(records, list), f"JSON is not a list for site={site}"


# ── SITE_OUTPUT_PREFIXES completeness ────────────────────────────────────────

class TestSiteRegistry:
    def test_all_7_prefixes_defined(self):
        assert len(SITE_OUTPUT_PREFIXES) == 7

    def test_prefix_keys_match_schema_registry(self):
        assert set(SITE_OUTPUT_PREFIXES.keys()) == set(SITE_SCHEMA_MAP.keys())

    def test_all_site_ids_constant_has_7_entries(self):
        assert len(ALL_SITE_IDS) == 7
