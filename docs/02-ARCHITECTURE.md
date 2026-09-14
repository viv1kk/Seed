# 02. Architecture

## Shape

```
requirements.md
      |
      v  POST /api/plans
 [ Parser ]  -> Plan (task graph)
      |
      v  POST /api/runs
 [ Orchestrator ]  asyncio, Semaphore(2), dependency gating
      |
      | await runner.run(task, ctx)
      v
 [ AgentRunner ]  <== the only simulated component
      |  yields SeedEvent
      |  awaits real work from WorkKernel
      v
 [ EventBus ]  asyncio.Queue per run, assigns seq
      |
      v  GET /api/runs/{id}/stream   (text/event-stream)
 [ EventSource ] -> [ Zustand store ] -> [ React ]
                                 ^
 [ WorkKernel ] --- Polars. Artifacts, metrics. ---+
```

One direction. The frontend never computes; it only draws what arrives.

## Repository layout

```
seed/
  CLAUDE.md  README.md  Makefile  docs/  examples/
  backend/
    CLAUDE.md
    pyproject.toml
    app/
      main.py               # FastAPI app, routers, static mount (mounted LAST)
      api/
        plans.py  runs.py  artifacts.py  examples.py
        deps.py             # RunRegistry dependency
      core/
        types.py            # Pydantic models. The frozen contract.
        events.py           # EventBus: asyncio.Queue, seq assignment, fan-in
        rng.py              # the only randomness in the project
        clock.py            # speed-aware sleep, pause Event, cancellation
        registry.py         # in-memory run registry, no persistence
      parser/
        lexer.py            # markdown-it-py token stream
        rules.py            # heading levels, Agent:, Depends on:
        build_plan.py       # tokens -> Plan, topological sort, cycle detection
      orchestrator/
        orchestrator.py     # the scheduling loop
        scheduler.py        # ready-set computation over the DAG
      runners/
        base.py             # AgentRunner ABC, AgentContext, shared helpers
        simulated.py        # THE stub
        scripts/            # one module per agent
      pipeline/             # REAL WORK. Pure. Imports nothing from runners/ or api/.
        load.py  profile.py  clean.py  transform.py  aggregate.py
        kernel.py           # WorkKernel facade
        highlight.py        # Pygments, source -> HTML
      data/                 # generated CSVs, committed
    scripts/generate_data.py
    tests/
  frontend/
    CLAUDE.md
    src/
      api/                  # fetch wrappers, EventSource subscription
      types/events.ts       # GENERATED. Never hand-edited.
      state/                # Zustand store, event application, selectors
      ui/
        shell/  graph/  agents/  logs/  artifacts/  dashboard/  primitives/
```

## API surface

Small on purpose.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/examples` | Bundled requirement files, id and title |
| `POST` | `/api/plans` | Body `{markdown}` or `{example_id}`. Returns `Plan` or parse errors. |
| `POST` | `/api/runs` | Body `{plan_id, seed, speed}`. Returns `{run_id}`. Does not start streaming. |
| `GET` | `/api/runs/{id}/stream` | SSE. Replays from `seq=0` so a reconnect loses nothing. |
| `POST` | `/api/runs/{id}/control` | Body `{action: pause\|resume\|cancel\|speed, value?}` |
| `GET` | `/api/artifacts/{id}` | Artifact body. Code artifacts return Pygments HTML. |
| `POST` | `/api/runs/{id}/query` | Cross-filter. Body `{date_from?, date_to?, category?, region?}`. Re-runs the aggregations in Polars and returns a fresh `AggBundle`. |

That last endpoint matters more than it looks. It is what makes the delivered dashboard a live surface over the pipeline rather than a picture of one. See `05-DATA-AND-PIPELINE.md`.

**Static mount goes last** in `main.py`, after every router, or it will swallow `/api`.

## Parser rules

Authoritative. Implement exactly these.

| Markdown | Meaning |
|---|---|
| `# Heading` | Requirement title |
| `## Heading` | Phase, numbered in document order from 1 |
| `### Heading` | Task in the current phase. Id is `phase.task`, e.g. `2.1`. |
| `Agent: <name>` line in a task | Owning agent, matched case-insensitively against the roster in `04-AGENT-RUNTIME.md` |
| `Depends on: 1.2, 1.3` line in a task | Dependency ids, comma separated |
| `- bullet` in a task | A step. Drives progress granularity and log narration. |
| Fenced code block in a task | Technical constraint, language tag preserved |
| `> blockquote` in a task | Acceptance criterion, echoed at completion and restated in the verification artifact |

- No `Agent:` line means assignment by keyword match against agent capability keywords. Still ambiguous means Architect, plus a parse warning.
- No `Depends on:` line means an implicit dependency on all tasks in the previous phase.
- An unknown dependency id is a parse error. Return it, refuse to run.
- A cycle is a parse error, caught by the topological sort at parse time.
- Content outside any `##` is prose. Ignored for planning, still returned for display.

The plan is fully derived from the document and from nothing else.

## Orchestrator

A loop over a ready set, not a timeline.

```python
async def execute(self) -> None:
    while self.has_incomplete_tasks():
        ready = self.scheduler.ready_set()          # deps all completed
        if not ready and not self.running:
            await self.fail("deadlock")
            return
        for task in ready[: self.free_slots()]:
            self.start(task)                        # asyncio.Task draining a runner
        event = await self.inbox.get()              # fan-in from all running runners
        await self.bus.publish(event)
        self.apply_terminal(event)
```

`MAX_PARALLEL = 2`. Two agents working at once reads as parallel. Four reads as noise.

Fan-in: each runner's async generator is drained by its own `asyncio.Task` that puts events on a shared `asyncio.Queue`. Do not try to merge generators directly.

Pause, resume, and cancel live in `core/clock.py` and are observed at every `await clock.sleep()`. Cancel raises `asyncio.CancelledError` into the runner, which must let it propagate. Cancellation leaves the registry in a clean, resettable state.

## AgentRunner, the swap seam

```python
@dataclass(frozen=True)
class AgentContext:
    run_id: str
    plan: Plan
    artifacts: Mapping[str, Artifact]   # outputs of completed tasks
    kernel: WorkKernel                  # real work
    clock: Clock                        # speed-aware sleep, pause, cancel
    rng: random.Random                  # seeded

class AgentRunner(ABC):
    agent_id: AgentId

    @abstractmethod
    def run(self, task: Task, ctx: AgentContext) -> AsyncIterator[SeedEvent]: ...
```

`SimulatedRunner` yields narration around real `kernel` calls. A future `LlmRunner` yields narration derived from streamed model output around real tool calls. The orchestrator, the event bus, the API, and the entire frontend are identical in both cases.

When API access arrives:
1. Add `runners/llm.py`.
2. Add a runner-selection setting.
3. Nothing else.

Write the code so that claim is true, because it will be made to the client.

## Why the work is real

`backend/app/pipeline/` is an ordinary Polars pipeline with no knowledge that a simulation exists.

```python
class WorkKernel(Protocol):
    def load_csv(self, name: str) -> LoadResult: ...
    def profile(self, df: pl.DataFrame) -> ProfileResult: ...
    def clean(self, df: pl.DataFrame, strategy: CleanStrategy) -> CleanResult: ...
    def join(self, left: pl.DataFrame, right: pl.DataFrame, on: str) -> JoinResult: ...
    def derive(self, df: pl.DataFrame) -> DeriveResult: ...
    def aggregate(self, df: pl.DataFrame, filters: Filters | None = None) -> AggBundle: ...
    def emit_artifact(self, artifact: Artifact) -> None: ...
```

Every metric in a log line or on the dashboard comes from one of these return values. Writing a number into a string literal is a mistake.

## Frontend state

`EventSource` receives events, they are applied to a Zustand store, components subscribe to slices.

Two performance requirements, not niceties:

**Batch the appends.** SSE can deliver several events per frame. Accumulate incoming events in a ref and flush to the store on `requestAnimationFrame`. Applying each event synchronously means hundreds of renders a minute and a visibly stuttering log.

**Subscribe narrowly.** Logs in their own slice with a 500-line render window. Graph nodes subscribe per task id. Agent cards subscribe per agent id. A log append must not re-render the graph.

The store applies events with a `switch` over `event.type` and a `default: assertNever(event)`, so a new backend event fails the frontend build until it is handled.

## Generated types

The contract is defined once, in Python.

```bash
uv run python -m scripts.export_schema > frontend/src/types/events.schema.json
npm --prefix frontend run gen:types    # json-schema-to-typescript
```

`frontend/src/types/events.ts` is generated output. It is committed, it is never hand-edited, and `make demo` regenerates it. If the backend and frontend disagree about the contract, that is now a build failure rather than a runtime surprise.
