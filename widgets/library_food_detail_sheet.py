"""Full-screen sheet: library food nutrition, macro pie chart, grams, Add."""

from __future__ import annotations

import math
from typing import Callable, List, Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButtonText, MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField, MDTextFieldMaxLengthText

from models.food import Food, NutritionInfo
from utils.constants import (
    COLOR_CARBS,
    RGBA_BG,
    RGBA_CARBS,
    RGBA_FAT,
    RGBA_PRIMARY,
    RGBA_PROTEIN,
    RGBA_SURFACE,
    hex_to_rgba,
)
from widgets.macro_pie_chart import EXPLODE_DP, SEGMENT_GAP_DEG
from widgets.macros_button import MacrosFilledButton
import widgets.macros_button  # noqa: F401 — registers Macros*Button

Builder.load_string("""
#:import dp kivy.metrics.dp
#:import RGBA_PRIMARY utils.constants.RGBA_PRIMARY

<LibraryFoodDetailSheet>:
    size_hint: 1, 1
    auto_dismiss: False
    overlay_color: 0, 0, 0, 0.6
    # Match Profile/Goals modals — default ModalView background otherwise tints the whole sheet.
    background: " "
    background_color: 0, 0, 0, 0
""")


def _macro_calories_from_grams(p: float, c: float, f: float) -> tuple[float, float, float]:
    """Atwater-style kcal from grams of protein, carbs, and fat."""
    return p * 4.0, c * 4.0, f * 9.0


def _kcal_label_text(kcal: float) -> str:
    """Compact kcal string for slice labels."""
    if kcal < 1.0:
        return f"{kcal:.1f} kcal"
    return f"{kcal:.0f} kcal"


class MacroCaloriePieChart(FloatLayout):
    """Macro kcal donut pie: same geometry as ``MacroPieChart`` (gaps, explode, labels)."""

    _SLICE_COLORS: List[tuple[float, float, float, float]] = [
        tuple(RGBA_PROTEIN[:4]),
        tuple(RGBA_CARBS[:4]),
        tuple(RGBA_FAT[:4]),
    ]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(size_hint=(1, 1), **kwargs)
        self._p = self._c = self._f = 0.0
        self._pie_canvas = Widget(size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        lbl_kw = {
            "size_hint": (None, None),
            "size": (dp(80), dp(28)),
            "bold": True,
            "halign": "center",
            "valign": "middle",
            "theme_text_color": "Custom",
            "text_color": (1, 1, 1, 1),
            "font_style": "Title",
            "role": "small",
        }
        self._lbl_p = MDLabel(**lbl_kw)
        self._lbl_c = MDLabel(**lbl_kw)
        self._lbl_f = MDLabel(**lbl_kw)
        self.add_widget(self._pie_canvas)
        self.add_widget(self._lbl_p)
        self.add_widget(self._lbl_c)
        self.add_widget(self._lbl_f)
        self._trigger = Clock.create_trigger(self._redraw, 0.08)
        self.bind(pos=self._schedule_redraw, size=self._schedule_redraw)

    def on_parent(self, *_args: object) -> None:
        self._schedule_redraw()

    def _schedule_redraw(self, *_args: object) -> None:
        self._trigger()

    def set_macros_g(self, protein_g: float, carbs_g: float, fat_g: float) -> None:
        self._p = max(0.0, protein_g)
        self._c = max(0.0, carbs_g)
        self._f = max(0.0, fat_g)
        self._schedule_redraw()

    def _redraw(self, *_args: object) -> None:
        self._pie_canvas.canvas.clear()
        kp, kc, kf = _macro_calories_from_grams(self._p, self._c, self._f)
        kcals = [kp, kc, kf]
        total = kp + kc + kf
        labels = (self._lbl_p, self._lbl_c, self._lbl_f)

        if self.width < 4 or self.height < 4:
            for lbl in labels:
                lbl.opacity = 0
            return

        cx = self.center_x
        cy = self.center_y
        radius = min(self.width, self.height) / 2.0 * 0.85
        if radius <= 0:
            for lbl in labels:
                lbl.opacity = 0
            return

        if total <= 1e-9:
            with self._pie_canvas.canvas:
                Color(0.35, 0.35, 0.38, 1)
                Ellipse(pos=(cx - radius, cy - radius), size=(radius * 2, radius * 2))
            for lbl in labels:
                lbl.text = ""
                lbl.opacity = 0
            return

        diameter = radius * 2.0
        gap_half = SEGMENT_GAP_DEG / 2.0
        explode = dp(EXPLODE_DP)
        mid_angles: List[float] = []

        with self._pie_canvas.canvas:
            cur = 0.0
            for i, k in enumerate(kcals):
                if k <= 1e-12:
                    mid_angles.append(cur)
                    continue
                sweep = (k / total) * 360.0
                seg_start = cur + gap_half
                seg_end = cur + sweep - gap_half
                mid = (seg_start + seg_end) / 2.0
                mid_angles.append(mid)
                r, g, b, a = self._SLICE_COLORS[i]
                Color(r, g, b, a)
                mid_rad = math.radians(mid)
                edx = explode * math.sin(mid_rad)
                edy = explode * math.cos(mid_rad)
                Ellipse(
                    pos=(cx + edx - radius, cy + edy - radius),
                    size=(diameter, diameter),
                    angle_start=seg_start,
                    angle_end=seg_end,
                )
                cur += sweep

            hole_r, hole_g, hole_b, hole_a = RGBA_SURFACE
            Color(hole_r, hole_g, hole_b, hole_a)
            inner_r = radius * 0.33
            Ellipse(
                pos=(cx - inner_r, cy - inner_r),
                size=(inner_r * 2.0, inner_r * 2.0),
            )

        inner_r = radius * 0.33
        label_radius = (radius + inner_r) / 2.0 + explode
        lw = float(self._lbl_p.width)
        lh = float(self._lbl_p.height)

        for i, lbl in enumerate(labels):
            k = kcals[i]
            if k <= 0.05:
                lbl.text = ""
                lbl.opacity = 0
                continue
            lbl.opacity = 1
            lbl.text = _kcal_label_text(k)
            angle_deg = mid_angles[i] if i < len(mid_angles) else 0.0
            angle_rad = math.radians(angle_deg)
            x = cx + label_radius * math.sin(angle_rad)
            y = cy + label_radius * math.cos(angle_rad)
            lbl.pos = (x - lw / 2.0, y - lh / 2.0)


class LibraryFoodDetailSheet(ModalView):
    """Nutrition detail for a library food: name, pie, macro columns, grams, Add."""

    def __init__(
        self,
        food: Food,
        on_add: Callable[[float, str], None],
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._food = food
        self._canonical_name = (food.name or "").strip() or "Food"
        self._on_add = on_add
        self._base: Optional[NutritionInfo] = food.nutrition
        self._macro_chart = MacroCaloriePieChart()
        self._name_row: Optional[MDBoxLayout] = None
        self._pie_box: Optional[MDBoxLayout] = None
        self._name_block: Optional[MDBoxLayout] = None
        self._name_field: Optional[MDTextField] = None
        self._canonical_lbl: Optional[MDLabel] = None
        self._qty_field: Optional[MDTextField] = None
        self._lbl_cal: Optional[MDLabel] = None
        self._lbl_p: Optional[MDLabel] = None
        self._lbl_c: Optional[MDLabel] = None
        self._lbl_f: Optional[MDLabel] = None
        self._build()

    def _build(self) -> None:
        root = MDBoxLayout(orientation="vertical", md_bg_color=RGBA_BG)
        food = self._food

        # Header (teal)
        header = MDBoxLayout(
            size_hint_y=None,
            height=dp(56),
            padding=[dp(4), 0, dp(8), 0],
            md_bg_color=RGBA_PRIMARY,
        )
        header.add_widget(
            MDIconButton(
                icon="arrow-left",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
                on_release=lambda *_: self.dismiss(),
            )
        )
        title = MDLabel(
            text="Nutrition",
            font_style="Title",
            role="medium",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        header.add_widget(title)
        root.add_widget(header)

        body = MDBoxLayout(
            orientation="vertical",
            spacing=dp(16),
            padding=[dp(16), dp(20), dp(16), dp(16)],
            size_hint_y=1,
        )

        # Name + pie row — height and pie box size follow window (see _sync_top_layout).
        name_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=max(dp(160), min(Window.height * 0.26, dp(320))),
            spacing=dp(12),
        )
        name_col = MDBoxLayout(
            orientation="vertical",
            size_hint_x=1,
            spacing=dp(6),
        )
        _white = (0.97, 0.98, 1.0, 1)
        # KivyMD 2: max length is set via MDTextFieldMaxLengthText child, not a kwarg.
        self._name_field = MDTextField(
            MDTextFieldMaxLengthText(max_text_length=200),
            text=self._canonical_name,
            hint_text="Name",
            mode="filled",
            size_hint_y=None,
            height=dp(56),
            font_style="Title",
            role="medium",
            theme_text_color="Custom",
            text_color_normal=_white,
            text_color_focus=_white,
            line_color_focus=tuple(RGBA_PRIMARY[:4]),
        )
        name_col.add_widget(self._name_field)
        self._canonical_lbl = MDLabel(
            text=self._canonical_name,
            font_style="Body",
            role="small",
            theme_text_color="Custom",
            text_color=tuple(hex_to_rgba(COLOR_CARBS)),
            size_hint_y=None,
            height=dp(80),
            halign="left",
            valign="top",
            shorten=True,
            shorten_from="right",
            max_lines=4,
        )
        self._canonical_lbl.bind(size=self._on_canonical_label_size)
        name_col.add_widget(self._canonical_lbl)
        name_row.add_widget(name_col)
        pie_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            size=(dp(120), dp(120)),
            md_bg_color=RGBA_SURFACE,
            radius=[dp(8), dp(8), dp(8), dp(8)],
            padding=[dp(4), dp(4), dp(4), dp(4)],
        )
        pie_box.add_widget(self._macro_chart)
        name_row.add_widget(pie_box)

        name_block = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(200),
            spacing=dp(8),
        )
        name_block.add_widget(name_row)
        body.add_widget(name_block)

        # Four macro columns
        row4 = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(84),
            spacing=dp(6),
            padding=[0, 0, 0, 0],
        )
        col_cal, self._lbl_cal = self._macro_column("Calories", RGBA_PRIMARY)
        col_p, self._lbl_p = self._macro_column("Protein", RGBA_PROTEIN)
        col_c, self._lbl_c = self._macro_column("Carbs", RGBA_CARBS)
        col_f, self._lbl_f = self._macro_column("Fat", RGBA_FAT)
        row4.add_widget(col_cal)
        row4.add_widget(col_p)
        row4.add_widget(col_c)
        row4.add_widget(col_f)
        body.add_widget(row4)

        # Grams: narrow field (~30% width) + label, then Add directly below
        qty_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            spacing=dp(12),
            padding=[0, 0, 0, 0],
        )
        self._qty_field = MDTextField(
            hint_text="Amount",
            text="100",
            mode="filled",
            input_filter="float",
            size_hint_x=0.3,
            size_hint_y=None,
            height=dp(56),
        )
        self._qty_field.bind(text=self._on_qty_text)
        qty_row.add_widget(self._qty_field)
        qty_row.add_widget(
            MDLabel(
                text="grams",
                font_style="Body",
                role="medium",
                theme_text_color="Custom",
                text_color=(0.75, 0.78, 0.82, 1),
                size_hint_x=None,
                width=dp(72),
                halign="left",
                valign="center",
            )
        )
        qty_row.add_widget(MDBoxLayout(size_hint_x=1))
        body.add_widget(qty_row)

        add_btn = MacrosFilledButton(
            size_hint_y=None,
            height=dp(48),
            size_hint_x=1,
            on_release=lambda *_: self._confirm_add(),
        )
        add_btn.add_widget(MDButtonText(text="Add", halign="center"))
        body.add_widget(add_btn)

        body.add_widget(MDBoxLayout(size_hint_y=1))

        root.add_widget(body)

        self.add_widget(root)
        self._name_row = name_row
        self._pie_box = pie_box
        self._name_block = name_block
        name_row.bind(width=self._sync_top_layout, height=self._sync_top_layout)
        Window.bind(width=self._sync_top_layout, height=self._sync_top_layout)
        self.bind(on_dismiss=self._on_dismiss_unbind_layout)
        Clock.schedule_once(self._sync_top_layout, 0.1)
        self._refresh_values()

    def _on_dismiss_unbind_layout(self, *_args: object) -> None:
        if self._name_row:
            self._name_row.unbind(width=self._sync_top_layout, height=self._sync_top_layout)
        Window.unbind(width=self._sync_top_layout, height=self._sync_top_layout)

    def _sync_top_layout(self, *_args: object) -> None:
        """Resize name row and square pie card from window and row width (responsive)."""
        if not self._name_row or not self._pie_box or not self._name_block:
            return
        wh = max(float(Window.height), 1.0)
        row_h = max(dp(160), min(wh * 0.26, dp(320)))
        self._name_row.height = row_h
        rw = self._name_row.width
        if rw > 10:
            side = min(rw * 0.40, row_h * 0.92)
            side = max(dp(88), min(side, dp(300)))
            self._pie_box.size = (side, side)
        self._name_block.height = row_h + dp(8)

    def _on_canonical_label_size(self, instance: MDLabel, size: tuple[float, float]) -> None:
        if size[0] > 1:
            instance.text_size = (size[0], None)

    def _macro_column(
        self, title: str, rgba: list[float]
    ) -> tuple[MDBoxLayout, MDLabel]:
        col = MDBoxLayout(
            orientation="vertical",
            spacing=dp(4),
            md_bg_color=RGBA_SURFACE,
            radius=[dp(8), dp(8), dp(8), dp(8)],
            padding=[dp(8), dp(10), dp(8), dp(10)],
            size_hint_x=1,
        )
        t = MDLabel(
            text=title,
            font_style="Body",
            role="small",
            theme_text_color="Custom",
            text_color=(0.65, 0.68, 0.72, 1),
            halign="center",
            size_hint_y=None,
            height=dp(18),
        )
        val = MDLabel(
            text="0",
            font_style="Title",
            role="small",
            theme_text_color="Custom",
            text_color=tuple(rgba[:4]),
            halign="center",
            size_hint_y=None,
            height=dp(30),
        )
        col.add_widget(t)
        col.add_widget(val)
        return col, val

    def _on_qty_text(self, _instance: MDTextField, text: str) -> None:
        self._refresh_values()

    def _parse_qty(self) -> float:
        if self._qty_field is None:
            return 100.0
        try:
            q = float((self._qty_field.text or "100").strip())
            return max(0.0, q)
        except ValueError:
            return 100.0

    def _refresh_values(self) -> None:
        base = self._base or NutritionInfo()
        qty = self._parse_qty()
        scaled = base.scale(qty)
        p, c, fd = scaled.protein_g, scaled.carbs_g, scaled.fat_g
        cal = scaled.calories

        if self._lbl_cal:
            self._lbl_cal.text = f"{cal:.0f} kcal"
        if self._lbl_p:
            self._lbl_p.text = f"{p:.1f} g"
        if self._lbl_c:
            self._lbl_c.text = f"{c:.1f} g"
        if self._lbl_f:
            self._lbl_f.text = f"{fd:.1f} g"
        self._macro_chart.set_macros_g(p, c, fd)

    def _confirm_add(self) -> None:
        qty = self._parse_qty()
        raw = ""
        if self._name_field is not None:
            raw = (self._name_field.text or "").strip()
        display_name = raw if raw else self._canonical_name
        self.dismiss()
        self._on_add(qty, display_name)
