"""Full-screen food editor: metadata + nutrition per 100 g (surface cards, ruled rows)."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog,
    MDDialogButtonContainer,
    MDDialogContentContainer,
    MDDialogHeadlineText,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.textfield import MDTextField

import widgets.macros_button  # noqa: F401 — MacrosFilledButton KV
from widgets.macros_button import MacrosFilledButton
from models.food import Food, NutritionInfo
from screens.base_screen import BaseScreen
from services.food_service import FoodService
from services.repository import _salt_g_to_sodium_mg, _sodium_mg_to_salt_g
from utils.constants import (
    RGBA_CARBS,
    RGBA_FAT,
    RGBA_LINE,
    RGBA_POPUP,
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


def _nut_val_w() -> float:
    """Responsive width for the numeric value text field."""
    w = float(Window.width) if Window.width else dp(360)
    return max(dp(80), min(w * 0.24, dp(130)))


def _nut_unit_w() -> float:
    """Consistent unit column width across all rows (sized for 'kcal')."""
    w = float(Window.width) if Window.width else dp(360)
    return max(dp(30), min(w * 0.085, dp(44)))


def _format_serving_g(grams: float) -> str:
    """Single string so the value and ``g`` stay visually tight (no wide gap)."""
    g = float(grams)
    if abs(g - round(g)) < 1e-6:
        return f"{int(round(g))}g"
    return f"{g:.1f}g"


def _style_mdtf(
    tf: MDTextField,
    fg: tuple[float, float, float, float],
    *,
    right_align: bool = True,
    compact: bool = False,
    opt_placeholder: bool = False,
) -> None:
    """Apply text alignment, padding, and foreground color to the inner TextInput.

    Do not pass ``text_color=`` into ``MDTextField(...)`` — Kivy ``TextInput`` rejects it.
    When ``opt_placeholder=True``, sets Kivy's native ``TextInput.hint_text`` = "Optional"
    on the inner widget — this is a simple placeholder that shows only when the field is
    empty and disappears the moment the user types, with no floating-label animation.
    """

    def _apply(*_a: object) -> None:
        try:
            inner = tf.ids.get("text_field")
            if inner is None:
                Clock.schedule_once(_apply, 0.05)
                return
            inner.font_size = card_font()
            inner.multiline = False
            if right_align:
                inner.halign = "right"
                if compact:
                    inner.padding = [dp(2), dp(0), dp(4), dp(0)]
                else:
                    inner.padding = [dp(5), dp(5), dp(6), dp(5)]
            inner.foreground_color = fg
            if opt_placeholder:
                inner.hint_text = "Optional"
                inner.hint_text_color = list(_HINT)
        except Exception:  # pylint: disable=broad-except
            pass

    Clock.schedule_once(_apply, 0)


class _ServingSizesRow(ButtonBehavior, MDBoxLayout):
    """Tappable row: label, grams, chevron → opens serving dialog."""

    def __init__(self, value_g: float, on_open: Callable[[], None], **kwargs: object) -> None:
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(12), dp(4), dp(10), dp(4)],
            spacing=dp(4),
            **kwargs,
        )
        self._on_open = on_open
        self.value_label = MDLabel(
            text=_format_serving_g(value_g),
            size_hint_x=1,
            font_style="Body",
            role="small",
            font_size=card_font(),
            theme_text_color="Custom",
            text_color=_WHITE,
            halign="right",
            valign="middle",
        )
        self.add_widget(
            MDLabel(
                text="Serving sizes",
                size_hint_x=None,
                width=dp(132),
                font_style="Body",
                role="small",
                font_size=card_font(),
                theme_text_color="Custom",
                text_color=_WHITE,
                halign="left",
                valign="middle",
            )
        )
        self.add_widget(self.value_label)
        self.add_widget(
            MDIcon(
                icon="chevron-right",
                theme_text_color="Custom",
                text_color=tuple(RGBA_LINE[:4]),
                size_hint_x=None,
                width=dp(22),
            )
        )

    def set_value_g(self, grams: float) -> None:
        self.value_label.text = _format_serving_g(grams)

    def on_release(self) -> None:
        self._on_open()


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
        self._field_refs: dict[str, MDTextField] = {}
        self._barcode_scan_cb: Optional[Callable[[], None]] = None
        self._return_screen: str = "food_search"
        self._serving_size_g: float = 100.0
        self._serving_row: Optional[_ServingSizesRow] = None

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
        self._serving_size_g = float(self._draft.serving_size_g or 100.0)
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

    def _open_serving_size_dialog(self) -> None:
        dlg_ref: list[MDDialog] = []

        tf = MDTextField(
            text=(
                str(int(self._serving_size_g))
                if abs(self._serving_size_g - round(self._serving_size_g)) < 1e-6
                else f"{self._serving_size_g:.1f}"
            ),
            mode="filled",
            size_hint_y=None,
            height=dp(52),
            input_filter="float",
            theme_bg_color="Custom",
            fill_color_normal=(*RGBA_SURFACE[:3], 1),
            theme_line_color="Custom",
            line_color_normal=(0, 0, 0, 0),
        )
        _style_mdtf(tf, _WHITE, right_align=False, opt_placeholder=True)

        def apply_ok(*_a: object) -> None:
            try:
                raw = (tf.text or "").strip()
                v = float(raw) if raw else 100.0
                v = max(1.0, v)
                self._serving_size_g = v
                if self._serving_row is not None:
                    self._serving_row.set_value_g(v)
                dlg_ref[0].dismiss()
            except ValueError:
                self.show_error("Enter a valid number of grams.")

        def cancel(*_a: object) -> None:
            dlg_ref[0].dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Serving sizes"),
            MDDialogContentContainer(
                tf,
                orientation="vertical",
                padding=[dp(8), dp(12), dp(8), dp(8)],
            ),
            MDDialogButtonContainer(
                Widget(),
                MacrosFilledButton(
                    MDButtonText(text="Cancel"),
                    on_release=cancel,
                ),
                MacrosFilledButton(
                    MDButtonText(text="OK"),
                    on_release=apply_ok,
                ),
                spacing="8dp",
            ),
            theme_bg_color="Custom",
            md_bg_color=RGBA_POPUP,
        )
        dlg_ref.append(dlg)
        dlg.open()

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
        serving = max(1.0, float(self._serving_size_g))

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
            if not w:
                return None
            t = (w.text or "").strip()
            if not t:
                return None
            try:
                return float(t)
            except ValueError:
                return None

        salt_g = fo("salt")
        sodium_mg = _salt_g_to_sodium_mg(salt_g) if salt_g is not None else None

        return NutritionInfo(
            calories=f("calories", 0.0),
            protein_g=f("protein", 0.0),
            carbs_g=f("carbs", 0.0),
            fat_g=f("fat", 0.0),
            fiber_g=fo("fiber"),
            sugar_g=fo("sugar"),
            sodium_mg=sodium_mg,
            fat_saturated_g=fo("fat_sat"),
            fat_trans_g=fo("fat_trans"),
            fat_polyunsaturated_g=fo("fat_poly"),
            fat_monounsaturated_g=fo("fat_mono"),
        )

    def _rebuild_ui(self) -> None:
        si = self.ids.scroll_inner
        si.clear_widgets()
        self._field_refs.clear()
        self._serving_row = None
        if self._draft is None:
            return

        f = self._draft
        n = f.nutrition or NutritionInfo()
        self._serving_size_g = float(f.serving_size_g or 100.0)
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

        self._serving_row = _ServingSizesRow(
            self._serving_size_g,
            self._open_serving_size_dialog,
        )
        info.add_widget(self._serving_row)
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
                indent=dp(14),
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
            indent=dp(14),
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
            indent=dp(14),
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
        salt_display = _sodium_mg_to_salt_g(n.sodium_mg)
        self._nut_row(
            nut,
            "Salt",
            "salt",
            salt_display,
            _WHITE,
            unit_suffix=" g",
            decimals=2,
            optional=True,
        )
        nut.bind(minimum_height=nut.setter("height"))

        si.add_widget(nut)

    def set_barcode_text(self, barcode: str) -> None:
        w = self._field_refs.get("barcode")
        if w:
            w.text = barcode

    def _add_metadata_text_row(
        self,
        parent: MDBoxLayout,
        label: str,
        key: str,
        value: str,
        *,
        optional_field: bool = False,
    ) -> None:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            padding=[dp(12), dp(4), dp(12), dp(4)],
            spacing=dp(8),
        )
        row.add_widget(
            MDLabel(
                text=label,
                size_hint_x=None,
                width=dp(132),
                font_style="Body",
                role="small",
                font_size=card_font(),
                theme_text_color="Custom",
                text_color=_WHITE,
                halign="left",
                valign="middle",
            )
        )
        empty = not (value or "").strip()
        tf = MDTextField(
            text=value if not (optional_field and empty) else "",
            mode="filled",
            size_hint_x=1,
            size_hint_y=None,
            height=dp(40),
            theme_bg_color="Custom",
            fill_color_normal=(*RGBA_SURFACE[:3], 1),
            theme_line_color="Custom",
            line_color_normal=(0, 0, 0, 0),
        )
        self._field_refs[key] = tf
        _style_mdtf(tf, _WHITE, opt_placeholder=optional_field)
        row.add_widget(tf)
        parent.add_widget(row)

    def _add_barcode_row(self, parent: MDBoxLayout, value: str) -> None:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(46),
            padding=[dp(12), dp(4), dp(4), dp(4)],
            spacing=dp(4),
        )
        row.add_widget(
            MDLabel(
                text="Barcode",
                size_hint_x=None,
                width=dp(132),
                font_style="Body",
                role="small",
                font_size=card_font(),
                theme_text_color="Custom",
                text_color=_WHITE,
                halign="left",
                valign="middle",
            )
        )
        t_bc = MDTextField(
            text=value,
            mode="filled",
            size_hint_x=1,
            size_hint_y=None,
            height=dp(40),
            theme_bg_color="Custom",
            fill_color_normal=(*RGBA_SURFACE[:3], 1),
            theme_line_color="Custom",
            line_color_normal=(0, 0, 0, 0),
        )
        self._field_refs["barcode"] = t_bc
        _style_mdtf(t_bc, _WHITE, opt_placeholder=True)
        row.add_widget(t_bc)
        row.add_widget(
            MDIconButton(
                icon="barcode-scan",
                theme_icon_color="Custom",
                icon_color=(1.0, 1.0, 1.0, 1.0),
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
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            padding=[indent, dp(2), dp(0), dp(2)],
            spacing=dp(0),
        )
        row.add_widget(
            MDLabel(
                text=label,
                size_hint_x=0.40,
                font_style="Body",
                role="small",
                font_size=card_font(),
                theme_text_color="Custom",
                text_color=label_rgba,
                halign="left",
                valign="middle",
            )
        )

        vtxt = ""
        is_opt_placeholder = False

        if calories_mode:
            vtxt = "" if value is None else f"{value:.0f}"
        elif optional:
            if value is None:
                vtxt = ""
                is_opt_placeholder = True
            else:
                formatted = f"{value:.{decimals}f}"
                try:
                    if abs(float(formatted)) < 1e-9:
                        vtxt = ""
                        is_opt_placeholder = True
                    else:
                        vtxt = formatted
                except ValueError:
                    vtxt = formatted
        elif value is None:
            vtxt = f"{0.0:.{decimals}f}"
        else:
            vtxt = f"{value:.{decimals}f}"

        if vtxt and vtxt.startswith("."):
            vtxt = f"0{vtxt}"

        unit_txt = unit_suffix.strip()
        val_w = _nut_val_w()
        unit_w = _nut_unit_w()

        value_area = MDBoxLayout(
            orientation="horizontal",
            size_hint_x=0.60,
            spacing=dp(0),
        )
        value_area.add_widget(Widget(size_hint_x=1))

        tf = MDTextField(
            text=vtxt,
            mode="filled",
            size_hint_x=None,
            width=val_w,
            size_hint_y=None,
            height=dp(32),
            theme_bg_color="Custom",
            fill_color_normal=tuple(RGBA_SURFACE[:4]),
            theme_line_color="Custom",
            line_color_normal=(0, 0, 0, 0),
            input_filter="float",
        )
        self._field_refs[key] = tf

        _style_mdtf(tf, _WHITE, compact=True, opt_placeholder=is_opt_placeholder)

        value_area.add_widget(tf)

        unit_lbl = MDLabel(
            text=unit_txt,
            size_hint_x=None,
            width=unit_w,
            font_style="Body",
            role="small",
            font_size=card_font(),
            theme_text_color="Custom",
            text_color=_HINT,
            halign="left",
            valign="middle",
        )
        value_area.add_widget(unit_lbl)
        value_area.add_widget(Widget(size_hint_x=1))

        row.add_widget(value_area)
        parent.add_widget(row)

Builder.load_file("assets/kv/food_edit.kv")
