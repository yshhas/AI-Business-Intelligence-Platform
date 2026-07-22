"""Pydantic schemas for LLM structured outputs (T-05: SQL path only)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from agent.llm_client import LLMResponseError


class SqlDraft(BaseModel):
    """Expected JSON object from Text-to-SQL LLM calls."""

    sql: str = Field(min_length=1, description="Single SELECT (optional WITH) statement")

    @field_validator("sql")
    @classmethod
    def normalize_sql(cls, value: str) -> str:
        cleaned = value.strip()
        fenced = re.search(r"```(?:sql)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
        if fenced:
            cleaned = fenced.group(1).strip()
        if not cleaned:
            raise ValueError("sql is empty after normalization")
        return cleaned


def parse_sql_draft(content: str) -> str:
    """Parse LLM content into a SQL string via SqlDraft.

    Primary path: JSON object {"sql": "..."}.
    Fallback: legacy fenced/raw SQL text (compat when provider ignores JSON mode).
    """
    text = (content or "").strip()
    if not text:
        raise LLMResponseError("Empty LLM content for SQL draft")

    # Strip optional markdown fence wrapping a JSON object
    fenced_json = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    candidate = fenced_json.group(1).strip() if fenced_json else text

    data: Any | None = None
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        try:
            return SqlDraft.model_validate(data).sql
        except ValidationError as exc:
            raise LLMResponseError(f"Invalid SQL JSON draft: {exc}") from exc

    # Legacy fallback — keep Gate as the real safety net
    from agent.llm import extract_sql

    legacy = extract_sql(text)
    if not legacy:
        raise LLMResponseError(f"Could not parse SQL draft from LLM content: {text[:300]!r}")
    return legacy
