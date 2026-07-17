"""
Site-specific Pydantic schemas.

Each class inherits ProductBase and adds the extra fields that the
LLM is expected (but not required) to extract from that particular site.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field

from .core import ProductBase


# ── 01 ActiveFloor ─────────────────────────────────────────────────────────────
class ActiveFloorProduct(ProductBase):
    """
    Source: https://activefloor.com/interactive-spaces/
    Categories: Floor | Wall | Table
    Previously extracted via PDF OCR; now extracted directly from the web page.
    """

    # Physical dimensions visible on product pages
    height_metric: Optional[str] = Field(None, description="Installation box height (metric)")
    height_imperial: Optional[str] = Field(None, description="Installation box height (imperial)")
    width_metric: Optional[str] = Field(None, description="Installation box width (metric)")
    width_imperial: Optional[str] = Field(None, description="Installation box width (imperial)")
    weight_metric: Optional[str] = Field(None, description="Product weight (metric)")
    weight_imperial: Optional[str] = Field(None, description="Product weight (imperial)")
    vinyl_size: Optional[str] = Field(None, description="Vinyl / projection surface size")
    projector: Optional[str] = Field(None, description="Projector model or specification")
    brightness: Optional[str] = Field(None, description="Projector brightness (lumens)")


# ── 02 SmartTech ───────────────────────────────────────────────────────────────
class SmartTechProduct(ProductBase):
    """
    Source: https://www.smarttech.com/products
    Categories: interactive-displays | commercial-displays | software | accessories
    """

    display_size: Optional[str] = Field(None, description="Display diagonal size")
    resolution: Optional[str] = Field(None, description="Display resolution")
    touch_points: Optional[str] = Field(None, description="Number of simultaneous touch points")
    connectivity: Optional[str] = Field(None, description="Connectivity options (USB, HDMI, Wi-Fi…)")
    operating_system: Optional[str] = Field(None, description="Built-in OS if any")


# ── 03 Play-Lu ─────────────────────────────────────────────────────────────────
class PlayLuProduct(ProductBase):
    """
    Source: https://play-lu.com/
    Types: app | configuration
    """

    item_type: Optional[str] = Field(None, description="'app' or 'configuration'")
    description: Optional[str] = Field(None, description="Short product / app description")
    target_age: Optional[str] = Field(None, description="Target age range (e.g. '6+', 'All ages')")
    technical_specifications: Optional[List[str]] = Field(
        default_factory=list,
        description="Key elements list for configuration products",
    )


# ── 05 Ultimaker ───────────────────────────────────────────────────────────────
class UltimakerProduct(ProductBase):
    """
    Source: https://ultimaker.com/
    Series: Factor | S | Method
    Specs are a list of {spec_name, type, spec_value} objects.
    """

    specs: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Structured specs table rows: [{spec_name, type, spec_value}]",
    )


# ── 06 MakerBot ────────────────────────────────────────────────────────────────
class MakerbotProduct(ProductBase):
    """
    Source: https://www.makerbot.com/ (redirects to store.ultimaker.com)
    Categories: 3D Printers | Materials | Extruders | Parts & Accessories
    """

    price_current: Optional[str] = Field(None, description="Current (possibly discounted) price")


# ── 07 Bambu Lab ───────────────────────────────────────────────────────────────
class BambulabProduct(ProductBase):
    """
    Source: https://bambulab.com/en-us/
    Categories: 3D Printers | Filament | Accessories | Maker's Supply | Spare Parts
    Maker's Supply has subcategories: Model Kits | Hardware Parts | Electronics |
    Tool&Others | CyberBrick
    """

    details: Optional[str] = Field(
        None,
        description="Product features / physical properties extracted from the PDP",
    )


# ── 08 Formlabs ────────────────────────────────────────────────────────────────
class FormlabsProduct(ProductBase):
    """
    Source: https://formlabs.com/store/
    Categories: 3D Printers | Materials | Post-Processing | Accessories | Parts |
                Deals and Factory Reconditioned
    """

    product_details: Optional[str] = Field(
        None,
        description="Product description or what's included, from the PDP",
    )


# ── Registry ───────────────────────────────────────────────────────────────────
SITE_SCHEMA_MAP: Dict[str, type] = {
    "active_floor": ActiveFloorProduct,
    "smart_tech": SmartTechProduct,
    "play_lu": PlayLuProduct,
    "ultimaker": UltimakerProduct,
    "makerbot": MakerbotProduct,
    "bambulab": BambulabProduct,
    "formlabs": FormlabsProduct,
}
