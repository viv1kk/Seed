/**
 * The exhaustiveness guard behind every switch over the event union.
 *
 * Reaching this at runtime means the backend sent an event the frontend has
 * never heard of. It should be unreachable: a new variant in the contract makes
 * `assertNever` fail to typecheck, so the frontend build breaks before anyone
 * can ship a renderer that silently drops events.
 */
export function assertNever(value: never): never {
  throw new Error(`Unhandled discriminated union member: ${JSON.stringify(value)}`);
}
