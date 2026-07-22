"""Database dialect helpers.

Business code should depend on SQLAlchemy Session + models only.
Dialect-specific quirks stay here so switching DATABASE_URL
(sqlite → postgresql+psycopg) does not require rewriting services/routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class DialectProfile:
    name: str  # "sqlite" | "postgresql" | "other"
    connect_args: dict[str, Any]
    enable_sqlite_fk_pragma: bool
    alembic_render_as_batch: bool


def dialect_name_from_url(database_url: str) -> str:
    # SQLAlchemy URLs look like: postgresql+psycopg://... or sqlite:///...
    scheme = urlparse(database_url).scheme.lower()
    driver = scheme.split("+", 1)[0]
    if driver.startswith("sqlite"):
        return "sqlite"
    if driver.startswith("postgres"):
        return "postgresql"
    return driver or "other"


def build_dialect_profile(database_url: str) -> DialectProfile:
    name = dialect_name_from_url(database_url)
    if name == "sqlite":
        return DialectProfile(
            name=name,
            # FastAPI may use the connection across threads in local smoke.
            connect_args={"check_same_thread": False},
            enable_sqlite_fk_pragma=True,
            # SQLite ALTER limitations → Alembic batch mode.
            alembic_render_as_batch=True,
        )
    # PostgreSQL (and default): no special connect args.
    return DialectProfile(
        name=name,
        connect_args={},
        enable_sqlite_fk_pragma=False,
        alembic_render_as_batch=False,
    )
