"""Cooperative run abort signals — no SQLAlchemy / Shell imports.

Worker injects ``cancel_check`` into AnalysisContext; Skills/nodes call checkpoint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.state import AnalysisContext


class RunAborted(Exception):
    """Raised at a cooperative checkpoint when cancel or wall-clock timeout was requested."""

    def __init__(self, reason: str) -> None:
        self.reason = reason  # "cancelled" | "timeout"
        super().__init__(f"run aborted: {reason}")


def checkpoint(ctx: AnalysisContext) -> None:
    """Invoke optional cancel_check; no-op when unset (unit tests / direct Skill calls)."""
    check = getattr(ctx, "cancel_check", None)
    if check is not None:
        check()
