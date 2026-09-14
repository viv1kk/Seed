# frontend/CLAUDE.md

Rules for this tree. Loads when you work in `frontend/`.

- This is a renderer. It may hold view state: selection, filters, zoom, scroll position, autoscroll pinning. It may not compute a metric, derive a task status, decide what happens next, or filter data locally.
- Dashboard filtering goes to `POST /api/runs/{id}/query`. Never filter an AggBundle client side.
- `src/types/events.ts` is generated from the backend schema. Never hand-edit it. Regenerate with `npm run gen:types`.
- Apply SSE events in a `requestAnimationFrame`-batched flush, not one store write per event.
- Subscribe narrowly: logs in their own slice with a 500-line render window, graph nodes per task id, agent cards per agent id. A log append must not re-render the graph.
- The event switch ends in `default: assertNever(event)` so a new backend event fails this build.
- The plan graph is custom SVG with dagre layout. No React Flow.
- Code highlighting arrives as HTML from the API. No client-side highlighter.
- No em dashes in user-facing strings. Exact copy is in docs/06-UI-SPEC.md.
