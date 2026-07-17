"""Quick smoke-test for the Runner module (run as a plain script, no pytest required)."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner.base_runner import BrowserAgentRunner, RunnerResult, _attempt_json_repair
from runner.mock_runner import MockRunner, _minimal_stub
from runner import get_runner
from runner.browseruse_runner import BrowserUseRunner
from runner.agentcore_runner import AgentCoreRunner

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

errors: list[str] = []
passed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed
    if not condition:
        msg = f"FAIL: {label}" + (f" — {detail}" if detail else "")
        errors.append(msg)
    else:
        print(f"  ok  {label}")
        passed += 1


# ── RunnerResult ──────────────────────────────────────────────────────────────
r = RunnerResult(raw_items=[{"a": 1}], site="test", duration_s=1.5)
check("RunnerResult: success True when no error", r.success is True)
check("RunnerResult: site stored", r.site == "test")
check("RunnerResult: duration stored", abs(r.duration_s - 1.5) < 0.01)

r_fail = RunnerResult(raw_items=[], site="x", error="boom")
check("RunnerResult: success False when error set", r_fail.success is False)
check("RunnerResult: repr ok",  "ok" in repr(r))
check("RunnerResult: repr error", "error=" in repr(r_fail))

# ── _parse_json_response ──────────────────────────────────────────────────────
parse = BrowserAgentRunner._parse_json_response

check("parse: plain array",
      parse('[{"name": "A"}]')[0]["name"] == "A")
check("parse: markdown fences stripped",
      parse('```json\n[{"name": "B"}]\n```')[0]["name"] == "B")
check("parse: prose before array",
      parse('Here:\n[{"name": "C"}]')[0]["name"] == "C")
check("parse: single object wrapped",
      parse('{"name": "D"}')[0]["name"] == "D")
check("parse: empty string → []",
      parse("") == [])
check("parse: garbage → []",
      parse("not json") == [])
check("parse: non-dict items filtered",
      len(parse('[{"name": "ok"}, "str", 42]')) == 1)

# ── _attempt_json_repair ──────────────────────────────────────────────────────
repaired = _attempt_json_repair('[{"name": "X"')
check("repair: closes unclosed brace",
      json.loads(repaired)[0]["name"] == "X")
check("repair: valid JSON unchanged",
      _attempt_json_repair('[{"a": 1}]') == '[{"a": 1}]')

# ── MockRunner: basic ─────────────────────────────────────────────────────────
runner = MockRunner(fixtures_dir=FIXTURES_DIR)
result = runner.run("any prompt", "bambulab")
check("MockRunner: returns RunnerResult", isinstance(result, RunnerResult))
check("MockRunner: success True", result.success is True)
check("MockRunner: site on result", result.site == "bambulab")
check("MockRunner: duration >= 0", result.duration_s >= 0)
check("MockRunner: items are dicts", all(isinstance(i, dict) for i in result.raw_items))

# force_error
r_err = MockRunner(force_error="test error").run("p", "bambulab")
check("MockRunner force_error: success False", r_err.success is False)
check("MockRunner force_error: error message set", "test error" in r_err.error)
check("MockRunner force_error: empty raw_items", r_err.raw_items == [])

# extra_items
extra = [{"product_name": "EXTRA_ITEM", "category": "Test"}]
r_extra = MockRunner(fixtures_dir=FIXTURES_DIR, extra_items=extra).run("p", "bambulab")
names = [i.get("product_name") for i in r_extra.raw_items]
check("MockRunner extra_items: EXTRA_ITEM present", "EXTRA_ITEM" in names)

# context manager
with MockRunner(fixtures_dir=FIXTURES_DIR) as m:
    r_ctx = m.run("p", "formlabs")
check("MockRunner: context manager works", r_ctx.success is True)

# ── MockRunner: all 7 fixture files ──────────────────────────────────────────
for site in ALL_SITES:
    r_site = MockRunner(fixtures_dir=FIXTURES_DIR).run("p", site)
    check(f"MockRunner fixture '{site}': at least 1 item",
          len(r_site.raw_items) >= 1)
    check(f"MockRunner fixture '{site}': all items are dicts",
          all(isinstance(i, dict) for i in r_site.raw_items))
    check(f"MockRunner fixture '{site}': items have product_name",
          all("product_name" in i for i in r_site.raw_items))

# ── MockRunner: missing fixture falls back to stub ────────────────────────────
with tempfile.TemporaryDirectory() as tmpdir:
    r_stub = MockRunner(fixtures_dir=tmpdir).run("p", "no_such_site")
    check("MockRunner: missing fixture → stub returned", len(r_stub.raw_items) == 1)
    check("MockRunner: stub has _stub flag", r_stub.raw_items[0].get("_stub") is True)

# ── _minimal_stub ─────────────────────────────────────────────────────────────
stub = _minimal_stub("test_site")
check("_minimal_stub: product_name present", "product_name" in stub)
check("_minimal_stub: category present", "category" in stub)
check("_minimal_stub: specifications present", "specifications" in stub)
check("_minimal_stub: _stub flag True", stub.get("_stub") is True)

# ── add_fixture round-trip ────────────────────────────────────────────────────
with tempfile.TemporaryDirectory() as tmpdir:
    m2 = MockRunner(fixtures_dir=tmpdir)
    m2.add_fixture("written_site", [{"product_name": "Written", "price": "$1"}])
    r2 = m2.run("p", "written_site")
    check("add_fixture: written fixture loaded", r2.raw_items[0]["product_name"] == "Written")

# ── get_runner factory ────────────────────────────────────────────────────────
check("get_runner('mock') → MockRunner",         get_runner("mock") is MockRunner)
check("get_runner('MOCK') case-insensitive",      get_runner("MOCK") is MockRunner)
check("get_runner('browseruse') → BrowserUseRunner", get_runner("browseruse") is BrowserUseRunner)
check("get_runner('agentcore') → AgentCoreRunner",   get_runner("agentcore") is AgentCoreRunner)

try:
    get_runner("unknown_xyz")
    errors.append("FAIL: get_runner unknown should raise ValueError")
except ValueError:
    check("get_runner: unknown name raises ValueError", True)

for name in ("mock", "browseruse", "agentcore"):
    cls = get_runner(name)
    check(f"get_runner('{name}') is BrowserAgentRunner subclass",
          issubclass(cls, BrowserAgentRunner))

# ── AgentCoreRunner (structural, no AWS calls) ────────────────────────────────
ac = AgentCoreRunner()
check("AgentCoreRunner: is BrowserAgentRunner subclass",
      issubclass(AgentCoreRunner, BrowserAgentRunner))
check("AgentCoreRunner: default model contains 'claude'",
      "claude" in ac._model_id.lower())
check("AgentCoreRunner: custom model accepted",
      AgentCoreRunner(model_id="my-model")._model_id == "my-model")
check("AgentCoreRunner: custom region accepted",
      AgentCoreRunner(region="eu-west-1")._region == "eu-west-1")
check("AgentCoreRunner: max_tokens accepted",
      AgentCoreRunner(max_tokens=4096)._max_tokens == 4096)
check("AgentCoreRunner: repr contains model",
      "my-model" in repr(AgentCoreRunner(model_id="my-model")))

# close() resets the client reference
ac2 = AgentCoreRunner()
ac2._client = object()
ac2.close()
check("AgentCoreRunner: close() resets _client to None", ac2._client is None)

# run() must not raise — it returns a RunnerResult even on failure
r_ac = AgentCoreRunner().run("test", "bambulab")
check("AgentCoreRunner: run() returns RunnerResult (no raise)", isinstance(r_ac, RunnerResult))
check("AgentCoreRunner: run() site set", r_ac.site == "bambulab")

# ── BrowserUseRunner (structural, no browser calls) ──────────────────────────
check("BrowserUseRunner: is BrowserAgentRunner subclass",
      issubclass(BrowserUseRunner, BrowserAgentRunner))
bu = BrowserUseRunner()
check("BrowserUseRunner: default provider openai", bu._provider == "openai")
check("BrowserUseRunner: default model gpt-4o",    bu._model == "gpt-4o")
check("BrowserUseRunner: custom headless False accepted",
      BrowserUseRunner(headless=False)._headless is False)
check("BrowserUseRunner: custom timeout accepted",
      BrowserUseRunner(timeout=300)._timeout == 300)
check("BrowserUseRunner: custom max_actions accepted",
      BrowserUseRunner(max_actions=50)._max_actions == 50)

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print(f"ALL {passed} RUNNER CHECKS PASSED")
