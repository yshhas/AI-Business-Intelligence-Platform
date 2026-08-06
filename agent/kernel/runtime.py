"""Kernel runtime — single platform entry: kernel.run(RunRequest)."""

from __future__ import annotations

import logging

from agent.kernel import registry
from agent.kernel.types import RunRequest, RunResult

logger = logging.getLogger(__name__)


def run(request: RunRequest) -> RunResult:
    """Execute a registered skill. Backend workers should use the Facade instead."""
    registry.ensure_platform_registrations()
    meta = registry.get_skill_meta(request.skill_id)
    if meta is None:
        logger.warning("Skill not registered skill_id=%s", request.skill_id)
        return RunResult(
            success=False,
            skill_id=request.skill_id,
            error_message=f"Unknown skill_id={request.skill_id!r}",
            limitations=["Skill not registered on Enterprise Data Agent Platform."],
        )
    if not meta.enabled:
        logger.warning("Skill disabled skill_id=%s version=%s", request.skill_id, meta.version)
        return RunResult(
            success=False,
            skill_id=request.skill_id,
            skill_version=meta.version,
            error_message=f"Skill {request.skill_id!r} is disabled",
            limitations=["Skill Lifecycle: skill disabled via platform configuration."],
        )
    logger.info("Skill execution started skill_id=%s version=%s", request.skill_id, meta.version)
    result = meta.handler(request)
    # Pin version observed at dispatch time (lifecycle lite)
    if result.skill_version is None:
        result.skill_version = meta.version
    logger.info(
        "Skill execution completed skill_id=%s success=%s steps=%d",
        request.skill_id, result.success, len(result.steps or []),
    )
    return result


def platform_info() -> dict:
    registry.ensure_platform_registrations()
    return {
        "platform": "enterprise-data-agent",
        "skills": registry.list_skills(),
        "tools": registry.list_tools(),
        "policies": registry.list_policies(),
    }
