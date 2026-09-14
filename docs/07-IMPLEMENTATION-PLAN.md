# 07. Implementation Plan

Five days. Demo-ready at the end of day 4. Day 5 is hardening and rehearsal, not build.

The failure mode for this project is a beautiful shell with nothing running inside it. The order is deliberately ugly-but-complete first, polish last. Do not reorder. Do not start styling on day 2 because the screen looks bad. It is supposed to look bad on day 2.

Each phase has a gate, which is a demonstrable behaviour rather than a checklist of files. Do not begin the next phase until the gate passes and both builds are clean.

Local serving removes the whole deployment phase, which is why there is room for the interactive graph and cross-filtering. Spend it there.

---

## Phase 0. Scaffold and contract, half of day 1

**Backend**
1. `uv init`, Python 3.12, FastAPI, sse-starlette, Pydantic v2, Polars, markdown-it-py, Pygments. ruff, mypy strict, pytest, pytest-asyncio.
2. `app/core/types.py`, the models from `03-EVENT-CONTRACT.md`, verbatim.
3. `app/core/rng.py`: one seeded `random.Random`. A ruff rule banning bare `random.` and `numpy.random` elsewhere.
4. `app/core/clock.py`: `Clock.sleep(ms)` dividing by speed, `pause()`, `resume()`, `cancel()`, waiting on an `asyncio.Event` and propagating `CancelledError`.
5. `app/core/events.py`: `EventBus` over `asyncio.Queue`, assigning `seq`, retaining all events for replay.
6. `app/core/registry.py`: in-memory run registry.
7. `app/main.py` with a health route. Static mount comes later and must be mounted last.

**Frontend**
8. Vite, React 18, TS strict, Tailwind v4, Zustand. Dev proxy `/api` to 8000.
9. `scripts/export_schema.py` and `npm run gen:types`. Commit the generated `types/events.ts`.
10. Zustand store applying events with an exhaustive switch and `assertNever`.

**Gate:** a pytest replays a hand-written list of ten events through the reducer and asserts the resulting state. `npm run gen:types` produces TypeScript that compiles, and the frontend store applies the same ten events to the same result.

---

## Phase 1. Parser and plan, rest of day 1

1. `scripts/generate_data.py` producing the three CSVs per `05-DATA-AND-PIPELINE.md`, with every deliberate defect at the stated volume. Run it, commit the output, assert the defect counts in a test.
2. `app/parser/`: lexer, rules, `build_plan`. Topological sort with cycle detection. Parse warnings and errors as returned data, not raised exceptions.
3. `POST /api/plans`, `GET /api/examples`.
4. `examples/requirements/retail-analytics.md` parsing into 3 phases and 7 tasks with correct owners and dependencies.
5. Frontend: load an example, render the source document, render the plan as a plain list with owner and dependencies. No graph, no styling.

**Gate:** load the demo file, see the correct plan. Edit a `###` heading, reload, see the plan change. Break a `Depends on:` reference and see the error, with the run refused.

---

## Phase 2. Orchestrator and live stream, day 2

1. `app/pipeline/` stubs returning plausibly shaped results instantly. The only sanctioned stub, and it is temporary.
2. `app/runners/base.py` and `simulated.py`, with generic beats derived from task steps. Agent scripts come in phase 3.
3. `app/orchestrator/`: ready-set scheduling, `Semaphore(2)`, dependency gating, queue fan-in, deadlock detection, cancellation.
4. `POST /api/runs`, `GET /api/runs/{id}/stream` with replay from `seq=0`, `POST /api/runs/{id}/control`.
5. Frontend: `EventSource` subscription, rAF-batched application to the store, plan list with status text, a plain `div` log, Start, Pause, Reset.

**Gate:** press Start and watch a run complete end to end in the browser over SSE. Statuses move correctly, two tasks run in parallel where the graph allows, log lines arrive in order, `run.completed` fires. Pause and Resume work. Refresh mid-run and the run replays and rejoins. Two runs at the same seed produce identical logs, verified by diff. It looks terrible. Correct.

---

## Phase 3. Real work, day 3

The day that determines whether the demo survives scrutiny. Protect it.

1. `pipeline/load.py` with `pl.read_csv(infer_schema_length=0)`. Real timings and counts.
2. `pipeline/profile.py`, including timestamp format fingerprinting.
3. `pipeline/clean.py` with both strategies. Verify that `iso-strict` genuinely raises on the real file and that `multi-format-day-first` genuinely resolves every row.
4. `pipeline/transform.py`: joins with real match statistics, all derived columns.
5. `pipeline/aggregate.py`: five aggregations, `maintain_order=True` everywhere, optional `Filters`.
6. `pipeline/kernel.py` and `pipeline/highlight.py`.
7. `POST /api/runs/{id}/query` and the retained derived frame in the registry.
8. Per-agent scripts replacing the generic beats. Every number in a log line sourced from a prior `Work` result.
9. The failure and retry beat, driven by the real exception and a real probe for the failing count and samples.
10. Artifacts: real source reads, real dataset previews, `GET /api/artifacts/{id}`, and the generated `verification.md`.
11. The dashboard, bound to the real `AggBundle`. Minimally styled is fine today.

**Gate:** a full run ends with a dashboard whose numbers can be verified independently against the CSVs with a short script. The retry happens and the first attempt genuinely raised. `curl` the query endpoint with a date range and get different, correct figures. Opening `pipeline/clean.py` in the artifacts panel shows the code that just ran.

---

## Phase 4. Make it the plan room, day 4

Now, and only now, `06-UI-SPEC.md`.

1. Tokens, fonts, the three-column shell.
2. The plan graph: dagre layout, custom SVG, all six node states, orthogonal edges with the ready-brightening.
3. Graph interaction: click to inspect, hover dependency tracing, pan and zoom, fit, auto-focus on failure, keyboard path.
4. Agent rail with rolling activity and the attempt counter.
5. Log stream: fixed columns, level tinting, filters, autoscroll release, copy all, capped render window.
6. Artifacts panel: tree, viewers, insert flash.
7. Dashboard on paper: five surfaces, chart palette, INR formatting, tabular figures.
8. **Cross-filtering**: brush, category click, region click, filter chips, in-flight dimming.
9. The completion transition. One moment, per spec.
10. Controls, simulation badge, empty states, every copy string.
11. Accessibility floor: focus rings, contrast verification, reduced motion, aria-live scoping.

**Gate:** run `make demo` and watch the whole thing at 1x on the actual demo screen without touching anything, then cross-filter the dashboard. If any moment is unclear to someone who has not seen it, fix that moment rather than adding a feature.

---

## Phase 5. Harden and rehearse, day 5

Not a build day. Anything unfinished is cut.

1. Second requirement file, `logistics-ops.md`, with a different graph shape. It is the answer to "does this only work for one document?"
2. Paste-your-own box, proving an unscripted task still runs on the generic fallback beats.
3. The shared event fixture test in both languages, asserting terminal state and exactly one retry.
4. Full pass for server exceptions, React warnings, and `EventSource` reconnection behaviour. Three consecutive runs without a restart, watching for memory growth in the registry.
5. `make demo` from a clean checkout on the demo laptop. Pin the port, confirm nothing else holds it, check the projector resolution against the 1440 layout, pre-warm one run.
6. Rehearse the eight beats from `01-PRD.md` twice, end to end, out loud.

**Gate:** two clean full runs via `make demo` on the actual demo laptop and the actual projector.

---

## Cut list

If day 3 runs long, cut in this order, deliberately, and tell the team.

1. The second requirement file
2. The paste-your-own box
3. Keyboard navigation in the graph
4. Category and region click filtering, keeping the time brush
5. The artifacts code viewer, keeping the tree and dataset previews
6. Revenue by region, keeping four dashboard surfaces

Never cut: the real Polars pipeline, the retry beat, node inspection, the time-axis cross-filter, the completion transition. Those five are the demo.

## Rehearsal notes

- Open on the plan view, not mid-run. Let the graph be understood before anything moves.
- Click a node early, before starting. It shows the plan came from their document.
- Edit a heading live. Fifteen seconds, and it settles the "is this a video" question before it is asked.
- Say "simulated" yourself, before anyone else does, and say what is real in the same breath.
- Run at 1x until the retry, then offer to speed up. The retry is worth the wait.
- Have `pipeline/clean.py` open in the artifacts panel ready for the "is the data real" question.
- Finish on the cross-filter, not on the static dashboard. Brush a quarter and let the numbers move. That is the last thing they should see.
