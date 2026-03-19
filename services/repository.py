"""Repository pattern — direct Supabase PostgreSQL CRUD for all domain entities.

All reads and writes go directly to the remote Supabase database.
No local caching or offline support.

Call Repository.set_client(supabase) once at app startup before any
repository method is invoked.

Domain repositories:
  ProfileRepository, GoalsRepository, FoodRepository,
  MealRepository, MealItemRepository, RecipeRepository
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from models.user import Profile, Goals
from models.food import Food, NutritionInfo
from models.meal import Meal, MealItem
from models.recipe import Recipe, RecipeIngredient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base Repository
# ---------------------------------------------------------------------------

class Repository:
    """Abstract base providing the shared Supabase client reference.

    Subclasses call self._table(name) to obtain a Supabase table handle.
    If the client has not been initialised, all reads return empty/None and
    all writes are silently skipped.
    """

    _supabase: Optional[Any] = None

    @classmethod
    def set_client(cls, client: Any) -> None:
        """Attach the Supabase client for all repositories.

        Args:
            client: An initialised supabase-py Client instance (or None).
        """
        cls._supabase = client

    def _table(self, name: str) -> Optional[Any]:
        if self._supabase is None:
            return None
        return self._supabase.table(name)

    @staticmethod
    def new_id() -> str:
        """Generate a new UUID v4 string for use as a primary key."""
        return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# ProfileRepository
# ---------------------------------------------------------------------------

class ProfileRepository(Repository):
    """CRUD for the profiles table."""

    def get(self, profile_id: str) -> Optional[Profile]:
        """Fetch a single Profile by its UUID."""
        tbl = self._table("profiles")
        if tbl is None:
            return None
        response = tbl.select("*").eq("id", profile_id).execute()
        if not response.data:
            return None
        return self._row_to_profile(response.data[0])

    def save(self, profile: Profile) -> None:
        """Upsert a Profile to Supabase."""
        tbl = self._table("profiles")
        if tbl is None:
            return
        payload = self._profile_to_dict(profile)
        try:
            tbl.upsert(payload).execute()
        except Exception as exc:  # pylint: disable=broad-except
            # Backward-compatibility fallback for remote schemas that have not
            # yet added body-fat columns.
            message = str(exc)
            optional_cols = ("waist_cm", "neck_cm", "hips_cm", "body_fat_pct")
            missing_optional_col = any(
                f"'{col}'" in message and "profiles" in message for col in optional_cols
            )
            if not missing_optional_col:
                raise
            legacy_payload = {k: v for k, v in payload.items() if k not in optional_cols}
            tbl.upsert(legacy_payload).execute()
            logger.warning(
                "profiles table missing body-fat columns; saved profile without %s",
                ", ".join(optional_cols),
            )

    def _profile_to_dict(self, p: Profile) -> Dict[str, Any]:
        return {
            "id": p.id,
            "email": p.email,
            "height_cm": p.height_cm,
            "weight_kg": p.weight_kg,
            "age": p.age,
            "sex": p.sex,
            "activity": p.activity,
            "goal": p.goal,
            "unit_system": p.unit_system,
            "waist_cm": p.waist_cm,
            "neck_cm": p.neck_cm,
            "hips_cm": p.hips_cm,
            "body_fat_pct": p.body_fat_pct,
            "updated_at": p.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_profile(row: Dict[str, Any]) -> Profile:
        return Profile(
            id=row["id"],
            email=row.get("email") or "",
            height_cm=row.get("height_cm"),
            weight_kg=row.get("weight_kg"),
            age=row.get("age"),
            sex=row.get("sex"),
            activity=row.get("activity"),
            goal=row.get("goal"),
            unit_system=row.get("unit_system") or "metric",
            waist_cm=row.get("waist_cm"),
            neck_cm=row.get("neck_cm"),
            hips_cm=row.get("hips_cm"),
            body_fat_pct=row.get("body_fat_pct"),
            updated_at=row.get("updated_at") or 0.0,
        )


# ---------------------------------------------------------------------------
# GoalsRepository
# ---------------------------------------------------------------------------

class GoalsRepository(Repository):
    """CRUD for the goals table."""

    def get_for_profile(self, profile_id: str) -> Optional[Goals]:
        """Fetch the most recent Goals record for a given profile."""
        tbl = self._table("goals")
        if tbl is None:
            return None
        response = (
            tbl.select("*")
            .eq("profile_id", profile_id)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return self._row_to_goals(response.data[0])

    def save(self, goals: Goals) -> None:
        """Upsert a Goals record to Supabase."""
        tbl = self._table("goals")
        if tbl is None:
            return
        payload = self._goals_to_dict(goals)
        try:
            tbl.upsert(payload).execute()
        except Exception as exc:  # pylint: disable=broad-except
            if "meal_labels" in str(exc) and "schema" in str(exc).lower():
                payload.pop("meal_labels", None)
                tbl.upsert(payload).execute()
                logger.warning("goals table missing meal_labels column; saved without it")
            else:
                raise

    def _goals_to_dict(self, g: Goals) -> Dict[str, Any]:
        out = {
            "id": g.id,
            "profile_id": g.profile_id,
            "protein_pct": g.protein_pct,
            "carbs_pct": g.carbs_pct,
            "fat_pct": g.fat_pct,
            "diet_type": g.diet_type,
            "meals_per_day": g.meals_per_day,
            "calorie_target": g.calorie_target,
            "updated_at": g.updated_at or time.time(),
        }
        if g.meal_labels is not None:
            out["meal_labels"] = json.dumps(
                {str(k): v for k, v in g.meal_labels.items()}
            )
        return out

    @staticmethod
    def _row_to_goals(row: Dict[str, Any]) -> Goals:
        meal_labels_raw = row.get("meal_labels")
        meal_labels: Optional[Dict[int, str]] = None
        if meal_labels_raw:
            try:
                d = json.loads(meal_labels_raw)
                meal_labels = {int(k): str(v) for k, v in d.items()}
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        return Goals(
            id=row["id"],
            profile_id=row["profile_id"],
            protein_pct=row.get("protein_pct") or 30.0,
            carbs_pct=row.get("carbs_pct") or 40.0,
            fat_pct=row.get("fat_pct") or 30.0,
            diet_type=row.get("diet_type") or "balanced",
            meals_per_day=row.get("meals_per_day") or 3,
            meal_labels=meal_labels,
            calorie_target=row.get("calorie_target"),
            updated_at=row.get("updated_at") or 0.0,
        )


# ---------------------------------------------------------------------------
# FoodRepository
# ---------------------------------------------------------------------------

class FoodRepository(Repository):
    """CRUD and search for the foods table."""

    def get(self, food_id: str) -> Optional[Food]:
        """Fetch a single Food by its UUID."""
        tbl = self._table("foods")
        if tbl is None:
            return None
        response = tbl.select("*").eq("id", food_id).execute()
        if not response.data:
            return None
        return self._row_to_food(response.data[0])

    def get_by_barcode(self, barcode: str) -> Optional[Food]:
        """Look up a food by its EAN-13/UPC-A barcode."""
        tbl = self._table("foods")
        if tbl is None:
            return None
        response = tbl.select("*").eq("barcode", barcode).limit(1).execute()
        if not response.data:
            return None
        return self._row_to_food(response.data[0])

    def search(self, query: str, profile_id: Optional[str] = None, limit: int = 20) -> List[Food]:
        """Search foods by name/brand with optional user-scoping.

        When profile_id is provided, results are filtered client-side to only
        include Open Food Facts entries and the user's own manual foods.
        """
        tbl = self._table("foods")
        if tbl is None:
            return []
        pattern = f"%{query}%"
        response = (
            tbl.select("*")
            .or_(f"name.ilike.{pattern},brand.ilike.{pattern}")
            .order("name")
            .limit(100)
            .execute()
        )
        foods = [self._row_to_food(r) for r in response.data]
        if profile_id:
            foods = [
                f for f in foods
                if f.source == "openfoodfacts" or f.created_by == profile_id
            ]
        return foods[:limit]

    def get_manual_foods(self, profile_id: str) -> List[Food]:
        """Return all user-created manual foods for a profile."""
        tbl = self._table("foods")
        if tbl is None:
            return []
        response = (
            tbl.select("*")
            .eq("source", "manual")
            .eq("created_by", profile_id)
            .order("name")
            .execute()
        )
        return [self._row_to_food(r) for r in response.data]

    def save(self, food: Food) -> None:
        """Upsert a Food record to Supabase."""
        tbl = self._table("foods")
        if tbl is None:
            return
        tbl.upsert(self._food_to_dict(food)).execute()

    def delete(self, food_id: str) -> None:
        """Delete a Food record from Supabase."""
        tbl = self._table("foods")
        if tbl is None:
            return
        tbl.delete().eq("id", food_id).execute()

    def _food_to_dict(self, f: Food) -> Dict[str, Any]:
        n = f.nutrition
        return {
            "id": f.id,
            "barcode": f.barcode,
            "name": f.name,
            "brand": f.brand,
            "source": f.source,
            "calories": n.calories if n else None,
            "protein_g": n.protein_g if n else None,
            "carbs_g": n.carbs_g if n else None,
            "fat_g": n.fat_g if n else None,
            "fiber_g": n.fiber_g if n else None,
            "sugar_g": n.sugar_g if n else None,
            "sodium_mg": n.sodium_mg if n else None,
            "serving_size_g": f.serving_size_g,
            "created_by": f.created_by,
            "updated_at": f.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_food(row: Dict[str, Any]) -> Food:
        nutrition = NutritionInfo(
            calories=row.get("calories") or 0.0,
            protein_g=row.get("protein_g") or 0.0,
            carbs_g=row.get("carbs_g") or 0.0,
            fat_g=row.get("fat_g") or 0.0,
            fiber_g=row.get("fiber_g"),
            sugar_g=row.get("sugar_g"),
            sodium_mg=row.get("sodium_mg"),
        )
        return Food(
            id=row["id"],
            name=row["name"],
            barcode=row.get("barcode"),
            brand=row.get("brand"),
            source=row.get("source") or "manual",
            nutrition=nutrition,
            serving_size_g=row.get("serving_size_g") or 100.0,
            created_by=row.get("created_by"),
            updated_at=row.get("updated_at") or 0.0,
        )


# ---------------------------------------------------------------------------
# MealRepository
# ---------------------------------------------------------------------------

class MealRepository(Repository):
    """CRUD for the meals table."""

    def get_meals_for_date(self, profile_id: str, date: str) -> List[Meal]:
        """Fetch all meal slots for a given profile and date."""
        tbl = self._table("meals")
        if tbl is None:
            return []
        response = (
            tbl.select("*")
            .eq("profile_id", profile_id)
            .eq("date", date)
            .order("meal_number")
            .execute()
        )
        return [self._row_to_meal(r) for r in response.data]

    def get_all_meals(self, profile_id: str) -> List[Meal]:
        """Fetch every meal for a profile, ordered by date and slot."""
        tbl = self._table("meals")
        if tbl is None:
            return []
        response = (
            tbl.select("*")
            .eq("profile_id", profile_id)
            .order("date")
            .order("meal_number")
            .execute()
        )
        return [self._row_to_meal(r) for r in response.data]

    def get_or_create(self, profile_id: str, date: str, meal_number: int, label: str) -> Meal:
        """Return an existing meal slot or create one if it doesn't exist."""
        tbl = self._table("meals")
        if tbl is not None:
            response = (
                tbl.select("*")
                .eq("profile_id", profile_id)
                .eq("date", date)
                .eq("meal_number", meal_number)
                .execute()
            )
            if response.data:
                return self._row_to_meal(response.data[0])
        meal = Meal(
            id=self.new_id(),
            profile_id=profile_id,
            date=date,
            meal_number=meal_number,
            label=label,
            updated_at=time.time(),
        )
        self.save(meal)
        return meal

    def save(self, meal: Meal) -> None:
        """Upsert a Meal record to Supabase."""
        tbl = self._table("meals")
        if tbl is None:
            return
        tbl.upsert(self._meal_to_dict(meal)).execute()

    def delete(self, meal_id: str) -> None:
        """Delete a Meal from Supabase (cascade to meal_items via FK)."""
        tbl = self._table("meals")
        if tbl is None:
            return
        tbl.delete().eq("id", meal_id).execute()

    def _meal_to_dict(self, m: Meal) -> Dict[str, Any]:
        return {
            "id": m.id,
            "profile_id": m.profile_id,
            "date": m.date,
            "meal_number": m.meal_number,
            "label": m.label,
            "updated_at": m.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_meal(row: Dict[str, Any]) -> Meal:
        return Meal(
            id=row["id"],
            profile_id=row["profile_id"],
            date=row["date"],
            meal_number=row["meal_number"],
            label=row.get("label") or "",
            updated_at=row.get("updated_at") or 0.0,
        )


# ---------------------------------------------------------------------------
# MealItemRepository
# ---------------------------------------------------------------------------

class MealItemRepository(Repository):
    """CRUD for the meal_items table with denormalised food data."""

    _ITEM_SELECT = (
        "id, meal_id, food_id, quantity_g, updated_at, "
        "foods(name, calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g, sodium_mg)"
    )

    def get_items_for_meal(self, meal_id: str) -> List[MealItem]:
        """Fetch all food entries for a meal, with nutrition from a FK join."""
        tbl = self._table("meal_items")
        if tbl is None:
            return []
        response = (
            tbl.select(self._ITEM_SELECT)
            .eq("meal_id", meal_id)
            .execute()
        )
        return [self._row_to_item(r) for r in response.data]

    def save(self, item: MealItem) -> None:
        """Upsert a MealItem to Supabase."""
        tbl = self._table("meal_items")
        if tbl is None:
            return
        tbl.upsert(self._item_to_dict(item)).execute()

    def delete(self, item_id: str) -> None:
        """Delete a MealItem from Supabase."""
        tbl = self._table("meal_items")
        if tbl is None:
            return
        tbl.delete().eq("id", item_id).execute()

    def _item_to_dict(self, i: MealItem) -> Dict[str, Any]:
        return {
            "id": i.id,
            "meal_id": i.meal_id,
            "food_id": i.food_id,
            "quantity_g": i.quantity_g,
            "updated_at": i.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_item(row: Dict[str, Any]) -> MealItem:
        food_data = row.get("foods") or {}
        nutrition = NutritionInfo(
            calories=food_data.get("calories") or 0.0,
            protein_g=food_data.get("protein_g") or 0.0,
            carbs_g=food_data.get("carbs_g") or 0.0,
            fat_g=food_data.get("fat_g") or 0.0,
            fiber_g=food_data.get("fiber_g"),
            sugar_g=food_data.get("sugar_g"),
            sodium_mg=food_data.get("sodium_mg"),
        )
        return MealItem(
            id=row["id"],
            meal_id=row["meal_id"],
            food_id=row["food_id"],
            quantity_g=row["quantity_g"],
            updated_at=row.get("updated_at") or 0.0,
            food_name=food_data.get("name") or "",
            nutrition_per_100g=nutrition,
        )


# ---------------------------------------------------------------------------
# RecipeRepository
# ---------------------------------------------------------------------------

class RecipeRepository(Repository):
    """CRUD for recipes and their ingredients."""

    _INGREDIENT_SELECT = (
        "id, recipe_id, food_id, quantity_g, updated_at, "
        "foods(name, calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g, sodium_mg)"
    )

    def get_recipes_for_profile(self, profile_id: str) -> List[Recipe]:
        """Fetch all recipes belonging to a profile, with ingredients."""
        tbl = self._table("recipes")
        if tbl is None:
            return []
        response = (
            tbl.select("*")
            .eq("profile_id", profile_id)
            .order("name")
            .execute()
        )
        recipes = [self._row_to_recipe(r) for r in response.data]
        for recipe in recipes:
            recipe.ingredients = self._load_ingredients(recipe.id)
        return recipes

    def get(self, recipe_id: str) -> Optional[Recipe]:
        """Fetch a single Recipe with all its ingredients."""
        tbl = self._table("recipes")
        if tbl is None:
            return None
        response = tbl.select("*").eq("id", recipe_id).execute()
        if not response.data:
            return None
        recipe = self._row_to_recipe(response.data[0])
        recipe.ingredients = self._load_ingredients(recipe.id)
        return recipe

    def save(self, recipe: Recipe) -> None:
        """Upsert a Recipe to Supabase (does not save ingredients)."""
        tbl = self._table("recipes")
        if tbl is None:
            return
        tbl.upsert(self._recipe_to_dict(recipe)).execute()

    def delete(self, recipe_id: str) -> None:
        """Delete a Recipe from Supabase (cascade to ingredients via FK)."""
        tbl = self._table("recipes")
        if tbl is None:
            return
        tbl.delete().eq("id", recipe_id).execute()

    def save_ingredient(self, ingredient: RecipeIngredient) -> None:
        """Upsert a RecipeIngredient to Supabase."""
        tbl = self._table("recipe_ingredients")
        if tbl is None:
            return
        data = {
            "id": ingredient.id,
            "recipe_id": ingredient.recipe_id,
            "food_id": ingredient.food_id,
            "quantity_g": ingredient.quantity_g,
            "updated_at": ingredient.updated_at or time.time(),
        }
        tbl.upsert(data).execute()

    def delete_ingredient(self, ingredient_id: str) -> None:
        """Delete a RecipeIngredient from Supabase."""
        tbl = self._table("recipe_ingredients")
        if tbl is None:
            return
        tbl.delete().eq("id", ingredient_id).execute()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_ingredients(self, recipe_id: str) -> List[RecipeIngredient]:
        tbl = self._table("recipe_ingredients")
        if tbl is None:
            return []
        response = (
            tbl.select(self._INGREDIENT_SELECT)
            .eq("recipe_id", recipe_id)
            .execute()
        )
        return [self._row_to_ingredient(r) for r in response.data]

    @staticmethod
    def _row_to_ingredient(row: Dict[str, Any]) -> RecipeIngredient:
        food_data = row.get("foods") or {}
        return RecipeIngredient(
            id=row["id"],
            recipe_id=row["recipe_id"],
            food_id=row["food_id"],
            quantity_g=row["quantity_g"],
            updated_at=row.get("updated_at") or 0.0,
            food_name=food_data.get("name") or "",
            nutrition_per_100g=NutritionInfo(
                calories=food_data.get("calories") or 0.0,
                protein_g=food_data.get("protein_g") or 0.0,
                carbs_g=food_data.get("carbs_g") or 0.0,
                fat_g=food_data.get("fat_g") or 0.0,
                fiber_g=food_data.get("fiber_g"),
                sugar_g=food_data.get("sugar_g"),
                sodium_mg=food_data.get("sodium_mg"),
            ),
        )

    def _recipe_to_dict(self, r: Recipe) -> Dict[str, Any]:
        return {
            "id": r.id,
            "profile_id": r.profile_id,
            "name": r.name,
            "servings": r.servings,
            "updated_at": r.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_recipe(row: Dict[str, Any]) -> Recipe:
        return Recipe(
            id=row["id"],
            profile_id=row["profile_id"],
            name=row["name"],
            servings=row.get("servings") or 1,
            updated_at=row.get("updated_at") or 0.0,
        )
