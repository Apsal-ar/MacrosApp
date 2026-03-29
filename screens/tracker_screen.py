"""Tracker screen — the primary daily food logging view.

Features:
- Date selector (defaults to today, navigate ±1 day)
- N MealCard widgets based on Goals.meals_per_day
- FoodSearchScreen for adding foods per meal slot
- Daily macro totals with progress bars
- Colour-coded progress: green / amber / red
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Dict, List, Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivymd.app import MDApp

from screens.base_screen import BaseScreen
from services.macro_calculator import MacroCalculator
from services.repository import (
    GoalsRepository,
    MealItemRepository,
    MealRepository,
    Repository,
)
from models.meal import Meal, MealItem
from models.food import Food
from utils.constants import (
    DEFAULT_MEAL_LABELS,
    RGBA_CALORIE_INDICATOR,
    RGBA_CALORIE_TRACK,
)
from widgets.library_food_detail_sheet import LibraryFoodDetailSheet
from widgets.meal_card import MealCard

Builder.load_file("assets/kv/tracker.kv")


class TrackerScreen(BaseScreen):
    """Main daily tracking screen.

    KV file: assets/kv/tracker.kv
    """

    name = "tracker"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._current_date: date = date.today()
        self._meals: Dict[int, Meal] = {}          # meal_number → Meal
        self._meal_cards: Dict[str, MealCard] = {}  # meal_id → MealCard
        self._goals_calorie: float = 2000.0
        self._goals_protein: float = 150.0
        self._goals_carbs: float = 200.0
        self._goals_fat: float = 67.0
        self._meals_per_day: int = 3

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self) -> None:
        """Load today's data when the screen becomes active."""
        self._pending_load_retries = 0
        Clock.schedule_once(self._load_day, 0)

    # ------------------------------------------------------------------
    # Date navigation
    # ------------------------------------------------------------------

    def go_previous_day(self) -> None:
        """Navigate to the previous day."""
        self._current_date -= timedelta(days=1)
        self._refresh_date_label()
        Clock.schedule_once(self._load_day, 0)

    def go_next_day(self) -> None:
        """Navigate to the next day."""
        self._current_date += timedelta(days=1)
        self._refresh_date_label()
        Clock.schedule_once(self._load_day, 0)

    def _refresh_date_label(self) -> None:
        if self._current_date == date.today():
            self.ids.date_label.text = "Today"
        else:
            self.ids.date_label.text = self._current_date.strftime("%A, %d %B %Y")

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_day(self, dt: float) -> None:  # noqa: ARG002
        """Load meals and goals for the current date.

        Args:
            dt: Kivy Clock delta (unused).
        """
        user_id = self.get_current_user_id()
        if not user_id:
            # Auth / app state can lag the first frame after opening the shell; retry briefly.
            self._pending_load_retries = getattr(self, "_pending_load_retries", 0) + 1
            if self._pending_load_retries <= 60:
                Clock.schedule_once(self._load_day, 0.05)
            return
        self._pending_load_retries = 0

        self._refresh_date_label()
        self._load_goals(user_id)
        self._load_meals(user_id)

    def _load_goals(self, user_id: str) -> None:
        goals_repo: GoalsRepository = self.get_repo(GoalsRepository)
        goals = goals_repo.get_for_profile(user_id)
        if goals and goals.calorie_target:
            grams = MacroCalculator.calculate_macro_grams(
                goals.calorie_target,
                goals.protein_pct,
                goals.carbs_pct,
                goals.fat_pct,
            )
            self._goals_calorie = goals.calorie_target
            self._goals_protein = grams["protein_g"]
            self._goals_carbs = grams["carbs_g"]
            self._goals_fat = grams["fat_g"]
            self._meals_per_day = goals.meals_per_day
        else:
            self._meals_per_day = 3

    def _load_meals(self, user_id: str) -> None:
        date_str = self._current_date.isoformat()
        meal_repo: MealRepository = self.get_repo(MealRepository)
        item_repo: MealItemRepository = self.get_repo(MealItemRepository)

        self.ids.meals_container.clear_widgets()
        self._meals.clear()
        self._meal_cards.clear()

        goals_repo = self.get_repo(GoalsRepository)
        goals = goals_repo.get_for_profile(user_id)
        meal_labels = goals.meal_labels if goals and goals.meal_labels else {}
        for meal_number in range(1, self._meals_per_day + 1):
            label = meal_labels.get(
                meal_number,
                DEFAULT_MEAL_LABELS.get(meal_number, f"Meal {meal_number}"),
            )
            meal = meal_repo.get_or_create(user_id, date_str, meal_number, label)
            meal.items = item_repo.get_items_for_meal(meal.id)
            self._meals[meal_number] = meal

            card = MealCard()
            card.bind(
                on_add_food=self._on_add_food_tapped,
                on_delete_item=self._on_delete_item,
                on_edit_item=self._on_edit_item,
            )
            card.load_meal(meal)
            self._meal_cards[meal.id] = card
            self.ids.meals_container.add_widget(card)

        self._update_daily_totals()
        # ScrollView often skips sizing the inner column until the next input/layout pass;
        # force height + layout so meal cards appear immediately on cold start.
        Clock.schedule_once(self._sync_meals_scroll_layout, 0)
        Clock.schedule_once(self._sync_meals_scroll_layout, 0.05)

    def _sync_meals_scroll_layout(self, _dt: Optional[float] = None) -> None:
        """Update scroll content height and relayout so cards are visible without tapping."""
        try:
            inner = self.ids.meals_scroll_inner
            inner.height = inner.minimum_height
            container = self.ids.meals_container
            container.height = container.minimum_height
            self.ids.meals_scroll.do_layout()
        except Exception:
            return

    # ------------------------------------------------------------------
    # Add food flow
    # ------------------------------------------------------------------

    def _on_add_food_tapped(self, card: MealCard, meal_id: str) -> None:  # noqa: ARG002
        """Open the full-screen food search for the tapped meal slot.

        Args:
            card: The MealCard widget (unused; meal_id used instead).
            meal_id: UUID of the target Meal.
        """
        user_id = self.get_current_user_id()
        if not user_id:
            return
        try:
            shell = MDApp.get_running_app().root.get_screen("app")
            sm = shell.ids.inner_sm
            search_screen = sm.get_screen("food_search")
            search_screen.meal_id = meal_id
            sm.current = "food_search"
        except Exception:  # pylint: disable=broad-except
            self.show_error("Could not open food search.")

    def add_food_from_search(
        self,
        meal_id: str,
        food: Food,
        quantity_g: float,
        display_name: Optional[str] = None,
    ) -> None:
        """Called by FoodSearchScreen after the user confirms a food + quantity."""
        self._add_food_to_meal(meal_id, food, quantity_g, display_name)

    def _add_food_to_meal(
        self,
        meal_id: str,
        food: Food,
        quantity_g: float,
        display_name: Optional[str] = None,
    ) -> None:
        """Create a MealItem and add it to the meal card.

        Args:
            meal_id: Target Meal UUID.
            food: The selected or created Food.
            quantity_g: Consumed quantity in grams.
            display_name: Optional label for the log entry (e.g. library sheet edit).
        """
        name = (display_name or "").strip() or food.name
        item = MealItem(
            id=Repository.new_id(),
            meal_id=meal_id,
            food_id=food.id,
            quantity_g=quantity_g,
            updated_at=time.time(),
            food_name=name,
            nutrition_per_100g=food.nutrition,
        )

        item_repo: MealItemRepository = self.get_repo(MealItemRepository)
        item_repo.save(item)

        card = self._meal_cards.get(meal_id)
        if card:
            card.add_item(item)

        self._update_daily_totals()

    # ------------------------------------------------------------------
    # Edit item (serving size)
    # ------------------------------------------------------------------

    def _on_edit_item(self, card: MealCard, item_id: str) -> None:  # noqa: ARG002
        """Open full-screen Nutrition sheet (same as library) to update serving size."""
        item_repo: MealItemRepository = self.get_repo(MealItemRepository)
        item = item_repo.get(item_id)
        if item is None:
            self.show_error("Could not load this food entry.")
            return

        food = Food(
            id=item.food_id,
            name=item.food_name or "Food",
            nutrition=item.nutrition_per_100g,
            source="manual",
            serving_size_g=100.0,
            updated_at=item.updated_at,
        )

        def on_confirm(qty_g: float, _display_name: str) -> None:
            if qty_g <= 0 or qty_g > 100_000:
                self.show_error(
                    "Enter a valid serving size between 1 and 100000 g."
                )
                return
            item.quantity_g = qty_g
            item.updated_at = time.time()
            item_repo.save(item)
            meal_card = self._meal_cards.get(item.meal_id)
            if meal_card:
                meal_card.update_item(item)
            self._update_daily_totals()

        sheet = LibraryFoodDetailSheet(
            food=food,
            on_add=on_confirm,
            on_edit=None,
            primary_button_text="UPDATE",
            initial_quantity_g=item.quantity_g,
        )
        sheet.open()

    # ------------------------------------------------------------------
    # Delete item
    # ------------------------------------------------------------------

    def _on_delete_item(self, card: MealCard, item_id: str) -> None:  # noqa: ARG002
        """Remove a MealItem from the repository and the card.

        Args:
            card: The MealCard the item belongs to.
            item_id: UUID of the MealItem to delete.
        """
        item_repo: MealItemRepository = self.get_repo(MealItemRepository)
        item_repo.delete(item_id)
        for c in self._meal_cards.values():
            c.remove_item(item_id)
        self._update_daily_totals()

    # ------------------------------------------------------------------
    # Daily totals
    # ------------------------------------------------------------------

    def _update_daily_totals(self) -> None:
        """Sum macros across all meal cards and update progress bars."""
        total_cal = total_p = total_c = total_f = 0.0
        for card in self._meal_cards.values():
            total_cal += card._calories_total
            total_p += card._protein_total
            total_c += card._carbs_total
            total_f += card._fat_total

        ids = self.ids
        cbar = ids.progress_calories_bar
        cbar.track_color = list(RGBA_CALORIE_TRACK)
        cbar.indicator_color = list(RGBA_CALORIE_INDICATOR)
        ids.total_calories.text = f"{total_cal:.0f} / {self._goals_calorie:.0f} kcal"
        goal_k = self._goals_calorie
        if goal_k > 0:
            cbar.value = min(100.0, (total_cal / goal_k) * 100.0)
        else:
            cbar.value = 0.0
        ids.progress_protein.consumed = total_p
        ids.progress_protein.target = self._goals_protein
        ids.progress_carbs.consumed = total_c
        ids.progress_carbs.target = self._goals_carbs
        ids.progress_fat.consumed = total_f
        ids.progress_fat.target = self._goals_fat
