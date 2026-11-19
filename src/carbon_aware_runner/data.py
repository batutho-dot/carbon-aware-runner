"""Get a series from Energi Data Service through energidata-mcp's client (imported, not copied)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from energidata_mcp import api

DK = ZoneInfo("Europe/Copenhagen")

# metric -> (dataset, UTC time key, value key template, unit template)
SOURCES = {
    "co2": ("CO2EmisProg", "Minutes5UTC", "CO2Emission", "g CO2/kWh"),
    "price": ("DayAheadPrices", "TimeUTC", "DayAheadPrice{cur}", "{cur}/MWh"),
}


def describe(metric: str, currency: str) -> tuple[str, str]:
    dataset, _, _, unit = SOURCES[metric]
    return dataset, unit.format(cur=currency)


def to_series(records: list[dict[str, Any]], time_key: str, value_key: str) -> list[tuple[datetime, float]]:
    """Rows -> sorted (UTC slot start, value). Rows without a value are dropped."""
    series = []
    for row in records:
        value = row.get(value_key)
        if value is None:
            continue
        t = datetime.fromisoformat(row[time_key]).replace(tzinfo=timezone.utc)
        series.append((t, float(value)))
    series.sort()
    return series


async def fetch_series(
    metric: str, area: str, start_utc: datetime, end_utc: datetime, currency: str = "DKK"
) -> list[tuple[datetime, float]]:
    """Fetch [start_utc, end_utc) for one area. The API reads start and end as Danish local time."""
    dataset, time_key, value_key, _ = SOURCES[metric]
    start_dk = start_utc.astimezone(DK).replace(minute=0, second=0, microsecond=0)
    end_dk = (end_utc + timedelta(hours=1)).astimezone(DK).replace(minute=0, second=0, microsecond=0)
    records = await api.fetch_records(dataset, f"{start_dk:%Y-%m-%dT%H:%M}", f"{end_dk:%Y-%m-%dT%H:%M}", area)
    return to_series(records, time_key, value_key.format(cur=currency))
