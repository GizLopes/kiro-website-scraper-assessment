# Websites Assessment — LLM-Powered Product Scraper

Product data extraction pipeline combining an LLM agent with browser control to collect, map, and export catalogs from 7 educational technology websites that use 3D printers.

---

## Overview

```
Prompt Builder  →  Runner (LLM/browser)  →  Schema Mapper  →  Output Builder
     ↓                      ↓                      ↓                  ↓
Loads site YAML        Sends prompt          Maps raw dicts     Saves JSON,
and builds final       to agent and          to Pydantic        CSV, and HTML
prompt                 receives data         w/ confidence      per site
```

The pipeline is triggered by `scraper/main.py` and runs through three stages for each site:

1. **Stage 1 — Runner**: Sends the extraction prompt to the LLM agent (mock, BrowserUse, or AgentCore/Bedrock) and receives a list of raw dicts.
2. **Stage 2 — Mapper**: Maps each dict to the site's Pydantic schema, annotating each field with a confidence level (`high`, `low`, `missing`).
3. **Stage 3 — Output**: Serializes the mapped products into `.json`, `.csv`, and `_report.html` inside `scraper/outputs/`.

---

## Covered Websites

| ID | Website | URL |
|----|---------|-----|
| `active_floor` | ActiveFloor | https://activefloor.com |
| `smart_tech` | SMART Technologies | https://smarttech.com |
| `play_lu` | Play-Lu | https://play-lu.com |
| `ultimaker` | Ultimaker | https://ultimaker.com |
| `makerbot` | MakerBot | https://makerbot.com |
| `bambulab` | Bambu Lab | https://bambulab.com/en-us |
| `formlabs` | Formlabs | https://formlabs.com/store |

---

## Project Structure

```
websites-assessment/
└── scraper/                            # Main package
    ├── main.py                         # CLI entry point
    ├── descriptors/                    # Per-site configuration (YAML)
    │   ├── bambulab.yaml
    │   ├── formlabs.yaml
    │   └── ... (7 files)
    ├── schemas/
    │   ├── core.py                    # ProductBase + FieldConfidence
    │   └── sites.py                   # Per-site schemas + SITE_SCHEMA_MAP
    ├── prompts/
    │   └── prompt_builder.py          # Loads YAML and builds the final prompt
    ├── runner/
    │   ├── base_runner.py             # ABC BrowserAgentRunner + RunnerResult
    │   ├── mock_runner.py             # Browserless runner (uses JSON fixtures)
    │   ├── browseruse_runner.py       # Runner using browser-use + Bedrock
    │   ├── agentcore_runner.py        # Runner using Bedrock Converse API
    │   └── fixtures/                  # Test data for all 7 sites
    ├── mapper/
    │   └── schema_mapper.py           # Fuzzy dict → Pydantic mapping
    ├── output/
    │   └── output_builder.py          # JSON / CSV / HTML serialization
    ├── pipeline/
    │   └── pipeline.py                # Orchestrates the 3 stages
    ├── outputs/                        # Generated files (git-ignored)
    └── tests/
        ├── test_pipeline.py           # Pytest suite — pipeline (136 tests)
        ├── test_runner.py             # Pytest suite — runners
        ├── test_mapper.py             # Pytest suite — schema mapper
        ├── test_output_builder.py     # Pytest suite — output builder
        ├── test_prompt_builder.py     # Pytest suite — prompt builder
        ├── test_schemas.py            # Pytest suite — Pydantic schemas
        ├── run_pipeline_check.py      # Smoke script — pipeline (no pytest)
        ├── run_runner_check.py        # Smoke script — runners
        ├── run_mapper_check.py        # Smoke script — mapper
        ├── run_output_builder_check.py
        └── run_prompt_builder_check.py
```

---

## How to Run

### Prerequisites

```powershell
# Install base dependencies (Pydantic, PyYAML, etc.)
pip install pydantic pyyaml
```

### Running with MockRunner (default — no browser, no API)

```powershell
# All 7 sites
python scraper/main.py

# A specific site
python scraper/main.py --sites bambulab

# Multiple sites
python scraper/main.py --sites bambulab formlabs ultimaker

# Dry-run (do not save files)
python scraper/main.py --dry-run

# Custom output directory
python scraper/main.py --output-dir C:\tmp\outputs
```

The MockRunner serves data from fixtures in `scraper/runner/fixtures/` without opening any browser. Useful for development, testing, and CI.

### Running with BrowserUse Runner (real browser + Bedrock)

```powershell
pip install "browser-use[aws]" boto3
playwright install chromium

$env:AWS_PROFILE        = "my-profile"
$env:AWS_DEFAULT_REGION = "us-east-1"
$env:BEDROCK_MODEL_ID   = "anthropic.claude-sonnet-4-6"

python scraper/main.py --runner browseruse --sites bambulab
```

The BrowserUseRunner opens a real Chromium browser controlled by the LLM. The agent navigates the site, extracts data, and returns a JSON array.

### Running with AgentCore Runner (Bedrock Converse API, browserless)

```powershell
pip install boto3

$env:AWS_ACCESS_KEY_ID     = "..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_DEFAULT_REGION    = "us-east-1"

python scraper/main.py --runner agentcore --sites bambulab
```

The AgentCoreRunner calls the Bedrock Converse API directly (no local browser). It sends the extraction prompt and parses the returned JSON from the model.

### Full CLI Options

```
python scraper/main.py --help

  --sites SITE_ID [...]    Sites to process (default: all 7)
  --runner {mock,browseruse,agentcore}
  --output-dir PATH        Output directory (default: scraper/outputs/)
  --dry-run                Skip Stage 3 (does not save files)
  --quiet                  Suppress per-site progress lines
  --llm-provider STR       LLM provider for browseruse: 'bedrock'
  --model STR              Model ID (browseruse / agentcore)
  --headless / --no-headless  Browser headless mode (browseruse)
```

---

## Output Files

For each site, three files are generated in `scraper/outputs/`:

| File | Content |
|------|---------|
| `07_bambulab_products.json` | JSON array containing all fields + `_field_confidence` metadata |
| `07_bambulab_products.csv` | Flat table; inferred fields marked with `*`, missing as `N/A` |
| `07_bambulab_products_report.html` | HTML table with cells color-coded by confidence |

**HTML Color Scale:**

| Color | Meaning |
|-------|---------|
| 🟢 Green | Field extracted with exact match (`high`) |
| 🟡 Yellow | Field inferred via semantic similarity (`low`) |
| 🔴 Red | Field missing in LLM response (`missing`) |

---

## Components in Detail

### Descriptors (YAML)

Each site has a YAML file in `scraper/descriptors/` with three sections:

```yaml
site: bambulab
base_url: "https://bambulab.com/en-us/"
output_prefix: "07_bambulab_products"

schema_fields:
  - product_name
  - category
  - price
  - product_url
  - details
  - specifications

instructions: |
  Detailed navigation and extraction instructions for the LLM agent...
```

The `PromptBuilder` loads this YAML and builds the final prompt, including instructions, a JSON Schema of expected fields, and the output contract (JSON array only).

### Pydantic Schemas

`ProductBase` defines common fields across all sites. Each site inherits and adds specific fields:

```python
# Base fields (all sites)
product_name, category, subcategory, price,
product_url, source_url, specifications, scraped_at

# Examples of site-specific fields
ActiveFloorProduct  → height_metric, width_metric, weight_metric, projector, brightness
SmartTechProduct    → display_size, resolution, touch_points, connectivity
BambulabProduct     → details
FormlabsProduct     → product_details
UltimakerProduct    → specs (list of objects {spec_name, type, spec_value})
MakerbotProduct     → price_current
PlayLuProduct       → item_type, description, target_age, technical_specifications
```

### Schema Mapper

`SchemaMapper` resolves key name mismatches between LLM responses and Pydantic schema fields using three cascading strategies:

1. **Exact match** (case-insensitive, normalized) → `high` confidence
2. **Explicit aliases** (e.g., `"cost"` → `price`, `"title"` → `product_name`) → `high` confidence
3. **Fuzzy similarity** via `difflib.SequenceMatcher` with a 0.72 threshold → `low` confidence

If no strategy finds a match, the field receives `None` and `missing` confidence.

### Runners

| Runner | Usage | Dependencies |
|--------|-------|--------------|
| `MockRunner` | Testing and CI — serves local fixtures | None |
| `BrowserUseRunner` | Real extraction with Chromium browser | `browser-use[aws]`, `boto3`, `playwright` |
| `AgentCoreRunner` | Extraction via Bedrock Converse API (browserless) | `boto3` |

All inherit from `BrowserAgentRunner` and implement `run(prompt, site) → RunnerResult`. The pipeline communicates strictly with this interface, allowing runners to be swapped without modifying any other module.

---

## Testing

### Pytest (full suite)

```powershell
# All modules
python -m pytest scraper/tests/ -v

# Pipeline only
python -m pytest scraper/tests/test_pipeline.py -v

# With coverage report (requires pytest-cov)
python -m pytest scraper/tests/ --cov=scraper --cov-report=term-missing
```

### Smoke Scripts (without pytest)

```powershell
python scraper/tests/run_pipeline_check.py       # 160 checks
python scraper/tests/run_runner_check.py
python scraper/tests/run_mapper_check.py
python scraper/tests/run_output_builder_check.py
python scraper/tests/run_prompt_builder_check.py
```

Smoke scripts are useful in environments without pytest installed or for quick diagnosis. They exit with code 0 if everything passes, and 1 if any check fails.

---

## Environment Variables

| Variable | Used By | Default |
|----------|---------|---------|
| `BEDROCK_MODEL_ID` | AgentCoreRunner, BrowserUseRunner | `anthropic.claude-sonnet-4-6` |
| `AWS_DEFAULT_REGION` | AgentCoreRunner, BrowserUseRunner | `us-east-1` |
| `AWS_ACCESS_KEY_ID` | AgentCoreRunner | — |
| `AWS_SECRET_ACCESS_KEY` | AgentCoreRunner | — |
| `AWS_PROFILE` | BrowserUseRunner | — |
