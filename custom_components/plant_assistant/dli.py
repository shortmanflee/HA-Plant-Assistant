"""
Daily Light Integral (DLI) calculation utilities for Plant Assistant.

This module provides functions to calculate, track, and aggregate Daily Light Integral
(DLI) values based on illuminance measurements. DLI represents the total amount of
photosynthetically active radiation (PAR) delivered in a 24-hour period, measured in
moles of photons per square meter per day (mol/m²/d).

Reference: https://en.wikipedia.org/wiki/Daily_light_integral

Conversion factors:
- Illuminance (lux) to PPFD (μmol/m²/s): multiply by 0.0185 (for standard daylight)
- PPFD integration over time gives total photon flux
- Daily integration: sum of PPFD values over 24 hours gives DLI
"""

from __future__ import annotations

import contextlib
import math
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

# Conversion constants
# See https://www.apogeeinstruments.com/conversion-ppfd-to-lux/
# This conversion factor is for typical daylight spectrum
LUX_TO_PPFD = 0.0185  # μmol/m²/s per lux

# PPFD to DLI conversion:
# DLI (mol/m²/d) = PPFD (μmol/m²/s) x seconds_per_day / 1,000,000 μmol/mol
# = PPFD x 86400 / 1,000,000
# = PPFD x 0.0864
PPFD_DAILY_FACTOR = 0.0864  # μmol/m²/s to mol/m²/d (over 24 hours)

# Illuminance-based DLI: lux to daily DLI over 24 hours at peak illuminance
# Peak illuminance to DLI during daylight hours (simplified):
# Assumes continuous operation at given illuminance for 24 hours
LUX_TO_DLI_24H = LUX_TO_PPFD * PPFD_DAILY_FACTOR  # 0.0015984


def lux_to_ppfd(lux_value: Any) -> float | None:
    """
    Convert illuminance (lux) to PPFD (Photosynthetic Photon Flux Density).

    This uses the standard conversion factor for typical daylight spectrum.

    Args:
        lux_value: Illuminance in lux (lx).

    Returns:
        PPFD in μmol/m²/s, or None if input is invalid.

    """
    # Be forgiving with input types: accept numeric strings like '1000 lx'
    if lux_value is None:
        return None

    fv = None
    try:
        # Try direct numeric conversion first
        fv = float(lux_value)
    except (TypeError, ValueError):
        # Fallback: extract the first numeric-like substring (handles '1000 lx')
        if isinstance(lux_value, str):
            m = re.search(r"[-+]?[0-9]*\.?[0-9]+", lux_value)
            if m:
                with contextlib.suppress(TypeError, ValueError):
                    fv = float(m.group(0))

    if fv is None or not math.isfinite(fv):
        return None
    if fv < 0:
        return 0.0

    return fv * LUX_TO_PPFD


def ppfd_to_dli_instantaneous(
    ppfd_value: Any, duration_hours: float = 24.0
) -> float | None:
    """
    Convert instantaneous PPFD to DLI assuming constant illumination.

    This is useful for calculating what the DLI would be if the given
    PPFD remained constant for the specified duration.

    Args:
        ppfd_value: PPFD in μmol/m²/s.
        duration_hours: Duration in hours (default 24 for daily calculation).

    Returns:
        Estimated DLI in mol/m²/d, or None if input is invalid.

    """
    if ppfd_value is None:
        return None

    try:
        fv = float(ppfd_value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(fv):
        return None
    if fv < 0:
        return 0.0

    # Convert hours to seconds
    duration_seconds = duration_hours * 3600

    # DLI = PPFD (μmol/m²/s) x seconds / 1,000,000 μmol/mol
    return (fv * duration_seconds) / 1_000_000


def lux_to_dli(lux_value: Any) -> float | None:
    """
    Convert peak illuminance (lux) to estimated daily DLI.

    This assumes the given illuminance is maintained constant for 24 hours,
    which is useful for estimating DLI from peak light measurements.

    Args:
        lux_value: Illuminance in lux (lx).

    Returns:
        Estimated DLI in mol/m²/d assuming constant illumination over 24 hours,
        or None if input is invalid.

    """
    # Reuse lux_to_ppfd which now accepts numeric strings
    ppfd = lux_to_ppfd(lux_value)
    if ppfd is None:
        return None
    return ppfd_to_dli_instantaneous(ppfd, duration_hours=24.0)


def _collect_numeric(values: Iterable[Any]) -> list[float]:
    """Collect numeric values from an iterable, filtering out invalid values."""
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            fv = float(v)
            # Ignore NaN and infinities
            if not math.isfinite(fv):
                continue
            if fv < 0:
                continue  # DLI cannot be negative
            out.append(fv)
        except (TypeError, ValueError):
            continue
    return out


def max_of_mins_dli(
    plants: Iterable[dict[str, Any]], min_key: str = "minimum_light"
) -> float | None:
    """
    Get the maximum of minimum DLI requirements across plants.

    Converts illuminance (lux) values to DLI before aggregation.
    This represents the most restrictive minimum light requirement.

    Args:
        plants: Iterable of plant attribute dictionaries.
        min_key: Key for minimum light values (e.g., 'minimum_light' in lux).

    Returns:
        The maximum minimum DLI in mol/m²/d, or None if no valid values found.

    """
    # Extract minimum light values and convert to DLI
    dli_values = []
    for plant in plants:
        min_light = plant.get(min_key)
        if min_light is not None:
            try:
                min_light_float = float(min_light)
                if min_light_float >= 0 and math.isfinite(min_light_float):
                    dli = lux_to_dli(min_light_float)
                    if dli is not None and dli >= 0:
                        dli_values.append(dli)
            except (TypeError, ValueError):
                continue

    return max(dli_values) if dli_values else None


def min_of_maxs_dli(
    plants: Iterable[dict[str, Any]], max_key: str = "maximum_light"
) -> float | None:
    """
    Get the minimum of maximum DLI tolerances across plants.

    Converts illuminance (lux) values to DLI before aggregation.
    This represents the most restrictive maximum light tolerance.

    Args:
        plants: Iterable of plant attribute dictionaries.
        max_key: Key for maximum light values (e.g., 'maximum_light' in lux).

    Returns:
        The minimum maximum DLI in mol/m²/d, or None if no valid values found.

    """
    # Extract maximum light values and convert to DLI
    dli_values = []
    for plant in plants:
        max_light = plant.get(max_key)
        if max_light is not None:
            try:
                max_light_float = float(max_light)
                if max_light_float >= 0 and math.isfinite(max_light_float):
                    dli = lux_to_dli(max_light_float)
                    if dli is not None and dli >= 0:
                        dli_values.append(dli)
            except (TypeError, ValueError):
                continue

    return min(dli_values) if dli_values else None


class DLIAccumulator:
    """
    Tracks accumulated Daily Light Integral over time.

    This class maintains a running total of DLI by integrating PPFD values
    over time. It resets daily at midnight.
    """

    def __init__(self) -> None:
        """Initialize the DLI accumulator."""
        self._accumulated_dli = 0.0
        self._last_update = None
        self._current_day = None

    def reset(self) -> None:
        """Reset the accumulator for a new day."""
        self._accumulated_dli = 0.0
        self._last_update = None
        self._current_day = datetime.now(UTC).date()

    def should_reset(self) -> bool:
        """Check if the accumulator should reset (new day)."""
        today = datetime.now(UTC).date()
        return self._current_day is None or self._current_day != today

    def update(self, ppfd: float, timestamp: datetime | None = None) -> float:
        """
        Update the accumulator with a new PPFD reading.

        Args:
            ppfd: Current PPFD value in μmol/m²/s.
            timestamp: Timestamp of the reading (defaults to now).

        Returns:
            Current accumulated DLI value in mol/m²/d.

        """
        if timestamp is None:
            timestamp = datetime.now(UTC)

        # Reset if day has changed
        if self.should_reset():
            self.reset()

        # On first update of the day, just initialize
        if self._last_update is None:
            self._last_update = timestamp
            return self._accumulated_dli

        # Calculate time delta
        time_delta = timestamp - self._last_update
        if time_delta.total_seconds() < 0:
            # Time went backwards, just update timestamp
            self._last_update = timestamp
            return self._accumulated_dli

        # Calculate DLI contribution from this interval
        # DLI contribution = PPFD (μmol/m²/s) x seconds / 1,000,000 μmol/mol
        if ppfd > 0:
            dli_contribution = (ppfd * time_delta.total_seconds()) / 1_000_000
            self._accumulated_dli += dli_contribution

        # Update last update time
        self._last_update = timestamp

        return self._accumulated_dli

    @property
    def dli(self) -> float:
        """Get current accumulated DLI value."""
        return self._accumulated_dli

    @property
    def last_update(self) -> datetime | None:
        """Get timestamp of last update."""
        return self._last_update

    def set_dli(self, dli: float) -> None:
        """
        Directly set the accumulated DLI value (for testing/restoration).

        Args:
            dli: The DLI value to set in mol/m²/d.

        """
        self._accumulated_dli = max(0.0, float(dli))
