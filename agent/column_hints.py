"""Shared column-name hints for dimension / metric / temporal inference.

Used by:
  - charts.py      (_pick_fields, _column_looks_numeric, _is_temporal_name)
  - prompts_sql.py (_few_shot_examples)

All three sets are immutable (frozenset) to prevent accidental mutation.
"""

from __future__ import annotations

DIM_HINTS: frozenset[str] = frozenset({
    "region", "area", "category", "product", "name",
    "dim", "city", "country", "month", "date", "day", "week",
})

METRIC_HINTS: frozenset[str] = frozenset({
    "amount", "sales", "revenue", "qty", "quantity", "total",
    "value", "count", "sum", "avg", "mean",
})

TEMPORAL_HINTS: frozenset[str] = frozenset({
    "date", "day", "month", "week", "year", "time", "timestamp",
})