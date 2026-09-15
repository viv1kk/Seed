/**
 * The requirement document, displayed as written.
 *
 * Not re-rendered from the parsed plan. The person reading it should see their
 * own file, unmodified, which is what makes "edit a heading and watch the graph
 * change" land. Lines are styled by their Markdown prefix, which is formatting
 * rather than parsing: nothing here decides what a line means to the run, and
 * the plan on the right came entirely from the backend.
 *
 * The lines belonging to the selected task are lit, so clicking a node points
 * at the paragraph it came from.
 */

import { useEffect, useMemo, useRef } from "react";

import type { Plan } from "../../types/events.ts";

type Kind = "title" | "phase" | "task" | "meta" | "bullet" | "quote" | "code" | "prose" | "blank";

interface Line {
  index: number;
  text: string;
  kind: Kind;
  /** The `### ` heading this line sits under, by its text. */
  headingText: string | null;
}

export function RequirementColumn({
  markdown,
  plan,
  selectedTaskId,
}: {
  markdown: string;
  plan: Plan;
  selectedTaskId: string | null;
}) {
  const lines = useMemo(() => classify(markdown), [markdown]);
  const selectedHeading = useMemo(() => {
    if (selectedTaskId === null) return null;
    const task = plan.tasks[selectedTaskId];
    return task === undefined ? null : task.title;
  }, [plan, selectedTaskId]);

  const marker = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (selectedHeading === null) return;
    marker.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [selectedHeading]);

  return (
    <div className="h-full overflow-y-auto px-4 py-3">
      {lines.map((line) => {
        const lit = selectedHeading !== null && line.headingText === selectedHeading;
        const first = lit && line.kind === "task";
        return (
          <div
            key={line.index}
            ref={first ? marker : undefined}
            className={`${classesFor(line.kind)} ${
              selectedHeading === null ? "" : lit ? "opacity-100" : "opacity-35"
            } transition-opacity duration-150`}
          >
            {line.text === "" ? " " : line.text}
          </div>
        );
      })}
    </div>
  );
}

function classesFor(kind: Kind): string {
  switch (kind) {
    case "title":
      return "t-body pt-1 pb-2 font-medium text-chalk";
    case "phase":
      return "t-panel-header pt-4 pb-1 text-signal";
    case "task":
      return "t-secondary pt-3 font-medium text-chalk";
    case "meta":
      return "t-secondary text-chalk-dim";
    case "bullet":
      return "t-secondary pl-2 text-chalk-dim";
    case "quote":
      return "t-secondary border-l-2 border-ink-600 pl-2 text-chalk-dim italic";
    case "code":
      return "t-log text-chalk-dim opacity-80";
    case "blank":
      return "h-2";
    case "prose":
      return "t-secondary text-chalk-dim";
  }
}

/**
 * Tag each line by its Markdown prefix and remember the task heading above it.
 *
 * The `### ` text is kept rather than a task id, because ids are the parser's
 * to assign and this column is deliberately reading the raw file. Matching on
 * the title is enough to light the right paragraph and keeps this side of the
 * app from having its own opinion about how a document decomposes.
 */
function classify(markdown: string): Line[] {
  const out: Line[] = [];
  let heading: string | null = null;
  let inFence = false;

  markdown.split("\n").forEach((raw, index) => {
    const text = raw.replace(/\s+$/, "");
    if (text.startsWith("```")) {
      inFence = !inFence;
      out.push({ index, text, kind: "code", headingText: heading });
      return;
    }
    if (inFence) {
      out.push({ index, text, kind: "code", headingText: heading });
      return;
    }

    let kind: Kind = "prose";
    if (text === "") kind = "blank";
    else if (text.startsWith("### ")) {
      heading = text.slice(4).replace(/^\d+(\.\d+)*\s*/, "");
      kind = "task";
    } else if (text.startsWith("## ")) {
      heading = null;
      kind = "phase";
    } else if (text.startsWith("# ")) {
      heading = null;
      kind = "title";
    } else if (/^(Agent|Depends on):/i.test(text)) kind = "meta";
    else if (text.startsWith("- ") || text.startsWith("* ")) kind = "bullet";
    else if (text.startsWith("> ")) kind = "quote";

    out.push({ index, text, kind, headingText: heading });
  });

  return out;
}
