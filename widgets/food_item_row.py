"""Single food item row displayed inside a MealCard.

Left column  (60 %): food name (bold, left) + quantity line (secondary, left).
Right column (40 %): calories (primary colour, right) + C/P/F macros (right,
                     letter in macro colour / value in white).
Swipe left on the row to reveal a delete zone; tap Delete to remove. Tap content to edit
when closed, or dismiss the delete zone when open. Swipe right or tap outside to close.
"""

from __future__ import annotations

from typing import Any, Optional

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import (
    AliasProperty,
    BooleanProperty,
    NumericProperty,
    StringProperty,
)
from kivy.uix.behaviors import ButtonBehavior
from kivy.utils import get_hex_from_color
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.relativelayout import MDRelativeLayout

from utils.constants import RGBA_CARBS, RGBA_FAT, RGBA_PRIMARY, RGBA_PROTEIN

# Pre-computed hex colour tags for Kivy markup
_C_HEX = get_hex_from_color(tuple(RGBA_CARBS[:4]))
_P_HEX = get_hex_from_color(tuple(RGBA_PROTEIN[:4]))
_F_HEX = get_hex_from_color(tuple(RGBA_FAT[:4]))


def _metric_to_px(value) -> float:
    """Convert padding/spacing from KV (e.g. '3dp') or numeric to pixels."""
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if s.endswith("dp"):
        return float(dp(float(s[:-2])))
    if s.endswith("sp"):
        return float(sp(float(s[:-2])))
    if s.endswith("px"):
        return float(s[:-2])
    try:
        return float(s)
    except ValueError:
        return 0.0


class DeleteSwipeButton(ButtonBehavior, MDBoxLayout):
    """Red tappable delete strip (trash icon + label)."""


class FoodItemTapArea(MDBoxLayout):
    """Row content; handles swipe / tap and forwards to FoodItemRow."""

    _row: Any = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Clock.schedule_once(self._bind_row, 0)

    def _bind_row(self, _dt: Optional[float]) -> None:
        p = self.parent
        if p is not None and p.__class__.__name__ == "FoodItemRow":
            self._row = p

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        touch.grab(self)
        touch.ud["fip_start_x"] = touch.x
        touch.ud["fip_start_y"] = touch.y
        touch.ud["fip_acc_dx"] = 0.0
        touch.ud["fip_acc_dy"] = 0.0
        touch.ud["fip_moved"] = False
        return True

    def on_touch_move(self, touch):
        if touch.grab_current is not self:
            return super().on_touch_move(touch)
        row = self._row
        if row is None:
            return True
        touch.ud["fip_acc_dx"] = touch.ud.get("fip_acc_dx", 0.0) + float(touch.dx)
        touch.ud["fip_acc_dy"] = touch.ud.get("fip_acc_dy", 0.0) + float(touch.dy)
        acc_dx = touch.ud["fip_acc_dx"]
        acc_dy = touch.ud["fip_acc_dy"]
        if abs(acc_dx) > 8 or abs(acc_dy) > 8:
            touch.ud["fip_moved"] = True
        thr = dp(40)
        if abs(acc_dx) > abs(acc_dy):
            if acc_dx <= -thr:
                row._reveal_delete()
            elif acc_dx >= thr and row.delete_revealed:
                row._hide_delete()
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            row = self._row
            if row is None:
                return True
            dx = touch.x - touch.ud.get("fip_start_x", touch.x)
            dy = touch.y - touch.ud.get("fip_start_y", touch.y)
            moved = touch.ud.get("fip_moved", False)
            if not row.delete_revealed:
                if not moved and abs(dx) < dp(12) and abs(dy) < dp(12):
                    row.dispatch("on_edit", row.item_id)
            else:
                if not moved and abs(dx) < dp(12) and abs(dy) < dp(12):
                    row._hide_delete()
            return True
        return super().on_touch_up(touch)


Builder.load_string("""
#:import RGBA_PRIMARY utils.constants.RGBA_PRIMARY

<FoodItemTapArea>:
    orientation: "horizontal"
    md_bg_color: app.theme_cls.surfaceContainerLowestColor

<DeleteSwipeButton>:
    orientation: "horizontal"
    spacing: "4dp"
    padding: ["4dp", "0dp", "4dp", "0dp"]
    md_bg_color: 0.88, 0.22, 0.22, 1
    ripple_color: 1, 1, 1, 0.25

<FoodItemRow>:
    size_hint_y: None
    padding: ["8dp", "3dp", "8dp", "3dp"]

    # Right ~20%: delete action (hidden until revealed)
    DeleteSwipeButton:
        id: delete_zone
        size_hint_x: 0.2
        size_hint_y: 1
        pos_hint: {"right": 1, "top": 1}
        opacity: root.delete_button_opacity
        disabled: root.delete_button_opacity < 0.01
        on_release: root.dispatch("on_delete", root.item_id)

        MDIcon:
            icon: "delete"
            icon_size: "20sp"
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
            pos_hint: {"center_y": 0.5}
            size_hint_x: None
            width: "28dp"

        MDLabel:
            text: "Delete"
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
            font_style: "Title"
            role: "small"
            size_hint_x: 1
            halign: "left"
            shorten: True
            pos_hint: {"center_y": 0.5}

    FoodItemTapArea:
        id: tap
        size_hint_x: root.tap_width_hint
        size_hint_y: None
        height: self.minimum_height
        pos_hint: {"x": 0, "top": 1}

        # ── Left 60 %: name + quantity, left-aligned ──────────────────────
        MDBoxLayout:
            orientation: "vertical"
            size_hint_x: 0.6
            size_hint_y: None
            height: self.minimum_height
            spacing: "0dp"

            MDLabel:
                text: root.food_name
                theme_font_size: "Custom"
                font_size: "14sp"
                bold: True
                halign: "left"
                size_hint_y: None
                height: self.texture_size[1]
                text_size: self.width, None
                shorten: True
                shorten_from: "right"

            MDLabel:
                text: f"{root.quantity_g:.0f}g"
                theme_font_size: "Custom"
                font_size: "12sp"
                halign: "left"
                size_hint_y: None
                height: self.texture_size[1]
                theme_text_color: "Secondary"

        # ── Right 40 %: calories + macros, right-aligned ─────────────────
        MDBoxLayout:
            orientation: "vertical"
            size_hint_x: 0.4
            size_hint_y: None
            height: self.minimum_height
            spacing: "0dp"

            MDLabel:
                text: f"{root.calories:.0f}"
                theme_font_size: "Custom"
                font_size: "14sp"
                bold: True
                halign: "right"
                text_size: self.size
                size_hint_y: None
                height: self.texture_size[1]
                theme_text_color: "Custom"
                text_color: RGBA_PRIMARY[:4]

            MDLabel:
                text: root.macro_line
                markup: True
                theme_font_size: "Custom"
                font_size: "12sp"
                halign: "right"
                text_size: self.size
                size_hint_y: None
                height: self.texture_size[1]
                theme_text_color: "Custom"
                text_color: 1, 1, 1, 1
""")


class FoodItemRow(MDRelativeLayout):
    """A single row in a meal card representing one logged food item.

    Attributes:
        item_id:    UUID of the MealItem this row represents.
        food_name:  Display name of the food product.
        quantity_g: Consumed quantity in grams.
        calories:   Scaled calorie count for this quantity.
        protein_g:  Scaled protein grams.
        carbs_g:    Scaled carbohydrate grams.
        fat_g:      Scaled fat grams.

    Events:
        on_delete: Fired when the delete button is tapped; passes item_id.
        on_edit:   Fired when the row content is tapped (edit); passes item_id.
    """

    item_id = StringProperty("")
    food_name = StringProperty("")
    quantity_g = NumericProperty(100.0)
    calories = NumericProperty(0.0)
    protein_g = NumericProperty(0.0)
    carbs_g = NumericProperty(0.0)
    fat_g = NumericProperty(0.0)

    delete_revealed = BooleanProperty(False)
    delete_button_opacity = NumericProperty(0.0)
    tap_width_hint = NumericProperty(1.0)

    def _get_macro_line(self) -> str:
        return (
            f"C: [color={_C_HEX}]{self.carbs_g:.1f}[/color]  "
            f"P: [color={_P_HEX}]{self.protein_g:.1f}[/color]  "
            f"F: [color={_F_HEX}]{self.fat_g:.1f}[/color]"
        )

    macro_line = AliasProperty(
        _get_macro_line, None, bind=["carbs_g", "protein_g", "fat_g"]
    )

    __events__ = ("on_delete", "on_edit")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._outside_bound = False
        tap = self.ids.tap
        tap.bind(height=self._sync_height)
        self.bind(padding=self._sync_height)
        self.bind(delete_button_opacity=self._on_delete_opacity)
        Clock.schedule_once(lambda _dt: self._sync_height(), 0)

    def on_parent(self, _widget, parent):
        if parent is None and self._outside_bound:
            Window.unbind(on_touch_down=self._on_window_touch_down)
            self._outside_bound = False

    def _on_delete_opacity(self, _instance, value: float) -> None:
        if value > 0.01 and not self._outside_bound:
            Window.bind(on_touch_down=self._on_window_touch_down)
            self._outside_bound = True
        elif value < 0.01 and self._outside_bound:
            Window.unbind(on_touch_down=self._on_window_touch_down)
            self._outside_bound = False

    def _touch_in_row_window(self, touch) -> bool:
        lx, ly = self.to_widget(touch.x, touch.y)
        return 0 <= lx <= self.width and 0 <= ly <= self.height

    def _on_window_touch_down(self, *args) -> None:
        # Window may dispatch (touch) or (window, touch) depending on Kivy version.
        touch = args[-1]
        if self.delete_button_opacity < 0.01:
            return
        if not self._touch_in_row_window(touch):
            self._hide_delete()

    def _sync_height(self, *args) -> None:
        if "tap" not in self.ids:
            return
        pad = self.padding
        h = self.ids.tap.height + _metric_to_px(pad[1]) + _metric_to_px(pad[3])
        self.height = h

    def _reveal_delete(self) -> None:
        if self.delete_revealed:
            return
        self.delete_revealed = True
        Animation.cancel_all(self, "delete_button_opacity", "tap_width_hint")
        Animation(
            delete_button_opacity=1.0,
            tap_width_hint=0.8,
            d=0.2,
            t="out_quad",
        ).start(self)

    def _hide_delete(self) -> None:
        if not self.delete_revealed and self.delete_button_opacity < 0.01:
            return
        self.delete_revealed = False
        Animation.cancel_all(self, "delete_button_opacity", "tap_width_hint")
        Animation(
            delete_button_opacity=0.0,
            tap_width_hint=1.0,
            d=0.2,
            t="out_quad",
        ).start(self)

    def on_delete(self, item_id: str) -> None:  # noqa: ARG002
        """Default no-op (kept for API compatibility)."""

    def on_edit(self, item_id: str) -> None:  # noqa: ARG002
        """Default handler for on_edit (override in parent)."""
