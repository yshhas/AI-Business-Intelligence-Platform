"""Thin output guardrails (Wave 3 + P1.7) — redact secrets/PII patterns from user-visible text.

Not a compliance product: heuristic only.
Applied on Facade ``result_json`` and Dataset HTTP preview (same redaction helpers).
Does **not** replace Policy SQL Gate.
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


def _redact_cell(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_table_preview(preview: Any) -> Any:
    """Redact string cells/column names in a table_preview-like dict.

    Accepts ``{columns, rows}`` where rows are dicts or sequences.
    Non-dict previews are returned unchanged.
    """
    if not isinstance(preview, dict):
        return preview
    out = dict(preview)
    cols = out.get("columns")
    if isinstance(cols, list):
        out["columns"] = [
            redact_text(c) if isinstance(c, str) else c for c in cols
        ]
    rows = out.get("rows")
    if isinstance(rows, list):
        new_rows: list[Any] = []
        for row in rows:
            if isinstance(row, dict):
                new_rows.append({k: _redact_cell(v) for k, v in row.items()})
            elif isinstance(row, (list, tuple)):
                new_rows.append([_redact_cell(v) for v in row])
            else:
                new_rows.append(_redact_cell(row))
        out["rows"] = new_rows
    return out


def redact_preview_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Redact a Dataset preview response ``{columns, rows, row_count?}``."""
    if not isinstance(data, dict):
        return data
    redacted = redact_table_preview(data)
    if not isinstance(redacted, dict):
        return data
    out = dict(data)
    out.update(redacted)
    return out


def apply_output_guardrails(result_json: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow-copied result with summary/report/preview strings redacted."""
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
    if "table_preview" in out:
        out["table_preview"] = redact_table_preview(out.get("table_preview"))
    platform = dict(out.get("platform") or {})
    platform["guardrails"] = {
        "applied": True,
        "schema_version": 1,
        "covers": ["summary", "report", "limitations", "table_preview"],
    }
    out["platform"] = platform
    return out
