"""Profile screen — summary cards + unified full-screen edit sheet.

UI components:
  PickerModal  — full-screen selection overlay (height, activity, goal)
  GenderSheet  — bottom-anchored action sheet (male / female)
  EditProfileSheet — unified form showing all six parameters
  ProfileScreen    — summary cards that open the edit sheet
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.appbar import MDTopAppBar  # noqa: F401 — registers KV Factory
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogContentContainer,
    MDDialogHeadlineText,
)
from kivymd.uix.divider import MDDivider  # noqa: F401 — registers KV Factory
from kivymd.uix.label import MDLabel
from kivymd.uix.list import (
    MDList,
    MDListItem,
    MDListItemHeadlineText,
    MDListItemSupportingText,
    MDListItemTrailingIcon,
    MDListItemTrailingSupportingText,
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


# ---------------------------------------------------------------------------
# KV templates
# ---------------------------------------------------------------------------

_KV = """
# ── Full-screen radio-list picker ─────────────────────────────────────────
<PickerModal>:
    background: " "
    background_color: 0, 0, 0, 0
    auto_dismiss: False

    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.theme_cls.backgroundColor

        # Custom header — explicit colours so it is always visible
        MDBoxLayout:
            size_hint_y: None
            height: "56dp"
            md_bg_color: app.theme_cls.primaryColor
            spacing: "4dp"
            padding: ["4dp", "0dp", "16dp", "0dp"]

            MDIconButton:
                icon: "arrow-left"
                theme_icon_color: "Custom"
                icon_color: 1, 1, 1, 1
                pos_hint: {"center_y": 0.5}
                on_release: root._dismiss_with_selection()

            MDLabel:
                text: root.picker_title
                theme_text_color: "Custom"
                text_color: 1, 1, 1, 1
                font_style: "Title"
                role: "medium"
                halign: "left"
                valign: "center"

        ScrollView:
            id: scroll

            MDList:
                id: option_list

# ── Bottom-anchored gender action sheet ───────────────────────────────────
<GenderSheet>:
    background: " "
    background_color: 0, 0, 0, 0.5

    FloatLayout:
        size_hint: 1, 1

        MDBoxLayout:
            orientation: "vertical"
            adaptive_height: True
            size_hint_x: 1
            pos_hint: {"x": 0, "y": 0}
            padding: ["8dp", "0dp", "8dp", "32dp"]
            spacing: "8dp"

            MDCard:
                orientation: "vertical"
                adaptive_height: True
                radius: [dp(12)]
                padding: "0dp"
                elevation: 0

                MDListItem:
                    on_release: root.select("female")
                    theme_bg_color: "Custom"
                    md_bg_color: 0, 0, 0, 0
                    MDListItemHeadlineText:
                        text: "Female"

                MDDivider:

                MDListItem:
                    on_release: root.select("male")
                    theme_bg_color: "Custom"
                    md_bg_color: 0, 0, 0, 0
                    MDListItemHeadlineText:
                        text: "Male"

            MDCard:
                orientation: "vertical"
                adaptive_height: True
                radius: [dp(12)]
                padding: "0dp"
                elevation: 0

                MDListItem:
                    on_release: root.dismiss()
                    theme_bg_color: "Custom"
                    md_bg_color: 0, 0, 0, 0
                    MDListItemHeadlineText:
                        text: "Cancel"
                        theme_text_color: "Custom"
                        text_color: app.theme_cls.primaryColor

# ── Unified edit sheet ────────────────────────────────────────────────────
<EditProfileSheet>:
    background: " "
    background_color: 0, 0, 0, 0
    auto_dismiss: False

    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.theme_cls.backgroundColor

        # Custom header — explicit colours so it is always visible
        MDBoxLayout:
            size_hint_y: None
            height: "56dp"
            md_bg_color: app.theme_cls.primaryColor
            spacing: "4dp"
            padding: ["4dp", "0dp", "16dp", "0dp"]

            MDIconButton:
                icon: "arrow-left"
                theme_icon_color: "Custom"
                icon_color: 1, 1, 1, 1
                pos_hint: {"center_y": 0.5}
                on_release: root.dismiss()

            MDLabel:
                text: "Edit Profile"
                theme_text_color: "Custom"
                text_color: 1, 1, 1, 1
                font_style: "Title"
                role: "medium"
                halign: "left"
                valign: "center"

        ScrollView:
            size_hint_y: 1

            MDBoxLayout:
                orientation: "vertical"
                padding: ["16dp", "16dp", "16dp", "0dp"]
                size_hint_y: None
                height: self.minimum_height

                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    radius: [dp(12)]
                    padding: "0dp"
                    elevation: 0

                    MDListItem:
                        on_release: root.edit_field("height")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Height"
                        MDListItemTrailingSupportingText:
                            text: root.height_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"

                    MDDivider:

                    MDListItem:
                        on_release: root.edit_field("weight")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Weight"
                        MDListItemTrailingSupportingText:
                            text: root.weight_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"

                    MDDivider:

                    MDListItem:
                        on_release: root.edit_field("gender")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Gender"
                        MDListItemTrailingSupportingText:
                            text: root.gender_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"

                    MDDivider:

                    MDListItem:
                        on_release: root.edit_field("age")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Age"
                        MDListItemTrailingSupportingText:
                            text: root.age_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"

                    MDDivider:

                    MDListItem:
                        on_release: root.edit_field("activity")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Activity"
                        MDListItemTrailingSupportingText:
                            text: root.activity_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"

                    MDDivider:

                    MDListItem:
                        on_release: root.edit_field("goal")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Goal"
                        MDListItemTrailingSupportingText:
                            text: root.goal_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"

        MDBoxLayout:
            size_hint_y: None
            height: "88dp"
            padding: ["16dp", "8dp", "16dp", "24dp"]

            MDButton:
                style: "filled"
                size_hint_x: 1
                on_release: root._save_and_dismiss()

                MDButtonText:
                    text: "Save"
"""

Builder.load_string(_KV)
Builder.load_file("assets/kv/profile.kv")


# ---------------------------------------------------------------------------
# PickerModal — full-screen radio-list selection
# ---------------------------------------------------------------------------

class PickerModal(ModalView):
    """Reusable full-screen picker.  Call ``build()`` once, then
    ``open_with_key(key)`` every time you need to show it.
    """

    picker_title = StringProperty("")

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._callback: Optional[Callable[[str], None]] = None
        self._selected_key: Optional[str] = None
        self._icons: Dict[str, MDListItemTrailingIcon] = {}
        self._item_widgets: Dict[str, MDListItem] = {}

    # ------------------------------------------------------------------
    # Build (once)
    # ------------------------------------------------------------------

    def build(
        self,
        title: str,
        options: Dict[str, str],
        descriptions: Dict[str, str],
        callback: Callable[[str], None],
    ) -> None:
        """Populate the list.  Expensive for large option sets; call once.

        Args:
            title: Toolbar title string.
            options: Ordered dict key → display label.
            descriptions: Dict key → one-line description (may be empty).
            callback: Called with the selected key when the user goes back.
        """
        self.picker_title = title
        self._callback = callback
        self._icons.clear()
        self._item_widgets.clear()

        lst = self.ids.option_list
        lst.clear_widgets()

        try:
            secondary_color = (0.6, 0.6, 0.6, 1)
        except Exception:  # noqa: BLE001
            secondary_color = (0.6, 0.6, 0.6, 1)

        for key, label in options.items():
            trailing = MDListItemTrailingIcon(
                icon="radiobox-blank",
                theme_icon_color="Custom",
                icon_color=secondary_color,
            )
            self._icons[key] = trailing

            children: list = [MDListItemHeadlineText(text=label)]
            desc = descriptions.get(key, "")
            if desc:
                children.append(MDListItemSupportingText(text=desc))
            children.append(trailing)

            item = MDListItem(
                *children,
                on_release=lambda x, k=key: self._on_item_tapped(k),
                theme_bg_color="Custom",
                md_bg_color=(0, 0, 0, 0),
            )
            self._item_widgets[key] = item
            lst.add_widget(item)

    # ------------------------------------------------------------------
    # Open
    # ------------------------------------------------------------------

    def open_with_key(self, current_key: str, needs_scroll: bool = False) -> None:
        """Mark ``current_key`` as selected and open the modal.

        Always resets the scroll position to the top before opening so that
        short lists (Activity, Goal) never start in a mid-list position.
        For long lists (Height, 171 items) pass ``needs_scroll=True`` to
        also scroll to the selected row after the layout has been computed.

        Args:
            current_key: The option key to pre-select.
            needs_scroll: When True, scroll the list to the selected item
                after opening.  Use for large lists only.
        """
        self._apply_selection(current_key)
        # Reset to top so content never appears floating at the bottom
        try:
            self.ids.scroll.scroll_y = 1.0
        except Exception:  # noqa: BLE001
            pass
        self.open()
        if needs_scroll:
            # 0.5 s gives Kivy enough time to finish laying out the full list
            # before we ask ScrollView for widget positions
            Clock.schedule_once(lambda dt: self._scroll_to_current(), 0.5)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _primary_color(self):
        try:
            return MDApp.get_running_app().theme_cls.primaryColor
        except Exception:  # noqa: BLE001
            return (0.2, 0.6, 0.5, 1)

    def _apply_selection(self, key: str) -> None:
        """Update radio icons to reflect ``key`` as the new selection."""
        # Deselect previous
        if self._selected_key and self._selected_key in self._icons:
            self._icons[self._selected_key].icon = "radiobox-blank"
            self._icons[self._selected_key].icon_color = (0.6, 0.6, 0.6, 1)

        self._selected_key = key
        if key in self._icons:
            self._icons[key].icon = "radiobox-marked"
            self._icons[key].icon_color = self._primary_color()

    def _on_item_tapped(self, key: str) -> None:
        self._apply_selection(key)

    def _scroll_to_current(self) -> None:
        if self._selected_key and self._selected_key in self._item_widgets:
            try:
                self.ids.scroll.scroll_to(
                    self._item_widgets[self._selected_key], padding=dp(80)
                )
            except Exception:  # noqa: BLE001
                pass

    def _dismiss_with_selection(self) -> None:
        if self._callback and self._selected_key is not None:
            self._callback(self._selected_key)
        self.dismiss()


# ---------------------------------------------------------------------------
# GenderSheet — bottom action sheet (male / female only)
# ---------------------------------------------------------------------------

class GenderSheet(ModalView):
    """iOS-style bottom sheet for gender selection (Male / Female)."""

    def __init__(self, callback: Callable[[str], None], **kwargs: Any) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._callback = callback

    def select(self, key: str) -> None:
        """Apply the selection and dismiss.

        Args:
            key: 'male' or 'female'.
        """
        if self._callback:
            self._callback(key)
        self.dismiss()


# ---------------------------------------------------------------------------
# EditProfileSheet — unified full-screen edit form
# ---------------------------------------------------------------------------

class EditProfileSheet(ModalView):
    """Full-screen sheet listing all six profile parameters.

    Each row tap opens the appropriate picker or input dialog.
    Changes are held in memory; Save commits them all at once.
    """

    height_text = StringProperty("—")
    weight_text = StringProperty("—")
    gender_text = StringProperty("—")
    age_text = StringProperty("—")
    activity_text = StringProperty("—")
    goal_text = StringProperty("—")

    def __init__(self, profile_screen: ProfileScreen, **kwargs: Any) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._ps = profile_screen

        # Pending state
        self._height_cm: Optional[float] = None
        self._weight_kg: Optional[float] = None
        self._age: Optional[int] = None
        self._sex: str = "male"
        self._activity: str = "moderate"
        self._goal: str = "maintain"
        self._unit: str = "metric"

        # Cached pickers (built lazily; height has 171 items so worth caching)
        self._height_picker: Optional[PickerModal] = None
        self._gender_sheet: Optional[GenderSheet] = None

    # ------------------------------------------------------------------
    # Populate & display
    # ------------------------------------------------------------------

    def populate(self) -> None:
        """Copy current values from the owning ProfileScreen."""
        ps = self._ps
        self._height_cm = ps._height_cm
        self._weight_kg = ps._weight_kg
        self._age = ps._age
        self._sex = ps._sex
        self._activity = ps._activity
        self._goal = ps._goal
        self._unit = ps.get_unit_system()
        self._refresh_display()

    def _refresh_display(self) -> None:
        unit = self._unit
        self.height_text = (
            UnitConverter.format_height(self._height_cm, unit)
            if self._height_cm else "—"
        )
        self.weight_text = (
            UnitConverter.format_weight(self._weight_kg, unit)
            if self._weight_kg else "—"
        )
        self.gender_text = "Male" if self._sex == "male" else "Female"
        self.age_text = str(self._age) if self._age else "—"
        self.activity_text = ACTIVITY_LABELS.get(self._activity, "—")
        self.goal_text = GOAL_LABELS.get(self._goal, "—")

    # ------------------------------------------------------------------
    # Field dispatch
    # ------------------------------------------------------------------

    def edit_field(self, name: str) -> None:
        """Open the appropriate picker / dialog for the tapped row."""
        if name == "height":
            self._open_height_picker()
        elif name == "weight":
            self._open_weight_dialog()
        elif name == "gender":
            self._open_gender_sheet()
        elif name == "age":
            self._open_age_dialog()
        elif name == "activity":
            self._open_picker_fresh(
                "Activity Level", ACTIVITY_LABELS, ACTIVITY_DESCRIPTIONS,
                self._activity, self._set_activity,
            )
        elif name == "goal":
            self._open_picker_fresh(
                "Goal", GOAL_LABELS, GOAL_DESCRIPTIONS,
                self._goal, self._set_goal,
            )

    # ------------------------------------------------------------------
    # Height picker (cached — 171 items)
    # ------------------------------------------------------------------

    def _open_height_picker(self) -> None:
        current_cm = int(self._height_cm) if self._height_cm else 163
        current_cm = max(80, min(250, current_cm))

        if self._height_picker is None:
            self._height_picker = PickerModal()
            options = {str(i): f"{i} cm" for i in range(80, 251)}
            self._height_picker.build(
                title="Height",
                options=options,
                descriptions={},
                callback=self._set_height_from_key,
            )

        self._height_picker.open_with_key(str(current_cm), needs_scroll=True)

    def _set_height_from_key(self, key: str) -> None:
        try:
            self._height_cm = float(int(key))
            self._refresh_display()
        except (ValueError, TypeError):
            pass

    # ------------------------------------------------------------------
    # Weight dialog (text input, 25–500 kg)
    # ------------------------------------------------------------------

    def _open_weight_dialog(self) -> None:
        unit = self._unit
        if unit == "imperial":
            hint = "lbs  (55 – 1 100)"
            prefill = (
                str(round(UnitConverter.kg_to_lbs(self._weight_kg), 1))
                if self._weight_kg else ""
            )
        else:
            hint = "kg  (25 – 500)"
            prefill = (
                str(round(self._weight_kg, 1)) if self._weight_kg else ""
            )

        field = MDTextField(hint_text=hint, input_filter="float", text=prefill)
        dlg_ref: list = []

        def _apply(x: Any) -> None:
            try:
                v = float(field.text)
                kg = UnitConverter.lbs_to_kg(v) if unit == "imperial" else v
                if not 25.0 <= kg <= 500.0:
                    field.error = True
                    field.helper_text = "Must be 25–500 kg"
                    field.helper_text_mode = "on_error"
                    return
                self._weight_kg = kg
                self._refresh_display()
                if dlg_ref:
                    dlg_ref[0].dismiss()
            except ValueError:
                field.error = True

        dlg = MDDialog(
            MDDialogHeadlineText(text="Weight"),
            MDDialogContentContainer(
                field,
                orientation="vertical",
                padding=[0, dp(4), 0, dp(4)],
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(
                    MDButtonText(text="Cancel"),
                    style="text",
                    on_release=lambda x: dlg_ref[0].dismiss() if dlg_ref else None,
                ),
                MDButton(MDButtonText(text="Set"), style="filled", on_release=_apply),
                spacing="8dp",
            ),
        )
        dlg_ref.append(dlg)
        dlg.open()

    # ------------------------------------------------------------------
    # Gender sheet (bottom action sheet)
    # ------------------------------------------------------------------

    def _open_gender_sheet(self) -> None:
        if self._gender_sheet is None:
            self._gender_sheet = GenderSheet(callback=self._set_gender)
        self._gender_sheet.open()

    def _set_gender(self, key: str) -> None:
        self._sex = key
        self._refresh_display()

    # ------------------------------------------------------------------
    # Age dialog (text input, 1–120)
    # ------------------------------------------------------------------

    def _open_age_dialog(self) -> None:
        field = MDTextField(
            hint_text="years  (1 – 120)",
            input_filter="int",
            text=str(self._age) if self._age else "",
        )
        dlg_ref: list = []

        def _apply(x: Any) -> None:
            try:
                v = int(field.text)
                if not 1 <= v <= 120:
                    field.error = True
                    field.helper_text = "Must be 1–120"
                    field.helper_text_mode = "on_error"
                    return
                self._age = v
                self._refresh_display()
                if dlg_ref:
                    dlg_ref[0].dismiss()
            except ValueError:
                field.error = True

        dlg = MDDialog(
            MDDialogHeadlineText(text="Age"),
            MDDialogContentContainer(
                field,
                orientation="vertical",
                padding=[0, dp(4), 0, dp(4)],
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(
                    MDButtonText(text="Cancel"),
                    style="text",
                    on_release=lambda x: dlg_ref[0].dismiss() if dlg_ref else None,
                ),
                MDButton(MDButtonText(text="Set"), style="filled", on_release=_apply),
                spacing="8dp",
            ),
        )
        dlg_ref.append(dlg)
        dlg.open()

    # ------------------------------------------------------------------
    # Activity / Goal pickers (fresh each open — small lists)
    # ------------------------------------------------------------------

    def _open_picker_fresh(
        self,
        title: str,
        options: Dict[str, str],
        descriptions: Dict[str, str],
        current_key: str,
        callback: Callable[[str], None],
    ) -> None:
        picker = PickerModal()
        picker.build(
            title=title,
            options=options,
            descriptions=descriptions,
            callback=callback,
        )
        picker.open_with_key(current_key)

    def _set_activity(self, key: str) -> None:
        self._activity = key
        self._refresh_display()

    def _set_goal(self, key: str) -> None:
        self._goal = key
        self._refresh_display()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_and_dismiss(self) -> None:
        """Write all pending values back to ProfileScreen and persist."""
        ps = self._ps
        ps._height_cm = self._height_cm
        ps._weight_kg = self._weight_kg
        ps._age = self._age
        ps._sex = self._sex
        ps._activity = self._activity
        ps._goal = self._goal

        user_id = ps.get_current_user_id()
        if user_id:
            ps._persist_profile(user_id)

        ps._refresh_display(self._unit)
        self.dismiss()


# ---------------------------------------------------------------------------
# ProfileScreen
# ---------------------------------------------------------------------------

class ProfileScreen(BaseScreen):
    """Profile summary screen — three tappable cards, one unified edit sheet.

    KV file: assets/kv/profile.kv
    """

    name = "profile"

    _height_cm: Optional[float] = None
    _weight_kg: Optional[float] = None
    _age: Optional[int] = None
    _sex: str = "male"
    _activity: str = "moderate"
    _goal: str = "maintain"

    _edit_sheet: Optional[EditProfileSheet] = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_enter(self) -> None:
        Clock.schedule_once(self._load_profile, 0)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_profile(self, dt: float) -> None:  # noqa: ARG002
        user_id = self.get_current_user_id()
        if not user_id:
            return

        repo: ProfileRepository = self.get_repo(ProfileRepository)
        profile = repo.get(user_id)
        if profile is None:
            return

        unit = profile.unit_system or "metric"

        self._activity = ACTIVITY_KEY_MIGRATION.get(
            profile.activity or "moderate", profile.activity or "moderate"
        )
        self._goal = GOAL_KEY_MIGRATION.get(
            profile.goal or "maintain", profile.goal or "maintain"
        )
        self._sex = profile.sex or "male"
        self._height_cm = profile.height_cm
        self._weight_kg = profile.weight_kg
        self._age = profile.age

        self._refresh_display(unit)

    def _refresh_display(self, unit: str = "metric") -> None:
        ids = self.ids
        ids.height_value.text = (
            UnitConverter.format_height(self._height_cm, unit)
            if self._height_cm else "—"
        )
        ids.weight_value.text = (
            UnitConverter.format_weight(self._weight_kg, unit)
            if self._weight_kg else "—"
        )
        ids.gender_value.text = "Male" if self._sex == "male" else "Female"
        ids.age_value.text = str(self._age) if self._age else "—"
        ids.activity_value.text = ACTIVITY_LABELS.get(self._activity, "—")
        ids.goal_value.text = GOAL_LABELS.get(self._goal, "—")

    # ------------------------------------------------------------------
    # Edit sheet
    # ------------------------------------------------------------------

    def open_edit_sheet(self) -> None:
        """Build (once) and open the unified edit sheet."""
        if self._edit_sheet is None:
            self._edit_sheet = EditProfileSheet(profile_screen=self)
        self._edit_sheet.populate()
        self._edit_sheet.open()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def get_unit_system(self) -> str:
        user_id = self.get_current_user_id()
        if not user_id:
            return "metric"
        repo: ProfileRepository = self.get_repo(ProfileRepository)
        profile = repo.get(user_id)
        return (profile.unit_system or "metric") if profile else "metric"

    def _persist_profile(self, user_id: str) -> None:
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
