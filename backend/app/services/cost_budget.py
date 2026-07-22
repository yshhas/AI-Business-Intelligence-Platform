"""P0-2 Soft Cost Budget — workspace UTC-day token gate (Shell only).

Trace/step LLM usage remains the detail source of truth.
`analysis_tasks.llm_total_tokens` is a denormalized sum for cheap budget checks.
Not a billing / FinOps product.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import AgentRunStep, AnalysisTask
from app.services import run_lifecycle as rl

logger = logging.getLogger(__name__)


class BudgetError(Exception):
    """Enqueue rejected due to soft LLM token budget (map to HTTP 429)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.failure_class = rl.FAILURE_BUDGET


def utc_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return [start, end) for the current UTC calendar day."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return start, end


def tokens_from_usage_dict(usage: dict[str, Any] | None) -> int:
    if not isinstance(usage, dict):
        return 0
    total = usage.get("total_tokens")
    if total is not None:
        try:
            return max(0, int(total))
        except (TypeError, ValueError):
            pass
    try:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        return max(0, prompt + completion)
    except (TypeError, ValueError):
        return 0


def extract_tokens_from_output_json(output_json: dict[str, Any] | None) -> int:
    """Pull tokens from a single step's output_json (llm usage meta)."""
    if not isinstance(output_json, dict):
        return 0
    llm = output_json.get("llm")
    if isinstance(llm, dict):
        return tokens_from_usage_dict(llm.get("usage") if "usage" in llm else None) or (
            tokens_from_usage_dict(llm) if "prompt_tokens" in llm else 0
        )
    # Some steps may nest usage at top level
    if "usage" in output_json:
        return tokens_from_usage_dict(output_json.get("usage"))
    return 0


def sum_tokens_from_steps(steps: list[AgentRunStep] | list[Any]) -> int:
    total = 0
    for step in steps:
        out = getattr(step, "output_json", None)
        if isinstance(step, dict):
            out = step.get("output_json")
        total += extract_tokens_from_output_json(out if isinstance(out, dict) else None)
    return total


def workspace_day_token_usage(
    db: Session,
    *,
    workspace_id: UUID,
    now: datetime | None = None,
) -> int:
    """Sum denormalized llm_total_tokens for workspace tasks created in UTC day."""
    start, end = utc_day_bounds(now)
    value = db.scalar(
        select(func.coalesce(func.sum(AnalysisTask.llm_total_tokens), 0)).where(
            AnalysisTask.workspace_id == workspace_id,
            AnalysisTask.created_at >= start,
            AnalysisTask.created_at < end,
            AnalysisTask.llm_total_tokens.is_not(None),
        )
    )
    return int(value or 0)


def assert_budget_allowed(
    db: Session,
    *,
    workspace_id: UUID,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> None:
    """Reject when workspace UTC-day usage >= configured soft budget."""
    settings = settings or get_settings()
    budget = int(settings.llm_token_budget_per_workspace_day or 0)
    if budget <= 0:
        return
    used = workspace_day_token_usage(db, workspace_id=workspace_id, now=now)
    if used >= budget:
        raise BudgetError(
            f"Workspace daily LLM token budget exceeded "
            f"(used={used}, budget={budget}, window=UTC-day). "
            f"failure_class={rl.FAILURE_BUDGET}"
        )


def apply_llm_total_tokens(db: Session, task: AnalysisTask) -> int:
    """Aggregate step usage → task.llm_total_tokens; echo on platform.run when present.

    Steps remain the detail source of truth; column is a stats/index field.
    """
    steps = list(
        db.scalars(
            select(AgentRunStep)
            .where(AgentRunStep.task_id == task.id)
            .order_by(AgentRunStep.step_no)
        ).all()
    )
    total = sum_tokens_from_steps(steps)
    # Store 0 when steps exist but no usage (honest zero); None only if we skip apply
    task.llm_total_tokens = total

    if task.result_json is not None:
        data = dict(task.result_json)
        platform = dict(data.get("platform") or {})
        run = dict(platform.get("run") or {})
        run["llm_total_tokens"] = total
        platform["run"] = run
        data["platform"] = platform
        task.result_json = data

    return total
