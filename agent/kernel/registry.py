"""Skill / Tool / Policy registries (minimal) + Skill Lifecycle lite metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from agent.kernel.types import RunRequest, RunResult

SkillHandler = Callable[[RunRequest], RunResult]

DATA_BI_SKILL_ID = "data.bi"
DATA_PROFILE_SKILL_ID = "data.profile"
DEFAULT_DATA_BI_VERSION = "1.0.0"
DEFAULT_DATA_PROFILE_VERSION = "1.0.0"


class PolicyFn(Protocol):
    def __call__(self, **kwargs: Any) -> Any: ...


@dataclass
class SkillMeta:
    skill_id: str
    handler: SkillHandler
    version: str = DEFAULT_DATA_BI_VERSION
    enabled: bool = True
    display_name: str = ""

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "display_name": self.display_name or self.skill_id,
            "version": self.version,
            "enabled": bool(self.enabled),
        }


_skills: dict[str, SkillMeta] = {}
_tools: dict[str, str] = {}  # tool_id -> description
_policies: dict[str, str] = {}  # policy_id -> description


def register_skill(
    skill_id: str,
    handler: SkillHandler,
    *,
    version: str = DEFAULT_DATA_BI_VERSION,
    enabled: bool = True,
    display_name: str | None = None,
) -> None:
    _skills[skill_id] = SkillMeta(
        skill_id=skill_id,
        handler=handler,
        version=version,
        enabled=enabled,
        display_name=display_name or skill_id,
    )


def get_skill(skill_id: str) -> SkillHandler | None:
    meta = _skills.get(skill_id)
    return meta.handler if meta else None


def get_skill_meta(skill_id: str) -> SkillMeta | None:
    return _skills.get(skill_id)


def set_skill_lifecycle(
    skill_id: str,
    *,
    enabled: bool | None = None,
    version: str | None = None,
) -> None:
    """Update lifecycle flags for an already-registered skill (Settings sync)."""
    meta = _skills.get(skill_id)
    if meta is None:
        return
    if enabled is not None:
        meta.enabled = bool(enabled)
    if version is not None and str(version).strip():
        meta.version = str(version).strip()


def is_skill_enabled(skill_id: str) -> bool:
    meta = _skills.get(skill_id)
    return bool(meta and meta.enabled)


def list_skills() -> list[dict[str, Any]]:
    return [meta.as_public_dict() for meta in sorted(_skills.values(), key=lambda m: m.skill_id)]


def register_tool(tool_id: str, description: str) -> None:
    _tools[tool_id] = description


def register_policy(policy_id: str, description: str) -> None:
    _policies[policy_id] = description


def list_tools() -> list[dict[str, str]]:
    return [{"tool_id": k, "description": v} for k, v in sorted(_tools.items())]


def list_policies() -> list[dict[str, str]]:
    return [
        {"policy_id": k, "description": v} for k, v in sorted(_policies.items())
    ]


def ensure_platform_registrations() -> None:
    """Idempotent bootstrap of tools/policies + registered Data Skills."""
    if DATA_BI_SKILL_ID in _skills and DATA_PROFILE_SKILL_ID in _skills:
        return

    register_tool("llm.chat", "OpenAI-compatible chat completion")
    register_tool("sql.generate", "Produce SQL draft (LLM or heuristic)")
    register_tool("sql.validate_policy", "Run sql.select_gate on draft SQL")
    register_tool("sql.execute_select", "Execute SELECT via injected executor after policy")
    register_tool("chart.build_spec", "Heuristic ChartSpec (bar|line)")
    register_tool("report.build", "Short markdown analysis report")
    register_tool("schema.profile", "Deterministic column profile aggregates")

    register_policy(
        "sql.select_gate",
        "Deterministic SELECT-only gate; required before sql.execute_select",
    )

    from agent.skills.data_bi.skill import run_data_bi_skill
    from agent.skills.data_profile.skill import run_data_profile_skill

    if DATA_BI_SKILL_ID not in _skills:
        register_skill(
            DATA_BI_SKILL_ID,
            run_data_bi_skill,
            version=DEFAULT_DATA_BI_VERSION,
            enabled=True,
            display_name="Data BI",
        )
    if DATA_PROFILE_SKILL_ID not in _skills:
        register_skill(
            DATA_PROFILE_SKILL_ID,
            run_data_profile_skill,
            version=DEFAULT_DATA_PROFILE_VERSION,
            enabled=True,
            display_name="Data Profile",
        )
