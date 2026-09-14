# Seed: specification set

Everything Claude Code needs to build the Seed environment end to end. Python backend, React renderer, served as one process on localhost.

```
CLAUDE.md                                 loads automatically at launch
backend/CLAUDE.md                         loads when working in backend/
frontend/CLAUDE.md                        loads when working in frontend/
docs/01-PRD.md                            scope, demo narrative, out of scope
docs/02-ARCHITECTURE.md                   modules, API surface, parser rules, swap path
docs/03-EVENT-CONTRACT.md                 Pydantic models, generated TypeScript. Frozen.
docs/04-AGENT-RUNTIME.md                  roster, log voice, timing, the failure beat
docs/05-DATA-AND-PIPELINE.md              dataset, defects, Polars steps, cross-filter
docs/06-UI-SPEC.md                        design direction, graph interaction, dashboard, copy
docs/07-IMPLEMENTATION-PLAN.md            five phases with acceptance gates
examples/requirements/retail-analytics.md the demo input and the parser reference
```

Drop this in at the repo root before any code exists, then `git init`, then `claude`.

**Do not turn the docs table in `CLAUDE.md` into `@docs/...` imports.** Imports load at launch, so seven specs would fill the context window before you type. Plain paths mean Claude Code reads only what the current phase needs. Also grep for stray un-backticked `@` in prose, which get treated as imports too.

After the first launch, run `/context` and confirm `CLAUDE.md` appears under Memory files. That is the only non-guess that it loaded.

## Driving the build

One phase per session. Claude Code degrades when handed the whole week at once, and the gates exist to catch drift before it compounds.

Start in plan mode. The kickoff prompt:

```
Read CLAUDE.md, then docs/07-IMPLEMENTATION-PLAN.md.

We are building Phase 0 only. Before writing any code, read
docs/02-ARCHITECTURE.md and docs/03-EVENT-CONTRACT.md in full.

Backend scope: uv project on Python 3.12 with the stack in CLAUDE.md,
app/core/types.py copied verbatim from the event contract, plus
app/core/rng.py, clock.py, events.py, registry.py, and a main.py with a
health route.

Frontend scope: Vite + React + TS strict + Tailwind v4 + Zustand, the
schema export script, generated types/events.ts, and the store applying
events with an exhaustive switch.

Out of scope: the parser, the orchestrator, any runner, any pipeline
code, any API route beyond health, and all styling.

Give me the plan first: files, signatures, and the pyproject. I will
approve before you write.

Stop when the Phase 0 gate passes and show me it passing.
```

Then each subsequent phase:

```
Phase 1. Read docs/07-IMPLEMENTATION-PLAN.md for scope and gate, and
docs/05-DATA-AND-PIPELINE.md for the dataset defects. The parser rules
table in docs/02-ARCHITECTURE.md is authoritative.

Build Phase 1 only. Stop at the gate.
```

Run the gate yourself before approving. They are behaviours, so actually load the file and actually break a `Depends on:` reference.

## When it drifts

Roughly in order of likelihood:

> That number is a literal. Every figure comes from a WorkKernel return value. Rule 4 in CLAUDE.md.

> That logic belongs in Python. The frontend is a renderer. Rule 2.

> You are styling. Polish is Phase 4. Go back to the Phase 3 gate.

> The strict timestamp parse is supposed to raise. Remove the pre-check and let the runner catch it. See the failure beat in docs/04-AGENT-RUNTIME.md.

> You filtered client side. Dashboard filters go to POST /api/runs/{id}/query.

Keep any rules you add concrete and falsifiable. Instructions like "always double-check your work" cause current models to re-verify work that was already correct, which burns turns for nothing.

## Before Phase 0

- Confirm the demo laptop and the projector resolution. The layout targets 1440 wide and projectors are often 1280x720.
- Confirm currency and locale. The spec assumes INR and `en-IN`.
- Confirm nobody expects the generated project to be downloadable as a repo. That is out of scope and it is the most likely thing to be asked for in the room.
