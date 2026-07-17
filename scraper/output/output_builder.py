"""
Output Builder

Receives a list of mapped ProductBase instances (with _field_confidence)
and writes three output files per site:

  outputs/{prefix}.json          — full records including confidence metadata
  outputs/{prefix}.csv           — flat CSV; inferred fields marked with *,
                                   missing fields as N/A
  outputs/{prefix}_report.html   — HTML table with colour-coded cells:
                                     green  → confidence HIGH
                                     yellow → confidence LOW  (inferred)
                                     red    → confidence MISSING
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from schemas.core import FieldConfidence, ProductBase

# Default output directory (relative to the scraper package root)
DEFAULT_OUTPUTS_DIR = Path(__file__).resolve().parent.parent / "outputs"

# ── Colour palette (inline CSS) ───────────────────────────────────────────────
_CELL_STYLE: Dict[str, str] = {
    FieldConfidence.HIGH.value:    "background:#d4edda; color:#155724;",   # green
    FieldConfidence.LOW.value:     "background:#fff3cd; color:#856404;",   # yellow
    FieldConfidence.MISSING.value: "background:#f8d7da; color:#721c24;",   # red
    "default":                     "",
}

# Fields that are always excluded from the HTML / CSV data columns
# (they're shown separately or are internal)
_EXCLUDE_FROM_TABLE = {"scraped_at", "_field_confidence"}


class OutputBuilder:
    """
    Serialise a list of ProductBase instances to JSON, CSV, and HTML.

    Usage:
        builder = OutputBuilder(products, site="bambulab", output_prefix="07_bambulab_products")
        builder.save()                       # writes all three files
        builder.save(outputs_dir=Path("./outputs"))
    """

    def __init__(
        self,
        products: Sequence[ProductBase],
        *,
        site: str,
        output_prefix: str,
    ) -> None:
        self.products = list(products)
        self.site = site
        self.output_prefix = output_prefix

    # ── Public API ────────────────────────────────────────────────────────

    def save(
        self,
        outputs_dir: Path = DEFAULT_OUTPUTS_DIR,
    ) -> Dict[str, Path]:
        """
        Write all three output files. Returns a dict of {format: path}.
        Creates outputs_dir if it doesn't exist.
        """
        outputs_dir.mkdir(parents=True, exist_ok=True)

        json_path = outputs_dir / f"{self.output_prefix}.json"
        csv_path  = outputs_dir / f"{self.output_prefix}.csv"
        html_path = outputs_dir / f"{self.output_prefix}_report.html"

        self._write_json(json_path)
        self._write_csv(csv_path)
        self._write_html(html_path)

        return {"json": json_path, "csv": csv_path, "html": html_path}

    # ── JSON ──────────────────────────────────────────────────────────────

    def _write_json(self, path: Path) -> None:
        records = []
        for p in self.products:
            data = p.model_dump(exclude_none=False)
            # Attach confidence dict as a sibling key
            data["_field_confidence"] = p.confidence_dict()
            records.append(data)

        with path.open("w", encoding="utf-8") as fh:
            json.dump(records, fh, ensure_ascii=False, indent=2, default=str)

    # ── CSV ───────────────────────────────────────────────────────────────

    def _write_csv(self, path: Path) -> None:
        if not self.products:
            path.write_text("", encoding="utf-8")
            return

        # Build flat rows
        rows = [self._flatten_for_csv(p) for p in self.products]

        # Determine column order: declared fields first, then extras
        all_keys: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for k in row:
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)

        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=all_keys, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    def _flatten_for_csv(self, p: ProductBase) -> Dict[str, Any]:
        """
        Flatten one product to a CSV row dict.
        - HIGH fields: value as-is
        - LOW fields:  value + " *" suffix (flagged, inferred)
        - MISSING fields: "N/A"
        - specifications (dict) → JSON string
        - list fields → pipe-separated string
        """
        flat = p.to_flat_dict()

        # to_flat_dict already serialises specs and confidence; remove internal key
        flat.pop("_field_confidence", None)

        conf_dict = p.confidence_dict()

        result: Dict[str, Any] = {}
        for field, raw_value in flat.items():
            if field in _EXCLUDE_FROM_TABLE:
                continue

            conf = conf_dict.get(field, FieldConfidence.HIGH.value)
            value = _serialise_value(raw_value)

            if conf == FieldConfidence.MISSING.value and (value is None or value == ""):
                result[field] = "N/A"
            elif conf == FieldConfidence.LOW.value and value not in (None, "", "N/A"):
                result[field] = f"{value} *"
            else:
                result[field] = value if value is not None else ""

        return result

    # ── HTML ──────────────────────────────────────────────────────────────

    def _write_html(self, path: Path) -> None:
        html = self._build_html()
        path.write_text(html, encoding="utf-8")

    def _build_html(self) -> str:
        if not self.products:
            return _html_page(self.site, "<p>No products extracted.</p>")

        # Collect all column names
        all_cols: list[str] = []
        seen_cols: set[str] = set()
        for p in self.products:
            for k in p.model_dump():
                if k not in _EXCLUDE_FROM_TABLE and k not in seen_cols:
                    seen_cols.add(k)
                    all_cols.append(k)

        # Build legend + table
        legend = _build_legend()
        table  = self._build_table(all_cols)

        stats = self._build_stats()

        return _html_page(
            self.site,
            f"{stats}\n{legend}\n{table}",
        )

    def _build_table(self, cols: List[str]) -> str:
        header_cells = "".join(f"<th>{_esc(c)}</th>" for c in cols)
        header = f"<tr>{header_cells}</tr>"

        rows_html = []
        for p in self.products:
            data = p.model_dump(exclude_none=False)
            conf_dict = p.confidence_dict()

            cells = []
            for col in cols:
                raw = data.get(col)
                value = _serialise_value(raw)
                conf  = conf_dict.get(col, FieldConfidence.HIGH.value)
                style = _CELL_STYLE.get(conf, "")

                # Display label for inferred/missing
                display = value or ""
                badge = ""
                if conf == FieldConfidence.LOW.value:
                    badge = ' <span class="badge badge-low">inferred</span>'
                elif conf == FieldConfidence.MISSING.value:
                    display = display or "N/A"
                    badge = ' <span class="badge badge-missing">missing</span>'

                cells.append(
                    f'<td style="{style}">{_esc(display)}{badge}</td>'
                )

            rows_html.append(f"<tr>{''.join(cells)}</tr>")

        rows_str = "\n".join(rows_html)
        return (
            '<div class="table-wrapper">'
            f'<table><thead>{header}</thead>'
            f"<tbody>{rows_str}</tbody></table>"
            "</div>"
        )

    def _build_stats(self) -> str:
        total = len(self.products)
        if total == 0:
            return ""

        high_count = low_count = missing_count = 0
        for p in self.products:
            for conf in p.confidence_dict().values():
                if conf == FieldConfidence.HIGH.value:
                    high_count += 1
                elif conf == FieldConfidence.LOW.value:
                    low_count += 1
                else:
                    missing_count += 1

        return (
            f'<div class="stats">'
            f"<strong>{total}</strong> products &nbsp;|&nbsp; "
            f'<span style="color:#155724">{high_count} high-confidence fields</span> &nbsp;|&nbsp; '
            f'<span style="color:#856404">{low_count} inferred fields</span> &nbsp;|&nbsp; '
            f'<span style="color:#721c24">{missing_count} missing fields</span>'
            "</div>"
        )


# ── Convenience function ──────────────────────────────────────────────────────

def save_outputs(
    products: Sequence[ProductBase],
    *,
    site: str,
    output_prefix: str,
    outputs_dir: Path = DEFAULT_OUTPUTS_DIR,
) -> Dict[str, Path]:
    """
    Convenience wrapper.

    Example:
        paths = save_outputs(products, site="bambulab",
                             output_prefix="07_bambulab_products")
        print(paths["html"])
    """
    builder = OutputBuilder(products, site=site, output_prefix=output_prefix)
    return builder.save(outputs_dir=outputs_dir)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _esc(text: Any) -> str:
    """HTML-escape a value for safe embedding in a table cell."""
    s = str(text) if text is not None else ""
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace('"', "&quot;").replace("'", "&#39;")
    return s


def _serialise_value(raw: Any) -> str:
    """Convert any Python value to a display string for CSV / HTML."""
    if raw is None:
        return ""
    if isinstance(raw, list):
        return " | ".join(str(x) for x in raw)
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw)


def _build_legend() -> str:
    return (
        '<div class="legend">'
        '<span class="swatch" style="background:#d4edda"></span> High confidence &nbsp;'
        '<span class="swatch" style="background:#fff3cd"></span> Inferred (low confidence) &nbsp;'
        '<span class="swatch" style="background:#f8d7da"></span> Missing'
        "</div>"
    )


def _html_page(site: str, body: str) -> str:
    title = f"Extraction Report — {site}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(title)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 13px;
      background: #f8f9fa;
      color: #212529;
      padding: 24px;
    }}
    h1 {{
      font-size: 18px;
      margin-bottom: 12px;
      color: #343a40;
    }}
    .stats {{
      margin-bottom: 10px;
      font-size: 13px;
      color: #495057;
    }}
    .legend {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 16px;
      font-size: 12px;
      color: #495057;
    }}
    .swatch {{
      display: inline-block;
      width: 14px;
      height: 14px;
      border: 1px solid #ced4da;
      border-radius: 2px;
      vertical-align: middle;
    }}
    .table-wrapper {{
      overflow-x: auto;
      border-radius: 6px;
      box-shadow: 0 1px 4px rgba(0,0,0,.12);
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      background: #fff;
    }}
    thead tr {{
      background: #343a40;
      color: #fff;
    }}
    th {{
      padding: 8px 10px;
      text-align: left;
      font-weight: 600;
      white-space: nowrap;
      font-size: 12px;
      letter-spacing: .03em;
    }}
    td {{
      padding: 6px 10px;
      border-bottom: 1px solid #dee2e6;
      vertical-align: top;
      max-width: 320px;
      overflow-wrap: break-word;
    }}
    tbody tr:hover td {{
      filter: brightness(0.96);
    }}
    .badge {{
      display: inline-block;
      font-size: 10px;
      font-weight: 700;
      padding: 1px 5px;
      border-radius: 3px;
      vertical-align: middle;
      margin-left: 4px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .badge-low     {{ background:#ffc107; color:#212529; }}
    .badge-missing {{ background:#dc3545; color:#fff; }}
  </style>
</head>
<body>
  <h1>{_esc(title)}</h1>
  {body}
</body>
</html>
"""
