"""Persist guards for AgentRunStep / side effects after Run terminalization."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AnalysisTask
from app.services import run_lifecycle as rl
from app.workers.run_control import CancelToken


def write_allowed(
    db: Session,
    task_id: UUID,
    token: CancelToken | None = None,
) -> bool:
    """True only while the Run is still ``running`` and the token fence is open.

    Abort signal (cancel/timeout) denies writes immediately, even before
    ``token.close()`` and before the DB status is flipped terminal.
    """
    if token is not None and (token.is_closed() or token.is_aborted()):
        return False
    task = db.get(AnalysisTask, task_id)
    if task is None:
        return False
    if task.status != "running":
        return False
    if task.status in rl.TERMINAL_STATUSES:
        return False
    return True
