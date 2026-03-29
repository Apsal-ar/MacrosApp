"""Full-screen food editor: metadata + nutrition per 100 g (surface cards, ruled rows)."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Optional

from kivy.clock import Clock
from kivy.lang import Builder
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

from models.food import Food, NutritionInfo
from screens.base_screen import BaseScreen
from services.food_service import FoodService
from utils.constants import (
    RGBA_BG,
    RGBA_CARBS,
    RGBA_FAT,
    RGBA_LINE,
    RGBA_PRIMARY,
    RGBA_PROTEIN,
    RGBA_SURFACE,
    UI_CORNER_RADIUS_DP,
)

_LINE_RGBA = (0.32, 0.33, 0.36, 1)
_WHITE = (0.92, 0.93, 0.95, 1)
TIP = (0.65, 0.68, 0.72, 1)


def _thin_rule() -> MDBoxLayout:
    return MDBoxLayout(
        size_hint_y=None,
        height=dp(1),
        md_bg_color=_LINE_RGBA,
    )


class FoodEditScreen(BaseScreen):
    """Edit name, brand, barcode, serving size (g), and per-100g nutrients."""

    name = "food_edit"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._food_service = FoodService()
        self._draft: Optional[Food] = None
        self._field_refs: dict[str, MDTextField] = {}
        self._barcode_scan_cb: Optional[Callable[[], None]] = None

    def bind_food(
        self,
        food: Food,
        *,
        on_barcode_scan: Optional[Callable[[], None]] = None,
    ) -> None:
        """Load a copy of ``food`` for editing."""
        self._barcode_scan_cb = on_barcode_scan
        self._draft = self._clone_food(food)
        Clock.schedule_once(lambda _dt: self._rebuild_ui(), 0)

    def _clone_food(self, food: Food) -> Food:
        n = food.nutrition or NutritionInfo()
        n2 = replace(n)
        return replace(
            food,
            nutrition=n2,
            name=food.name or "",
            brand=food.brand,
            barcode=food.barcode,
            serving_size_g=food.serving_size_g or 100.0,
        )

    def on_pre_enter(self, *args: object) -> None:
        self._set_bottom_nav_visible(False)

    def on_leave(self, *args: object) -> None:
        self._set_bottom_nav_visible(True)

    def _set_bottom_nav_visible(self, visible: bool) -> None:
        try:
            app = MDApp.get_running_app()
            shell = app.root.get_screen("app")
            nav = shell.ids.nav_bar
            nav.opacity = 1.0 if visible else 0.0
            nav.disabled = not visible
        except Exception:  # pylint: disable=broad-except
            pass

    def go_back(self) -> None:
        try:
            app = MDApp.get_running_app()
            shell = app.root.get_screen("app")
            fs = shell.ids.inner_sm.get_screen("food_search")
            fs.mark_return_from_food_edit()
            shell.ids.inner_sm.current = "food_search"
        except Exception:  # pylint: disable=broad-except
            shell = MDApp.get_running_app().root.get_screen("app")
            shell.ids.inner_sm.current = "food_search"

    def _on_barcode_icon(self) -> None:
        if self._barcode_scan_cb:
            self._barcode_scan_cb()

    def save_food(self) -> None:
        if self._draft is None:
            return
        uid = self.get_current_user_id()
        if not uid:
            self.show_error("Not signed in.")
            return
        name = (self._field_refs.get("name") and self._field_refs["name"].text or "").strip()
        if not name:
            self.show_error("Description (name) is required.")
            return
        brand_t = (self._field_refs.get("brand") and self._field_refs["brand"].text or "").strip()
        bc = (self._field_refs.get("barcode") and self._field_refs["barcode"].text or "").strip()
        try:
            serving = float((self._field_refs.get("serving") and self._field_refs["serving"].text or "100").strip())
            serving = max(1.0, serving)
        except ValueError:
            serving = 100.0

        try:
            n = self._read_nutrition_from_fields()
        except ValueError:
            self.show_error("Enter valid numbers for nutrition fields.")
            return

        cal_empty = not (
            self._field_refs.get("calories") and self._field_refs["calories"].text.strip()
        )
        if cal_empty:
            p, c, f = n.protein_g, n.carbs_g, n.fat_g
            n = replace(n, calories=round(p * 4.0 + c * 4.0 + f * 9.0, 1))
        else:
            try:
                cal = float(self._field_refs["calories"].text.strip())
                n = replace(n, calories=cal)
            except ValueError:
                self.show_error("Invalid calories.")
                return

        updated = replace(
            self._draft,
            name=name,
            brand=brand_t or None,
            barcode=bc or None,
            serving_size_g=serving,
            nutrition=n,
            updated_at=time.time(),
            created_by=self._draft.created_by or uid,
        )
        self._food_service.save_food(updated)
        self.show_success("Food saved")
        self.go_back()

    def _read_nutrition_from_fields(self) -> NutritionInfo:
        def f(key: str, default: float = 0.0) -> float:
            w = self._field_refs.get(key)
            if not w or not (w.text or "").strip():
                return default
            return float(w.text.strip())

        def fo(key: str) -> Optional[float]:
            w = self._field_refs.get(key)
            if not w or not (w.text or "").strip():
                return None
            return float(w.text.strip())

        return NutritionInfo(
            calories=f("calories", 0.0),
            protein_g=f("protein", 0.0),
            carbs_g=f("carbs", 0.0),
            fat_g=f("fat", 0.0),
            fiber_g=fo("fiber"),
            sugar_g=fo("sugar"),
            sodium_mg=fo("sodium"),
            fat_saturated_g=fo("fat_sat"),
            fat_trans_g=fo("fat_trans"),
            fat_polyunsaturated_g=fo("fat_poly"),
            fat_monounsaturated_g=fo("fat_mono"),
        )

    def _rebuild_ui(self) -> None:
        si = self.ids.scroll_inner
        si.clear_widgets()
        self._field_refs.clear()
        if self._draft is None:
            return

        f = self._draft
        n = f.nutrition or NutritionInfo()
        r = dp(UI_CORNER_RADIUS_DP)

        def surface_card() -> MDBoxLayout:
            return MDBoxLayout(
                orientation="vertical",
                spacing=0,
                size_hint_y=None,
                padding=[dp(4), dp(4), dp(4), dp(8)],
                md_bg_color=RGBA_SURFACE,
                theme_bg_color="Custom",
                radius=[r, r, r, r],
            )

        info = surface_card()
        self._add_text_row(info, "Description", "name", f.name or "", tuple(RGBA_PRIMARY[:4]))
        info.add_widget(_thin_rule())
        self._add_text_row(info, "Brand", "brand", f.brand or "", _WHITE)
        info.add_widget(_thin_rule())

        bc_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            padding=[dp(12), dp(4), dp(8), dp(4)],
            spacing=dp(4),
        )
        bc_row.add_widget(
            MDLabel(
                text="Barcode",
                size_hint_x=0.35,
                font_style="Body",
                role="medium",
                theme_text_color="Custom",
                text_color=_WHITE,
                halign="left",
                valign="middle",
            )
        )
        t_bc = MDTextField(
            text=f.barcode or "",
            mode="filled",
            size_hint_x=1,
            size_hint_y=None,
            height=dp(40),
            theme_bg_color="Custom",
            fill_color_normal=(*RGBA_BG[:3], 1),
            theme_line_color="Custom",
            line_color_normal=(0, 0, 0, 0),
        )
        self._field_refs["barcode"] = t_bc
        bc_row.add_widget(t_bc)
        bc_row.add_widget(
            MDIconButton(
                icon="barcode-scan",
                theme_icon_color="Custom",
                icon_color=tuple(RGBA_PRIMARY[:4]),
                on_release=lambda *_: self._on_barcode_icon(),
            )
        )
        info.add_widget(bc_row)
        info.add_widget(_thin_rule())

        sg = float(f.serving_size_g or 100.0)
        serving_txt = str(int(sg)) if sg == int(sg) else f"{sg:.1f}"
        self._add_text_row(
            info,
            "Serving size (g)",
            "serving",
            serving_txt,
            _WHITE,
        )

        si.add_widget(info)

        si.add_widget(
            MDLabel(
                text="Tip: Leave the calories field empty to auto-calculate from macronutrients.",
                font_style="Body",
                role="small",
                theme_text_color="Custom",
                text_color=TIP,
                size_hint_y=None,
                halign="center",
                text_size=(None, None),
            )
        )

        nut = surface_card()
        nut.add_widget(
            MDLabel(
                text="Nutrition Facts per 100 g",
                font_style="Title",
                role="small",
                theme_text_color="Custom",
                text_color=TIP,
                size_hint_y=None,
                height=dp(36),
                halign="center",
                padding=[0, dp(8), 0, dp(4)],
            )
        )
        nut.add_widget(_thin_rule())

        self._nut_row(nut, "Calories", "calories", n.calories, tuple(RGBA_PRIMARY[:4]), fmt_kcal=True)
        nut.add_widget(_thin_rule())
        self._nut_row(nut, "Fat (g)", "fat", n.fat_g, tuple(RGBA_FAT[:4]))
        nut.add_widget(_thin_rule())
        for label, key, val in (
            ("Saturated", "fat_sat", n.fat_saturated_g),
            ("Trans", "fat_trans", n.fat_trans_g),
            ("Polyunsaturated", "fat_poly", n.fat_polyunsaturated_g),
            ("Monounsaturated", "fat_mono", n.fat_monounsaturated_g),
        ):
            self._nut_row(nut, label, key, val, _WHITE, indent=dp(14))
            nut.add_widget(_thin_rule())
        self._nut_row(nut, "Carbohydrate (g)", "carbs", n.carbs_g, tuple(RGBA_CARBS[:4]))
        nut.add_widget(_thin_rule())
        self._nut_row(nut, "Dietary fiber", "fiber", n.fiber_g, _WHITE, indent=dp(14))
        nut.add_widget(_thin_rule())
        self._nut_row(nut, "Sugars", "sugar", n.sugar_g, _WHITE, indent=dp(14))
        nut.add_widget(_thin_rule())
        self._nut_row(nut, "Protein (g)", "protein", n.protein_g, tuple(RGBA_PROTEIN[:4]))
        nut.add_widget(_thin_rule())
        self._nut_row(nut, "Sodium (mg)", "sodium", n.sodium_mg, _WHITE)

        si.add_widget(nut)

    def set_barcode_text(self, barcode: str) -> None:
        w = self._field_refs.get("barcode")
        if w:
            w.text = barcode

    def _add_text_row(
        self,
        parent: MDBoxLayout,
        label: str,
        key: str,
        value: str,
        label_rgba: tuple[float, float, float, float],
    ) -> None:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            padding=[dp(12), dp(4), dp(12), dp(4)],
            spacing=dp(8),
        )
        row.add_widget(
            MDLabel(
                text=label,
                size_hint_x=0.38,
                font_style="Body",
                role="medium",
                theme_text_color="Custom",
                text_color=label_rgba,
                halign="left",
                valign="middle",
            )
        )
        tf = MDTextField(
            text=value,
            mode="filled",
            size_hint_x=1,
            size_hint_y=None,
            height=dp(40),
            theme_bg_color="Custom",
            fill_color_normal=(*RGBA_BG[:3], 1),
            theme_line_color="Custom",
            line_color_normal=(0, 0, 0, 0),
        )
        self._field_refs[key] = tf
        row.add_widget(tf)
        parent.add_widget(row)

    def _nut_row(
        self,
        parent: MDBoxLayout,
        label: str,
        key: str,
        value: Optional[float],
        label_rgba: tuple[float, float, float, float],
        *,
        indent: float = 0,
        fmt_kcal: bool = False,
    ) -> None:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(12) + indent, dp(4), dp(12), dp(4)],
            spacing=dp(8),
        )
        row.add_widget(
            MDLabel(
                text=label,
                size_hint_x=0.5,
                font_style="Body",
                role="small",
                theme_text_color="Custom",
                text_color=label_rgba,
                halign="left",
                valign="middle",
            )
        )
        if value is None:
            if key == "sodium":
                vtxt = "0"
            elif fmt_kcal:
                vtxt = ""
            else:
                vtxt = "0.0"
        elif fmt_kcal:
            vtxt = f"{value:.0f}"
        elif key == "sodium":
            vtxt = f"{value:.0f}"
        else:
            vtxt = f"{value:.1f}"
        tf = MDTextField(
            text=vtxt,
            hint_text="",
            mode="filled",
            size_hint_x=0.5,
            size_hint_y=None,
            height=dp(38),
            theme_bg_color="Custom",
            fill_color_normal=(*RGBA_BG[:3], 1),
            theme_line_color="Custom",
            line_color_normal=(0, 0, 0, 0),
            input_filter="float",
        )
        self._field_refs[key] = tf
        row.add_widget(tf)
        parent.add_widget(row)

Builder.load_file("assets/kv/food_edit.kv")
