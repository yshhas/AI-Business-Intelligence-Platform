"""Workspace Memory MVP (Wave 3) — persist successful column synonyms for linking.

Not chat memory. Stores phrase → column token maps from succeeded data.bi Runs.
P1.3: TTL + per-workspace row cap with expire-then-LRU prune on write.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
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


def _compute_expires_at(now: datetime | None = None) -> datetime | None:
    settings = get_settings()
    days = int(settings.workspace_memory_ttl_days or 0)
    if days <= 0:
        return None
    base = now or datetime.now(UTC)
    return base + timedelta(days=days)


def prune_workspace_memory(
    db: Session,
    *,
    workspace_id: UUID,
    room_for: int = 0,
    protect_phrases: set[str] | None = None,
) -> int:
    """Delete expired rows, then LRU-evict until count + room_for <= cap.

    Rows whose phrase is in protect_phrases are not LRU-evicted (about to upsert).
    Returns number of rows deleted.
    """
    settings = get_settings()
    max_rows = max(1, int(settings.workspace_memory_max_rows or 2000))
    now = datetime.now(UTC)
    deleted = 0
    protect = {p for p in (protect_phrases or set()) if p}

    exp_result = db.execute(
        delete(WorkspaceColumnMemory).where(
            WorkspaceColumnMemory.workspace_id == workspace_id,
            WorkspaceColumnMemory.expires_at.is_not(None),
            WorkspaceColumnMemory.expires_at <= now,
        )
    )
    deleted += int(exp_result.rowcount or 0)

    count = int(
        db.scalar(
            select(func.count()).select_from(WorkspaceColumnMemory).where(
                WorkspaceColumnMemory.workspace_id == workspace_id
            )
        )
        or 0
    )
    overflow = count + max(0, room_for) - max_rows
    if overflow > 0:
        stmt = (
            select(WorkspaceColumnMemory)
            .where(WorkspaceColumnMemory.workspace_id == workspace_id)
            .order_by(
                WorkspaceColumnMemory.updated_at.asc(),
                WorkspaceColumnMemory.hit_count.asc(),
            )
        )
        if protect:
            stmt = stmt.where(WorkspaceColumnMemory.phrase.not_in(list(protect)))
        victims = list(db.scalars(stmt.limit(overflow)).all())
        for row in victims:
            db.delete(row)
            deleted += 1
    if deleted:
        db.flush()
    return deleted


def load_synonyms(
    db: Session,
    *,
    workspace_id: UUID,
    dataset_id: UUID | None = None,
    limit: int = 64,
) -> dict[str, list[str]]:
    now = datetime.now(UTC)
    live = or_(
        WorkspaceColumnMemory.expires_at.is_(None),
        WorkspaceColumnMemory.expires_at > now,
    )
    stmt = (
        select(WorkspaceColumnMemory)
        .where(
            WorkspaceColumnMemory.workspace_id == workspace_id,
            live,
        )
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

    phrases = phrases[:16]
    existing_phrases = {
        r.phrase
        for r in db.scalars(
            select(WorkspaceColumnMemory).where(
                WorkspaceColumnMemory.workspace_id == workspace_id,
                WorkspaceColumnMemory.dataset_id == dataset_id,
                WorkspaceColumnMemory.phrase.in_(phrases),
            )
        ).all()
    }
    new_count = sum(1 for p in phrases if p not in existing_phrases)
    phrase_set = set(phrases)
    prune_workspace_memory(
        db,
        workspace_id=workspace_id,
        room_for=new_count,
        protect_phrases=phrase_set,
    )

    expires = _compute_expires_at()
    touched = 0
    for phrase in phrases:
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
                expires_at=expires,
            )
            db.add(row)
            touched += 1
        else:
            merged = list(dict.fromkeys([*(row.column_tokens or []), *cols]))[:12]
            row.column_tokens = merged
            row.hit_count = int(row.hit_count or 0) + 1
            # Refresh TTL on hit; keep grandfather NULL only if TTL disabled
            row.expires_at = expires
            db.add(row)
            touched += 1
    db.flush()
    # Enforce cap after upsert in case protected phrases blocked enough LRU room.
    prune_workspace_memory(db, workspace_id=workspace_id, room_for=0)
    return touched
