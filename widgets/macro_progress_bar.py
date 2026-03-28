"""Macro progress bar: label, consumed/target text, and bar in the macro palette colour."""

from __future__ import annotations

from kivy.lang import Builder
from kivy.properties import ListProperty, NumericProperty, StringProperty
from kivymd.uix.boxlayout import MDBoxLayout

from utils.constants import (
    PROGRESS_INDICATOR_ALPHA,
    PROGRESS_TRACK_ALPHA,
    RGBA_CARBS,
    RGBA_FAT,
    RGBA_PROTEIN,
    rgba_with_alpha,
)

Builder.load_string("""
#:import dp kivy.metrics.dp

<MacroProgressBar>:
    orientation: "vertical"
    size_hint_y: None
    height: "64dp"
    spacing: "6dp"
    padding: [0, 0, 0, 0]

    # Column: centered name → bar → centered grams
    MDLabel:
        text: root.label
        font_style: "Body"
        role: "small"
        halign: "center"
        valign: "middle"
        text_size: self.size
        size_hint_y: None
        height: "22dp"
        theme_text_color: "Custom"
        text_color: root.macro_rgba

    MDLinearProgressIndicator:
        id: progress_bar
        size_hint_x: 1
        value: root.clipped_pct
        max: 100
        size_hint_y: None
        height: "8dp"
        track_color: root.macro_track_rgba
        radius: [dp(4), dp(4), dp(4), dp(4)]
        indicator_color: root.macro_indicator_rgba

    MDLabel:
        text: f"{root.consumed:.0f} / {root.target:.0f} g"
        font_style: "Body"
        role: "small"
        halign: "center"
        valign: "middle"
        text_size: self.size
        size_hint_y: None
        height: "22dp"
        theme_text_color: "Custom"
        text_color: root.macro_rgba
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
    # 0–100 for MDLinearProgressIndicator; must be a Property so KV updates when totals change.
    clipped_pct = NumericProperty(0.0)
    # Observable RGBA so KV text_color / indicator_color update when label is set from rules.
    macro_rgba = ListProperty(list(RGBA_PROTEIN))
    macro_track_rgba = ListProperty(
        rgba_with_alpha(RGBA_PROTEIN, PROGRESS_TRACK_ALPHA)
    )
    macro_indicator_rgba = ListProperty(
        rgba_with_alpha(RGBA_PROTEIN, PROGRESS_INDICATOR_ALPHA)
    )

    def on_label(self, *args: object) -> None:
        # `self.label` is already updated when this runs; arity varies by Kivy version.
        self.macro_rgba = self._rgba_for_label(self.label)

    def on_macro_rgba(self, *args: object) -> None:
        self.macro_track_rgba = rgba_with_alpha(self.macro_rgba, PROGRESS_TRACK_ALPHA)
        self.macro_indicator_rgba = rgba_with_alpha(
            self.macro_rgba, PROGRESS_INDICATOR_ALPHA
        )

    def on_kv_post(self, base_widget: object) -> None:
        self.macro_rgba = self._rgba_for_label(self.label)
        self._sync_clipped_pct()

    def on_consumed(self, *args: object) -> None:
        self._sync_clipped_pct()

    def on_target(self, *args: object) -> None:
        self._sync_clipped_pct()

    def _sync_clipped_pct(self, *args: object) -> None:
        t = self.target
        if t <= 0:
            self.clipped_pct = 0.0
        else:
            self.clipped_pct = min(100.0, max(0.0, (self.consumed / t) * 100.0))

    @staticmethod
    def _rgba_for_label(text: str) -> list[float]:
        label_lower = (text or "").lower()
        if "protein" in label_lower:
            return RGBA_PROTEIN
        if "carb" in label_lower:
            return RGBA_CARBS
        if "fat" in label_lower:
            return RGBA_FAT
        return RGBA_PROTEIN
