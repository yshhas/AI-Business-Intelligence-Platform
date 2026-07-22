"""In-process cooperative cancel / timeout token for the analysis Worker.

Shell only sets ``cancel_requested`` in DB; Worker owns this token and injects
``raise_if_aborted`` into the Skill via AnalysisContext.cancel_check.
"""

from __future__ import annotations

import threading


class CancelToken:
    """Thread-safe abort signal + write fence after terminal status is committed."""

    def __init__(self) -> None:
        self._cancel = threading.Event()
        self._timeout = threading.Event()
        self._closed = threading.Event()

    def request_cancel(self) -> None:
        self._cancel.set()

    def request_timeout(self) -> None:
        self._timeout.set()

    def close(self) -> None:
        """Close write fence after Worker commits cancelled/timed_out."""
        self._closed.set()

    def is_closed(self) -> bool:
        return self._closed.is_set()

    def is_aborted(self) -> bool:
        return self._cancel.is_set() or self._timeout.is_set()

    def reason(self) -> str | None:
        if self._cancel.is_set():
            return "cancelled"
        if self._timeout.is_set():
            return "timeout"
        return None

    def raise_if_aborted(self) -> None:
        # Lazy import: agent package is on path after ensure_repo_root_on_path()
        from agent.run_control import RunAborted

        if self._closed.is_set():
            reason = self.reason() or "cancelled"
            raise RunAborted(reason)
        if self._cancel.is_set():
            raise RunAborted("cancelled")
        if self._timeout.is_set():
            raise RunAborted("timeout")
