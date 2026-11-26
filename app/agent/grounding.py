from typing import Iterable


def enforce_grounded_ids(
    mentioned_job_ids: Iterable[int],
    tool_returned_job_ids: set[int],
) -> tuple[list[int], list[int]]:
    """Splits candidate job_ids into valid grounded IDs and rejected ungrounded IDs."""
    grounded: list[int] = []
    rejected: list[int] = []
    for jid in dict.fromkeys(mentioned_job_ids):
        if jid in tool_returned_job_ids:
            grounded.append(jid)
        else:
            rejected.append(jid)
    return grounded, rejected
