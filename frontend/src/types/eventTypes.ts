/**
 * GENERATED FILE. DO NOT EDIT.
 *
 * Generated from backend/app/core/types.py, which is authoritative for the
 * event contract. See docs/03-EVENT-CONTRACT.md.
 *
 * Regenerate with:  make types
 */

import type { SeedEvent } from "./events.ts";

/** Every event name on the wire. Used to attach EventSource listeners. */
export const EVENT_TYPES: readonly SeedEvent["type"][] = [
  "agent.idle",
  "agent.spawned",
  "artifact.chunk",
  "artifact.created",
  "artifact.streaming",
  "log.emitted",
  "plan.built",
  "run.completed",
  "run.failed",
  "run.started",
  "task.completed",
  "task.failed",
  "task.progress",
  "task.ready",
  "task.retried",
  "task.started",
];
