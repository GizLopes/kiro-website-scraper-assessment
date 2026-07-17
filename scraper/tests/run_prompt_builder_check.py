"""Quick smoke-test for PromptBuilder (run as a plain script)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prompts.prompt_builder import PromptBuilder, build_prompt

DDIR = Path(__file__).resolve().parents[1] / "descriptors"

SITES = ["active_floor", "smart_tech", "play_lu", "ultimaker", "makerbot", "bambulab", "formlabs"]

EXPECTED_PREFIXES = {
    "active_floor": "01_activefloor_products",
    "smart_tech":   "02_smart_tech_products",
    "play_lu":      "03_play_lu_products",
    "ultimaker":    "05_ultimaker_products",
    "makerbot":     "06_makerbot_products",
    "bambulab":     "07_bambulab_products",
    "formlabs":     "08_formlabs_products",
}

errors = []

def check(label, condition, detail=""):
    if not condition:
        msg = f"FAIL: {label}" + (f" — {detail}" if detail else "")
        errors.append(msg)
    else:
        print(f"  ok  {label}")


# ── descriptor files exist ────────────────────────────────────────────────────
for site in SITES:
    path = DDIR / f"{site}.yaml"
    check(f"{site}: descriptor file exists", path.exists())

# ── per-site checks ───────────────────────────────────────────────────────────
for site in SITES:
    try:
        b = PromptBuilder(site, descriptors_dir=DDIR)
        prompt = b.build()
        d = b.descriptor

        # required descriptor keys
        for k in ("site", "base_url", "schema_fields", "instructions"):
            check(f"{site}: descriptor has key '{k}'", k in d)

        # base_url present and in prompt
        check(f"{site}: base_url starts https", b.base_url().startswith("https://"))
        check(f"{site}: base_url in prompt", b.base_url() in prompt)

        # instructions non-trivial
        check(
            f"{site}: instructions non-empty",
            len(d.get("instructions", "").strip()) > 50,
        )

        # all schema fields referenced in prompt
        for f in b.schema_fields():
            if f == "scraped_at":
                continue
            check(
                f"{site}: field '{f}' referenced in prompt",
                f in prompt,
                detail=f"prompt length={len(prompt)}",
            )

        # output contract present
        check(f"{site}: JSON array contract in prompt", "JSON array" in prompt)
        check(f"{site}: null rule in prompt", "null" in prompt)

        # scraped_at not a required output bullet
        lines = prompt.splitlines()
        field_bullets = [ln for ln in lines if ln.strip().startswith("- `")]
        bullet_names = [ln.strip().lstrip("- `").rstrip("`") for ln in field_bullets]
        check(
            f"{site}: scraped_at not a required output bullet",
            "scraped_at" not in bullet_names,
        )

        # output_prefix
        check(
            f"{site}: output_prefix correct",
            b.output_prefix() == EXPECTED_PREFIXES[site],
            detail=f"got '{b.output_prefix()}'",
        )

        print(f"       → prompt_len={len(prompt)} fields={len(b.schema_fields())}")

    except Exception as exc:
        errors.append(f"EXCEPTION for {site}: {exc}")

# ── from_dict constructor ─────────────────────────────────────────────────────
desc = {
    "site": "test_site",
    "base_url": "https://example.com/",
    "output_prefix": "test_output",
    "schema_fields": ["product_name", "price", "product_url"],
    "instructions": "Go to example.com and extract product names and prices.",
}
b2 = PromptBuilder.from_dict(desc)
p2 = b2.build()
check("from_dict: base_url in prompt", "https://example.com/" in p2)
check("from_dict: product_name in prompt", "product_name" in p2)
check("from_dict: price in prompt", "price" in p2)

# ── missing descriptor raises ─────────────────────────────────────────────────
try:
    PromptBuilder("nonexistent_site_xyz", descriptors_dir=DDIR)
    errors.append("FAIL: missing descriptor should raise FileNotFoundError")
except FileNotFoundError:
    check("missing descriptor raises FileNotFoundError", True)

# ── build_prompt function ─────────────────────────────────────────────────────
prompt_bam = build_prompt("bambulab", descriptors_dir=DDIR)
check("build_prompt: returns string", isinstance(prompt_bam, str))
check("build_prompt: bambulab.com in result", "bambulab.com" in prompt_bam)

# ── summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print(f"ALL PROMPT BUILDER CHECKS PASSED")
