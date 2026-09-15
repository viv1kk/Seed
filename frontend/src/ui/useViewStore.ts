/**
 * The React binding for the view store. See useSeedStore.ts for why the
 * bindings live in src/ui and the stores do not.
 *
 * Always pass a selector, and make it narrow. A graph node that subscribes to
 * the whole view store re-renders on every keystroke in the log filter.
 */
import { useStore } from "zustand";

import { viewStore, type ViewStore } from "../state/viewStore.ts";

export function useViewStore<T>(selector: (state: ViewStore) => T): T {
  return useStore(viewStore, selector);
}

/** The actions, which never change, for components that only dispatch. */
export function viewActions(): ViewStore {
  return viewStore.getState();
}
