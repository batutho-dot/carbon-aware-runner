"""carbon-run: wait for the cleanest (or cheapest) window before a deadline, then run a command.

    carbon-run --area DK1 --within 24h --duration 2h -- python train.py
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
import time
from datetime import datetime, timezone

from energidata_mcp.api import ApiError

from . import data
from .window import Window, best_window, parse_duration, saving, window_at


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="carbon-run",
        description="Start a command in the window with the lowest CO2 intensity (or price) before a deadline.",
        epilog="Example: carbon-run --area DK1 --within 24h --duration 2h -- python train.py",
    )
    p.add_argument("--area", required=True, choices=["DK1", "DK2"], help="Danish price area")
    p.add_argument("--within", required=True, help="deadline from now: the job must finish by then, e.g. 24h")
    p.add_argument("--duration", required=True, help="how long the job runs, e.g. 2h or 90m")
    p.add_argument("--metric", choices=["co2", "price"], default="co2", help="what to minimise (default co2)")
    p.add_argument("--currency", choices=["DKK", "EUR"], default="DKK", help="price unit (with --metric price)")
    p.add_argument("--dry-run", action="store_true", help="print the chosen window and exit without waiting or running")
    p.add_argument("command", nargs=argparse.REMAINDER, help="the command to run, after --")
    return p


def _local(t: datetime) -> str:
    return t.astimezone(data.DK).strftime("%Y-%m-%d %H:%M")


def plan(args: argparse.Namespace, now: datetime) -> tuple[Window, Window, str, list[str]]:
    """Fetch data and pick the window. Returns (best, now_window, unit, notes)."""
    within = parse_duration(args.within)
    duration = parse_duration(args.duration)
    if duration > within:
        raise ValueError(f"--duration {args.duration} is longer than --within {args.within}")
    deadline = now + within
    series = asyncio.run(data.fetch_series(args.metric, args.area, now, deadline, args.currency))
    dataset, unit = data.describe(args.metric, args.currency)
    if len(series) < 2:
        raise ValueError(f"{dataset} has no data for {args.area} from now on")
    notes = []
    covered_until = series[-1][0] + (series[1][0] - series[0][0])
    if covered_until < deadline:
        notes.append(
            f"{dataset} only reaches {_local(covered_until)}; windows after that are not considered."
        )
        deadline = covered_until
    best = best_window(series, now, deadline, duration)
    now_window = window_at(series, now, duration)
    return best, now_window, unit, notes


def report(args, best: Window, now_window: Window, unit: str, notes: list[str], now: datetime) -> str:
    dataset, _ = data.describe(args.metric, args.currency)
    diff, pct = saving(now_window, best)
    what = "CO2 intensity" if args.metric == "co2" else "price"
    lines = [
        f"Area {args.area}, {what} from {dataset}, times in Danish local time.",
        f"Chosen window: {_local(best.start)} to {_local(best.end)}, mean {best.mean:.1f} {unit}",
        f"Running now:   {_local(now_window.start)} to {_local(now_window.end)}, mean {now_window.mean:.1f} {unit}",
        f"Saved vs now:  {diff:.1f} {unit} ({pct:.0f}%)",
    ]
    wait_h = (best.start - now).total_seconds() / 3600
    lines.append(f"Starts in {wait_h:.1f} h." if wait_h > 0 else "Starts now.")
    return "\n".join(lines + [f"Note: {n}" for n in notes])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command and not args.dry_run:
        print("carbon-run: give the command to run after --, or use --dry-run", file=sys.stderr)
        return 2
    now = _now()
    try:
        best, now_window, unit, notes = plan(args, now)
    except (ValueError, ApiError) as err:
        print(f"carbon-run: {err}", file=sys.stderr)
        return 2
    print(report(args, best, now_window, unit, notes, now), flush=True)
    if args.dry_run:
        print("Dry run: not waiting, not running" + (f" {' '.join(command)}." if command else "."))
        return 0
    delay = (best.start - _now()).total_seconds()
    if delay > 0:
        time.sleep(delay)
    print(f"Running: {' '.join(command)}", flush=True)
    return subprocess.run(command).returncode


if __name__ == "__main__":
    sys.exit(main())
