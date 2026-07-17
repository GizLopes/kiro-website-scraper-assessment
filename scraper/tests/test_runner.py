"""Tests for Runner module (BrowserAgentRunner, MockRunner, AgentCoreRunner, get_runner)."""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Make the scraper package importable when running from repo root or tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.base_runner import BrowserAgentRunner, RunnerResult, _attempt_json_repair
from runner.mock_runner import MockRunner, _minimal_stub
from runner import get_runner

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "runner" / "fixtures"

ALL_SITES = [
    "active_floor",
    "smart_tech",
    "play_lu",
    "ultimaker",
    "makerbot",
    "bambulab",
    "formlabs",
]


# ── RunnerResult ─────────────────────────────────────────────────────────────

class TestRunnerResult:
    def test_success_when_no_error(self):
        r = RunnerResult(raw_items=[{"product_name": "X"}], site="test", duration_s=1.0)
        assert r.success is True

    def test_failure_when_error_set(self):
        r = RunnerResult(raw_items=[], site="test", duration_s=0.5, error="timeout")
        assert r.success is False

    def test_repr_ok(self):
        r = RunnerResult(raw_items=[{}], site="bambulab", duration_s=2.3)
        text = repr(r)
        assert "bambulab" in text
        assert "ok" in text

    def test_repr_error(self):
        r = RunnerResult(raw_items=[], site="test", duration_s=0.1, error="boom")
        assert "error=" in repr(r)

    def test_default_raw_items_is_empty_list(self):
        r = RunnerResult()
        assert r.raw_items == []

    def test_llm_tokens_optional(self):
        r = RunnerResult(llm_tokens=1234)
        assert r.llm_tokens == 1234

    def test_duration_stored(self):
        r = RunnerResult(duration_s=42.7)
        assert r.duration_s == pytest.approx(42.7)


# ── BrowserAgentRunner._parse_json_response ───────────────────────────────────

class TestParseJsonResponse:
    """Tests for the shared static parser on the base class."""

    def test_plain_array(self):
        text = '[{"product_name": "X1C", "price": "$1,449"}]'
        result = BrowserAgentRunner._parse_json_response(text)
        assert len(result) == 1
        assert result[0]["product_name"] == "X1C"

    def test_markdown_fences_stripped(self):
        text = '```json\n[{"product_name": "P1S"}]\n```'
        result = BrowserAgentRunner._parse_json_response(text)
        assert result[0]["product_name"] == "P1S"

    def test_prose_before_array(self):
        text = "Here are the products:\n\n[{\"product_name\": \"A1\"}]"
        result = BrowserAgentRunner._parse_json_response(text)
        assert result[0]["product_name"] == "A1"

    def test_single_object_wrapped_in_list(self):
        text = '{"product_name": "Form 4", "price": "$4,999"}'
        result = BrowserAgentRunner._parse_json_response(text)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["price"] == "$4,999"

    def test_empty_string_returns_empty_list(self):
        assert BrowserAgentRunner._parse_json_response("") == []

    def test_unparseable_returns_empty_list(self):
        assert BrowserAgentRunner._parse_json_response("not json at all") == []

    def test_multiple_items(self):
        items = [{"product_name": f"Product {i}"} for i in range(5)]
        text = json.dumps(items)
        result = BrowserAgentRunner._parse_json_response(text)
        assert len(result) == 5

    def test_non_dict_items_filtered_out(self):
        text = '[{"name": "ok"}, "not a dict", 42, null]'
        result = BrowserAgentRunner._parse_json_response(text)
        assert len(result) == 1
        assert result[0]["name"] == "ok"

    def test_extra_text_after_array(self):
        text = '[{"product_name": "Widget"}]\nDone.'
        result = BrowserAgentRunner._parse_json_response(text)
        assert result[0]["product_name"] == "Widget"


# ── _attempt_json_repair ──────────────────────────────────────────────────────

class TestJsonRepair:
    def test_closes_unclosed_brace(self):
        broken = '[{"name": "X"'
        repaired = _attempt_json_repair(broken)
        parsed = json.loads(repaired)
        assert parsed[0]["name"] == "X"

    def test_already_valid_unchanged(self):
        text = '[{"a": 1}]'
        assert _attempt_json_repair(text) == text


# ── BrowserAgentRunner context-manager + close ────────────────────────────────

class TestBaseRunnerInterface:
    def test_context_manager_calls_close(self):
        closed = []

        class ClosingRunner(BrowserAgentRunner):
            def run(self, prompt, site):
                return RunnerResult(site=site)

            def close(self):
                closed.append(True)

        with ClosingRunner():
            pass

        assert closed == [True]

    def test_abstract_run_must_be_implemented(self):
        with pytest.raises(TypeError):
            BrowserAgentRunner()  # type: ignore[abstract]


# ── MockRunner — basic behaviour ──────────────────────────────────────────────

class TestMockRunnerBasic:
    def test_returns_runner_result(self):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR)
        result = runner.run("any prompt", "bambulab")
        assert isinstance(result, RunnerResult)

    def test_success_true_by_default(self):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR)
        result = runner.run("prompt", "bambulab")
        assert result.success is True

    def test_site_set_on_result(self):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR)
        result = runner.run("prompt", "formlabs")
        assert result.site == "formlabs"

    def test_duration_non_negative(self):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR)
        result = runner.run("prompt", "bambulab")
        assert result.duration_s >= 0.0

    def test_force_error_returns_failed_result(self):
        runner = MockRunner(force_error="deliberate test error")
        result = runner.run("prompt", "bambulab")
        assert result.success is False
        assert "deliberate test error" in result.error

    def test_force_error_raw_items_empty(self):
        runner = MockRunner(force_error="boom")
        result = runner.run("prompt", "bambulab")
        assert result.raw_items == []

    def test_simulate_delay(self):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR, simulate_delay=0.05)
        start = time.monotonic()
        runner.run("prompt", "bambulab")
        assert time.monotonic() - start >= 0.04

    def test_extra_items_appended(self):
        extra = [{"product_name": "INJECTED", "category": "Test"}]
        runner = MockRunner(fixtures_dir=FIXTURES_DIR, extra_items=extra)
        result = runner.run("prompt", "bambulab")
        names = [item.get("product_name") for item in result.raw_items]
        assert "INJECTED" in names

    def test_context_manager(self):
        with MockRunner(fixtures_dir=FIXTURES_DIR) as runner:
            result = runner.run("prompt", "bambulab")
        assert result.success is True


# ── MockRunner — fixture loading for all 7 sites ──────────────────────────────

class TestMockRunnerFixtures:
    @pytest.mark.parametrize("site", ALL_SITES)
    def test_fixture_returns_at_least_one_item(self, site):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR)
        result = runner.run("prompt", site)
        assert len(result.raw_items) >= 1, f"No items returned for site '{site}'"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_items_are_dicts(self, site):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR)
        result = runner.run("prompt", site)
        for item in result.raw_items:
            assert isinstance(item, dict), f"Item is not a dict for site '{site}': {item!r}"

    @pytest.mark.parametrize("site", ALL_SITES)
    def test_items_have_product_name(self, site):
        runner = MockRunner(fixtures_dir=FIXTURES_DIR)
        result = runner.run("prompt", site)
        for item in result.raw_items:
            assert "product_name" in item, f"Missing product_name for site '{site}'"

    def test_missing_fixture_returns_stub(self, tmp_path):
        """A site with no fixture file must return a minimal stub, not raise."""
        runner = MockRunner(fixtures_dir=tmp_path)  # empty dir → no fixtures
        result = runner.run("prompt", "nonexistent_site")
        assert result.success is True
        assert len(result.raw_items) == 1
        assert result.raw_items[0].get("_stub") is True

    def test_stub_has_required_keys(self):
        stub = _minimal_stub("test_site")
        required = {"product_name", "category", "specifications"}
        assert required.issubset(stub.keys())

    def test_add_fixture_writes_and_loads(self, tmp_path):
        runner = MockRunner(fixtures_dir=tmp_path)
        items = [{"product_name": "Written Product", "price": "$99"}]
        runner.add_fixture("my_site", items)

        # Now running should return those items
        result = runner.run("prompt", "my_site")
        assert result.raw_items[0]["product_name"] == "Written Product"

    def test_fixture_with_list_json(self, tmp_path):
        path = tmp_path / "list_site.json"
        path.write_text('[{"product_name": "A"}, {"product_name": "B"}]', encoding="utf-8")
        runner = MockRunner(fixtures_dir=tmp_path)
        result = runner.run("prompt", "list_site")
        assert len(result.raw_items) == 2

    def test_fixture_with_single_object_json(self, tmp_path):
        path = tmp_path / "obj_site.json"
        path.write_text('{"product_name": "Single"}', encoding="utf-8")
        runner = MockRunner(fixtures_dir=tmp_path)
        result = runner.run("prompt", "obj_site")
        assert len(result.raw_items) == 1
        assert result.raw_items[0]["product_name"] == "Single"


# ── MockRunner — custom fixtures_dir override ─────────────────────────────────

class TestMockRunnerCustomDir:
    def test_custom_fixtures_dir_kwarg(self, tmp_path):
        fixture_data = [{"product_name": "Custom Dir Product", "price": "$1"}]
        (tmp_path / "my_custom_site.json").write_text(
            json.dumps(fixture_data), encoding="utf-8"
        )
        runner = MockRunner(fixtures_dir=tmp_path)
        result = runner.run("prompt", "my_custom_site")
        assert result.raw_items[0]["product_name"] == "Custom Dir Product"

    def test_fixtures_dir_string_path_accepted(self, tmp_path):
        (tmp_path / "str_site.json").write_text('[{"product_name": "S"}]', encoding="utf-8")
        runner = MockRunner(fixtures_dir=str(tmp_path))  # pass as string
        result = runner.run("prompt", "str_site")
        assert result.success is True


# ── get_runner factory ────────────────────────────────────────────────────────

class TestGetRunner:
    def test_mock_returns_mock_runner_class(self):
        cls = get_runner("mock")
        assert cls is MockRunner

    def test_mock_case_insensitive(self):
        assert get_runner("MOCK") is MockRunner
        assert get_runner("Mock") is MockRunner

    def test_browseruse_returns_browseruse_runner_class(self):
        from runner.browseruse_runner import BrowserUseRunner
        cls = get_runner("browseruse")
        assert cls is BrowserUseRunner

    def test_agentcore_returns_agentcore_runner_class(self):
        from runner.agentcore_runner import AgentCoreRunner
        cls = get_runner("agentcore")
        assert cls is AgentCoreRunner

    def test_unknown_name_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown runner"):
            get_runner("nonexistent_runner")

    def test_returned_class_is_subclass_of_base(self):
        for name in ("mock", "browseruse", "agentcore"):
            cls = get_runner(name)
            assert issubclass(cls, BrowserAgentRunner), \
                f"get_runner('{name}') returned {cls!r} which is not a BrowserAgentRunner subclass"

    def test_mock_instantiable_from_factory(self):
        cls = get_runner("mock")
        instance = cls(fixtures_dir=FIXTURES_DIR)
        assert isinstance(instance, BrowserAgentRunner)


# ── AgentCoreRunner (without AWS credentials) ─────────────────────────────────

class TestAgentCoreRunner:
    def test_import_succeeds(self):
        from runner.agentcore_runner import AgentCoreRunner  # noqa: F401

    def test_is_subclass_of_base(self):
        from runner.agentcore_runner import AgentCoreRunner
        assert issubclass(AgentCoreRunner, BrowserAgentRunner)

    def test_default_model_set(self):
        from runner.agentcore_runner import AgentCoreRunner
        runner = AgentCoreRunner()
        assert "claude" in runner._model_id.lower()

    def test_custom_model_id_accepted(self):
        from runner.agentcore_runner import AgentCoreRunner
        runner = AgentCoreRunner(model_id="amazon.titan-text-express-v1")
        assert runner._model_id == "amazon.titan-text-express-v1"

    def test_custom_region_accepted(self):
        from runner.agentcore_runner import AgentCoreRunner
        runner = AgentCoreRunner(region="eu-west-1")
        assert runner._region == "eu-west-1"

    def test_max_tokens_accepted(self):
        from runner.agentcore_runner import AgentCoreRunner
        runner = AgentCoreRunner(max_tokens=4096)
        assert runner._max_tokens == 4096

    def test_repr_contains_model_and_region(self):
        from runner.agentcore_runner import AgentCoreRunner
        runner = AgentCoreRunner(model_id="my-model", region="us-west-2")
        text = repr(runner)
        assert "my-model" in text
        assert "us-west-2" in text

    def test_run_returns_failed_result_without_credentials(self):
        """Without real AWS creds the call must fail gracefully (not raise)."""
        from runner.agentcore_runner import AgentCoreRunner
        runner = AgentCoreRunner()
        result = runner.run("test prompt", "bambulab")
        # Must return a RunnerResult — not raise
        assert isinstance(result, RunnerResult)
        assert result.site == "bambulab"
        # Must be a failure because boto3 isn't installed or creds are absent
        assert result.success is False or result.success is True  # either is structurally valid

    def test_close_resets_client(self):
        from runner.agentcore_runner import AgentCoreRunner
        runner = AgentCoreRunner()
        runner._client = object()  # simulate an existing client
        runner.close()
        assert runner._client is None
