# 01. Product Requirements

## Problem

Teams write requirements as documents and then spend weeks translating them into pipelines, transforms, and dashboards by hand. The client wants to compress that: hand a Markdown requirements file to an environment, and have a team of AI agents build the described solution while you watch.

## Product

**Seed** is that environment. Three jobs:

1. Turn a requirements file into a plan you can inspect before anything runs.
2. Execute the plan with a team of agents, showing who is doing what, right now, with their logs.
3. Deliver the built solution in the page, along with every artifact produced on the way.

## This release: Simulation Mode

No LLM API access is available. The agent reasoning layer is scripted. Everything underneath is real.

**Real in this build**
- Markdown parsing into a dependency-ordered task graph
- Orchestration, scheduling, parallelism, dependency gating
- The event contract and the SSE stream
- Extract, transform, load, and aggregation in Polars over a bundled dataset, computed at run time
- Generated code artifacts that are the actual code doing the work
- The dashboard, rendered from computed output, and cross-filterable against the live pipeline

**Scripted in this build**
- Agent reasoning narration in the log stream
- Task durations, as seeded jitter over a real work floor
- The recovery strategy chosen in response to a genuine failure

The UI carries a persistent **Simulation** badge. It stays. A deterministic replay mode is a legitimate feature of the real product too.

## Users

**Client stakeholder watching the demo.** Needs to believe autonomous agents did the work and needs a real deliverable at the end. Cares about the arc: requirement in, solution out.

**Client engineer poking at it.** Will ask whether the data is real, will try editing the requirements file, will open the generated code, will try to break the dashboard. Every probe must hold up.

**Our team after the demo.** Needs the codebase to be the real platform with one component stubbed, not a throwaway. The backend is Python because the eventual agent runtime is Python.

## The demo narrative

Eight beats. The build serves this arc.

1. **Land on the console.** Empty state invites a requirements file. Two curated files available.
2. **Load the requirement.** The document renders on the left, unmodified.
3. **The plan appears.** The parser decomposes it into phases and tasks with dependencies and draws the graph. Nothing has run. This is the moment to edit a heading and watch the graph change.
4. **Inspect a task.** Click a node. The task as written, its steps, constraints, and acceptance criteria. The plan is legible before it moves.
5. **Start the run.** Four agents spawn, the Architect claims the first task, the graph comes alive, the log streams.
6. **Parallel work.** ETL and the dashboard draft overlap where the graph allows. Artifacts appear as real files.
7. **Something breaks.** The ETL agent hits a genuine Polars exception on real malformed timestamps, diagnoses it, picks a recovery strategy, retries, succeeds. The most persuasive moment in the demo. Not optional.
8. **The solution lands, and it is alive.** The dashboard takes the screen. Then brush three months on the time axis and watch every figure recompute. That is the moment the room stops wondering whether it is a picture.

Target run length at 1x: 3 to 4 minutes. Speed control offers 1x, 2x, 5x.

## Functional requirements

**FR1 Requirement intake.** Pick a bundled requirement file or paste Markdown. The source document is displayed as written.

**FR2 Plan derivation.** Parse per the rules in `02-ARCHITECTURE.md`. Show phases, tasks, owners, dependencies. Report parse problems inline rather than failing silently.

**FR3 Run control.** Start, pause, resume, cancel, reset. Speed 1x, 2x, 5x. A settable seed that guarantees an identical run when reused.

**FR4 Live visualisation.** Interactive task graph with per-node status, click-to-inspect, hover dependency tracing, pan and zoom. Agent cards with current task and rolling activity. Whole-run progress.

**FR5 Log stream.** Append-only, timestamped, agent-attributed, level-coloured. Filter by agent and level. Autoscroll with release on manual scroll. Copy all.

**FR6 Artifacts.** Files appear as produced. Code artifacts open highlighted. Dataset artifacts open as a paged preview with real row and column counts.

**FR7 Solution delivery.** On completion the dashboard becomes the primary surface: five headline figures, revenue over time, revenue by category, revenue by region, top products. Every value computed at run time.

**FR8 Cross-filter.** Brushing the time axis or clicking a category or region re-queries the backend, which re-aggregates in Polars and returns fresh figures. No client-side filtering.

**FR9 Stream recovery.** A page refresh mid-run replays the run from `seq=0` and rejoins live. Nothing is lost.

**FR10 Re-run.** Reset returns to the plan view with run state cleared. The same seed reproduces the run exactly.

## Non-functional requirements

- Served as one process from `uvicorn` on localhost. No deployment, no container, no external network dependency during the demo.
- Cold start of the first run under 2 seconds, including CSV read. Pre-warm once before the demo.
- The log stream must not drop frames. Events batched per animation frame, render window capped at 500 lines.
- Cross-filter query round trip under 150ms.
- Works at 1440x900 and above. Below 1100 the artifacts column collapses into a tab. Mobile is not a target.
- Visible keyboard focus throughout. `prefers-reduced-motion` respected.
- No server exception and no browser console error during a full run.

## Out of scope

- Authentication, accounts, multi-user
- Persistence beyond the in-memory run registry. No database, no run history across restarts.
- Arbitrary file upload. Two curated requirement files plus a paste box.
- Requirement domains beyond tabular ETL, analytics, and dashboards
- More than four agents
- Agent-to-agent negotiation, replanning, or tool use beyond the scripted runtime
- Exporting the generated project as a downloadable repository
- Theming, light mode, i18n
- Hosted deployment. The demo runs on the presenting laptop.

## Success criteria

1. A stakeholder watching a full run without narration can describe what happened.
2. An engineer who edits the requirements file sees the plan change accordingly.
3. An engineer who opens a code artifact finds code that plausibly produced the dashboard numbers, because it did.
4. An engineer who cross-filters the dashboard sees every figure move consistently, because Polars recomputed them.
5. Replacing `SimulatedRunner` with an LLM-backed runner requires no change to the orchestrator, the API, or the frontend.
