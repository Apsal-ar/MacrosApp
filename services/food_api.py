"""Library food data: USDA Foundation snapshot (local JSON) + Open Food Facts barcode API."""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

import config
from models.food import Food, NutritionInfo

logger = logging.getLogger(__name__)

_OFF_PRODUCT_URL = "https://world.openfoodfacts.org/api/v0/product/{barcode}.json"

# Bundled USDA Foundation JSON (per 100 g). Calories: FDC uses several Energy rows (all kcal);
# match ``nutrient.id`` — first of 1008 / 2047 / 2048 wins. Other macros: exact names below.
_USDA_ENERGY_KCAL_NUTRIENT_IDS = frozenset({1008, 2047, 2048})
_USDA_NUTRIENT_PROTEIN_NAME = "Protein"
_USDA_NUTRIENT_CARBS_NAME = "Carbohydrate, by difference"
_USDA_NUTRIENT_FAT_NAME = "Total lipid (fat)"

_USDA_JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "Food_data_USDA_foundation.json"


def _load_usda_local() -> List[Dict[str, Any]]:
    """Load ``FoundationFoods`` from the bundled USDA JSON (offline)."""
    try:
        with _USDA_JSON_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
        raw = data.get("FoundationFoods") if isinstance(data, dict) else None
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    except OSError as exc:
        logger.warning("Could not read USDA foundation file %s: %s", _USDA_JSON_PATH, exc)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in USDA foundation file: %s", exc)
    return []


_FOUNDATION_FOODS: List[Dict[str, Any]] = _load_usda_local()
if _FOUNDATION_FOODS:
    logger.info("Loaded %s USDA Foundation foods from local file", len(_FOUNDATION_FOODS))


def _float_nutriment(nutriments: Dict[str, Any], key: str) -> float:
    raw = nutriments.get(key)
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _product_dict_to_food(product: Dict[str, Any]) -> Food | None:
    """Parse Open Food Facts product JSON (e.g. v0 product endpoint) into ``Food``."""
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


def _fdc_nutrients_to_info(food_nutrients: Any) -> NutritionInfo:
    """Map bundled USDA ``foodNutrients`` to per-100g macros (energy by ``nutrient.id``, others by name).

    Parsed amounts are clamped with ``max(0.0, amount)`` for calories, protein, carbs, and fat.
    """
    calories = protein_g = carbs_g = fat_g = 0.0
    have_calories = False
    if not isinstance(food_nutrients, list):
        return NutritionInfo(
            calories=0.0,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=0.0,
        )
    for fn in food_nutrients:
        if not isinstance(fn, dict):
            continue
        nut = fn.get("nutrient")
        if not isinstance(nut, dict):
            continue
        nname = nut.get("name")
        raw = fn.get("amount")
        if raw is None:
            raw = fn.get("value")
        try:
            val = float(raw) if raw is not None else 0.0
        except (TypeError, ValueError):
            continue
        val = max(0.0, val)
        nid = nut.get("id")
        try:
            nid_int = int(nid) if nid is not None else None
        except (TypeError, ValueError):
            nid_int = None
        if not have_calories and nid_int in _USDA_ENERGY_KCAL_NUTRIENT_IDS:
            calories = val
            have_calories = True
        elif nname == _USDA_NUTRIENT_PROTEIN_NAME:
            protein_g = val
        elif nname == _USDA_NUTRIENT_CARBS_NAME:
            carbs_g = val
        elif nname == _USDA_NUTRIENT_FAT_NAME:
            fat_g = val
    return NutritionInfo(
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )


def _fdc_item_to_food(item: Dict[str, Any]) -> Food | None:
    name = (item.get("description") or "").strip()
    if not name:
        return None
    nutrition = _fdc_nutrients_to_info(item.get("foodNutrients"))
    return Food(
        id=str(uuid.uuid4()),
        name=name,
        barcode=None,
        brand=None,
        source="usda",
        nutrition=nutrition,
        serving_size_g=100.0,
        created_by=None,
        updated_at=time.time(),
    )


def search_local(query: str) -> List[Food]:
    """Text search over the bundled USDA Foundation snapshot (offline, Library tab only)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    out: List[Food] = []
    for item in _FOUNDATION_FOODS:
        desc = (item.get("description") or "").lower()
        if q not in desc:
            continue
        food = _fdc_item_to_food(item)
        if food is not None:
            out.append(food)
    return out


def lookup_barcode(barcode: str) -> Optional[Food]:
    """Resolve a barcode via Open Food Facts API only (no USDA). Returns ``None`` if not found."""
    try:
        b = (barcode or "").strip()
        if not b:
            return None
        url = _OFF_PRODUCT_URL.format(barcode=b)
        response = httpx.get(
            url,
            headers={"User-Agent": config.OFF_USER_AGENT},
            timeout=20.0,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("status") != 1:
            return None
        product = data.get("product")
        if not isinstance(product, dict):
            return None
        return _product_dict_to_food(product)
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Open Food Facts barcode lookup failed for '%s': %s", barcode, exc)
        return None
