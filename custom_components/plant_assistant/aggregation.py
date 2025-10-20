"""
Aggregation utilities for Plant Assistant.

Pure functions that compute aggregated metrics (min, max, avg) across a list
of plant attribute dictionaries. These functions are intentionally simple and
unit-testable.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable


def _collect_numeric(values: Iterable[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            fv = float(v)
            # ignore NaN and infinities
            if not math.isfinite(fv):
                continue
            out.append(fv)
        except (TypeError, ValueError):
            continue
    return out


def min_metric(plants: Iterable[dict[str, Any]], key: str) -> float | None:
    """Get the minimum value of a metric across plants."""
    vals = _collect_numeric(p.get(key) for p in plants)
    return min(vals) if vals else None


def max_metric(plants: Iterable[dict[str, Any]], key: str) -> float | None:
    """Get the maximum value of a metric across plants."""
    vals = _collect_numeric(p.get(key) for p in plants)
    return max(vals) if vals else None


def avg_metric(plants: Iterable[dict[str, Any]], key: str) -> float | None:
    """Get the average value of a metric across plants."""
    vals = _collect_numeric(p.get(key) for p in plants)
    return sum(vals) / len(vals) if vals else None


def max_of_mins(plants: Iterable[dict[str, Any]], min_key: str) -> float | None:
    """
    Get the maximum of the minimum values across plants.

    This is useful for location sensors where you want the most restrictive
    minimum value (e.g., the highest minimum light requirement).

    Args:
        plants: Iterable of plant attribute dictionaries.
        min_key: Key for minimum values (e.g., 'minimum_light').

    Returns:
        The maximum of all minimum values, or None if no valid values found.

    """
    mins = _collect_numeric(p.get(min_key) for p in plants)
    return max(mins) if mins else None


def min_of_maxs(plants: Iterable[dict[str, Any]], max_key: str) -> float | None:
    """
    Get the minimum of the maximum values across plants.

    This is useful for location sensors where you want the most restrictive
    maximum value (e.g., the lowest maximum light tolerance).

    Args:
        plants: Iterable of plant attribute dictionaries.
        max_key: Key for maximum values (e.g., 'maximum_light').

    Returns:
        The minimum of all maximum values, or None if no valid values found.

    """
    maxs = _collect_numeric(p.get(max_key) for p in plants)
    return min(maxs) if maxs else None
