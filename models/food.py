"""Dataclasses for food items and their nutritional information."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class NutritionInfo:
    """Per-100g macro and micro nutrient values for a food.

    All values are stored per 100g; quantity scaling is handled at the
    MealItem level using the quantity_g field.

    Attributes:
        calories: Energy in kcal per 100g.
        protein_g: Protein in grams per 100g.
        carbs_g: Total carbohydrates in grams per 100g.
        fat_g: Total fat in grams per 100g.
        fiber_g: Dietary fibre in grams per 100g (optional).
        sugar_g: Total sugars in grams per 100g (optional).
        fat_saturated_g: Saturated fatty acids, grams per 100g (optional).
        fat_trans_g: Trans fatty acids, grams per 100g (optional).
        fat_polyunsaturated_g: Polyunsaturated fatty acids, grams per 100g (optional).
        fat_monounsaturated_g: Monounsaturated fatty acids, grams per 100g (optional).
    """

    calories: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0
    fiber_g: Optional[float] = None
    sugar_g: Optional[float] = None
    fat_saturated_g: Optional[float] = None
    fat_trans_g: Optional[float] = None
    fat_polyunsaturated_g: Optional[float] = None
    fat_monounsaturated_g: Optional[float] = None

    def scale(self, quantity_g: float) -> "NutritionInfo":
        """Return a new NutritionInfo scaled to quantity_g from the 100g base.

        Args:
            quantity_g: Actual serving weight in grams.

        Returns:
            A new NutritionInfo instance with all values proportionally scaled.
        """
        factor = quantity_g / 100.0
        return NutritionInfo(
            calories=self.calories * factor,
            protein_g=self.protein_g * factor,
            carbs_g=self.carbs_g * factor,
            fat_g=self.fat_g * factor,
            fiber_g=self.fiber_g * factor if self.fiber_g is not None else None,
            sugar_g=self.sugar_g * factor if self.sugar_g is not None else None,
            fat_saturated_g=self.fat_saturated_g * factor
            if self.fat_saturated_g is not None
            else None,
            fat_trans_g=self.fat_trans_g * factor if self.fat_trans_g is not None else None,
            fat_polyunsaturated_g=self.fat_polyunsaturated_g * factor
            if self.fat_polyunsaturated_g is not None
            else None,
            fat_monounsaturated_g=self.fat_monounsaturated_g * factor
            if self.fat_monounsaturated_g is not None
            else None,
        )


@dataclass
class Food:
    """Represents a food product, either from Open Food Facts or user-created.

    Attributes:
        id: UUID v4, generated client-side for offline compatibility.
        name: Human-readable product name.
        barcode: EAN-13/UPC-A barcode string (None for manual foods).
        brand: Brand or manufacturer name.
        source: 'openfoodfacts' for API-sourced foods, 'manual' for user-created.
        nutrition: Per-100g nutritional values.
        serving_size_g: Suggested serving size in grams (default 100g).
        created_by: profile_id of the user who created a manual food (None for OFF).
        updated_at: Unix timestamp.
    """

    id: str
    name: str
    barcode: Optional[str] = None
    brand: Optional[str] = None
    source: str = "manual"             # 'openfoodfacts' | 'manual'
    nutrition: NutritionInfo = None    # type: ignore[assignment]
    serving_size_g: float = 100.0
    created_by: Optional[str] = None
    updated_at: float = 0.0

    def __post_init__(self) -> None:
        if self.nutrition is None:
            self.nutrition = NutritionInfo()
