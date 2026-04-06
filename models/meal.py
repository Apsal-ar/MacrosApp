"""Dataclasses for daily meal log entries."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from models.food import NutritionInfo


@dataclass
class MealItem:
    """A single food entry within a meal slot.

    Attributes:
        id: UUID v4.
        meal_id: Foreign key to the parent Meal.
        food_id: Foreign key to the Food record.
        quantity_g: Actual consumed weight in grams; used to scale nutrition.
        updated_at: Unix timestamp.
        food_name: Denormalised display name (populated by repository joins).
        nutrition_per_100g: Denormalised per-100g values for offline scaling.
    """

    id: str
    meal_id: str
    food_id: str
    quantity_g: float = 100.0
    updated_at: float = 0.0
    food_name: str = ""
    nutrition_per_100g: NutritionInfo = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.nutrition_per_100g is None:
            self.nutrition_per_100g = NutritionInfo()

    @property
    def scaled_nutrition(self) -> NutritionInfo:
        """Return macros scaled to the actual quantity_g consumed."""
        return self.nutrition_per_100g.scale(self.quantity_g)


@dataclass
class Meal:
    """Represents one named meal slot for a given date.

    The unique constraint (profile_id, date, meal_number) is enforced at the
    database level; the repository handles upsert logic on the client.

    Attributes:
        id: UUID v4.
        profile_id: Owning user's profile UUID.
        date: ISO-8601 date string, e.g. '2026-03-15'.
        meal_number: 1-based index within the day (1 = first meal).
        label: User-editable display name, e.g. 'Breakfast'.
        items: Eagerly loaded list of MealItem (populated by repository).
        updated_at: Unix timestamp.
    """

    id: str
    profile_id: str
    date: str
    meal_number: int
    label: str = ""
    items: List[MealItem] = field(default_factory=list)
    updated_at: float = 0.0

    @property
    def total_nutrition(self) -> NutritionInfo:
        """Sum of scaled nutrition across all items in this meal."""
        totals = NutritionInfo()
        for item in self.items:
            scaled = item.scaled_nutrition
            totals.calories += scaled.calories
            totals.protein_g += scaled.protein_g
            totals.carbs_g += scaled.carbs_g
            totals.fat_g += scaled.fat_g
            if scaled.fiber_g is not None:
                totals.fiber_g = (totals.fiber_g or 0.0) + scaled.fiber_g
            if scaled.sugar_g is not None:
                totals.sugar_g = (totals.sugar_g or 0.0) + scaled.sugar_g
            if scaled.salt_mg is not None:
                totals.salt_mg = (totals.salt_mg or 0.0) + scaled.salt_mg
        return totals
