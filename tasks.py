#!/usr/bin/env python3
"""The project's entry points, in one place that runs everywhere.

    python tasks.py install     set up both toolchains
    python tasks.py types       regenerate the TypeScript contract
    python tasks.py data        regenerate the bundled CSVs (commit the result)
    python tasks.py check       the full gate: lint, types, tests, build
    python tasks.py demo        build the frontend and serve the whole thing on 8000
    python tasks.py api         backend on 8000, reloading
    python tasks.py web         frontend on 5173, proxying /api to 8000

The Makefile delegates here, so `make check` and `python tasks.py check` do the
same thing. This file exists because neither `uv` nor `make` runs on every
machine this project is built on, and CLAUDE.md must not name a command that
fails. Only Python and Node are assumed.

When uv is available, BACKEND_PYTHON below becomes ["uv", "run", "python"] and
`install` becomes `uv sync`. Nothing else changes.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

VENV = BACKEND / ".venv"
IS_WINDOWS = platform.system() == "Windows"
VENV_PYTHON = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")

SCHEMA_OUT = FRONTEND / "src" / "types" / "events.schema.json"

# Pinned, because the demo laptop needs one address known in advance and checked
# for a squatter before the room fills up.
DEMO_PORT = 8000

# npm is a shell script on Windows, so it needs a shell to resolve.
NPM = "npm.cmd" if IS_WINDOWS else "npm"


class TaskError(RuntimeError):
    pass


def run(command: Sequence[str | Path], cwd: Path, label: str) -> None:
    printable = " ".join(str(part) for part in command)
    print(f"\n\033[1m=== {label} ===\033[0m\n{printable}\n", flush=True)
    result = subprocess.run([str(part) for part in command], cwd=cwd, check=False)  # noqa: S603
    if result.returncode != 0:
        raise TaskError(f"{label} failed with exit code {result.returncode}")


def require_venv() -> Path:
    if not VENV_PYTHON.exists():
        raise TaskError(f"No backend virtualenv at {VENV}. Run: python tasks.py install")
    return VENV_PYTHON


# ---------------------------------------------------------------- tasks


def install() -> None:
    """Create the backend virtualenv and install both dependency trees."""
    if not VENV_PYTHON.exists():
        run([sys.executable, "-m", "venv", str(VENV)], BACKEND, "create virtualenv")
    # --group needs a recent pip, and the venv ships whatever the host had.
    run([VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip"], BACKEND, "upgrade pip")
    run(
        [VENV_PYTHON, "-m", "pip", "install", "-e", ".", "--group", "dev"],
        BACKEND,
        "backend dependencies",
    )
    run([NPM, "install", "--no-audit", "--no-fund"], FRONTEND, "frontend dependencies")


def types() -> None:
    """Regenerate the TypeScript contract from the Pydantic models.

    Both halves, in order: Python writes the schema, Node turns it into
    TypeScript and refuses to emit a union that will not discriminate.
    """
    python = require_venv()
    run(
        [python, "-m", "scripts.export_schema", "--out", SCHEMA_OUT],
        BACKEND,
        "export JSON schema",
    )
    run([NPM, "run", "gen:types"], FRONTEND, "generate TypeScript")


def data() -> None:
    """Regenerate the bundled dataset. The output is committed, so commit it."""
    run([require_venv(), "-m", "scripts.generate_data"], BACKEND, "generate dataset")


def check() -> None:
    """The phase gate. Everything, in the order that fails fastest."""
    python = require_venv()
    run([python, "-m", "ruff", "check", "."], BACKEND, "ruff")
    run([python, "-m", "mypy", "."], BACKEND, "mypy")
    run([python, "-m", "pytest"], BACKEND, "pytest")
    run([NPM, "run", "typecheck"], FRONTEND, "tsc")
    run([NPM, "test"], FRONTEND, "node --test")
    run([NPM, "run", "build"], FRONTEND, "vite build")


def demo() -> None:
    """What the client sees: one process on 8000 serving the API and the build.

    Types first, then the bundle, then uvicorn. Regenerating the contract here is
    deliberate: the demo must never run against TypeScript that has drifted from
    the Pydantic models, and this is the command that starts the demo.

    No --reload. A reloader watching the tree mid-presentation is a way to lose a
    run to a stray file save.
    """
    types()
    run([NPM, "run", "build"], FRONTEND, "vite build")
    print(f"\n\033[1mSeed is on http://127.0.0.1:{DEMO_PORT}\033[0m\n", flush=True)
    run(
        [require_venv(), "-m", "uvicorn", "app.main:app", "--port", str(DEMO_PORT)],
        BACKEND,
        "uvicorn",
    )


def api() -> None:
    run(
        [
            require_venv(),
            "-m",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--port",
            str(DEMO_PORT),
        ],
        BACKEND,
        "uvicorn",
    )


def web() -> None:
    run([NPM, "run", "dev"], FRONTEND, "vite")


TASKS: dict[str, Callable[[], None]] = {
    "install": install,
    "types": types,
    "data": data,
    "check": check,
    "demo": demo,
    "api": api,
    "web": web,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in TASKS:
        print(__doc__)
        print(f"Tasks: {', '.join(TASKS)}")
        return 1 if argv else 0

    try:
        TASKS[argv[0]]()
    except TaskError as error:
        print(f"\n\033[31m{error}\033[0m", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    print(f"\n\033[32m{argv[0]}: ok\033[0m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
