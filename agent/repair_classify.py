"""Classify SQL Gate / execute failures for repair metrics (P1).

Provides two layers:
- `classify_repair_error()` — lightweight string-only classifier (backward compat).
- `classify_with_hint()` — returns `RepairHint` with repair action + repairability.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RepairClass = Literal[
    "policy_keyword",
    "policy_allowlist",
    "policy_limit",
    "policy_other",
    "engine_syntax",
    "engine_runtime",
    "empty_result",
    "unknown",
]

# ── Repair action templates ─────────────────────────────────────────────

_REPAIR_ACTIONS: dict[RepairClass, str] = {
    "policy_keyword": (
        "Remove forbidden DDL/DML keywords (INSERT/UPDATE/DELETE/DROP/ALTER, etc). "
        "Generate a safe SELECT-only query. If the user question asks to modify data, "
        "explain that this is a read-only analytics platform."
    ),
    "policy_allowlist": (
        "Use ONLY the tables listed in 'Allowed tables'. "
        "Remove any reference to unauthorized tables, CTE aliases, or subqueries "
        "that access tables outside the allowlist."
    ),
    "policy_limit": (
        "Add a LIMIT clause to the query. "
        "The platform requires every SELECT to include an explicit LIMIT."
    ),
    "policy_other": (
        "Review the SQL against the Gate policy. "
        "The query was rejected by the SQL validation gate. "
        "Check table names, statement type, and security constraints."
    ),
    "engine_syntax": (
        "Fix the SQL syntax error. "
        "Common issues: missing commas, unmatched quotes, incorrect keywords, "
        "or malformed expressions. Verify the SQL is valid for the target dialect."
    ),
    "engine_runtime": (
        "Fix the runtime error. "
        "Common issues: column name mismatch, type casting error, "
        "function not available, or division by zero. "
        "Double-check column names against the schema."
    ),
    "empty_result": (
        "The query executed but returned no rows. "
        "Consider broadening WHERE conditions, removing unnecessary filters, "
        "or using a different aggregation approach."
    ),
    "unknown": (
        "The SQL Gate rejected the query for an unrecognized reason. "
        "Review the original error message and regenerate the SQL "
        "with stricter adherence to the platform rules."
    ),
}

# Repairable classes: errors the LLM has a reasonable chance of fixing.
_REPAIRABLE: set[RepairClass] = {
    "policy_allowlist",
    "policy_limit",
    "engine_syntax",
    "engine_runtime",
    "empty_result",
    "policy_other",
}

# Non-repairable: policy_keyword (prompt injection indicator) and unknown.
# policy_keyword IS technically repairable but kept conservative — if the LLM
# generated DROP/INSERT despite the system prompt, it may be a prompt injection
# attempt.  Callers can override via `repairable_override`.


@dataclass(frozen=True)
class RepairHint:
    """Structured repair guidance for the SQL generation retry loop."""

    repair_class: RepairClass
    action: str
    is_repairable: bool

    def as_tagged_error(self, message: str) -> str:
        """Backward-compatible tagged error string."""
        return f"[{self.repair_class}] {message}"


def classify_repair_error(message: str | None, *, stage: str = "validate") -> RepairClass:
    """Map Gate/execute error text → coarse class (deterministic)."""
    msg = (message or "").lower()
    if not msg.strip():
        return "unknown"

    if stage == "execute" and ("no rows" in msg or "empty" in msg):
        return "empty_result"

    if "allowlist" in msg or "not in allowlist" in msg or "unknown table" in msg:
        return "policy_allowlist"
    if "forbidden" in msg or "keyword" in msg or "ddl" in msg or "dml" in msg:
        return "policy_keyword"
    if "limit" in msg and ("missing" in msg or "required" in msg or "exceed" in msg):
        return "policy_limit"
    # policy_other: gate/policy related but not matching allowlist/keyword/limit
    # Use word-boundary check for "gate" to avoid matching "navigate"/"aggregate"
    if "sql policy" in msg or "policy violation" in msg or "policy check" in msg:
        return "policy_other"
    if "policy" in msg:
        return "policy_other"
    if any(
        k in msg
        for k in (
            " gate ",
            "gate:",
            "gate.",
            "gate rejected",
            "gate denied",
            "gate error",
            "gate policy",
            "gate check",
            "gate validation",
        )
    ):
        return "policy_other"
    if msg.startswith("gate ") or msg.endswith(" gate"):
        return "policy_other"

    if any(
        k in msg
        for k in (
            "syntax",
            "parse",
            "unexpected",
            "near ",
            "token",
            "malformed",
        )
    ):
        return "engine_syntax"

    if stage == "execute":
        return "engine_runtime"
    return "unknown"


def classify_with_hint(
    message: str | None,
    *,
    stage: str = "validate",
    repairable_override: dict[RepairClass, bool] | None = None,
) -> RepairHint:
    """Classify error → RepairHint with action + repairability.

    Args:
        message: The error message from Gate or execute.
        stage: "validate" (Gate) or "execute" (runtime).
        repairable_override: Optional overrides for is_repairable per class.
    """
    rc = classify_repair_error(message, stage=stage)
    action = _REPAIR_ACTIONS.get(rc, _REPAIR_ACTIONS["unknown"])
    is_repairable = _REPAIRABLE.__contains__(rc)
    if repairable_override:
        ov = repairable_override.get(rc)
        if ov is not None:
            is_repairable = ov
    return RepairHint(repair_class=rc, action=action, is_repairable=is_repairable)
