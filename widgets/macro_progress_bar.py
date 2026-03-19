"""Horizontal macro progress bar widget.

Displays consumed vs target for one macro (protein, carbs, or fat).
Colour transitions: green → amber → red based on threshold constants.
"""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import NumericProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout

from utils.constants import (
    PROGRESS_COLOUR_OK,
    PROGRESS_COLOUR_WARN,
    RGBA_CARBS,
    RGBA_FAT,
    RGBA_PROTEIN,
)

Builder.load_string("""
<MacroProgressBar>:
    orientation: "vertical"
    size_hint_y: None
    height: "56dp"
    spacing: "4dp"
    padding: [0, 0, 0, 0]

    MDBoxLayout:
        size_hint_y: None
        height: "20dp"

        MDLabel:
            text: root.label
            font_style: "Body"
            role: "small"
            adaptive_width: True

        Widget:

        MDLabel:
            text: f"{root.consumed:.0f} / {root.target:.0f} g"
            font_style: "Body"
            role: "small"
            halign: "right"
            adaptive_width: True

    MDLinearProgressIndicator:
        id: progress_bar
        value: root._clipped_pct
        max: 100
        size_hint_y: None
        height: "8dp"
        indicator_color: root._bar_color
""")


class MacroProgressBar(MDBoxLayout):
    """Labelled progress bar for a single macro nutrient.

    Attributes:
        label: Display name shown on the left, e.g. 'Protein'.
        consumed: Amount consumed so far in grams.
        target: Daily target in grams.
    """

    label = StringProperty("Macro")
    consumed = NumericProperty(0.0)
    target = NumericProperty(100.0)

    @property
    def _pct(self) -> float:
        """Percentage of target consumed (may exceed 100)."""
        if self.target <= 0:
            return 0.0
        return (self.consumed / self.target) * 100.0

    @property
    def _clipped_pct(self) -> float:
        """Percentage clamped to 0–100 for the progress indicator widget."""
        return min(100.0, max(0.0, self._pct))

    @property
    def _bar_color(self) -> list:
        """Macro-specific bar colour (protein/carbs/fat from app palette)."""
        label_lower = (self.label or "").lower()
        if "protein" in label_lower:
            return RGBA_PROTEIN
        if "carb" in label_lower:
            return RGBA_CARBS
        if "fat" in label_lower:
            return RGBA_FAT
        return RGBA_PROTEIN  # fallback
