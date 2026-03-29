"""Repository pattern — SQLite cache first; Supabase via SyncManager (background).

Screens read/write SQLite through repositories only. Remote sync is async.

Call Repository.set_client(supabase) and Repository.set_cache(cache) at startup.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from sync.cache_db import CacheDB

from models.user import Profile, Goals
from models.food import Food, NutritionInfo
from models.meal import Meal, MealItem
from models.recipe import Recipe, RecipeIngredient
from sync.sync_manager import trigger_flush_async

logger = logging.getLogger(__name__)


def _salt_g_to_sodium_mg(salt_g: Optional[float]) -> Optional[float]:
    """EU-style: salt (g per 100g) ↔ sodium (mg): sodium_mg = salt * 1000 / 2.5."""
    if salt_g is None:
        return None
    return (float(salt_g) * 1000.0) / 2.5


def _sodium_mg_to_salt_g(sodium_mg: Optional[float]) -> Optional[float]:
    """salt (g) = sodium (mg) * 2.5 / 1000."""
    if sodium_mg is None:
        return None
    return (float(sodium_mg) / 1000.0) * 2.5


def _food_payload_to_join(fd: Dict[str, Any]) -> Dict[str, Any]:
    """Shape stored meal_items / recipe_foods `foods` FK join for row parsers."""
    sodium_mg = fd.get("sodium_mg")
    if sodium_mg is None and fd.get("salt") is not None:
        sodium_mg = _salt_g_to_sodium_mg(float(fd["salt"]))
    return {
        "name": fd.get("name"),
        "calories": fd.get("calories"),
        "protein_g": fd.get("protein_g"),
        "carbs_g": fd.get("carbs_g"),
        "fat_g": fd.get("fat_g"),
        "fiber_g": fd.get("fiber_g"),
        "sugar_g": fd.get("sugar_g"),
        "sodium_mg": sodium_mg,
    }


# ---------------------------------------------------------------------------
# Base Repository
# ---------------------------------------------------------------------------

class Repository:
    """Shared Supabase client (for sync only) + local CacheDB (all reads/writes)."""

    _supabase: Optional[Any] = None
    _cache: Optional["CacheDB"] = None

    @classmethod
    def set_client(cls, client: Any) -> None:
        cls._supabase = client

    @classmethod
    def set_cache(cls, cache: Optional["CacheDB"]) -> None:
        cls._cache = cache

    @classmethod
    def set_local_store(cls, cache: Optional["CacheDB"]) -> None:
        """Backward-compatible alias for set_cache."""
        cls._cache = cache

    def _table(self, name: str) -> Optional[Any]:
        if self._supabase is None:
            return None
        return self._supabase.table(name)

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# ProfileRepository
# ---------------------------------------------------------------------------

class ProfileRepository(Repository):
    """CRUD for the profiles table."""

    def get(self, profile_id: str) -> Optional[Profile]:
        """Read profile from SQLite cache only."""
        cache = Repository._cache
        if cache is None:
            return None
        cached = cache.get_profile(profile_id)
        if cached is None:
            return None
        return self._row_to_profile(cached)

    def save(self, profile: Profile) -> None:
        """Write profile to cache, enqueue sync, flush in background."""
        payload = self._profile_to_dict(profile)
        cache = Repository._cache
        if cache is None:
            return
        cache.upsert_profile(payload, from_remote=False)
        cache.enqueue_sync("profiles", "upsert", profile.id, payload)
        trigger_flush_async()

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
        """Read goals from SQLite cache only."""
        cache = Repository._cache
        if cache is None:
            return None
        cached = cache.get_goals_for_profile(profile_id)
        if cached is None:
            return None
        return self._row_to_goals(cached)

    def save(self, goals: Goals) -> None:
        """Write goals to cache, enqueue sync."""
        cache = Repository._cache
        if cache is None:
            return
        payload = self._goals_to_dict(goals)
        cache.upsert_goals(payload, from_remote=False)
        cache.enqueue_sync("goals", "upsert", goals.id, payload)
        trigger_flush_async()

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
    """CRUD and search for the foods table (SQLite cache; sync via SyncManager)."""

    def get(self, food_id: str) -> Optional[Food]:
        """Fetch a single Food from the local cache."""
        cache = Repository._cache
        if cache is None:
            return None
        row = cache.get_food(food_id)
        if row is None:
            return None
        return self._row_to_food(row)

    def get_by_barcode(self, barcode: str) -> Optional[Food]:
        """Look up a food by barcode in the local cache."""
        cache = Repository._cache
        if cache is None:
            return None
        for row in cache.get_all_food_payloads():
            if row.get("barcode") == barcode:
                return self._row_to_food(row)
        return None

    def search(self, query: str, profile_id: Optional[str] = None, limit: int = 20) -> List[Food]:
        """Search cached foods by name/brand (substring match, case-insensitive)."""
        cache = Repository._cache
        if cache is None:
            return []
        q = (query or "").strip().lower()
        if not q:
            return []
        foods: List[Food] = []
        for row in cache.get_all_food_payloads():
            name = (row.get("name") or "").lower()
            brand = (row.get("brand") or "").lower()
            if q not in name and q not in brand:
                continue
            f = self._row_to_food(row)
            if profile_id:
                if f.source not in ("openfoodfacts", "usda") and f.created_by != profile_id:
                    continue
            foods.append(f)
        foods.sort(key=lambda x: (x.name or "").lower())
        return foods[:limit]

    def get_manual_foods(self, profile_id: str) -> List[Food]:
        """Return all user-created manual foods from the cache."""
        cache = Repository._cache
        if cache is None:
            return []
        rows = cache.get_manual_foods_local(profile_id)
        return [self._row_to_food(r) for r in rows]

    def save(self, food: Food) -> None:
        """Upsert food in cache, enqueue sync."""
        cache = Repository._cache
        if cache is None:
            return
        payload = self._food_to_dict(food)
        cache.upsert_food(payload, from_remote=False)
        cache.enqueue_sync("foods", "upsert", food.id, payload)
        trigger_flush_async()

    def delete(self, food_id: str) -> None:
        """Delete from cache and enqueue remote delete."""
        cache = Repository._cache
        if cache is None:
            return
        cache.delete_food(food_id)
        cache.enqueue_sync("foods", "delete", food_id, {"id": food_id})
        trigger_flush_async()

    def _food_to_dict(self, f: Food) -> Dict[str, Any]:
        """JSON / Supabase `foods` row (column names match PostgREST)."""
        n = f.nutrition
        salt = _sodium_mg_to_salt_g(n.sodium_mg) if n else None
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
            "fat_saturated": n.fat_saturated_g if n else None,
            "fat_trans": n.fat_trans_g if n else None,
            "fat_polyunsaturated": n.fat_polyunsaturated_g if n else None,
            "fat_monounsaturated": n.fat_monounsaturated_g if n else None,
            "fiber_g": n.fiber_g if n else None,
            "sugar_g": n.sugar_g if n else None,
            "salt": salt,
            "serving_size": f.serving_size_g,
            "created_by": f.created_by,
            "updated_at": f.updated_at or time.time(),
        }

    @staticmethod
    def _row_to_food(row: Dict[str, Any]) -> Food:
        sodium_mg = row.get("sodium_mg")
        if sodium_mg is None and row.get("salt") is not None:
            sodium_mg = _salt_g_to_sodium_mg(float(row["salt"]))

        def _g(key_new: str, key_legacy: str) -> Optional[float]:
            v = row.get(key_new)
            if v is None:
                v = row.get(key_legacy)
            if v is None:
                return None
            return float(v)

        nutrition = NutritionInfo(
            calories=row.get("calories") or 0.0,
            protein_g=row.get("protein_g") or 0.0,
            carbs_g=row.get("carbs_g") or 0.0,
            fat_g=row.get("fat_g") or 0.0,
            fiber_g=row.get("fiber_g"),
            sugar_g=row.get("sugar_g"),
            sodium_mg=sodium_mg,
            fat_saturated_g=_g("fat_saturated", "fat_saturated_g"),
            fat_trans_g=_g("fat_trans", "fat_trans_g"),
            fat_polyunsaturated_g=_g("fat_polyunsaturated", "fat_polyunsaturated_g"),
            fat_monounsaturated_g=_g("fat_monounsaturated", "fat_monounsaturated_g"),
        )
        serving = row.get("serving_size")
        if serving is None:
            serving = row.get("serving_size_g")
        return Food(
            id=row["id"],
            name=row["name"],
            barcode=row.get("barcode"),
            brand=row.get("brand"),
            source=row.get("source") or "manual",
            nutrition=nutrition,
            serving_size_g=float(serving) if serving is not None else 100.0,
            created_by=row.get("created_by"),
            updated_at=row.get("updated_at") or 0.0,
        )


# ---------------------------------------------------------------------------
# MealRepository
# ---------------------------------------------------------------------------

class MealRepository(Repository):
    """CRUD for the meals table (cache-first)."""

    def get_meals_for_date(self, profile_id: str, date: str) -> List[Meal]:
        """Fetch all meal slots for a given profile and date from cache."""
        cache = Repository._cache
        if cache is None:
            return []
        rows = cache.get_meals_for_date_rows(profile_id, date)
        return [self._row_to_meal(r) for r in rows]

    def get_all_meals(self, profile_id: str) -> List[Meal]:
        """Fetch every meal for a profile from cache."""
        cache = Repository._cache
        if cache is None:
            return []
        rows = cache.get_all_meals_for_profile_rows(profile_id)
        return [self._row_to_meal(r) for r in rows]

    def get_or_create(self, profile_id: str, date: str, meal_number: int, label: str) -> Meal:
        """Return an existing meal slot or create one if it doesn't exist."""
        cache = Repository._cache
        if cache is not None:
            for row in cache.get_meals_for_date_rows(profile_id, date):
                if int(row.get("meal_number") or 0) == int(meal_number):
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
        """Upsert meal in cache, enqueue sync."""
        cache = Repository._cache
        if cache is None:
            return
        payload = self._meal_to_dict(meal)
        cache.upsert_meal(payload, from_remote=False)
        cache.enqueue_sync("meals", "upsert", meal.id, payload)
        trigger_flush_async()

    def delete(self, meal_id: str) -> None:
        """Delete meal (and cached items) locally, enqueue remote delete."""
        cache = Repository._cache
        if cache is None:
            return
        cache.delete_meal(meal_id)
        cache.enqueue_sync("meals", "delete", meal_id, {"id": meal_id})
        trigger_flush_async()

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
    """CRUD for the meal_items table with denormalised food data from cache."""

    def get_items_for_meal(self, meal_id: str) -> List[MealItem]:
        """Fetch meal items from cache; join food nutrition from cached foods."""
        cache = Repository._cache
        if cache is None:
            return []
        rows = cache.get_meal_items_for_meal(meal_id)
        return [self._row_to_item(self._enrich_item_row(r)) for r in rows]

    def get(self, item_id: str) -> Optional[MealItem]:
        """Load a single meal item by id (for editing)."""
        cache = Repository._cache
        if cache is None:
            return None
        row = cache.get_meal_item_payload(item_id)
        if row is None:
            return None
        return self._row_to_item(self._enrich_item_row(row))

    def _enrich_item_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if row.get("foods"):
            return row
        cache = Repository._cache
        fid = row.get("food_id")
        if cache is None or not fid:
            return row
        fd = cache.get_food(fid)
        if not fd:
            return row
        out = dict(row)
        out["foods"] = _food_payload_to_join(fd)
        return out

    def save(self, item: MealItem) -> None:
        """Upsert meal item in cache, enqueue sync."""
        cache = Repository._cache
        if cache is None:
            return
        payload = self._item_to_dict(item)
        cache.upsert_meal_item(payload, from_remote=False)
        cache.enqueue_sync("meal_items", "upsert", item.id, payload)
        trigger_flush_async()

    def delete(self, item_id: str) -> None:
        """Delete from cache, enqueue remote delete."""
        cache = Repository._cache
        if cache is None:
            return
        cache.delete_meal_item(item_id)
        cache.enqueue_sync("meal_items", "delete", item_id, {"id": item_id})
        trigger_flush_async()

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
        food_data = row.get("foods") if isinstance(row.get("foods"), dict) else {}
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
    """CRUD for recipes and their ingredients (cache-first)."""

    def get_recipes_for_profile(self, profile_id: str) -> List[Recipe]:
        """Fetch all recipes for a profile from cache, with ingredients."""
        cache = Repository._cache
        if cache is None:
            return []
        rows = cache.get_recipes_for_profile_rows(profile_id)
        rows.sort(key=lambda r: (r.get("name") or "").lower())
        recipes = [self._row_to_recipe(r) for r in rows]
        for recipe in recipes:
            recipe.ingredients = self._load_ingredients(recipe.id)
        return recipes

    def get(self, recipe_id: str) -> Optional[Recipe]:
        """Fetch a single Recipe with ingredients from cache."""
        cache = Repository._cache
        if cache is None:
            return None
        row = cache.get_recipe_row(recipe_id)
        if row is None:
            return None
        recipe = self._row_to_recipe(row)
        recipe.ingredients = self._load_ingredients(recipe.id)
        return recipe

    def save(self, recipe: Recipe) -> None:
        """Upsert recipe in cache (ingredients saved separately)."""
        cache = Repository._cache
        if cache is None:
            return
        payload = self._recipe_to_dict(recipe)
        cache.upsert_recipe(payload, from_remote=False)
        cache.enqueue_sync("recipes", "upsert", recipe.id, payload)
        trigger_flush_async()

    def delete(self, recipe_id: str) -> None:
        """Delete recipe and cached ingredients; enqueue remote delete."""
        cache = Repository._cache
        if cache is None:
            return
        cache.delete_recipe(recipe_id)
        cache.enqueue_sync("recipes", "delete", recipe_id, {"id": recipe_id})
        trigger_flush_async()

    def save_ingredient(self, ingredient: RecipeIngredient) -> None:
        """Upsert a recipe ingredient in cache."""
        cache = Repository._cache
        if cache is None:
            return
        data = {
            "id": ingredient.id,
            "recipe_id": ingredient.recipe_id,
            "food_id": ingredient.food_id,
            "quantity_g": ingredient.quantity_g,
            "updated_at": ingredient.updated_at or time.time(),
        }
        cache.upsert_recipe_food(data, from_remote=False)
        cache.enqueue_sync("recipe_foods", "upsert", ingredient.id, data)
        trigger_flush_async()

    def delete_ingredient(self, ingredient_id: str) -> None:
        """Delete ingredient from cache, enqueue sync."""
        cache = Repository._cache
        if cache is None:
            return
        cache.delete_recipe_food(ingredient_id)
        cache.enqueue_sync("recipe_foods", "delete", ingredient_id, {"id": ingredient_id})
        trigger_flush_async()

    def _load_ingredients(self, recipe_id: str) -> List[RecipeIngredient]:
        cache = Repository._cache
        if cache is None:
            return []
        rows = cache.get_recipe_food_rows(recipe_id)
        return [self._row_to_ingredient(self._enrich_ing_row(r)) for r in rows]

    def _enrich_ing_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if row.get("foods"):
            return row
        cache = Repository._cache
        fid = row.get("food_id")
        if cache is None or not fid:
            return row
        fd = cache.get_food(fid)
        if not fd:
            return row
        out = dict(row)
        out["foods"] = _food_payload_to_join(fd)
        return out

    @staticmethod
    def _row_to_ingredient(row: Dict[str, Any]) -> RecipeIngredient:
        food_data = row.get("foods") if isinstance(row.get("foods"), dict) else {}
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
