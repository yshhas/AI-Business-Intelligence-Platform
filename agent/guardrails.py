"""Thin output guardrails (Wave 3) — redact obvious secrets/PII patterns from user-visible text.

Not a compliance product: heuristic only; applied on Facade result_json before return.
"""

from __future__ import annotations

import re
from typing import Any

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_BEARER = re.compile(r"(?i)\b(bearer|api[_-]?key|sk-)[\s:=]+[A-Za-z0-9._\-/+=]{8,}")
_LONG_TOKEN = re.compile(r"\b(?:sk|pk|rk)[_-][A-Za-z0-9]{16,}\b")


def redact_text(text: str) -> str:
    if not text:
        return text
    out = _EMAIL.sub("[REDACTED_EMAIL]", text)
    out = _BEARER.sub(r"\1=[REDACTED]", out)
    out = _LONG_TOKEN.sub("[REDACTED_TOKEN]", out)
    return out


def apply_output_guardrails(result_json: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow-copied result with summary/report strings redacted."""
    if not isinstance(result_json, dict):
        return result_json
    out = dict(result_json)
    if isinstance(out.get("summary"), str):
        out["summary"] = redact_text(out["summary"])
    report = out.get("report")
    if isinstance(report, dict):
        rep = dict(report)
        if isinstance(rep.get("markdown"), str):
            rep["markdown"] = redact_text(rep["markdown"])
        if isinstance(rep.get("title"), str):
            rep["title"] = redact_text(rep["title"])
        out["report"] = rep
    limitations = out.get("limitations")
    if isinstance(limitations, list):
        out["limitations"] = [
            redact_text(x) if isinstance(x, str) else x for x in limitations
        ]
    platform = dict(out.get("platform") or {})
    platform["guardrails"] = {"applied": True, "schema_version": 1}
    out["platform"] = platform
    return out
