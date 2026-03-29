"""Shared button styles matching Goals → Caloric requirement → Save.

All primary (filled) and secondary (outlined) actions use the same height,
corner radius, full width, and centered label text.
"""

from __future__ import annotations

from typing import Any

from kivy.lang import Builder
from kivymd.uix.button import MDButton

Builder.load_string("""
#:import dp kivy.metrics.dp
#:import UI_CORNER_RADIUS_DP utils.constants.UI_CORNER_RADIUS_DP

<MacrosFilledButton>:
    style: "filled"
    theme_width: "Custom"
    theme_height: "Custom"
    radius: [dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP)]
    size_hint_y: None
    height: "48dp"
    size_hint_x: 1

<MacrosOutlinedButton>:
    style: "outlined"
    theme_width: "Custom"
    theme_height: "Custom"
    radius: [dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP)]
    size_hint_y: None
    height: "48dp"
    size_hint_x: 1

<MacrosTextButton>:
    style: "text"
    theme_width: "Custom"
    theme_height: "Custom"
    radius: [dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP), dp(UI_CORNER_RADIUS_DP)]
    size_hint_y: None
    height: "48dp"
    size_hint_x: 1
""")


def _apply_macros_button_kwargs(kwargs: dict[str, Any]) -> None:
    """KivyMD defaults MDButton.theme_width to 'Primary', which sizes the button to
    its label and clears horizontal size_hint — that breaks programmatic full-width
    buttons. Always default to Custom unless the caller overrides."""
    kwargs.setdefault("theme_width", "Custom")
    kwargs.setdefault("theme_height", "Custom")


def _center_label_if_no_icon(button: MDButton) -> None:
    t = getattr(button, "_button_text", None)
    if t is None:
        return
    if getattr(button, "_button_icon", None) is not None:
        return
    t.x = (button.width - t.texture_size[0]) * 0.5


class MacrosFilledButton(MDButton):
    """Filled primary button — same look as Caloric requirement Save."""

    def __init__(self, **kwargs):
        _apply_macros_button_kwargs(kwargs)
        super().__init__(**kwargs)
        self.fbind("width", self._macros_recenter)

    def _macros_recenter(self, *args):
        self.adjust_pos()

    def adjust_pos(self, *args):
        super().adjust_pos(*args)
        _center_label_if_no_icon(self)


class MacrosOutlinedButton(MDButton):
    """Outlined secondary button — same geometry as MacrosFilledButton."""

    def __init__(self, **kwargs):
        _apply_macros_button_kwargs(kwargs)
        super().__init__(**kwargs)
        self.fbind("width", self._macros_recenter)

    def _macros_recenter(self, *args):
        self.adjust_pos()

    def adjust_pos(self, *args):
        super().adjust_pos(*args)
        _center_label_if_no_icon(self)


class MacrosTextButton(MDButton):
    """Text-style button — same height and corners as Save (e.g. tabs, secondary text)."""

    def __init__(self, **kwargs):
        _apply_macros_button_kwargs(kwargs)
        super().__init__(**kwargs)
        self.fbind("width", self._macros_recenter)

    def _macros_recenter(self, *args):
        self.adjust_pos()

    def adjust_pos(self, *args):
        super().adjust_pos(*args)
        _center_label_if_no_icon(self)
