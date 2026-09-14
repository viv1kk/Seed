# CLAUDE.md

Project context for Claude Code. Read this before writing any code. Read the docs listed under "Specification set" before starting a phase.

## What this is

**Seed** is an environment that takes a requirements file written in Markdown, decomposes it into a task graph, and fulfils it by running a team of AI agents. The run is visualised live: an interactive task graph, the agents working, a streaming log, and the artifacts they produce. The run ends with an interactive analytics dashboard rendered from data the pipeline actually processed.

We do not have LLM API access. This build ships **Simulation Mode**: agent reasoning is scripted, the engineering work underneath is real. The client knows this and has approved it. The goal is to prove the platform shape so the agent runtime can be swapped in later behind an unchanged interface.

## Shape

Python does all the work. React renders it.

- **Backend (Python 3.12, FastAPI).** Parser, orchestrator, agent runners, and the data pipeline. Every number originates here.
- **Frontend (React, TypeScript).** Subscribes to a server-sent event stream and draws. No business logic, no data processing, no simulation awareness.
- **Serving.** One process. FastAPI serves the API and mounts the built frontend as static files. The demo runs on localhost, not on a deployed URL.

## Non-negotiable rules

1. **All logic is Python.** Parsing, planning, orchestration, simulation, and data work live in `backend/`. If you are writing a rule, a calculation, or a decision in TypeScript, it is in the wrong place.
2. **The frontend is a renderer.** It may hold view state (selection, filters, zoom, scroll). It may not compute a metric, derive a status, or decide what happens next.
3. **No network calls to any model provider.** No API key exists in this project and no code path may expect one.
4. **Fake the agents, not the work.** The ETL, transforms, and aggregations run for real in Polars over a real bundled dataset. Every figure on the dashboard is computed at run time. A hardcoded number, row count, or duration is a defect.
5. **Everything reaches the UI as an event.** The orchestrator emits the events in `docs/03-EVENT-CONTRACT.md` over SSE. Components subscribe to state derived from those events.
6. **All agent work goes through `AgentRunner`.** One ABC, one simulated implementation. Simulation details must not leak into the orchestrator, the API, or the frontend.
7. **Runners are async generators.** `async def run(...)` yielding events. Pause, cancel, and speed depend on it.
8. **Seeded randomness only.** One `random.Random(seed)` instance in `core/rng.py`. Bare `random.*` and `numpy.random` are banned. All Polars `group_by` calls pass `maintain_order=True`, or run output drifts between runs.
9. **The parser is real.** Editing a heading in the requirements file must visibly change the task graph. No filename-keyed shortcuts.

## Specification set

Read in order. Each is authoritative for its area.

| Doc | Authoritative for |
|---|---|
| `docs/01-PRD.md` | Scope, demo narrative, what is explicitly out |
| `docs/02-ARCHITECTURE.md` | Modules, API surface, parser rules, orchestrator, swap path |
| `docs/03-EVENT-CONTRACT.md` | Pydantic models and generated TypeScript. Frozen. |
| `docs/04-AGENT-RUNTIME.md` | Agent roster, log voice, timing, the failure beat |
| `docs/05-DATA-AND-PIPELINE.md` | Dataset, defects, Polars transforms, aggregations, cross-filter |
| `docs/06-UI-SPEC.md` | Design direction, tokens, layout, interaction, motion, copy |
| `docs/07-IMPLEMENTATION-PLAN.md` | Phase order, tasks, acceptance gates |

`examples/requirements/retail-analytics.md` is the demo input and the parser reference.

`backend/CLAUDE.md` and `frontend/CLAUDE.md` carry rules scoped to those trees and load only when you work in them.

## Stack

**Backend.** Python 3.12, `uv` for dependencies, FastAPI, `sse-starlette`, Pydantic v2, Polars, `markdown-it-py`, Pygments. Tooling: ruff, mypy strict, pytest with pytest-asyncio.

**Frontend.** Vite, React 18, TypeScript strict, Tailwind v4 via `@tailwindcss/vite`, Zustand, Recharts, dagre for graph layout. Native `EventSource` for SSE. No data-fetching library for four endpoints.

Do not add libraries beyond this list without saying in the commit what it replaces. Specifically: no React Flow (custom SVG, see the UI spec), no client-side syntax highlighter (Pygments does it server side), no state machine library, no UI component kit, no charting library besides Recharts.

## Commands

Everything goes through `tasks.py`. Use these, not the underlying tools.

```bash
python tasks.py install   # both toolchains, from scratch
python tasks.py check     # the gate: ruff, mypy, pytest, tsc, node --test, vite build
python tasks.py types     # regenerate frontend/src/types/events.ts from the Pydantic models
python tasks.py api       # backend on 8000, reloading
python tasks.py web       # frontend on 5173, proxying /api to 8000
```

`make check` and the rest work identically where `make` exists; the Makefile just
delegates. `make demo` arrives in phase 2, once `main.py` mounts the built frontend
and one process serves everything. That is how the client sees it, so test on that
path rather than on the Vite dev server.

`uv` is the intended package manager and the pyproject is a uv project, but it does
not run on every build machine (Windows Application Control blocks it on at least
one), so `tasks.py` drives a plain `backend/.venv` instead and `uv.lock` is not yet
committed. Where uv runs, `uv sync` and `uv run <cmd>` are equivalent and preferred;
generate and commit the lock file from there.

Run a single test file with `backend/.venv/Scripts/python -m pytest tests/test_clock.py`
(`backend/.venv/bin/python` off Windows).

## Code conventions

**Python.** Full type annotations, mypy strict, no `Any`. Pydantic models for anything crossing a boundary. Pure functions in `pipeline/`, which imports nothing from `runners/` or `orchestrator/`. Prefer `match` on `event.type` with an exhaustiveness assert.

**TypeScript.** No `any`. Event types are generated from the backend schema and are never hand-edited. Discriminated unions over optional fields. No React imports outside `src/ui/`.

Keep files under about 250 lines. Split by responsibility.

## Definition of done, per phase

The phase gate in `docs/07-IMPLEMENTATION-PLAN.md` passes, `python tasks.py check` is clean, and a full run completes with no server exception and no browser console error. Do not start the next phase before the gate passes. Do not skip ahead to visual polish.

## Writing copy

UI copy is design content. Sentence case, active voice, plain verbs. A button says what happens when pressed. Errors say what went wrong and what to do next. No em dashes in user-facing strings. Exact strings are in `docs/06-UI-SPEC.md`.
