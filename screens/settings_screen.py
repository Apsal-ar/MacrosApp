"""Settings screen — formula info, My Foods, cloud status, export.

Responsibilities:
- Formula: summary of metric calculations (app uses metric only)
- My Foods: list user-created manual foods; edit and swipe-to-delete
- Cloud connection indicator
- Data export: write meal history to CSV in the app's documents directory
- About section with app version
"""

from __future__ import annotations

import csv
import io
import logging
import time
from typing import List, Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.button import MDButtonText
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogHeadlineText,
    MDDialogSupportingText,
)

from screens.base_screen import BaseScreen
from services.food_service import FoodService
from services.macro_calculator import MacroCalculator
from services.repository import (
    GoalsRepository,
    MealRepository,
    MealItemRepository,
    ProfileRepository,
    RecipeRepository,
    Repository,
)
from models.food import Food
from models.recipe import Recipe
import config
import widgets.macros_button  # noqa: F401 — registers Macros*Button for settings.kv
from widgets.macros_button import MacrosFilledButton
from utils.constants import (
    ACTIVITY_LABELS,
    ACTIVITY_MULTIPLIERS,
    GOAL_LABELS,
    GOAL_MODIFIERS,
    RGBA_POPUP,
)

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
        self._refresh_sync_status()

    def _refresh_sync_status(self) -> None:
        connected = Repository._supabase is not None
        self.ids.online_indicator.text = "Connected" if connected else "Not connected"
        self.ids.sync_status_label.text = (
            "All data stored in cloud" if connected else "No database connection"
        )

    # ------------------------------------------------------------------
    # Formula
    # ------------------------------------------------------------------

    def open_formula(self) -> None:
        """Show how the daily calorie target is derived (BMR → TDEE → goal)."""
        dlg_ref: list[MDDialog] = []
        body = self._build_calorie_target_formula_text()
        dlg = MDDialog(
            MDDialogHeadlineText(text="Calorie target"),
            MDDialogSupportingText(text=body),
            MDDialogButtonContainer(
                Widget(),
                MacrosFilledButton(
                    MDButtonText(text="Ok"),
                    on_release=lambda *_a: dlg_ref[0].dismiss() if dlg_ref else None,
                ),
                spacing="8dp",
            ),
            theme_bg_color="Custom",
            md_bg_color=RGBA_POPUP,
        )
        dlg_ref.append(dlg)
        dlg.open()

    @staticmethod
    def _mifflin_st_jeor_reference_block() -> str:
        """Same equations as ``MacroCalculator.calculate_bmr`` (docstring)."""
        return (
            "Mifflin–St Jeor BMR (kcal/day):\n"
            "  base = 10×weight(kg) + 6.25×height(cm) − 5×age\n"
            "  Male:   BMR = base + 5\n"
            "  Female: BMR = base − 161\n"
            "  Other:  BMR = base − 78 (midpoint between male and female)\n"
        )

    def _build_calorie_target_formula_text(self) -> str:
        """Explain BMR → TDEE → goal adjustment; include user numbers when possible."""
        generic = (
            self._mifflin_st_jeor_reference_block()
            + "\n"
            "Then your daily calorie target uses three steps:\n\n"
            "1) BMR from your profile (kcal/day).\n\n"
            "2) TDEE (maintenance): BMR × an activity multiplier (PAL) for your "
            "activity level.\n\n"
            "3) Goal: TDEE plus a fixed adjustment for your weight goal "
            "(for example −250 kcal/day to lose slowly). "
            "The result is never below 1200 kcal/day.\n\n"
            "Complete your profile (Goals / Profile) to see your personal numbers here."
        )

        user_id = self.get_current_user_id()
        if not user_id:
            return generic

        profile = self.get_repo(ProfileRepository).get(user_id)
        if profile is None:
            return generic

        required = (
            profile.weight_kg,
            profile.height_cm,
            profile.age,
            profile.sex,
            profile.activity,
            profile.goal,
        )
        if any(v is None for v in required):
            return generic

        w, h, age, sex, activity, goal = required
        fw, fh, iage = float(w), float(h), int(age)
        sex_s = str(sex).lower()
        bmr = MacroCalculator.calculate_bmr(fw, fh, iage, str(sex))
        base = (10.0 * fw) + (6.25 * fh) - (5.0 * float(iage))
        tdee = MacroCalculator.calculate_tdee(bmr, str(activity))
        recommended = MacroCalculator.apply_goal_modifier(tdee, str(goal))

        act_norm = MacroCalculator._ACTIVITY_ALIASES.get(str(activity), str(activity))
        pal = ACTIVITY_MULTIPLIERS.get(
            act_norm, ACTIVITY_MULTIPLIERS.get("moderate", 1.55)
        )
        goal_norm = MacroCalculator._GOAL_ALIASES.get(str(goal), str(goal))
        delta = GOAL_MODIFIERS.get(goal_norm, GOAL_MODIFIERS["maintain"])
        act_label = ACTIVITY_LABELS.get(act_norm, act_norm)
        goal_label = GOAL_LABELS.get(goal_norm, goal_norm)

        if sex_s == "male":
            bmr_line = f"  Male:   BMR = {base:.0f} + 5 = {bmr:.0f} kcal/day"
        elif sex_s == "female":
            bmr_line = f"  Female: BMR = {base:.0f} − 161 = {bmr:.0f} kcal/day"
        else:
            bmr_line = f"  Other:  BMR = {base:.0f} − 78 = {bmr:.0f} kcal/day"

        lines: List[str] = [
            "Your daily calorie target is built from your profile:",
            "",
            "Mifflin–St Jeor BMR:",
            f"  base = 10×{fw:.1f} + 6.25×{fh:.1f} − 5×{iage} = {base:.0f}",
            bmr_line,
            "",
            f"1) TDEE (maintenance): BMR × PAL",
            f"   {bmr:.0f} × {pal} ≈ {tdee:.0f} kcal/day",
            f"   Activity: {act_label}.",
            "",
            f"2) Goal adjustment: {delta:+.0f} kcal/day ({goal_label})",
            f"   Recommended intake: {recommended:.0f} kcal/day (min. 1200 kcal).",
        ]

        goals = self.get_repo(GoalsRepository).get_for_profile(user_id)
        saved: Optional[float] = (
            float(goals.calorie_target)
            if goals is not None and goals.calorie_target is not None
            else None
        )
        if saved is not None:
            lines.append("")
            lines.append(f"Saved target in Goals: {saved:.0f} kcal/day.")
            if abs(saved - recommended) > 1.0:
                lines.append(
                    "You may have adjusted this on Goals (Caloric requirement)."
                )
        else:
            lines.append("")
            lines.append("Open Goals to save your calorie target.")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # My Foods
    # ------------------------------------------------------------------

    def open_my_foods(self) -> None:
        """Navigate to the food search screen with the My Foods tab active."""
        try:
            app = MDApp.get_running_app()
            shell = app.root.get_screen("app")
            sm = shell.ids.inner_sm
            search = sm.get_screen("food_search")
            search.open_from_settings()
            sm.current = "food_search"
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("open_my_foods: %s", exc)
            self.show_error("Could not open My Foods.")

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
