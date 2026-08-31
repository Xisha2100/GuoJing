"""One bounded polling pass for the local MVP worker process."""

from collections.abc import Callable
from uuid import UUID

from guojing.application.help_requests.queue import HelpRequestQueue
from guojing.application.help_requests.workflow import HelpRequestWorkflowState


class HelpRequestWorker:
    """Drive the already-composed workflow without owning scheduling or I/O."""

    def __init__(
        self,
        queue: HelpRequestQueue,
        run_workflow: Callable[[UUID], HelpRequestWorkflowState],
    ) -> None:
        self._queue = queue
        self._run_workflow = run_workflow

    def run_once(self, limit: int = 10) -> tuple[HelpRequestWorkflowState, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("worker limit must be between 1 and 100")
        states: list[HelpRequestWorkflowState] = []
        processed_ids: set[UUID] = set()
        for _ in range(limit):
            request = self._queue.next_pending()
            if request is None:
                break
            if request.request_id in processed_ids:
                break
            processed_ids.add(request.request_id)
            states.append(self._run_workflow(request.request_id))
        return tuple(states)
