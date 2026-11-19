# carbon-aware-runner

Start a heavy job (a model training run, a big build, a batch export) in the cleanest window before your deadline, in Danish price area DK1 or DK2. It looks up Energinet's CO2 intensity forecast, picks the run of hours with the lowest mean, tells you how much cleaner that is than starting now, then waits and runs your command.

It uses the Energi Data Service client from [energidata-mcp](https://github.com/batutho-dot/energidata-mcp) as a dependency. Open data, no API key.

## Install

Python 3.11 or newer.

```
git clone https://github.com/batutho-dot/carbon-aware-runner.git
cd carbon-aware-runner
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -e .[dev]
```

## Use

```
carbon-run --area DK1 --within 24h --duration 2h -- python train.py
```

- `--within`: the job must be finished by then (`24h`, `90m`, `1h30m`).
- `--duration`: how long the job runs.
- `--dry-run`: print the chosen window and stop.
- `--metric price`: pick the cheapest window by day-ahead price instead (`--currency DKK` or `EUR`).

Everything after `--` is the command. Its exit code becomes carbon-run's exit code.

## Live dry run, 2026-11-19

Run at 22:44 Danish time:

```
$ carbon-run --area DK1 --within 24h --duration 2h --dry-run -- python train.py
Area DK1, CO2 intensity from CO2EmisProg, times in Danish local time.
Chosen window: 2026-11-20 19:30 to 2026-11-20 21:30, mean 61.5 g CO2/kWh
Running now:   2026-11-19 22:40 to 2026-11-20 00:40, mean 235.0 g CO2/kWh
Saved vs now:  173.6 g CO2/kWh (74%)
Starts in 20.8 h.
Dry run: not waiting, not running python train.py.
```

Waiting 20.8 hours cut the forecast intensity of this two-hour job from 235.0 to 61.5 g CO2/kWh, 74% less. That is one evening's forecast, not an average: other days and other deadlines give other numbers.

## How it picks

- Data: `CO2EmisProg`, Energinet's forecast of the CO2 intensity of consumed electricity, in 5-minute steps. Realised data (`CO2Emis`) stops at the present, so it cannot rank future hours. The forecast usually reaches the end of the next day; if `--within` goes further, the tool says so and only looks at the part it has.
- Window: the run of back-to-back slots that lasts at least `--duration`, starts no earlier than now and ends by the deadline, with the lowest mean. Ties go to the earliest start.
- Saving: mean of the chosen window minus mean of the window that starts now, per kWh (or per MWh for price). Multiply by the job's energy use for an absolute figure.

Diagram and file map: [docs/architecture.md](docs/architecture.md).

## Check

```
python verify.py
```

Compiles everything, runs the tests (fixed series with hand-checked windows, the CLI offline), checks the installed command and the docs. No network.

## Licence

MIT, see [LICENSE](LICENSE). Data: Energi Data Service, Energinet.
