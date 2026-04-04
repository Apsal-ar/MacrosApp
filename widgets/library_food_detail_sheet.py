"""Full-screen sheet: library food nutrition, macro pie chart, grams, Add."""

from __future__ import annotations

import math
from typing import Callable, List, Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButtonText, MDIconButton
from kivymd.uix.label import MDLabel
from models.food import Food, NutritionInfo
from utils.constants import (
    COLOR_CARBS,
    RGBA_BG,
    RGBA_CARBS,
    RGBA_FAT,
    RGBA_LINE,
    RGBA_PRIMARY,
    RGBA_PROTEIN,
    RGBA_SURFACE,
    UI_CORNER_RADIUS_DP,
    hex_to_rgba,
)
from widgets.macro_pie_chart import EXPLODE_DP, SEGMENT_GAP_DEG
from widgets.macros_button import MacrosFilledButton, MacrosTextButton
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
    """Numeric-only label on pie slices (no unit)."""
    if kcal < 1.0:
        return f"{kcal:.1f}"
    return f"{kcal:.0f}"


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
            "size": (dp(52), dp(28)),
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


def _thin_hline() -> MDBoxLayout:
    """1dp horizontal rule; same as nutrition-facts row separators in this sheet."""
    return MDBoxLayout(
        size_hint_y=None,
        height=dp(1),
        md_bg_color=(0.32, 0.33, 0.36, 1),
    )


class LibraryFoodDetailSheet(ModalView):
    """Nutrition detail for a library food: name, pie, macro columns, grams, primary action."""

    def __init__(
        self,
        food: Food,
        on_add: Callable[[float, str], None],
        on_edit: Optional[Callable[[], None]] = None,
        *,
        primary_button_text: str = "Add",
        initial_quantity_g: Optional[float] = None,
        **kwargs: object,
    ) -> None:
        kwargs.setdefault("padding", [0, 0, 0, 0])
        super().__init__(**kwargs)
        self._food = food
        self._canonical_name = (food.name or "").strip() or "Food"
        self._on_add = on_add
        self._on_edit = on_edit
        self._primary_button_text = primary_button_text
        self._initial_quantity_g = initial_quantity_g
        self._base: Optional[NutritionInfo] = food.nutrition
        self._macro_chart = MacroCaloriePieChart()
        self._name_row: Optional[MDBoxLayout] = None
        self._pie_box: Optional[MDBoxLayout] = None
        self._title_lbl: Optional[MDLabel] = None
        self._qty_field: Optional[TextInput] = None
        self._lbl_cal: Optional[MDLabel] = None
        self._lbl_p: Optional[MDLabel] = None
        self._lbl_c: Optional[MDLabel] = None
        self._lbl_f: Optional[MDLabel] = None
        self._facts_box: Optional[MDBoxLayout] = None
        self._build()

    def _build(self) -> None:
        root = MDBoxLayout(
            orientation="vertical",
            md_bg_color=RGBA_BG,
            spacing=0,
            padding=[0, 0, 0, 0],
        )
        food = self._food

        # Header (teal): back left, title centered on full width.
        header = MDBoxLayout(
            size_hint_y=None,
            height=dp(56),
            padding=0,
            md_bg_color=RGBA_PRIMARY,
        )
        header_inner = FloatLayout(size_hint=(1, 1))
        hdr_title = MDLabel(
            text="Nutrition",
            font_style="Title",
            role="medium",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            halign="center",
            valign="middle",
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            size_hint=(1, None),
            text_size=(None, None),
        )
        header_inner.add_widget(hdr_title)
        header_inner.add_widget(
            MDIconButton(
                icon="arrow-left",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 1),
                pos_hint={"x": 0, "center_y": 0.5},
                on_release=lambda *_: self.dismiss(),
            )
        )
        header.add_widget(header_inner)
        root.add_widget(header)

        body = MDBoxLayout(
            orientation="vertical",
            spacing=dp(16),
            padding=[dp(16), 0, dp(16), dp(16)],
            size_hint_y=1,
        )

        # Food name (centered in left column) + pie card — pie vertically centered in row.
        name_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=max(dp(120), min(Window.height * 0.22, dp(280))),
            spacing=dp(12),
            padding=[0, 0, 0, 0],
        )
        name_anchor = AnchorLayout(
            anchor_x="center",
            anchor_y="center",
            size_hint_x=1,
            padding=[0, 0, 0, 0],
        )
        self._title_lbl = MDLabel(
            text=self._canonical_name,
            font_style="Title",
            role="small",
            theme_text_color="Custom",
            text_color=tuple(hex_to_rgba(COLOR_CARBS)),
            size_hint=(1, None),
            halign="center",
            valign="middle",
            shorten=False,
            max_lines=0,
        )

        def _title_wrap_width(*_a: object) -> None:
            if self._title_lbl is None:
                return
            w = max(name_anchor.width - dp(4), 1.0)
            self._title_lbl.text_size = (w, None)

        name_anchor.bind(width=_title_wrap_width)
        name_anchor.add_widget(self._title_lbl)
        Clock.schedule_once(lambda _dt: _title_wrap_width(), 0)
        name_row.add_widget(name_anchor)
        pie_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(None, None),
            size=(dp(120), dp(120)),
            pos_hint={"center_y": 0.5},
            md_bg_color=RGBA_BG,
            radius=[dp(8), dp(8), dp(8), dp(8)],
            padding=[dp(4), dp(4), dp(4), dp(4)],
        )
        pie_box.add_widget(self._macro_chart)
        name_row.add_widget(pie_box)

        # Four macro columns (stacked with name_row below — no gap)
        # Natural content height; equal vertical padding to the rules above/below.
        _macro_row_pad_v = dp(8)
        _macro_col_h = dp(50)  # matches _macro_column padding + value + name rows
        row4 = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=_macro_col_h,
            spacing=dp(6),
            padding=[0, 0, 0, 0],
        )
        col_cal, self._lbl_cal = self._macro_column("calories", RGBA_PRIMARY, _macro_col_h)
        col_p, self._lbl_p = self._macro_column("protein", RGBA_PROTEIN, _macro_col_h)
        col_c, self._lbl_c = self._macro_column("carbs", RGBA_CARBS, _macro_col_h)
        col_f, self._lbl_f = self._macro_column("fat", RGBA_FAT, _macro_col_h)
        row4.add_widget(col_cal)
        row4.add_widget(col_p)
        row4.add_widget(col_c)
        row4.add_widget(col_f)
        macro_padded = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=_macro_col_h + 2 * _macro_row_pad_v,
            spacing=0,
            padding=[0, _macro_row_pad_v, 0, _macro_row_pad_v],
        )
        macro_padded.add_widget(row4)

        summary_stack = MDBoxLayout(
            orientation="vertical",
            spacing=0,
            size_hint_y=None,
        )
        summary_stack.add_widget(name_row)
        summary_stack.add_widget(_thin_hline())
        summary_stack.add_widget(macro_padded)
        summary_stack.add_widget(_thin_hline())
        summary_stack.bind(minimum_height=summary_stack.setter("height"))
        body.add_widget(summary_stack)

        # Grams: tight bordered box (TextInput avoids MD filled vertical padding); "g" outside
        _qty_h = dp(38)
        qty_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=_qty_h,
            spacing=dp(8),
            padding=[0, 0, 0, 0],
        )
        r = dp(UI_CORNER_RADIUS_DP)
        qty_box = MDBoxLayout(
            orientation="horizontal",
            padding=[dp(8), dp(2), dp(8), dp(2)],
            size_hint_x=None,
            width=dp(84),
            size_hint_y=None,
            height=_qty_h,
            md_bg_color=RGBA_BG,
            theme_bg_color="Custom",
            line_color=tuple(RGBA_LINE[:4]),
            line_width=1,
            radius=[r, r, r, r],
        )
        _qty_txt = "100"
        if self._initial_quantity_g is not None:
            q0 = float(self._initial_quantity_g)
            _qty_txt = f"{q0:.0f}" if abs(q0 - round(q0)) < 1e-6 else f"{q0:.1f}"
        self._qty_field = TextInput(
            text=_qty_txt,
            input_filter="float",
            multiline=False,
            write_tab=False,
            halign="center",
            size_hint_x=1,
            size_hint_y=1,
            background_color=(0, 0, 0, 0),
            foreground_color=(0.92, 0.93, 0.95, 1),
            cursor_color=(1, 1, 1, 1),
            padding=[dp(6), 0, dp(6), 0],
            font_size=sp(16),
        )
        self._qty_field.bind(text=self._on_qty_text)
        self._qty_field.bind(size=self._sync_qty_field_padding, font_size=self._sync_qty_field_padding)
        Clock.schedule_once(self._sync_qty_field_padding, 0)
        qty_box.add_widget(self._qty_field)
        g_lbl = MDLabel(
            text="g",
            font_style="Body",
            role="medium",
            theme_text_color="Custom",
            text_color=(0.75, 0.78, 0.82, 1),
            size_hint_x=None,
            width=dp(16),
            size_hint_y=None,
            height=_qty_h,
            halign="left",
            valign="middle",
        )

        def _sync_g_text_size(*_a: object) -> None:
            g_lbl.text_size = (g_lbl.width, g_lbl.height)

        g_lbl.bind(width=_sync_g_text_size, height=_sync_g_text_size)
        Clock.schedule_once(lambda _dt: _sync_g_text_size(), 0)
        qty_row.add_widget(qty_box)
        qty_row.add_widget(g_lbl)
        qty_row.add_widget(MDBoxLayout(size_hint_x=1))
        body.add_widget(qty_row)

        if self._on_edit is not None:
            action_row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(48),
                spacing=dp(8),
            )
            add_btn = MacrosFilledButton(
                size_hint_x=0.6667,
                size_hint_y=None,
                height=dp(48),
                on_release=lambda *_: self._confirm_add(),
            )
            add_btn.add_widget(
                MDButtonText(text=self._primary_button_text, halign="center")
            )
            action_row.add_widget(add_btn)
            edit_btn = MacrosTextButton(
                size_hint_x=0.3333,
                size_hint_y=None,
                height=dp(48),
                on_release=lambda *_: self._on_edit_pressed(),
            )
            edit_btn.add_widget(
                MDButtonText(
                    text="Edit",
                    halign="center",
                    theme_text_color="Custom",
                    text_color=tuple(RGBA_PRIMARY[:4]),
                )
            )
            action_row.add_widget(edit_btn)
            body.add_widget(action_row)
        else:
            add_btn = MacrosFilledButton(
                size_hint_y=None,
                height=dp(48),
                size_hint_x=1,
                on_release=lambda *_: self._confirm_add(),
            )
            add_btn.add_widget(
                MDButtonText(text=self._primary_button_text, halign="center")
            )
            body.add_widget(add_btn)

        facts_scroll = ScrollView(
            size_hint=(1, 1),
            do_scroll_x=False,
            bar_width=dp(5),
        )
        self._facts_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=0,
            padding=[dp(4), dp(12), dp(4), dp(8)],
        )
        self._facts_box.bind(minimum_height=self._facts_box.setter("height"))
        facts_scroll.add_widget(self._facts_box)
        body.add_widget(facts_scroll)

        root.add_widget(body)

        self.add_widget(root)
        self._name_row = name_row
        self._pie_box = pie_box
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
        if not self._name_row or not self._pie_box:
            return
        wh = max(float(Window.height), 1.0)
        row_h = max(dp(120), min(wh * 0.22, dp(280)))
        self._name_row.height = row_h
        rw = self._name_row.width
        if rw > 10:
            side = min(rw * 0.40, row_h * 0.92)
            side = max(dp(88), min(side, dp(300)))
            self._pie_box.size = (side, side)

    def _macro_column(
        self, name_below: str, rgba: list[float], col_height: float
    ) -> tuple[MDBoxLayout, MDLabel]:
        col = MDBoxLayout(
            orientation="vertical",
            spacing=0,
            md_bg_color=RGBA_BG,
            radius=[dp(8), dp(8), dp(8), dp(8)],
            padding=[dp(8), dp(2), dp(8), dp(2)],
            size_hint_x=1,
            size_hint_y=None,
            height=col_height,
        )
        tc = tuple(rgba[:4])
        val = MDLabel(
            text="0",
            font_style="Title",
            role="small",
            theme_font_size="Custom",
            font_size="20sp",
            bold=True,
            theme_text_color="Custom",
            text_color=tc,
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(30),
        )
        t = MDLabel(
            text=name_below,
            font_style="Body",
            role="small",
            theme_text_color="Custom",
            text_color=tc,
            halign="center",
            valign="middle",
            size_hint_y=None,
            height=dp(16),
        )
        col.add_widget(val)
        col.add_widget(t)
        return col, val

    def _sync_qty_field_padding(self, *_args: object) -> None:
        """Equal top/bottom padding so the value is vertically centered in the box."""
        ti = self._qty_field
        if ti is None or ti.height <= 1:
            return
        lh = float(ti.line_height)
        v = max(0.0, (float(ti.height) - lh) / 2.0)
        h = float(dp(6))
        ti.padding = [h, v, h, v]

    def _on_qty_text(self, _instance: TextInput, text: str) -> None:
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
            self._lbl_cal.text = f"{cal:.0f}"
        if self._lbl_p:
            self._lbl_p.text = f"{p:.1f}"
        if self._lbl_c:
            self._lbl_c.text = f"{c:.1f}"
        if self._lbl_f:
            self._lbl_f.text = f"{fd:.1f}"
        self._macro_chart.set_macros_g(p, c, fd)
        self._refresh_nutrition_facts(scaled)

    def _nf_divider(self) -> None:
        if self._facts_box is None:
            return
        self._facts_box.add_widget(_thin_hline())

    def _nf_row(
        self,
        label: str,
        value: str,
        rgba: tuple[float, float, float, float],
        indent: float = 0.0,
    ) -> None:
        if self._facts_box is None:
            return
        tc = tuple(rgba[:4])
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(30),
            padding=[dp(indent), dp(4), dp(4), dp(4)],
            spacing=dp(8),
        )
        row.add_widget(
            MDLabel(
                text=label,
                font_style="Body",
                role="small",
                theme_text_color="Custom",
                text_color=tc,
                halign="left",
                valign="middle",
                size_hint_x=0.62,
                shorten=True,
                shorten_from="right",
            )
        )
        row.add_widget(
            MDLabel(
                text=value,
                font_style="Body",
                role="small",
                theme_text_color="Custom",
                text_color=tc,
                halign="right",
                valign="middle",
                size_hint_x=0.38,
            )
        )
        self._facts_box.add_widget(row)

    @staticmethod
    def _fmt_g(x: float) -> str:
        return f"{x:.1f} g"

    def _refresh_nutrition_facts(self, n: NutritionInfo) -> None:
        """Rebuild detailed nutrition list for the current portion (scaled values)."""
        if self._facts_box is None:
            return
        self._facts_box.clear_widgets()
        teal = tuple(RGBA_PRIMARY[:4])
        fat_c = tuple(RGBA_FAT[:4])
        carb_c = tuple(RGBA_CARBS[:4])
        prot_c = tuple(RGBA_PROTEIN[:4])
        white = (1.0, 1.0, 1.0, 1.0)

        self._facts_box.add_widget(
            MDLabel(
                text="Nutrition facts",
                font_style="Title",
                role="small",
                theme_text_color="Custom",
                text_color=(0.7, 0.72, 0.76, 1),
                size_hint_y=None,
                height=dp(30),
                halign="left",
                valign="bottom",
            )
        )
        self._nf_divider()

        self._nf_row("Calories", f"{n.calories:.0f} kcal", teal)
        self._nf_divider()
        self._nf_row("Fat (g)", self._fmt_g(n.fat_g), fat_c)
        ind = dp(14)
        sat_val = 0.0 if n.fat_saturated_g is None else n.fat_saturated_g
        trans_val = 0.0 if n.fat_trans_g is None else n.fat_trans_g
        poly_val = 0.0 if n.fat_polyunsaturated_g is None else n.fat_polyunsaturated_g
        mono_val = 0.0 if n.fat_monounsaturated_g is None else n.fat_monounsaturated_g
        self._nf_row("Saturated", self._fmt_g(sat_val), white, indent=ind)
        self._nf_row("Trans", self._fmt_g(trans_val), white, indent=ind)
        self._nf_row("Polyunsaturated", self._fmt_g(poly_val), white, indent=ind)
        self._nf_row("Monounsaturated", self._fmt_g(mono_val), white, indent=ind)
        self._nf_divider()
        self._nf_row("Carbohydrate (g)", self._fmt_g(n.carbs_g), carb_c)
        fiber_val = 0.0 if n.fiber_g is None else n.fiber_g
        sugar_val = 0.0 if n.sugar_g is None else n.sugar_g
        self._nf_row("Dietary fiber", self._fmt_g(fiber_val), white, indent=ind)
        self._nf_row("Sugars", self._fmt_g(sugar_val), white, indent=ind)
        self._nf_divider()
        self._nf_row("Protein (g)", self._fmt_g(n.protein_g), prot_c)

    def _on_edit_pressed(self) -> None:
        if self._on_edit is None:
            return
        cb = self._on_edit
        self.dismiss()
        Clock.schedule_once(lambda _dt: cb(), 0.12)

    def _confirm_add(self) -> None:
        qty = self._parse_qty()
        self.dismiss()
        self._on_add(qty, self._canonical_name)
