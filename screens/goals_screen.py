"""Goals screen — calorie target + donut chart + macro editor page."""

from __future__ import annotations

import time
from typing import Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.modalview import ModalView

from screens.base_screen import BaseScreen
from services.macro_calculator import MacroCalculator
from services.repository import GoalsRepository, ProfileRepository
from models.user import Goals
from utils.constants import (
    COLOR_CARBS,
    COLOR_FAT,
    COLOR_PROTEIN,
    KCAL_PER_G_CARBS,
    KCAL_PER_G_FAT,
    KCAL_PER_G_PROTEIN,
)

Builder.load_file("assets/kv/goals.kv")


class EditMacrosSheet(ModalView):
    """Full-screen editor where users enter macro percentages."""

    def __init__(self, goals_screen: "GoalsScreen", **kwargs: object) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._gs = goals_screen

    def populate(self) -> None:
        """Prefill inputs with the current percentages."""
        self.ids.protein_input.text = f"{self._gs.protein_pct:.0f}"
        self.ids.fat_input.text = f"{self._gs.fat_pct:.0f}"
        self.ids.carbs_input.text = f"{self._gs.carbs_pct:.0f}"

    def save_changes(self) -> None:
        """Validate percentages and persist them through the owning screen."""
        try:
            protein = float(self.ids.protein_input.text.strip())
            fat = float(self.ids.fat_input.text.strip())
            carbs = float(self.ids.carbs_input.text.strip())
        except ValueError:
            self._gs.show_error("Please enter valid numbers")
            return

        if protein < 0 or fat < 0 or carbs < 0:
            self._gs.show_error("Percentages cannot be negative")
            return

        total = protein + fat + carbs
        if abs(total - 100.0) > 0.1:
            self._gs.show_error("Protein + Fat + Carbs must equal 100%")
            return

        self._gs.apply_macro_split(protein, carbs, fat)
        self.dismiss()


class GoalsScreen(BaseScreen):
    """Screen for calorie target and macro split.

    KV file: assets/kv/goals.kv

    The three macro values are Kivy properties so the donut chart widget
    can bind to them directly for reactive redraws.
    """

    name = "goals"

    protein_pct = NumericProperty(30.0)
    carbs_pct = NumericProperty(40.0)
    fat_pct = NumericProperty(30.0)
    protein_breakdown_text = StringProperty(
        f"[color={COLOR_PROTEIN}]Protein[/color]\n— g\n— kcal"
    )
    carbs_breakdown_text = StringProperty(
        f"[color={COLOR_CARBS}]Carbohydrate[/color]\n— g\n— kcal"
    )
    fat_breakdown_text = StringProperty(
        f"[color={COLOR_FAT}]Fat[/color]\n— g\n— kcal"
    )

    _edit_sheet: Optional[EditMacrosSheet] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self) -> None:
        """Load persisted goals when the screen becomes active."""
        Clock.schedule_once(self._load_goals, 0)

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

        self.protein_pct = goals.protein_pct
        self.carbs_pct = goals.carbs_pct
        self.fat_pct = goals.fat_pct

        if goals.calorie_target:
            self.ids.calorie_label.text = f"{goals.calorie_target:.0f} kcal / day"
            self._update_macro_breakdown(goals.calorie_target)
        else:
            self.ids.calorie_label.text = "— Set profile data first —"
            self._update_macro_breakdown(None)

    # ------------------------------------------------------------------
    # Macro editor page
    # ------------------------------------------------------------------

    def open_macro_editor(self) -> None:
        """Open the full-screen macro editor."""
        if self._edit_sheet is None:
            self._edit_sheet = EditMacrosSheet(goals_screen=self)
        self._edit_sheet.populate()
        self._edit_sheet.open()

    def apply_macro_split(self, protein: float, carbs: float, fat: float) -> None:
        """Apply percentages and persist them."""
        self.protein_pct = round(protein, 1)
        self.carbs_pct = round(carbs, 1)
        self.fat_pct = round(fat, 1)
        self.save_goals()


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

        calorie_target = self._recalculate_calories(user_id)

        from services.repository import Repository  # avoid circular at module level
        goals = Goals(
            id=existing.id if existing else Repository.new_id(),
            profile_id=user_id,
            protein_pct=self.protein_pct,
            carbs_pct=self.carbs_pct,
            fat_pct=self.fat_pct,
            diet_type=existing.diet_type if existing else "custom",
            meals_per_day=existing.meals_per_day if existing else 3,
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
            else:
                self.ids.calorie_label.text = "— Set profile data first —"
            self._update_macro_breakdown(calorie_target)
        except Exception as exc:  # pylint: disable=broad-except
            self.hide_loading()
            self.show_error(f"Save failed: {exc}")

    def _update_macro_breakdown(self, calorie_target: Optional[float]) -> None:
        """Refresh grams and kcal text per macro from current percentages."""
        if calorie_target is None or calorie_target <= 0:
            self.protein_breakdown_text = (
                f"[color={COLOR_PROTEIN}]Protein[/color]\n— g\n— kcal"
            )
            self.carbs_breakdown_text = (
                f"[color={COLOR_CARBS}]Carbohydrate[/color]\n— g\n— kcal"
            )
            self.fat_breakdown_text = f"[color={COLOR_FAT}]Fat[/color]\n— g\n— kcal"
            return

        protein_kcal = calorie_target * (self.protein_pct / 100.0)
        carbs_kcal = calorie_target * (self.carbs_pct / 100.0)
        fat_kcal = calorie_target * (self.fat_pct / 100.0)

        protein_g = protein_kcal / KCAL_PER_G_PROTEIN
        carbs_g = carbs_kcal / KCAL_PER_G_CARBS
        fat_g = fat_kcal / KCAL_PER_G_FAT

        self.protein_breakdown_text = (
            f"[color={COLOR_PROTEIN}]Protein[/color]\n"
            f"{protein_g:.0f} g\n{protein_kcal:.0f} kcal"
        )
        self.carbs_breakdown_text = (
            f"[color={COLOR_CARBS}]Carbohydrate[/color]\n"
            f"{carbs_g:.0f} g\n{carbs_kcal:.0f} kcal"
        )
        self.fat_breakdown_text = (
            f"[color={COLOR_FAT}]Fat[/color]\n"
            f"{fat_g:.0f} g\n{fat_kcal:.0f} kcal"
        )

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
