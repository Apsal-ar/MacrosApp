"""Dataclasses for user-created recipes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from models.food import NutritionInfo


@dataclass
class RecipeIngredient:
    """A single food component in a recipe.

    Attributes:
        id: UUID v4.
        recipe_id: Foreign key to the parent Recipe.
        food_id: Foreign key to the Food record.
        quantity_g: Weight of this ingredient in grams for the whole batch.
        updated_at: Unix timestamp.
        food_name: Denormalised display name.
        nutrition_per_100g: Denormalised per-100g values for offline scaling.
    """

    id: str
    recipe_id: str
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
        """Return macros scaled to the ingredient's quantity_g."""
        return self.nutrition_per_100g.scale(self.quantity_g)


@dataclass
class Recipe:
    """A user-created collection of foods representing a multi-ingredient dish.

    Macros are computed from the sum of all ingredients divided by servings,
    allowing users to log a recipe by number of servings rather than individual foods.

    Attributes:
        id: UUID v4.
        profile_id: Owning user's profile UUID.
        name: Display name for the recipe.
        servings: How many equal servings the full batch yields.
        ingredients: Eagerly loaded list of RecipeIngredient.
        updated_at: Unix timestamp.
    """

    id: str
    profile_id: str
    name: str
    servings: int = 1
    ingredients: List[RecipeIngredient] = field(default_factory=list)
    updated_at: float = 0.0

    @property
    def total_nutrition(self) -> NutritionInfo:
        """Sum of scaled nutrition across all ingredients (full batch)."""
        totals = NutritionInfo()
        for ingredient in self.ingredients:
            scaled = ingredient.scaled_nutrition
            totals.calories += scaled.calories
            totals.protein_g += scaled.protein_g
            totals.carbs_g += scaled.carbs_g
            totals.fat_g += scaled.fat_g
            if scaled.fiber_g is not None:
                totals.fiber_g = (totals.fiber_g or 0.0) + scaled.fiber_g
            if scaled.sugar_g is not None:
                totals.sugar_g = (totals.sugar_g or 0.0) + scaled.sugar_g
            if scaled.sodium_mg is not None:
                totals.sodium_mg = (totals.sodium_mg or 0.0) + scaled.sodium_mg
        return totals

    @property
    def per_serving_nutrition(self) -> NutritionInfo:
        """Nutrition values for a single serving of the recipe.

        Returns:
            NutritionInfo scaled to one serving; returns zero-filled if
            servings is 0 to avoid division by zero.
        """
        if self.servings <= 0:
            return NutritionInfo()
        total = self.total_nutrition
        factor = 1.0 / self.servings
        return NutritionInfo(
            calories=total.calories * factor,
            protein_g=total.protein_g * factor,
            carbs_g=total.carbs_g * factor,
            fat_g=total.fat_g * factor,
            fiber_g=total.fiber_g * factor if total.fiber_g is not None else None,
            sugar_g=total.sugar_g * factor if total.sugar_g is not None else None,
            sodium_mg=total.sodium_mg * factor if total.sodium_mg is not None else None,
        )
