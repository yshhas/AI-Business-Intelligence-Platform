"""Ensure monorepo root is on sys.path so `agent` can be imported from backend workers."""

from __future__ import annotations

import sys
from pathlib import Path


def ensure_repo_root_on_path() -> Path:
    # backend/app/core/repo_path.py → parents[3] = repo root
    root = Path(__file__).resolve().parents[3]
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    return root
