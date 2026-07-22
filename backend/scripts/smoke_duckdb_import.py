"""Smoke-test DuckDB import without HTTP (Phase 2 Step 2.2)."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from uuid import uuid4

from app.core.storage_paths import ensure_storage_dirs
from app.services import duckdb_service


def main() -> None:
    ensure_storage_dirs()
    workspace_id = uuid4()
    table = f"ds_{uuid4().hex}"

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "sales.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["region", "amount"])
            writer.writerow(["East", "100"])
            writer.writerow(["West", "250"])

        imported = duckdb_service.import_file(
            workspace_id=workspace_id,
            table_name=table,
            file_path=csv_path,
        )
        preview = duckdb_service.preview_table(
            workspace_id=workspace_id,
            table_name=table,
            limit=10,
        )

    print("SCHEMA", imported["schema"])
    print("ROWS", imported["row_count"])
    print("PREVIEW", preview)
    assert imported["row_count"] == 2
    assert preview["columns"] == ["region", "amount"]
    print("STEP22_OK")


if __name__ == "__main__":
    main()
