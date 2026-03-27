"""Goals screen — calorie target + donut chart + macro editor page."""

from __future__ import annotations

import time
from typing import Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
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
from kivymd.uix.selectioncontrol import MDSwitch  # noqa: F401 — registers MDSwitch for KV

from widgets.macro_pie_chart import MacroPieChart  # noqa: F401 — registers MacroPieChart for KV


class EditCalorieTargetSheet(ModalView):
    """Caloric requirement: recommended kcal ± slider %, optional use-recommended."""

    maintenance_kcal = NumericProperty(0.0)
    recommended_kcal = NumericProperty(0.0)
    adjustment_pct = NumericProperty(0.0)
    use_recommended = BooleanProperty(True)
    hero_kcal_text = StringProperty("—")
    maintenance_line = StringProperty("")
    caloric_row_value = StringProperty("")
    modification_line = StringProperty("")
    body_available = BooleanProperty(False)
    info_notice = StringProperty("")

    def __init__(self, goals_screen: "GoalsScreen", **kwargs: object) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._gs = goals_screen
        self._populating = False

    def populate(self) -> None:
        """Load TDEE, recommended kcal, and derive slider from saved target."""
        if "slider_adj" not in self.ids:
            Clock.schedule_once(lambda _dt: self.populate(), 0)
            return
        self._populating = True
        tdee, rec = self._gs.get_tdee_and_recommended_kcal()
        self.maintenance_kcal = float(tdee or 0.0)
        self.recommended_kcal = float(rec or 0.0)
        self.body_available = bool(rec and rec > 0)
        self.info_notice = ""

        current = self._gs.get_calorie_target_optional()
        if current is None or current <= 0:
            current = rec if rec else None

        if self.body_available and rec and current:
            adj = (float(current) / float(rec) - 1.0) * 100.0
            adj = max(-50.0, min(50.0, adj))
            self.adjustment_pct = adj
            self.use_recommended = abs(adj) < 0.5
        else:
            self.adjustment_pct = 0.0
            self.use_recommended = True
            if not self.body_available:
                self.info_notice = (
                    "Complete your profile (weight, height, age, activity, goal) "
                    "to calculate recommended calories."
                )

        if "slider_adj" in self.ids:
            self.ids.slider_adj.value = self.adjustment_pct
        if "use_rec_switch" in self.ids:
            self.ids.use_rec_switch.active = self.use_recommended

        self._populating = False
        self._refresh_labels()

    def _display_kcal(self) -> float:
        rec = float(self.recommended_kcal)
        if rec <= 0:
            return 0.0
        raw = rec * (1.0 + float(self.adjustment_pct) / 100.0)
        return max(400.0, min(25000.0, raw))

    def _refresh_labels(self) -> None:
        d = self._display_kcal()
        self.hero_kcal_text = f"{d:.0f}" if self.body_available and d else "—"
        self.caloric_row_value = f"{d:.0f} kcal" if self.body_available and d else "—"
        if self.maintenance_kcal > 0:
            self.maintenance_line = (
                f"Maintenance calories: {self.maintenance_kcal:.0f} kcal"
            )
        else:
            self.maintenance_line = ""
        ap = float(self.adjustment_pct)
        self.modification_line = (
            f"Recommended calories modification: {ap:+.0f} %"
            if self.body_available
            else ""
        )

    def on_adjustment_pct(self, *_a: object) -> None:
        if self._populating:
            return
        self._refresh_labels()

    def on_slider_changed(self, value: float) -> None:
        """Slider moved: update % and clear use-recommended when non-zero."""
        if self._populating:
            return
        self.adjustment_pct = float(value)
        use_rec = abs(float(value)) < 0.5
        if self.use_recommended != use_rec:
            self._populating = True
            self.use_recommended = use_rec
            if "use_rec_switch" in self.ids:
                self.ids.use_rec_switch.active = use_rec
            self._populating = False

    def on_use_switch_active(self, _inst: object, active: bool) -> None:
        """Toggle on → snap to recommended (0% adjustment)."""
        if self._populating:
            return
        if not self.body_available:
            return
        if active:
            self._populating = True
            self.adjustment_pct = 0.0
            self.use_recommended = True
            if "slider_adj" in self.ids:
                self.ids.slider_adj.value = 0.0
            self._populating = False
            self._refresh_labels()

    def save_calories(self) -> None:
        """Persist computed daily kcal."""
        if not self.body_available:
            self._gs.show_error("Complete your profile first.")
            return
        kcal = self._display_kcal()
        if kcal < 400 or kcal > 25000:
            self._gs.show_error("Enter a value between 400 and 25000 kcal")
            return
        self._gs.apply_manual_calorie_target(kcal)
        self.dismiss()


class EditMacrosSheet(ModalView):
    """Full-screen macronutrient editor: % or grams, live chart, validation."""

    draft_protein_pct = NumericProperty(30.0)
    draft_carbs_pct = NumericProperty(40.0)
    draft_fat_pct = NumericProperty(30.0)
    validation_message = StringProperty("")
    can_save = BooleanProperty(False)
    input_mode = StringProperty("percent")
    mode_display_text = StringProperty("Percentages")
    unit_suffix = StringProperty("%")
    sheet_carbs_breakdown_text = StringProperty(
        f"[color={COLOR_CARBS}]Carbohydrate[/color]\n— g\n— kcal"
    )
    sheet_protein_breakdown_text = StringProperty(
        f"[color={COLOR_PROTEIN}]Protein[/color]\n— g\n— kcal"
    )
    sheet_fat_breakdown_text = StringProperty(
        f"[color={COLOR_FAT}]Fat[/color]\n— g\n— kcal"
    )

    def __init__(self, goals_screen: "GoalsScreen", **kwargs: object) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._gs = goals_screen
        self._initial_goal_pct: tuple[float, float, float] = (30.0, 40.0, 30.0)
        self._populating = False

    def on_input_mode(self, *args: object) -> None:
        """Update labels when switching % / g."""
        value = args[-1] if args else self.input_mode
        self.mode_display_text = "Percentages" if value == "percent" else "Grams"
        self.unit_suffix = "%" if value == "percent" else "g"

    def populate(self) -> None:
        """Prefill inputs and chart from Goals screen; reset dirty baseline."""
        self._populating = True
        self.input_mode = "percent"
        self.mode_display_text = "Percentages"
        self.unit_suffix = "%"
        p = float(self._gs.protein_pct)
        c = float(self._gs.carbs_pct)
        f = float(self._gs.fat_pct)
        self.draft_protein_pct = p
        self.draft_carbs_pct = c
        self.draft_fat_pct = f
        self._initial_goal_pct = (round(p, 2), round(c, 2), round(f, 2))
        if "protein_input" not in self.ids:
            self._populating = False
            Clock.schedule_once(lambda _dt: self.populate(), 0)
            return
        self.ids.protein_input.text = f"{p:.0f}"
        self.ids.carbs_input.text = f"{c:.0f}"
        self.ids.fat_input.text = f"{f:.0f}"
        self._populating = False
        self._refresh_validation()

    def _refresh_breakdown(self) -> None:
        """Live grams + kcal per macro from draft % and daily calorie target."""
        cal = self._gs.get_calorie_target_optional()
        if cal is None or cal <= 0:
            self.sheet_carbs_breakdown_text = (
                f"[color={COLOR_CARBS}]Carbohydrate[/color]\n— g\n— kcal"
            )
            self.sheet_protein_breakdown_text = (
                f"[color={COLOR_PROTEIN}]Protein[/color]\n— g\n— kcal"
            )
            self.sheet_fat_breakdown_text = (
                f"[color={COLOR_FAT}]Fat[/color]\n— g\n— kcal"
            )
            return

        p_pct = float(self.draft_protein_pct)
        c_pct = float(self.draft_carbs_pct)
        f_pct = float(self.draft_fat_pct)

        protein_kcal = cal * (p_pct / 100.0)
        carbs_kcal = cal * (c_pct / 100.0)
        fat_kcal = cal * (f_pct / 100.0)

        protein_g = protein_kcal / KCAL_PER_G_PROTEIN
        carbs_g = carbs_kcal / KCAL_PER_G_CARBS
        fat_g = fat_kcal / KCAL_PER_G_FAT

        self.sheet_carbs_breakdown_text = (
            f"[color={COLOR_CARBS}]Carbohydrate[/color]\n"
            f"[b]{carbs_g:.0f} g[/b]\n{carbs_kcal:.0f} kcal"
        )
        self.sheet_protein_breakdown_text = (
            f"[color={COLOR_PROTEIN}]Protein[/color]\n"
            f"[b]{protein_g:.0f} g[/b]\n{protein_kcal:.0f} kcal"
        )
        self.sheet_fat_breakdown_text = (
            f"[color={COLOR_FAT}]Fat[/color]\n"
            f"[b]{fat_g:.0f} g[/b]\n{fat_kcal:.0f} kcal"
        )

    @staticmethod
    def _grams_to_pct(
        pg: float, cg: float, fg: float
    ) -> tuple[float, float, float]:
        pk = pg * KCAL_PER_G_PROTEIN
        ck = cg * KCAL_PER_G_CARBS
        fk = fg * KCAL_PER_G_FAT
        total = pk + ck + fk
        if total <= 0:
            return (0.0, 0.0, 0.0)
        return (
            100.0 * pk / total,
            100.0 * ck / total,
            100.0 * fk / total,
        )

    def _pct_to_grams(
        self, p: float, c: float, f: float, calorie_target: float
    ) -> tuple[float, float, float]:
        pk = calorie_target * (p / 100.0)
        ck = calorie_target * (c / 100.0)
        fk = calorie_target * (f / 100.0)
        return (
            pk / KCAL_PER_G_PROTEIN,
            ck / KCAL_PER_G_CARBS,
            fk / KCAL_PER_G_FAT,
        )

    def _apply_pcts_from_grams(self, pg: float, cg: float, fg: float) -> None:
        pp, cp, fp = self._grams_to_pct(pg, cg, fg)
        self.draft_protein_pct = pp
        self.draft_carbs_pct = cp
        self.draft_fat_pct = fp

    def sync_from_field(self, which: str, text: str) -> None:
        """Update draft chart values when a field changes (% or g)."""
        if self._populating:
            return
        try:
            v = float((text or "").strip() or "0")
        except ValueError:
            v = 0.0
        if self.input_mode == "percent":
            if which == "carbs":
                self.draft_carbs_pct = v
            elif which == "protein":
                self.draft_protein_pct = v
            else:
                self.draft_fat_pct = v
        else:
            try:
                p = float(self.ids.protein_input.text.strip() or "0")
                c = float(self.ids.carbs_input.text.strip() or "0")
                f = float(self.ids.fat_input.text.strip() or "0")
            except (ValueError, KeyError, AttributeError):
                p, c, f = 0.0, 0.0, 0.0
            if which == "carbs":
                c = v
            elif which == "protein":
                p = v
            else:
                f = v
            self._apply_pcts_from_grams(p, c, f)
        self._refresh_validation()

    def _read_grams_tuple(self) -> tuple[float, float, float]:
        """Current protein, carbs, fat grams from fields (grams mode)."""
        try:
            p = float(self.ids.protein_input.text.strip() or "0")
            c = float(self.ids.carbs_input.text.strip() or "0")
            f = float(self.ids.fat_input.text.strip() or "0")
        except (ValueError, KeyError, AttributeError):
            return (0.0, 0.0, 0.0)
        return (p, c, f)

    def _refresh_validation(self) -> None:
        if self.input_mode == "percent":
            p, c, f = self.draft_protein_pct, self.draft_carbs_pct, self.draft_fat_pct
            total = p + c + f
            if p < 0 or c < 0 or f < 0:
                self.validation_message = "Percentages cannot be negative."
                self.can_save = False
                self._refresh_breakdown()
                return
            if abs(total - 100.0) <= 0.05:
                self.validation_message = ""
                self.can_save = True
            else:
                self.validation_message = (
                    "Percentages must total 100%.\n"
                    f"Current total: {total:.0f}%"
                )
                self.can_save = False
            self._refresh_breakdown()
            return

        pg, cg, fg = self._read_grams_tuple()
        if pg < 0 or cg < 0 or fg < 0:
            self.validation_message = "Grams cannot be negative."
            self.can_save = False
            self._refresh_breakdown()
            return
        t_kcal = pg * KCAL_PER_G_PROTEIN + cg * KCAL_PER_G_CARBS + fg * KCAL_PER_G_FAT
        if t_kcal <= 0:
            self.validation_message = "Enter at least one macro amount greater than zero."
            self.can_save = False
            self._refresh_breakdown()
            return
        self.validation_message = ""
        self.can_save = True
        self._refresh_breakdown()

    def _read_floats(self) -> tuple[float, float, float]:
        try:
            protein = float(self.ids.protein_input.text.strip())
            carbs = float(self.ids.carbs_input.text.strip())
            fat = float(self.ids.fat_input.text.strip())
        except (ValueError, KeyError, AttributeError):
            return (0.0, 0.0, 0.0)
        return (protein, carbs, fat)

    def _current_result_percentages(self) -> tuple[float, float, float]:
        """Percentages implied by current fields (for dirty check and save)."""
        if self.input_mode == "percent":
            p, c, f = self._read_floats()
            return (p, c, f)
        pg, cg, fg = self._read_grams_tuple()
        return self._grams_to_pct(pg, cg, fg)

    def _is_dirty(self) -> bool:
        try:
            p, c, f = self._current_result_percentages()
        except Exception:  # pylint: disable=broad-except
            return True
        g = self._initial_goal_pct
        return (
            abs(p - g[0]) > 0.05
            or abs(c - g[1]) > 0.05
            or abs(f - g[2]) > 0.05
        )

    def open_mode_menu(self) -> None:
        """Popup to choose Percentages vs Grams."""
        from kivymd.uix.button import MDButton, MDButtonText  # noqa: PLC0415
        from kivymd.uix.dialog import (  # noqa: PLC0415
            MDDialog,
            MDDialogButtonContainer,
            MDDialogHeadlineText,
            MDDialogSupportingText,
        )

        dlg_ref: list = []

        def pick_percent(*_a: object) -> None:
            dlg_ref[0].dismiss()
            self.set_input_mode("percent")

        def pick_grams(*_a: object) -> None:
            dlg_ref[0].dismiss()
            self.set_input_mode("grams")

        dlg = MDDialog(
            MDDialogHeadlineText(text="Set in"),
            MDDialogSupportingText(text="Choose how to enter macronutrients"),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Percentages"),
                    style="filled",
                    on_release=pick_percent,
                ),
                MDButton(
                    MDButtonText(text="Grams (g)"),
                    style="filled",
                    on_release=pick_grams,
                ),
                MDButton(
                    MDButtonText(text="Cancel"),
                    style="text",
                    on_release=lambda *_a: dlg_ref[0].dismiss(),
                ),
                orientation="vertical",
                spacing="8dp",
            ),
        )
        dlg_ref.append(dlg)
        dlg.open()

    def set_input_mode(self, mode: str) -> None:
        """Switch between % and g, converting values using daily calorie target."""
        if mode == self.input_mode:
            return
        if mode == "grams":
            cal = self._gs.get_calorie_target_optional()
            if cal is None or cal <= 0:
                self._gs.show_error("Set a daily calorie target on Goals first to use grams.")
                return
            p, c, f = self._read_floats()
            pg, cg, fg = self._pct_to_grams(p, c, f, cal)
            self._populating = True
            self.input_mode = "grams"
            self.ids.protein_input.text = f"{pg:.1f}"
            self.ids.carbs_input.text = f"{cg:.1f}"
            self.ids.fat_input.text = f"{fg:.1f}"
            self._apply_pcts_from_grams(pg, cg, fg)
            self._populating = False
            self._refresh_validation()
            return

        # grams -> percent
        pg, cg, fg = self._read_grams_tuple()
        pp, cp, fp = self._grams_to_pct(pg, cg, fg)
        self._populating = True
        self.input_mode = "percent"
        self.draft_protein_pct = pp
        self.draft_carbs_pct = cp
        self.draft_fat_pct = fp
        self.ids.protein_input.text = f"{pp:.0f}"
        self.ids.carbs_input.text = f"{cp:.0f}"
        self.ids.fat_input.text = f"{fp:.0f}"
        self._populating = False
        self._refresh_validation()

    def request_back(self) -> None:
        """Back arrow: leave immediately or confirm unsaved changes."""
        if not self._is_dirty():
            self.dismiss()
            return
        from kivymd.uix.button import MDButton, MDButtonText  # noqa: PLC0415
        from kivymd.uix.dialog import (  # noqa: PLC0415
            MDDialog,
            MDDialogButtonContainer,
            MDDialogHeadlineText,
        )

        dlg_ref: list = []

        def do_save(*_a: object) -> None:
            dlg_ref[0].dismiss()
            self.save_changes()

        def do_discard(*_a: object) -> None:
            dlg_ref[0].dismiss()
            self.dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Save changes?"),
            MDDialogButtonContainer(
                MDButton(
                    MDButtonText(text="Save"),
                    style="filled",
                    on_release=do_save,
                ),
                MDButton(
                    MDButtonText(text="Don't save"),
                    style="filled",
                    on_release=do_discard,
                ),
                MDButton(
                    MDButtonText(text="Cancel"),
                    style="text",
                    on_release=lambda *_a: dlg_ref[0].dismiss(),
                ),
                orientation="vertical",
                spacing="8dp",
            ),
        )
        dlg_ref.append(dlg)
        dlg.open()

    def save_changes(self) -> None:
        """Validate inputs and persist macro split (% always stored remotely)."""
        if self.input_mode == "grams":
            pg, cg, fg = self._read_grams_tuple()
            if pg < 0 or cg < 0 or fg < 0:
                self._gs.show_error("Grams cannot be negative")
                return
            t_kcal = (
                pg * KCAL_PER_G_PROTEIN
                + cg * KCAL_PER_G_CARBS
                + fg * KCAL_PER_G_FAT
            )
            if t_kcal <= 0:
                self._gs.show_error("Enter a valid macro split in grams")
                return
            pp, cp, fp = self._grams_to_pct(pg, cg, fg)
            self._gs.apply_macro_split(pp, cp, fp)
            self.dismiss()
            return

        try:
            protein = float(self.ids.protein_input.text.strip())
            fat = float(self.ids.fat_input.text.strip())
            carbs = float(self.ids.carbs_input.text.strip())
        except (ValueError, KeyError, AttributeError):
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
    _calorie_sheet: Optional[EditCalorieTargetSheet] = None

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
    # Calorie target editor
    # ------------------------------------------------------------------

    def get_calorie_target_optional(self) -> Optional[float]:
        """Daily kcal target from goals, or None if missing."""
        user_id = self.get_current_user_id()
        if not user_id:
            return None
        goals = self.get_repo(GoalsRepository).get_for_profile(user_id)
        if goals is None or goals.calorie_target is None:
            return None
        return float(goals.calorie_target)

    def get_tdee_and_recommended_kcal(self) -> tuple[Optional[float], Optional[float]]:
        """TDEE (maintenance) and goal-adjusted recommended kcal from profile."""
        user_id = self.get_current_user_id()
        if not user_id:
            return None, None
        profile = self.get_repo(ProfileRepository).get(user_id)
        if profile is None:
            return None, None
        if any(
            v is None
            for v in (
                profile.weight_kg,
                profile.height_cm,
                profile.age,
                profile.sex,
                profile.activity,
                profile.goal,
            )
        ):
            return None, None
        bmr = MacroCalculator.calculate_bmr(
            profile.weight_kg,
            profile.height_cm,
            profile.age,
            profile.sex,
        )
        tdee = MacroCalculator.calculate_tdee(bmr, profile.activity)
        recommended = MacroCalculator.apply_goal_modifier(tdee, profile.goal)
        return float(tdee), float(recommended)

    def open_calorie_editor(self) -> None:
        """Open the full-screen manual calorie target editor."""
        if self._calorie_sheet is None:
            self._calorie_sheet = EditCalorieTargetSheet(goals_screen=self)
        self._calorie_sheet.populate()
        self._calorie_sheet.open()

    def apply_manual_calorie_target(self, kcal: float) -> None:
        """Persist a user-entered daily kcal (does not run TDEE calculation)."""
        user_id = self.get_current_user_id()
        if not user_id:
            self.show_error("Not logged in")
            return

        from services.repository import Repository  # noqa: PLC0415

        repo: GoalsRepository = self.get_repo(GoalsRepository)
        existing = repo.get_for_profile(user_id)
        goals = Goals(
            id=existing.id if existing else Repository.new_id(),
            profile_id=user_id,
            protein_pct=self.protein_pct,
            carbs_pct=self.carbs_pct,
            fat_pct=self.fat_pct,
            diet_type=existing.diet_type if existing else "custom",
            meals_per_day=existing.meals_per_day if existing else 3,
            meal_labels=existing.meal_labels if existing else None,
            calorie_target=kcal,
            updated_at=time.time(),
        )

        self.show_loading("Saving…")
        try:
            repo.save(goals)
            self.hide_loading()
            self.show_success("Calorie target saved")
            self.ids.calorie_label.text = f"{kcal:.0f} kcal / day"
            self._update_macro_breakdown(kcal)
        except Exception as exc:  # pylint: disable=broad-except
            self.hide_loading()
            self.show_error(f"Save failed: {exc}")

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


Builder.load_file("assets/kv/goals.kv")
