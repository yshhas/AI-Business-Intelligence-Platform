"""Schema Linking v2 — deterministic column/table selection before Text-to-SQL.

Skill-local only. No LLM, no Kernel/Policy/Plane changes.
Outcomes are always classified (ok | partial | fallback_full | failed) — no silent fallback.

v2: builtin + injected synonym expansion (business jargon → column tokens).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

DEFAULT_MAX_COLUMNS = 12
SCHEMA_LINK_VERSION = "link-v2.0.0"

_TOKEN_RE = re.compile(r"[a-z0-9\u4e00-\u9fff]+", re.IGNORECASE)
_SPLIT_NAME_RE = re.compile(r"[_\-\s]+")

# Builtin synonyms: phrase/token → column-name tokens to inject into the haystack.
# Keep small and deterministic; datasets may override via schema_synonyms.
BUILTIN_SYNONYMS: dict[str, list[str]] = {
    "销售额": ["amount", "sales", "revenue"],
    "销售": ["amount", "sales", "revenue"],
    "营收": ["amount", "revenue", "sales"],
    "金额": ["amount", "value", "total"],
    "数量": ["qty", "quantity", "amount"],
    "区域": ["region", "area"],
    "地区": ["region", "area"],
    "省份": ["region", "province"],
    "城市": ["city", "region"],
    "产品": ["product", "item", "sku"],
    "商品": ["product", "item"],
    "品类": ["category", "product"],
    "客户": ["customer", "client"],
    "订单": ["order", "order_id"],
    "日期": ["date", "day", "order_date"],
    "时间": ["date", "time", "timestamp"],
    "汇总": ["amount", "total", "sum"],
    "合计": ["amount", "total", "sum"],
    "revenue": ["amount", "sales"],
    "sales": ["amount", "revenue"],
    "turnover": ["amount", "sales", "revenue"],
}


@dataclass
class LinkResult:
    link_status: str  # ok | partial | fallback_full | failed
    link_method: str  # token_overlap | synonym_overlap | fallback_full | identity
    link_reason: str | None
    selected_tables: list[str]
    selected_columns: list[str]
    column_count_full: int
    column_count_linked: int
    scores: dict[str, float] = field(default_factory=dict)
    synonyms_applied: list[str] = field(default_factory=list)
    schema_link_version: str = SCHEMA_LINK_VERSION

    def as_step_output(self) -> dict[str, Any]:
        return {
            "link_status": self.link_status,
            "link_method": self.link_method,
            "link_reason": self.link_reason,
            "selected_tables": list(self.selected_tables),
            "selected_columns": list(self.selected_columns),
            "column_count_full": self.column_count_full,
            "column_count_linked": self.column_count_linked,
            "synonyms_applied": list(self.synonyms_applied),
            "schema_link_version": self.schema_link_version,
            # Recall-oriented: how much of the wide schema was kept
            "link_recall_ratio": (
                round(self.column_count_linked / self.column_count_full, 4)
                if self.column_count_full
                else None
            ),
        }

    def as_platform_sql_quality(self) -> dict[str, Any]:
        out = self.as_step_output()
        out["schema_version"] = 2
        return out


def _column_names(schema: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for col in schema or []:
        if not isinstance(col, dict):
            continue
        name = col.get("name")
        if name is None or str(name).strip() == "":
            continue
        names.append(str(name))
    return names


def _merge_synonyms(
    extra: Mapping[str, list[str]] | None,
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {k.lower(): list(v) for k, v in BUILTIN_SYNONYMS.items()}
    if extra:
        for key, vals in extra.items():
            if not key or not vals:
                continue
            k = str(key).strip().lower()
            bucket = merged.setdefault(k, [])
            for v in vals:
                token = str(v).strip().lower()
                if token and token not in bucket:
                    bucket.append(token)
    return merged


def _expand_haystack(
    question: str,
    *,
    synonyms: Mapping[str, list[str]],
) -> tuple[str, list[str]]:
    """Lowercased question + synonym column tokens; returns (haystack, applied keys)."""
    q = (question or "").strip()
    lower = q.lower()
    applied: list[str] = []
    extras: list[str] = []
    # Longer keys first so「销售额」beats「销售」
    for key in sorted(synonyms.keys(), key=len, reverse=True):
        if len(key) < 2:
            continue
        if key in lower or key in q:
            applied.append(key)
            extras.extend(synonyms[key])
    hay = lower
    if extras:
        hay = f"{lower} {' '.join(extras)}"
    return hay, applied


def _name_tokens(name: str) -> list[str]:
    parts = _SPLIT_NAME_RE.split(str(name).strip())
    tokens: list[str] = []
    for p in parts:
        tokens.extend(_TOKEN_RE.findall(p.lower()))
    if not tokens and name:
        tokens = [str(name).lower()]
    return tokens


def _score_column(name: str, hay: str) -> float:
    """Deterministic overlap score: higher = better match to the question."""
    if not hay:
        return 0.0
    lower = name.lower()
    score = 0.0
    if lower and lower in hay:
        score += 3.0 + min(len(lower), 12) * 0.05
    for tok in _name_tokens(name):
        if len(tok) < 2:
            continue
        if tok in hay:
            score += 1.0 + min(len(tok), 8) * 0.05
    return score


def link_schema(
    *,
    question: str,
    schema: list[dict[str, Any]],
    table: str,
    allowed_tables: list[str] | None = None,
    max_columns: int = DEFAULT_MAX_COLUMNS,
    synonyms: Mapping[str, list[str]] | None = None,
) -> LinkResult:
    """Select primary-table columns for the Text-to-SQL prompt."""
    cols = _column_names(schema)
    full_n = len(cols)
    k = max(1, int(max_columns) if max_columns else DEFAULT_MAX_COLUMNS)
    syn_map = _merge_synonyms(synonyms)

    tables: list[str] = []
    if table:
        tables.append(table)
    for t in allowed_tables or []:
        if t and t not in tables:
            tables.append(t)
    if not tables and table:
        tables = [table]

    if full_n == 0:
        return LinkResult(
            link_status="failed",
            link_method="token_overlap",
            link_reason="schema_empty",
            selected_tables=tables,
            selected_columns=[],
            column_count_full=0,
            column_count_linked=0,
            scores={},
        )

    # Schema already within budget — identity (still observable).
    if full_n <= k:
        return LinkResult(
            link_status="ok",
            link_method="identity",
            link_reason="within_k_noop",
            selected_tables=tables,
            selected_columns=list(cols),
            column_count_full=full_n,
            column_count_linked=full_n,
            scores={c: 0.0 for c in cols},
        )

    hay, applied = _expand_haystack(question, synonyms=syn_map)
    scores = {c: _score_column(c, hay) for c in cols}
    ranked = sorted(cols, key=lambda c: (-scores[c], cols.index(c)))
    positive = [c for c in ranked if scores[c] > 0]

    if not positive:
        linked = ranked[:k]
        return LinkResult(
            link_status="fallback_full",
            link_method="fallback_full",
            link_reason="no_token_overlap",
            selected_tables=tables,
            selected_columns=linked,
            column_count_full=full_n,
            column_count_linked=len(linked),
            scores=scores,
            synonyms_applied=applied,
        )

    linked = positive[:k]
    max_pos = max(scores[c] for c in linked)
    if len(linked) < 2 or max_pos < 1.5:
        status = "partial"
        reason = "weak_coverage"
    else:
        status = "ok"
        reason = "synonym_hit" if applied else None

    method = "synonym_overlap" if applied else "token_overlap"
    return LinkResult(
        link_status=status,
        link_method=method,
        link_reason=reason,
        selected_tables=tables,
        selected_columns=linked,
        column_count_full=full_n,
        column_count_linked=len(linked),
        scores=scores,
        synonyms_applied=applied,
    )


def filter_schema_by_columns(
    schema: list[dict[str, Any]],
    selected_columns: list[str],
) -> list[dict[str, Any]]:
    """Preserve selected_columns order; drop unknown names."""
    by_name = {
        str(c.get("name")): c
        for c in (schema or [])
        if isinstance(c, dict) and c.get("name") is not None
    }
    out: list[dict[str, Any]] = []
    for name in selected_columns or []:
        col = by_name.get(str(name))
        if col is not None:
            out.append(col)
    return out
