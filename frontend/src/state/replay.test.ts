/**
 * The phase 0 gate, TypeScript half.
 *
 * Replays the same fixture files as backend/tests/test_reducer.py, through the
 * real Zustand store, and asserts the same hand-written `expected` block. One
 * fixture, two languages, same assertions: that is the regression net for the
 * whole contract, and it catches drift between the two reducers the day it
 * happens rather than during a demo.
 *
 * Run with `npm test`. No test framework: Node runs TypeScript directly and
 * ships its own runner, so the parity net costs no dependency.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import type { SeedEvent } from "../types/events.ts";
import { applyEvents } from "./applyEvent.ts";
import { initialState } from "./runState.ts";
import { seedStore } from "./store.ts";
import { summarise, type StateSummary } from "./summarise.ts";

const FIXTURE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../../backend/tests/fixtures",
);

const FIXTURE_FILES = [
  "phase0_events.json",
  "phase0_events_full.json",
  "phase0_events_failed.json",
  "phase2_artifact_streaming.json",
] as const;

interface Fixture {
  name: string;
  description: string;
  events: SeedEvent[];
  expected: StateSummary;
}

function loadFixture(filename: string): Fixture {
  return JSON.parse(readFileSync(resolve(FIXTURE_DIR, filename), "utf8")) as Fixture;
}

for (const filename of FIXTURE_FILES) {
  const fixture = loadFixture(filename);

  test(`${fixture.name}: the reducer reaches the expected state`, () => {
    const state = applyEvents(initialState(), fixture.events);
    assert.deepStrictEqual(summarise(state), fixture.expected, fixture.description);
  });

  test(`${fixture.name}: the store reaches the expected state`, () => {
    // Through the real store, not just the reducer, because the store is what
    // the gate names and what the app actually renders from.
    seedStore.getState().reset();
    seedStore.getState().applyEvents(fixture.events);
    assert.deepStrictEqual(summarise(seedStore.getState().run), fixture.expected);
  });

  test(`${fixture.name}: applying one event at a time gives the same result`, () => {
    // The live stream is batched on requestAnimationFrame, so batch size varies
    // with how busy the run is. It must not change where the run ends up.
    seedStore.getState().reset();
    for (const event of fixture.events) seedStore.getState().applyEvents([event]);
    assert.deepStrictEqual(summarise(seedStore.getState().run), fixture.expected);
  });
}

test("the ten-event gate fixture is exactly ten events", () => {
  assert.equal(loadFixture("phase0_events.json").events.length, 10);
});

test("the retry beat happens exactly once", () => {
  const state = applyEvents(initialState(), loadFixture("phase0_events.json").events);
  assert.equal(state.retryCount, 1);
  assert.equal(state.taskAttempts["1.1"], 2);
  assert.equal(state.taskStatus["1.1"], "completed");
});

test("a recoverable failure reads as retrying, not failed", () => {
  const fixture = loadFixture("phase0_events.json");
  const state = applyEvents(
    initialState(),
    fixture.events.filter((event) => event.seq <= 6),
  );
  assert.equal(state.taskStatus["1.1"], "retrying");
});

test("applyEvent does not mutate the state it is given", () => {
  const fixture = loadFixture("phase0_events.json");
  const before = applyEvents(initialState(), fixture.events);
  const snapshot = summarise(before);

  applyEvents(before, [
    {
      type: "run.started",
      run_id: "other",
      seq: 99,
      at: 0,
      requirement_title: "x",
      seed: 1,
      speed: 1,
    },
  ]);

  assert.deepStrictEqual(summarise(before), snapshot);
});

test("reset returns the store to its initial state", () => {
  seedStore.getState().applyEvents(loadFixture("phase0_events.json").events);
  seedStore.getState().reset();
  assert.deepStrictEqual(summarise(seedStore.getState().run), summarise(initialState()));
});

test("an empty batch does not disturb the store", () => {
  seedStore.getState().reset();
  const before = seedStore.getState().run;
  seedStore.getState().applyEvents([]);
  assert.equal(seedStore.getState().run, before, "an empty batch should not produce a new state");
});
