"""Eval data models — CheckResult and CaseResult dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class CaseResult:
    id: str
    passed: bool
    skipped: bool = False
    skip_reason: str | None = None
    checks: dict[str, str] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "passed": self.passed,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "checks": self.checks,
            "observed": self.observed,
            "errors": self.errors,
        }