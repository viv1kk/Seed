/**
 * Requirement intake: the bundled examples, and the person's own document.
 *
 * FR1 in docs/01-PRD.md is "pick a bundled requirement file or paste Markdown".
 * The examples are there to open the demo on something known; the box beneath
 * them is the actual product, because the requirement belongs to whoever is
 * using this and the parser reads both by exactly the same path. Nothing here
 * treats an example differently from a pasted document once it is chosen.
 *
 * The file control reads a local file into the box. It is not an upload: no
 * file reaches the server, no multipart endpoint exists, and what gets sent is
 * the same `{markdown}` body a paste sends. "Arbitrary file upload" stays out
 * of scope exactly as the PRD says; opening a .md file from disk is how a
 * person hands over a document they already wrote.
 */

import { useRef, useState } from "react";

import type { ExampleSummary } from "../../types/events.ts";

/** What a document can arrive as. Anything else is rejected with a reason. */
const ACCEPT = ".md,.markdown,.txt,text/markdown,text/plain";

/**
 * Refuse a file large enough to be something other than a requirement.
 *
 * A requirements document is a few kilobytes. A megabyte of it is a mistake,
 * and reading it would stall the tab and blow the sessionStorage quota that the
 * refresh-recovery relies on.
 */
const MAX_BYTES = 512 * 1024;

export interface IntakeProps {
  examples: readonly ExampleSummary[];
  loadingExamples: boolean;
  /** The document in the box. Held by App so the header's button can use it. */
  draft: string;
  onDraftChange: (text: string, name?: string) => void;
  onPickExample: (exampleId: string) => void;
  onBuild: () => void;
  /** Shown above the box when a document has just been rejected by the parser. */
  notice?: string | null;
}

export function Intake({
  examples,
  loadingExamples,
  draft,
  onDraftChange,
  onPickExample,
  onBuild,
  notice,
}: IntakeProps) {
  const [dropping, setDropping] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement | null>(null);

  const accept = async (file: File | undefined) => {
    setFileError(null);
    if (file === undefined) return;
    if (file.size > MAX_BYTES) {
      setFileError("That file is larger than 512 KB. Pick the requirements document itself.");
      return;
    }
    try {
      const text = await file.text();
      onDraftChange(text, file.name);
    } catch {
      setFileError("That file could not be read. Try opening it and pasting the text.");
    }
  };

  const ready = draft.trim().length > 0;

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col justify-center gap-6 px-8 py-10">
      <div>
        <h2 className="t-run-title text-chalk">Load a requirement to begin</h2>
        <p className="t-body max-w-xl pt-2 text-chalk-dim">
          Seed reads a Markdown requirements file, plans the work, and builds it. Pick one of
          the examples or paste your own.
        </p>
      </div>

      <section className="flex flex-col gap-2">
        <h3 className="t-panel-header text-chalk-dim">Examples</h3>
        {loadingExamples ? (
          <p className="t-secondary text-chalk-dim">Loading examples.</p>
        ) : (
          <ul className="flex flex-wrap gap-2">
            {examples.map((example) => (
              <li key={example.id}>
                <button
                  type="button"
                  onClick={() => onPickExample(example.id)}
                  className="t-body rounded-sm border border-ink-600 px-4 py-2 text-left text-chalk hover:border-signal hover:text-signal"
                >
                  {example.title}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex min-h-0 flex-col gap-2">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="t-panel-header text-chalk-dim">Your requirement</h3>
          <div className="flex items-center gap-3">
            {draft.length > 0 && (
              <span className="t-secondary t-num text-chalk-dim">
                {draft.split("\n").length} lines
              </span>
            )}
            <button
              type="button"
              onClick={() => picker.current?.click()}
              className="t-secondary rounded-sm border border-ink-600 px-2.5 py-0.5 text-chalk-dim hover:border-chalk-dim hover:text-chalk"
            >
              Open a file
            </button>
            {draft.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  onDraftChange("");
                  setFileError(null);
                }}
                className="t-secondary text-chalk-dim underline underline-offset-2 hover:text-chalk"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        <input
          ref={picker}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          aria-label="Open a Markdown requirements file"
          onChange={(event) => {
            void accept(event.target.files?.[0]);
            // Reset, so choosing the same file twice in a row still fires.
            event.target.value = "";
          }}
        />

        <textarea
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          spellCheck={false}
          aria-label="Paste your requirements document"
          placeholder={PLACEHOLDER}
          onDragOver={(event) => {
            event.preventDefault();
            setDropping(true);
          }}
          onDragLeave={() => setDropping(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDropping(false);
            void accept(event.dataTransfer.files[0]);
          }}
          className={`t-log h-64 w-full resize-none rounded-sm border bg-ink-800 px-3 py-2 text-chalk placeholder:text-chalk-dim placeholder:opacity-60 ${
            dropping ? "border-signal" : "border-ink-600"
          }`}
        />

        <p className="t-secondary text-chalk-dim">
          Paste the document, drop a file on the box, or open one. Headings become phases and
          tasks.
        </p>

        {fileError !== null && (
          <p role="alert" className="t-secondary text-fault-ink">
            {fileError}
          </p>
        )}
        {notice != null && notice !== "" && (
          <p role="status" className="t-secondary text-signal">
            {notice}
          </p>
        )}

        <div>
          <button
            type="button"
            onClick={onBuild}
            disabled={!ready}
            className="t-body rounded-sm border border-signal px-4 py-1.5 font-medium text-signal hover:bg-signal/10 disabled:border-ink-600 disabled:text-chalk-dim disabled:hover:bg-transparent"
          >
            Build the plan
          </button>
        </div>
      </section>
    </div>
  );
}

const PLACEHOLDER = `# Your requirement

## Phase 1: Design

### 1.1 Define the schema contract

Agent: Architect

- Read the source extracts and record the columns
- Decide the join keys

> Every column consumed downstream is named in the contract.`;
