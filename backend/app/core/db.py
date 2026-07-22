from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.db_dialect import build_dialect_profile

_settings = get_settings()
_profile = build_dialect_profile(_settings.database_url)

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    connect_args=_profile.connect_args,
)


if _profile.enable_sqlite_fk_pragma:

    @event.listens_for(Engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_dialect_name() -> str:
    """Expose current dialect for health/debug; services should not branch on this."""
    return _profile.name
