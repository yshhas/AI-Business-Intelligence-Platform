"""Filesystem conventions for Phase 2 uploads + DuckDB.

Relative UPLOAD_DIR / DUCKDB_DIR values are resolved from the **repo root**,
not the process cwd, so running uvicorn from `backend/` stays consistent.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def repo_root() -> Path:
    # backend/app/core/storage_paths.py → parents[3] = repository root
    return Path(__file__).resolve().parents[3]


def resolve_configured_dir(configured: str) -> Path:
    path = Path(configured)
    if path.is_absolute():
        return path.resolve()
    return (repo_root() / path).resolve()


def upload_root() -> Path:
    return resolve_configured_dir(get_settings().upload_dir)


def duckdb_root() -> Path:
    return resolve_configured_dir(get_settings().duckdb_dir)


def ensure_storage_dirs() -> None:
    upload_root().mkdir(parents=True, exist_ok=True)
    duckdb_root().mkdir(parents=True, exist_ok=True)


def workspace_upload_dir(workspace_id: UUID) -> Path:
    path = upload_root() / str(workspace_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def duckdb_path_for_workspace(workspace_id: UUID) -> Path:
    duckdb_root().mkdir(parents=True, exist_ok=True)
    return duckdb_root() / f"{workspace_id}.duckdb"


def duckdb_table_name(dataset_id: UUID) -> str:
    # Stable, SQL-safe identifier derived from UUID (no hyphens).
    return f"ds_{dataset_id.hex}"


def sanitize_filename(filename: str) -> str:
    name = Path(filename).name  # drop any path components
    name = _SAFE_FILENAME.sub("_", name).strip("._")
    return name or "upload.bin"


def upload_file_path(workspace_id: UUID, dataset_id: UUID, original_filename: str) -> Path:
    safe = sanitize_filename(original_filename)
    return workspace_upload_dir(workspace_id) / f"{dataset_id}_{safe}"
