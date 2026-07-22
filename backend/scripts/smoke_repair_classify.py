"""Unit smoke: agent.repair_classify.classify_repair_error."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.repair_classify import classify_repair_error  # noqa: E402


def main() -> None:
    assert classify_repair_error(None) == "unknown"
    assert classify_repair_error("") == "unknown"

    assert classify_repair_error("table not in allowlist") == "policy_allowlist"
    assert classify_repair_error("unknown table foo") == "policy_allowlist"

    assert classify_repair_error("forbidden keyword DROP") == "policy_keyword"
    assert classify_repair_error("DDL statements not allowed") == "policy_keyword"

    assert classify_repair_error("LIMIT missing in query") == "policy_limit"
    assert classify_repair_error("LIMIT exceeds maximum") == "policy_limit"

    assert classify_repair_error("SQL policy violation") == "policy_other"

    assert classify_repair_error("syntax error near FROM") == "engine_syntax"
    assert classify_repair_error("unexpected token") == "engine_syntax"

    assert classify_repair_error("no rows returned", stage="execute") == "empty_result"
    assert classify_repair_error("result set empty", stage="execute") == "empty_result"

    assert classify_repair_error("connection reset", stage="execute") == "engine_runtime"
    assert classify_repair_error("something went wrong", stage="validate") == "unknown"

    print("REPAIR_CLASSIFY_OK")


if __name__ == "__main__":
    main()
