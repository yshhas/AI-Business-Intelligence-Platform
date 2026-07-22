"""LLM helpers — compatibility facade over LLMClient.

Callers (pipeline nodes) keep importing chat_completion / LLMError / extract_sql
from this module. Implementation lives in agent.llm_client.

Retry defaults come from LLMClient constants or explicit caller args.
Worker/Shell injects Settings-backed retries via AnalysisContext — this module
does **not** import app.core.config.
"""

from __future__ import annotations

import re
from typing import Any, Callable

import httpx

from agent.llm_client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    LLMAuthError,
    LLMCallResult,
    LLMClient,
    LLMConfigError,
    LLMError,
    LLMHTTPError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
    LLMTransportError,
)

__all__ = [
    "LLMAuthError",
    "LLMCallResult",
    "LLMClient",
    "LLMConfigError",
    "LLMError",
    "LLMHTTPError",
    "LLMRateLimitError",
    "LLMResponseError",
    "LLMServerError",
    "LLMTimeoutError",
    "LLMTransportError",
    "chat_completion",
    "chat_completion_result",
    "extract_sql",
]


def _build_client(
    *,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float,
    timeout: float,
    max_retries: int | None,
    retry_backoff_seconds: float | None,
    retry_backoff_max_seconds: float | None,
    transport: httpx.BaseTransport | None,
    sleep_fn: Callable[[float], None] | None,
) -> LLMClient:
    return LLMClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        temperature=temperature,
        max_retries=DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
        retry_backoff_seconds=(
            DEFAULT_RETRY_BACKOFF_SECONDS
            if retry_backoff_seconds is None
            else retry_backoff_seconds
        ),
        retry_backoff_max_seconds=(
            DEFAULT_RETRY_BACKOFF_MAX_SECONDS
            if retry_backoff_max_seconds is None
            else retry_backoff_max_seconds
        ),
        transport=transport,
        sleep_fn=sleep_fn,
    )


def chat_completion_result(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.1,
    timeout: float = 60.0,
    max_retries: int | None = None,
    retry_backoff_seconds: float | None = None,
    retry_backoff_max_seconds: float | None = None,
    response_format: dict[str, Any] | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> LLMCallResult:
    """Full result including usage metadata (T-07)."""
    client = _build_client(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_backoff_max_seconds=retry_backoff_max_seconds,
        transport=transport,
        sleep_fn=sleep_fn,
    )
    return client.chat(
        system=system,
        user=user,
        response_format=response_format,
    )


def chat_completion(
    *,
    api_key: str,
    base_url: str,
    model: str,
    system: str,
    user: str,
    temperature: float = 0.1,
    timeout: float = 60.0,
    max_retries: int | None = None,
    retry_backoff_seconds: float | None = None,
    retry_backoff_max_seconds: float | None = None,
    response_format: dict[str, Any] | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep_fn: Callable[[float], None] | None = None,
) -> str:
    """Backward-compatible entry — returns assistant content string only."""
    return chat_completion_result(
        api_key=api_key,
        base_url=base_url,
        model=model,
        system=system,
        user=user,
        temperature=temperature,
        timeout=timeout,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_backoff_max_seconds=retry_backoff_max_seconds,
        response_format=response_format,
        transport=transport,
        sleep_fn=sleep_fn,
    ).content


def extract_sql(text: str) -> str:
    """Pull SQL from fenced code block or raw text."""
    fenced = re.search(r"```(?:sql)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()
