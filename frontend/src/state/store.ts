/**
 * The Zustand store.
 *
 * Built on `zustand/vanilla` rather than `zustand`, for two reasons. The React
 * binding pulls React in, and frontend/CLAUDE.md keeps React imports inside
 * src/ui. And a vanilla store can be driven directly by `node --test`, which is
 * what lets the parity test exercise the real store rather than a stand-in for
 * it. The React hook lives in src/ui/useSeedStore.ts.
 *
 * `applyEvents` takes a batch, never a single event. SSE delivers several
 * events per frame during a busy stretch of a run, and one store write per
 * event means hundreds of renders a minute and a log that visibly stutters. The
 * subscription accumulates into a ref and flushes here on requestAnimationFrame
 * (phase 2). Keeping the signature batch-only makes the wrong thing awkward to
 * write.
 */

import { createStore } from "zustand/vanilla";

import type { SeedEvent } from "../types/events.ts";
import { applyEvents } from "./applyEvent.ts";
import { initialState, type RunState } from "./runState.ts";

export interface SeedStore {
  run: RunState;
  /** Fold a batch of events into the run state. */
  applyEvents: (events: readonly SeedEvent[]) => void;
  /** Return to the pre-run state. Used by the Reset control. */
  reset: () => void;
}

export const seedStore = createStore<SeedStore>()((set) => ({
  run: initialState(),
  applyEvents: (events) => {
    if (events.length === 0) return;
    set((state) => {
      // Drop anything already applied.
      //
      // Every connection to a run replays it from seq 0, and there can be more
      // than one: EventSource reconnects on its own, and React remounts effects
      // in development. Without this the log silently doubles, which showed up
      // first as duplicate React keys. `seq` is monotonic per run (contract rule
      // 1), so the last one applied is all that has to be remembered.
      //
      // This is idempotency on a replayable stream, not a decision about the
      // run. The reducer itself stays a plain fold, which is what keeps it
      // checkable against the Python one.
      const fresh = events.filter((event) => event.seq > state.run.lastSeq);
      if (fresh.length === 0) return state;
      return { run: applyEvents(state.run, fresh) };
    });
  },
  reset: () => set({ run: initialState() }),
}));
