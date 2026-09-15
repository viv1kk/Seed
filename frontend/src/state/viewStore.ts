/**
 * View state: what the person looking at the screen has chosen.
 *
 * Selection, filters, and which file is open. None of it is derived from a
 * calculation and none of it decides anything about the run; it is the same
 * kind of state as a scroll position, which frontend/CLAUDE.md allows here.
 * The run's own state lives in store.ts and arrives entirely as events.
 *
 * It is a store rather than props because the pieces that share it are far
 * apart in the tree: clicking an agent card filters the log, clicking a node
 * opens the inspector over the requirement column, and a stream opening in the
 * artifacts panel opens the viewer over the centre column.
 */

import { createStore } from "zustand/vanilla";

import type { AgentId, LogLevel } from "../types/events.ts";

export type AgentFilter = AgentId | "all";
export type LevelFilter = LogLevel | "all";

export interface ViewState {
  /** The task whose inspector is open. */
  selectedTaskId: string | null;
  /** The task under the cursor, which traces its dependency path. */
  hoveredTaskId: string | null;
  logAgent: AgentFilter;
  logLevel: LevelFilter;
  /** The artifact open in the viewer. */
  openArtifactId: string | null;
  /**
   * True when the viewer opened itself because a runner started writing, rather
   * than because someone clicked. Only an automatic one closes itself again.
   */
  artifactAutoOpened: boolean;
  /** True once the person has scrolled the log up, releasing autoscroll. */
  logReleased: boolean;
}

export interface ViewStore extends ViewState {
  selectTask: (taskId: string | null) => void;
  hoverTask: (taskId: string | null) => void;
  setLogAgent: (agent: AgentFilter) => void;
  setLogLevel: (level: LevelFilter) => void;
  clearLogFilters: () => void;
  openArtifact: (artifactId: string | null, auto?: boolean) => void;
  setLogReleased: (released: boolean) => void;
  /** Back to a clean console. Called by Reset and by building a new plan. */
  reset: () => void;
}

const EMPTY: ViewState = {
  selectedTaskId: null,
  hoveredTaskId: null,
  logAgent: "all",
  logLevel: "all",
  openArtifactId: null,
  artifactAutoOpened: false,
  logReleased: false,
};

export const viewStore = createStore<ViewStore>()((set) => ({
  ...EMPTY,
  selectTask: (selectedTaskId) => set({ selectedTaskId }),
  hoverTask: (hoveredTaskId) => set({ hoveredTaskId }),
  setLogAgent: (logAgent) => set({ logAgent }),
  setLogLevel: (logLevel) => set({ logLevel }),
  clearLogFilters: () => set({ logAgent: "all", logLevel: "all" }),
  openArtifact: (openArtifactId, auto = false) =>
    set({ openArtifactId, artifactAutoOpened: openArtifactId !== null && auto }),
  setLogReleased: (logReleased) => set({ logReleased }),
  reset: () => set({ ...EMPTY }),
}));
