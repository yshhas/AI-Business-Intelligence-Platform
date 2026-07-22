"""Quick xlsx first-sheet import check."""
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook

from app.core.storage_paths import ensure_storage_dirs
from app.services import duckdb_service

ensure_storage_dirs()
ws_id = uuid4()
table = f"ds_{uuid4().hex}"
path = Path("..") / "data" / "uploads" / f"_xlsx_smoke_{ws_id}.xlsx"
path.parent.mkdir(parents=True, exist_ok=True)
wb = Workbook()
sheet = wb.active
sheet.append(["product", "qty"])
sheet.append(["A", 3])
sheet.append(["B", 7])
wb.save(path)
try:
    out = duckdb_service.import_file(workspace_id=ws_id, table_name=table, file_path=path)
    print(out)
    print("XLSX_OK")
except Exception as e:
    print("XLSX_FAIL", type(e), e)
finally:
    path.unlink(missing_ok=True)
