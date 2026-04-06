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
from kivy.uix.behaviors import ButtonBehavior
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.divider import MDDivider

from models.meal import Meal, MealItem
from widgets.food_item_row import FoodItemRow


class _AddFoodBtn(ButtonBehavior, MDBoxLayout):
    """Borderless, shadowless 'Add food' button that blends into the card surface."""

Builder.load_string("""
#:import RGBA_PRIMARY utils.constants.RGBA_PRIMARY
#:import RGBA_PROTEIN utils.constants.RGBA_PROTEIN
#:import RGBA_CARBS utils.constants.RGBA_CARBS
#:import RGBA_FAT utils.constants.RGBA_FAT
#:import dp kivy.metrics.dp

<_AddFoodBtn>:
    size_hint_y: None
    height: "36dp"

    MDLabel:
        text: "[size=15sp]+[/size]  Add food"
        markup: True
        bold: True
        font_size: "12sp"
        halign: "center"
        valign: "middle"
        theme_text_color: "Custom"
        text_color: RGBA_PRIMARY[:4]

<MealCard>:
    orientation: "vertical"
    size_hint_y: None
    height: self.minimum_height
    padding: "8dp"
    spacing: "4dp"
    radius: [dp(12)]
    elevation: 1
    ripple_behavior: False
    focus_behavior: False

    # Meal name header
    MDBoxLayout:
        size_hint_y: None
        height: "36dp"

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

    MDDivider:

    MDBoxLayout:
        id: items_container
        orientation: "vertical"
        size_hint_y: None
        height: self.minimum_height

    MDDivider:

    # 4-column macro summary: Calories | Protein | Carbs | Fat
    MDBoxLayout:
        size_hint_y: None
        height: self.minimum_height
        spacing: "4dp"
        padding: ["2dp", "0dp", "2dp", "0dp"]

        MDBoxLayout:
            orientation: "vertical"
            size_hint_y: None
            height: self.minimum_height
            spacing: "0dp"
            MDLabel:
                text: root._cal_summary
                font_style: "Title"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_PRIMARY[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]
            MDLabel:
                text: "kcal"
                font_style: "Body"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_PRIMARY[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]

        MDBoxLayout:
            orientation: "vertical"
            size_hint_y: None
            height: self.minimum_height
            spacing: "0dp"
            MDLabel:
                text: root._pro_summary
                font_style: "Title"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_PROTEIN[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]
            MDLabel:
                text: "protein"
                font_style: "Body"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_PROTEIN[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]

        MDBoxLayout:
            orientation: "vertical"
            size_hint_y: None
            height: self.minimum_height
            spacing: "0dp"
            MDLabel:
                text: root._carb_summary
                font_style: "Title"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_CARBS[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]
            MDLabel:
                text: "carbs"
                font_style: "Body"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_CARBS[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]

        MDBoxLayout:
            orientation: "vertical"
            size_hint_y: None
            height: self.minimum_height
            spacing: "0dp"
            MDLabel:
                text: root._fat_summary
                font_style: "Title"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_FAT[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]
            MDLabel:
                text: "fat"
                font_style: "Body"
                role: "small"
                theme_text_color: "Custom"
                text_color: RGBA_FAT[:4]
                halign: "center"
                size_hint_y: None
                height: self.texture_size[1]

    MDDivider:

    _AddFoodBtn:
        on_release: root.dispatch("on_add_food", root.meal_id)
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

    # Per-meal targets (daily goal / meals_per_day); set by TrackerScreen after load
    _target_calories = NumericProperty(0.0)
    _target_protein = NumericProperty(0.0)
    _target_carbs = NumericProperty(0.0)
    _target_fat = NumericProperty(0.0)

    # Reactive summary strings bound to the KV labels
    _cal_summary = StringProperty("0")
    _pro_summary = StringProperty("0")
    _carb_summary = StringProperty("0")
    _fat_summary = StringProperty("0")

    __events__ = ("on_add_food", "on_delete_item", "on_edit_item")

    def set_targets(self, cal: float, protein: float, carbs: float, fat: float) -> None:
        """Set per-meal targets and refresh the summary labels."""
        self._target_calories = cal
        self._target_protein = protein
        self._target_carbs = carbs
        self._target_fat = fat
        self._update_summaries()

    @staticmethod
    def _fmt_summary(actual: float, target: float) -> str:
        a = f"{actual:.0f}"
        return f"{a} / {target:.0f}" if target > 0 else a

    def _update_summaries(self) -> None:
        self._cal_summary = self._fmt_summary(self._calories_total, self._target_calories)
        self._pro_summary = self._fmt_summary(self._protein_total, self._target_protein)
        self._carb_summary = self._fmt_summary(self._carbs_total, self._target_carbs)
        self._fat_summary = self._fmt_summary(self._fat_total, self._target_fat)

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
        container = self.ids.items_container
        row = self._make_row(item)
        existing = [w for w in container.children if isinstance(w, FoodItemRow)]
        if existing:
            container.add_widget(MDDivider())
        container.add_widget(row)
        s = item.scaled_nutrition
        self._calories_total += s.calories
        self._protein_total += s.protein_g
        self._carbs_total += s.carbs_g
        self._fat_total += s.fat_g
        self._update_summaries()

    def remove_item(self, item_id: str) -> None:
        """Remove the row with matching item_id and its adjacent divider.

        Args:
            item_id: UUID of the MealItem to remove.
        """
        container = self.ids.items_container
        children = list(container.children)
        for i, child in enumerate(children):
            if isinstance(child, FoodItemRow) and child.item_id == item_id:
                container.remove_widget(child)
                # Remove the divider displayed after this row (lower index in reversed list)
                if i > 0 and isinstance(children[i - 1], MDDivider):
                    container.remove_widget(children[i - 1])
                # Fallback: remove the divider displayed before this row (higher index)
                elif i + 1 < len(children) and isinstance(children[i + 1], MDDivider):
                    container.remove_widget(children[i + 1])
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
        for i, item in enumerate(items):
            container.add_widget(self._make_row(item))
            if i < len(items) - 1:
                container.add_widget(MDDivider())

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
        self._update_summaries()

    def _resum_totals(self, container: object) -> None:
        rows = [w for w in container.children if isinstance(w, FoodItemRow)]
        self._calories_total = sum(r.calories for r in rows)
        self._protein_total = sum(r.protein_g for r in rows)
        self._carbs_total = sum(r.carbs_g for r in rows)
        self._fat_total = sum(r.fat_g for r in rows)
        self._update_summaries()

    # ------------------------------------------------------------------
    # Default event handlers
    # ------------------------------------------------------------------

    def on_add_food(self, meal_id: str) -> None:  # noqa: ARG002
        """Default no-op for on_add_food."""

    def on_delete_item(self, item_id: str) -> None:  # noqa: ARG002
        """Default no-op for on_delete_item."""

    def on_edit_item(self, item_id: str) -> None:  # noqa: ARG002
        """Default no-op for on_edit_item."""
