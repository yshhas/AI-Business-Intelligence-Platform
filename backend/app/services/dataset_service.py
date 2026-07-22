"""Dataset orchestration: file→DuckDB upload + M3 postgres_ro bind."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.storage_paths import (
    duckdb_table_name,
    ensure_storage_dirs,
    sanitize_filename,
    upload_file_path,
)
from app.models import Dataset
from app.services import duckdb_service, postgres_ro_service
from app.services.duckdb_service import DuckDBServiceError
from app.services.postgres_ro_service import ConnectorError


class DatasetServiceError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def list_datasets(
    db: Session,
    *,
    workspace_id: UUID,
    member=None,
    workspace=None,
) -> list[Dataset]:
    stmt = (
        select(Dataset)
        .where(Dataset.workspace_id == workspace_id)
        .order_by(Dataset.created_at.desc())
    )
    items = list(db.scalars(stmt).all())
    if member is None:
        return items
    from app.services.dataset_acl_service import filter_readable_datasets

    return filter_readable_datasets(
        db, datasets=items, member=member, workspace=workspace
    )


def get_dataset(db: Session, *, workspace_id: UUID, dataset_id: UUID) -> Dataset | None:
    stmt = select(Dataset).where(
        Dataset.id == dataset_id,
        Dataset.workspace_id == workspace_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def allowed_tables_for(
    dataset: Dataset,
    *,
    db: Session | None = None,
    user_id: UUID | None = None,
) -> set[str]:
    """Resolve Gate allowlist for a dataset (file / postgres_ro / mysql_ro).

    Wave 3: when DatasetAcl.tables_json is set for the actor, intersect with base allowlist.
    """
    if dataset.source_type == "postgres_ro":
        cfg = dataset.source_config_json or {}
        raw = cfg.get("allowed_tables") or [dataset.duckdb_table]
        try:
            base = set(postgres_ro_service.normalize_allowlist(list(raw)))
        except ConnectorError as exc:
            raise DatasetServiceError(str(exc), status_code=400) from exc
    elif dataset.source_type == "mysql_ro":
        from app.services import mysql_ro_service

        cfg = dataset.source_config_json or {}
        raw = cfg.get("allowed_tables") or [dataset.duckdb_table]
        try:
            base = set(mysql_ro_service.normalize_allowlist(list(raw)))
        except mysql_ro_service.ConnectorError as exc:
            raise DatasetServiceError(str(exc), status_code=400) from exc
    else:
        base = {dataset.duckdb_table}

    if db is None or user_id is None:
        return base
    from app.models import DatasetAcl

    entry = db.execute(
        select(DatasetAcl).where(
            DatasetAcl.dataset_id == dataset.id,
            DatasetAcl.user_id == user_id,
        )
    ).scalar_one_or_none()
    if entry is None or not entry.tables_json:
        return base
    subset = {str(t).strip() for t in entry.tables_json if str(t).strip()}
    if not subset:
        return base
    # Normalize postgres/mysql relations when possible
    projected = set()
    for t in subset:
        if dataset.source_type == "postgres_ro":
            try:
                projected.add(postgres_ro_service.normalize_relation(t))
            except ConnectorError:
                projected.add(t)
        elif dataset.source_type == "mysql_ro":
            from app.services import mysql_ro_service

            try:
                projected.add(mysql_ro_service.normalize_relation(t))
            except mysql_ro_service.ConnectorError:
                projected.add(t)
        else:
            projected.add(t)
    inter = base & projected
    if not inter:
        raise DatasetServiceError(
            "ACL table projection empty after intersect with dataset allowlist",
            status_code=403,
        )
    return inter



async def create_dataset_from_upload(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    upload: UploadFile,
    name: str | None = None,
) -> Dataset:
    ensure_storage_dirs()
    settings = get_settings()

    original = upload.filename or "upload.bin"
    safe_name = sanitize_filename(original)
    ext = Path(safe_name).suffix.lower()
    if ext not in duckdb_service.ALLOWED_EXTENSIONS:
        raise DatasetServiceError(
            f"Unsupported file type {ext!r}. Allowed: .csv, .xlsx",
            status_code=400,
        )

    dataset_id = uuid4()
    table = duckdb_table_name(dataset_id)
    dest = upload_file_path(workspace_id, dataset_id, safe_name)

    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise DatasetServiceError(
                        f"File exceeds max upload size ({settings.max_upload_bytes} bytes)",
                        status_code=413,
                    )
                out.write(chunk)
    except DatasetServiceError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        dest.unlink(missing_ok=True)
        raise DatasetServiceError(f"Failed to store upload: {exc}", status_code=500) from exc
    finally:
        await upload.close()

    display_name = (name or Path(safe_name).stem).strip() or "Untitled dataset"
    dataset = Dataset(
        id=dataset_id,
        workspace_id=workspace_id,
        name=display_name[:200],
        source_type="file",
        original_filename=safe_name,
        storage_path=str(dest),
        duckdb_table=table,
        schema_json=[],
        row_count=0,
        status="processing",
        source_config_json={},
        created_by=user_id,
    )
    db.add(dataset)
    db.flush()

    try:
        imported = duckdb_service.import_file(
            workspace_id=workspace_id,
            table_name=table,
            file_path=dest,
        )
        dataset.schema_json = imported["schema"]
        dataset.row_count = imported["row_count"]
        dataset.status = "ready"
    except DuckDBServiceError as exc:
        dataset.status = "failed"
        dataset.schema_json = []
        dataset.row_count = 0
        db.commit()
        db.refresh(dataset)
        raise DatasetServiceError(f"Import failed: {exc}", status_code=400) from exc

    db.commit()
    db.refresh(dataset)
    return dataset


def create_dataset_from_postgres_ro(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    name: str,
    tables: list[str],
) -> Dataset:
    """Bind a read-only Postgres source (thin M3 API — not a connector product)."""
    display = (name or "").strip() or "Postgres RO dataset"
    try:
        probed = postgres_ro_service.probe_and_describe(tables)
    except ConnectorError as exc:
        raise DatasetServiceError(str(exc), status_code=400) from exc

    primary = probed["primary_table"]
    allowed = probed["allowed_tables"]
    dataset = Dataset(
        id=uuid4(),
        workspace_id=workspace_id,
        name=display[:200],
        source_type="postgres_ro",
        original_filename="postgres_ro",
        storage_path="postgres_ro://default",
        duckdb_table=primary,
        schema_json=probed["schema"],
        row_count=probed["row_count"],
        status="ready",
        source_config_json={
            "connection_ref": "default",
            "allowed_tables": allowed,
        },
        created_by=user_id,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


def create_dataset_from_mysql_ro(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    name: str,
    tables: list[str],
) -> Dataset:
    """Bind a read-only MySQL source (Wave 3 thin plane — DSN from MYSQL_RO_DSN only)."""
    from app.services import mysql_ro_service

    display = (name or "").strip() or "MySQL RO dataset"
    try:
        probed = mysql_ro_service.probe_tables(tables)
    except mysql_ro_service.ConnectorError as exc:
        raise DatasetServiceError(str(exc), status_code=400) from exc

    primary = probed["primary_table"]
    allowed = probed["allowed_tables"]
    dataset = Dataset(
        id=uuid4(),
        workspace_id=workspace_id,
        name=display[:200],
        source_type="mysql_ro",
        original_filename="mysql_ro",
        storage_path="mysql_ro://default",
        duckdb_table=primary,
        schema_json=probed["schema_json"],
        row_count=probed["row_count"],
        status="ready",
        source_config_json={
            "connection_ref": "default",
            "allowed_tables": allowed,
        },
        created_by=user_id,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


def preview_dataset(
    db: Session,
    *,
    workspace_id: UUID,
    dataset_id: UUID,
    limit: int = 50,
) -> dict:
    dataset = get_dataset(db, workspace_id=workspace_id, dataset_id=dataset_id)
    if dataset is None:
        raise DatasetServiceError("Dataset not found", status_code=404)
    if dataset.status != "ready":
        raise DatasetServiceError(
            f"Dataset is not ready (status={dataset.status})",
            status_code=409,
        )
    try:
        if dataset.source_type == "postgres_ro":
            allowed = allowed_tables_for(dataset)
            raw = postgres_ro_service.preview_table(
                primary_table=dataset.duckdb_table,
                allowed_tables=allowed,
                limit=limit,
            )
            return _apply_preview_guardrails(raw)
        if dataset.source_type == "mysql_ro":
            from app.services import mysql_ro_service

            allowed = allowed_tables_for(dataset)
            # Minimal preview via SELECT * LIMIT
            rel = dataset.duckdb_table
            db_name, table = rel.split(".", 1)
            sql = f"SELECT * FROM `{db_name}`.`{table}` LIMIT {int(limit)}"
            preview = mysql_ro_service.run_select(
                sql, allowed_tables=allowed, default_limit=limit
            )
            cols = preview.get("columns") or []
            rows = preview.get("rows") or []
            if rows and isinstance(rows[0], dict):
                dict_rows = rows
            else:
                dict_rows = [dict(zip(cols, r, strict=False)) for r in rows]
            return _apply_preview_guardrails(
                {
                    "columns": cols,
                    "rows": dict_rows,
                    "row_count": len(dict_rows),
                }
            )
        if dataset.source_type != "file":
            raise DatasetServiceError(
                f"Unsupported source_type={dataset.source_type!r}",
                status_code=400,
            )
        raw = duckdb_service.preview_table(
            workspace_id=workspace_id,
            table_name=dataset.duckdb_table,
            limit=limit,
        )
        return _apply_preview_guardrails(raw)
    except ConnectorError as exc:
        raise DatasetServiceError(str(exc), status_code=400) from exc
    except Exception as exc:  # noqa: BLE001
        from app.services import mysql_ro_service

        if isinstance(exc, mysql_ro_service.ConnectorError):
            raise DatasetServiceError(str(exc), status_code=400) from exc
        if isinstance(exc, DuckDBServiceError):
            raise DatasetServiceError(str(exc), status_code=400) from exc
        raise


def _apply_preview_guardrails(data: dict) -> dict:
    """P1.7: same string redaction as Facade table_preview (not Policy Gate)."""
    try:
        from app.core.repo_path import ensure_repo_root_on_path

        ensure_repo_root_on_path()
        from agent.guardrails import redact_preview_payload

        return redact_preview_payload(data)
    except Exception:  # noqa: BLE001 — preview must not fail closed on guardrails import
        return data
