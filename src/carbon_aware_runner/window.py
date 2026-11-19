"""Pure window logic: no network, no clock. Everything here is tested on fixed series.

A series is a list of (slot_start_utc, value) pairs with one fixed step between slots
(5 minutes for CO2EmisProg, 15 minutes or 1 hour for DayAheadPrices). A window is a run
of back-to-back slots that together last at least the job's duration.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

Series = list[tuple[datetime, float]]

_DURATION = re.compile(r"^(?:(\d+(?:\.\d+)?)h)?(?:(\d+)m)?$")


def parse_duration(text: str) -> timedelta:
    """'2h', '90m', '1h30m' or '1.5h' -> timedelta. Must be longer than zero."""
    match = _DURATION.match(text.strip().lower())
    if not match or not any(match.groups()):
        raise ValueError(f"{text!r} is not a duration like 2h, 90m or 1h30m")
    hours = float(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    result = timedelta(hours=hours, minutes=minutes)
    if result <= timedelta(0):
        raise ValueError(f"{text!r} must be longer than zero")
    return result


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime
    mean: float


def step_of(series: Series) -> timedelta:
    """The fixed step between slots (the smallest gap seen)."""
    if len(series) < 2:
        raise ValueError("need at least two slots to know the step")
    return min(b[0] - a[0] for a, b in zip(series, series[1:]))


def _slots_needed(duration: timedelta, step: timedelta) -> int:
    return math.ceil(duration / step)


def window_at(series: Series, start: datetime, duration: timedelta) -> Window:
    """The window that starts at the slot holding `start` (used for 'run now')."""
    step = step_of(series)
    n = _slots_needed(duration, step)
    for i, (t, _) in enumerate(series):
        if t <= start < t + step:
            block = series[i : i + n]
            if len(block) < n or not _back_to_back(block, step):
                raise ValueError("the data does not cover the job if it started now")
            return Window(block[0][0], block[-1][0] + step, sum(v for _, v in block) / n)
    raise ValueError("the data does not cover the current time")


def best_window(series: Series, earliest: datetime, deadline: datetime, duration: timedelta) -> Window:
    """Lowest-mean window that starts at or after the slot holding `earliest` and ends by `deadline`.

    Ties go to the earliest start, so a flat series runs now.
    """
    step = step_of(series)
    n = _slots_needed(duration, step)
    best: Window | None = None
    for i in range(len(series) - n + 1):
        block = series[i : i + n]
        start, end = block[0][0], block[-1][0] + step
        if start + step <= earliest or end > deadline or not _back_to_back(block, step):
            continue
        mean = sum(v for _, v in block) / n
        if best is None or mean < best.mean:
            best = Window(start, end, mean)
    if best is None:
        raise ValueError("no window of that duration fits between now and the deadline in the data")
    return best


def _back_to_back(block: Series, step: timedelta) -> bool:
    return all(b[0] - a[0] == step for a, b in zip(block, block[1:]))


def saving(now: Window, best: Window) -> tuple[float, float]:
    """(absolute saving per unit of energy, percent of 'now'). Positive means the best window is lower."""
    diff = now.mean - best.mean
    pct = 100 * diff / now.mean if now.mean else 0.0
    return diff, pct
