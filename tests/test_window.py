"""Window logic on a fixed hourly series. Every expected window below was worked out by hand.

Series (UTC, 2026-01-01), g CO2/kWh:
    hour   00   01   02   03   04   05   06   07
    value 100   80   60   90   40   50  120   30

Two-hour block means, by start hour:
    00: 90   01: 70   02: 75   03: 65   04: 45   05: 85   06: 75
"""

from datetime import datetime, timedelta, timezone

import pytest

from carbon_aware_runner.window import Window, best_window, parse_duration, saving, step_of, window_at

H = timedelta(hours=1)
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
VALUES = [100, 80, 60, 90, 40, 50, 120, 30]
SERIES = [(T0 + i * H, float(v)) for i, v in enumerate(VALUES)]


def at(hour: float) -> datetime:
    return T0 + timedelta(hours=hour)


def test_best_two_hours_whole_day():
    assert best_window(SERIES, at(0), at(8), 2 * H) == Window(at(4), at(6), 45.0)


def test_deadline_cuts_off_the_best_block():
    # must end by 05:00, so blocks start 00..03; best is 03 (90+40)/2 = 65
    assert best_window(SERIES, at(0), at(5), 2 * H) == Window(at(3), at(5), 65.0)


def test_one_hour_picks_single_lowest_hour():
    assert best_window(SERIES, at(0), at(8), H) == Window(at(7), at(8), 30.0)


def test_slot_holding_now_counts_as_now():
    # now = 00:30: the 00:00 slot holds 'now', so it may still be picked
    assert best_window(SERIES, at(0.5), at(2), H) == Window(at(1), at(2), 80.0)
    assert best_window(SERIES, at(0.5), at(1), H) == Window(at(0), at(1), 100.0)


def test_slots_already_over_are_skipped():
    # now = 05:10: blocks may start at 05 (85) or 06 (75)
    assert best_window(SERIES, at(5 + 10 / 60), at(8), 2 * H) == Window(at(6), at(8), 75.0)


def test_duration_rounds_up_to_whole_slots():
    assert best_window(SERIES, at(0), at(8), timedelta(minutes=90)) == Window(at(4), at(6), 45.0)


def test_ties_go_to_earliest_start():
    flat = [(T0 + i * H, 50.0) for i in range(6)]
    assert best_window(flat, at(0), at(6), 2 * H).start == at(0)


def test_gap_in_data_is_never_bridged():
    gappy = [s for i, s in enumerate(SERIES) if i != 4]  # hour 04 missing
    # valid 2 h blocks: 00 90, 01 70, 02 75, 05 85, 06 75 -> 01
    assert best_window(gappy, at(0), at(8), 2 * H) == Window(at(1), at(3), 70.0)


def test_no_window_fits():
    with pytest.raises(ValueError):
        best_window(SERIES, at(0), at(2), 3 * H)


def test_window_now_and_saving():
    now = window_at(SERIES, at(0.5), 2 * H)
    assert now == Window(at(0), at(2), 90.0)
    best = best_window(SERIES, at(0.5), at(8), 2 * H)
    assert saving(now, best) == (45.0, 50.0)


def test_window_now_outside_data():
    with pytest.raises(ValueError):
        window_at(SERIES, at(9), H)
    with pytest.raises(ValueError):
        window_at(SERIES, at(7), 2 * H)


def test_five_minute_series():
    # 12 five-minute slots from 00:00; 15 min job = 3 slots; lowest run is slots 6-8 (10, 5, 15) mean 10
    vals = [50, 50, 40, 40, 30, 30, 10, 5, 15, 60, 60, 60]
    five = [(T0 + i * timedelta(minutes=5), float(v)) for i, v in enumerate(vals)]
    assert step_of(five) == timedelta(minutes=5)
    w = best_window(five, at(0), at(1), timedelta(minutes=15))
    assert (w.start, w.end, w.mean) == (T0 + timedelta(minutes=30), T0 + timedelta(minutes=45), 10.0)


@pytest.mark.parametrize(
    "text,expected",
    [("2h", 2 * H), ("90m", timedelta(minutes=90)), ("1h30m", timedelta(minutes=90)), ("1.5h", timedelta(minutes=90)), ("24H", 24 * H)],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "2", "two hours", "0h", "-1h", "2d"])
def test_parse_duration_rejects(text):
    with pytest.raises(ValueError):
        parse_duration(text)
