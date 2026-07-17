"""
Smoke-test for the Pipeline module

Run as a plain script — no pytest required:
    python scraper/tests/run_pipeline_check.py

Covers:
  - PipelineResult dataclass (success, product_count, repr, defaults)
  - Pipeline construction (default runner, site registry, context manager)
  - run_site() for all 7 sites via MockRunner (skip_output=True)
  - run_site() output files written to a temp directory
  - run_all() returning 7 results, all successful
  - run_site() convenience function
  - Stage 1 error isolation (force_error propagates, products empty)
  - Stage 3 error isolation (runner error still writes empty output files)
  - Stub fall-back when no fixture file exists
  - Confidence metadata present and valid in JSON output
  - SITE_OUTPUT_PREFIXES / ALL_SITE_IDS registry completeness
  - main.py CLI: _validate_sites(), _print_summary()
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Make the scraper package importable when running from repo root or tests/
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

errors: list[str] = []
passed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed
    if not condition:
        msg = f"FAIL: {label}" + (f" — {detail}" if detail else "")
        errors.append(msg)
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))
    else:
        print(f"  ok   {label}")
        passed += 1


def _mock_pl(tmp_path: Path, **kwargs) -> Pipeline:
    """Return a MockRunner pipeline writing to tmp_path."""
    return Pipeline(runner_name="mock", outputs_dir=tmp_path, **kwargs)


# ── PipelineResult dataclass ──────────────────────────────────────────────────
print("\n── PipelineResult ──────────────────────────────────────────────────")

r_ok = PipelineResult(site="bambulab", products=[], errors=[])
check("success True when no errors", r_ok.success is True)

r_fail = PipelineResult(site="bambulab", errors=["stage failed"])
check("success False when errors present", r_fail.success is False)

from schemas.sites import BambulabProduct
products_4 = [BambulabProduct(product_name=f"P{i}") for i in range(4)]
r_count = PipelineResult(site="bambulab", products=products_4)
check("product_count == 4", r_count.product_count == 4)

r_empty = PipelineResult(site="test")
check("product_count == 0 (empty)", r_empty.product_count == 0)

check("output_paths default empty dict", r_empty.output_paths == {})
check("duration_s stored", PipelineResult(site="t", duration_s=3.14).duration_s == 3.14)
check("repr ok contains site name", "bambulab" in repr(r_ok))
check("repr ok contains 'ok'", "ok" in repr(r_ok))
check("repr error contains 'errors='", "errors=" in repr(r_fail))

# ── Pipeline construction ─────────────────────────────────────────────────────
print("\n── Pipeline construction ────────────────────────────────────────────")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)

    pl_default = Pipeline(outputs_dir=tmp)
    check("default runner_name is 'mock'", pl_default.runner_name == "mock")
    pl_default.close()

    pl_mock = Pipeline(runner_name="mock", outputs_dir=tmp)
    check("runner_name 'mock' stored", pl_mock.runner_name == "mock")
    pl_mock.close()

    check("SITE_IDS matches SITE_OUTPUT_PREFIXES keys",
          set(Pipeline.SITE_IDS) == set(SITE_OUTPUT_PREFIXES.keys()))
    check("7 sites registered", len(Pipeline.SITE_IDS) == 7)

    try:
        Pipeline(runner_name="nonexistent_xyz", outputs_dir=tmp)
        check("unknown runner raises ValueError", False,
              "expected ValueError but nothing was raised")
    except ValueError:
        check("unknown runner raises ValueError", True)

    # Context manager closes the runner
    closed: list[bool] = []

    class TrackingMock(MockRunner):
        def close(self):
            closed.append(True)
            super().close()

    pl_ctx = Pipeline(outputs_dir=tmp)
    pl_ctx._runner = TrackingMock(fixtures_dir=FIXTURES_DIR)
    with pl_ctx:
        pass
    check("context manager calls runner.close()", closed == [True])

    # MockRunner gets fixtures_dir injected automatically
    pl_inj = Pipeline(runner_name="mock", outputs_dir=tmp)
    check("MockRunner fixtures_dir auto-injected",
          isinstance(pl_inj._runner, MockRunner)
          and pl_inj._runner._fixtures_dir == FIXTURES_DIR)
    pl_inj.close()

# ── run_site for all 7 sites (skip_output=True) ───────────────────────────────
print("\n── run_site — all 7 sites (skip_output=True) ───────────────────────")

ALL_SITES = list(SITE_OUTPUT_PREFIXES.keys())

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    for site in ALL_SITES:
        pl = _mock_pl(tmp, skip_output=True)
        result = pl.run_site(site)
        pl.close()

        check(f"{site}: returns PipelineResult", isinstance(result, PipelineResult))
        check(f"{site}: site id on result", result.site == site)
        check(f"{site}: success", result.success,
              f"errors={result.errors}")
        check(f"{site}: at least 1 product", result.product_count >= 1,
              f"got {result.product_count}")
        check(f"{site}: all products are ProductBase",
              all(isinstance(p, ProductBase) for p in result.products))
        check(f"{site}: correct schema class",
              all(isinstance(p, SITE_SCHEMA_MAP[site]) for p in result.products))
        check(f"{site}: duration >= 0", result.duration_s >= 0.0)
        check(f"{site}: runner_result attached",
              isinstance(result.runner_result, RunnerResult))

# ── run_site output files ─────────────────────────────────────────────────────
print("\n── run_site — output files ──────────────────────────────────────────")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    for site in ALL_SITES:
        pl = _mock_pl(tmp)
        result = pl.run_site(site)
        pl.close()

        prefix = SITE_OUTPUT_PREFIXES[site]
        check(f"{site}: JSON file exists",
              result.output_paths.get("json", Path()).exists())
        check(f"{site}: CSV file exists",
              result.output_paths.get("csv", Path()).exists())
        check(f"{site}: HTML file exists",
              result.output_paths.get("html", Path()).exists())
        check(f"{site}: JSON filename has correct prefix",
              result.output_paths["json"].name.startswith(prefix),
              f"got '{result.output_paths['json'].name}'")

        records = json.loads(
            result.output_paths["json"].read_text(encoding="utf-8")
        )
        check(f"{site}: JSON is a non-empty list",
              isinstance(records, list) and len(records) >= 1)
        check(f"{site}: JSON records have _field_confidence",
              all("_field_confidence" in rec for rec in records))

    # skip_output leaves no files
    pl2 = _mock_pl(tmp, skip_output=True)
    r2 = pl2.run_site("bambulab")
    pl2.close()
    check("skip_output: output_paths is empty dict", r2.output_paths == {})

    # outputs_dir created when missing
    deep = tmp / "a" / "b" / "c"
    pl3 = Pipeline(runner_name="mock", outputs_dir=deep)
    pl3.run_site("bambulab")
    pl3.close()
    check("outputs_dir created when missing", deep.exists())

# ── run_all ───────────────────────────────────────────────────────────────────
print("\n── run_all ──────────────────────────────────────────────────────────")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    pl = _mock_pl(tmp, skip_output=True)
    results = pl.run_all(verbose=False)
    pl.close()

    check("run_all returns 7 results", len(results) == 7)
    check("run_all all successful",
          all(r.success for r in results),
          str([r.site for r in results if not r.success]))
    check("run_all total products >= 7",
          sum(r.product_count for r in results) >= 7)

    # Subset
    pl2 = _mock_pl(tmp, skip_output=True)
    subset = pl2.run_all(["bambulab", "formlabs"], verbose=False)
    pl2.close()
    check("run_all subset returns 2 results", len(subset) == 2)
    check("run_all subset correct sites",
          {r.site for r in subset} == {"bambulab", "formlabs"})

    # Order preserved
    pl3 = _mock_pl(tmp, skip_output=True)
    order = ["formlabs", "bambulab", "ultimaker"]
    ordered = pl3.run_all(order, verbose=False)
    pl3.close()
    check("run_all order preserved",
          [r.site for r in ordered] == order)

# ── run_site convenience function ─────────────────────────────────────────────
print("\n── run_site() convenience function ─────────────────────────────────")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)

    fn_result = run_site("bambulab", outputs_dir=tmp, skip_output=True)
    check("run_site() returns PipelineResult", isinstance(fn_result, PipelineResult))
    check("run_site() success", fn_result.success)
    check("run_site() products mapped", fn_result.product_count >= 1)
    check("run_site() skip_output honoured", fn_result.output_paths == {})

    fn_result2 = run_site("bambulab", outputs_dir=tmp)
    check("run_site() JSON file written", fn_result2.output_paths["json"].exists())

    for site in ALL_SITES:
        r = run_site(site, outputs_dir=tmp, skip_output=True)
        check(f"run_site('{site}') success", r.success,
              f"errors={r.errors}")

# ── Unknown site captured as error, not raised ────────────────────────────────
print("\n── Error isolation ──────────────────────────────────────────────────")

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)

    # Unknown site → schema lookup fails, error captured in result
    pl = _mock_pl(tmp, skip_output=True)
    r_bad = pl.run_site("nonexistent_site_xyz")
    pl.close()
    check("unknown site: success is False", r_bad.success is False)
    check("unknown site: error message mentions site or schema",
          any("nonexistent_site_xyz" in e or "schema" in e.lower()
              for e in r_bad.errors))

    # force_error propagates as runner error
    pl_err = Pipeline(
        runner_name="mock",
        runner_kwargs={"force_error": "deliberate smoke error"},
        outputs_dir=tmp,
        skip_output=True,
    )
    r_err = pl_err.run_site("bambulab")
    pl_err.close()
    check("force_error: success is False", r_err.success is False)
    check("force_error: error message present",
          any("deliberate smoke error" in e for e in r_err.errors))
    check("force_error: product_count is 0", r_err.product_count == 0)

    # Runner error still attempts Stage 3 (output files, even if empty)
    pl_out = Pipeline(
        runner_name="mock",
        runner_kwargs={"force_error": "boom"},
        outputs_dir=tmp,
    )
    r_out = pl_out.run_site("bambulab")
    pl_out.close()
    check("runner error: JSON file still created",
          r_out.output_paths.get("json", Path()).exists())

    # Missing fixture falls back to stub → 1 product, success
    with tempfile.TemporaryDirectory() as empty_dir:
        pl_stub = Pipeline(
            runner_name="mock",
            runner_kwargs={"fixtures_dir": empty_dir},
            outputs_dir=tmp,
            skip_output=True,
        )
        r_stub = pl_stub.run_site("bambulab")
        pl_stub.close()
    check("stub fall-back: success is True", r_stub.success)
    check("stub fall-back: 1 product returned", r_stub.product_count == 1)

# ── Confidence metadata in JSON output ────────────────────────────────────────
print("\n── Confidence metadata ──────────────────────────────────────────────")

valid_conf = {v.value for v in FieldConfidence}

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    pl = _mock_pl(tmp)
    result = pl.run_site("bambulab")
    pl.close()

    records = json.loads(result.output_paths["json"].read_text(encoding="utf-8"))
    check("bambulab: all records have _field_confidence",
          all("_field_confidence" in rec for rec in records))
    check("bambulab: product_name confidence is 'high'",
          all(rec["_field_confidence"].get("product_name") == FieldConfidence.HIGH.value
              for rec in records))
    all_conf_valid = all(
        v in valid_conf
        for rec in records
        for v in rec["_field_confidence"].values()
    )
    check("bambulab: all confidence values are valid strings", all_conf_valid)

# ── Registry completeness ─────────────────────────────────────────────────────
print("\n── Registry / constants ─────────────────────────────────────────────")

check("SITE_OUTPUT_PREFIXES has 7 entries", len(SITE_OUTPUT_PREFIXES) == 7)
check("ALL_SITE_IDS has 7 entries", len(ALL_SITE_IDS) == 7)
check("SITE_OUTPUT_PREFIXES keys == SITE_SCHEMA_MAP keys",
      set(SITE_OUTPUT_PREFIXES.keys()) == set(SITE_SCHEMA_MAP.keys()))
check("ALL_SITE_IDS matches SITE_OUTPUT_PREFIXES keys",
      set(ALL_SITE_IDS) == set(SITE_OUTPUT_PREFIXES.keys()))
check("DESCRIPTORS_DIR exists", DESCRIPTORS_DIR.exists())
check("FIXTURES_DIR exists", FIXTURES_DIR.exists())

# ── main.py helpers (_validate_sites, _print_summary) ────────────────────────
print("\n── main.py helpers ──────────────────────────────────────────────────")

from main import _validate_sites, _print_summary, ALL_SITE_IDS as MAIN_ALL_SITES

check("_validate_sites(None) returns all 7 sites",
      len(_validate_sites(None)) == 7)
check("_validate_sites(['bambulab']) returns ['bambulab']",
      _validate_sites(["bambulab"]) == ["bambulab"])
check("_validate_sites(['bambulab', 'formlabs']) returns both",
      set(_validate_sites(["bambulab", "formlabs"])) == {"bambulab", "formlabs"})
check("_validate_sites(['bad_site']) falls back to all sites",
      len(_validate_sites(["bad_site"])) == 7)
check("_validate_sites(['bambulab', 'bad']) keeps only valid",
      _validate_sites(["bambulab", "bad_site_xyz"]) == ["bambulab"])

# _print_summary runs without exception
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    pl = _mock_pl(tmp)
    results = pl.run_all(verbose=False)
    pl.close()
    total_s = sum(r.duration_s for r in results)
    try:
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _print_summary(results, total_s)
        summary = buf.getvalue()
        check("_print_summary: prints site count", "7" in summary)
        check("_print_summary: runs without exception", True)
    except Exception as exc:  # noqa: BLE001
        check("_print_summary: runs without exception", False, str(exc))

check("main.py ALL_SITE_IDS has 7 entries", len(MAIN_ALL_SITES) == 7)
check("main.py ALL_SITE_IDS matches pipeline ALL_SITE_IDS",
      set(MAIN_ALL_SITES) == set(ALL_SITE_IDS))

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    for e in errors:
        print(e)
    print(f"\n{len(errors)} check(s) FAILED  ({passed} passed)")
    sys.exit(1)
else:
    print(f"ALL {passed} PIPELINE CHECKS PASSED")
