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
    set((state) => ({ run: applyEvents(state.run, events) }));
  },
  reset: () => set({ run: initialState() }),
}));
