"""P1.4 smoke: hot result_json slim keeps Trace execution; truncates with explicit payload."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ["RESULT_JSON_MAX_BYTES"] = str(32 * 1024)
os.environ["TABLE_PREVIEW_HOT_MAX_ROWS"] = "5"

from app.core.config import get_settings  # noqa: E402
from app.services.result_payload import slim_for_persist  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.result_json_max_bytes == 32 * 1024
    assert settings.table_preview_hot_max_rows == 5

    rows = [{"email": f"u{i}@example.com", "n": i, "blob": "x" * 200} for i in range(40)]
    fat = {
        "summary": "ok",
        "sql": "SELECT 1",
        "table_preview": {"columns": ["email", "n", "blob"], "rows": rows, "row_count": 40},
        "report": {"title": "R", "markdown": ("# H\n" + ("para " * 5000))},
        "charts": [{"type": "bar", "title": "c", "data": [{"x": i, "y": i} for i in range(100)]}],
        "platform": {
            "skill_id": "data.bi",
            "execution": {
                "schema_version": 1,
                "tool_calls": [{"tool": "sql.execute"}],
                "summary": {"tool_count": 1, "incomplete": False},
            },
        },
    }
    slim = slim_for_persist(fat)
    assert slim is not None
    payload = (slim.get("platform") or {}).get("payload") or {}
    assert payload.get("truncated") is True
    assert payload.get("omissions")
    assert (slim.get("platform") or {}).get("execution", {}).get("tool_calls")
    preview = slim.get("table_preview") or {}
    assert isinstance(preview.get("rows"), list)
    assert len(preview["rows"]) <= 5
    assert preview.get("truncated") is True
    assert "omitted_row_count" in preview
    # Byte budget under configured max (allow small overhead for metadata)
    import json

    size = len(json.dumps(slim, ensure_ascii=False, default=str).encode("utf-8"))
    assert size <= settings.result_json_max_bytes + 2048, size
    print(f"RESULT_PAYLOAD_SLIM_OK bytes={size} omissions={len(payload['omissions'])}")


if __name__ == "__main__":
    main()
