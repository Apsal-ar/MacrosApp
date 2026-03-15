"""Goals screen — macro ratio sliders, diet presets, and pie chart.

Sliders for protein/carbs/fat are coupled: when one changes, the others
adjust proportionally to maintain a 100% sum. Selecting a preset auto-sets
all three. The pie chart updates in real time.
"""

from __future__ import annotations

import time
from typing import Optional  # noqa: F401

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import NumericProperty
from kivymd.uix.menu import MDDropdownMenu

from screens.base_screen import BaseScreen
from services.macro_calculator import MacroCalculator
from services.repository import GoalsRepository, ProfileRepository
from models.user import Goals
from utils.constants import DIET_PRESETS, DIET_PRESET_LABELS

Builder.load_file("assets/kv/goals.kv")


class GoalsScreen(BaseScreen):
    """Screen for setting macro split, diet presets, and meals per day.

    KV file: assets/kv/goals.kv

    The three slider values are Kivy properties so the pie chart widget
    can bind to them directly for reactive redraws.
    """

    name = "goals"

    protein_pct = NumericProperty(30.0)
    carbs_pct = NumericProperty(40.0)
    fat_pct = NumericProperty(30.0)

    _updating_sliders: bool = False
    _diet_key: str = "balanced"
    _diet_menu: Optional[MDDropdownMenu] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_kv_post(self, base_widget: object) -> None:
        """Build the diet preset dropdown after KV widgets are ready."""
        super().on_kv_post(base_widget)
        self._build_diet_menu()

    def on_enter(self) -> None:
        """Load persisted goals when the screen becomes active."""
        Clock.schedule_once(self._load_goals, 0)

    # ------------------------------------------------------------------
    # Diet menu
    # ------------------------------------------------------------------

    def _build_diet_menu(self) -> None:
        """Create MDDropdownMenu for diet preset selection."""
        items = []
        for key, label in DIET_PRESET_LABELS.items():
            def _cb(k=key, l=label):
                return lambda: self._select_diet(k, l)
            items.append({"text": label, "on_release": _cb()})
        self._diet_menu = MDDropdownMenu(
            caller=self.ids.diet_dropdown,
            items=items,
        )

    def open_diet_menu(self) -> None:
        """Open the diet preset dropdown (called from KV on_release)."""
        if self._diet_menu:
            self._diet_menu.open()

    def _select_diet(self, key: str, label: str) -> None:
        """Apply a named diet preset and update display.

        Args:
            key: Preset key, e.g. 'keto'.
            label: Display label.
        """
        self._diet_key = key
        self.ids.diet_text.text = label
        self._diet_menu.dismiss()
        self.on_diet_preset_selected(label)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_goals(self, dt: float) -> None:  # noqa: ARG002
        user_id = self.get_current_user_id()
        if not user_id:
            return

        repo: GoalsRepository = self.get_repo(GoalsRepository)
        goals = repo.get_for_profile(user_id)
        if goals is None:
            return

        self._updating_sliders = True
        self.protein_pct = goals.protein_pct
        self.carbs_pct = goals.carbs_pct
        self.fat_pct = goals.fat_pct
        self.ids.meals_slider.value = goals.meals_per_day

        self._diet_key = goals.diet_type
        diet_label = DIET_PRESET_LABELS.get(goals.diet_type, "Balanced")
        self.ids.diet_text.text = diet_label

        if goals.calorie_target:
            self.ids.calorie_label.text = f"{goals.calorie_target:.0f} kcal / day"

        self._update_gram_labels(goals.calorie_target or 0)
        self._updating_sliders = False

    # ------------------------------------------------------------------
    # Slider coupling
    # ------------------------------------------------------------------

    def on_protein_slider(self, value: float) -> None:
        """Handle protein slider movement — adjust carbs/fat proportionally.

        Args:
            value: New protein percentage value from the slider.
        """
        if self._updating_sliders:
            return
        self._updating_sliders = True
        self.protein_pct = round(value, 1)
        remaining = 100.0 - self.protein_pct
        total_other = self.carbs_pct + self.fat_pct
        if total_other > 0:
            self.carbs_pct = round(remaining * (self.carbs_pct / total_other), 1)
            self.fat_pct = round(100.0 - self.protein_pct - self.carbs_pct, 1)
        else:
            self.carbs_pct = round(remaining / 2, 1)
            self.fat_pct = round(remaining / 2, 1)
        self._sync_sliders_to_ui()
        self._set_custom_preset()
        self._updating_sliders = False

    def on_carbs_slider(self, value: float) -> None:
        """Handle carbs slider movement — adjust protein/fat proportionally.

        Args:
            value: New carbs percentage value.
        """
        if self._updating_sliders:
            return
        self._updating_sliders = True
        self.carbs_pct = round(value, 1)
        remaining = 100.0 - self.carbs_pct
        total_other = self.protein_pct + self.fat_pct
        if total_other > 0:
            self.protein_pct = round(remaining * (self.protein_pct / total_other), 1)
            self.fat_pct = round(100.0 - self.carbs_pct - self.protein_pct, 1)
        else:
            self.protein_pct = round(remaining / 2, 1)
            self.fat_pct = round(remaining / 2, 1)
        self._sync_sliders_to_ui()
        self._set_custom_preset()
        self._updating_sliders = False

    def on_fat_slider(self, value: float) -> None:
        """Handle fat slider movement — adjust protein/carbs proportionally.

        Args:
            value: New fat percentage value.
        """
        if self._updating_sliders:
            return
        self._updating_sliders = True
        self.fat_pct = round(value, 1)
        remaining = 100.0 - self.fat_pct
        total_other = self.protein_pct + self.carbs_pct
        if total_other > 0:
            self.protein_pct = round(remaining * (self.protein_pct / total_other), 1)
            self.carbs_pct = round(100.0 - self.fat_pct - self.protein_pct, 1)
        else:
            self.protein_pct = round(remaining / 2, 1)
            self.carbs_pct = round(remaining / 2, 1)
        self._sync_sliders_to_ui()
        self._set_custom_preset()
        self._updating_sliders = False

    def _sync_sliders_to_ui(self) -> None:
        """Push current pct properties back to the slider widgets."""
        self.ids.protein_slider.value = self.protein_pct
        self.ids.carbs_slider.value = self.carbs_pct
        self.ids.fat_slider.value = self.fat_pct
        self.ids.protein_label.text = f"Protein: {self.protein_pct:.0f}%"
        self.ids.carbs_label.text = f"Carbs: {self.carbs_pct:.0f}%"
        self.ids.fat_label.text = f"Fat: {self.fat_pct:.0f}%"
        self.ids.pie_chart.protein_pct = self.protein_pct
        self.ids.pie_chart.carbs_pct = self.carbs_pct
        self.ids.pie_chart.fat_pct = self.fat_pct

    def _set_custom_preset(self) -> None:
        self._diet_key = "custom"
        self.ids.diet_text.text = DIET_PRESET_LABELS["custom"]

    # ------------------------------------------------------------------
    # Preset selection
    # ------------------------------------------------------------------

    def on_diet_preset_selected(self, label: str) -> None:
        """Apply the chosen diet preset macro percentages to the sliders.

        Args:
            label: Display label from the diet type spinner.
        """
        key = next((k for k, v in DIET_PRESET_LABELS.items() if v == label), None)
        if key is None or key == "custom":
            return
        preset = DIET_PRESETS[key]
        self._updating_sliders = True
        self.protein_pct = preset["protein_pct"]
        self.carbs_pct = preset["carbs_pct"]
        self.fat_pct = preset["fat_pct"]
        self._sync_sliders_to_ui()
        self._updating_sliders = False

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_goals(self) -> None:
        """Persist the current macro settings to GoalsRepository."""
        user_id = self.get_current_user_id()
        if not user_id:
            self.show_error("Not logged in")
            return

        repo: GoalsRepository = self.get_repo(GoalsRepository)
        existing = repo.get_for_profile(user_id)

        diet_key = self._diet_key or "custom"
        meals_per_day = int(self.ids.meals_slider.value)

        calorie_target = self._recalculate_calories(user_id)

        from services.repository import Repository  # avoid circular at module level
        goals = Goals(
            id=existing.id if existing else Repository.new_id(),
            profile_id=user_id,
            protein_pct=self.protein_pct,
            carbs_pct=self.carbs_pct,
            fat_pct=self.fat_pct,
            diet_type=diet_key,
            meals_per_day=meals_per_day,
            calorie_target=calorie_target,
            updated_at=time.time(),
        )

        self.show_loading("Saving…")
        try:
            repo.save(goals)
            self.hide_loading()
            self.show_success("Goals saved")
            if calorie_target:
                self.ids.calorie_label.text = f"{calorie_target:.0f} kcal / day"
            self._update_gram_labels(calorie_target or 0)
        except Exception as exc:  # pylint: disable=broad-except
            self.hide_loading()
            self.show_error(f"Save failed: {exc}")

    def _recalculate_calories(self, user_id: str) -> Optional[float]:
        """Return the updated calorie target based on current profile data.

        Args:
            user_id: Profile UUID.

        Returns:
            Calorie target float, or None if profile is incomplete.
        """
        profile_repo: ProfileRepository = self.get_repo(ProfileRepository)
        profile = profile_repo.get(user_id)
        if profile is None:
            return None
        if any(v is None for v in [profile.weight_kg, profile.height_cm, profile.age, profile.sex, profile.activity, profile.goal]):
            return None
        targets = MacroCalculator.calculate_targets(
            weight_kg=profile.weight_kg,
            height_cm=profile.height_cm,
            age=profile.age,
            sex=profile.sex,
            activity_level=profile.activity,
            goal=profile.goal,
            protein_pct=self.protein_pct,
            carbs_pct=self.carbs_pct,
            fat_pct=self.fat_pct,
        )
        return targets["calories"]

    def _update_gram_labels(self, calories: float) -> None:
        """Update the gram target display labels below the sliders.

        Args:
            calories: Daily calorie target.
        """
        grams = MacroCalculator.calculate_macro_grams(
            calories, self.protein_pct, self.carbs_pct, self.fat_pct
        )
        self.ids.grams_label.text = (
            f"Protein: {grams['protein_g']:.0f}g  |  "
            f"Carbs: {grams['carbs_g']:.0f}g  |  "
            f"Fat: {grams['fat_g']:.0f}g"
        )
