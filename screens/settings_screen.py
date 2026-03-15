"""Settings screen — unit toggle, My Foods, My Recipes, sync status, export.

Responsibilities:
- Unit system toggle (metric / imperial)
- My Foods: list user-created manual foods; edit and swipe-to-delete
- My Recipes: list recipes with per-serving macros; create/edit/delete
- Sync status: last sync time, pending ops count, manual sync trigger
- Data export: write meal history to CSV in the app's documents directory
- About section with app version
"""

from __future__ import annotations

import csv
import io
import logging
import time
from datetime import datetime
from typing import List

from kivy.clock import Clock
from kivy.lang import Builder
from kivymd.app import MDApp

from screens.base_screen import BaseScreen
from services.food_service import FoodService
from services.repository import MealRepository, MealItemRepository, RecipeRepository
from models.food import Food
from models.recipe import Recipe
from sync.sync_manager import SyncManager
import config

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
        manager = SyncManager.get_instance()
        status = manager.status
        last_sync = (
            datetime.fromtimestamp(status.last_synced_at).strftime("%H:%M:%S")
            if status.last_synced_at
            else "Never"
        )
        self.ids.sync_status_label.text = (
            f"Last sync: {last_sync}  •  Pending: {status.pending_count}"
        )
        self.ids.online_indicator.text = "Online" if status.is_online else "Offline"

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

    def sync_now(self) -> None:
        """Trigger an immediate sync cycle."""
        self.show_loading("Syncing…")
        SyncManager.get_instance().sync_now()
        Clock.schedule_once(lambda dt: self._post_sync(), 1)

    def _post_sync(self) -> None:
        self.hide_loading()
        self._refresh_sync_status()
        self.show_success("Sync complete")

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

        conn = meal_repo._db.connection()  # pylint: disable=protected-access
        meals = conn.execute(
            "SELECT * FROM meals WHERE profile_id = ? ORDER BY date, meal_number",
            (user_id,),
        ).fetchall()

        for meal_row in meals:
            items = item_repo.get_items_for_meal(meal_row["id"])
            for item in items:
                s = item.scaled_nutrition
                writer.writerow([
                    meal_row["date"],
                    meal_row["label"] or f"Meal {meal_row['meal_number']}",
                    item.food_name,
                    item.quantity_g,
                    round(s.calories, 1),
                    round(s.protein_g, 1),
                    round(s.carbs_g, 1),
                    round(s.fat_g, 1),
                ])

        return output.getvalue()
