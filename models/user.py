"""Dataclasses for user profile and macro goals."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Profile:
    """Represents a user's physical profile used for TDEE calculation.

    Attributes:
        id: UUID v4 string — matches Supabase auth.users.id.
        email: User's email address, sourced from Supabase Auth.
        height_cm: Height in centimetres (stored normalised; display depends on unit_system).
        weight_kg: Body weight in kilograms.
        age: Age in whole years.
        sex: Biological sex used by Mifflin-St Jeor equation.
        activity: PAL category used to derive TDEE multiplier.
        goal: Calorie adjustment intent.
        unit_system: Controls display units across all screens.
        updated_at: Unix timestamp (float) for conflict resolution.
    """

    id: str
    email: str = ""
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    age: Optional[int] = None
    sex: Optional[str] = None          # 'male' | 'female' | 'other'
    activity: Optional[str] = None     # 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active'
    goal: Optional[str] = None         # 'lose' | 'maintain' | 'gain'
    unit_system: str = "metric"        # 'metric' | 'imperial'
    updated_at: float = 0.0


@dataclass
class Goals:
    """Stores the user's macro targets and meal structure.

    Attributes:
        id: UUID v4.
        profile_id: Foreign key to Profile.id.
        protein_pct: Percentage of total calories from protein (0–100).
        carbs_pct: Percentage of total calories from carbohydrates (0–100).
        fat_pct: Percentage of total calories from fat (0–100).
        diet_type: Named preset or 'custom' for freeform adjustment.
        meals_per_day: How many meal slots to render on the Tracker screen.
        calorie_target: Calculated TDEE ± goal modifier; stored for offline use.
        updated_at: Unix timestamp.
    """

    id: str
    profile_id: str
    protein_pct: float = 30.0
    carbs_pct: float = 40.0
    fat_pct: float = 30.0
    diet_type: str = "balanced"
    meals_per_day: int = 3
    calorie_target: Optional[float] = None
    updated_at: float = 0.0

    def validate_percentages(self) -> bool:
        """Return True when macro percentages sum to exactly 100."""
        return abs(self.protein_pct + self.carbs_pct + self.fat_pct - 100.0) < 0.01
