/**
 * The plan, as a plain list. No graph, no styling.
 *
 * Phase 1 deliberately looks like this. The graph is phase 4 and starting it
 * early is the failure mode the implementation plan warns about, so what is
 * here shows only that the plan came from the document: phases in order, tasks
 * with their owner and dependencies, and the warnings the parser returned.
 */

import type { Plan } from "../types/events.ts";

const AGENT_NAMES: Record<Plan["tasks"][string]["agent_id"], string> = {
  architect: "Architect",
  etl: "ETL Engineer",
  analytics: "Analytics Engineer",
  dashboard: "Dashboard Engineer",
};

export function PlanView({ plan }: { plan: Plan }) {
  return (
    <section>
      <h2>{plan.title}</h2>
      <p>
        {plan.phases.length} phases, {Object.keys(plan.tasks).length} tasks.
      </p>

      {plan.warnings.length > 0 && (
        <div>
          <h3>Warnings</h3>
          <ul>
            {plan.warnings.map((warning, index) => (
              <li key={`${warning.code}-${warning.task_id ?? index}`}>
                {warning.task_id !== null && warning.task_id !== undefined && (
                  <strong>{warning.task_id} </strong>
                )}
                {warning.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan.phases.map((phase) => (
        <div key={phase.id}>
          <h3>
            Phase {phase.index}. {phase.title}
          </h3>
          <ol>
            {phase.task_ids.map((taskId) => {
              const task = plan.tasks[taskId];
              if (task === undefined) return null;
              return (
                <li key={taskId}>
                  <strong>{task.id}</strong> {task.title}
                  <br />
                  Owner: {AGENT_NAMES[task.agent_id]}
                  <br />
                  Depends on:{" "}
                  {task.depends_on.length === 0 ? "nothing" : task.depends_on.join(", ")}
                  <br />
                  {task.steps.length} steps, {task.constraints.length} constraints,{" "}
                  {task.acceptance.length} acceptance criteria
                </li>
              );
            })}
          </ol>
        </div>
      ))}

      <h3>Run order</h3>
      <p>{plan.order.join(" then ")}</p>
    </section>
  );
}
