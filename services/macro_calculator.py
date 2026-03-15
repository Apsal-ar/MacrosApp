"""TDEE calculation and macro gram target computation.

All methods are pure static functions — no state, fully testable in isolation.
Calorie energy constants:
  Protein  → 4 kcal/g
  Carbs    → 4 kcal/g
  Fat      → 9 kcal/g
"""

from __future__ import annotations

from typing import Dict

from utils.constants import ACTIVITY_MULTIPLIERS, GOAL_MODIFIERS


class MacroCalculator:
    """TDEE and macro calculation service.

    All methods are static and stateless; instantiate only when dependency
    injection is needed (e.g. mocking in tests).
    """

    # ------------------------------------------------------------------
    # BMR
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
        """Calculate Basal Metabolic Rate using the Mifflin-St Jeor equation.

        Mifflin-St Jeor (1990) is the most validated equation for modern populations.
        Male:   BMR = (10 × weight_kg) + (6.25 × height_cm) − (5 × age) + 5
        Female: BMR = (10 × weight_kg) + (6.25 × height_cm) − (5 × age) − 161

        Args:
            weight_kg: Body weight in kilograms.
            height_cm: Height in centimetres.
            age: Age in whole years.
            sex: 'male', 'female', or 'other'. 'other' averages male/female.

        Returns:
            BMR in kcal/day as a float.
        """
        base = (10.0 * weight_kg) + (6.25 * height_cm) - (5.0 * age)
        if sex == "male":
            return base + 5.0
        if sex == "female":
            return base - 161.0
        return base - 78.0  # midpoint average for 'other'

    # ------------------------------------------------------------------
    # TDEE
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_tdee(bmr: float, activity_level: str) -> float:
        """Multiply BMR by the Physical Activity Level (PAL) multiplier.

        Args:
            bmr: Basal Metabolic Rate in kcal/day.
            activity_level: One of 'sedentary', 'light', 'moderate', 'active',
                'very_active'. Unknown values fall back to 'sedentary'.

        Returns:
            TDEE in kcal/day as a float.
        """
        multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, ACTIVITY_MULTIPLIERS["sedentary"])
        return round(bmr * multiplier, 1)

    # ------------------------------------------------------------------
    # Goal modifier
    # ------------------------------------------------------------------

    @staticmethod
    def apply_goal_modifier(tdee: float, goal: str) -> float:
        """Adjust TDEE by a fixed calorie offset based on the user's goal.

        Args:
            tdee: Total Daily Energy Expenditure in kcal/day.
            goal: One of 'lose' (−500 kcal), 'maintain' (±0), 'gain' (+300 kcal).
                Unknown values default to 'maintain'.

        Returns:
            Target calorie intake per day as a float.
        """
        modifier = GOAL_MODIFIERS.get(goal, GOAL_MODIFIERS["maintain"])
        return max(1200.0, round(tdee + modifier, 1))  # floor at 1200 kcal for safety

    # ------------------------------------------------------------------
    # Macro gram targets
    # ------------------------------------------------------------------

    @staticmethod
    def calculate_macro_grams(
        calories: float,
        protein_pct: float,
        carbs_pct: float,
        fat_pct: float,
    ) -> Dict[str, float]:
        """Convert a calorie target and macro percentages into gram targets.

        Args:
            calories: Daily calorie target in kcal.
            protein_pct: Percentage of calories from protein (0–100).
            carbs_pct: Percentage of calories from carbohydrates (0–100).
            fat_pct: Percentage of calories from fat (0–100).

        Returns:
            Dict with keys 'protein_g', 'carbs_g', 'fat_g' as floats.
        """
        return {
            "protein_g": round((calories * protein_pct / 100.0) / 4.0, 1),
            "carbs_g": round((calories * carbs_pct / 100.0) / 4.0, 1),
            "fat_g": round((calories * fat_pct / 100.0) / 9.0, 1),
        }

    # ------------------------------------------------------------------
    # Convenience: full pipeline
    # ------------------------------------------------------------------

    @classmethod
    def calculate_targets(
        cls,
        weight_kg: float,
        height_cm: float,
        age: int,
        sex: str,
        activity_level: str,
        goal: str,
        protein_pct: float,
        carbs_pct: float,
        fat_pct: float,
    ) -> Dict[str, float]:
        """Run the complete pipeline: BMR → TDEE → goal-adjusted calories → grams.

        Args:
            weight_kg: Body weight in kilograms.
            height_cm: Height in centimetres.
            age: Age in whole years.
            sex: 'male', 'female', or 'other'.
            activity_level: PAL category string.
            goal: 'lose', 'maintain', or 'gain'.
            protein_pct: Protein share of calories (0–100).
            carbs_pct: Carbohydrate share of calories (0–100).
            fat_pct: Fat share of calories (0–100).

        Returns:
            Dict with keys 'calories', 'protein_g', 'carbs_g', 'fat_g'.
        """
        bmr = cls.calculate_bmr(weight_kg, height_cm, age, sex)
        tdee = cls.calculate_tdee(bmr, activity_level)
        calories = cls.apply_goal_modifier(tdee, goal)
        grams = cls.calculate_macro_grams(calories, protein_pct, carbs_pct, fat_pct)
        return {"calories": calories, **grams}

    # ------------------------------------------------------------------
    # Progress utilities
    # ------------------------------------------------------------------

    @staticmethod
    def progress_pct(consumed: float, target: float) -> float:
        """Calculate percentage of a macro target consumed.

        Args:
            consumed: Amount consumed so far.
            target: Daily target amount.

        Returns:
            Percentage as a float; clamped to a minimum of 0. May exceed 100.
        """
        if target <= 0:
            return 0.0
        return round(max(0.0, (consumed / target) * 100.0), 1)
