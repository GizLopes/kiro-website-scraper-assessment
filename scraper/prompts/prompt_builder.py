"""
Prompt Builder

Loads a site descriptor YAML and builds the final extraction prompt
to be sent to the LLM browser agent.

The prompt embeds:
  1. The navigation + extraction instructions from the descriptor.
  2. A JSON Schema derived from the declared schema_fields, so the LLM
     knows exactly which keys to include in every output object.
  3. A strict output contract telling the LLM to return ONLY a JSON array.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from schemas.sites import SITE_SCHEMA_MAP

# Default location of descriptor files
DESCRIPTORS_DIR = Path(__file__).resolve().parent.parent / "descriptors"

# Field-level descriptions extracted from Pydantic schemas to enrich the
# JSON Schema snippet embedded in the prompt.
_FIELD_TYPE_HINTS: Dict[str, str] = {
    "product_name":             "string",
    "category":                 "string",
    "subcategory":              "string",
    "price":                    "string",
    "price_current":            "string",
    "product_url":              "string (URL)",
    "source_url":               "string (URL)",
    "specifications":           "object (key-value pairs)",
    "scraped_at":               "string (ISO-8601, auto-filled — omit from output)",
    "details":                  "string",
    "product_details":          "string",
    "height_metric":            "string",
    "height_imperial":          "string",
    "width_metric":             "string",
    "width_imperial":           "string",
    "weight_metric":            "string",
    "weight_imperial":          "string",
    "vinyl_size":               "string",
    "projector":                "string",
    "brightness":               "string",
    "display_size":             "string",
    "resolution":               "string",
    "touch_points":             "string",
    "connectivity":             "string",
    "operating_system":         "string",
    "item_type":                "string ('app' or 'configuration')",
    "description":              "string",
    "target_age":               "string",
    "technical_specifications": "array of strings",
    "specs":                    "array of objects {spec_name, type, spec_value}",
}


class PromptBuilder:
    """
    Builds a structured extraction prompt from a site descriptor YAML.

    Usage:
        builder = PromptBuilder("bambulab")
        prompt  = builder.build()
        print(prompt)

    Or with an explicit descriptor dict (useful for tests):
        builder = PromptBuilder.from_dict(descriptor_dict)
        prompt  = builder.build()
    """

    def __init__(
        self,
        site_name: str,
        *,
        descriptors_dir: Path = DESCRIPTORS_DIR,
    ) -> None:
        self.site_name = site_name
        self._descriptor = self._load(site_name, descriptors_dir)

    # ── Constructors ──────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, descriptor: Dict[str, Any]) -> "PromptBuilder":
        """Create a PromptBuilder from a pre-parsed descriptor dict."""
        instance = object.__new__(cls)
        instance.site_name = descriptor.get("site", "unknown")
        instance._descriptor = descriptor
        return instance

    @staticmethod
    def _load(site_name: str, descriptors_dir: Path) -> Dict[str, Any]:
        path = descriptors_dir / f"{site_name}.yaml"
        if not path.exists():
            raise FileNotFoundError(
                f"Descriptor not found: {path}\n"
                f"Available sites: {[p.stem for p in descriptors_dir.glob('*.yaml')]}"
            )
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def descriptor(self) -> Dict[str, Any]:
        return self._descriptor

    def build(self) -> str:
        """
        Build and return the full prompt string.
        """
        d = self._descriptor
        site      = d.get("site", self.site_name)
        base_url  = d.get("base_url", "")
        fields    = d.get("schema_fields", [])
        instructions = (d.get("instructions") or "").strip()

        json_schema_snippet = self._build_json_schema(fields)
        output_contract     = self._build_output_contract(fields)

        prompt = (
            f"# Web Extraction Task — {site}\n\n"
            f"**Entry URL:** {base_url}\n\n"
            "---\n\n"
            "## Instructions\n\n"
            f"{instructions}\n\n"
            "---\n\n"
            "## Output Schema\n\n"
            "Each item in your output array MUST be a JSON object with "
            "**exactly** these keys (use `null` for missing values — do NOT "
            "omit keys):\n\n"
            f"```json\n{json_schema_snippet}\n```\n\n"
            "---\n\n"
            "## Output Contract\n\n"
            f"{output_contract}"
        )
        return prompt

    def schema_fields(self) -> List[str]:
        """Return the list of declared schema fields from the descriptor."""
        return list(self._descriptor.get("schema_fields", []))

    def base_url(self) -> str:
        return self._descriptor.get("base_url", "")

    def output_prefix(self) -> str:
        return self._descriptor.get("output_prefix", self.site_name)

    # ── Private helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_json_schema(fields: List[str]) -> str:
        """
        Build a compact JSON Schema-like example object showing field names
        and their expected types.
        """
        obj: Dict[str, str] = {}
        for f in fields:
            hint = _FIELD_TYPE_HINTS.get(f, "string | null")
            # Skip auto-filled fields from the LLM prompt
            if f == "scraped_at":
                continue
            obj[f] = hint

        return json.dumps(obj, indent=2, ensure_ascii=False)

    @staticmethod
    def _build_output_contract(fields: List[str]) -> str:
        # Filter out auto-filled fields
        visible_fields = [f for f in fields if f != "scraped_at"]
        fields_list = "\n".join(f"  - `{f}`" for f in visible_fields)

        return (
            "Your response MUST be **only** a valid JSON array — no markdown "
            "fences, no commentary, no extra text before or after.\n\n"
            "Every object in the array must include all of these keys:\n\n"
            f"{fields_list}\n\n"
            "Rules:\n"
            "- Use `null` (JSON null) for any field you cannot find.\n"
            "- Use an empty object `{}` for `specifications` when no specs are found.\n"
            "- Use an empty array `[]` for array fields when nothing is found.\n"
            "- Do NOT include the `scraped_at` field — it is filled automatically.\n"
            "- Strings must be UTF-8; do not escape non-ASCII characters.\n"
            "- If there are zero products, return an empty array: `[]`.\n"
        )


# ── Convenience function ─────────────────────────────────────────────────────

def build_prompt(
    site_name: str,
    *,
    descriptors_dir: Path = DESCRIPTORS_DIR,
) -> str:
    """
    Build and return the extraction prompt for the given site.

    Example:
        prompt = build_prompt("bambulab")
        print(prompt)
    """
    return PromptBuilder(site_name, descriptors_dir=descriptors_dir).build()
