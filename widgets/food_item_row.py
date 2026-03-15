"""Single food item row displayed inside a MealCard.

Shows the food name, quantity, calorie count, and macro breakdown per item.
Includes a delete button that fires an on_delete event.
"""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout

Builder.load_string("""
<FoodItemRow>:
    size_hint_y: None
    height: "60dp"
    padding: ["8dp", "4dp", "4dp", "4dp"]
    spacing: "8dp"

    MDBoxLayout:
        orientation: "vertical"
        size_hint_x: 1

        MDLabel:
            text: root.food_name
            font_style: "Body"
            role: "medium"
            shorten: True
            shorten_from: "right"

        MDLabel:
            text: f"{root.quantity_g:.0f}g  •  {root.calories:.0f} kcal  •  P:{root.protein_g:.1f}  C:{root.carbs_g:.1f}  F:{root.fat_g:.1f}"
            font_style: "Body"
            role: "small"
            theme_text_color: "Secondary"

    MDIconButton:
        icon: "delete-outline"
        size_hint: None, None
        size: "40dp", "40dp"
        pos_hint: {"center_y": 0.5}
        theme_icon_color: "Custom"
        icon_color: app.theme_cls.errorColor
        on_release: root.dispatch("on_delete", root.item_id)
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
    """

    item_id = StringProperty("")
    food_name = StringProperty("")
    quantity_g = NumericProperty(100.0)
    calories = NumericProperty(0.0)
    protein_g = NumericProperty(0.0)
    carbs_g = NumericProperty(0.0)
    fat_g = NumericProperty(0.0)

    __events__ = ("on_delete",)

    def on_delete(self, item_id: str) -> None:  # noqa: ARG002
        """Default handler for the on_delete event (no-op; override in parent).

        Args:
            item_id: The MealItem UUID passed from the delete button.
        """
