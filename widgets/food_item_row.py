"""Single food item row displayed inside a MealCard.

Left column  (60 %): food name (bold, left) + quantity line (secondary, left).
Right column (40 %): calories (primary colour, right) + C/P/F macros (right,
                     letter in macro colour / value in white).
Tap the row to open the nutrition editor.
"""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import AliasProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.utils import get_hex_from_color
from kivymd.uix.boxlayout import MDBoxLayout

from utils.constants import RGBA_CARBS, RGBA_FAT, RGBA_PRIMARY, RGBA_PROTEIN

# Pre-computed hex colour tags for Kivy markup
_C_HEX = get_hex_from_color(tuple(RGBA_CARBS[:4]))
_P_HEX = get_hex_from_color(tuple(RGBA_PROTEIN[:4]))
_F_HEX = get_hex_from_color(tuple(RGBA_FAT[:4]))


class FoodItemTapArea(ButtonBehavior, MDBoxLayout):
    """Tappable wrapper that fires on_release when the row is tapped."""


Builder.load_string("""
#:import RGBA_PRIMARY utils.constants.RGBA_PRIMARY

<FoodItemTapArea>:
    orientation: "horizontal"
    size_hint_x: 1
    ripple_alpha: 0.2

<FoodItemRow>:
    size_hint_y: None
    height: self.minimum_height
    padding: ["8dp", "3dp", "8dp", "3dp"]

    FoodItemTapArea:
        size_hint_x: 1
        size_hint_y: None
        height: self.minimum_height
        on_release: root.dispatch("on_edit", root.item_id)

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
                text: root._macro_line
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


class FoodItemRow(MDBoxLayout):
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
        on_delete: Kept for API compatibility; passes item_id.
        on_edit:   Fired when the row is tapped; passes item_id.
    """

    item_id = StringProperty("")
    food_name = StringProperty("")
    quantity_g = NumericProperty(100.0)
    calories = NumericProperty(0.0)
    protein_g = NumericProperty(0.0)
    carbs_g = NumericProperty(0.0)
    fat_g = NumericProperty(0.0)

    def _get_macro_line(self) -> str:
        return (
            f"[color={_C_HEX}]C[/color]: {self.carbs_g:.1f}  "
            f"[color={_P_HEX}]P[/color]: {self.protein_g:.1f}  "
            f"[color={_F_HEX}]F[/color]: {self.fat_g:.1f}"
        )

    _macro_line = AliasProperty(
        _get_macro_line, None, bind=["carbs_g", "protein_g", "fat_g"]
    )

    __events__ = ("on_delete", "on_edit")

    def on_delete(self, item_id: str) -> None:  # noqa: ARG002
        """Default no-op (kept for API compatibility)."""

    def on_edit(self, item_id: str) -> None:  # noqa: ARG002
        """Default handler for on_edit (override in parent)."""
