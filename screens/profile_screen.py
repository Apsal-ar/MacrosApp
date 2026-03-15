"""Profile screen — summary display with per-section edit dialogs.

The screen shows three tappable rows:
  Row 1  — height / weight / gender / age
  Row 2  — activity level
  Row 3  — goal

Tapping any row opens a focused dialog for editing that section.
All dialog content is built programmatically so there are no extra KV files.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (
    MDList,
    MDListItem,
    MDListItemHeadlineText,
    MDListItemSupportingText,
    MDListItemTrailingIcon,
)
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField

from screens.base_screen import BaseScreen
from services.macro_calculator import MacroCalculator
from services.repository import GoalsRepository, ProfileRepository
from models.user import Profile
from utils.constants import (
    ACTIVITY_DESCRIPTIONS,
    ACTIVITY_KEY_MIGRATION,
    ACTIVITY_LABELS,
    GOAL_DESCRIPTIONS,
    GOAL_KEY_MIGRATION,
    GOAL_LABELS,
)
from utils.unit_converter import UnitConverter


# MDCard in KivyMD 2.0 already inherits ButtonBehavior, so on_release
# works natively — no TappableCard wrapper needed.
Builder.load_file("assets/kv/profile.kv")


# ---------------------------------------------------------------------------
# ProfileScreen
# ---------------------------------------------------------------------------

class ProfileScreen(BaseScreen):
    """Profile summary screen with three tappable edit rows.

    KV file: assets/kv/profile.kv

    Internal state (instance variables) hold the current values and are
    written to the repository only when the user confirms in a dialog.
    """

    name = "profile"

    # Internal state
    _height_cm: Optional[float] = None
    _weight_kg: Optional[float] = None
    _age: Optional[int] = None
    _sex: str = "other"
    _activity: str = "moderate"
    _goal: str = "maintain"

    # Dialog handles
    _personal_dialog: Optional[MDDialog] = None
    _activity_dialog: Optional[MDDialog] = None
    _goal_dialog: Optional[MDDialog] = None

    # Field refs inside personal dialog
    _height_field: Optional[MDTextField] = None
    _weight_field: Optional[MDTextField] = None
    _age_field: Optional[MDTextField] = None
    _gender_buttons: Dict[str, MDButton] = {}

    # Icon refs inside selection dialogs
    _activity_icons: Dict[str, MDListItemTrailingIcon] = {}
    _goal_icons: Dict[str, MDListItemTrailingIcon] = {}
    _activity_selected: str = "moderate"
    _goal_selected: str = "maintain"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._gender_buttons = {}
        self._activity_icons = {}
        self._goal_icons = {}

    def on_enter(self) -> None:
        """Refresh display values when the screen becomes active."""
        Clock.schedule_once(self._load_profile, 0)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_profile(self, dt: float) -> None:  # noqa: ARG002
        """Read the cached profile and update all three summary rows."""
        user_id = self.get_current_user_id()
        if not user_id:
            return

        repo: ProfileRepository = self.get_repo(ProfileRepository)
        profile = repo.get(user_id)
        if profile is None:
            return

        unit = profile.unit_system

        # Migrate old activity/goal keys if needed
        raw_activity = profile.activity or "moderate"
        raw_goal = profile.goal or "maintain"
        self._activity = ACTIVITY_KEY_MIGRATION.get(raw_activity, raw_activity)
        self._goal = GOAL_KEY_MIGRATION.get(raw_goal, raw_goal)
        self._activity_selected = self._activity
        self._goal_selected = self._goal

        self._sex = profile.sex or "other"
        self._height_cm = profile.height_cm
        self._weight_kg = profile.weight_kg
        self._age = profile.age

        self._refresh_display(unit)

    def _refresh_display(self, unit: str = "metric") -> None:
        """Push current values into the three summary card labels."""
        ids = self.ids

        # Row 1 — personal stats
        if self._height_cm is not None:
            ids.height_value.text = UnitConverter.format_height(self._height_cm, unit)
        else:
            ids.height_value.text = "—"

        if self._weight_kg is not None:
            ids.weight_value.text = UnitConverter.format_weight(self._weight_kg, unit)
        else:
            ids.weight_value.text = "—"

        ids.gender_value.text = {"male": "Male", "female": "Female"}.get(self._sex, "Other")
        ids.age_value.text = str(self._age) if self._age else "—"

        # Row 2 — activity
        ids.activity_value.text = ACTIVITY_LABELS.get(self._activity, "—")

        # Row 3 — goal
        ids.goal_value.text = GOAL_LABELS.get(self._goal, "—")

    # ------------------------------------------------------------------
    # Personal data dialog
    # ------------------------------------------------------------------

    def open_personal_dialog(self) -> None:
        """Build (once) and open the personal data edit dialog."""
        if self._personal_dialog is None:
            self._personal_dialog = self._build_personal_dialog()
        self._prefill_personal_dialog()
        self._personal_dialog.open()

    def _build_personal_dialog(self) -> MDDialog:
        """Create the personal data dialog widget tree.

        Returns:
            A fully constructed MDDialog ready to be opened.
        """
        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(292),
            spacing=dp(8),
            padding=[0, dp(4), 0, dp(4)],
        )

        # Height + Weight on the same row
        hw_row = MDBoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        self._height_field = MDTextField(hint_text="Height (cm)", input_filter="float")
        self._weight_field = MDTextField(hint_text="Weight (kg)", input_filter="float")
        hw_row.add_widget(self._height_field)
        hw_row.add_widget(self._weight_field)
        content.add_widget(hw_row)

        # Age
        self._age_field = MDTextField(
            hint_text="Age",
            input_filter="int",
            size_hint_y=None,
            height=dp(56),
        )
        content.add_widget(self._age_field)

        # Gender label
        gender_label = MDLabel(
            text="Gender",
            font_style="Body",
            role="medium",
            theme_text_color="Secondary",
            size_hint_y=None,
            height=dp(24),
        )
        content.add_widget(gender_label)

        # Gender buttons (outlined → filled when selected)
        self._gender_buttons = {}
        gender_row = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        for key, label in [("male", "Male"), ("female", "Female"), ("other", "Other")]:
            def _cb(x, k=key):
                self._select_gender(k)
            btn = MDButton(
                MDButtonText(text=label),
                style="outlined",
                size_hint_x=1,
                on_release=_cb,
            )
            self._gender_buttons[key] = btn
            gender_row.add_widget(btn)
        content.add_widget(gender_row)

        # Spacer
        content.add_widget(Widget(size_hint_y=None, height=dp(8)))

        # Cancel / Save buttons
        btn_row = MDBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        btn_row.add_widget(Widget())  # left spacer
        btn_row.add_widget(
            MDButton(
                MDButtonText(text="Cancel"),
                style="text",
                on_release=lambda x: self._personal_dialog.dismiss(),
            )
        )
        btn_row.add_widget(
            MDButton(
                MDButtonText(text="Save"),
                style="filled",
                on_release=lambda x: self._save_personal(),
            )
        )
        content.add_widget(btn_row)

        return MDDialog(title="Personal Info", type="custom", content_cls=content)

    def _prefill_personal_dialog(self) -> None:
        """Populate dialog fields with the current stored values."""
        unit = self.get_unit_system()

        if self._height_cm is not None:
            val = (
                str(UnitConverter.cm_to_inches(self._height_cm))
                if unit == "imperial"
                else str(self._height_cm)
            )
            self._height_field.text = val
        else:
            self._height_field.text = ""

        if self._weight_kg is not None:
            val = (
                str(UnitConverter.kg_to_lbs(self._weight_kg))
                if unit == "imperial"
                else str(self._weight_kg)
            )
            self._weight_field.text = val
        else:
            self._weight_field.text = ""

        self._age_field.text = str(self._age) if self._age else ""
        self._select_gender(self._sex)

    def _select_gender(self, key: str) -> None:
        """Visually activate the chosen gender button and store the key.

        Args:
            key: 'male', 'female', or 'other'.
        """
        self._sex = key
        for k, btn in self._gender_buttons.items():
            btn.style = "filled" if k == key else "outlined"

    def _save_personal(self) -> None:
        """Validate personal dialog fields, persist, and close."""
        user_id = self.get_current_user_id()
        if not user_id:
            self.show_error("Not logged in")
            return

        unit = self.get_unit_system()
        try:
            raw_h = float(self._height_field.text or "0")
            raw_w = float(self._weight_field.text or "0")
            age = int(self._age_field.text or "0")
        except ValueError:
            self.show_error("Please enter valid numbers")
            return

        if raw_h <= 0 or raw_w <= 0 or age <= 0:
            self.show_error("Height, weight and age must be greater than zero")
            return

        self._height_cm = UnitConverter.inches_to_cm(raw_h) if unit == "imperial" else raw_h
        self._weight_kg = UnitConverter.lbs_to_kg(raw_w) if unit == "imperial" else raw_w
        self._age = age

        self._persist_profile(user_id)
        self._personal_dialog.dismiss()
        self._refresh_display(unit)
        self.show_success("Personal info saved")

    # ------------------------------------------------------------------
    # Activity level dialog
    # ------------------------------------------------------------------

    def open_activity_dialog(self) -> None:
        """Build (once) and open the activity level selection dialog."""
        if self._activity_dialog is None:
            self._activity_dialog = self._build_selection_dialog(
                title="Activity Level",
                options=ACTIVITY_LABELS,
                descriptions=ACTIVITY_DESCRIPTIONS,
                icons=self._activity_icons,
                current_key_getter=lambda: self._activity_selected,
                on_save=self._save_activity,
                dialog_ref_setter=lambda d: setattr(self, "_activity_dialog", d),
            )
        self._update_selection_icons(self._activity_icons, self._activity_selected)
        self._activity_dialog.open()

    def _save_activity(self) -> None:
        """Persist the selected activity level."""
        user_id = self.get_current_user_id()
        if not user_id:
            self.show_error("Not logged in")
            return
        self._activity = self._activity_selected
        self._persist_profile(user_id)
        self._activity_dialog.dismiss()
        self.ids.activity_value.text = ACTIVITY_LABELS.get(self._activity, "—")
        self.show_success("Activity level saved")

    # ------------------------------------------------------------------
    # Goal dialog
    # ------------------------------------------------------------------

    def open_goal_dialog(self) -> None:
        """Build (once) and open the goal selection dialog."""
        if self._goal_dialog is None:
            self._goal_dialog = self._build_selection_dialog(
                title="Goal",
                options=GOAL_LABELS,
                descriptions=GOAL_DESCRIPTIONS,
                icons=self._goal_icons,
                current_key_getter=lambda: self._goal_selected,
                on_save=self._save_goal,
                dialog_ref_setter=lambda d: setattr(self, "_goal_dialog", d),
            )
        self._update_selection_icons(self._goal_icons, self._goal_selected)
        self._goal_dialog.open()

    def _save_goal(self) -> None:
        """Persist the selected goal."""
        user_id = self.get_current_user_id()
        if not user_id:
            self.show_error("Not logged in")
            return
        self._goal = self._goal_selected
        self._persist_profile(user_id)
        self._goal_dialog.dismiss()
        self.ids.goal_value.text = GOAL_LABELS.get(self._goal, "—")
        self.show_success("Goal saved")

    # ------------------------------------------------------------------
    # Generic selection dialog builder (shared by activity + goal)
    # ------------------------------------------------------------------

    def _build_selection_dialog(
        self,
        title: str,
        options: Dict[str, str],
        descriptions: Dict[str, str],
        icons: Dict[str, MDListItemTrailingIcon],
        current_key_getter,
        on_save,
        dialog_ref_setter,
    ) -> MDDialog:
        """Build a radio-style list dialog for picking one option.

        Args:
            title: Dialog headline text.
            options: Ordered dict of key → display label.
            descriptions: Dict of key → one-line description.
            icons: Empty dict that will be populated with trailing icon refs.
            current_key_getter: Callable returning the currently selected key.
            on_save: Callable invoked when Save is pressed.
            dialog_ref_setter: Callable to set the dialog reference after creation.

        Returns:
            A fully constructed MDDialog.
        """
        option_list = MDList(size_hint_y=None)
        option_list.bind(minimum_height=option_list.setter("height"))

        for key, label in options.items():
            is_current = key == current_key_getter()
            trailing = MDListItemTrailingIcon(
                icon="check-circle" if is_current else "checkbox-blank-circle-outline",
                theme_icon_color="Custom",
            )
            if is_current:
                from kivymd.app import MDApp  # noqa: PLC0415
                try:
                    trailing.icon_color = MDApp.get_running_app().theme_cls.primaryColor
                except Exception:  # noqa: BLE001
                    pass
            icons[key] = trailing

            def _on_item_release(x, k=key, ig=icons):
                self._on_selection_item_tapped(k, ig, current_key_getter)

            item = MDListItem(
                MDListItemHeadlineText(text=label),
                MDListItemSupportingText(text=descriptions.get(key, "")),
                trailing,
                on_release=_on_item_release,
            )
            option_list.add_widget(item)

        scroll = MDScrollView(size_hint_y=None, height=dp(320))
        scroll.add_widget(option_list)

        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(376),
            spacing=dp(0),
            padding=[0, dp(4), 0, dp(4)],
        )
        content.add_widget(scroll)

        # Spacer + Cancel/Save row
        content.add_widget(Widget(size_hint_y=None, height=dp(8)))
        btn_row = MDBoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
        btn_row.add_widget(Widget())

        dialog_holder: list = []

        def _cancel(x):
            if dialog_holder:
                dialog_holder[0].dismiss()

        def _save(x):
            on_save()

        btn_row.add_widget(
            MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel)
        )
        btn_row.add_widget(
            MDButton(MDButtonText(text="Save"), style="filled", on_release=_save)
        )
        content.add_widget(btn_row)

        dialog = MDDialog(title=title, type="custom", content_cls=content)
        dialog_holder.append(dialog)
        dialog_ref_setter(dialog)
        return dialog

    def _on_selection_item_tapped(
        self,
        key: str,
        icons: Dict[str, MDListItemTrailingIcon],
        current_key_getter,
    ) -> None:
        """Update icon states when the user taps a selection item.

        Args:
            key: The key of the tapped option.
            icons: Dict of all icon widgets for this dialog.
            current_key_getter: Callable that returns which temp-selected key to update.
        """
        self._update_selection_icons(icons, key)
        # Determine which temp-selection variable to update
        if icons is self._activity_icons:
            self._activity_selected = key
        elif icons is self._goal_icons:
            self._goal_selected = key

    @staticmethod
    def _update_selection_icons(
        icons: Dict[str, MDListItemTrailingIcon], selected_key: str
    ) -> None:
        """Swap icon between filled-circle (selected) and outline (unselected).

        Args:
            icons: Dict mapping option keys to their trailing icon widgets.
            selected_key: The key that should show the filled icon.
        """
        for key, icon in icons.items():
            icon.icon = (
                "check-circle" if key == selected_key else "checkbox-blank-circle-outline"
            )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_profile(self, user_id: str) -> None:
        """Write current instance state to ProfileRepository and recalculate goals.

        Args:
            user_id: The authenticated user's profile UUID.
        """
        profile = Profile(
            id=user_id,
            email="",
            height_cm=self._height_cm,
            weight_kg=self._weight_kg,
            age=self._age,
            sex=self._sex,
            activity=self._activity,
            goal=self._goal,
            unit_system=self.get_unit_system(),
            updated_at=time.time(),
        )
        repo: ProfileRepository = self.get_repo(ProfileRepository)
        repo.save(profile)
        self._recalculate_goals(profile)

    def _recalculate_goals(self, profile: Profile) -> None:
        """Recalculate calorie target from updated profile and persist Goals.

        Args:
            profile: The freshly saved Profile.
        """
        if any(v is None for v in [
            profile.height_cm, profile.weight_kg,
            profile.age, profile.sex, profile.activity, profile.goal,
        ]):
            return

        goals_repo: GoalsRepository = self.get_repo(GoalsRepository)
        goals = goals_repo.get_for_profile(profile.id)
        if goals is None:
            return

        targets = MacroCalculator.calculate_targets(
            weight_kg=profile.weight_kg,
            height_cm=profile.height_cm,
            age=profile.age,
            sex=profile.sex,
            activity_level=profile.activity,
            goal=profile.goal,
            protein_pct=goals.protein_pct,
            carbs_pct=goals.carbs_pct,
            fat_pct=goals.fat_pct,
        )
        goals.calorie_target = targets["calories"]
        goals.updated_at = time.time()
        goals_repo.save(goals)
