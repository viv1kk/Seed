# backend/CLAUDE.md

Rules for this tree. Loads when you work in `backend/`.

- All project logic lives here. If a rule, calculation, or decision is being written in TypeScript, it belongs in this tree instead.
- `app/pipeline/` is pure. It imports nothing from `app/runners/`, `app/orchestrator/`, or `app/api/`, and it has no knowledge that a simulation exists. Every returned number is measured, never assumed.
- Every `pl.DataFrame.group_by` passes `maintain_order=True`, or runs stop being reproducible.
- Randomness comes from `app/core/rng.py` only. Bare `random.` and `numpy.random` are banned.
- Runners never call `asyncio.sleep` directly. Use `ctx.clock.sleep(ms)` so speed, pause, and cancel work.
- Let `asyncio.CancelledError` propagate. Never swallow it in a runner or a kernel call.
- The strict timestamp parse in `pipeline/clean.py` is supposed to raise. Do not add a pre-check, a try/except inside the pipeline, or a flag that avoids it. The runner catches it.
- The static files mount in `main.py` goes after every router, or it swallows `/api`.
- mypy strict, no `Any`. Pydantic models for anything crossing a boundary.
