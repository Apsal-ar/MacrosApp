"""Full-screen food search: header, search field, barcode scan, tabs, results."""

from __future__ import annotations

import logging
import time
import uuid
from typing import List, Optional

import config
from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from models.food import Food, NutritionInfo
from screens.base_screen import BaseScreen
from services.barcode_service import BarcodeService
from services.food_service import FoodService
Builder.load_file("assets/kv/food_search.kv")

logger = logging.getLogger(__name__)


class FoodSearchScreen(BaseScreen):
    """Pushed from Tracker when user taps Add food on a meal card."""

    name = "food_search"

    meal_id = StringProperty("")
    profile_id = StringProperty("")
    search_tab = NumericProperty(0)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._food_service = FoodService()
        self._barcode_service: Optional[BarcodeService] = None
        self._camera_modal: Optional[ModalView] = None
        self._selected_food: Optional[Food] = None
        self._search_event: Optional[object] = None

    def on_pre_enter(self, *args: object) -> None:
        self._set_bottom_nav_visible(False)
        uid = self.get_current_user_id()
        if uid:
            self.profile_id = uid
        self._reset_ui()

    def on_leave(self, *args: object) -> None:
        self._set_bottom_nav_visible(True)
        self._stop_barcode_scan()
        if self._camera_modal:
            try:
                self._camera_modal.dismiss()
            except Exception:  # pylint: disable=broad-except
                pass
            self._camera_modal = None

    def _set_bottom_nav_visible(self, visible: bool) -> None:
        try:
            app = MDApp.get_running_app()
            shell = app.root.get_screen("app")
            nav = shell.ids.nav_bar
            nav.opacity = 1.0 if visible else 0.0
            nav.disabled = not visible
        except Exception:  # pylint: disable=broad-except
            pass

    def _reset_ui(self) -> None:
        self._selected_food = None
        self._stop_barcode_scan()
        self.search_tab = 0
        if "search_field" in self.ids:
            self.ids.search_field.text = ""
        self._ensure_list_attached()
        if "results_list" in self.ids:
            self.ids.results_list.clear_widgets()
        self._hide_quantity_row()
        self._hide_manual_form()
        self._update_clear_button("")
        self._update_tab_styles()

    def go_back(self) -> None:
        """Return to Tracker without adding."""
        self._stop_barcode_scan()
        self._go_to_tracker()

    def _go_to_tracker(self) -> None:
        try:
            app = MDApp.get_running_app()
            shell = app.root.get_screen("app")
            shell.ids.inner_sm.current = "tracker"
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("go_to_tracker: %s", exc)

    def clear_search(self) -> None:
        if "search_field" in self.ids:
            self.ids.search_field.text = ""

    def open_manual_form(self) -> None:
        self._show_manual_form(prefill_name="")

    def set_tab(self, index: int) -> None:
        self.search_tab = int(index)
        self._update_tab_styles()
        text = self.ids.search_field.text.strip() if "search_field" in self.ids else ""
        if len(text) >= 2:
            self._run_search(text)
        else:
            self._show_tab_placeholder()

    def _update_tab_styles(self) -> None:
        active = self.search_tab
        for i, bid in enumerate(("tab_b0", "tab_b1", "tab_b2")):
            if bid in self.ids:
                self.ids[bid].theme_text_color = (
                    "Primary" if i == active else "Secondary"
                )

    def on_search_text(self, text: str) -> None:
        self._update_clear_button(text)
        if self._search_event:
            self._search_event.cancel()
        if len(text.strip()) < 2:
            self._ensure_list_attached()
            self.ids.results_list.clear_widgets()
            self._show_tab_placeholder()
            return
        self._search_event = Clock.schedule_once(
            lambda dt: self._run_search(text.strip()), 0.35
        )

    def _update_clear_button(self, text: str) -> None:
        if "clear_search_btn" not in self.ids:
            return
        show = len(text.strip()) > 0
        self.ids.clear_search_btn.opacity = 1.0 if show else 0.0
        self.ids.clear_search_btn.disabled = not show

    def _show_tab_placeholder(self) -> None:
        """Clear results when the query is too short (no placeholder copy)."""
        self._ensure_list_attached()
        self.ids.results_list.clear_widgets()

    def _ensure_list_attached(self) -> None:
        """Put the results MDList back inside the scroll area (after an empty-state view)."""
        outer = self.ids.results_outer
        lst = self.ids.results_list
        outer.clear_widgets()
        outer.add_widget(lst)

    def _run_search(self, query: str) -> None:
        if self.search_tab == 1:
            if len(query) < 2:
                self._show_tab_placeholder()
                return
            self._show_empty_state_recipes(query)
            return

        raw: List[Food] = self._food_service.search(query, self.profile_id)
        if self.search_tab == 0:
            results = [
                f
                for f in raw
                if f.created_by and f.created_by == self.profile_id
            ]
        else:
            results = raw

        if not results:
            if self.search_tab == 0:
                self._show_empty_state_my_foods(query)
            else:
                self._ensure_list_attached()
                self.ids.results_list.clear_widgets()
                from kivymd.uix.list import (  # pylint: disable=import-outside-toplevel
                    MDListItem,
                    MDListItemHeadlineText,
                )

                item = MDListItem()
                item.add_widget(MDListItemHeadlineText(text="No foods found"))
                self.ids.results_list.add_widget(item)
            return

        self._ensure_list_attached()
        self.ids.results_list.clear_widgets()

        from kivymd.uix.list import (  # pylint: disable=import-outside-toplevel
            MDListItem,
            MDListItemHeadlineText,
            MDListItemSupportingText,
        )

        for food in results[:40]:
            n = food.nutrition
            cal = n.calories if n else 0.0
            pg = n.protein_g if n else 0.0
            cg = n.carbs_g if n else 0.0
            fg = n.fat_g if n else 0.0
            brand = food.brand or ""
            sub = (
                f"{brand}  •  {cal:.0f} kcal/100g\n"
                f"C:{cg:.0f}  P:{pg:.0f}  F:{fg:.0f}"
            )
            item = MDListItem(on_release=lambda _, f=food: self._select_food(f))
            item.add_widget(MDListItemHeadlineText(text=food.name))
            item.add_widget(MDListItemSupportingText(text=sub))
            self.ids.results_list.add_widget(item)

    def _show_empty_state_my_foods(self, query: str) -> None:
        """Bowl icon + blue message + CTA to search the same term in Library."""
        outer = self.ids.results_outer
        lst = self.ids.results_list
        if lst.parent:
            outer.remove_widget(lst)
        outer.clear_widgets()
        outer.add_widget(self._build_empty_state_my_foods(query))

    def _show_empty_state_recipes(self, query: str) -> None:
        """Chef-hat icon + blue message (no recipes DB yet)."""
        outer = self.ids.results_outer
        lst = self.ids.results_list
        if lst.parent:
            outer.remove_widget(lst)
        outer.clear_widgets()
        outer.add_widget(self._build_empty_state_recipes(query))

    def _build_empty_state_my_foods(self, query: str) -> MDBoxLayout:
        root = MDBoxLayout(
            orientation="vertical",
            spacing=dp(20),
            padding=[dp(16), dp(32), dp(16), dp(24)],
            size_hint_y=None,
        )
        root.bind(minimum_height=root.setter("height"))

        icon = MDIconButton(
            icon="bowl-mix-outline",
            theme_text_color="Custom",
            text_color=(1.0, 0.48, 0.2, 1.0),
            pos_hint={"center_x": 0.5},
        )
        icon.font_size = dp(40)
        root.add_widget(icon)

        msg = (
            f'No foods found for the search: "{query}" in your foods.'
        )
        card = MDCard(
            orientation="vertical",
            padding=[dp(16), dp(18), dp(16), dp(18)],
            radius=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=None,
            md_bg_color=(0.12, 0.18, 0.42, 1.0),
        )
        lbl = MDLabel(
            text=msg,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
            size_hint_y=None,
            size_hint_x=1,
            text_size=(dp(300), None),
        )
        card.add_widget(lbl)

        root.add_widget(card)

        btn = MDButton(
            style="filled",
            size_hint_y=None,
            height=dp(48),
            size_hint_x=1,
            on_release=lambda *_: self.search_in_library(),
        )
        btn.add_widget(
            MDButtonText(
                text=f'Search "{query}" in the library',
            )
        )
        root.add_widget(btn)
        return root

    def _build_empty_state_recipes(self, query: str) -> MDBoxLayout:
        root = MDBoxLayout(
            orientation="vertical",
            spacing=dp(20),
            padding=[dp(16), dp(32), dp(16), dp(24)],
            size_hint_y=None,
        )
        root.bind(minimum_height=root.setter("height"))

        icon = MDIconButton(
            icon="chef-hat",
            theme_text_color="Custom",
            text_color=(1.0, 0.48, 0.2, 1.0),
            pos_hint={"center_x": 0.5},
        )
        icon.font_size = dp(40)
        root.add_widget(icon)

        msg = f'No recipes found for the search: "{query}" in your recipes.'
        card = MDCard(
            orientation="vertical",
            padding=[dp(16), dp(18), dp(16), dp(18)],
            radius=[dp(12), dp(12), dp(12), dp(12)],
            size_hint_y=None,
            md_bg_color=(0.12, 0.18, 0.42, 1.0),
        )
        lbl = MDLabel(
            text=msg,
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            halign="center",
            size_hint_y=None,
            size_hint_x=1,
            text_size=(dp(300), None),
        )
        card.add_widget(lbl)
        root.add_widget(card)
        return root

    def search_in_library(self) -> None:
        """Switch to Library tab and re-run search with the current query."""
        self.set_tab(2)

    def _select_food(self, food: Food) -> None:
        self._selected_food = food
        self._show_quantity_row()

    def _show_quantity_row(self) -> None:
        row = self.ids.quantity_row
        row.height = "56dp"
        row.opacity = 1
        self._ensure_list_attached()
        self.ids.results_list.clear_widgets()

    def _hide_quantity_row(self) -> None:
        row = self.ids.quantity_row
        row.height = "0dp"
        row.opacity = 0

    def on_confirm_quantity(self) -> None:
        if self._selected_food is None:
            return
        try:
            qty = float(self.ids.quantity_field.text or "100")
        except ValueError:
            qty = 100.0
        self._finish_add(self._selected_food, qty)

    def _finish_add(self, food: Food, qty: float) -> None:
        if not self.meal_id:
            self.show_error("Missing meal — go back and tap Add food again.")
            return
        try:
            app = MDApp.get_running_app()
            shell = app.root.get_screen("app")
            tracker = shell.ids.inner_sm.get_screen("tracker")
            tracker.add_food_from_search(self.meal_id, food, qty)
            shell.ids.inner_sm.current = "tracker"
            self._reset_ui()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("add food: %s", exc)
            self.show_error("Could not add food.")

    def on_scan_pressed(self) -> None:
        if not config.ENABLE_BARCODE_SCAN:
            self.show_error("Barcode scanning is disabled.")
            return
        try:
            from kivy.uix.camera import Camera  # pylint: disable=import-outside-toplevel
        except ImportError:
            self.show_error("Camera is not available on this platform.")
            return

        self._stop_barcode_scan()
        layout = FloatLayout()
        try:
            cam = Camera(
                play=True,
                resolution=(640, 480),
                size_hint=(1, 1),
                pos_hint={"x": 0, "y": 0},
            )
        except Exception:  # pylint: disable=broad-except
            self.show_error("Camera is not available on this device.")
            return
        layout.add_widget(cam)
        close = MDIconButton(
            icon="close",
            pos_hint={"right": 0.99, "top": 0.99},
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
        )
        layout.add_widget(close)

        mv = ModalView(size_hint=(1, 1), auto_dismiss=False)
        mv.add_widget(layout)
        self._camera_modal = mv

        self._barcode_service = BarcodeService(on_result=lambda b: self._on_barcode_camera(b))

        def dismiss_mv(*_a: object) -> None:
            self._stop_barcode_scan()
            mv.dismiss()
            self._camera_modal = None

        close.bind(on_release=dismiss_mv)

        if not self._barcode_service.start_scan(cam):
            self.show_error("Barcode scanner unavailable (install pyzbar / use camera).")
            self._barcode_service = None
            return

        mv.open()

    def _on_barcode_camera(self, barcode: str) -> None:
        if self._camera_modal:
            try:
                self._camera_modal.dismiss()
            except Exception:  # pylint: disable=broad-except
                pass
            self._camera_modal = None
        self._stop_barcode_scan()
        self._on_barcode_result(barcode)

    def _on_barcode_result(self, barcode: str) -> None:
        food = self._food_service.lookup_barcode(barcode, self.profile_id)
        if food:
            self._select_food(food)
        else:
            self._show_manual_form(prefill_name=barcode)

    def _stop_barcode_scan(self) -> None:
        if self._barcode_service is not None:
            try:
                self._barcode_service.stop_scan()
            except Exception:  # pylint: disable=broad-except
                pass
            self._barcode_service = None

    def _hide_manual_form(self) -> None:
        form = self.ids.manual_form
        form.height = "0dp"
        form.opacity = 0

    def _show_manual_form(self, prefill_name: str = "") -> None:
        self._hide_quantity_row()
        form = self.ids.manual_form
        form.height = "300dp"
        form.opacity = 1
        self.ids.manual_name.text = prefill_name
        self._ensure_list_attached()
        self.ids.results_list.clear_widgets()

    def on_save_manual(self) -> None:
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
        self._hide_manual_form()
        self._select_food(saved)
