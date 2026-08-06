from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypedDict
from uuid import UUID

# Optional cooperative abort: () -> None, raises RunAborted when cancel/timeout requested.
CancelCheckFn = Callable[[], None]


class AnalysisState(TypedDict, total=False):
    question: str
    workspace_id: str
    dataset_id: str
    duckdb_table: str
    schema: list[dict[str, Any]]
    sql_draft: str
    sql_final: str
    gate_ok: bool
    gate_error: str
    preview: dict[str, Any]
    summary: str
    charts: list[dict[str, Any]]
    report: dict[str, Any] | None
    limitations: list[str]
    error: str
    status: str
    retry_count: int
    max_retries: int
    default_limit: int
    # E1-A Schema Linking Lite
    selected_tables: list[str]
    selected_columns: list[str]
    link_status: str
    link_method: str
    link_reason: str | None
    column_count_full: int
    column_count_linked: int
    hitl_plan_only: bool
    hitl_execute_only: bool
    # P3 repair tracking
    repair_history: list[dict[str, Any]]
    repair_class: str | None
    repair_hint: dict[str, Any] | None
    repair_stage: str | None


ExecuteSelectFn = Callable[[str, int], dict[str, Any]]


@dataclass
class StepRecord:
    node_name: str
    status: str
    input_json: dict[str, Any] | None = None
    output_json: dict[str, Any] | None = None
    error_message: str | None = None
    latency_ms: int | None = None


@dataclass
class AnalysisContext:
    workspace_id: UUID
    dataset_id: UUID
    question: str
    duckdb_table: str
    schema: list[dict[str, Any]]
    default_limit: int
    max_retries: int
    execute_select: ExecuteSelectFn
    skill_id: str = "data.bi"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    allow_heuristic_sql: bool = True
    # M3: full Gate allowlist (defaults to [duckdb_table] in Facade)
    allowed_tables: list[str] | None = None
    source_type: str = "file"
    # E1-A: Skill-local linking budget (not a Kernel setting)
    schema_link_max_columns: int = 12
    # Linking v2: optional synonym map {phrase: [column_tokens...]}
    schema_synonyms: dict[str, list[str]] | None = None
    # LLM transport retries — injected by Worker/Shell; never read app Settings from agent
    llm_max_retries: int | None = None
    llm_retry_backoff_seconds: float | None = None
    llm_retry_backoff_max_seconds: float | None = None
    # P1.1 — Worker-injected cooperative abort (no DB access inside agent)
    cancel_check: CancelCheckFn | None = None
    # HITL H1 — stop after Gate allow; no Data Plane execute
    hitl_plan_only: bool = False
    # HITL H2 T3 — execute approved SQL only (no LLM regen)
    hitl_execute_only: bool = False
    approved_sql: str | None = None


@dataclass
class AnalysisOutcome:
    success: bool
    result_json: dict[str, Any]
    steps: list[StepRecord] = field(default_factory=list)
    error_message: str | None = None
