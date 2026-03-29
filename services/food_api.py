"""Open Food Facts HTTP search for the in-app library."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List

import httpx

from models.food import Food, NutritionInfo

logger = logging.getLogger(__name__)

OFF_LIBRARY_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
LIBRARY_USER_AGENT = "MacroTracker/1.0"
# Minimal payload: only keys read in ``_product_dict_to_food``.
OFF_LIBRARY_SEARCH_FIELDS = "product_name,brands,nutriments,code"


def _float_nutriment(nutriments: Dict[str, Any], key: str) -> float:
    raw = nutriments.get(key)
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _product_dict_to_food(product: Dict[str, Any]) -> Food | None:
    name = (product.get("product_name") or "").strip()
    if not name:
        return None
    raw_nut = product.get("nutriments")
    nutriments: Dict[str, Any] = raw_nut if isinstance(raw_nut, dict) else {}
    nutrition = NutritionInfo(
        calories=_float_nutriment(nutriments, "energy-kcal_100g"),
        protein_g=_float_nutriment(nutriments, "proteins_100g"),
        carbs_g=_float_nutriment(nutriments, "carbohydrates_100g"),
        fat_g=_float_nutriment(nutriments, "fat_100g"),
    )
    code = product.get("code") or product.get("barcode")
    brands = product.get("brands") or ""
    brand = brands.split(",")[0].strip() if brands else None
    return Food(
        id=str(uuid.uuid4()),
        name=name,
        barcode=str(code) if code else None,
        brand=brand,
        source="openfoodfacts",
        nutrition=nutrition,
        serving_size_g=100.0,
        created_by=None,
        updated_at=time.time(),
    )


def search_library(query: str) -> List[Food]:
    """Search Open Food Facts by name; returns up to 20 products as ``Food`` rows."""
    try:
        q = (query or "").strip()
        if not q:
            return []
        response = httpx.get(
            OFF_LIBRARY_SEARCH_URL,
            params={
                "search_terms": q,
                "json": "true",
                "page_size": 20,
                "sort_by": "unique_scans_n",
                "lang": "en",
                "action": "process",
                "fields": OFF_LIBRARY_SEARCH_FIELDS,
            },
            headers={"User-Agent": LIBRARY_USER_AGENT},
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        products = data.get("products") or []
        out: List[Food] = []
        for p in products:
            if not isinstance(p, dict):
                continue
            food = _product_dict_to_food(p)
            if food is not None:
                out.append(food)
        return out
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Open Food Facts library search failed: %s", exc)
        return []
