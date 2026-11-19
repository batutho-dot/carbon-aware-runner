"""CLI and data layer, offline: the API call is swapped for the fixed series from test_window."""

import sys
from datetime import datetime, timezone

import pytest

from carbon_aware_runner import cli, data
from test_window import SERIES, at


@pytest.fixture
def offline(monkeypatch):
    calls = []

    async def fake_fetch(metric, area, start, end, currency="DKK"):
        calls.append((metric, area, start, end, currency))
        return SERIES

    monkeypatch.setattr(data, "fetch_series", fake_fetch)
    monkeypatch.setattr(cli, "_now", lambda: at(0.5))
    return calls


def test_dry_run_prints_window_and_saving(offline, capsys):
    code = cli.main(["--area", "DK1", "--within", "8h", "--duration", "2h", "--dry-run", "--", "python", "train.py"])
    out = capsys.readouterr().out
    assert code == 0
    # 2026-01-01 04:00 UTC is 05:00 in Denmark (winter time)
    assert "Chosen window: 2026-01-01 05:00 to 2026-01-01 07:00, mean 45.0 g CO2/kWh" in out
    assert "Saved vs now:  45.0 g CO2/kWh (50%)" in out
    assert "Starts in 3.5 h." in out
    assert "not running python train.py" in out
    assert offline[0][:2] == ("co2", "DK1")


def test_deadline_past_forecast_gives_note(offline, capsys):
    assert cli.main(["--area", "DK2", "--within", "24h", "--duration", "1h", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Chosen window: 2026-01-01 08:00 to 2026-01-01 09:00, mean 30.0" in out
    assert "Note: CO2EmisProg only reaches 2026-01-01 09:00" in out


def test_price_metric_uses_price_unit(offline, capsys):
    assert cli.main(["--area", "DK1", "--within", "8h", "--duration", "2h", "--metric", "price", "--currency", "EUR", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "price from DayAheadPrices" in out and "EUR/MWh" in out
    assert offline[0][0] == "price" and offline[0][4] == "EUR"


def test_runs_command_when_window_is_now(offline, monkeypatch, capsys):
    monkeypatch.setattr(cli.time, "sleep", lambda s: pytest.fail("should not wait"))
    # 1 h within 1 h deadline from 00:30: only the 'now' slot fits
    code = cli.main(["--area", "DK1", "--within", "30m", "--duration", "30m", "--", sys.executable, "-c", "raise SystemExit(7)"])
    assert code == 7
    assert "Starts now." in capsys.readouterr().out


def test_waits_until_window(offline, monkeypatch):
    slept = []
    monkeypatch.setattr(cli.time, "sleep", slept.append)
    assert cli.main(["--area", "DK1", "--within", "8h", "--duration", "2h", "--", sys.executable, "-c", "pass"]) == 0
    assert slept == [3.5 * 3600]


def test_bad_input_exits_2(offline, capsys):
    assert cli.main(["--area", "DK1", "--within", "1h", "--duration", "2h", "--dry-run"]) == 2
    assert "longer than --within" in capsys.readouterr().err
    assert cli.main(["--area", "DK1", "--within", "8h", "--duration", "2h"]) == 2  # no command


def test_to_series_sorts_and_drops_empty_rows():
    rows = [
        {"Minutes5UTC": "2026-11-19T10:05:00", "CO2Emission": 80},
        {"Minutes5UTC": "2026-11-19T10:00:00", "CO2Emission": 90.5},
        {"Minutes5UTC": "2026-11-19T10:10:00", "CO2Emission": None},
    ]
    assert data.to_series(rows, "Minutes5UTC", "CO2Emission") == [
        (datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc), 90.5),
        (datetime(2026, 11, 19, 10, 5, tzinfo=timezone.utc), 80.0),
    ]


def test_fetch_series_asks_api_in_danish_time(monkeypatch):
    seen = []

    async def fake(dataset, start, end, area):
        seen.append((dataset, start, end, area))
        return [{"TimeUTC": "2026-11-19T10:00:00", "DayAheadPriceDKK": 500.0}]

    monkeypatch.setattr(data.api, "fetch_records", fake)
    import asyncio

    out = asyncio.run(data.fetch_series("price", "DK2", datetime(2026, 11, 19, 9, 40, tzinfo=timezone.utc),
                                        datetime(2026, 11, 19, 20, 0, tzinfo=timezone.utc)))
    # 09:40 UTC = 10:40 DK -> 10:00; 20:00 UTC + 1 h = 22:00 DK
    assert seen == [("DayAheadPrices", "2026-11-19T10:00", "2026-11-19T22:00", "DK2")]
    assert out == [(datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc), 500.0)]
