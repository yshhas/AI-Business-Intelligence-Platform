"""Workspace Memory MVP (Wave 3) — persist successful column synonyms for linking.

Not chat memory. Stores phrase → column token maps from succeeded data.bi Runs.
"""

from __future__ import annotations

import re
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WorkspaceColumnMemory

_TOKEN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]{2,}")


def _phrases_from_question(question: str) -> list[str]:
    q = (question or "").strip().lower()
    if not q:
        return []
    tokens = _TOKEN.findall(q)
    # Keep short phrases: unigrams + adjacent bigrams (cap)
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t not in seen:
            out.append(t)
            seen.add(t)
        if len(out) >= 12:
            break
    for i in range(len(tokens) - 1):
        big = f"{tokens[i]} {tokens[i + 1]}"
        if big not in seen:
            out.append(big)
            seen.add(big)
        if len(out) >= 20:
            break
    return out


def load_synonyms(
    db: Session,
    *,
    workspace_id: UUID,
    dataset_id: UUID | None = None,
    limit: int = 64,
) -> dict[str, list[str]]:
    stmt = (
        select(WorkspaceColumnMemory)
        .where(WorkspaceColumnMemory.workspace_id == workspace_id)
        .order_by(WorkspaceColumnMemory.hit_count.desc())
        .limit(limit)
    )
    if dataset_id is not None:
        stmt = stmt.where(
            (WorkspaceColumnMemory.dataset_id == dataset_id)
            | (WorkspaceColumnMemory.dataset_id.is_(None))
        )
    rows = list(db.scalars(stmt).all())
    out: dict[str, list[str]] = {}
    for row in rows:
        phrase = (row.phrase or "").strip().lower()
        cols = [str(c) for c in (row.column_tokens or []) if c]
        if phrase and cols:
            existing = out.get(phrase, [])
            merged = list(dict.fromkeys([*existing, *cols]))
            out[phrase] = merged
    return out


def remember_from_link(
    db: Session,
    *,
    workspace_id: UUID,
    dataset_id: UUID,
    question: str,
    selected_columns: list[str],
) -> int:
    """Upsert memory rows from a successful link_schema selection. Returns rows touched."""
    cols = [str(c).strip() for c in selected_columns if str(c).strip()]
    if not cols:
        return 0
    phrases = _phrases_from_question(question)
    if not phrases:
        return 0
    # Prefer column name tokens as phrases too
    for c in cols[:8]:
        low = c.lower()
        if low not in phrases:
            phrases.append(low)

    touched = 0
    for phrase in phrases[:16]:
        row = db.execute(
            select(WorkspaceColumnMemory).where(
                WorkspaceColumnMemory.workspace_id == workspace_id,
                WorkspaceColumnMemory.dataset_id == dataset_id,
                WorkspaceColumnMemory.phrase == phrase,
            )
        ).scalar_one_or_none()
        if row is None:
            row = WorkspaceColumnMemory(
                id=uuid4(),
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                phrase=phrase,
                column_tokens=cols[:12],
                hit_count=1,
            )
            db.add(row)
            touched += 1
        else:
            merged = list(dict.fromkeys([*(row.column_tokens or []), *cols]))[:12]
            row.column_tokens = merged
            row.hit_count = int(row.hit_count or 0) + 1
            db.add(row)
            touched += 1
    db.flush()
    return touched
