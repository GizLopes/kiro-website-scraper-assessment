"""
main.py

Unified entry point for the Client scraper pipeline.

Runs the three-stage extraction pipeline (Runner → Mapper → Output) for one
or more target sites and writes JSON / CSV / HTML reports to outputs/.

Usage examples
--------------
# Run all 7 sites with the MockRunner (default — no browser needed):
    python main.py

# Run a single site:
    python main.py --sites bambulab

# Run multiple specific sites:
    python main.py --sites bambulab formlabs ultimaker

# Use the BrowserUse runner (requires OPENAI_API_KEY or ANTHROPIC_API_KEY):
    python main.py --runner browseruse

# Use the AgentCore / Bedrock runner (requires AWS credentials):
# MELHOR COMANDO EVEEEER
    python main.py --runner agentcore

# Use a custom outputs directory:
    python main.py --output-dir /tmp/scraper_outputs

# Dry-run: skip writing output files (useful for debugging):
    python main.py --dry-run

# Verbose / quiet:
    python main.py --verbose   # default
    python main.py --quiet

Available site IDs
------------------
    active_floor  smart_tech  play_lu  ultimaker  makerbot  bambulab  formlabs
"""
from __future__ import annotations
import os
import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

# Make the scraper package importable when run as __main__
_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from pipeline.pipeline import (
    DEFAULT_OUTPUTS_DIR,
    SITE_OUTPUT_PREFIXES,
    Pipeline,
    PipelineResult,
)

ALL_SITE_IDS = list(SITE_OUTPUT_PREFIXES.keys())


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Scraper Agent — LLM-powered product data extraction pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--sites",
        nargs="+",
        metavar="SITE_ID",
        default=None,
        help=(
            "One or more site IDs to process. "
            f"Choices: {', '.join(ALL_SITE_IDS)}. "
            "Defaults to ALL sites."
        ),
    )
    parser.add_argument(
        "--runner",
        default="mock",
        choices=["mock", "browseruse", "agentcore"],
        help="Runner backend to use (default: mock).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUTS_DIR,
        metavar="PATH",
        help=f"Directory for output files (default: {DEFAULT_OUTPUTS_DIR}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip writing output files (Stage 3). Useful for debugging.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress per-site progress lines.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print per-site progress lines (default behaviour).",
    )

    # Runner-specific overrides (forwarded as runner_kwargs)
    parser.add_argument("--llm-provider", default=None,
                        help="LLM provider for browseruse runner: 'openai' | 'anthropic'.")
    parser.add_argument("--model", default=None,
                        help="LLM model name (browseruse / agentcore runners).")
    parser.add_argument("--headless", action="store_true", default=None,
                        help="Run browser headless (browseruse runner).")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Run browser with visible UI (browseruse runner).")

    return parser


def _runner_kwargs(args: argparse.Namespace) -> dict:
    """Build the runner_kwargs dict from CLI arguments."""
    kwargs: dict = {}
    if args.llm_provider is not None:
        kwargs["llm_provider"] = args.llm_provider
    if args.model is not None:
        if args.runner == "agentcore":
            kwargs["model_id"] = args.model
        else:
            kwargs["model"] = args.model
    if args.headless is not None:
        kwargs["headless"] = args.headless
    return kwargs


def _validate_sites(requested: Optional[List[str]]) -> List[str]:
    """Return validated site list, printing a warning for unknown IDs."""
    if requested is None:
        return ALL_SITE_IDS

    valid, invalid = [], []
    for s in requested:
        (valid if s in SITE_OUTPUT_PREFIXES else invalid).append(s)

    if invalid:
        print(
            f"[WARN] Unknown site IDs (ignored): {invalid}\n"
            f"       Valid choices: {ALL_SITE_IDS}",
            file=sys.stderr,
        )

    return valid if valid else ALL_SITE_IDS


# ── Pretty printing ───────────────────────────────────────────────────────────

def _print_summary(results: List[PipelineResult], total_s: float) -> None:
    successes = [r for r in results if r.success]
    failures  = [r for r in results if not r.success]

    print()
    print("=" * 72)
    print("PIPELINE SUMMARY")
    print("=" * 72)
    print(f"  Sites processed : {len(results)}")
    print(f"  Successful      : {len(successes)}")
    print(f"  Failed          : {len(failures)}")
    print(f"  Total products  : {sum(r.product_count for r in results)}")
    print(f"  Total time      : {total_s:.1f}s")

    if successes:
        print()
        print("  Outputs written:")
        for r in successes:
            for fmt, path in r.output_paths.items():
                print(f"    {fmt.upper():<5} {path}")

    if failures:
        print()
        print("  Errors:")
        for r in failures:
            for err in r.errors:
                print(f"    [{r.site}] {err}")

    print("=" * 72)


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser  = _build_parser()
    args    = parser.parse_args(argv)

    sites   = _validate_sites(args.sites)
    verbose = not args.quiet   # --quiet suppresses, everything else is verbose

    print(
        f"\nScraper Agent  |  runner={args.runner}  |  "
        f"sites={sites}  |  output={args.output_dir}"
    )
    if args.dry_run:
        print("  [DRY RUN — no files will be written]")
    print()

    wall_start = time.monotonic()

    with Pipeline(
        runner_name=args.runner,
        runner_kwargs=_runner_kwargs(args),
        outputs_dir=args.output_dir,
        skip_output=args.dry_run,
    ) as pipeline:
        results = pipeline.run_all(sites, verbose=verbose)

    total_s = round(time.monotonic() - wall_start, 1)
    _print_summary(results, total_s)

    # Exit 1 if any site failed
    return 0 if all(r.success for r in results) else 1



if __name__ == "__main__":
    exit_code = 1

    try:
        exit_code = main()
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Execution cancelled by user.")
        exit_code = 130
    except Exception as exc:
        print(f"\n[FATAL ERROR] {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        print()
        print("=" * 72)
        print("EXECUTION FINISHED — THE END")
        print("=" * 72)
        sys.stdout.flush()
        sys.stderr.flush()

    sys.exit(exit_code)
