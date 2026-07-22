"""LLM provider defaults — thin layer over OpenAI-compatible HTTP path.

Wave 2: `llm_provider` selects default base_url/model when settings values are
empty-ish. Native Anthropic/Gemini APIs are not wired directly; point
`LLM_BASE_URL` at an OpenAI-compatible gateway (LiteLLM, OpenRouter, etc.) or
use provider defaults where a compatible endpoint exists (e.g. Gemini OpenAI shim).
"""

from __future__ import annotations

from typing import Literal

LLMProvider = Literal["openai_compatible", "anthropic", "gemini"]

_EMPTY_URL_MARKERS = frozenset({"", "auto", "default", "none"})

# Default base_url + model per provider (used only when settings omit them).
_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "openai_compatible": ("https://api.openai.com/v1", "gpt-4o-mini"),
    # Anthropic: set LLM_BASE_URL to your compatible proxy; placeholder for docs.
    "anthropic": ("https://api.anthropic.com/v1", "claude-3-5-sonnet-20241022"),
    # Google OpenAI-compatible surface (v1beta/openai).
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-1.5-flash",
    ),
}


def _is_emptyish(value: str | None) -> bool:
    text = (value or "").strip()
    return not text or text.lower() in _EMPTY_URL_MARKERS


def resolve_llm_config(
    provider: str,
    base_url: str,
    model: str,
) -> tuple[str, str]:
    """Return (base_url, model) after applying provider defaults."""
    key = (provider or "openai_compatible").strip().lower()
    if key not in _PROVIDER_DEFAULTS:
        key = "openai_compatible"
    default_url, default_model = _PROVIDER_DEFAULTS[key]
    resolved_url = default_url if _is_emptyish(base_url) else base_url.strip()
    resolved_model = default_model if _is_emptyish(model) else model.strip()
    return resolved_url, resolved_model
