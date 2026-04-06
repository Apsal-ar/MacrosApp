"""Single food item row displayed inside a MealCard.

Shows the food name, quantity, calorie count, and macro breakdown per item.
Tap the row to edit nutrition; delete button removes the entry.
"""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout


class FoodItemTapArea(ButtonBehavior, MDBoxLayout):
    """Tappable area (excluding delete) to open the nutrition editor."""


Builder.load_string("""
#:import dp kivy.metrics.dp
<FoodItemTapArea>:
    orientation: "horizontal"
    size_hint_x: 1
    ripple_alpha: 0.2

<FoodItemRow>:
    size_hint_y: None
    height: self.minimum_height
    padding: ["8dp", "2dp", "8dp", "2dp"]

    FoodItemTapArea:
        size_hint_x: 1
        size_hint_y: None
        height: self.minimum_height
        on_release: root.dispatch("on_edit", root.item_id)

        MDBoxLayout:
            orientation: "vertical"
            size_hint_x: 1
            size_hint_y: None
            height: self.minimum_height
            spacing: "0dp"

            MDLabel:
                text: root.food_name
                font_size: "12sp"
                size_hint_y: None
                height: self.texture_size[1]
                shorten: True
                shorten_from: "right"

            MDLabel:
                text: f"{root.quantity_g:.0f}g  •  {root.calories:.0f} kcal  •  P:{root.protein_g:.1f}  C:{root.carbs_g:.1f}  F:{root.fat_g:.1f}"
                font_size: "11sp"
                size_hint_y: None
                height: self.texture_size[1]
                theme_text_color: "Secondary"
""")


class FoodItemRow(MDBoxLayout):
    """A single row in a meal card representing one logged food item.

    Attributes:
        item_id: UUID of the MealItem this row represents.
        food_name: Display name of the food product.
        quantity_g: Consumed quantity in grams.
        calories: Scaled calorie count for this quantity.
        protein_g: Scaled protein grams.
        carbs_g: Scaled carbohydrate grams.
        fat_g: Scaled fat grams.

    Events:
        on_delete: Fired when the delete button is pressed; passes item_id.
        on_edit: Fired when the row is tapped; passes item_id.
    """

    item_id = StringProperty("")
    food_name = StringProperty("")
    quantity_g = NumericProperty(100.0)
    calories = NumericProperty(0.0)
    protein_g = NumericProperty(0.0)
    carbs_g = NumericProperty(0.0)
    fat_g = NumericProperty(0.0)

    __events__ = ("on_delete", "on_edit")

    def on_delete(self, item_id: str) -> None:  # noqa: ARG002
        """Default handler for on_delete (override in parent)."""

    def on_edit(self, item_id: str) -> None:  # noqa: ARG002
        """Default handler for on_edit (override in parent)."""
