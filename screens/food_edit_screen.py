"""Full-screen food editor: metadata + nutrition per 100 g (surface cards, ruled rows)."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel

import widgets.macros_button  # noqa: F401 — KV registration side-effect
from models.food import Food, NutritionInfo
from screens.base_screen import BaseScreen
from services.food_service import FoodService
from utils.constants import (
    RGBA_CARBS,
    RGBA_FAT,
    RGBA_LINE,
    RGBA_PRIMARY,
    RGBA_PROTEIN,
    RGBA_SURFACE,
    UI_CARD_RADIUS_DP,
)

_WHITE = (0.92, 0.93, 0.95, 1)
_HINT = (0.55, 0.58, 0.62, 1)
TIP = (0.65, 0.68, 0.72, 1)

def card_font() -> float:
    """Body text for surface cards — scales slightly with window width; ``sp`` for DPI."""
    w = float(Window.width) if Window.width else dp(360)
    factor = max(0.88, min(1.12, w / dp(390)))
    return sp(13.0 * factor)







def _thin_rule() -> MDBoxLayout:
    """1dp divider — same hue as ``RGBA_LINE`` (shared with Library sheet, goals, etc.)."""
    return MDBoxLayout(
        size_hint_y=None,
        height=dp(1),
        theme_bg_color="Custom",
        md_bg_color=tuple(RGBA_LINE[:4]),
    )


class FoodEditScreen(BaseScreen):
    """Edit name, brand, barcode, serving size (g), and per-100g nutrients."""

    name = "food_edit"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._food_service = FoodService()
        self._draft: Optional[Food] = None
        self._field_refs: dict[str, object] = {}
        self._barcode_scan_cb: Optional[Callable[[], None]] = None
        self._return_screen: str = "food_search"

    def set_return_screen(self, name: str) -> None:
        """Where ``go_back`` navigates (e.g. ``food_search`` or ``tracker``)."""
        self._return_screen = name

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
            sm = shell.ids.inner_sm
            target = self._return_screen or "food_search"
            if target == "food_search":
                fs = sm.get_screen("food_search")
                fs.mark_return_from_food_edit()
            sm.current = target
        except Exception:  # pylint: disable=broad-except
            try:
                shell = MDApp.get_running_app().root.get_screen("app")
                shell.ids.inner_sm.current = self._return_screen or "food_search"
            except Exception:  # pylint: disable=broad-except
                pass

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
            raw_s = (self._field_refs.get("serving") and self._field_refs["serving"].text or "").strip()
            serving = max(1.0, float(raw_s) if raw_s else 100.0)
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
        self._food_service.save_food_dedup(updated, uid)
        self.show_success("Food saved")
        self.go_back()

    def _read_nutrition_from_fields(self) -> NutritionInfo:
        def f(key: str, default: float = 0.0) -> float:
            w = self._field_refs.get(key)
            t = (getattr(w, "text", "") or "").strip()
            if not t:
                return default
            try:
                return float(t)
            except ValueError:
                return default

        def fo(key: str) -> Optional[float]:
            w = self._field_refs.get(key)
            t = (getattr(w, "text", "") or "").strip()
            if not t:
                return None
            try:
                return float(t)
            except ValueError:
                return None

        return NutritionInfo(
            calories=f("calories", 0.0),
            protein_g=f("protein", 0.0),
            carbs_g=f("carbs", 0.0),
            fat_g=f("fat", 0.0),
            fiber_g=fo("fiber"),
            sugar_g=fo("sugar"),
            fat_saturated_g=fo("fat_sat"),
            fat_trans_g=fo("fat_trans"),
            fat_polyunsaturated_g=fo("fat_poly"),
            fat_monounsaturated_g=fo("fat_mono"),
            salt_mg=fo("salt"),
        )

    def _rebuild_ui(self) -> None:
        si = self.ids.scroll_inner
        si.clear_widgets()
        self._field_refs.clear()
        if self._draft is None:
            return

        f = self._draft
        n = f.nutrition or NutritionInfo()
        r = dp(UI_CARD_RADIUS_DP)

        def surface_card() -> MDBoxLayout:
            return MDBoxLayout(
                orientation="vertical",
                spacing=0,
                size_hint_y=None,
                padding=[dp(12), dp(8), dp(12), dp(10)],
                md_bg_color=RGBA_SURFACE,
                theme_bg_color="Custom",
                radius=[r, r, r, r],
            )

        info = surface_card()
        self._add_metadata_text_row(info, "Description", "name", f.name or "")
        info.add_widget(_thin_rule())
        self._add_metadata_text_row(
            info,
            "Brand",
            "brand",
            f.brand or "",
            optional_field=True,
        )
        info.add_widget(_thin_rule())
        self._add_barcode_row(info, f.barcode or "")
        info.add_widget(_thin_rule())

        serving_val = f.serving_size_g or 100.0
        serving_txt = (
            str(int(round(serving_val)))
            if abs(serving_val - round(serving_val)) < 1e-6
            else f"{serving_val:.1f}"
        )
        self._add_metadata_text_row(
            info, "Serving size", "serving", serving_txt, numeric=True, unit_suffix="g"
        )
        info.bind(minimum_height=info.setter("height"))

        si.add_widget(info)

        si.add_widget(
            MDLabel(
                text="Tip: Leave the calories field empty to auto-calculate from macronutrients.",
                font_style="Body",
                role="small",
                font_size=card_font(),
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
                font_style="Body",
                role="small",
                font_size=card_font(),
                theme_text_color="Custom",
                text_color=TIP,
                size_hint_y=None,
                height=dp(28),
                halign="center",
                padding=[0, dp(4), 0, dp(2)],
            )
        )
        nut.add_widget(_thin_rule())

        self._nut_row(
            nut,
            "Calories",
            "calories",
            n.calories,
            tuple(RGBA_PRIMARY[:4]),
            calories_mode=True,
            unit_suffix=" kcal",
        )
        nut.add_widget(_thin_rule())
        self._nut_row(nut, "Fat (g)", "fat", n.fat_g, tuple(RGBA_FAT[:4]), unit_suffix=" g")
        nut.add_widget(_thin_rule())
        for label, key, val in (
            ("Saturated", "fat_sat", n.fat_saturated_g),
            ("Trans", "fat_trans", n.fat_trans_g),
            ("Polyunsaturated", "fat_poly", n.fat_polyunsaturated_g),
            ("Monounsaturated", "fat_mono", n.fat_monounsaturated_g),
        ):
            self._nut_row(
                nut,
                label,
                key,
                val,
                _WHITE,
                unit_suffix=" g",
                optional=True,
            )
            nut.add_widget(_thin_rule())
        self._nut_row(
            nut,
            "Carbohydrate (g)",
            "carbs",
            n.carbs_g,
            tuple(RGBA_CARBS[:4]),
            unit_suffix=" g",
        )
        nut.add_widget(_thin_rule())
        self._nut_row(
            nut,
            "Dietary fiber",
            "fiber",
            n.fiber_g,
            _WHITE,
            unit_suffix=" g",
            optional=True,
        )
        nut.add_widget(_thin_rule())
        self._nut_row(
            nut,
            "Sugars",
            "sugar",
            n.sugar_g,
            _WHITE,
            unit_suffix=" g",
            optional=True,
        )
        nut.add_widget(_thin_rule())
        self._nut_row(
            nut,
            "Protein (g)",
            "protein",
            n.protein_g,
            tuple(RGBA_PROTEIN[:4]),
            unit_suffix=" g",
        )
        nut.add_widget(_thin_rule())
        self._nut_row(
            nut,
            "Salt",
            "salt",
            n.salt_mg,
            _WHITE,
            unit_suffix=" mg",
            decimals=0,
            optional=True,
        )
        nut.bind(minimum_height=nut.setter("height"))

        si.add_widget(nut)

    def set_barcode_text(self, barcode: str) -> None:
        w = self._field_refs.get("barcode")
        if w:
            w.text = barcode

    def populate_from_food(self, food: Food) -> None:
        """Replace the draft with ``food`` and rebuild the entire UI.

        Called when a barcode scan finds a matching food in the database so
        all fields (name, brand, nutrition …) are filled automatically.
        """
        self._draft = self._clone_food(food)
        Clock.schedule_once(lambda _dt: self._rebuild_ui(), 0)

    def _meta_row_base(self, label: str) -> tuple[BoxLayout, MDLabel]:
        """Shared skeleton: same BoxLayout + left MDLabel as _nut_row."""
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(6),
        )
        lbl = MDLabel(
            text=label,
            size_hint_x=0.55,
            font_style="Body",
            role="small",
            font_size=card_font(),
            theme_text_color="Custom",
            text_color=_WHITE,
            halign="left",
            valign="middle",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        row.add_widget(lbl)
        return row, lbl

    def _meta_ti(self, value: str, *, optional: bool = False, numeric: bool = False) -> TextInput:
        """Styled TextInput identical to the one used in _nut_row."""
        _teal = list(RGBA_PRIMARY[:3]) + [1.0]
        ti = TextInput(
            text=value,
            size_hint_x=1,
            multiline=False,
            input_filter="float" if numeric else None,
            halign="right",
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=list(_WHITE),
            cursor_color=_teal,
            cursor_width=dp(2),
            selection_color=list(RGBA_PRIMARY[:3]) + [0.25],
            font_size=card_font(),
            hint_text="Optional" if optional else "",
            hint_text_color=list(_HINT),
        )
        ti.bind(height=lambda w, h: setattr(w, "padding", [0, h * 0.25, 0, 0]))
        return ti

    def _meta_unit_lbl(self, unit: str) -> MDLabel:
        """Auto-width unit label identical to the one used in _nut_row."""
        lbl = MDLabel(
            text=unit,
            size_hint_x=None,
            width=dp(36),
            font_style="Body",
            role="small",
            font_size=card_font(),
            theme_text_color="Custom",
            text_color=_HINT,
            halign="left",
            valign="middle",
        )
        lbl.bind(
            size=lambda w, s: setattr(w, "text_size", s),
            texture_size=lambda w, ts: setattr(w, "width", ts[0]) if ts[0] > 0 else None,
        )
        return lbl

    def _add_metadata_text_row(
        self,
        parent: MDBoxLayout,
        label: str,
        key: str,
        value: str,
        *,
        optional_field: bool = False,
        unit_suffix: str = "",
        numeric: bool = False,
    ) -> None:
        row, _ = self._meta_row_base(label)
        ti = self._meta_ti(value, optional=optional_field, numeric=numeric)
        self._field_refs[key] = ti
        row.add_widget(ti)
        if unit_suffix:
            row.add_widget(self._meta_unit_lbl(unit_suffix))
        parent.add_widget(row)

    def _add_barcode_row(self, parent: MDBoxLayout, value: str) -> None:
        row, _ = self._meta_row_base("Barcode")
        t_bc = self._meta_ti(value, optional=True)
        self._field_refs["barcode"] = t_bc
        row.add_widget(t_bc)
        row.add_widget(
            MDIconButton(
                icon="barcode-scan",
                theme_icon_color="Custom",
                icon_color=(1.0, 1.0, 1.0, 1.0),
                size_hint_x=None,
                width=dp(48),
                on_release=lambda *_: self._on_barcode_icon(),
            )
        )
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
        unit_suffix: str = " g",
        decimals: int = 1,
        calories_mode: bool = False,
        optional: bool = False,
    ) -> None:
        row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(6),
        )

        lbl = MDLabel(
            text=label,
            size_hint_x=0.55,
            font_style="Body",
            role="small",
            font_size=card_font(),
            theme_text_color="Custom",
            text_color=label_rgba,
            halign="left",
            valign="middle",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        row.add_widget(lbl)

        # Build number-only initial text
        if calories_mode:
            vtxt = "" if value is None else f"{value:.0f}"
        elif optional:
            if value is None:
                vtxt = ""
            else:
                formatted = f"{value:.{decimals}f}"
                vtxt = "" if abs(float(formatted)) < 1e-9 else formatted
        else:
            v = value if value is not None else 0.0
            vtxt = f"{v:.0f}" if calories_mode else f"{v:.{decimals}f}"
        if vtxt and vtxt.startswith("."):
            vtxt = f"0{vtxt}"

        _teal = list(RGBA_PRIMARY[:3]) + [1.0]
        ti = TextInput(
            text=vtxt,
            size_hint_x=1,          # fills all space left after the fixed-width unit label
            multiline=False,
            input_filter="float",
            halign="right",
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=list(_WHITE),
            cursor_color=_teal,
            cursor_width=dp(2),
            selection_color=list(RGBA_PRIMARY[:3]) + [0.25],
            font_size=card_font(),
            hint_text="Optional" if optional else "",
            hint_text_color=list(_HINT),
        )
        ti.bind(height=lambda w, h: setattr(w, "padding", [0, h * 0.25, 0, 0]))
        self._field_refs[key] = ti
        row.add_widget(ti)

        unit_lbl = MDLabel(
            text=unit_suffix.strip(),
            size_hint_x=None,
            width=dp(36),   # initial render needs non-zero width; shrinks after texture fires
            font_style="Body",
            role="small",
            font_size=card_font(),
            theme_text_color="Custom",
            text_color=_HINT,
            halign="left",
            valign="middle",
        )
        # text_size=self.size lets halign/valign work correctly.
        # texture_size then reports the actual rendered text width so we can
        # shrink the column to fit — "g" becomes narrow, "kcal" stays wider.
        # Starting at dp(36) (not 0) avoids the zero-width render deadlock.
        unit_lbl.bind(
            size=lambda w, s: setattr(w, "text_size", s),
            texture_size=lambda w, ts: setattr(w, "width", ts[0]) if ts[0] > 0 else None,
        )
        row.add_widget(unit_lbl)
        parent.add_widget(row)

Builder.load_file("assets/kv/food_edit.kv")
