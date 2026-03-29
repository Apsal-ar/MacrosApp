"""Expandable meal card widget rendered on the Tracker screen.

Each card represents one meal slot for the day (e.g. Breakfast, Lunch).
It shows:
  - A read-only meal label (names are edited under Profile)
  - A list of FoodItemRow widgets for each logged item
  - Per-meal macro totals
  - An "Add food" button that fires on_add_food
"""

from __future__ import annotations

from typing import List

from kivy.lang import Builder
from kivy.properties import NumericProperty, ObjectProperty, StringProperty
from kivymd.uix.card import MDCard

from models.meal import Meal, MealItem
from widgets.food_item_row import FoodItemRow
import widgets.macros_button  # noqa: F401 — registers Macros*Button for MealCard KV

Builder.load_string("""
<MealCard>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: "8dp"
    spacing: "4dp"
    radius: [dp(12)]
    elevation: 1

    MDBoxLayout:
        size_hint_y: None
        height: "48dp"
        spacing: "8dp"

        MDLabel:
            id: label_display
            text: root.meal_label
            font_style: "Title"
            role: "medium"
            theme_text_color: "Primary"
            size_hint_x: 1
            size_hint_y: 1
            halign: "left"
            valign: "middle"
            shorten: True
            shorten_from: "right"

        MDLabel:
            id: totals_label
            text: root._totals_text
            font_style: "Body"
            role: "small"
            theme_text_color: "Secondary"
            size_hint_x: None
            width: "160dp"
            halign: "right"

    MDDivider:
        theme_divider_color: "Custom"
        color: "#94A09F"

    MDBoxLayout:
        id: items_container
        orientation: "vertical"
        size_hint_y: None
        height: self.minimum_height

    MDBoxLayout:
        size_hint_y: None
        height: "48dp"

        MacrosFilledButton:
            size_hint_x: 1
            on_release: root.dispatch("on_add_food", root.meal_id)

            MDButtonIcon:
                icon: "plus"

            MDButtonText:
                text: "Add Food"
""")


class MealCard(MDCard):
    """Card widget for one meal slot on the Tracker screen.

    Attributes:
        meal_id: UUID of the underlying Meal record.
        meal_label: Display name (set from goals / meal data; edit names in Profile).

    Events:
        on_add_food: Fired when the Add Food button is tapped; passes meal_id.
        on_delete_item: Fired when a FoodItemRow delete button is pressed; passes item_id.
        on_edit_item: Fired when a food row is tapped; passes item_id.
    """

    meal_id = StringProperty("")
    meal_label = StringProperty("")

    _protein_total = NumericProperty(0.0)
    _carbs_total = NumericProperty(0.0)
    _fat_total = NumericProperty(0.0)
    _calories_total = NumericProperty(0.0)

    __events__ = ("on_add_food", "on_delete_item", "on_edit_item")

    @property
    def _totals_text(self) -> str:
        return (
            f"{self._calories_total:.0f} kcal  "
            f"P:{self._protein_total:.0f}  "
            f"C:{self._carbs_total:.0f}  "
            f"F:{self._fat_total:.0f}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_meal(self, meal: Meal) -> None:
        """Populate the card from a Meal dataclass with items attached.

        Args:
            meal: A Meal instance with items list already populated.
        """
        self.meal_id = meal.id
        self.meal_label = meal.label
        self._rebuild_items(meal.items)
        self._recalculate_totals(meal.items)

    def add_item(self, item: MealItem) -> None:
        """Append a single MealItem row to the card without a full reload.

        Args:
            item: MealItem with scaled nutrition populated.
        """
        row = self._make_row(item)
        self.ids.items_container.add_widget(row)
        # Recalculate totals incrementally
        s = item.scaled_nutrition
        self._calories_total += s.calories
        self._protein_total += s.protein_g
        self._carbs_total += s.carbs_g
        self._fat_total += s.fat_g

    def remove_item(self, item_id: str) -> None:
        """Remove the row with matching item_id from the card.

        Args:
            item_id: UUID of the MealItem to remove.
        """
        container = self.ids.items_container
        for child in list(container.children):
            if isinstance(child, FoodItemRow) and child.item_id == item_id:
                container.remove_widget(child)
                self._resum_totals(container)
                break

    def update_item(self, item: MealItem) -> None:
        """Refresh display after quantity or underlying food data changes."""
        container = self.ids.items_container
        s = item.scaled_nutrition
        for child in container.children:
            if isinstance(child, FoodItemRow) and child.item_id == item.id:
                child.quantity_g = item.quantity_g
                child.calories = s.calories
                child.protein_g = s.protein_g
                child.carbs_g = s.carbs_g
                child.fat_g = s.fat_g
                child.food_name = item.food_name
                break
        self._resum_totals(container)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _rebuild_items(self, items: List[MealItem]) -> None:
        container = self.ids.items_container
        container.clear_widgets()
        for item in items:
            container.add_widget(self._make_row(item))

    def _make_row(self, item: MealItem) -> FoodItemRow:
        s = item.scaled_nutrition
        row = FoodItemRow(
            item_id=item.id,
            food_name=item.food_name,
            quantity_g=item.quantity_g,
            calories=s.calories,
            protein_g=s.protein_g,
            carbs_g=s.carbs_g,
            fat_g=s.fat_g,
        )
        row.bind(
            on_delete=lambda _, iid: self.dispatch("on_delete_item", iid),
            on_edit=lambda _, iid: self.dispatch("on_edit_item", iid),
        )
        return row

    def _recalculate_totals(self, items: List[MealItem]) -> None:
        self._calories_total = sum(i.scaled_nutrition.calories for i in items)
        self._protein_total = sum(i.scaled_nutrition.protein_g for i in items)
        self._carbs_total = sum(i.scaled_nutrition.carbs_g for i in items)
        self._fat_total = sum(i.scaled_nutrition.fat_g for i in items)

    def _resum_totals(self, container: object) -> None:
        rows = [w for w in container.children if isinstance(w, FoodItemRow)]
        self._calories_total = sum(r.calories for r in rows)
        self._protein_total = sum(r.protein_g for r in rows)
        self._carbs_total = sum(r.carbs_g for r in rows)
        self._fat_total = sum(r.fat_g for r in rows)

    # ------------------------------------------------------------------
    # Default event handlers
    # ------------------------------------------------------------------

    def on_add_food(self, meal_id: str) -> None:  # noqa: ARG002
        """Default no-op for on_add_food."""

    def on_delete_item(self, item_id: str) -> None:  # noqa: ARG002
        """Default no-op for on_delete_item."""

    def on_edit_item(self, item_id: str) -> None:  # noqa: ARG002
        """Default no-op for on_edit_item."""
