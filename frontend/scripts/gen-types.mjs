// Generate src/types/events.ts from the schema the backend exports.
//
// This is build tooling, not application code. It exists as a script rather
// than an inline npm command for two reasons: a multi-line banner comment does
// not survive npm argument parsing, and the generated union is worth checking
// before it reaches the store.
//
// The check at the bottom is the important part. The whole exhaustive-switch
// discipline in src/state depends on SeedEvent being a *discriminated* union of
// string literal types. If json-schema-to-typescript ever widens `type` to
// `string`, assertNever silently stops catching unhandled events and this
// build should fail loudly instead.

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { compile } from "json-schema-to-typescript";

const here = dirname(fileURLToPath(import.meta.url));
const schemaPath = resolve(here, "../src/types/events.schema.json");
const outPath = resolve(here, "../src/types/events.ts");

const BANNER = `/**
 * GENERATED FILE. DO NOT EDIT.
 *
 * Generated from backend/app/core/types.py, which is authoritative for the
 * event contract. See docs/03-EVENT-CONTRACT.md.
 *
 * Regenerate with:  make types
 */`;

// Every event type in the contract. Kept here rather than derived from the
// output so that a variant vanishing from the schema is caught too.
const EXPECTED_EVENT_TYPES = [
  "run.started",
  "plan.built",
  "agent.spawned",
  "task.ready",
  "task.started",
  "task.progress",
  "log.emitted",
  "artifact.created",
  "task.failed",
  "task.retried",
  "task.completed",
  "agent.idle",
  "run.completed",
  "run.failed",
];

const schema = JSON.parse(await readFile(schemaPath, "utf8"));

let ts = await compile(schema, "SeedContract", {
  bannerComment: BANNER,
  additionalProperties: false,
  unreachableDefinitions: true,
  declareExternallyReferenced: true,
  style: { singleQuote: false, semi: true },
});

// Normalise line endings so the committed file is identical on every platform
// and `git diff` after a regeneration is genuinely empty.
ts = ts.replace(/\r\n/g, "\n");

await writeFile(outPath, ts, "utf8");

// ---------------------------------------------------------------- verify

const problems = [];

const unionMatch = ts.match(/export type SeedEvent =([^;]+);/);
if (!unionMatch) {
  problems.push("no `export type SeedEvent = ...` union was generated");
}

for (const eventType of EXPECTED_EVENT_TYPES) {
  // A discriminated union needs `type: "run.started";` as a literal, not
  // `type?: string`. Match the property declaration exactly.
  const literal = new RegExp(`\\btype\\??:\\s*"${eventType.replace(".", "\\.")}";`);
  if (!literal.test(ts)) {
    problems.push(`\`type: "${eventType}"\` is not a string literal in the output`);
  }
}

if (/\btype\??:\s*string;/.test(ts)) {
  problems.push("at least one `type` discriminant was widened to `string`");
}

// Any union tagged by a single-value literal must have that tag REQUIRED, or the
// union does not discriminate and every switch over it silently stops being
// exhaustive. Pydantic omits a tag from `required` because it has a default, so
// this is a standing trap, not a one-off: SeedEvent tags on `type` and
// ParseResult on `status`, and the next one will tag on something else again.
for (const [, name] of ts.matchAll(/^\s*(\w+)\?:\s*"[^"|]*";$/gm)) {
  problems.push(
    `\`${name}\` is an optional single-value literal, so its union will not ` +
      "discriminate (see _require_discriminants in export_schema.py)",
  );
}

// Every union of interfaces we generate should be reachable by name.
for (const expected of ["SeedEvent", "ParseResult"]) {
  if (!new RegExp(`export type ${expected} =`).test(ts)) {
    problems.push(`\`export type ${expected}\` is missing from the output`);
  }
}

if (problems.length > 0) {
  console.error("gen:types produced a union that will not discriminate:\n");
  for (const problem of problems) console.error(`  - ${problem}`);
  console.error(
    "\nFix backend/scripts/export_schema.py. Do not work around this in " +
      "src/types/events.ts, which is generated output.",
  );
  process.exit(1);
}

console.log(
  `events.ts written: SeedEvent discriminates over ${EXPECTED_EVENT_TYPES.length} literal types.`,
);
