"""Application-wide constants: activity multipliers, goal modifiers, diet presets."""

from __future__ import annotations

from typing import Dict

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
    4: "Snack 1",
    5: "Snack 2",
    6: "Snack 3",
}

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
