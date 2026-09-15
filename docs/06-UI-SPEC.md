# 06. UI Specification

The frontend is a renderer, but it is the reason the demo lands. Everything here is presentation and interaction. Nothing here computes.

## Design direction: the plan room

The product turns a written specification into a built thing, which is what architectural drawing has always done. The console borrows from the drawing office, not the developer terminal.

The run surface is a **cyanotype ground**: deep drawing-blue with chalk-white line work. Status is expressed the way a drawing expresses it. Planned work is drawn in dashed outline. Work in progress is solid stroke in survey amber. Completed work is filled. Faulted work is struck through in red before it is redrawn.

Then the payoff. On completion the dashboard arrives on **paper white**, full colour, and takes the screen. The environment is the drawing office. The deliverable is the finished print. One orchestrated transition carries the whole demo narrative.

**Why not the obvious direction.** The default for "AI agents running a pipeline" is near-black with an acid green accent and monospace everywhere. It is the aesthetic of every terminal screenshot and it is where this brief lands if nobody decides otherwise. Cyanotype is a specific, older reference matching what the product does, and it gives the ending somewhere to go: dark to light, draft to print. That contrast is unavailable if the console is already black.

Monospace stays where it is functionally correct: the log stream, code artifacts, and numeric table columns. Not UI labels.

### Tokens

```css
--ink-900: #0A2138;   /* ground */
--ink-800: #123049;   /* panels */
--ink-600: #26485F;   /* rules, borders, dashed outlines */
--chalk:   #E9EFF3;   /* primary text, line work */
--chalk-dim: #8FA7B8; /* secondary text */

--signal: #F0A63F;    /* running */
--verify: #72BE95;    /* completed */
--fault:  #DD6257;    /* failed */

--paper:     #F8F7F3;
--paper-ink: #1A2230;
```

Chart series on paper: a five-step ramp from the ink blue through to a warm ochre, so the dashboard reads as a relative of the console. No rainbow default palette.

### Type

- **Archivo** (variable) for all interface text. Drafting lettering is narrow and even-weight. Use the width axis: condensed for graph node labels and panel headers, normal for body.
- **IBM Plex Mono** for the log stream, code artifacts, and numeric table columns only.

| Role | Size / line-height | Weight |
|---|---|---|
| Run title | 28 / 32 | 500 |
| Panel header | 13 / 16 | 600, normal case |
| Node label | 14 / 18 | 500, condensed |
| Body | 15 / 22 | 400 |
| Secondary | 13 / 18 | 400 |
| Log line | 12.5 / 19 mono | 400 |
| Headline numeral | 44 / 44, tabular figures | 500 |

No all-caps labels. No tracked-out eyebrows above headings. Sentence case throughout.

## Layout

Three columns at 1440. Below 1100 the artifacts column becomes a tab beside the log.

```
+---------------------------------------------------------------------------+
|  Seed            retail-analytics.md          [Simulation]  seed 4471      |
|                                          [1x 2x 5x]  [Pause]  [Reset]      |
+----------------+--------------------------------------+-------------------+
|  REQUIREMENT   |          PLAN                        |   AGENTS          |
|                |                                      |                   |
|  # Retail      |   Phase 1  Design                    |  [Architect  ]    |
|  analytics     |    (1.1)--+                          |   working 1.1     |
|  platform      |           |                          |   "Reading req..."|
|                |    (1.2)--+---+                      |                   |
|  ## Phase 1    |               |                      |  [ETL Engineer]   |
|  ### 1.1 ...   |   Phase 2  Build                     |   idle            |
|  Agent: Arch.. |    (2.1)      (2.2)                   |                   |
|  - step        |       \        /                      |  [Analytics   ]   |
|  - step        |      (2.3)    /                       |   idle            |
|                |         \    /                        |                   |
|  > acceptance  |   Phase 3  Deliver                   |  [Dashboard   ]   |
|                |          (3.1)                        |   idle            |
|  ## Phase 2    |            |                          |                   |
|  ...           |          (3.2)                        |  ARTIFACTS        |
|                |                                      |  design/          |
|                |   [fit] [zoom -] [zoom +]            |  pipeline/        |
|                +--------------------------------------+   load.py         |
|                |  LOG            [all agents v] [all] |   clean.py        |
|                |  00:12.480 ETL      Profiling ord...  |                   |
|                |  00:12.541 [kernel] 12,847 rows, 6..  |                   |
+----------------+--------------------------------------+-------------------+
```

On `run.completed`, the requirement and log columns recede and the dashboard occupies the rest.

Left-aligned throughout. Numerics right-aligned with tabular figures.

## The plan graph

The single most interactive surface, and the thing that proves the environment reads the document.

**Layout.** `dagre` computes node positions from the DAG. Render as custom SVG, not a graph library. React Flow would fight the drawing aesthetic, and for 7 to 15 nodes its pan, zoom, and minimap are not worth the weight. If a requirement file ever produces more than about 25 nodes, revisit.

Phases are horizontal bands with a hairline rule and the phase name set in the left margin. Dagre ranks within the band.

**Node states.**

| Status | Treatment |
|---|---|
| pending | 1px dashed `--ink-600` outline, `--chalk-dim` label |
| ready | solid `--ink-600` outline |
| running | 2px `--signal` stroke, slow animating dash offset |
| retrying | 2px `--signal` stroke, `attempt n` badge |
| completed | filled `--ink-800`, `--verify` left rule |
| failed | `--fault` stroke, label struck through |

Nodes show id, title, owning agent initial, and a thin step-progress rule along the bottom edge driven by `task.progress`.

**Edges.** Orthogonal connectors, chalk at 40%. An edge brightens to `--signal` when its source completes and its target becomes ready.

**Interaction.** This is where React earns its place.

- **Click a node** to open an inspector over the requirement column: the task as written in the source document, its steps with per-step status, its constraints, its acceptance criteria, its metrics once complete, its artifacts, and the log filtered to that task alone. This one panel answers almost every question a client asks mid-run.
- **Hover a node** to trace its dependency path. Ancestors highlight in `--chalk` at 70%, descendants in `--signal` at 50%, everything else drops to 25%. Reading a DAG is hard, and this makes it readable in a second.
- **Pan and zoom.** Wheel to zoom about the cursor, drag to pan, `Fit` button to reset. Zoom clamped 0.5x to 2.5x.
- **Auto-focus.** When a task fails, pan the failing node into view if it is outside the viewport. Do not auto-pan for any other reason, it is disorienting.
- **Keyboard.** Arrow keys move selection along edges, Enter opens the inspector, Escape closes it.

## Other panels

**Agent card.** Name, one-line role, current task id, and a rolling activity line showing that agent's most recent message truncated to one line. A 2px amber rule on the left edge while working. Idle cards at 60% opacity. During the retry, `attempt 2 of 3` beside the task id. Clicking a card filters the log to that agent.

**Log stream.** Fixed columns: timestamp, agent, message. `[kernel]` lines in `--chalk-dim`. Levels tint the message text, not the row background. Autoscroll pinned to bottom, released on manual scroll up, with a "Jump to latest" affordance that appears only when released. Filter by agent and by level. Copy all.

Two performance requirements. Batch incoming events through a `requestAnimationFrame` flush rather than applying each one synchronously. Cap the rendered window at 500 lines with the rest retained in state. Both are specified in `02-ARCHITECTURE.md` and both are load-bearing at 200 lines per minute.

**Artifacts panel.** File tree grouped by folder. New rows flash amber for 400ms and nothing else. Clicking opens a viewer over the centre column: code artifacts as the Pygments HTML from the API with a line count, datasets as a 20-row preview with real row and column counts, docs rendered as Markdown.

**Controls.** Speed as a segmented control. Pause and Resume as one button swapping label and action. Reset. Seed field editable only while idle.

**Simulation badge.** Top right, always present, `--chalk-dim` on `--ink-800`, no icon. Tooltip: "Agent reasoning is scripted. The pipeline and all figures are computed from real data."

## The dashboard

Not a static payoff. It is a live surface over the pipeline, and that is the point.

Five headline figures, a weekly revenue area chart with order count on a secondary axis, revenue by category sorted with margin visible, revenue by region with share of total, and a top ten products table.

**Cross-filtering.** Every filter interaction issues `POST /api/runs/{id}/query` and re-renders from the response. The frontend never filters locally.

- **Brush the time axis** on the revenue chart. All five surfaces recompute for that window.
- **Click a category bar.** Region, time, and top products recompute for that category. The bar takes a selected treatment.
- **Click a region bar.** Same, for region.
- **Active filters** appear as removable chips above the headline figures. A "Clear filters" action resets.
- While a query is in flight, dim the affected surfaces to 60% rather than showing spinners. Queries take single-digit milliseconds and a spinner would flash.

This is the strongest available answer to "is that just a picture." Someone brushes three months and every number moves, because Polars just recomputed them. Protect this in the schedule.

## Motion

One orchestrated moment.

The completion transition: the console dims 30% over 250ms, the dashboard wipes up from the bottom edge over 400ms on an ease-out curve, and the headline numerals count from zero to their real values over 600ms staggered by 60ms. Nothing else animates during it.

Everything else is small and functional:
- Node state changes cross-fade over 150ms.
- The running node's dash offset animates continuously. This is the only ambient motion on the page and it exists to mark the live task.
- Dependency path highlighting transitions over 120ms.
- Log lines append with no animation. Animated log lines look fake and cost frames.
- New artifact rows flash amber for 400ms.
- Cross-filter re-renders cross-fade over 180ms. Charts should not re-animate from zero on every filter, which reads as a reload.

`prefers-reduced-motion: reduce` disables the dash animation, the numeral count-up, the wipe (replaced with a 150ms fade), and the cross-filter cross-fade. States still change, instantly.

## Copy

Exact strings. Sentence case, active voice, no em dashes.

The intake surface carries the empty state, the bundled examples, and the
box a person pastes or opens their own document into. FR1 in `01-PRD.md`
is "pick a bundled requirement file or paste Markdown", and the examples
exist to open the demo on something known rather than to be the only way
in. Opening a local file reads it into the same box and sends the same
`{markdown}` body; nothing is uploaded, so "arbitrary file upload" stays
out of scope as the PRD says.

Most documents somebody writes will not describe a revenue aggregate, so a
completed run with no analytical table is an ordinary outcome and says so
rather than reading as a failure.

| Location | String |
|---|---|
| Empty state heading | `Load a requirement to begin` |
| Empty state body | `Seed reads a Markdown requirements file, plans the work, and builds it. Pick one of the examples or paste your own.` |
| Primary action, idle | `Build the plan` |
| Primary action, planned | `Start the run` |
| Running | `Pause` / `Resume` |
| Reset | `Reset` |
| Plan warning banner | `{n} tasks had no agent assigned. Seed inferred an owner from the task text.` |
| Parse error banner | `Task {id} depends on {ref}, which does not exist. Fix the requirement and build the plan again.` |
| Cycle error | `Tasks {ids} depend on each other in a loop. Seed cannot order the work. Remove one of the Depends on references to break it.` |
| Connection lost | `Lost the event stream. Reconnecting.` |
| Log empty | `The log fills as agents work.` |
| Artifacts empty | `Files appear here as agents produce them.` |
| Filter hides the retry | `The ETL Engineer is recovering from a failure. Clear the filter to watch.` |
| Node inspector, no logs yet | `This task has not started.` |
| Run complete | `Built in {duration}. {n} artifacts, {rows} rows processed.` |
| Run failed | `The run stopped at task {id}. {reason}` |
| Filter chips | `Clear filters` |
| Simulation tooltip | `Agent reasoning is scripted. The pipeline and all figures are computed from real data.` |

## Accessibility floor

Focus rings in `--signal` on every interactive element. The log is `aria-live="polite"` but announces only `error` and `success` lines, otherwise it is unusable with a screen reader. Task nodes are buttons with an accessible name of `{id} {title}, {status}`. The graph has a keyboard path. All text meets 4.5:1 against its background, including `--chalk-dim` on `--ink-900`, verified rather than assumed.
