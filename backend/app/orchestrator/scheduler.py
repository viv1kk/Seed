"""The ready set over the task graph.

Scheduling is a loop over a ready set, not a timeline. Nothing here knows about
time, agents or runners; it only answers which tasks may start next given what
has finished.
"""

from app.core.types import Plan, TaskStatus


class Scheduler:
    def __init__(self, plan: Plan) -> None:
        self._plan = plan
        # Plan order is a topological sort, so iterating it gives a stable,
        # document-derived priority whenever several tasks become ready at once.
        self._order = list(plan.order)
        self.status: dict[str, TaskStatus] = dict.fromkeys(self._order, "pending")

    def ready_set(self) -> list[str]:
        """Pending tasks whose dependencies have all completed, in plan order."""
        return [
            task_id
            for task_id in self._order
            if self.status[task_id] in {"pending", "ready"}
            and all(
                self.status[dependency] == "completed"
                for dependency in self._plan.tasks[task_id].depends_on
            )
        ]

    def mark_ready(self, task_id: str) -> None:
        self.status[task_id] = "ready"

    def mark_running(self, task_id: str) -> None:
        self.status[task_id] = "running"

    def mark_completed(self, task_id: str) -> None:
        self.status[task_id] = "completed"

    def mark_failed(self, task_id: str) -> list[str]:
        """Fail a task and skip everything that was waiting on it.

        Returns the skipped ids so the orchestrator can report them. Leaving
        them pending instead would read as a run that simply stopped, and would
        also look like a deadlock to the loop.
        """
        self.status[task_id] = "failed"

        skipped: list[str] = []
        changed = True
        while changed:
            changed = False
            for candidate in self._order:
                if self.status[candidate] != "pending":
                    continue
                blockers = self._plan.tasks[candidate].depends_on
                if any(self.status[b] in {"failed", "skipped"} for b in blockers):
                    self.status[candidate] = "skipped"
                    skipped.append(candidate)
                    changed = True
        return skipped

    @property
    def incomplete(self) -> list[str]:
        return [
            task_id
            for task_id in self._order
            if self.status[task_id] in {"pending", "ready", "running"}
        ]

    def has_incomplete_tasks(self) -> bool:
        return bool(self.incomplete)
