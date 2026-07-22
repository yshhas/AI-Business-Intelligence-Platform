"""Persist and revoke refresh JWT ``jti`` sessions (P1.2).

Access tokens remain stateless. Refresh rotation revokes the previous ``jti``;
reuse of a revoked/unknown ``jti`` yields auth failure (no family kill-switch).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_token_pair, decode_token
from app.models.refresh_session import RefreshSession


class RefreshSessionError(Exception):
    """Invalid / revoked / expired refresh session."""


def _exp_from_payload(payload: dict) -> datetime:
    exp = payload.get("exp")
    if exp is None:
        raise RefreshSessionError("refresh token missing exp")
    if isinstance(exp, datetime):
        return exp if exp.tzinfo else exp.replace(tzinfo=UTC)
    return datetime.fromtimestamp(int(exp), tz=UTC)


def issue_token_pair(db: Session, *, user_id: UUID, email: str) -> tuple[str, str]:
    """Mint access+refresh and persist the refresh ``jti``."""
    access, refresh = create_token_pair(user_id=user_id, email=email)
    payload = decode_token(refresh, expected_type="refresh")
    jti = str(payload.get("jti") or "")
    if not jti:
        raise RefreshSessionError("refresh token missing jti")
    row = RefreshSession(
        id=uuid4(),
        jti=jti,
        user_id=user_id,
        expires_at=_exp_from_payload(payload),
        revoked_at=None,
        replaced_by_jti=None,
    )
    db.add(row)
    db.flush()
    return access, refresh


def get_active_session(db: Session, *, jti: str) -> RefreshSession:
    now = datetime.now(UTC)
    row = db.execute(
        select(RefreshSession).where(RefreshSession.jti == jti)
    ).scalar_one_or_none()
    if row is None:
        raise RefreshSessionError("unknown refresh session")
    if row.revoked_at is not None:
        raise RefreshSessionError("refresh session revoked")
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp <= now:
        raise RefreshSessionError("refresh session expired")
    return row


def revoke_session(db: Session, row: RefreshSession, *, replaced_by_jti: str | None = None) -> None:
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
    if replaced_by_jti:
        row.replaced_by_jti = replaced_by_jti
    db.add(row)
    db.flush()


def revoke_jti(db: Session, *, jti: str) -> bool:
    """Revoke by jti. Returns True if a row was found (already-revoked counts as found)."""
    row = db.execute(
        select(RefreshSession).where(RefreshSession.jti == jti)
    ).scalar_one_or_none()
    if row is None:
        return False
    revoke_session(db, row)
    return True


def rotate_refresh(
    db: Session,
    *,
    user_id: UUID,
    email: str,
    old_jti: str,
) -> tuple[str, str]:
    """Validate ``old_jti``, revoke it, issue a new pair. Reuse of old_jti → error."""
    old = get_active_session(db, jti=old_jti)
    if old.user_id != user_id:
        raise RefreshSessionError("refresh session user mismatch")
    access, new_refresh = issue_token_pair(db, user_id=user_id, email=email)
    new_payload = decode_token(new_refresh, expected_type="refresh")
    new_jti = str(new_payload.get("jti") or "")
    revoke_session(db, old, replaced_by_jti=new_jti or None)
    return access, new_refresh
