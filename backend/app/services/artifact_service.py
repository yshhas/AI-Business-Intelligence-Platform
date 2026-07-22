"""M6 Artifact lifecycle — metadata in run_artifacts; payload via content_ref."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AnalysisTask, RunArtifact

# data.bi expected artifact types for unavailable stubs
DATA_BI_EXPECTED_TYPES = ("summary", "sql", "table", "chart", "report")

STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"


def materialize_for_task(
    db: Session,
    task: AnalysisTask,
    result_json: dict[str, Any] | None,
    *,
    skill_id: str = "data.bi",
) -> list[RunArtifact]:
    """Replace run_artifacts for this task from result_json + Trace ArtifactRefs.

    Payload is never copied — only content_ref into result_json fields.
    Missing expected types become status=unavailable.
    """
    db.execute(delete(RunArtifact).where(RunArtifact.task_id == task.id))
    db.flush()

    data = dict(result_json or {})
    platform = dict(data.get("platform") or {})
    execution = dict(platform.get("execution") or {})
    refs = [r for r in list(execution.get("artifacts") or []) if isinstance(r, dict)]
    sid = skill_id or platform.get("skill_id") or "data.bi"

    rows: list[RunArtifact] = []
    seen_types: set[str] = set()

    if refs:
        chart_index = 0
        for ref in refs:
            art_type = str(ref.get("type") or "")
            if not art_type:
                continue
            seen_types.add(art_type)
            artifact_id = _parse_uuid(ref.get("artifact_id")) or uuid4()
            content_ref, title, available = _content_ref_for(
                art_type, data, ref=ref, chart_index=chart_index
            )
            if art_type == "chart":
                chart_index += 1
            rows.append(
                _add_row(
                    db,
                    task,
                    artifact_id=artifact_id,
                    art_type=art_type,
                    status=STATUS_AVAILABLE if available else STATUS_UNAVAILABLE,
                    content_ref=content_ref,
                    title=title,
                    skill_id=sid,
                )
            )
    else:
        # No Trace refs (e.g. mock) — invent metadata from legacy result_json fields
        for art_type in DATA_BI_EXPECTED_TYPES:
            if art_type == "chart":
                charts = data.get("charts") or []
                if isinstance(charts, list) and charts:
                    for i, ch in enumerate(charts):
                        content_ref, title, available = _content_ref_for(
                            art_type, data, ref={}, chart_index=i
                        )
                        rows.append(
                            _add_row(
                                db,
                                task,
                                artifact_id=uuid4(),
                                art_type=art_type,
                                status=(
                                    STATUS_AVAILABLE
                                    if available
                                    else STATUS_UNAVAILABLE
                                ),
                                content_ref=content_ref,
                                title=title,
                                skill_id=sid,
                            )
                        )
                    seen_types.add("chart")
                continue
            content_ref, title, available = _content_ref_for(
                art_type, data, ref={}, chart_index=0
            )
            if not available:
                continue
            seen_types.add(art_type)
            rows.append(
                _add_row(
                    db,
                    task,
                    artifact_id=uuid4(),
                    art_type=art_type,
                    status=STATUS_AVAILABLE,
                    content_ref=content_ref,
                    title=title,
                    skill_id=sid,
                )
            )

    # Unavailable stubs for expected types never produced
    for art_type in DATA_BI_EXPECTED_TYPES:
        if art_type in seen_types:
            continue
        content_ref = {"storage": "result_json", "field": _legacy_field(art_type)}
        rows.append(
            _add_row(
                db,
                task,
                artifact_id=uuid4(),
                art_type=art_type,
                status=STATUS_UNAVAILABLE,
                content_ref=content_ref,
                title=None,
                skill_id=sid,
            )
        )

    _sync_execution_artifact_refs(data, rows)
    task.result_json = data
    db.flush()
    return rows


def list_for_task(
    db: Session, *, workspace_id: UUID, task_id: UUID
) -> list[RunArtifact]:
    stmt = (
        select(RunArtifact)
        .where(
            RunArtifact.task_id == task_id,
            RunArtifact.workspace_id == workspace_id,
        )
        .order_by(RunArtifact.created_at.asc())
    )
    return list(db.scalars(stmt).all())


def get_for_task(
    db: Session, *, workspace_id: UUID, task_id: UUID, artifact_id: UUID
) -> RunArtifact | None:
    return db.execute(
        select(RunArtifact).where(
            RunArtifact.id == artifact_id,
            RunArtifact.task_id == task_id,
            RunArtifact.workspace_id == workspace_id,
        )
    ).scalar_one_or_none()


def resolve_payload(task: AnalysisTask, artifact: RunArtifact) -> Any:
    """Load payload from result_json via content_ref (no CMS)."""
    if artifact.status != STATUS_AVAILABLE:
        return None
    data = dict(task.result_json or {})
    ref = dict(artifact.content_ref or {})
    field = ref.get("field")
    if not field:
        return None
    if field == "charts":
        charts = data.get("charts") or []
        if not isinstance(charts, list):
            return None
        idx = ref.get("index")
        chart_id = ref.get("chart_id")
        if chart_id:
            for ch in charts:
                if isinstance(ch, dict) and str(ch.get("id")) == str(chart_id):
                    return ch
        if isinstance(idx, int) and 0 <= idx < len(charts):
            return charts[idx]
        return charts[0] if charts else None
    return data.get(field)


def lineage_for(task: AnalysisTask, artifact: RunArtifact) -> dict[str, Any]:
    platform = dict((task.result_json or {}).get("platform") or {})
    plane = platform.get("data_plane") or {}
    return {
        "run_id": str(task.id),
        "artifact_id": str(artifact.id),
        "skill_id": artifact.skill_id or platform.get("skill_id") or "data.bi",
        "dataset_id": str(task.dataset_id),
        "source_type": task.source_type
        or (plane.get("source_type") if isinstance(plane, dict) else None),
        "failure_class": task.failure_class,
        "run_status": task.status,
        "trace": {
            "path": f"/api/v1/workspaces/{task.workspace_id}/tasks/{task.id}/execution"
        },
    }


def _add_row(
    db: Session,
    task: AnalysisTask,
    *,
    artifact_id: UUID,
    art_type: str,
    status: str,
    content_ref: dict[str, Any],
    title: str | None,
    skill_id: str,
) -> RunArtifact:
    row = RunArtifact(
        id=artifact_id,
        task_id=task.id,
        workspace_id=task.workspace_id,
        type=art_type,
        status=status,
        content_ref=content_ref,
        title=title,
        skill_id=skill_id,
    )
    db.add(row)
    return row


def _legacy_field(art_type: str) -> str:
    return {
        "summary": "summary",
        "sql": "sql",
        "table": "table_preview",
        "chart": "charts",
        "report": "report",
    }.get(art_type, art_type)


def _content_ref_for(
    art_type: str,
    data: dict[str, Any],
    *,
    ref: dict[str, Any],
    chart_index: int,
) -> tuple[dict[str, Any], str | None, bool]:
    field = _legacy_field(art_type)
    content_ref: dict[str, Any] = {"storage": "result_json", "field": field}
    title = None
    available = False

    if art_type == "summary":
        text = data.get("summary")
        available = isinstance(text, str)  # empty string still "available"
    elif art_type == "sql":
        available = data.get("sql") is not None
    elif art_type == "table":
        preview = data.get("table_preview")
        available = isinstance(preview, dict)
    elif art_type == "chart":
        charts = data.get("charts") or []
        content_ref["index"] = chart_index
        existing = ref.get("ref") if isinstance(ref.get("ref"), dict) else {}
        chart_id = existing.get("chart_id")
        if chart_id:
            content_ref["chart_id"] = chart_id
        elif isinstance(charts, list) and chart_index < len(charts):
            ch = charts[chart_index]
            if isinstance(ch, dict) and ch.get("id"):
                content_ref["chart_id"] = ch.get("id")
            title = (
                str(ch.get("title") or "") or None if isinstance(ch, dict) else None
            )
        available = isinstance(charts, list) and len(charts) > chart_index
    elif art_type == "report":
        report = data.get("report")
        available = isinstance(report, dict) and bool(report)
        if available and isinstance(report, dict):
            title = str(report.get("title") or "") or None
    else:
        available = False

    if not title and isinstance(ref.get("title"), str):
        title = ref["title"]
    return content_ref, title, available


def _parse_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _sync_execution_artifact_refs(
    result_json: dict[str, Any], rows: list[RunArtifact]
) -> None:
    platform = dict(result_json.get("platform") or {})
    execution = dict(platform.get("execution") or {})
    synced = []
    for row in rows:
        synced.append(
            {
                "artifact_id": str(row.id),
                "type": row.type,
                "status": row.status,
                "ref": dict(row.content_ref or {}),
            }
        )
    execution["artifacts"] = synced
    summary = dict(execution.get("summary") or {})
    summary["artifact_count"] = len(synced)
    summary["artifact_types"] = [r.type for r in rows]
    execution["summary"] = summary
    platform["execution"] = execution
    platform["artifact_types"] = [
        r.type for r in rows if r.status == STATUS_AVAILABLE
    ]
    result_json["platform"] = platform
