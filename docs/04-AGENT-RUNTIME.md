# 04. Agent Runtime

How `SimulatedRunner` behaves. This is the difference between a convincing run and a progress bar.

## Roster

Four agents. No more.

| id | Display name | Capability keywords | Produces |
|---|---|---|---|
| `architect` | Architect | plan, design, schema, contract, review, verify | design docs, schema contract, verification note |
| `etl` | ETL Engineer | ingest, extract, load, clean, source, csv, quality | loader and cleaner code, cleaned dataset |
| `analytics` | Analytics Engineer | transform, join, aggregate, metric, model, kpi | transform code, aggregate tables |
| `dashboard` | Dashboard Engineer | dashboard, chart, visual, report, ui | chart spec, the dashboard artifact |

Each carries a one-line self-description for its card, in its own voice, short and free of marketing language.

## Log voice

Three sources, interleaved. The mix is what sells it.

**1. Reasoning (`source="agent"`, level `info`).** First person, present tense, specific to the task, templated from that task's own steps and constraints.

```
Architect      Reading requirement. 3 phases, 7 tasks, 4 with explicit constraints.
ETL Engineer   Task 2.1. Sources listed: orders.csv, products.csv, customers.csv.
ETL Engineer   Profiling orders.csv before I commit to a schema.
Analytics Eng  Joining orders to products on sku. Expecting 1:1, will verify.
```

**2. Runtime (`source="runtime"`, level `debug`).** Machine voice carrying real numbers from the kernel.

```
[kernel] read_csv: orders.csv 12,847 rows, 10 columns, 61ms
[kernel] profile: order_ts -> 2 distinct formats detected
[kernel] clean: dropped 19 duplicate order_id, coerced 1,203 qty values
[kernel] aggregate: revenue_by_category 8 groups, 4ms
```

**3. Outcome (`success`, `warn`, `error`).** Short, factual, tied to a metric.

```
ETL Engineer   Clean pass complete. 12,828 rows retained, 0.15% dropped.
Analytics Eng  Margin computed for 12,828 rows. Median 34.2%.
```

Rules:
- Roughly every fifth line carries a number that came from the kernel.
- No line may carry a number that did not.
- No emoji, no exclamation marks, no "Let me" or "I'll go ahead and".
- Vary line length. A stream of same-length lines reads as generated.
- Fixed-width agent column. Timestamp `mm:ss.mmm` from run start.

Polars timings are genuinely fast, often single-digit milliseconds. Report them honestly. Real numbers that happen to be small are more convincing than inflated ones, and an engineer in the room will recognise Polars timings as plausible.

## Timing model

```python
task_duration = real_work_ms + narration_ms
narration_ms  = sum(base_step_ms * rng.uniform(0.6, 1.6) for step in task.steps)
```

`base_step_ms` varies by agent, because uniform pacing is the loudest tell:

| Agent | base ms per step | character |
|---|---|---|
| architect | 900 | fast, decisive, short tasks |
| etl | 2200 | slowest, most log volume |
| analytics | 1400 | medium, bursty |
| dashboard | 1100 | fast, many small artifacts |

Lines within a step are spaced `rng.uniform(0.12, 0.9)` seconds. On about 10% of steps, seeded, insert a longer pause of 1.5 to 3 seconds before a line, as if the agent is thinking. That pause does more for realism than any animation.

All waits go through `clock.sleep(ms)`, which divides by the speed multiplier, waits on the pause event, and propagates cancellation. Never `asyncio.sleep` directly inside a runner.

## The failure and recovery beat

The centrepiece. Task **2.1, ETL Engineer, "Ingest and clean the order data"**, driven by real data and a real exception.

```python
try:
    result = kernel.clean(df, CleanStrategy(timestamp="iso-strict", ...))
except pl.exceptions.InvalidOperationError as exc:
    probe = kernel.profile(df)                   # real failing count and real samples
    yield log(...); yield task_failed(...); yield task_retried(...)
    result = kernel.clean(df, CleanStrategy(timestamp="multi-format-day-first", ...))
```

Sequence on screen:

```
ETL Engineer   Parsing order_ts as ISO 8601.
[kernel]       clean: strict parse raised InvalidOperationError
[kernel]       probe: 771 of 12,847 values unparseable under %Y-%m-%dT%H:%M:%S
ETL Engineer   That is 6% of the file, too many to drop. Inspecting the failures.
[kernel]       sample: "14/03/2025 09:22", "02/11/2025 17:41", "29/07/2025 08:03"
ETL Engineer   Second format present. Day-first, not month-first: 29 in position one rules out US ordering.
task.failed    recoverable, reason "order_ts: mixed timestamp formats"
task.retried   attempt 2, strategy "multi-format parse with day-first fallback"
ETL Engineer   Retrying with a coalesced two-format parse.
[kernel]       clean: 12,847 of 12,847 timestamps resolved
ETL Engineer   Clean. Moving on.
```

The exception is real. The failing count and the samples come from a real probe. The second `clean` call genuinely succeeds. The only scripted part is the sentence about day-first ordering, which narrates a detection that actually happened.

The samples must be pulled from the real failing rows, not written into the script. Someone will check them against the CSV.

UI behaviour during the beat:
- The task node goes to the fault colour and holds for a beat before flipping to `retrying`.
- If the user has a log filter active that would hide these lines, show a nudge in the filter bar rather than silently swallowing the moment.
- The ETL agent card shows `attempt 2 of 3`.
- The graph auto-focuses the failing node if it is outside the viewport.

## Script structure

One module per agent under `runners/scripts/`. A script maps a task id to an ordered list of beats.

```python
Beat = Say | Work | Emit | Pause

@dataclass
class Say:
    level: LogLevel
    text: Callable[[BeatCtx], str]

@dataclass
class Work:
    step_id: str
    call: Callable[[WorkKernel, BeatCtx], Awaitable[object]]

@dataclass
class Emit:
    build: Callable[[BeatCtx], Artifact]
```

`Say.text` is a callable so it can quote real numbers from prior `Work` results. **Any `Say` returning a fixed string containing a digit is a defect.**

Scripts degrade gracefully. An unrecognised task falls back to a generic beat sequence built from the task's own steps and constraints, over the bundled dataset. The demo files have specific scripts. An edited or pasted file must still run.
