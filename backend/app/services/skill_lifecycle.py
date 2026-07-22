"""Skill Lifecycle lite — Settings sync + Shell enqueue gate (T-09 / Wave 3).

Does not rewrite Kernel dispatch; only metadata + enable checks.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.repo_path import ensure_repo_root_on_path

DATA_BI = "data.bi"
DATA_PROFILE = "data.profile"
DEFAULT_SKILL = DATA_BI


class SkillLifecycleError(Exception):
    def __init__(self, message: str, *, status_code: int = 403) -> None:
        super().__init__(message)
        self.status_code = status_code


def sync_from_settings(settings: Settings) -> None:
    """Apply config enable/version onto the in-process registry."""
    ensure_repo_root_on_path()
    from agent.kernel import registry

    registry.ensure_platform_registrations()
    registry.set_skill_lifecycle(
        DATA_BI,
        enabled=bool(settings.skill_data_bi_enabled),
        version=str(settings.skill_data_bi_version or "1.0.0"),
    )
    registry.set_skill_lifecycle(
        DATA_PROFILE,
        enabled=bool(settings.skill_data_profile_enabled),
        version=str(settings.skill_data_profile_version or "1.0.0"),
    )


def assert_skill_invokable(
    settings: Settings, *, skill_id: str = DEFAULT_SKILL
) -> tuple[str, str]:
    """Return (skill_id, skill_version) or raise SkillLifecycleError."""
    sync_from_settings(settings)
    from agent.kernel import registry

    meta = registry.get_skill_meta(skill_id)
    if meta is None:
        raise SkillLifecycleError(f"Unknown skill_id={skill_id!r}", status_code=404)
    if not meta.enabled:
        raise SkillLifecycleError(
            f"Skill {skill_id!r} is disabled",
            status_code=403,
        )
    return meta.skill_id, meta.version


def catalog(settings: Settings) -> list[dict]:
    sync_from_settings(settings)
    from agent.kernel import registry

    return registry.list_skills()
