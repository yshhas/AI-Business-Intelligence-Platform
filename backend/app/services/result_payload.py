"""P1.4 — bound hot ``result_json`` before Worker persist (no object store).

Keeps Trace ``platform.execution`` on the hot path. Truncates heavy display
fields with explicit ``platform.payload`` omissions (not silent drop).
Artifacts are materialized **before** slim so refs remain valid against the
persisted (possibly truncated) fields.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.core.config import get_settings

_PAYLOAD_SCHEMA = 1
_TRUNCATION_NOTE = (
    "Hot result_json was truncated to respect RESULT_JSON_MAX_BYTES "
    "(see platform.payload). Full cold object store is not used in v1.1."
)


def _utf8_size(data: dict[str, Any]) -> int:
    return len(json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"))


def _ensure_platform(out: dict[str, Any]) -> dict[str, Any]:
    platform = dict(out.get("platform") or {})
    out["platform"] = platform
    return platform


def _record_omission(
    payload: dict[str, Any],
    *,
    field: str,
    reason: str,
    detail: dict[str, Any] | None = None,
) -> None:
    omissions = list(payload.get("omissions") or [])
    entry: dict[str, Any] = {"field": field, "reason": reason}
    if detail:
        entry.update(detail)
    omissions.append(entry)
    payload["omissions"] = omissions
    payload["truncated"] = True


def _append_limitation(out: dict[str, Any], note: str) -> None:
    lims = list(out.get("limitations") or [])
    if note not in lims:
        lims.append(note)
    out["limitations"] = lims


def slim_for_persist(result_json: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy safe to persist as hot ``analysis_tasks.result_json``."""
    if result_json is None:
        return None
    if not isinstance(result_json, dict):
        return result_json

    settings = get_settings()
    max_bytes = max(16 * 1024, int(settings.result_json_max_bytes or 256 * 1024))
    max_rows = max(1, int(settings.table_preview_hot_max_rows or 50))

    out = deepcopy(result_json)
    platform = _ensure_platform(out)
    # Never strip execution / authz / sql_quality / run — Trace contract.
    execution = platform.get("execution")
    payload = dict(platform.get("payload") or {})
    payload.setdefault("schema_version", _PAYLOAD_SCHEMA)
    payload.setdefault("truncated", False)
    payload.setdefault("omissions", [])

    # 1) Cap table_preview rows (keep columns)
    preview = out.get("table_preview")
    if isinstance(preview, dict):
        rows = preview.get("rows")
        if isinstance(rows, list) and len(rows) > max_rows:
            kept = rows[:max_rows]
            omitted = len(rows) - max_rows
            preview = dict(preview)
            preview["rows"] = kept
            preview["row_count"] = len(kept)
            preview["truncated"] = True
            preview["omitted_row_count"] = omitted
            out["table_preview"] = preview
            _record_omission(
                payload,
                field="table_preview.rows",
                reason="row_cap",
                detail={
                    "kept_rows": len(kept),
                    "omitted_rows": omitted,
                    "max_rows": max_rows,
                    "artifact_hint": "table artifact content_ref still points at hot table_preview (truncated)",
                },
            )

    # 2) Cap report.markdown length (keep title)
    report = out.get("report")
    if isinstance(report, dict) and isinstance(report.get("markdown"), str):
        md = report["markdown"]
        # Soft cap ~48 KiB of markdown before byte budget loop
        soft = 48 * 1024
        if len(md.encode("utf-8")) > soft:
            # Truncate on character boundary roughly by bytes
            encoded = md.encode("utf-8")[:soft]
            cut = encoded.decode("utf-8", errors="ignore")
            report = dict(report)
            report["markdown"] = cut + "\n\n…[truncated]"
            report["truncated"] = True
            out["report"] = report
            _record_omission(
                payload,
                field="report.markdown",
                reason="markdown_soft_cap",
                detail={
                    "original_bytes": len(md.encode("utf-8")),
                    "kept_bytes": len(cut.encode("utf-8")),
                    "artifact_hint": "report artifact content_ref points at hot report (truncated)",
                },
            )

    # 3) Byte budget — further shrink heavy fields if needed
    guard = 0
    while _utf8_size(out) > max_bytes and guard < 8:
        guard += 1
        preview = out.get("table_preview")
        if isinstance(preview, dict):
            rows = preview.get("rows")
            if isinstance(rows, list) and len(rows) > 0:
                new_len = max(0, len(rows) // 2)
                omitted = len(rows) - new_len
                preview = dict(preview)
                preview["rows"] = rows[:new_len]
                preview["row_count"] = new_len
                preview["truncated"] = True
                preview["omitted_row_count"] = int(preview.get("omitted_row_count") or 0) + omitted
                out["table_preview"] = preview
                _record_omission(
                    payload,
                    field="table_preview.rows",
                    reason="byte_budget",
                    detail={"kept_rows": new_len, "max_bytes": max_bytes},
                )
                continue
        report = out.get("report")
        if isinstance(report, dict) and isinstance(report.get("markdown"), str):
            md = report["markdown"]
            if len(md) > 256:
                report = dict(report)
                report["markdown"] = md[: max(64, len(md) // 2)] + "\n\n…[truncated]"
                report["truncated"] = True
                out["report"] = report
                _record_omission(
                    payload,
                    field="report.markdown",
                    reason="byte_budget",
                    detail={"max_bytes": max_bytes},
                )
                continue
        # Last resort: drop charts array bodies but keep empty list marker
        charts = out.get("charts")
        if isinstance(charts, list) and charts:
            out["charts"] = []
            _record_omission(
                payload,
                field="charts",
                reason="byte_budget",
                detail={
                    "omitted_charts": len(charts),
                    "artifact_hint": "chart artifacts may be unavailable if only hot charts were present",
                },
            )
            continue
        break

    if payload.get("truncated"):
        _append_limitation(out, _TRUNCATION_NOTE)
        payload["max_bytes"] = max_bytes

    # Restore execution if somehow lost (should never happen with deepcopy)
    if execution is not None:
        platform["execution"] = execution
    platform["payload"] = payload
    out["platform"] = platform
    if payload.get("truncated"):
        payload["hot_bytes"] = _utf8_size(out)
        platform["payload"] = payload
        out["platform"] = platform
    return out
