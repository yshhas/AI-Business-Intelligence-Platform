from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SchemaColumn(BaseModel):
    name: str
    type: str


class DatasetOut(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    source_type: str
    original_filename: str
    duckdb_table: str
    schema_json: list[dict[str, Any]]
    row_count: int
    status: str
    source_config_json: dict[str, Any] = Field(default_factory=dict)
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetListOut(BaseModel):
    items: list[DatasetOut]


class PreviewOut(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(description="Rows returned in this preview (≤ limit)")


class PostgresRoBindIn(BaseModel):
    """Thin bind request — tables must be public.* (1–2). DSN from env only."""

    name: str = Field(min_length=1, max_length=200)
    tables: list[str] = Field(
        min_length=1,
        max_length=2,
        description="Schema-qualified relations, e.g. public.demo_orders",
    )


class MysqlRoBindIn(BaseModel):
    """Thin MySQL RO bind — tables database.table (1–2). DSN from MYSQL_RO_DSN only."""

    name: str = Field(min_length=1, max_length=200)
    tables: list[str] = Field(min_length=1, max_length=2)


class DatasetAclGrantIn(BaseModel):
    user_id: UUID
    can_read: bool = True
    can_run: bool = False
    # Wave 3: optional subset of dataset allowlist projected into SQL Gate
    tables: list[str] | None = None


class DatasetAclReplaceIn(BaseModel):
    """Replace all grants for a dataset. Empty list ⇒ default_open (M5 compat)."""

    grants: list[DatasetAclGrantIn] = Field(default_factory=list)


class DatasetAclOut(BaseModel):
    id: UUID
    workspace_id: UUID
    dataset_id: UUID
    user_id: UUID
    can_read: bool
    can_run: bool
    tables_json: list[str] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetAclListOut(BaseModel):
    items: list[DatasetAclOut]
