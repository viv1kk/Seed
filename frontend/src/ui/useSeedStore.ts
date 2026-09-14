/**
 * The React binding for the vanilla store in src/state.
 *
 * This lives in src/ui because it is the only place React and the store meet,
 * and frontend/CLAUDE.md keeps React imports out of src/state.
 *
 * Always pass a selector. Subscribing to the whole store re-renders every
 * component on every event, which is exactly the failure the batching in
 * src/state/store.ts exists to avoid.
 */
import { useStore } from "zustand";

import { seedStore, type SeedStore } from "../state/store.ts";

export function useSeedStore<T>(selector: (state: SeedStore) => T): T {
  return useStore(seedStore, selector);
}
