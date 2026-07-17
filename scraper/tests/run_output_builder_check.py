"""Quick smoke-test for OutputBuilder (run as a plain script)."""
import csv
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from output.output_builder import OutputBuilder, save_outputs
from schemas.core import FieldConfidence, ProductBase
from schemas.sites import BambulabProduct, FormlabsProduct

errors = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if not condition:
        msg = f"FAIL: {label}" + (f" — {detail}" if detail else "")
        errors.append(msg)
    else:
        print(f"  ok  {label}")


# ── Fixture helpers ───────────────────────────────────────────────────────────

def make_bambulab_product(name: str, price: str | None, conf_price: FieldConfidence) -> BambulabProduct:
    p = BambulabProduct(
        product_name=name,
        category="3D Printers",
        price=price,
        product_url=f"https://bambulab.com/{name.lower().replace(' ', '-')}",
        specifications={"build_volume": "256x256x256 mm"},
    )
    p.set_confidence("product_name", FieldConfidence.HIGH)
    p.set_confidence("category", FieldConfidence.HIGH)
    p.set_confidence("price", conf_price)
    p.set_confidence("product_url", FieldConfidence.HIGH)
    p.set_confidence("specifications", FieldConfidence.HIGH)
    return p


def make_formlabs_product() -> FormlabsProduct:
    p = FormlabsProduct(
        product_name="Form 4",
        category="3D Printers",
        price=None,
        product_details="SLA resin printer",
    )
    p.set_confidence("product_name", FieldConfidence.HIGH)
    p.set_confidence("category", FieldConfidence.HIGH)
    p.set_confidence("price", FieldConfidence.MISSING)
    p.set_confidence("product_details", FieldConfidence.LOW)
    return p


# ── Build a set of mixed-confidence products ──────────────────────────────────
products = [
    make_bambulab_product("X1 Carbon", "$1,449", FieldConfidence.HIGH),
    make_bambulab_product("P1S", "$699", FieldConfidence.LOW),
    make_bambulab_product("A1 Mini", None, FieldConfidence.MISSING),
]
formlabs_products = [make_formlabs_product()]

with tempfile.TemporaryDirectory() as tmpdir:
    outdir = Path(tmpdir)

    # ── save_outputs convenience function ─────────────────────────────────
    paths = save_outputs(
        products,
        site="bambulab",
        output_prefix="07_bambulab_products",
        outputs_dir=outdir,
    )

    # Files created
    check("JSON file created", paths["json"].exists())
    check("CSV file created", paths["csv"].exists())
    check("HTML file created", paths["html"].exists())

    # ── JSON checks ───────────────────────────────────────────────────────
    with paths["json"].open(encoding="utf-8") as fh:
        records = json.load(fh)

    check("JSON: 3 records", len(records) == 3)
    check("JSON: product_name present", "product_name" in records[0])
    check("JSON: _field_confidence present", "_field_confidence" in records[0])
    check("JSON: HIGH conf for X1C name",
          records[0]["_field_confidence"].get("product_name") == "high")
    check("JSON: MISSING conf for A1 price",
          records[2]["_field_confidence"].get("price") == "missing")

    # ── CSV checks ────────────────────────────────────────────────────────
    with paths["csv"].open(encoding="utf-8-sig", newline="") as fh:
        reader = list(csv.DictReader(fh))

    check("CSV: 3 rows", len(reader) == 3)
    check("CSV: product_name column", "product_name" in reader[0])
    # HIGH confidence: value as-is
    check("CSV: HIGH price no star", reader[0]["price"] == "$1,449")
    # LOW confidence: value + " *"
    check("CSV: LOW price has star", reader[1]["price"] == "$699 *")
    # MISSING confidence: N/A
    check("CSV: MISSING price is N/A", reader[2]["price"] == "N/A")

    # ── HTML checks ───────────────────────────────────────────────────────
    html = paths["html"].read_text(encoding="utf-8")

    check("HTML: DOCTYPE present", "<!DOCTYPE html>" in html)
    check("HTML: title contains site name", "bambulab" in html.lower())
    check("HTML: table present", "<table>" in html)
    check("HTML: thead present", "<thead>" in html)
    check("HTML: legend present", "legend" in html)
    check("HTML: green HIGH colour", "#d4edda" in html)
    check("HTML: yellow LOW colour", "#fff3cd" in html)
    check("HTML: red MISSING colour", "#f8d7da" in html)
    check("HTML: inferred badge", "badge-low" in html)
    check("HTML: missing badge", "badge-missing" in html)
    check("HTML: product names in table", "X1 Carbon" in html)
    check("HTML: stats section present", "products" in html)

    # ── Empty products list ───────────────────────────────────────────────
    empty_paths = save_outputs(
        [],
        site="bambulab",
        output_prefix="07_bambulab_empty",
        outputs_dir=outdir,
    )
    check("Empty JSON: file created", empty_paths["json"].exists())
    check("Empty CSV: file created", empty_paths["csv"].exists())
    empty_html = empty_paths["html"].read_text(encoding="utf-8")
    check("Empty HTML: no products message", "No products extracted" in empty_html)

    # ── Formlabs: LOW product_details + MISSING price ─────────────────────
    fl_paths = save_outputs(
        formlabs_products,
        site="formlabs",
        output_prefix="08_formlabs_test",
        outputs_dir=outdir,
    )
    fl_csv_rows = list(csv.DictReader(fl_paths["csv"].open(encoding="utf-8-sig", newline="")))
    check("Formlabs CSV: LOW product_details has star",
          fl_csv_rows[0]["product_details"] == "SLA resin printer *")
    check("Formlabs CSV: MISSING price is N/A",
          fl_csv_rows[0]["price"] == "N/A")
    fl_html = fl_paths["html"].read_text(encoding="utf-8")
    check("Formlabs HTML: inferred badge present", "badge-low" in fl_html)
    check("Formlabs HTML: missing badge present", "badge-missing" in fl_html)

    # ── OutputBuilder directly ────────────────────────────────────────────
    builder = OutputBuilder(
        products,
        site="bambulab",
        output_prefix="07_bambulab_direct",
    )
    direct_paths = builder.save(outputs_dir=outdir)
    check("Direct builder: JSON exists", direct_paths["json"].exists())
    check("Direct builder: CSV exists", direct_paths["csv"].exists())
    check("Direct builder: HTML exists", direct_paths["html"].exists())

# ── HTML escaping ─────────────────────────────────────────────────────────────
from output.output_builder import _esc
check("_esc: ampersand", _esc("A & B") == "A &amp; B")
check("_esc: less-than", _esc("<script>") == "&lt;script&gt;")
check("_esc: None", _esc(None) == "")

# ── serialise_value ───────────────────────────────────────────────────────────
from output.output_builder import _serialise_value
check("_serialise_value: list", _serialise_value(["a", "b"]) == "a | b")
check("_serialise_value: None", _serialise_value(None) == "")
check("_serialise_value: dict", "{" in _serialise_value({"k": "v"}))

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print(f"ALL OUTPUT BUILDER CHECKS PASSED")
