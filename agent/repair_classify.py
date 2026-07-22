"""Classify SQL Gate / execute failures for repair metrics (P1)."""

from __future__ import annotations

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
    if "gate" in msg or "policy" in msg or "sql policy" in msg:
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
