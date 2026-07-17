"""Tests for PromptBuilder."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.prompt_builder import PromptBuilder, build_prompt

DESCRIPTORS_DIR = Path(__file__).resolve().parents[1] / "descriptors"

ALL_SITES = [
    "active_floor",
    "smart_tech",
    "play_lu",
    "ultimaker",
    "makerbot",
    "bambulab",
    "formlabs",
]


class TestPromptBuilder:

    def _builder(self, site: str) -> PromptBuilder:
        return PromptBuilder(site, descriptors_dir=DESCRIPTORS_DIR)

    # ── Descriptor loading ────────────────────────────────────────────────

    def test_all_descriptor_files_exist(self):
        for site in ALL_SITES:
            path = DESCRIPTORS_DIR / f"{site}.yaml"
            assert path.exists(), f"Missing descriptor: {path}"

    def test_missing_descriptor_raises(self):
        with pytest.raises(FileNotFoundError):
            PromptBuilder("nonexistent_site", descriptors_dir=DESCRIPTORS_DIR)

    def test_descriptor_has_required_keys(self):
        required = {"site", "base_url", "schema_fields", "instructions"}
        for site in ALL_SITES:
            b = self._builder(site)
            missing = required - set(b.descriptor.keys())
            assert not missing, f"{site} descriptor missing keys: {missing}"

    def test_schema_fields_non_empty(self):
        for site in ALL_SITES:
            b = self._builder(site)
            assert len(b.schema_fields()) > 0, f"{site} has no schema_fields"

    def test_base_url_starts_with_https(self):
        for site in ALL_SITES:
            b = self._builder(site)
            assert b.base_url().startswith("https://"), \
                f"{site} base_url does not start with https://"

    # ── Prompt content ────────────────────────────────────────────────────

    def test_prompt_contains_base_url(self):
        for site in ALL_SITES:
            b = self._builder(site)
            prompt = b.build()
            assert b.base_url() in prompt, f"{site}: base_url not in prompt"

    def test_prompt_contains_instructions(self):
        for site in ALL_SITES:
            b = self._builder(site)
            prompt = b.build()
            # Instructions should contribute meaningful text
            assert len(b.descriptor["instructions"].strip()) > 50
            # At least some of that text appears in the prompt
            first_line = b.descriptor["instructions"].strip().splitlines()[0][:40]
            assert first_line in prompt, \
                f"{site}: first instruction line not found in prompt"

    def test_prompt_contains_all_schema_fields(self):
        for site in ALL_SITES:
            b = self._builder(site)
            prompt = b.build()
            for field in b.schema_fields():
                if field == "scraped_at":
                    continue  # auto-filled, intentionally omitted from prompt
                assert f"`{field}`" in prompt or f'"{field}"' in prompt, \
                    f"{site}: field '{field}' not referenced in prompt"

    def test_prompt_contains_output_contract(self):
        for site in ALL_SITES:
            b = self._builder(site)
            prompt = b.build()
            assert "JSON array" in prompt
            assert "null" in prompt

    def test_scraped_at_not_in_output_contract(self):
        for site in ALL_SITES:
            b = self._builder(site)
            prompt = b.build()
            # scraped_at should be mentioned as "do NOT include" but not
            # listed as a required output field
            assert "scraped_at" in prompt  # the don't-include note
            # It should NOT appear as a required field bullet
            lines = prompt.splitlines()
            field_bullets = [ln for ln in lines if ln.strip().startswith("- `")]
            field_names = [ln.strip().strip("- `").rstrip("`") for ln in field_bullets]
            assert "scraped_at" not in field_names

    def test_prompt_is_string_and_non_empty(self):
        for site in ALL_SITES:
            b = self._builder(site)
            prompt = b.build()
            assert isinstance(prompt, str)
            assert len(prompt) > 200

    # ── from_dict constructor ─────────────────────────────────────────────

    def test_from_dict(self):
        descriptor = {
            "site": "test_site",
            "base_url": "https://example.com/",
            "output_prefix": "test_output",
            "schema_fields": ["product_name", "price", "product_url"],
            "instructions": "Go to example.com and extract product names and prices.",
        }
        b = PromptBuilder.from_dict(descriptor)
        prompt = b.build()
        assert "https://example.com/" in prompt
        assert "`product_name`" in prompt
        assert "`price`" in prompt

    # ── build_prompt convenience function ────────────────────────────────

    def test_build_prompt_function(self):
        prompt = build_prompt("bambulab", descriptors_dir=DESCRIPTORS_DIR)
        assert "bambulab" in prompt.lower()
        assert "bambulab.com" in prompt

    # ── output_prefix ─────────────────────────────────────────────────────

    def test_output_prefix_set_correctly(self):
        b = self._builder("bambulab")
        assert b.output_prefix() == "07_bambulab_products"

    def test_output_prefix_all_sites(self):
        expected = {
            "active_floor": "01_activefloor_products",
            "smart_tech":   "02_smart_tech_products",
            "play_lu":      "03_play_lu_products",
            "ultimaker":    "05_ultimaker_products",
            "makerbot":     "06_makerbot_products",
            "bambulab":     "07_bambulab_products",
            "formlabs":     "08_formlabs_products",
        }
        for site, prefix in expected.items():
            b = self._builder(site)
            assert b.output_prefix() == prefix, \
                f"{site}: expected prefix '{prefix}', got '{b.output_prefix()}'"
