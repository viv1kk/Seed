/**
 * The SSE subscription, batched onto animation frames.
 *
 * Batching is a correctness-adjacent requirement, not a nicety. A busy stretch
 * of a run delivers several events per frame, and one store write per event
 * means hundreds of renders a minute and a log that visibly stutters. Events
 * accumulate in a ref here and flush once per frame.
 *
 * The stream replays from seq=0 on every connection, so a reconnect re-delivers
 * the whole run. The store is reset before subscribing for that reason: applying
 * a replay on top of existing state would double every log line.
 */

import type { SeedEvent } from "../types/events.ts";
import { EVENT_TYPES } from "../types/eventTypes.ts";

export interface StreamHandle {
  close: () => void;
}

export interface StreamCallbacks {
  onBatch: (events: SeedEvent[]) => void;
  onError?: (message: string) => void;
  onOpen?: () => void;
}

export function subscribeToRun(runId: string, callbacks: StreamCallbacks): StreamHandle {
  const source = new EventSource(`/api/runs/${runId}/stream`);

  let pending: SeedEvent[] = [];
  let frame: number | null = null;
  let closed = false;

  // The highest seq handed to the store so far.
  //
  // EventSource reconnects by itself whenever the response ends, and this server
  // always replays a run from seq 0, so a reconnect re-delivers everything it
  // has already sent. Without this the log doubles on every reconnect, which is
  // exactly what happens the moment a run finishes and the server closes the
  // stream. Deduplicating here rather than in the reducer keeps the reducer a
  // plain fold and makes replay safe wherever it comes from.
  let delivered = -1;

  const flush = () => {
    frame = null;
    if (pending.length === 0) return;
    const batch = pending;
    pending = [];
    callbacks.onBatch(batch);
  };

  const finish = () => {
    closed = true;
    for (const name of EVENT_TYPES) source.removeEventListener(name, receive);
    if (frame !== null) cancelAnimationFrame(frame);
    flush();
    source.close();
  };

  source.onopen = () => callbacks.onOpen?.();

  const receive = (message: MessageEvent<string>) => {
    const event = JSON.parse(message.data) as SeedEvent;
    if (event.seq <= delivered) return;
    delivered = event.seq;
    pending.push(event);
    if (frame === null) frame = requestAnimationFrame(flush);

    // Contract rule 7: nothing follows run.completed. Closing here stops the
    // browser reconnecting to a run that has nothing left to say.
    if (event.type === "run.completed" || event.type === "run.failed") {
      queueMicrotask(finish);
    }
  };

  // One listener per event name, not `onmessage`.
  //
  // The stream sets `event:` to the event type, as the contract specifies, so
  // the browser dispatches a typed event. `onmessage` only fires for messages
  // with no event name, which means it would never fire here and the run would
  // silently never arrive. EVENT_TYPES is generated from the same schema as the
  // types, so a new event cannot be added without this picking it up.
  for (const name of EVENT_TYPES) source.addEventListener(name, receive);

  source.onerror = () => {
    // EventSource reconnects on its own, and the replay makes that safe. The
    // only case worth reporting is a connection that is actually gone.
    if (closed) return;
    if (source.readyState === EventSource.CLOSED) {
      callbacks.onError?.("Lost the event stream. Reconnecting.");
    }
  };

  // finish() delivers whatever arrived in the last part-frame rather than
  // dropping it, so closing mid-run never loses a line already received.
  return { close: finish };
}
