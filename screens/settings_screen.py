"""Settings screen — unit toggle, My Foods, My Recipes, cloud status, export.

Responsibilities:
- Unit system toggle (metric / imperial)
- My Foods: list user-created manual foods; edit and swipe-to-delete
- My Recipes: list recipes with per-serving macros; create/edit/delete
- Cloud connection indicator
- Data export: write meal history to CSV in the app's documents directory
- About section with app version
"""

from __future__ import annotations

import csv
import io
import logging
import time
from typing import List

from kivy.clock import Clock
from kivy.lang import Builder
from kivymd.app import MDApp

from screens.base_screen import BaseScreen
from services.food_service import FoodService
from services.repository import MealRepository, MealItemRepository, RecipeRepository, Repository
from models.food import Food
from models.recipe import Recipe
import config
import widgets.macros_button  # noqa: F401 — registers Macros*Button for settings.kv

logger = logging.getLogger(__name__)
Builder.load_file("assets/kv/settings.kv")


class SettingsScreen(BaseScreen):
    """Settings and account management screen.

    KV file: assets/kv/settings.kv
    """

    name = "settings"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._food_service = FoodService()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self) -> None:
        """Refresh all settings sections when the screen is shown."""
        Clock.schedule_once(self._refresh_all, 0)

    # ------------------------------------------------------------------
    # Load / refresh
    # ------------------------------------------------------------------

    def _refresh_all(self, dt: float) -> None:  # noqa: ARG002
        self._refresh_unit_toggle()
        self._refresh_my_foods()
        self._refresh_sync_status()

    def _refresh_unit_toggle(self) -> None:
        unit = self.get_unit_system()
        self.ids.unit_switch.active = (unit == "imperial")

    def _refresh_my_foods(self) -> None:
        user_id = self.get_current_user_id()
        if not user_id:
            return
        foods: List[Food] = self._food_service.get_manual_foods(user_id)
        self.ids.my_foods_list.clear_widgets()
        for food in foods:
            self._add_food_list_item(food)

    def _refresh_sync_status(self) -> None:
        connected = Repository._supabase is not None
        self.ids.online_indicator.text = "Connected" if connected else "Not connected"
        self.ids.sync_status_label.text = (
            "All data stored in cloud" if connected else "No database connection"
        )

    # ------------------------------------------------------------------
    # Unit system toggle
    # ------------------------------------------------------------------

    def on_unit_toggled(self, active: bool) -> None:
        """Persist the unit system change to app state and profile.

        Args:
            active: True = imperial, False = metric.
        """
        unit = "imperial" if active else "metric"
        try:
            app = MDApp.get_running_app()
            app.unit_system = unit
        except Exception:  # pylint: disable=broad-except
            pass
        logger.info("Unit system set to %s", unit)

    # ------------------------------------------------------------------
    # My Foods
    # ------------------------------------------------------------------

    def _add_food_list_item(self, food: Food) -> None:
        """Append a swipeable list item for a manual food.

        Args:
            food: The Food dataclass to display.
        """
        from kivymd.uix.list import MDListItem, MDListItemHeadlineText, MDListItemSupportingText  # noqa: PLC0415
        item = MDListItem(on_release=lambda _, f=food: self._edit_food(f))
        item.add_widget(MDListItemHeadlineText(text=food.name))
        item.add_widget(
            MDListItemSupportingText(
                text=(
                    f"{food.nutrition.calories:.0f} kcal  "
                    f"P:{food.nutrition.protein_g:.1f}  "
                    f"C:{food.nutrition.carbs_g:.1f}  "
                    f"F:{food.nutrition.fat_g:.1f}"
                )
            )
        )
        self.ids.my_foods_list.add_widget(item)

    def _edit_food(self, food: Food) -> None:
        """Open the food search dialog pre-filled for editing.

        Args:
            food: The manual food to edit.
        """
        # TODO: open an edit-specific dialog; for now show success placeholder
        self.show_success(f"Edit '{food.name}' — coming in next iteration")

    def delete_food(self, food_id: str) -> None:
        """Delete a manual food and refresh the list.

        Args:
            food_id: UUID of the food to remove.
        """
        self._food_service.delete_manual_food(food_id)
        self._refresh_my_foods()
        self.show_success("Food deleted")

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    def refresh_connection(self) -> None:
        """Refresh the cloud connection indicator."""
        self._refresh_sync_status()
        self.show_success("Connection status refreshed")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_csv(self) -> None:
        """Export all meal history for the current user to a CSV file.

        The file is written to the Kivy user_data_dir and the path is
        shown in a success snackbar.
        """
        user_id = self.get_current_user_id()
        if not user_id:
            self.show_error("Not logged in")
            return

        self.show_loading("Exporting…")
        try:
            csv_data = self._build_csv(user_id)
            app = MDApp.get_running_app()
            export_path = f"{app.user_data_dir}/macro_export_{int(time.time())}.csv"
            with open(export_path, "w", newline="", encoding="utf-8") as f:
                f.write(csv_data)
            self.hide_loading()
            self.show_success(f"Exported to {export_path}")
        except Exception as exc:  # pylint: disable=broad-except
            self.hide_loading()
            self.show_error(f"Export failed: {exc}")
            logger.error("CSV export failed: %s", exc, exc_info=True)

    def _build_csv(self, user_id: str) -> str:
        """Build a CSV string of all meal items for a user.

        Args:
            user_id: Profile UUID of the user to export.

        Returns:
            A UTF-8 CSV string.
        """
        meal_repo: MealRepository = self.get_repo(MealRepository)
        item_repo: MealItemRepository = self.get_repo(MealItemRepository)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Meal", "Food", "Quantity (g)", "Calories", "Protein (g)", "Carbs (g)", "Fat (g)"])

        meals = meal_repo.get_all_meals(user_id)

        for meal in meals:
            items = item_repo.get_items_for_meal(meal.id)
            for item in items:
                s = item.scaled_nutrition
                writer.writerow([
                    meal.date,
                    meal.label or f"Meal {meal.meal_number}",
                    item.food_name,
                    item.quantity_g,
                    round(s.calories, 1),
                    round(s.protein_g, 1),
                    round(s.carbs_g, 1),
                    round(s.fat_g, 1),
                ])

        return output.getvalue()
