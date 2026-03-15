"""Repository pattern — offline-first CRUD for all domain entities.

Write flow:
  1. Write locally to SQLite (instant, UI never waits for network).
  2. Enqueue the operation for deferred push to Supabase.
  3. Mark the row sync_status='pending'.

Read flow:
  - Always read from SQLite cache; Supabase data arrives via SyncManager pull.

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

from sync.cache_db import CacheDB
from sync.sync_queue import SyncQueue
from models.user import Profile, Goals
from models.food import Food, NutritionInfo
from models.meal import Meal, MealItem
from models.recipe import Recipe, RecipeIngredient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base Repository
# ---------------------------------------------------------------------------

class Repository:
    """Abstract base providing common offline-first write helpers.

    Subclasses define _TABLE_NAME and call _save_row / _delete_row.
    All reads are performed directly in subclasses using _db.connection().
    """

    _TABLE_NAME: str = ""

    def __init__(self) -> None:
        self._db = CacheDB.get_instance()
        self._queue = SyncQueue()

    # ------------------------------------------------------------------
    # Protected write helpers
    # ------------------------------------------------------------------

    def _save_row(self, row: Dict[str, Any], operation: str = "insert") -> None:
        """Upsert a row into the local cache and enqueue it for sync.

        Args:
            row: Dict mapping column names to values; must contain 'id'.
            operation: 'insert' or 'update' — passed verbatim to SyncQueue.
        """
        row = {**row, "sync_status": "pending", "updated_at": row.get("updated_at", time.time())}
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" * len(row))
        conn = self._db.connection()
        conn.execute(
            f"INSERT OR REPLACE INTO {self._TABLE_NAME} ({cols}) VALUES ({placeholders})",  # noqa: S608
            list(row.values()),
        )
        conn.commit()
        self._queue.enqueue(self._TABLE_NAME, row["id"], operation, row)

    def _delete_row(self, row_id: str) -> None:
        """Delete a row from the local cache and enqueue a delete op.

        Args:
            row_id: UUID primary key of the row to remove.
        """
        conn = self._db.connection()
        conn.execute(
            f"DELETE FROM {self._TABLE_NAME} WHERE id = ?", (row_id,)  # noqa: S608
        )
        conn.commit()
        self._queue.enqueue(self._TABLE_NAME, row_id, "delete", {"id": row_id})

    @staticmethod
    def new_id() -> str:
        """Generate a new UUID v4 string for use as a primary key.

        Returns:
            A UUID4 string, e.g. '550e8400-e29b-41d4-a716-446655440000'.
        """
        return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# ProfileRepository
# ---------------------------------------------------------------------------

class ProfileRepository(Repository):
    """CRUD for the profiles table."""

    _TABLE_NAME = "profiles"

    def get(self, profile_id: str) -> Optional[Profile]:
        """Fetch a single Profile by its UUID.

        Args:
            profile_id: UUID of the profile to retrieve.

        Returns:
            A Profile dataclass, or None if not found.
        """
        conn = self._db.connection()
        row = conn.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        ).fetchone()
        return self._row_to_profile(row) if row else None

    def save(self, profile: Profile) -> None:
        """Insert or update a Profile in the local cache.

        Args:
            profile: The Profile instance to persist.
        """
        self._save_row(self._profile_to_dict(profile))

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
            "updated_at": p.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_profile(row: Any) -> Profile:
        return Profile(
            id=row["id"],
            email=row["email"] or "",
            height_cm=row["height_cm"],
            weight_kg=row["weight_kg"],
            age=row["age"],
            sex=row["sex"],
            activity=row["activity"],
            goal=row["goal"],
            unit_system=row["unit_system"] or "metric",
            updated_at=row["updated_at"] or 0.0,
        )


# ---------------------------------------------------------------------------
# GoalsRepository
# ---------------------------------------------------------------------------

class GoalsRepository(Repository):
    """CRUD for the goals table."""

    _TABLE_NAME = "goals"

    def get_for_profile(self, profile_id: str) -> Optional[Goals]:
        """Fetch the Goals record for a given profile.

        Args:
            profile_id: UUID of the owning profile.

        Returns:
            A Goals dataclass, or None if not yet created.
        """
        conn = self._db.connection()
        row = conn.execute(
            "SELECT * FROM goals WHERE profile_id = ? ORDER BY updated_at DESC LIMIT 1",
            (profile_id,),
        ).fetchone()
        return self._row_to_goals(row) if row else None

    def save(self, goals: Goals) -> None:
        """Insert or update a Goals record.

        Args:
            goals: The Goals instance to persist.
        """
        self._save_row(self._goals_to_dict(goals))

    def _goals_to_dict(self, g: Goals) -> Dict[str, Any]:
        return {
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

    @staticmethod
    def _row_to_goals(row: Any) -> Goals:
        return Goals(
            id=row["id"],
            profile_id=row["profile_id"],
            protein_pct=row["protein_pct"],
            carbs_pct=row["carbs_pct"],
            fat_pct=row["fat_pct"],
            diet_type=row["diet_type"] or "balanced",
            meals_per_day=row["meals_per_day"] or 3,
            calorie_target=row["calorie_target"],
            updated_at=row["updated_at"] or 0.0,
        )


# ---------------------------------------------------------------------------
# FoodRepository
# ---------------------------------------------------------------------------

class FoodRepository(Repository):
    """CRUD and search for the foods table."""

    _TABLE_NAME = "foods"

    def get(self, food_id: str) -> Optional[Food]:
        """Fetch a single Food by its UUID.

        Args:
            food_id: UUID of the food to retrieve.

        Returns:
            A Food dataclass, or None if not found.
        """
        conn = self._db.connection()
        row = conn.execute("SELECT * FROM foods WHERE id = ?", (food_id,)).fetchone()
        return self._row_to_food(row) if row else None

    def get_by_barcode(self, barcode: str) -> Optional[Food]:
        """Look up a food by its EAN-13/UPC-A barcode.

        Args:
            barcode: The barcode string to search for.

        Returns:
            The matching Food, or None if not cached locally.
        """
        conn = self._db.connection()
        row = conn.execute(
            "SELECT * FROM foods WHERE barcode = ? LIMIT 1", (barcode,)
        ).fetchone()
        return self._row_to_food(row) if row else None

    def search(self, query: str, profile_id: Optional[str] = None, limit: int = 20) -> List[Food]:
        """Full-text name search over locally cached foods.

        Searches both global Open Food Facts cache and user-created foods.

        Args:
            query: Search term matched against food name and brand.
            profile_id: When provided, also includes that user's manual foods.
            limit: Maximum results to return.

        Returns:
            List of matching Food dataclasses ordered by relevance (name match first).
        """
        conn = self._db.connection()
        pattern = f"%{query}%"
        if profile_id:
            rows = conn.execute(
                """
                SELECT * FROM foods
                WHERE (name LIKE ? OR brand LIKE ?)
                  AND (source = 'openfoodfacts' OR created_by = ?)
                ORDER BY
                    CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                    name
                LIMIT ?
                """,
                (pattern, pattern, profile_id, f"{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM foods
                WHERE name LIKE ? OR brand LIKE ?
                ORDER BY
                    CASE WHEN name LIKE ? THEN 0 ELSE 1 END,
                    name
                LIMIT ?
                """,
                (pattern, pattern, f"{query}%", limit),
            ).fetchall()
        return [self._row_to_food(r) for r in rows]

    def get_manual_foods(self, profile_id: str) -> List[Food]:
        """Return all user-created manual foods for a profile.

        Args:
            profile_id: UUID of the owning profile.

        Returns:
            List of Food dataclasses with source='manual'.
        """
        conn = self._db.connection()
        rows = conn.execute(
            "SELECT * FROM foods WHERE source = 'manual' AND created_by = ? ORDER BY name",
            (profile_id,),
        ).fetchall()
        return [self._row_to_food(r) for r in rows]

    def save(self, food: Food) -> None:
        """Insert or update a Food record.

        Args:
            food: The Food instance to persist.
        """
        self._save_row(self._food_to_dict(food))

    def delete(self, food_id: str) -> None:
        """Remove a Food from the local cache and queue a remote delete.

        Args:
            food_id: UUID of the food to delete.
        """
        self._delete_row(food_id)

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
    def _row_to_food(row: Any) -> Food:
        nutrition = NutritionInfo(
            calories=row["calories"] or 0.0,
            protein_g=row["protein_g"] or 0.0,
            carbs_g=row["carbs_g"] or 0.0,
            fat_g=row["fat_g"] or 0.0,
            fiber_g=row["fiber_g"],
            sugar_g=row["sugar_g"],
            sodium_mg=row["sodium_mg"],
        )
        return Food(
            id=row["id"],
            name=row["name"],
            barcode=row["barcode"],
            brand=row["brand"],
            source=row["source"] or "manual",
            nutrition=nutrition,
            serving_size_g=row["serving_size_g"] or 100.0,
            created_by=row["created_by"],
            updated_at=row["updated_at"] or 0.0,
        )


# ---------------------------------------------------------------------------
# MealRepository
# ---------------------------------------------------------------------------

class MealRepository(Repository):
    """CRUD for the meals table. MealItems are managed by MealItemRepository."""

    _TABLE_NAME = "meals"

    def get_meals_for_date(self, profile_id: str, date: str) -> List[Meal]:
        """Fetch all meal slots for a given profile and date.

        Args:
            profile_id: UUID of the profile.
            date: ISO-8601 date string, e.g. '2026-03-15'.

        Returns:
            List of Meal dataclasses ordered by meal_number; items list is empty
            (populate via MealItemRepository.get_items_for_meal if needed).
        """
        conn = self._db.connection()
        rows = conn.execute(
            """
            SELECT * FROM meals
            WHERE profile_id = ? AND date = ?
            ORDER BY meal_number
            """,
            (profile_id, date),
        ).fetchall()
        return [self._row_to_meal(r) for r in rows]

    def get_or_create(self, profile_id: str, date: str, meal_number: int, label: str) -> Meal:
        """Return an existing meal slot or create one if it doesn't exist.

        Args:
            profile_id: UUID of the profile.
            date: ISO-8601 date string.
            meal_number: 1-based meal slot index.
            label: Display label, e.g. 'Breakfast'.

        Returns:
            The existing or newly created Meal.
        """
        conn = self._db.connection()
        row = conn.execute(
            """
            SELECT * FROM meals
            WHERE profile_id = ? AND date = ? AND meal_number = ?
            """,
            (profile_id, date, meal_number),
        ).fetchone()
        if row:
            return self._row_to_meal(row)
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
        """Insert or update a Meal record.

        Args:
            meal: The Meal instance to persist.
        """
        self._save_row(self._meal_to_dict(meal))

    def delete(self, meal_id: str) -> None:
        """Remove a Meal and cascade-delete its MealItems.

        SQLite enforces the cascade via the foreign key constraint.

        Args:
            meal_id: UUID of the meal to delete.
        """
        self._delete_row(meal_id)

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
    def _row_to_meal(row: Any) -> Meal:
        return Meal(
            id=row["id"],
            profile_id=row["profile_id"],
            date=row["date"],
            meal_number=row["meal_number"],
            label=row["label"] or "",
            updated_at=row["updated_at"] or 0.0,
        )


# ---------------------------------------------------------------------------
# MealItemRepository
# ---------------------------------------------------------------------------

class MealItemRepository(Repository):
    """CRUD for the meal_items table with denormalised food data."""

    _TABLE_NAME = "meal_items"

    def get_items_for_meal(self, meal_id: str) -> List[MealItem]:
        """Fetch all food entries for a given meal, with nutrition joined.

        Args:
            meal_id: UUID of the parent Meal.

        Returns:
            List of MealItem dataclasses with food_name and nutrition_per_100g populated.
        """
        conn = self._db.connection()
        rows = conn.execute(
            """
            SELECT
                mi.id, mi.meal_id, mi.food_id, mi.quantity_g, mi.updated_at,
                f.name   AS food_name,
                f.calories, f.protein_g, f.carbs_g, f.fat_g,
                f.fiber_g, f.sugar_g, f.sodium_mg
            FROM meal_items mi
            JOIN foods f ON f.id = mi.food_id
            WHERE mi.meal_id = ?
            ORDER BY mi.rowid
            """,
            (meal_id,),
        ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def save(self, item: MealItem) -> None:
        """Insert or update a MealItem.

        Args:
            item: The MealItem to persist.
        """
        self._save_row(self._item_to_dict(item))

    def delete(self, item_id: str) -> None:
        """Remove a MealItem from the local cache and queue a remote delete.

        Args:
            item_id: UUID of the MealItem to delete.
        """
        self._delete_row(item_id)

    def _item_to_dict(self, i: MealItem) -> Dict[str, Any]:
        return {
            "id": i.id,
            "meal_id": i.meal_id,
            "food_id": i.food_id,
            "quantity_g": i.quantity_g,
            "updated_at": i.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_item(row: Any) -> MealItem:
        nutrition = NutritionInfo(
            calories=row["calories"] or 0.0,
            protein_g=row["protein_g"] or 0.0,
            carbs_g=row["carbs_g"] or 0.0,
            fat_g=row["fat_g"] or 0.0,
            fiber_g=row["fiber_g"],
            sugar_g=row["sugar_g"],
            sodium_mg=row["sodium_mg"],
        )
        return MealItem(
            id=row["id"],
            meal_id=row["meal_id"],
            food_id=row["food_id"],
            quantity_g=row["quantity_g"],
            updated_at=row["updated_at"] or 0.0,
            food_name=row["food_name"] or "",
            nutrition_per_100g=nutrition,
        )


# ---------------------------------------------------------------------------
# RecipeRepository
# ---------------------------------------------------------------------------

class RecipeRepository(Repository):
    """CRUD for recipes and their ingredients."""

    _TABLE_NAME = "recipes"

    def get_recipes_for_profile(self, profile_id: str) -> List[Recipe]:
        """Fetch all recipes belonging to a profile.

        Args:
            profile_id: UUID of the owning profile.

        Returns:
            List of Recipe dataclasses with ingredients populated.
        """
        conn = self._db.connection()
        rows = conn.execute(
            "SELECT * FROM recipes WHERE profile_id = ? ORDER BY name",
            (profile_id,),
        ).fetchall()
        recipes = [self._row_to_recipe(r) for r in rows]
        for recipe in recipes:
            recipe.ingredients = self._load_ingredients(conn, recipe.id)
        return recipes

    def get(self, recipe_id: str) -> Optional[Recipe]:
        """Fetch a single Recipe with all its ingredients.

        Args:
            recipe_id: UUID of the recipe.

        Returns:
            A Recipe dataclass, or None if not found.
        """
        conn = self._db.connection()
        row = conn.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if not row:
            return None
        recipe = self._row_to_recipe(row)
        recipe.ingredients = self._load_ingredients(conn, recipe.id)
        return recipe

    def save(self, recipe: Recipe) -> None:
        """Insert or update a Recipe (does not save ingredients).

        Args:
            recipe: The Recipe to persist.
        """
        self._save_row(self._recipe_to_dict(recipe))

    def delete(self, recipe_id: str) -> None:
        """Remove a Recipe and cascade-delete its ingredients.

        Args:
            recipe_id: UUID of the recipe to delete.
        """
        self._delete_row(recipe_id)

    def save_ingredient(self, ingredient: RecipeIngredient) -> None:
        """Insert or update a RecipeIngredient.

        Args:
            ingredient: The RecipeIngredient to persist.
        """
        row = {
            "id": ingredient.id,
            "recipe_id": ingredient.recipe_id,
            "food_id": ingredient.food_id,
            "quantity_g": ingredient.quantity_g,
            "updated_at": ingredient.updated_at or time.time(),
        }
        conn = self._db.connection()
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" * len(row))
        conn.execute(
            f"INSERT OR REPLACE INTO recipe_ingredients ({cols}) VALUES ({placeholders})",  # noqa: S608
            list(row.values()),
        )
        conn.commit()
        self._queue.enqueue("recipe_ingredients", row["id"], "insert", row)

    def delete_ingredient(self, ingredient_id: str) -> None:
        """Remove a single RecipeIngredient.

        Args:
            ingredient_id: UUID of the ingredient to delete.
        """
        conn = self._db.connection()
        conn.execute("DELETE FROM recipe_ingredients WHERE id = ?", (ingredient_id,))
        conn.commit()
        self._queue.enqueue("recipe_ingredients", ingredient_id, "delete", {"id": ingredient_id})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_ingredients(conn: Any, recipe_id: str) -> List[RecipeIngredient]:
        rows = conn.execute(
            """
            SELECT
                ri.id, ri.recipe_id, ri.food_id, ri.quantity_g, ri.updated_at,
                f.name   AS food_name,
                f.calories, f.protein_g, f.carbs_g, f.fat_g,
                f.fiber_g, f.sugar_g, f.sodium_mg
            FROM recipe_ingredients ri
            JOIN foods f ON f.id = ri.food_id
            WHERE ri.recipe_id = ?
            ORDER BY ri.rowid
            """,
            (recipe_id,),
        ).fetchall()
        return [
            RecipeIngredient(
                id=r["id"],
                recipe_id=r["recipe_id"],
                food_id=r["food_id"],
                quantity_g=r["quantity_g"],
                updated_at=r["updated_at"] or 0.0,
                food_name=r["food_name"] or "",
                nutrition_per_100g=NutritionInfo(
                    calories=r["calories"] or 0.0,
                    protein_g=r["protein_g"] or 0.0,
                    carbs_g=r["carbs_g"] or 0.0,
                    fat_g=r["fat_g"] or 0.0,
                    fiber_g=r["fiber_g"],
                    sugar_g=r["sugar_g"],
                    sodium_mg=r["sodium_mg"],
                ),
            )
            for r in rows
        ]

    def _recipe_to_dict(self, r: Recipe) -> Dict[str, Any]:
        return {
            "id": r.id,
            "profile_id": r.profile_id,
            "name": r.name,
            "servings": r.servings,
            "updated_at": r.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_recipe(row: Any) -> Recipe:
        return Recipe(
            id=row["id"],
            profile_id=row["profile_id"],
            name=row["name"],
            servings=row["servings"] or 1,
            updated_at=row["updated_at"] or 0.0,
        )
