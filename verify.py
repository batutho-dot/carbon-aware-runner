"""Check this repository end to end. Prints `verify: PASS` or `verify: FAIL at <step>: <reason>`.

Steps (cheapest first, stops at the first failure, writes nothing into the repository):
  1. compile   every .py file compiles
  2. tests     pytest on fixed series (hand-checked windows, CLI offline); skips count as failure
  3. command   the installed `carbon-run` command starts and shows its help
  4. docs      README has install, the example and a dated live run; docs/architecture.md has
               a Mermaid block; LICENSE is MIT; no em dashes in the docs

Needs: the dev install (`pip install -e .[dev]`). No network in any step; the live dry run is
logged in the README by hand (the API rate-limits hard).

    python verify.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class Fail(Exception):
    pass


def step_compile() -> str:
    files = [p for d in ("src", "tests") for p in (ROOT / d).rglob("*.py")] + [ROOT / "verify.py"]
    for path in files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as err:
            raise Fail(f"{path.relative_to(ROOT)}: {err}") from err
    return f"{len(files)} files"


def step_tests() -> str:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs"],
        cwd=ROOT, capture_output=True, text=True, env=env,
    )
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else proc.stderr.strip()[-200:]
    if proc.returncode != 0 or "skipped" in last:
        raise Fail(last)
    return last


def step_command() -> str:
    exe = shutil.which("carbon-run", path=sysconfig.get_path("scripts"))
    if not exe:
        raise Fail("carbon-run command not installed in this environment")
    proc = subprocess.run([exe, "--help"], capture_output=True, text=True)
    if proc.returncode != 0 or "--dry-run" not in proc.stdout:
        raise Fail(f"carbon-run --help failed: {proc.stderr[-200:]}")
    return "carbon-run --help ok"


def step_docs() -> str:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("pip install", "carbon-run --area DK1 --within 24h --duration 2h -- python train.py"):
        if needle not in readme:
            raise Fail(f"README.md is missing {needle!r}")
    if not re.search(r"Live dry run, \d{4}-\d{2}-\d{2}", readme):
        raise Fail("README.md has no dated live dry run ('Live dry run, YYYY-MM-DD')")
    if "```mermaid" not in (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8"):
        raise Fail("docs/architecture.md has no Mermaid block")
    if not (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"):
        raise Fail("LICENSE is not MIT")
    docs = [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]
    dashed = [p.name for p in docs if chr(0x2014) in p.read_text(encoding="utf-8")]
    if dashed:
        raise Fail(f"em dash in {dashed}")
    return "README, architecture, LICENSE ok"


STEPS = [("compile", step_compile), ("tests", step_tests), ("command", step_command), ("docs", step_docs)]


def main() -> int:
    sys.dont_write_bytecode = True
    print(f"verify-repo: {ROOT}")
    for name, fn in STEPS:
        try:
            detail = fn()
        except Fail as err:
            print(f"verify: FAIL at {name}: {err}")
            return 1
        except Exception as err:  # an unexpected crash is a failure of that step, not a pass
            print(f"verify: FAIL at {name}: {type(err).__name__}: {err}")
            return 1
        print(f"{name}: ok ({detail})")
    print("verify: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
