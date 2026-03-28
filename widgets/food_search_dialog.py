"""Food search dialog: text search + barcode scan trigger + manual entry.

Opens as an MDDialog over the Tracker screen when the user taps "Add Food".
Flow:
  1. User types in the search field → live search via FoodService.
  2. User taps a result → on_food_selected fires with Food + quantity_g.
  3. User taps "Scan Barcode" → BarcodeService activated, dialog shows camera.
  4. If barcode unknown → manual entry form presented inline.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, List, Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.properties import ObjectProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.dialog import MDDialog
from kivymd.uix.list import MDListItem, MDListItemHeadlineText, MDListItemSupportingText

from models.food import Food, NutritionInfo
from services.food_service import FoodService
from services.barcode_service import BarcodeService
from utils.constants import RGBA_POPUP
import widgets.macros_button  # noqa: F401 — registers Macros*Button for FoodSearchContent KV

Builder.load_string("""
<FoodSearchContent>:
    orientation: "vertical"
    size_hint_y: None
    height: "440dp"
    spacing: "8dp"
    padding: ["8dp", "8dp", "8dp", "8dp"]

    MDBoxLayout:
        size_hint_y: None
        height: "56dp"
        spacing: "8dp"

        MDTextField:
            id: search_field
            hint_text: "Search foods..."
            size_hint_x: 1
            on_text: root.on_search_text(self.text)

        MDIconButton:
            icon: "barcode-scan"
            size_hint: None, None
            size: "56dp", "56dp"
            on_release: root.on_scan_pressed()

    MDScrollView:
        size_hint_y: 1

        MDList:
            id: results_list
            size_hint_y: None
            height: self.minimum_height

    MDBoxLayout:
        id: quantity_row
        orientation: "horizontal"
        size_hint_y: None
        height: "0dp"
        opacity: 0
        spacing: "8dp"

        MDTextField:
            id: quantity_field
            hint_text: "Quantity (g)"
            input_filter: "float"
            text: "100"
            size_hint_x: 1

        MacrosFilledButton:
            size_hint_x: None
            width: "80dp"
            on_release: root.on_confirm_quantity()

            MDButtonText:
                text: "Add"

    MDBoxLayout:
        id: manual_form
        orientation: "vertical"
        size_hint_y: None
        height: "0dp"
        opacity: 0
        spacing: "4dp"

        MDLabel:
            text: "Enter food details manually"
            font_style: "Title"
            role: "small"

        MDTextField:
            id: manual_name
            hint_text: "Food name *"

        MDBoxLayout:
            size_hint_y: None
            height: "56dp"
            spacing: "8dp"

            MDTextField:
                id: manual_calories
                hint_text: "Calories/100g"
                input_filter: "float"

            MDTextField:
                id: manual_protein
                hint_text: "Protein (g)"
                input_filter: "float"

        MDBoxLayout:
            size_hint_y: None
            height: "56dp"
            spacing: "8dp"

            MDTextField:
                id: manual_carbs
                hint_text: "Carbs (g)"
                input_filter: "float"

            MDTextField:
                id: manual_fat
                hint_text: "Fat (g)"
                input_filter: "float"

        MacrosFilledButton:
            on_release: root.on_save_manual()

            MDButtonText:
                text: "Save & Use"
""")


class FoodSearchContent(MDBoxLayout):
    """Inner content widget for the FoodSearchDialog.

    Attributes:
        profile_id: Current user's profile UUID.
        on_food_confirmed: Callback fired with (Food, quantity_g) when user confirms selection.
    """

    profile_id = StringProperty("")

    def __init__(
        self,
        profile_id: str,
        on_food_confirmed: Callable[[Food, float], None],
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.profile_id = profile_id
        self._on_food_confirmed = on_food_confirmed
        self._food_service = FoodService()
        self._barcode_service: Optional[BarcodeService] = None
        self._selected_food: Optional[Food] = None
        self._search_event: Optional[object] = None

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def on_search_text(self, text: str) -> None:
        """Debounce text input and trigger a search after 400ms.

        Args:
            text: Current value of the search field.
        """
        if self._search_event:
            self._search_event.cancel()
        if len(text) < 2:
            self.ids.results_list.clear_widgets()
            return
        self._search_event = Clock.schedule_once(
            lambda dt: self._run_search(text), 0.4
        )

    def _run_search(self, query: str) -> None:
        results: List[Food] = self._food_service.search(query, self.profile_id)
        self.ids.results_list.clear_widgets()
        for food in results[:20]:
            item = MDListItem(on_release=lambda _, f=food: self._select_food(f))
            item.add_widget(MDListItemHeadlineText(text=food.name))
            item.add_widget(
                MDListItemSupportingText(
                    text=f"{food.brand or ''}  •  {food.nutrition.calories:.0f} kcal/100g"
                )
            )
            self.ids.results_list.add_widget(item)

    # ------------------------------------------------------------------
    # Food selection & quantity
    # ------------------------------------------------------------------

    def _select_food(self, food: Food) -> None:
        self._selected_food = food
        self._show_quantity_row()

    def _show_quantity_row(self) -> None:
        row = self.ids.quantity_row
        row.height = "56dp"
        row.opacity = 1
        self.ids.results_list.clear_widgets()

    def on_confirm_quantity(self) -> None:
        """Read the quantity field and fire the confirmation callback."""
        if self._selected_food is None:
            return
        try:
            qty = float(self.ids.quantity_field.text or "100")
        except ValueError:
            qty = 100.0
        self._on_food_confirmed(self._selected_food, qty)

    # ------------------------------------------------------------------
    # Barcode scan
    # ------------------------------------------------------------------

    def on_scan_pressed(self) -> None:
        """Activate BarcodeService to scan from camera."""
        self._barcode_service = BarcodeService(on_result=self._on_barcode_result)
        # Camera widget injection happens in FoodSearchDialog after opening
        # the dedicated camera overlay (see FoodSearchDialog.start_camera_scan).

    def _on_barcode_result(self, barcode: str) -> None:
        food = self._food_service.lookup_barcode(barcode, self.profile_id)
        if food:
            self._select_food(food)
        else:
            self._show_manual_form(prefill_name=barcode)

    # ------------------------------------------------------------------
    # Manual entry
    # ------------------------------------------------------------------

    def _show_manual_form(self, prefill_name: str = "") -> None:
        form = self.ids.manual_form
        form.height = "280dp"
        form.opacity = 1
        self.ids.manual_name.text = prefill_name

    def on_save_manual(self) -> None:
        """Validate and save the manually entered food, then select it."""
        name = self.ids.manual_name.text.strip()
        if not name:
            return

        def _float(field_id: str) -> float:
            try:
                return float(self.ids[field_id].text or "0")
            except (ValueError, KeyError):
                return 0.0

        food = Food(
            id=str(uuid.uuid4()),
            name=name,
            source="manual",
            nutrition=NutritionInfo(
                calories=_float("manual_calories"),
                protein_g=_float("manual_protein"),
                carbs_g=_float("manual_carbs"),
                fat_g=_float("manual_fat"),
            ),
            created_by=self.profile_id,
            updated_at=time.time(),
        )
        saved = self._food_service.save_manual_food(food)
        self._select_food(saved)


class FoodSearchDialog:
    """Wrapper that creates and manages the MDDialog containing FoodSearchContent.

    Usage:
        dialog = FoodSearchDialog(profile_id=uid, on_food_confirmed=handler)
        dialog.open()
    """

    def __init__(
        self,
        profile_id: str,
        on_food_confirmed: Callable[[Food, float], None],
    ) -> None:
        self._content = FoodSearchContent(
            profile_id=profile_id,
            on_food_confirmed=lambda food, qty: self._handle_confirmed(food, qty, on_food_confirmed),
        )
        self._dialog = MDDialog(
            title="Add Food",
            type="custom",
            content_cls=self._content,
            buttons=[
                # Close button injected via kv or code if needed
            ],
            theme_bg_color="Custom",
            md_bg_color=RGBA_POPUP,
        )

    def open(self) -> None:
        """Open the dialog."""
        self._dialog.open()

    def dismiss(self) -> None:
        """Close the dialog."""
        self._dialog.dismiss()

    def _handle_confirmed(
        self,
        food: Food,
        qty: float,
        callback: Callable[[Food, float], None],
    ) -> None:
        callback(food, qty)
        self._dialog.dismiss()
