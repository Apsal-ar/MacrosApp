"""Metric ↔ imperial unit conversion utilities."""

from __future__ import annotations


class UnitConverter:
    """Static helpers for converting between metric and imperial units.

    All methods are pure functions — no side effects, fully testable.
    """

    # ------------------------------------------------------------------
    # Weight
    # ------------------------------------------------------------------

    @staticmethod
    def kg_to_lbs(kg: float) -> float:
        """Convert kilograms to pounds.

        Args:
            kg: Mass in kilograms.

        Returns:
            Mass in pounds, rounded to 1 decimal place.
        """
        return round(kg * 2.20462, 1)

    @staticmethod
    def lbs_to_kg(lbs: float) -> float:
        """Convert pounds to kilograms.

        Args:
            lbs: Mass in pounds.

        Returns:
            Mass in kilograms, rounded to 2 decimal places.
        """
        return round(lbs / 2.20462, 2)

    @staticmethod
    def g_to_oz(g: float) -> float:
        """Convert grams to ounces.

        Args:
            g: Mass in grams.

        Returns:
            Mass in ounces, rounded to 2 decimal places.
        """
        return round(g / 28.3495, 2)

    @staticmethod
    def oz_to_g(oz: float) -> float:
        """Convert ounces to grams.

        Args:
            oz: Mass in ounces.

        Returns:
            Mass in grams, rounded to 1 decimal place.
        """
        return round(oz * 28.3495, 1)

    # ------------------------------------------------------------------
    # Height
    # ------------------------------------------------------------------

    @staticmethod
    def cm_to_inches(cm: float) -> float:
        """Convert centimetres to inches.

        Args:
            cm: Length in centimetres.

        Returns:
            Length in inches, rounded to 1 decimal place.
        """
        return round(cm / 2.54, 1)

    @staticmethod
    def inches_to_cm(inches: float) -> float:
        """Convert inches to centimetres.

        Args:
            inches: Length in inches.

        Returns:
            Length in centimetres, rounded to 1 decimal place.
        """
        return round(inches * 2.54, 1)

    @staticmethod
    def cm_to_feet_inches(cm: float) -> tuple[int, float]:
        """Convert centimetres to a (feet, inches) tuple.

        Args:
            cm: Height in centimetres.

        Returns:
            Tuple of (whole_feet, remaining_inches) where remaining_inches
            is rounded to 1 decimal place.
        """
        total_inches = cm / 2.54
        feet = int(total_inches // 12)
        inches = round(total_inches % 12, 1)
        return feet, inches

    @staticmethod
    def feet_inches_to_cm(feet: int, inches: float) -> float:
        """Convert feet + inches to centimetres.

        Args:
            feet: Whole feet component.
            inches: Remaining inches component.

        Returns:
            Total height in centimetres, rounded to 1 decimal place.
        """
        return round(((feet * 12) + inches) * 2.54, 1)

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    @classmethod
    def format_weight(cls, kg: float, unit_system: str) -> str:
        """Format a weight value for display in the given unit system.

        Args:
            kg: Weight in kilograms (internal storage format).
            unit_system: 'metric' or 'imperial'.

        Returns:
            Formatted string, e.g. '75.0 kg' or '165.3 lbs'.
        """
        if unit_system == "imperial":
            return f"{cls.kg_to_lbs(kg):.1f} lbs"
        return f"{kg:.1f} kg"

    @classmethod
    def format_height(cls, cm: float, unit_system: str) -> str:
        """Format a height value for display in the given unit system.

        Args:
            cm: Height in centimetres (internal storage format).
            unit_system: 'metric' or 'imperial'.

        Returns:
            Formatted string, e.g. '175.0 cm' or '5\'9.1"'.
        """
        if unit_system == "imperial":
            feet, inches = cls.cm_to_feet_inches(cm)
            return f"{feet}'{inches}\""
        return f"{cm:.1f} cm"
