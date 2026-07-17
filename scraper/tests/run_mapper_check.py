"""Quick smoke-test for the mapper (run as a plain script)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mapper.schema_mapper import map_to_schema, _best_raw_key, _normalise_key
from schemas.core import FieldConfidence
from schemas.sites import BambulabProduct, FormlabsProduct, UltimakerProduct, ActiveFloorProduct

errors = []

def check(label, condition):
    if not condition:
        errors.append(f"FAIL: {label}")
    else:
        print(f"  ok  {label}")

# _normalise_key
check("normalise underscore", _normalise_key("product_name") == "product name")
check("normalise hyphen", _normalise_key("product-name") == "product name")
check("normalise upper", _normalise_key("ProductName") == "productname")

# _best_raw_key
k, c = _best_raw_key("product_name", ["product_name", "price"])
check("exact high", k == "product_name" and c == FieldConfidence.HIGH)

k, c = _best_raw_key("product_name", ["title", "price"])
check("alias title=high", k == "title" and c == FieldConfidence.HIGH)

k, c = _best_raw_key("price", ["Cost"])
check("alias Cost=high", k == "Cost" and c == FieldConfidence.HIGH)

k, c = _best_raw_key("price", ["Prise"])
check("fuzzy Prise=low", k == "Prise" and c == FieldConfidence.LOW)

k, c = _best_raw_key("price", ["color", "brand"])
check("no match=missing", k is None and c == FieldConfidence.MISSING)

# map_to_schema - exact
r = map_to_schema({"product_name": "X1C", "price": "$1,449"}, BambulabProduct)
check("exact product_name", r.product_name == "X1C")
check("exact price", r.price == "$1,449")
check("exact conf HIGH product_name", r.get_confidence("product_name") == FieldConfidence.HIGH)
check("exact conf HIGH price", r.get_confidence("price") == FieldConfidence.HIGH)

# map_to_schema - alias
r = map_to_schema({"title": "P1S", "Cost": "$699"}, BambulabProduct)
check("alias product_name", r.product_name == "P1S")
check("alias price", r.price == "$699")

# map_to_schema - missing field
r = map_to_schema({"product_name": "A1"}, BambulabProduct)
check("missing price is None", r.price is None)
check("missing price conf", r.get_confidence("price") == FieldConfidence.MISSING)

# map_to_schema - fuzzy LOW
r = map_to_schema({"product_name": "Widget", "Prise": "$200"}, BambulabProduct)
check("fuzzy price value", r.price == "$200")
check("fuzzy price conf LOW", r.get_confidence("price") == FieldConfidence.LOW)

# map_to_schema - formlabs alias
r = map_to_schema({"product_name": "Form 4", "description": "SLA printer"}, FormlabsProduct)
check("formlabs desc alias", r.product_details == "SLA printer")
check("formlabs desc conf HIGH", r.get_confidence("product_details") == FieldConfidence.HIGH)

# map_to_schema - list
rs = map_to_schema([{"product_name": "A"}, {"product_name": "B"}], BambulabProduct)
check("list length", len(rs) == 2)
check("list item 0", rs[0].product_name == "A")

# null string normalisation
r = map_to_schema({"product_name": "W", "price": "N/A"}, BambulabProduct)
check("null string price=None", r.price is None)

# extra pass-through
r = map_to_schema({"product_name": "X", "custom_weird": "hello"}, BambulabProduct)
check("extra field pass-through", getattr(r, "custom_weird", None) == "hello")

print()
if errors:
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print(f"ALL {18} MAPPER CHECKS PASSED")
