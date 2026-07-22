"""Kernel runtime — single platform entry: kernel.run(RunRequest)."""

from __future__ import annotations

from agent.kernel import registry
from agent.kernel.types import RunRequest, RunResult


def run(request: RunRequest) -> RunResult:
    """Execute a registered skill. Backend workers should use the Facade instead."""
    registry.ensure_platform_registrations()
    meta = registry.get_skill_meta(request.skill_id)
    if meta is None:
        return RunResult(
            success=False,
            skill_id=request.skill_id,
            error_message=f"Unknown skill_id={request.skill_id!r}",
            limitations=["Skill not registered on Enterprise Data Agent Platform."],
        )
    if not meta.enabled:
        return RunResult(
            success=False,
            skill_id=request.skill_id,
            skill_version=meta.version,
            error_message=f"Skill {request.skill_id!r} is disabled",
            limitations=["Skill Lifecycle: skill disabled via platform configuration."],
        )
    result = meta.handler(request)
    # Pin version observed at dispatch time (lifecycle lite)
    if result.skill_version is None:
        result.skill_version = meta.version
    return result


def platform_info() -> dict:
    registry.ensure_platform_registrations()
    return {
        "platform": "enterprise-data-agent",
        "skills": registry.list_skills(),
        "tools": registry.list_tools(),
        "policies": registry.list_policies(),
    }
