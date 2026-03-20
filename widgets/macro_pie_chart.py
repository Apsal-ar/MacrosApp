"""Kivy Canvas pie chart widget for macro ratio visualisation.

Draws three arcs (protein/carbs/fat) directly on the Kivy Canvas to avoid
a matplotlib dependency. Colours and proportions update reactively when the
bound properties change.
"""

from __future__ import annotations

import math
from typing import List

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse
from kivy.lang import Builder
from kivy.properties import NumericProperty
from kivymd.uix.boxlayout import MDBoxLayout

from utils.constants import RGBA_BG, RGBA_CARBS, RGBA_FAT, RGBA_PROTEIN

Builder.load_string("""
<MacroPieChart>:
    orientation: "vertical"
    size_hint_y: None
    height: "240dp"
    padding: ["8dp", "8dp", "8dp", "4dp"]
    spacing: "8dp"

    FloatLayout:
        id: canvas_area
        size_hint_y: 1
        Widget:
            id: pie_canvas
            size_hint: 1, 1

        MDLabel:
            id: pct_protein
            text: ""
            size_hint: None, None
            size: 48, 24
            bold: True
            halign: "center"
            valign: "middle"
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
            font_style: "Title"
            role: "small"

        MDLabel:
            id: pct_carbs
            text: ""
            size_hint: None, None
            size: 48, 24
            bold: True
            halign: "center"
            valign: "middle"
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
            font_style: "Title"
            role: "small"

        MDLabel:
            id: pct_fat
            text: ""
            size_hint: None, None
            size: 48, 24
            bold: True
            halign: "center"
            valign: "middle"
            theme_text_color: "Custom"
            text_color: 1, 1, 1, 1
            font_style: "Title"
            role: "small"

    MDBoxLayout:
        size_hint_y: None
        height: "34dp"
        spacing: "16dp"
        pos_hint: {"center_x": 0.5}
        adaptive_width: True

        MDLabel:
            id: legend_protein
            text: ""
            font_style: "Title"
            role: "small"
            adaptive_width: True
            theme_text_color: "Custom"

        MDLabel:
            id: legend_carbs
            text: ""
            font_style: "Title"
            role: "small"
            adaptive_width: True
            theme_text_color: "Custom"

        MDLabel:
            id: legend_fat
            text: ""
            font_style: "Title"
            role: "small"
            adaptive_width: True
            theme_text_color: "Custom"
""")

# Segment colours: protein, carbs, fat (from app palette)
_COLOURS: List[tuple] = [
    tuple(RGBA_PROTEIN),   # protein #155DFC
    tuple(RGBA_CARBS),     # carbs #EC253F
    tuple(RGBA_FAT),       # fat #FFB93B
]
_LABELS = ["Protein", "Carbs", "Fat"]


class MacroPieChart(MDBoxLayout):
    """Real-time pie chart showing macro percentage splits.

    Bind protein_pct, carbs_pct, fat_pct and the chart redraws automatically.

    Attributes:
        protein_pct: Percentage of calories from protein (0–100).
        carbs_pct: Percentage of calories from carbohydrates (0–100).
        fat_pct: Percentage of calories from fat (0–100).
    """

    protein_pct = NumericProperty(30.0)
    carbs_pct = NumericProperty(40.0)
    fat_pct = NumericProperty(30.0)

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.bind(
            protein_pct=self._redraw,
            carbs_pct=self._redraw,
            fat_pct=self._redraw,
            size=self._redraw,
            pos=self._redraw,
        )

    def on_kv_post(self, base_widget: object) -> None:
        """Called after KV rules are applied; trigger initial draw."""
        super().on_kv_post(base_widget)
        canvas_widget = self.ids.get("canvas_area")
        if canvas_widget is not None:
            canvas_widget.bind(size=self._redraw, pos=self._redraw)
        # Schedule after first layout pass so canvas_area has real size.
        Clock.schedule_once(lambda dt: self._redraw(), 0)

    def _redraw(self, *args: object) -> None:  # noqa: ARG002
        """Clear and redraw the pie chart and legend on the Canvas.

        Args:
            *args: Kivy property-change args (ignored).
        """
        canvas_widget = self.ids.get("pie_canvas")
        chart_area = self.ids.get("canvas_area")
        if canvas_widget is None or chart_area is None:
            return

        canvas_widget.canvas.clear()
        percentages = [self.protein_pct, self.carbs_pct, self.fat_pct]
        total = sum(percentages)
        if total <= 0:
            return

        cx = chart_area.center_x
        cy = chart_area.center_y
        radius = min(chart_area.width, chart_area.height) / 2.0 * 0.85
        if radius <= 0:
            self._update_legend(percentages, total)
            return
        diameter = radius * 2

        # Kivy Ellipse uses (x, y) = (r*sin(θ), r*cos(θ)) in normalized coords, so
        # θ = 0° is 12 o'clock (top), 90° is 3 o'clock — NOT the usual math convention.
        start_angle = 0.0
        pct_norm = [round((pct / total) * 100) if total > 0 else 0 for pct in percentages]
        mid_angles: List[float] = []

        with canvas_widget.canvas:
            for i, pct in enumerate(percentages):
                if pct <= 0:
                    mid_angles.append(start_angle)
                    continue
                sweep = (pct / total) * 360.0
                end_angle = start_angle + sweep
                r, g, b, a = _COLOURS[i]
                Color(r, g, b, a)
                Ellipse(
                    pos=(cx - radius, cy - radius),
                    size=(diameter, diameter),
                    angle_start=start_angle,
                    angle_end=end_angle,
                )
                # Bisector of this sector in Kivy angle space (0° = top).
                mid_angles.append(start_angle + (sweep / 2.0))
                start_angle = end_angle

            # Match app background in donut center.
            bg_r, bg_g, bg_b, bg_a = RGBA_BG
            Color(bg_r, bg_g, bg_b, bg_a)
            inner_r = radius * 0.33
            Ellipse(
                pos=(cx - inner_r, cy - inner_r),
                size=(inner_r * 2, inner_r * 2),
            )

        self._position_pct_labels(cx, cy, radius, mid_angles, pct_norm)
        self._update_legend(percentages, total)

    def _update_legend(self, percentages: List[float], total: float) -> None:
        """Update the colour-coded legend labels below the chart.

        Args:
            percentages: [protein_pct, carbs_pct, fat_pct] values.
            total: Sum of all percentages (used for normalisation).
        """
        legend_ids = ["legend_protein", "legend_carbs", "legend_fat"]
        colours = [_COLOURS[0], _COLOURS[1], _COLOURS[2]]
        for i, label_id in enumerate(legend_ids):
            label_widget = self.ids.get(label_id)
            if label_widget:
                pct_norm = round((percentages[i] / total) * 100) if total > 0 else 0
                label_widget.text = f"{_LABELS[i]} {pct_norm}%"
                label_widget.text_color = colours[i]

    def _position_pct_labels(
        self,
        cx: float,
        cy: float,
        radius: float,
        mid_angles: List[float],
        percentages: List[int],
    ) -> None:
        """Place white percentage labels on top of donut segments."""
        label_ids = ["pct_protein", "pct_carbs", "pct_fat"]
        inner_r = radius * 0.33
        label_radius = (radius + inner_r) / 2.0

        # Fixed label dimensions — avoids texture_size timing issues
        label_w = 48
        label_h = 24

        for i, label_id in enumerate(label_ids):
            lbl = self.ids.get(label_id)
            if lbl is None:
                continue
            pct = percentages[i] if i < len(percentages) else 0
            lbl.text = f"{pct}%"
            lbl.size = (label_w, label_h)

            # Match Kivy Ellipse: 0° = top, x = r*sin(θ), y = r*cos(θ)
            angle_deg = mid_angles[i] if i < len(mid_angles) else 0.0
            angle_rad = math.radians(angle_deg)
            x = cx + label_radius * math.sin(angle_rad)
            y = cy + label_radius * math.cos(angle_rad)
            lbl.pos = (x - label_w / 2.0, y - label_h / 2.0)
