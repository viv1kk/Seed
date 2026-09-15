/**
 * Presentation constants and formatters. No React, no decisions.
 *
 * Formatting is the one kind of computation this tree is allowed to do, because
 * it is presentation: the same number rendered for a person to read. Anything
 * that changes *which* number appears belongs in the backend.
 *
 * Indian numbering and INR throughout, per docs/05-DATA-AND-PIPELINE.md.
 */

import type { AgentId, LogLevel, TaskStatus } from "../types/events.ts";

export const AGENT_NAMES: Readonly<Record<AgentId, string>> = {
  architect: "Architect",
  etl: "ETL Engineer",
  analytics: "Analytics Engineer",
  dashboard: "Dashboard Engineer",
};

/** One line each, in the agent's own voice, per docs/04-AGENT-RUNTIME.md. */
export const AGENT_ROLES: Readonly<Record<AgentId, string>> = {
  architect: "Agrees the shape of the work before any of it is built",
  etl: "Loads the raw extracts and makes them trustworthy",
  analytics: "Joins, derives, and computes the numbers",
  dashboard: "Turns the numbers into something you can read",
};

/** The initial on a graph node. */
export const AGENT_INITIALS: Readonly<Record<AgentId, string>> = {
  architect: "A",
  etl: "E",
  analytics: "N",
  dashboard: "D",
};

export const AGENT_IDS: readonly AgentId[] = ["architect", "etl", "analytics", "dashboard"];

export const LOG_LEVELS: readonly LogLevel[] = ["debug", "info", "warn", "error", "success"];

export const STATUS_WORDS: Readonly<Record<TaskStatus, string>> = {
  pending: "pending",
  ready: "ready",
  running: "running",
  retrying: "retrying",
  completed: "completed",
  failed: "failed",
  skipped: "skipped",
};

/** Log level to a text colour. Levels tint the message, never the row. */
export const LEVEL_TEXT: Readonly<Record<LogLevel, string>> = {
  debug: "text-chalk-dim",
  info: "text-chalk",
  warn: "text-signal",
  error: "text-fault-ink",
  success: "text-verify",
};

/** The five chart steps, ink blue through to warm ochre. */
export const SERIES = ["#123b59", "#276680", "#4e8d95", "#8fa877", "#cfa84e"] as const;

export const INK = {
  ground: "#0a2138",
  panel: "#123049",
  rule: "#26485f",
  chalk: "#e9eff3",
  chalkDim: "#8fa7b8",
  signal: "#f0a63f",
  verify: "#72be95",
  fault: "#dd6257",
  paperInk: "#1a2230",
  paperDim: "#5d6673",
  paperRule: "#e2e0d9",
} as const;

// ---------------------------------------------------------------- numbers

const money0 = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});
const compactMoney = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  notation: "compact",
  maximumFractionDigits: 1,
});
const counts = new Intl.NumberFormat("en-IN");

export function money(value: number): string {
  return money0.format(value);
}

/** For axis ticks, where a full rupee figure would collide with its neighbour. */
export function moneyShort(value: number): string {
  return compactMoney.format(value);
}

export function count(value: number): string {
  return counts.format(value);
}

export function percent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

export function bytes(value: number): string {
  if (value < 1024) return `${counts.format(value)} bytes`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

// ---------------------------------------------------------------- time

/** mm:ss.mmm from run start, per docs/04-AGENT-RUNTIME.md. */
export function stamp(at: number): string {
  const minutes = Math.floor(at / 60_000);
  const seconds = Math.floor((at % 60_000) / 1_000);
  const millis = at % 1_000;
  return `${pad(minutes, 2)}:${pad(seconds, 2)}.${pad(millis, 3)}`;
}

/** A duration a person would say out loud: "1m 41s", "820ms". */
export function duration(ms: number): string {
  if (ms < 1_000) return `${ms}ms`;
  const seconds = ms / 1_000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds - minutes * 60)}s`;
}

/** "2025-03-14" as "14 Mar", for a brushed range shown in a chip. */
export function shortDate(iso: string): string {
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

function pad(value: number, width: number): string {
  return String(value).padStart(width, "0");
}
