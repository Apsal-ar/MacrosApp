"""Smooth gradient track (red → yellow → teal → yellow → red) behind the calorie slider."""

from __future__ import annotations

from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.lang import Builder
from kivy.uix.widget import Widget

Builder.load_string(
    """
<CalorieSliderTrack>:
    size_hint_y: None
    height: dp(8)
"""
)

# Stops match the previous five-segment design; transitions are smooth lerps between them.
_C_RED = (0.94, 0.27, 0.27)
_C_YELLOW = (0.96, 0.82, 0.18)
_C_TEAL = (0.0, 0.59, 0.53)


def _lerp3(
    a: tuple[float, float, float], b: tuple[float, float, float], t: float
) -> tuple[float, float, float]:
    t = max(0.0, min(1.0, t))
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _rgb_at_u(u: float) -> tuple[float, float, float]:
    """Map u in [0, 1] to a smooth multi-stop gradient."""
    u = max(0.0, min(1.0, u))
    if u <= 0.25:
        t = u / 0.25
        return _lerp3(_C_RED, _C_YELLOW, t)
    if u <= 0.5:
        t = (u - 0.25) / 0.25
        return _lerp3(_C_YELLOW, _C_TEAL, t)
    if u <= 0.75:
        t = (u - 0.5) / 0.25
        return _lerp3(_C_TEAL, _C_YELLOW, t)
    t = (u - 0.75) / 0.25
    return _lerp3(_C_YELLOW, _C_RED, t)


def _build_gradient_texture(width: int, height: int) -> Texture:
    w = max(2, int(width))
    h = max(2, int(height))
    buf = bytearray(w * h * 4)
    for y in range(h):
        row = y * w * 4
        for x in range(w):
            r, g, b = _rgb_at_u((x + 0.5) / w)
            i = row + x * 4
            buf[i] = int(r * 255)
            buf[i + 1] = int(g * 255)
            buf[i + 2] = int(b * 255)
            buf[i + 3] = 255
    tex = Texture.create(size=(w, h), colorfmt="rgba")
    tex.mag_filter = "linear"
    tex.min_filter = "linear"
    tex.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
    return tex


class CalorieSliderTrack(Widget):
    """Horizontal gradient strip; does not handle touches (siblings receive them)."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._tex_w = 0
        self._tex_h = 0
        with self.canvas.before:
            Color(1, 1, 1, 1)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._refresh_texture, size=self._refresh_texture)

    def _refresh_texture(self, *_args: object) -> None:
        if self.width < 2 or self.height < 2:
            return
        w = int(self.width)
        h = int(self.height)
        if w != self._tex_w or h != self._tex_h:
            self._tex_w = w
            self._tex_h = h
            self._rect.texture = _build_gradient_texture(w, h)
        self._rect.pos = self.pos
        self._rect.size = self.size

    def on_touch_down(self, touch: object) -> bool:
        if self.collide_point(*touch.pos):
            return False
        return super().on_touch_down(touch)

    def on_touch_move(self, touch: object) -> bool:
        if self.collide_point(*touch.pos):
            return False
        return super().on_touch_move(touch)

    def on_touch_up(self, touch: object) -> bool:
        if self.collide_point(*touch.pos):
            return False
        return super().on_touch_up(touch)
