"""Profile screen — summary cards + unified full-screen edit sheet.

UI components:
  PickerModal  — full-screen selection overlay (height, activity, goal)
  GenderSheet  — bottom-anchored action sheet (male / female)
  EditProfileSheet — unified form showing all six parameters
  ProfileScreen    — summary cards that open the edit sheet
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, Optional

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.uix.textinput import TextInput
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.appbar import MDTopAppBar  # noqa: F401 — registers KV Factory
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButtonText, MDIconButton

import widgets.macros_button  # noqa: F401 — registers Macros* KV rules before _KV
from widgets.macros_button import MacrosFilledButton, MacrosTextButton
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
from models.user import Goals, Profile
from utils.constants import (
    ACTIVITY_DESCRIPTIONS,
    ACTIVITY_KEY_MIGRATION,
    ACTIVITY_LABELS,
    BMI_RANGES,
    DEFAULT_MEAL_LABELS,
    get_bmi_category,
    GOAL_DESCRIPTIONS,
    GOAL_KEY_MIGRATION,
    GOAL_LABELS,
    RGBA_LINE,
    RGBA_POPUP,
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
                            size_hint_x: None
                            width: "140dp"
                            text_size: self.size
                            shorten: True
                            shorten_from: "left"

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
                            size_hint_x: None
                            width: "140dp"
                            text_size: self.size
                            shorten: True
                            shorten_from: "left"

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
                            size_hint_x: None
                            width: "140dp"
                            text_size: self.size
                            shorten: True
                            shorten_from: "left"

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
                            size_hint_x: None
                            width: "140dp"
                            text_size: self.size
                            shorten: True
                            shorten_from: "left"

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
                            size_hint_x: None
                            width: "140dp"
                            text_size: self.size
                            shorten: True
                            shorten_from: "left"

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
                            size_hint_x: None
                            width: "140dp"
                            text_size: self.size
                            shorten: True
                            shorten_from: "left"

        MDBoxLayout:
            size_hint_y: None
            height: "88dp"
            padding: ["16dp", "8dp", "16dp", "24dp"]

            MacrosFilledButton:
                on_release: root._save_and_dismiss()

                MDButtonText:
                    text: "Save"

# ── Full-screen body-fat sheet ────────────────────────────────────────────
<BodyFatSheet>:
    background: " "
    background_color: 0, 0, 0, 0
    auto_dismiss: False

    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.theme_cls.backgroundColor

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
                text: "Body Fat"
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
                        on_release: root.edit_field("waist")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Waist"
                        MDListItemTrailingSupportingText:
                            text: root.waist_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"
                            size_hint_x: None
                            width: "84dp"
                            text_size: self.size
                            shorten: True

                    MDDivider:

                    MDListItem:
                        on_release: root.edit_field("neck")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: "Neck"
                        MDListItemTrailingSupportingText:
                            text: root.neck_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"
                            size_hint_x: None
                            width: "84dp"
                            text_size: self.size
                            shorten: True

                    MDDivider:

                    MDListItem:
                        on_release: root.edit_field("hips")
                        theme_bg_color: "Custom"
                        md_bg_color: 0, 0, 0, 0
                        MDListItemHeadlineText:
                            text: root.hips_label
                        MDListItemTrailingSupportingText:
                            text: root.hips_text
                            theme_text_color: "Custom"
                            text_color: app.theme_cls.primaryColor
                            halign: "right"
                            size_hint_x: None
                            width: "84dp"
                            text_size: self.size
                            shorten: True

                MDLabel:
                    text: root.help_text
                    theme_text_color: "Secondary"
                    font_style: "Body"
                    role: "small"
                    size_hint_y: None
                    height: "36dp"
                    padding: ["2dp", "8dp", "2dp", "0dp"]

        MDBoxLayout:
            size_hint_y: None
            height: "88dp"
            padding: ["16dp", "8dp", "16dp", "24dp"]

            MacrosFilledButton:
                on_release: root.calculate_and_save()

                MDButtonText:
                    text: "Calculate"

# ── BMI ranges info sheet ────────────────────────────────────────────────
<BMISheet>:
    background: " "
    background_color: 0, 0, 0, 0
    auto_dismiss: False

    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.theme_cls.backgroundColor

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
                text: "Body Mass Index (BMI)"
                theme_text_color: "Custom"
                text_color: 1, 1, 1, 1
                font_style: "Title"
                role: "medium"
                halign: "center"
                valign: "center"

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: ["16dp", "16dp", "16dp", "24dp"]
                spacing: "12dp"
                size_hint_y: None
                height: self.minimum_height

                MDBoxLayout:
                    orientation: "vertical"
                    size_hint_y: None
                    height: "120dp"
                    padding: ["0dp", "8dp", "0dp", "8dp"]

                    MDLabel:
                        id: bmi_value_large
                        text: "—"
                        font_style: "Display"
                        role: "small"
                        halign: "center"
                        theme_text_color: "Custom"
                        text_color: 1, 1, 1, 1
                        size_hint_y: None
                        height: "48dp"

                    MDLabel:
                        id: bmi_status
                        text: ""
                        font_style: "Title"
                        role: "medium"
                        halign: "center"
                        theme_text_color: "Custom"
                        text_color: app.theme_cls.primaryColor
                        size_hint_y: None
                        height: "28dp"

                MDCard:
                    id: bmi_ranges_container
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    radius: [dp(12)]
                    padding: "0dp"
                    elevation: 0
                    md_bg_color: app.theme_cls.surfaceContainerHighColor

                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    radius: [dp(12)]
                    padding: ["16dp", "12dp", "16dp", "12dp"]
                    elevation: 0
                    md_bg_color: app.theme_cls.surfaceContainerHighColor

                    MDLabel:
                        text: "BMI is particularly inaccurate for people who are very fit or athletic, as their high muscle mass can classify them in the overweight category by BMI."
                        font_style: "Body"
                        role: "small"
                        theme_text_color: "Secondary"
                        halign: "center"
                        size_hint_y: None
                        height: "88dp"

# ── Meals customization sheet ────────────────────────────────────────────
<MealsSheet>:
    background: " "
    background_color: 0, 0, 0, 0
    auto_dismiss: False

    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: app.theme_cls.backgroundColor

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
                text: "Meals"
                theme_text_color: "Custom"
                text_color: 1, 1, 1, 1
                font_style: "Title"
                role: "medium"
                halign: "left"
                valign: "center"

        ScrollView:
            MDBoxLayout:
                orientation: "vertical"
                padding: ["16dp", "16dp", "16dp", "0dp"]
                spacing: "12dp"
                size_hint_y: None
                height: self.minimum_height

                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    radius: [dp(12)]
                    padding: ["16dp", "0dp", "16dp", "0dp"]
                    md_bg_color: 0.094, 0.098, 0.102, 1

                    BoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: "48dp"
                        spacing: dp(6)

                        MDLabel:
                            text: "Meals per day"
                            size_hint_x: 0.55
                            font_style: "Body"
                            role: "small"
                            theme_text_color: "Custom"
                            text_color: 0.92, 0.93, 0.95, 1
                            halign: "left"
                            valign: "middle"

                        TextInput:
                            id: meals_per_day_value
                            text: "3"
                            size_hint_x: 1
                            multiline: False
                            input_filter: "int"
                            halign: "right"
                            background_normal: ""
                            background_active: ""
                            background_color: 0, 0, 0, 0
                            foreground_color: 0.92, 0.93, 0.95, 1
                            cursor_color: 0, 0.588, 0.533, 1
                            cursor_width: dp(2)
                            font_size: "13sp"
                            hint_text: "1–10"
                            hint_text_color: 0.55, 0.58, 0.62, 1
                            padding: [0, dp(12), 0, dp(12)]

                MDLabel:
                    text: "Meals names"
                    font_style: "Title"
                    role: "small"
                    size_hint_y: None
                    height: "36dp"
                    padding: ["0dp", "8dp", "0dp", "0dp"]

                MDCard:
                    id: meal_names_container
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    radius: [dp(12)]
                    padding: ["16dp", "0dp", "16dp", "0dp"]
                    elevation: 0
                    md_bg_color: 0.094, 0.098, 0.102, 1

        MDBoxLayout:
            size_hint_y: None
            height: "88dp"
            padding: ["16dp", "8dp", "16dp", "24dp"]

            MacrosFilledButton:
                on_release: root._save_and_dismiss()

                MDButtonText:
                    text: "Save"
"""

_DRUM_KV = """
# ── Bottom-anchored meals-per-day drum-roll picker ────────────────────────
<MealsPerDayPickerSheet>:
    background: " "
    background_color: 0, 0, 0, 0.55
    auto_dismiss: True

    FloatLayout:
        size_hint: 1, 1

        MDCard:
            orientation: "vertical"
            size_hint_x: 1
            size_hint_y: None
            height: "428dp"
            pos_hint: {"x": 0, "y": 0}
            radius: [dp(16), dp(16), 0, 0]
            padding: "0dp"
            elevation: 4
            md_bg_color: app.theme_cls.surfaceContainerHighColor

            MDLabel:
                text: "Meals per day"
                size_hint_y: None
                height: "60dp"
                halign: "center"
                valign: "center"
                font_style: "Title"
                bold: True

            MDBoxLayout:
                id: picker_slot
                size_hint_y: 1
                padding: ["0dp", "0dp", "0dp", "0dp"]

            MDBoxLayout:
                size_hint_x: 1
                size_hint_y: None
                height: "60dp"
                padding: ["24dp", "0dp", "24dp", "16dp"]
                spacing: "12dp"
                orientation: "horizontal"

                MacrosTextButton:
                    size_hint_x: 1
                    on_release: root.dismiss()
                    MDButtonText:
                        text: "Cancel"

                MacrosFilledButton:
                    size_hint_x: 1
                    on_release: root._confirm()
                    MDButtonText:
                        text: "Ok"

# ── Bottom-anchored drum-roll height picker ───────────────────────────────
<HeightPickerSheet>:
    background: " "
    background_color: 0, 0, 0, 0.55
    auto_dismiss: True

    FloatLayout:
        size_hint: 1, 1

        MDCard:
            orientation: "vertical"
            size_hint_x: 1
            size_hint_y: None
            height: "428dp"
            pos_hint: {"x": 0, "y": 0}
            radius: [dp(16), dp(16), 0, 0]
            padding: "0dp"
            elevation: 4
            md_bg_color: app.theme_cls.surfaceContainerHighColor

            # Title — equal height with buttons
            MDLabel:
                text: "Height"
                size_hint_y: None
                height: "60dp"
                halign: "center"
                valign: "center"
                font_style: "Title"
                bold: True

            # Drum roll — fills remaining space, highlight centered
            MDBoxLayout:
                id: picker_slot
                size_hint_y: 1
                padding: ["0dp", "0dp", "0dp", "0dp"]

            # Cancel / OK row — equal height to title, no gap, centered
            MDBoxLayout:
                size_hint_x: 1
                size_hint_y: None
                height: "60dp"
                padding: ["24dp", "0dp", "24dp", "16dp"]
                spacing: "12dp"
                orientation: "horizontal"

                MacrosTextButton:
                    size_hint_x: 1
                    on_release: root.dismiss()
                    MDButtonText:
                        text: "Cancel"

                MacrosFilledButton:
                    size_hint_x: 1
                    on_release: root._confirm()
                    MDButtonText:
                        text: "Ok"
"""

Builder.load_string(_KV)
Builder.load_string(_DRUM_KV)
Builder.load_file("assets/kv/profile.kv")


def _show_range_popup(title: str, message: str) -> None:
    """Show a blocking popup that explains valid input range."""
    dlg_ref: list = []
    dlg = MDDialog(
        MDDialogHeadlineText(text=title),
        MDDialogContentContainer(
            MDLabel(text=message, halign="center"),
            orientation="vertical",
            padding=[0, dp(6), 0, dp(6)],
        ),
        MDDialogButtonContainer(
            Widget(),
            MacrosFilledButton(
                MDButtonText(text="Ok"),
                on_release=lambda x: dlg_ref[0].dismiss() if dlg_ref else None,
            ),
            spacing="8dp",
        ),
        theme_bg_color="Custom",
        md_bg_color=RGBA_POPUP,
    )
    dlg_ref.append(dlg)
    dlg.open()


# ---------------------------------------------------------------------------
# DrumRollPicker — slot-machine style integer scroll picker
# ---------------------------------------------------------------------------

class DrumRollPicker(FloatLayout):
    """A drum-roll (slot-machine) integer picker.

    Shows VISIBLE rows at once.  The centred row is the selected value,
    highlighted with a rounded-rectangle strip.  Scrolling snaps to the
    nearest integer on release.  Items fade and shrink with distance from
    the selection, mimicking a physical drum wheel.
    """

    ITEM_H: float = dp(44)
    VISIBLE: int = 7       # must be odd

    def __init__(
        self,
        min_val: int,
        max_val: int,
        initial: int,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._min = min_val
        self._max = max_val
        self._selected = max(min_val, min(max_val, initial))
        self._labels: Dict[int, Label] = {}
        self._scroll: Optional[ScrollView] = None
        self.size_hint = (1, None)
        self.height = self.VISIBLE * self.ITEM_H
        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.height = self.VISIBLE * self.ITEM_H
        self.size_hint = (1, None)
        half = self.VISIBLE // 2
        item_h = self.ITEM_H
        n = self._max - self._min + 1
        total_h = (n + 2 * half) * item_h

        scroll = ScrollView(
            size_hint=(1, 1),
            bar_width=0,
            do_scroll_x=False,
            scroll_type=["bars", "content"],
        )

        container = BoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            height=total_h,
        )

        for _ in range(half):
            container.add_widget(Widget(size_hint_y=None, height=item_h))

        for v in range(self._min, self._max + 1):
            lbl = Label(
                text=str(v),
                markup=True,
                size_hint_y=None,
                height=item_h,
                halign="center",
                valign="center",
            )
            lbl.bind(size=lbl.setter("text_size"))
            self._labels[v] = lbl
            container.add_widget(lbl)

        for _ in range(half):
            container.add_widget(Widget(size_hint_y=None, height=item_h))

        scroll.add_widget(container)
        self._scroll = scroll
        scroll.bind(scroll_y=self._on_scroll_changed)
        scroll.bind(on_scroll_stop=self._on_scroll_stopped)

        # Highlight strip — centered bar, ~85% width, rounded corners
        hl = Widget(
            size_hint=(0.85, None),
            height=item_h,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
        )
        try:
            app = MDApp.get_running_app()
            r, g, b, _ = app.theme_cls.primaryColor
        except Exception:  # noqa: BLE001
            r, g, b = 0.15, 0.5, 0.45
        with hl.canvas.before:
            Color(r, g, b, 0.35)
            rr = RoundedRectangle(pos=hl.pos, size=hl.size, radius=[dp(10)])
        hl.bind(
            pos=lambda w, p: setattr(rr, "pos", p),
            size=lambda w, s: setattr(rr, "size", s),
        )

        self.add_widget(scroll)
        self.add_widget(hl)

        self._update_labels(self._selected)
        # Delay until layout complete so scroll position and highlight align
        Clock.schedule_once(
            lambda dt: self._set_scroll(self._selected, animate=False), 0.12
        )

    # ------------------------------------------------------------------
    # Scroll helpers
    # ------------------------------------------------------------------

    def _scroll_y_for(self, value: int) -> float:
        """Scroll so value's row is centered in the viewport.

        Kivy: scroll_y=0 shows top of content, scroll_y=1 shows bottom.
        viewport_top = scroll_y * (content_h - viewport_h)
        """
        half = self.VISIBLE // 2
        n = self._max - self._min + 1
        if n <= 0:
            return 0.0
        # Center of value's row (from top of content) = (half + (v - min) + 0.5) * item_h
        # We want viewport_top = center - viewport_h/2
        viewport_top = (
            (half + (value - self._min) + 0.5) * self.ITEM_H
            - (self.VISIBLE * self.ITEM_H) / 2.0
        )
        content_h = (n + 2 * half) * self.ITEM_H
        viewport_h = self.VISIBLE * self.ITEM_H
        max_scroll = content_h - viewport_h
        if max_scroll <= 0:
            return 0.0
        return max(0.0, min(1.0, viewport_top / max_scroll))

    def _set_scroll(self, value: int, animate: bool = True) -> None:
        if self._scroll is None:
            return
        target = self._scroll_y_for(value)
        if animate:
            Animation(scroll_y=target, duration=0.12, t="out_quad").start(
                self._scroll
            )
        else:
            self._scroll.scroll_y = target
        self._selected = value
        self._update_labels(value)

    def _on_scroll_changed(self, instance: Any, scroll_y: float) -> None:
        # scroll_y=0 -> top of content, scroll_y=1 -> bottom
        n = self._max - self._min + 1
        content_h = (n + 2 * (self.VISIBLE // 2)) * self.ITEM_H
        viewport_h = self.VISIBLE * self.ITEM_H
        max_scroll = max(1, content_h - viewport_h)
        viewport_top = scroll_y * max_scroll
        center = viewport_top + viewport_h / 2.0
        half = self.VISIBLE // 2
        val = round(self._min + (center / self.ITEM_H - half - 0.5))
        val = max(self._min, min(self._max, val))
        if val != self._selected:
            old = self._selected
            self._selected = val
            span = self.VISIBLE + 1
            affected = (
                set(range(old - span, old + span + 1))
                | set(range(val - span, val + span + 1))
            )
            for v in affected:
                if self._min <= v <= self._max and v in self._labels:
                    self._style_label(self._labels[v], abs(v - val))

    def _on_scroll_stopped(self, *args: Any) -> None:
        self._set_scroll(self._selected)

    # ------------------------------------------------------------------
    # Label styling (depth illusion)
    # ------------------------------------------------------------------

    def _update_labels(self, selected: int) -> None:
        for v, lbl in self._labels.items():
            self._style_label(lbl, abs(v - selected))

    @staticmethod
    def _style_label(lbl: Label, dist: int) -> None:
        base_text = lbl.text.replace("[b]", "").replace("[/b]", "")
        if dist == 0:
            lbl.text = f"[b]{base_text}[/b]"
            lbl.font_size = "24sp"
            lbl.bold = True
            lbl.color = (1.0, 1.0, 1.0, 1.0)
        elif dist == 1:
            lbl.text = base_text
            lbl.font_size = "19sp"
            lbl.bold = False
            lbl.color = (0.85, 0.85, 0.85, 0.75)
        elif dist == 2:
            lbl.text = base_text
            lbl.font_size = "15sp"
            lbl.bold = False
            lbl.color = (0.70, 0.70, 0.70, 0.50)
        else:
            lbl.text = base_text
            lbl.font_size = "12sp"
            lbl.bold = False
            lbl.color = (0.55, 0.55, 0.55, 0.25)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def value(self) -> int:
        return self._selected

    def jump_to(self, value: int) -> None:
        """Jump to *value* instantly (no animation).  Safe to call at any time."""
        value = max(self._min, min(self._max, value))
        self._set_scroll(value, animate=False)


# ---------------------------------------------------------------------------
# HeightPickerSheet — bottom sheet wrapping DrumRollPicker
# ---------------------------------------------------------------------------

class HeightPickerSheet(ModalView):
    """Bottom sheet containing a drum-roll height picker (80–250 cm)."""

    def __init__(
        self, initial: int, callback: Callable[[int], None], **kwargs: Any
    ) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._callback = callback
        self._drum = DrumRollPicker(
            min_val=80, max_val=250, initial=max(80, min(250, initial))
        )
        self.ids.picker_slot.add_widget(self._drum)

    def update_value(self, value: int) -> None:
        """Reposition the drum roll to *value* before reopening."""
        self._drum.jump_to(max(80, min(250, value)))

    def _confirm(self) -> None:
        if self._callback:
            self._callback(self._drum.value)
        self.dismiss()


# ---------------------------------------------------------------------------
# MealsPerDayPickerSheet — drum-roll picker for 1–10 meals
# ---------------------------------------------------------------------------

class MealsPerDayPickerSheet(ModalView):
    """Bottom sheet containing a drum-roll picker for 1–10 meals per day."""

    def __init__(
        self,
        initial: int,
        callback: Callable[[int], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._callback = callback
        self._drum = DrumRollPicker(
            min_val=1,
            max_val=10,
            initial=max(1, min(10, initial)),
        )
        self.ids.picker_slot.add_widget(self._drum)

    def update_value(self, value: int) -> None:
        """Reposition the drum roll to *value* before reopening."""
        self._drum.jump_to(max(1, min(10, value)))

    def _confirm(self) -> None:
        if self._callback:
            self._callback(self._drum.value)
        self.dismiss()


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
# BodyFatSheet — full-screen circumference input sheet
# ---------------------------------------------------------------------------

class BodyFatSheet(ModalView):
    """Full-screen sheet for body-fat circumference inputs."""

    waist_text = StringProperty("—")
    neck_text = StringProperty("—")
    hips_text = StringProperty("—")
    hips_label = StringProperty("Hips")
    help_text = StringProperty("")
    female_mode = BooleanProperty(False)

    def __init__(self, profile_screen: "ProfileScreen", **kwargs: Any) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._ps = profile_screen
        self._waist_cm: Optional[float] = None
        self._neck_cm: Optional[float] = None
        self._hips_cm: Optional[float] = None

    def populate(self) -> None:
        """Load current saved values from the profile screen."""
        self._waist_cm = self._ps._waist_cm
        self._neck_cm = self._ps._neck_cm
        self._hips_cm = self._ps._hips_cm
        self.female_mode = (self._ps._sex == "female")
        self.hips_label = "Hips" if self.female_mode else "Hips (optional)"
        self.help_text = (
            "Women: waist, hips and neck are required."
            if self.female_mode else
            "Men: waist and neck are required."
        )
        self._refresh_display()

    def _refresh_display(self) -> None:
        self.waist_text = f"{self._waist_cm:.0f} cm" if self._waist_cm else "—"
        self.neck_text = f"{self._neck_cm:.0f} cm" if self._neck_cm else "—"
        if self.female_mode:
            self.hips_text = f"{self._hips_cm:.0f} cm" if self._hips_cm else "—"
        else:
            self.hips_text = f"{self._hips_cm:.0f} cm" if self._hips_cm else "Optional"

    def edit_field(self, name: str) -> None:
        if name == "waist":
            self._open_measure_dialog(
                title="Waist",
                hint="cm (40 - 220)",
                current=self._waist_cm,
                setter=self._set_waist,
                min_value=40.0,
                max_value=220.0,
            )
            return
        if name == "neck":
            self._open_measure_dialog(
                title="Neck",
                hint="cm (20 - 70)",
                current=self._neck_cm,
                setter=self._set_neck,
                min_value=20.0,
                max_value=70.0,
            )
            return
        if name == "hips":
            if not self.female_mode:
                self._ps.show_error("Hips measurement is only required for women")
                return
            self._open_measure_dialog(
                title="Hips",
                hint="cm (50 - 250)",
                current=self._hips_cm,
                setter=self._set_hips,
                min_value=50.0,
                max_value=250.0,
            )

    def _open_measure_dialog(
        self,
        title: str,
        hint: str,
        current: Optional[float],
        setter: Callable[[float], None],
        min_value: float,
        max_value: float,
    ) -> None:
        field = MDTextField(
            hint_text=hint,
            input_filter="float",
            text=str(round(current, 1)) if current else "",
        )
        dlg_ref: list = []

        def _apply(x: Any) -> None:
            try:
                value = float(field.text)
            except ValueError:
                field.error = True
                field.helper_text = "Enter a valid number"
                field.helper_text_mode = "on_error"
                _show_range_popup(
                    title,
                    f"Please enter a valid number between {min_value:.0f} and {max_value:.0f} cm.",
                )
                return

            if value < min_value or value > max_value:
                field.error = True
                field.helper_text = f"Must be {min_value:.0f}–{max_value:.0f} cm"
                field.helper_text_mode = "on_error"
                _show_range_popup(
                    title,
                    f"Please enter a value between {min_value:.0f} and {max_value:.0f} cm.",
                )
                return

            field.error = False
            setter(value)
            self._refresh_display()
            if dlg_ref:
                dlg_ref[0].dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogContentContainer(
                field,
                orientation="vertical",
                padding=[0, dp(4), 0, dp(4)],
            ),
            MDDialogButtonContainer(
                Widget(),
                MacrosTextButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda x: dlg_ref[0].dismiss() if dlg_ref else None,
                ),
                MacrosFilledButton(MDButtonText(text="Set"), on_release=_apply),
                spacing="8dp",
            ),
            theme_bg_color="Custom",
            md_bg_color=RGBA_POPUP,
        )
        dlg_ref.append(dlg)
        dlg.open()

    def _set_waist(self, value: float) -> None:
        self._waist_cm = value

    def _set_neck(self, value: float) -> None:
        self._neck_cm = value

    def _set_hips(self, value: float) -> None:
        self._hips_cm = value

    def _validate_measurements(self) -> bool:
        if self._waist_cm is None or self._neck_cm is None:
            self._ps.show_error("Waist and neck are required")
            return False
        if not 40 <= self._waist_cm <= 220:
            self._ps.show_error("Waist must be between 40 and 220 cm")
            return False
        if not 20 <= self._neck_cm <= 70:
            self._ps.show_error("Neck must be between 20 and 70 cm")
            return False

        if self.female_mode:
            if self._hips_cm is None:
                self._ps.show_error("Hips is required for women")
                return False
            if not 50 <= self._hips_cm <= 250:
                self._ps.show_error("Hips must be between 50 and 250 cm")
                return False
            if (self._waist_cm + self._hips_cm - self._neck_cm) <= 0:
                self._ps.show_error("Check measurements: waist + hips must exceed neck")
                return False
        else:
            if (self._waist_cm - self._neck_cm) <= 0:
                self._ps.show_error("Check measurements: waist must exceed neck")
                return False
        return True

    def calculate_and_save(self) -> None:
        if not self._ps._height_cm:
            self._ps.show_error("Set height first")
            return
        if not self._ps._sex:
            self._ps.show_error("Set gender first")
            return
        if not self._validate_measurements():
            return

        body_fat = self._ps._calculate_body_fat_pct(
            height_cm=self._ps._height_cm,
            sex=self._ps._sex,
            waist_cm=self._waist_cm or 0.0,
            neck_cm=self._neck_cm or 0.0,
            hips_cm=self._hips_cm,
        )
        if body_fat is None:
            self._ps.show_error("Could not calculate body fat with these values")
            return

        self._ps._waist_cm = self._waist_cm
        self._ps._neck_cm = self._neck_cm
        self._ps._hips_cm = self._hips_cm
        self._ps._body_fat_pct = body_fat
        self._ps._refresh_display(self._ps.get_unit_system())

        user_id = self._ps.get_current_user_id()
        if user_id:
            self._ps._persist_profile(user_id)

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

        # Cached pickers
        self._height_sheet: Optional[HeightPickerSheet] = None
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
    # Height picker — drum-roll bottom sheet
    # ------------------------------------------------------------------

    def _open_height_picker(self) -> None:
        current_cm = int(self._height_cm) if self._height_cm else 163
        current_cm = max(80, min(250, current_cm))

        if self._height_sheet is None:
            self._height_sheet = HeightPickerSheet(
                initial=current_cm,
                callback=self._set_height_from_int,
            )
        else:
            self._height_sheet.update_value(current_cm)

        self._height_sheet.open()

    def _set_height_from_int(self, value: int) -> None:
        self._height_cm = float(value)
        self._refresh_display()

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
                    _show_range_popup(
                        "Weight",
                        "Please enter a value between 25 and 500 kg.",
                    )
                    return
                self._weight_kg = kg
                self._refresh_display()
                if dlg_ref:
                    dlg_ref[0].dismiss()
            except ValueError:
                field.error = True
                field.helper_text = "Enter a valid number"
                field.helper_text_mode = "on_error"
                _show_range_popup(
                    "Weight",
                    "Please enter a valid number between 25 and 500 kg.",
                )

        dlg = MDDialog(
            MDDialogHeadlineText(text="Weight"),
            MDDialogContentContainer(
                field,
                orientation="vertical",
                padding=[0, dp(4), 0, dp(4)],
            ),
            MDDialogButtonContainer(
                Widget(),
                MacrosTextButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda x: dlg_ref[0].dismiss() if dlg_ref else None,
                ),
                MacrosFilledButton(MDButtonText(text="Set"), on_release=_apply),
                spacing="8dp",
            ),
            theme_bg_color="Custom",
            md_bg_color=RGBA_POPUP,
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
                    _show_range_popup(
                        "Age",
                        "Please enter an age between 1 and 120.",
                    )
                    return
                self._age = v
                self._refresh_display()
                if dlg_ref:
                    dlg_ref[0].dismiss()
            except ValueError:
                field.error = True
                field.helper_text = "Enter a valid integer"
                field.helper_text_mode = "on_error"
                _show_range_popup(
                    "Age",
                    "Please enter an age between 1 and 120.",
                )

        dlg = MDDialog(
            MDDialogHeadlineText(text="Age"),
            MDDialogContentContainer(
                field,
                orientation="vertical",
                padding=[0, dp(4), 0, dp(4)],
            ),
            MDDialogButtonContainer(
                Widget(),
                MacrosTextButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda x: dlg_ref[0].dismiss() if dlg_ref else None,
                ),
                MacrosFilledButton(MDButtonText(text="Set"), on_release=_apply),
                spacing="8dp",
            ),
            theme_bg_color="Custom",
            md_bg_color=RGBA_POPUP,
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
# BMISheet — BMI value, ranges, and info
# ---------------------------------------------------------------------------

class BMISheet(ModalView):
    """Full-screen sheet showing BMI value, classification ranges, and info."""

    def __init__(self, profile_screen: ProfileScreen, **kwargs: Any) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._ps = profile_screen

    def populate(self) -> None:
        """Load BMI from profile and build the ranges list."""
        bmi: Optional[float] = None
        if self._ps._height_cm and self._ps._weight_kg and self._ps._height_cm > 0:
            height_m = self._ps._height_cm / 100.0
            bmi = self._ps._weight_kg / (height_m * height_m)

        ids = self.ids
        ids.bmi_value_large.text = f"{bmi:.2f}" if bmi else "—"
        category = get_bmi_category(bmi) if bmi else None
        ids.bmi_status.text = category or ""

        container = ids.bmi_ranges_container
        container.clear_widgets()

        for i, (range_str, label, _lo, _hi) in enumerate(BMI_RANGES):
            is_highlighted = (
                bmi is not None
                and _lo <= bmi < _hi
            )
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(48),
                padding=["16dp", "8dp", "16dp", "8dp"],
            )
            if is_highlighted:
                row.theme_bg_color = "Custom"
                row.md_bg_color = (1, 1, 1, 1)
            range_lbl = MDLabel(
                text=range_str,
                size_hint_x=0.35,
                halign="left",
                theme_text_color="Custom" if is_highlighted else "Secondary",
                text_color=(0, 0, 0, 1) if is_highlighted else (0.7, 0.7, 0.7, 1),
            )
            cat_lbl = MDLabel(
                text=label,
                size_hint_x=0.65,
                halign="left",
                theme_text_color="Custom" if is_highlighted else "Secondary",
                text_color=(0, 0, 0, 1) if is_highlighted else (0.7, 0.7, 0.7, 1),
            )
            row.add_widget(range_lbl)
            row.add_widget(cat_lbl)
            container.add_widget(row)
            if i < len(BMI_RANGES) - 1:
                container.add_widget(
                    MDDivider(theme_divider_color="Custom", color=RGBA_LINE)
                )


# ---------------------------------------------------------------------------
# MealsSheet — meals per day + meal names
# ---------------------------------------------------------------------------

class MealsSheet(ModalView):
    """Full-screen sheet to configure meals per day and meal names."""

    _WHITE = [0.92, 0.93, 0.95, 1]
    _HINT  = [0.55, 0.58, 0.62, 1]
    _TEAL  = [0.0, 0.588, 0.533, 1.0]

    def __init__(self, profile_screen: ProfileScreen, **kwargs: Any) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._ps = profile_screen
        self._meals_per_day: int = 3
        self._meal_labels: Dict[int, str] = {}
        self._meal_fields: Dict[int, TextInput] = {}

    def populate(self) -> None:
        """Load current goals and build the form."""
        user_id = self._ps.get_current_user_id()
        if not user_id:
            return
        goals_repo: GoalsRepository = self._ps.get_repo(GoalsRepository)
        goals = goals_repo.get_for_profile(user_id)
        if goals:
            self._meals_per_day = goals.meals_per_day
            self._meal_labels = dict(goals.meal_labels or {})
        else:
            self._meals_per_day = 3
            self._meal_labels = {}

        self._sync_meal_labels_to_count()
        self.ids.meals_per_day_value.text = str(self._meals_per_day)
        self._build_meal_name_rows()
        # Rebuild name rows live as the user types a new count
        self.ids.meals_per_day_value.bind(text=self._on_count_text_changed)

    def _on_count_text_changed(self, _inst: object, text: str) -> None:
        """Called on every keystroke in the meals-per-day field."""
        try:
            n = max(1, min(10, int(text)))
        except (ValueError, TypeError):
            return
        if n != self._meals_per_day:
            self._meals_per_day = n
            self._sync_meal_labels_to_count()
            self._build_meal_name_rows()

    def _sync_meal_labels_to_count(self) -> None:
        """Ensure _meal_labels has entries 1..N; fill gaps from DEFAULT_MEAL_LABELS."""
        defaults = {i: DEFAULT_MEAL_LABELS.get(i, f"Meal {i}") for i in range(1, 11)}
        for i in range(1, self._meals_per_day + 1):
            if i not in self._meal_labels:
                self._meal_labels[i] = defaults.get(i, f"Meal {i}")
        to_drop = [k for k in self._meal_labels if k > self._meals_per_day]
        for k in to_drop:
            del self._meal_labels[k]

    def _build_meal_name_rows(self) -> None:
        """Populate meal_names_container with food-edit-screen style rows."""
        container = self.ids.meal_names_container
        # Snapshot current field values before clearing
        for i, field in self._meal_fields.items():
            v = (field.text or "").strip()
            if v:
                self._meal_labels[i] = v
        container.clear_widgets()
        self._meal_fields.clear()

        for i in range(1, self._meals_per_day + 1):
            row = BoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(48),
                spacing=dp(6),
            )
            lbl = MDLabel(
                text=f"Meal {i}",
                size_hint_x=0.55,
                font_style="Body",
                role="small",
                theme_text_color="Custom",
                text_color=self._WHITE,
                halign="left",
                valign="middle",
            )
            lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
            row.add_widget(lbl)

            field = TextInput(
                text=self._meal_labels.get(i, ""),
                size_hint_x=1,
                multiline=False,
                halign="right",
                background_normal="",
                background_active="",
                background_color=(0, 0, 0, 0),
                foreground_color=self._WHITE,
                cursor_color=self._TEAL,
                cursor_width=dp(2),
                selection_color=[0.0, 0.588, 0.533, 0.25],
                font_size=sp(13),
                hint_text=DEFAULT_MEAL_LABELS.get(i, f"Meal {i}"),
                hint_text_color=self._HINT,
            )
            field.bind(height=lambda w, h: setattr(w, "padding", [0, h * 0.25, 0, 0]))
            self._meal_fields[i] = field
            row.add_widget(field)
            container.add_widget(row)
            if i < self._meals_per_day:
                container.add_widget(
                    MDDivider(theme_divider_color="Custom", color=RGBA_LINE)
                )

    def _save_and_dismiss(self) -> None:
        """Collect values, validate count, save to goals, dismiss."""
        # Read confirmed meals-per-day from the text field
        try:
            n = max(1, min(10, int(self.ids.meals_per_day_value.text or "3")))
        except (ValueError, TypeError):
            n = self._meals_per_day
        self._meals_per_day = n
        self._sync_meal_labels_to_count()

        for i, field in self._meal_fields.items():
            name = (field.text or "").strip()
            self._meal_labels[i] = name or DEFAULT_MEAL_LABELS.get(i, f"Meal {i}")

        user_id = self._ps.get_current_user_id()
        if not user_id:
            self.dismiss()
            return

        goals_repo: GoalsRepository = self._ps.get_repo(GoalsRepository)
        goals = goals_repo.get_for_profile(user_id)
        if not goals:
            goals = Goals(
                id=goals_repo.new_id(),
                profile_id=user_id,
                updated_at=time.time(),
            )
        goals.meals_per_day = self._meals_per_day
        goals.meal_labels = dict(self._meal_labels)
        goals.updated_at = time.time()
        goals_repo.save(goals)

        self._ps._refresh_display(self._ps.get_unit_system())
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
    _waist_cm: Optional[float] = None
    _neck_cm: Optional[float] = None
    _hips_cm: Optional[float] = None
    _body_fat_pct: Optional[float] = None
    _meals_per_day: int = 3
    _meal_labels: Dict[int, str] = {}

    _edit_sheet: Optional[EditProfileSheet] = None
    _body_fat_sheet: Optional[BodyFatSheet] = None
    _bmi_sheet: Optional[BMISheet] = None
    _meals_sheet: Optional[MealsSheet] = None

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
        self._waist_cm = profile.waist_cm
        self._neck_cm = profile.neck_cm
        self._hips_cm = profile.hips_cm
        self._body_fat_pct = profile.body_fat_pct

        goals_repo = self.get_repo(GoalsRepository)
        goals = goals_repo.get_for_profile(user_id)
        self._meals_per_day = goals.meals_per_day if goals else 3
        self._meal_labels = dict(goals.meal_labels or {}) if goals else {}

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

        if self._height_cm and self._weight_kg and self._height_cm > 0:
            height_m = self._height_cm / 100.0
            bmi = self._weight_kg / (height_m * height_m)
            ids.bmi_value.text = f"{bmi:.2f}"
        else:
            ids.bmi_value.text = "—"

        if self._height_cm and self._weight_kg and self._age and self._sex:
            bmr = MacroCalculator.calculate_bmr(
                weight_kg=self._weight_kg,
                height_cm=self._height_cm,
                age=self._age,
                sex=self._sex,
            )
            ids.bmr_value.text = f"{bmr:.0f} kcal"
        else:
            ids.bmr_value.text = "—"

        if self._weight_kg:
            # Practical baseline hydration target.
            water_ml = int(round(self._weight_kg * 35.0))
            ids.water_value.text = f"{water_ml} ml"
        else:
            ids.water_value.text = "—"

        ids.body_fat_value.text = (
            f"{self._body_fat_pct:.1f} %" if self._body_fat_pct is not None else "Tap to calculate"
        )
        ids.customize_meals_summary.text = f"{self._meals_per_day} meals"

    # ------------------------------------------------------------------
    # Edit sheet
    # ------------------------------------------------------------------

    def open_edit_sheet(self) -> None:
        """Build (once) and open the unified edit sheet."""
        if self._edit_sheet is None:
            self._edit_sheet = EditProfileSheet(profile_screen=self)
        self._edit_sheet.populate()
        self._edit_sheet.open()

    def open_bmi_info(self) -> None:
        """Open the BMI ranges explanation sheet."""
        if self._bmi_sheet is None:
            self._bmi_sheet = BMISheet(profile_screen=self)
        self._bmi_sheet.populate()
        self._bmi_sheet.open()

    def open_body_fat_dialog(self) -> None:
        """Open the full-screen body-fat calculator sheet."""
        if not self._height_cm or not self._sex:
            self.show_error("Set height and gender first")
            return

        if self._body_fat_sheet is None:
            self._body_fat_sheet = BodyFatSheet(profile_screen=self)
        self._body_fat_sheet.populate()
        self._body_fat_sheet.open()

    def open_customize_meals(self) -> None:
        """Open the meals customization sheet."""
        if self._meals_sheet is None:
            self._meals_sheet = MealsSheet(profile_screen=self)
        self._meals_sheet.populate()
        self._meals_sheet.open()

    @staticmethod
    def _calculate_body_fat_pct(
        height_cm: float,
        sex: str,
        waist_cm: float,
        neck_cm: float,
        hips_cm: Optional[float] = None,
    ) -> Optional[float]:
        """Return body-fat percentage using the U.S. Navy circumference formula."""
        if height_cm <= 0 or waist_cm <= 0 or neck_cm <= 0:
            return None

        try:
            if sex == "male":
                diff = waist_cm - neck_cm
                if diff <= 0:
                    return None
                value = (
                    495.0
                    / (1.0324 - 0.19077 * math.log10(diff) + 0.15456 * math.log10(height_cm))
                ) - 450.0
                return round(max(0.0, value), 1)

            if hips_cm is None or hips_cm <= 0:
                return None
            diff = waist_cm + hips_cm - neck_cm
            if diff <= 0:
                return None
            value = (
                495.0
                / (1.29579 - 0.35004 * math.log10(diff) + 0.22100 * math.log10(height_cm))
            ) - 450.0
            return round(max(0.0, value), 1)
        except (ValueError, ZeroDivisionError):
            return None

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
            waist_cm=self._waist_cm,
            neck_cm=self._neck_cm,
            hips_cm=self._hips_cm,
            body_fat_pct=self._body_fat_pct,
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
