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
