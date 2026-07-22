"""Thin Data Plane protocol (Wave 3) — shared SELECT contract for file / RO planes.

Kernel/Skills never import this module; Product Shell Worker binds adapters.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DataPlane(Protocol):
    """Minimal read-only select plane used by Worker execute_select adapters."""

    source_type: str

    def run_select(
        self,
        sql: str,
        *,
        allowed_tables: set[str],
        default_limit: int,
    ) -> dict[str, Any]:
        """Execute Policy-gated SELECT; return {columns, rows, row_count}."""
        ...


SUPPORTED_SOURCE_TYPES = frozenset({"file", "postgres_ro", "mysql_ro"})
