"""Food lookup service: local cache → Open Food Facts → manual entry fallback.

Search strategy:
  1. Query FoodRepository by name (local SQLite).
  2. If results < OFF_MIN_LOCAL_RESULTS, also query Open Food Facts.
  3. Merge results, deduplicate by barcode.
  4. Cache any new OFF results locally for future offline use.

Barcode lookup strategy:
  1. Check FoodRepository by barcode.
  2. If not found, query Open Food Facts by barcode.
  3. Cache and return; return None if not found anywhere.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import List, Optional

import config
from models.food import Food, NutritionInfo
from services.repository import FoodRepository

logger = logging.getLogger(__name__)


class FoodService:
    """Manages food lookups with local cache priority and OFF fallback."""

    def __init__(self) -> None:
        self._repo = FoodRepository()
        self._off_client = self._build_off_client()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, profile_id: str) -> List[Food]:
        """Search for foods by name with local-first, OFF-fallback strategy.

        Args:
            query: Free-text search term matched against name and brand.
            profile_id: Used to include the user's own manual foods.

        Returns:
            Merged, deduplicated list of Food dataclasses.
        """
        local_results = self._repo.search(query, profile_id=profile_id)

        if len(local_results) >= config.OFF_MIN_LOCAL_RESULTS:
            return local_results

        off_results = self._search_off(query)
        cached_off = [self._cache_off_food(f) for f in off_results]

        seen_barcodes: set[str] = {f.barcode for f in local_results if f.barcode}
        seen_ids: set[str] = {f.id for f in local_results}
        merged: List[Food] = list(local_results)
        for food in cached_off:
            if food.barcode and food.barcode in seen_barcodes:
                continue
            if food.id in seen_ids:
                continue
            merged.append(food)
            seen_barcodes.add(food.barcode or "")
            seen_ids.add(food.id)

        return merged

    def lookup_barcode(self, barcode: str, profile_id: str) -> Optional[Food]:  # noqa: ARG002
        """Look up a food by its EAN-13/UPC-A barcode string.

        Args:
            barcode: Barcode string decoded by BarcodeService.
            profile_id: Unused directly but reserved for future per-user caching.

        Returns:
            The matching Food dataclass, or None if not found anywhere.
        """
        food = self._repo.get_by_barcode(barcode)
        if food:
            return food

        off_food = self._lookup_off_barcode(barcode)
        if off_food:
            return self._cache_off_food(off_food)

        return None

    def save_manual_food(self, food: Food) -> Food:
        """Persist a user-created manual food entry.

        Args:
            food: A Food instance with source='manual' and created_by set.

        Returns:
            The saved Food (same object, id populated if missing).
        """
        if not food.id:
            food.id = str(uuid.uuid4())
        food.updated_at = time.time()
        self._repo.save(food)
        return food

    def delete_manual_food(self, food_id: str) -> None:
        """Remove a user-created manual food and queue a remote delete.

        Args:
            food_id: UUID of the food to delete.
        """
        self._repo.delete(food_id)

    def get_manual_foods(self, profile_id: str) -> List[Food]:
        """Return all user-created foods for display in the Settings screen.

        Args:
            profile_id: UUID of the owning profile.

        Returns:
            List of Food dataclasses with source='manual'.
        """
        return self._repo.get_manual_foods(profile_id)

    # ------------------------------------------------------------------
    # Open Food Facts helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_off_client() -> Optional[object]:
        """Initialise the openfoodfacts API client.

        Returns:
            openfoodfacts API object or None if the library is unavailable.
        """
        try:
            import openfoodfacts  # pylint: disable=import-outside-toplevel
            return openfoodfacts.API(
                user_agent=config.OFF_USER_AGENT,
            )
        except ImportError:
            logger.warning("openfoodfacts library not installed; OFF lookup disabled")
            return None

    def _search_off(self, query: str) -> List[Food]:
        """Query Open Food Facts text search endpoint.

        Args:
            query: Search term.

        Returns:
            List of Food dataclasses parsed from OFF response, possibly empty.
        """
        if self._off_client is None:
            return []
        try:
            result = self._off_client.product.text_search(
                query, page=1, page_size=config.OFF_SEARCH_MAX_RESULTS
            )
            products = getattr(result, "products", []) or []
            return [f for f in (self._off_product_to_food(p) for p in products) if f is not None]
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("OFF text search failed for '%s': %s", query, exc)
            return []

    def _lookup_off_barcode(self, barcode: str) -> Optional[Food]:
        """Query Open Food Facts by barcode.

        Args:
            barcode: EAN-13/UPC-A barcode string.

        Returns:
            A Food dataclass if found, else None.
        """
        if self._off_client is None:
            return None
        try:
            product = self._off_client.product.get(barcode)
            if product is None:
                return None
            return self._off_product_to_food(product)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("OFF barcode lookup failed for '%s': %s", barcode, exc)
            return None

    @staticmethod
    def _off_product_to_food(product: object) -> Optional[Food]:
        """Convert an openfoodfacts product object to a Food dataclass.

        Nutriment values are per 100g as stored in OFF.

        Args:
            product: An openfoodfacts product dict or object.

        Returns:
            Food dataclass, or None if the product lacks a name.
        """
        try:
            if isinstance(product, dict):
                p = product
            else:
                p = product.__dict__ if hasattr(product, "__dict__") else {}

            name = (
                p.get("product_name_en")
                or p.get("product_name")
                or ""
            ).strip()
            if not name:
                return None

            nutriments = p.get("nutriments", {}) or {}

            def _get(key: str) -> Optional[float]:
                val = nutriments.get(f"{key}_100g") or nutriments.get(key)
                try:
                    return float(val) if val is not None else None
                except (TypeError, ValueError):
                    return None

            nutrition = NutritionInfo(
                calories=_get("energy-kcal") or _get("energy") or 0.0,
                protein_g=_get("proteins") or 0.0,
                carbs_g=_get("carbohydrates") or 0.0,
                fat_g=_get("fat") or 0.0,
                fiber_g=_get("fiber"),
                sugar_g=_get("sugars"),
                sodium_mg=(_get("sodium") or 0.0) * 1000 if _get("sodium") is not None else None,
            )

            return Food(
                id=str(uuid.uuid4()),
                name=name,
                barcode=p.get("code") or p.get("barcode"),
                brand=p.get("brands", "").split(",")[0].strip() or None,
                source="openfoodfacts",
                nutrition=nutrition,
                serving_size_g=float(p.get("serving_size", 100) or 100),
                created_by=None,
                updated_at=time.time(),
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.debug("Could not parse OFF product: %s", exc)
            return None

    def _cache_off_food(self, food: Food) -> Food:
        """Save an OFF-sourced food to the local cache if not already present.

        Skip if the barcode is already cached to avoid duplication.

        Args:
            food: Food dataclass with source='openfoodfacts'.

        Returns:
            The cached Food (may have its id updated if a conflict was found).
        """
        if food.barcode:
            existing = self._repo.get_by_barcode(food.barcode)
            if existing:
                return existing
        self._repo.save(food)
        return food
