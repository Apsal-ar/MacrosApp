"""Application-wide constants: activity multipliers, goal modifiers, diet presets."""

from __future__ import annotations

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# App color palette (hex and 0–1 RGBA)
# ---------------------------------------------------------------------------
COLOR_BG: str = "#121212"           # main background (black)
COLOR_SURFACE: str = "#18191A"      # cards, sections (dark grey)
COLOR_PRIMARY: str = "#009688"      # teal — headers, accents, values
COLOR_FAT: str = "#FFB93B"          # fat (quantities, pie, bars)
COLOR_CARBS: str = "#EC253F"        # carbs
COLOR_PROTEIN: str = "#155DFC"      # protein


def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> List[float]:
    """Convert #RRGGBB to [r, g, b, a] in 0–1 range."""
    hex_str = hex_str.lstrip("#")
    r = int(hex_str[0:2], 16) / 255.0
    g = int(hex_str[2:4], 16) / 255.0
    b = int(hex_str[4:6], 16) / 255.0
    return [r, g, b, alpha]


# Precomputed RGBA for Kivy
RGBA_BG: List[float] = hex_to_rgba(COLOR_BG)
RGBA_SURFACE: List[float] = hex_to_rgba(COLOR_SURFACE)
# Dialogs, modal prompts, and small popup cards (#212F3C — same as COLOR_SURFACE)
COLOR_POPUP: str = COLOR_SURFACE
RGBA_POPUP: List[float] = RGBA_SURFACE
RGBA_PRIMARY: List[float] = hex_to_rgba(COLOR_PRIMARY)
RGBA_FAT: List[float] = hex_to_rgba(COLOR_FAT)
RGBA_CARBS: List[float] = hex_to_rgba(COLOR_CARBS)
RGBA_PROTEIN: List[float] = hex_to_rgba(COLOR_PROTEIN)


def rgba_with_alpha(rgba: List[float], alpha: float) -> List[float]:
    """Same RGB as ``rgba`` (first three components), new alpha."""
    return [rgba[0], rgba[1], rgba[2], alpha]


# Progress bars: faint track, slightly stronger fill (same hue as macro / calorie colour)
PROGRESS_TRACK_ALPHA: float = 0.22
PROGRESS_INDICATOR_ALPHA: float = 0.58

# Calorie summary bar (protein colour) — precomputed for KV defaults so the bar is
# visible before Python assigns colours (e.g. tracker loads before user_id / totals).
RGBA_CALORIE_TRACK: List[float] = rgba_with_alpha(RGBA_PROTEIN, PROGRESS_TRACK_ALPHA)
RGBA_CALORIE_INDICATOR: List[float] = rgba_with_alpha(
    RGBA_PROTEIN, PROGRESS_INDICATOR_ALPHA
)

# Divider / rule lines (MDDivider, 1dp separators)
COLOR_LINE: str = "#94A09F"
RGBA_LINE: List[float] = hex_to_rgba(COLOR_LINE)

# ---------------------------------------------------------------------------
# Physical Activity Level multipliers
# ---------------------------------------------------------------------------
ACTIVITY_MULTIPLIERS: Dict[str, float] = {
    "low":         1.29,   # desk job / very little movement
    "moderate":    1.55,   # light exercise 1–3 days/week
    "high":        1.725,  # moderate exercise 3–5 days/week
    "very_high":   1.9,    # hard training 6–7 days/week
    "hyperactive": 2.1,    # intense daily training or physical job
}

ACTIVITY_LABELS: Dict[str, str] = {
    "low":         "Low",
    "moderate":    "Moderate",
    "high":        "High",
    "very_high":   "Very High",
    "hyperactive": "Hyperactive",
}

ACTIVITY_DESCRIPTIONS: Dict[str, str] = {
    "low":         "Desk job or very little movement",
    "moderate":    "Light exercise 1–3 days/week",
    "high":        "Moderate exercise 3–5 days/week",
    "very_high":   "Hard training 6–7 days/week",
    "hyperactive": "Intense daily training or physical job",
}

# ---------------------------------------------------------------------------
# Goal calorie modifiers (kcal/day delta from TDEE)
# ---------------------------------------------------------------------------
GOAL_MODIFIERS: Dict[str, float] = {
    "lose_fast":  -500.0,
    "lose_slow":  -250.0,
    "maintain":      0.0,
    "gain_slow":  +250.0,
    "gain_fast":  +500.0,
}

GOAL_LABELS: Dict[str, str] = {
    "lose_fast":  "Lose Weight",
    "lose_slow":  "Lose Weight Slowly",
    "maintain":   "Maintain Weight",
    "gain_slow":  "Increase Weight Slowly",
    "gain_fast":  "Increase Weight",
}

GOAL_DESCRIPTIONS: Dict[str, str] = {
    "lose_fast":  "−500 kcal/day · ~0.5 kg/week",
    "lose_slow":  "−250 kcal/day · ~0.25 kg/week",
    "maintain":   "Match energy expenditure",
    "gain_slow":  "+250 kcal/day · ~0.25 kg/week",
    "gain_fast":  "+500 kcal/day · ~0.5 kg/week",
}

# Migration map for data saved with old key names
ACTIVITY_KEY_MIGRATION: Dict[str, str] = {
    "sedentary":  "low",
    "light":      "low",
    "moderate":   "moderate",
    "active":     "high",
    "very_active": "very_high",
}

GOAL_KEY_MIGRATION: Dict[str, str] = {
    "lose":     "lose_fast",
    "maintain": "maintain",
    "gain":     "gain_slow",
}

# ---------------------------------------------------------------------------
# Diet type macro presets  (protein_pct, carbs_pct, fat_pct)
# ---------------------------------------------------------------------------
DIET_PRESETS: Dict[str, Dict[str, float]] = {
    "balanced":      {"protein_pct": 30.0, "carbs_pct": 40.0, "fat_pct": 30.0},
    "keto":          {"protein_pct": 25.0, "carbs_pct":  5.0, "fat_pct": 70.0},
    "low_carb":      {"protein_pct": 35.0, "carbs_pct": 25.0, "fat_pct": 40.0},
    "high_protein":  {"protein_pct": 40.0, "carbs_pct": 35.0, "fat_pct": 25.0},
    "mediterranean": {"protein_pct": 20.0, "carbs_pct": 50.0, "fat_pct": 30.0},
    "custom":        {"protein_pct": 30.0, "carbs_pct": 40.0, "fat_pct": 30.0},
}

DIET_PRESET_LABELS: Dict[str, str] = {
    "balanced":      "Balanced",
    "keto":          "Ketogenic",
    "low_carb":      "Low Carb",
    "high_protein":  "High Protein",
    "mediterranean": "Mediterranean",
    "custom":        "Custom",
}

# ---------------------------------------------------------------------------
# Default meal slot labels
# ---------------------------------------------------------------------------
DEFAULT_MEAL_LABELS: Dict[int, str] = {
    1: "Breakfast",
    2: "Lunch",
    3: "Dinner",
    4: "Tea",
    5: "Snacks",
    6: "Snack 1",
    7: "Snack 2",
    8: "Snack 3",
    9: "Snack 4",
    10: "Snack 5",
}

# ---------------------------------------------------------------------------
# BMI ranges (WHO classification)
# ---------------------------------------------------------------------------
# List of (range_display, label, min_bmi, max_bmi) — max_bmi is exclusive except last
BMI_RANGES: List[tuple] = [
    ("< 16", "Very severely underweight", 0, 16),
    ("16 - 16.99", "Severely underweight", 16, 17),
    ("17 - 18.49", "Underweight", 17, 18.5),
    ("18.5 - 24.99", "Normal (healthy weight)", 18.5, 25),
    ("25 - 29.99", "Overweight", 25, 30),
    ("30 - 34.99", "Obese Class I (Moderately obese)", 30, 35),
    ("35 - 39.99", "Obese Class II (Severely obese)", 35, 40),
    ("> 40", "Obese Class III (Very severely obese)", 40, 999),
]


def get_bmi_category(bmi: float) -> Optional[str]:
    """Return the classification label for a given BMI, or None if invalid."""
    if bmi <= 0:
        return None
    for _range_str, label, lo, hi in BMI_RANGES:
        if lo <= bmi < hi:
            return label
    return BMI_RANGES[-1][1]  # fallback: highest category


# ---------------------------------------------------------------------------
# Progress bar colour thresholds (% of target consumed)
# ---------------------------------------------------------------------------
PROGRESS_COLOUR_OK:     float = 85.0   # below this → green
PROGRESS_COLOUR_WARN:   float = 100.0  # 85–100 % → amber
# above 100 % → red

# ---------------------------------------------------------------------------
# Nutrition energy constants (kcal per gram)
# ---------------------------------------------------------------------------
KCAL_PER_G_PROTEIN: float = 4.0
KCAL_PER_G_CARBS:   float = 4.0
KCAL_PER_G_FAT:     float = 9.0
