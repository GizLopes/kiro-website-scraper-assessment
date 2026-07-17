"""
Pipeline

Wires together the three processing stages for a single site:

    1. Runner   — send the extraction prompt to the LLM / mock agent
    2. Mapper   — map each raw dict to the site-specific Pydantic schema
    3. Output   — write JSON, CSV, and HTML report to the outputs/ directory

Usage (one site):
    from pipeline import run_site
    result = run_site("bambulab", runner_name="mock")

Usage (multiple sites via Pipeline class):
    from pipeline import Pipeline
    from runner import get_runner

    pl = Pipeline(runner_name="mock")
    for site_id in pl.SITE_IDS:
        result = pl.run_site(site_id)
        print(result)

The pipeline never raises — failures are captured in PipelineResult.errors so
callers can handle partial success (some sites scraped, others failed).
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# Make the scraper package root importable when the module is loaded directly
_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from mapper.schema_mapper import SchemaMapper
from output.output_builder import save_outputs
from prompts.prompt_builder import PromptBuilder
from runner import get_runner
from runner.base_runner import BrowserAgentRunner, RunnerResult
from runner.mock_runner import MockRunner
from schemas.core import ProductBase
from schemas.sites import SITE_SCHEMA_MAP

# ── Site registry ─────────────────────────────────────────────────────────────
# Maps site_id → output_prefix (drives filename generation)
SITE_OUTPUT_PREFIXES: Dict[str, str] = {
    "active_floor": "01_activefloor_products",
    "smart_tech":   "02_smart_tech_products",
    "play_lu":      "03_play_lu_products",
    "ultimaker":    "05_ultimaker_products",
    "makerbot":     "06_makerbot_products",
    "bambulab":     "07_bambulab_products",
    "formlabs":     "08_formlabs_products",
}

# Flat list of all registered site IDs (mirrors SITE_OUTPUT_PREFIXES.keys()).
# Exported here so both main.py and tests can import from a single location.
ALL_SITE_IDS: List[str] = list(SITE_OUTPUT_PREFIXES.keys())

DEFAULT_OUTPUTS_DIR = _PKG_ROOT / "outputs"
DESCRIPTORS_DIR     = _PKG_ROOT / "descriptors"
FIXTURES_DIR        = _PKG_ROOT / "runner" / "fixtures"


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class PipelineResult:
    """
    Holds the outcome of running the full pipeline for one site.

    Attributes:
        site         : Site identifier (e.g. "bambulab").
        products     : Mapped ProductBase instances (may be empty on failure).
        output_paths : Dict of {format: Path} written by OutputBuilder.
        runner_result: The raw RunnerResult from Stage 1.
        errors       : List of error messages (empty on full success).
        duration_s   : Total wall-clock seconds for all three stages.
    """
    site: str
    products: List[ProductBase] = field(default_factory=list)
    output_paths: Dict[str, Path] = field(default_factory=dict)
    runner_result: Optional[RunnerResult] = None
    errors: List[str] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def success(self) -> bool:
        """True only when no errors were recorded."""
        return len(self.errors) == 0

    @property
    def product_count(self) -> int:
        return len(self.products)

    def __repr__(self) -> str:
        status = "ok" if self.success else f"errors={self.errors}"
        return (
            f"PipelineResult(site={self.site!r}, "
            f"products={self.product_count}, "
            f"duration={self.duration_s:.1f}s, "
            f"{status})"
        )


# ── Pipeline class ────────────────────────────────────────────────────────────

class Pipeline:
    """
    Orchestrates the three-stage extraction pipeline for any number of sites.

    Args:
        runner_name   : "mock" | "browseruse" | "agentcore"  (default: "mock")
        runner_kwargs : Extra keyword arguments forwarded to the runner constructor.
        outputs_dir   : Directory where JSON / CSV / HTML files are written.
        descriptors_dir: Directory containing site YAML descriptors.
        skip_output   : If True, Stage 3 (writing files) is skipped.
                        Useful in tests that only need mapped products.
    """

    SITE_IDS: List[str] = list(SITE_OUTPUT_PREFIXES.keys())

    def __init__(
        self,
        *,
        runner_name: str = "mock",
        runner_kwargs: Optional[Dict[str, Any]] = None,
        outputs_dir: Path = DEFAULT_OUTPUTS_DIR,
        descriptors_dir: Path = DESCRIPTORS_DIR,
        skip_output: bool = False,
    ) -> None:
        self.runner_name    = runner_name.lower().strip()
        self.runner_kwargs  = runner_kwargs or {}
        self.outputs_dir    = Path(outputs_dir)
        self.descriptors_dir = Path(descriptors_dir)
        self.skip_output    = skip_output

        # Inject fixtures_dir for MockRunner so it can find the fixture files
        if self.runner_name == "mock" and "fixtures_dir" not in self.runner_kwargs:
            self.runner_kwargs["fixtures_dir"] = FIXTURES_DIR

        runner_cls    = get_runner(self.runner_name)
        self._runner: BrowserAgentRunner = runner_cls(**self.runner_kwargs)

    # ── Public API ────────────────────────────────────────────────────────

    def run_site(self, site_id: str) -> PipelineResult:
        """
        Run all three pipeline stages for a single site and return a PipelineResult.

        Errors at each stage are caught and recorded; the pipeline continues
        to subsequent stages where possible (e.g. empty product list still
        generates output files).
        """
        start    = time.monotonic()
        result   = PipelineResult(site=site_id)
        errors   = result.errors

        # ── Stage 1: Runner ───────────────────────────────────────────────
        try:
            prompt        = self._build_prompt(site_id)
            runner_result = self._runner.run(prompt, site_id)
            result.runner_result = runner_result

            if not runner_result.success:
                errors.append(f"[Runner] {runner_result.error}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[Runner] Unexpected exception: {exc}")
            runner_result = RunnerResult(raw_items=[], site=site_id)
            result.runner_result = runner_result

        # ── Stage 2: Mapper ───────────────────────────────────────────────
        try:
            schema_cls = self._schema_for(site_id)
            mapper     = SchemaMapper(schema_cls)
            products   = mapper.map_many(runner_result.raw_items)
            result.products = products
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[Mapper] {exc}")
            products = []
            result.products = products

        # ── Stage 3: Output ───────────────────────────────────────────────
        if not self.skip_output:
            try:
                prefix = SITE_OUTPUT_PREFIXES.get(site_id, site_id)
                paths  = save_outputs(
                    products,
                    site=site_id,
                    output_prefix=prefix,
                    outputs_dir=self.outputs_dir,
                )
                result.output_paths = paths
            except Exception as exc:  # noqa: BLE001
                errors.append(f"[Output] {exc}")

        result.duration_s = round(time.monotonic() - start, 2)
        return result

    def run_all(
        self,
        site_ids: Optional[Sequence[str]] = None,
        *,
        verbose: bool = True,
    ) -> List[PipelineResult]:
        """
        Run the pipeline for every site in site_ids (default: all 7).

        Args:
            site_ids : Subset of SITE_IDS to process. None = all.
            verbose  : Print a one-line summary per site while running.

        Returns:
            List of PipelineResult, one per site (same order as site_ids).
        """
        targets = list(site_ids) if site_ids is not None else self.SITE_IDS
        results: List[PipelineResult] = []

        for site_id in targets:
            pr = self.run_site(site_id)
            results.append(pr)
            if verbose:
                status = "OK " if pr.success else "ERR"
                print(
                    f"  [{status}] {site_id:<20} "
                    f"{pr.product_count:>3} products  "
                    f"{pr.duration_s:.1f}s"
                    + (f"  !! {'; '.join(pr.errors)}" if pr.errors else "")
                )

        return results

    def close(self) -> None:
        """Release runner resources (e.g. browser session)."""
        self._runner.close()

    # ── Context manager ───────────────────────────────────────────────────

    def __enter__(self) -> "Pipeline":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── Internal helpers ──────────────────────────────────────────────────

    def _build_prompt(self, site_id: str) -> str:
        builder = PromptBuilder(site_id, descriptors_dir=self.descriptors_dir)
        return builder.build()

    @staticmethod
    def _schema_for(site_id: str):
        if site_id not in SITE_SCHEMA_MAP:
            raise KeyError(
                f"No schema registered for site '{site_id}'. "
                f"Available: {sorted(SITE_SCHEMA_MAP.keys())}"
            )
        return SITE_SCHEMA_MAP[site_id]


# ── Convenience function ──────────────────────────────────────────────────────

def run_site(
    site_id: str,
    *,
    runner_name: str = "mock",
    runner_kwargs: Optional[Dict[str, Any]] = None,
    outputs_dir: Path = DEFAULT_OUTPUTS_DIR,
    descriptors_dir: Path = DESCRIPTORS_DIR,
    skip_output: bool = False,
) -> PipelineResult:
    """
    Run the full pipeline for a single site and return a PipelineResult.

    Example:
        result = run_site("bambulab", runner_name="mock")
        print(result.product_count, result.output_paths)
    """
    pl = Pipeline(
        runner_name=runner_name,
        runner_kwargs=runner_kwargs,
        outputs_dir=outputs_dir,
        descriptors_dir=descriptors_dir,
        skip_output=skip_output,
    )
    with pl:
        return pl.run_site(site_id)
