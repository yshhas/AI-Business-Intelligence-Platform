"""HITL SQL snapshot helpers — pure functions (no FastAPI / SQLAlchemy).

Lifecycle:
  plan Gate allow → attach_snapshot_on_park (sql + sql_snapshot + sql_sha256)
  approve → resume CAS (unchanged)
  execute → verify_sql_snapshot (fail-closed) → approved_sql_from_hitl
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

# Stable reason codes for Trace / platform.hitl.snapshot_check
REASON_OK = "ok"
REASON_SQL_MISSING = "sql_missing"
REASON_HASH_MISSING = "hash_missing"
REASON_HASH_INVALID = "hash_invalid"
REASON_MISMATCH = "mismatch"
REASON_SNAPSHOT_TEXT_MISSING = "snapshot_text_missing"
REASON_SQL_SNAPSHOT_DIVERGE = "sql_snapshot_diverge"

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SnapshotVerifyResult:
    ok: bool
    reason_code: str
    message: str
    sql_snapshot: str | None = None
    expected_sha256: str | None = None
    actual_sha256: str | None = None


def normalize_sql_snapshot(sql: str | None) -> str:
    """Canonical form used for hashing and execute-only approved_sql."""
    if not isinstance(sql, str):
        return ""
    return sql.strip()


def compute_sql_sha256(sql: str) -> str:
    """SHA-256 hex digest of normalized SQL (UTF-8)."""
    normalized = normalize_sql_snapshot(sql)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def attach_snapshot_on_park(result_json: dict[str, Any] | None) -> dict[str, Any]:
    """At HITL park: persist sql (normalized), sql_snapshot, sql_sha256 under platform.hitl.

    Does not change Run status. Caller merges into awaiting_approval payload.
    """
    base = dict(result_json or {})
    sql_norm = normalize_sql_snapshot(base.get("sql") if isinstance(base.get("sql"), str) else None)
    # Keep result_json.sql aligned with the hashed snapshot (fail-closed later)
    if sql_norm:
        base["sql"] = sql_norm
    platform = dict(base.get("platform") or {})
    hitl = dict(platform.get("hitl") or {})
    if sql_norm:
        sha = compute_sql_sha256(sql_norm)
        hitl.update(
            {
                "required": True,
                "sql_snapshot": sql_norm,
                "sql_sha256": sha,
                "snapshot_algo": "sha256_utf8_strip",
            }
        )
    else:
        hitl.update(
            {
                "required": True,
                "sql_snapshot": None,
                "sql_sha256": None,
                "snapshot_algo": "sha256_utf8_strip",
            }
        )
    # Preserve phase if already set; park path usually sets phase=awaiting after this
    platform["hitl"] = hitl
    base["platform"] = platform
    return base


def verify_sql_snapshot(result_json: dict[str, Any] | None) -> SnapshotVerifyResult:
    """Fail-closed check before HITL execute.

    Rules:
    - result_json.sql (normalized) must be non-empty
    - platform.hitl.sql_sha256 must be present and valid 64-hex
    - platform.hitl.sql_snapshot should be present (T5); if present must equal sql
    - sha256(sql) must equal sql_sha256
    """
    base = result_json if isinstance(result_json, dict) else {}
    platform = base.get("platform") if isinstance(base.get("platform"), dict) else {}
    hitl = platform.get("hitl") if isinstance(platform.get("hitl"), dict) else {}

    sql_norm = normalize_sql_snapshot(base.get("sql") if isinstance(base.get("sql"), str) else None)
    if not sql_norm:
        return SnapshotVerifyResult(
            ok=False,
            reason_code=REASON_SQL_MISSING,
            message="HITL execute-only: approved SQL snapshot missing (result_json.sql)",
        )

    expected = hitl.get("sql_sha256")
    if expected is None or (isinstance(expected, str) and not expected.strip()):
        return SnapshotVerifyResult(
            ok=False,
            reason_code=REASON_HASH_MISSING,
            message="HITL execute-only: sql_sha256 missing",
            sql_snapshot=sql_norm,
        )
    if not isinstance(expected, str) or not _SHA256_HEX.match(expected.lower()):
        return SnapshotVerifyResult(
            ok=False,
            reason_code=REASON_HASH_INVALID,
            message="HITL execute-only: sql_sha256 invalid",
            sql_snapshot=sql_norm,
            expected_sha256=str(expected)[:80],
        )
    expected_l = expected.lower()

    actual = compute_sql_sha256(sql_norm)
    snap_text = hitl.get("sql_snapshot")

    if snap_text is not None and not isinstance(snap_text, str):
        return SnapshotVerifyResult(
            ok=False,
            reason_code=REASON_SNAPSHOT_TEXT_MISSING,
            message="HITL execute-only: platform.hitl.sql_snapshot invalid type",
            expected_sha256=expected_l,
            actual_sha256=actual,
        )

    if isinstance(snap_text, str) and snap_text.strip():
        snap_norm = normalize_sql_snapshot(snap_text)
        if snap_norm != sql_norm:
            return SnapshotVerifyResult(
                ok=False,
                reason_code=REASON_SQL_SNAPSHOT_DIVERGE,
                message="HITL execute-only: result_json.sql diverges from hitl.sql_snapshot",
                sql_snapshot=snap_norm,
                expected_sha256=expected_l,
                actual_sha256=actual,
            )
    else:
        # Pre-T5 parks: no sql_snapshot text — hash-only path below
        snap_norm = sql_norm

    if actual != expected_l:
        return SnapshotVerifyResult(
            ok=False,
            reason_code=REASON_MISMATCH,
            message="HITL SQL snapshot mismatch (fail-closed)",
            sql_snapshot=snap_norm,
            expected_sha256=expected_l,
            actual_sha256=actual,
        )

    return SnapshotVerifyResult(
        ok=True,
        reason_code=REASON_OK,
        message=(
            "ok"
            if isinstance(snap_text, str) and snap_text.strip()
            else "ok (hash-only; sql_snapshot absent — pre-T5 park)"
        ),
        sql_snapshot=snap_norm,
        expected_sha256=expected_l,
        actual_sha256=actual,
    )


def approved_sql_from_verified(result: SnapshotVerifyResult) -> str:
    """Return canonical approved SQL after a successful verify."""
    if not result.ok or not result.sql_snapshot:
        raise ValueError("approved_sql_from_verified called on failed snapshot check")
    return result.sql_snapshot


def snapshot_check_payload(result: SnapshotVerifyResult) -> dict[str, Any]:
    """Compact Trace payload under platform.hitl.snapshot_check."""
    payload: dict[str, Any] = {
        "ok": result.ok,
        "reason_code": result.reason_code,
        "message": result.message,
    }
    if result.expected_sha256:
        payload["expected_sha256"] = result.expected_sha256
    if result.actual_sha256:
        payload["actual_sha256"] = result.actual_sha256
    return payload
