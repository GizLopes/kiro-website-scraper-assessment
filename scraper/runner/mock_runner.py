"""
Mock Runner

Returns pre-loaded fixture data without opening a real browser.
Used for:
  - Unit / integration tests of the full pipeline
  - Smoke-testing all 7 site descriptors quickly
  - CI pipelines where a real browser is unavailable

Fixture files live in runner/fixtures/<site>.json
If no fixture file exists for the requested site, returns a single
minimal stub record so the pipeline can continue without error.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_runner import BrowserAgentRunner, RunnerResult

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


class MockRunner(BrowserAgentRunner):
    """
    Concrete runner that serves fixture JSON instead of a live LLM call.

    Configuration kwargs:
        fixtures_dir (Path | str): Override the default fixtures directory.
        extra_items  (list[dict]): Inject additional items on top of the fixture.
        simulate_delay (float)   : Fake delay in seconds (default 0).
        force_error (str | None) : If set, always return a failed RunnerResult
                                   with this string as the error message.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._fixtures_dir = Path(kwargs.get("fixtures_dir", FIXTURES_DIR))
        self._extra_items: List[Dict[str, Any]] = kwargs.get("extra_items", [])
        self._simulate_delay: float = float(kwargs.get("simulate_delay", 0))
        self._force_error: Optional[str] = kwargs.get("force_error", None)

    # ── BrowserAgentRunner contract ───────────────────────────────────────

    def run(self, prompt: str, site: str) -> RunnerResult:
        start = time.monotonic()

        if self._simulate_delay:
            time.sleep(self._simulate_delay)

        if self._force_error:
            return RunnerResult(
                raw_items=[],
                site=site,
                duration_s=self._elapsed(start),
                error=self._force_error,
            )

        items = self._load_fixture(site) + list(self._extra_items)

        return RunnerResult(
            raw_items=items,
            site=site,
            duration_s=self._elapsed(start),
        )

    # ── Fixture management ────────────────────────────────────────────────

    def _load_fixture(self, site: str) -> List[Dict[str, Any]]:
        path = self._fixtures_dir / f"{site}.json"
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        # No fixture → return a minimal stub so the pipeline doesn't break
        return [_minimal_stub(site)]

    def add_fixture(self, site: str, items: List[Dict[str, Any]]) -> None:
        """Write a fixture file for the given site (useful in tests)."""
        self._fixtures_dir.mkdir(parents=True, exist_ok=True)
        path = self._fixtures_dir / f"{site}.json"
        with path.open("w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)


def _minimal_stub(site: str) -> Dict[str, Any]:
    """Return a minimal stub record so the pipeline can exercise all stages."""
    return {
        "product_name": f"[STUB] {site} product",
        "category": "Unknown",
        "subcategory": None,
        "price": None,
        "product_url": None,
        "source_url": None,
        "specifications": {},
        "_stub": True,
    }
