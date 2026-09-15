# Setting up and running Seed

Seed runs entirely on your machine. There is no deployment, no container, no
database, and no API key: one Python process serves the API and the built
frontend together on `http://127.0.0.1:8000`.

Two commands get you there from a clean clone. Everything below is the long
version of those two.

---

## What you need

| | Version | Check with |
|---|---|---|
| **Python** | 3.12.x — **not 3.13** | `python --version` |
| **Node.js** | 18 or newer | `node --version` |
| **git** | any | `git --version` |

The Python version is a hard constraint, not a suggestion.
`backend/pyproject.toml` declares `requires-python = ">=3.12,<3.13"`, so step 2
stops with `Package 'seed' requires a different Python` on anything else. If
`python` on your PATH is not 3.12, see [Troubleshooting](#troubleshooting).

Nothing else is assumed. `uv` and `make` both work if you have them, and neither
is required.

---

## 1. Get the code

```bash
git clone https://github.com/viv1kk/Seed.git
cd Seed
```

## 2. Install, once

```bash
python tasks.py install
```

Around a minute with warm pip and npm caches, a few minutes on a cold one. It
creates the backend virtualenv and installs both dependency trees. When it
prints `install: ok`, setup is done — you do not run it again unless
dependencies change.

npm may warn that `esbuild` has an install script it has not run. Ignore it:
esbuild ships its platform binary as a separate package that npm installs
normally, and the build works without approving anything.

## 3. Run it

```bash
python tasks.py demo
```

This regenerates the TypeScript contract from the Python models, builds the
frontend, and starts the server. It prints:

```
Seed is on http://127.0.0.1:8000
```

Open that. Stop the server with `Ctrl+C`.

> Use `demo` rather than the dev server when you want to see what a viewer sees.
> It is the only configuration where the API and the page share an origin, which
> is how it actually runs.

## 4. Use it

1. The page opens on **Load a requirement to begin**.
2. Either click the **Retail revenue analytics platform** example, or put your
   own Markdown in the box below it — paste it, drop a `.md` file on the box, or
   click **Open a file** — and press **Build the plan**.
3. The plan graph is drawn on the right. Click any node to inspect the task it
   came from. Nothing has run yet.
4. Press **Start the run**. At `1x` the demo document takes about 1 minute 40
   seconds. `2x` and `5x` are in the toolbar.
5. On the retail example the dashboard arrives at the end. Brush the time axis or
   click a category bar: every figure is recomputed in Polars server side.

The first run of a session is slightly slower because the CSVs are read cold. If
you are presenting, do one run beforehand to warm it.

---

## What `install` actually does

You do not need this to run the project. It is here so the virtualenv is not a
black box, and so you can do the steps by hand if the script ever fails.

`tasks.py install` runs exactly four commands:

**1. Create the virtualenv**, at `backend/.venv`:

```bash
python -m venv backend/.venv
```

**2. Upgrade pip inside it.** The `--group` flag in the next step needs a recent
pip, and a fresh venv ships whatever version your host Python bundled:

```bash
# Windows
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
# macOS and Linux
backend/.venv/bin/python -m pip install --upgrade pip
```

**3. Install the backend**, editable, with its dev tools:

```bash
cd backend
# Windows
.venv\Scripts\python.exe -m pip install -e . --group dev
# macOS and Linux
.venv/bin/python -m pip install -e . --group dev
```

That pulls FastAPI, uvicorn, sse-starlette, Pydantic, Polars, markdown-it-py and
Pygments, plus ruff, mypy, pytest and httpx from the `dev` group.

**4. Install the frontend:**

```bash
cd frontend
npm install
```

The virtualenv lives at `backend/.venv` and is git-ignored, along with
`node_modules/` and `frontend/dist/`. Nothing you install lands outside the
project directory, and deleting the folder removes every trace of it.

**You never need to activate the virtualenv.** `tasks.py` calls its interpreter
by full path. Activate it only if you want to run tools directly:

```powershell
# Windows PowerShell
backend\.venv\Scripts\Activate.ps1
# Windows cmd
backend\.venv\Scripts\activate.bat
```

```bash
# macOS, Linux, Git Bash
source backend/.venv/bin/activate    # backend/.venv/Scripts/activate on Windows
```

### Using uv instead

`backend/pyproject.toml` is a valid uv project. If you have uv, `uv sync` and
`uv run <cmd>` are equivalent to the above and faster. `tasks.py` drives a plain
venv because uv does not run on every machine this is built on — Windows
Application Control blocks it on at least one.

---

## Commands

All of them go through `tasks.py`, from the repository root. `make <name>` works
identically wherever `make` exists; the Makefile just delegates.

| Command | What it does |
|---|---|
| `python tasks.py install` | Set up both toolchains. Once. |
| `python tasks.py demo` | **Build the frontend and serve everything on 8000.** |
| `python tasks.py check` | The full gate: ruff, mypy, pytest, tsc, node tests, vite build. |
| `python tasks.py api` | Backend only, on 8000, reloading on save. |
| `python tasks.py web` | Frontend only, on 5173, proxying `/api` to 8000. |
| `python tasks.py types` | Regenerate `frontend/src/types/events.ts` from the Pydantic models. |
| `python tasks.py data` | Regenerate the bundled CSVs. Commit the result. |

### Working on the code

Use `api` and `web` together, in two terminals, for hot reload:

```bash
# terminal 1
python tasks.py api

# terminal 2
python tasks.py web
```

Then open `http://127.0.0.1:5173`. Vite proxies `/api` to the backend on 8000.

Run a single test file with the venv's interpreter directly:

```bash
cd backend
# Windows
.venv\Scripts\python.exe -m pytest tests/test_clock.py
# macOS and Linux
.venv/bin/python -m pytest tests/test_clock.py
```

`frontend/src/types/events.ts` is generated from the Python models and must never
be hand-edited. If you change anything in `backend/app/core/types.py`, run
`python tasks.py types`. `demo` does it for you on every start.

---

## Troubleshooting

**`python --version` is not 3.12.** Install 3.12 and point the script at it. The
venv is created with whatever interpreter runs `tasks.py`, so naming it once is
enough:

```bash
# Windows, with the py launcher
py -3.12 tasks.py install
# macOS and Linux
python3.12 tasks.py install
```

After that, `python tasks.py demo` works normally: every later command uses the
interpreter inside `backend/.venv`, not the one on your PATH.

**`No backend virtualenv at ...`** — you skipped step 2. Run `python tasks.py install`.

**Port 8000 is already in use.** Uvicorn exits with `error while attempting to
bind`. Find and stop whatever holds it:

```powershell
# Windows PowerShell
Get-NetTCPConnection -LocalPort 8000 -State Listen |
  Select-Object -ExpandProperty OwningProcess -Unique |
  ForEach-Object { Stop-Process -Id $_ -Force }
```

```bash
# macOS and Linux
kill $(lsof -ti:8000)
```

A stale server is easy to miss, because the page still loads — from the *old*
build. If a change you made is not showing up, this is usually why.

**The page says "The frontend has not been built yet".** The API is running but
`frontend/dist` is missing, which is what `python tasks.py api` alone gives you.
Run `python tasks.py demo`, or use the dev server on 5173.

**"Cannot reach the backend. Start it on port 8000."** The page loaded but the
API did not answer. Check the terminal running the server.

**Starting over.** Everything installed is inside the project, so deleting three
directories is a clean slate:

```powershell
# Windows PowerShell
Remove-Item -Recurse -Force backend\.venv, frontend\node_modules, frontend\dist
python tasks.py install
```

```bash
# macOS, Linux, Git Bash
rm -rf backend/.venv frontend/node_modules frontend/dist
python tasks.py install
```

---

## Where things are

```
docs/01-PRD.md .. 07-IMPLEMENTATION-PLAN.md   the specification set
examples/requirements/retail-analytics.md     the demo input
backend/app/pipeline/                         the real Polars work
backend/app/runners/                          the simulated agents
frontend/src/ui/                              the renderer
tasks.py                                      every command above
```

One thing worth knowing before you read the code: agent *reasoning* is scripted,
and the engineering underneath is not. The parsing, orchestration, ETL,
transforms and aggregations are real, run at execution time over a real bundled
dataset, and every figure on the dashboard is computed rather than stored. The
**Simulation** badge in the corner says so and stays there. `docs/01-PRD.md` sets
out exactly which half is which.
