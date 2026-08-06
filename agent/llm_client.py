"""OpenAI-compatible LLM client (DeepSeek / OpenAI).

T-03: endpoint, auth, model, timeout, request/response, error classes.
T-04: limited exponential backoff retry for recoverable provider/transport errors.
T-07: optional usage / latency metadata on successful calls.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

# Defaults aligned with Settings (app.core.config) — used when Settings is unavailable.
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5
DEFAULT_RETRY_BACKOFF_MAX_SECONDS = 8.0

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base error for all LLM client failures (callers may catch this alone)."""


class LLMConfigError(LLMError):
    """Missing or invalid client configuration (e.g. empty API key)."""


class LLMTimeoutError(LLMError):
    """Request exceeded the configured timeout."""


class LLMTransportError(LLMError):
    """Network / transport failure before a usable HTTP response."""


class LLMHTTPError(LLMError):
    """Non-success HTTP response from the LLM provider."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class LLMAuthError(LLMHTTPError):
    """401 / 403 — credentials rejected."""


class LLMRateLimitError(LLMHTTPError):
    """429 — provider rate limit."""


class LLMServerError(LLMHTTPError):
    """5xx — provider server error."""


class LLMResponseError(LLMError):
    """HTTP 2xx but body shape is not a usable chat completion."""


# Recoverable: worth another attempt after backoff.
_RETRYABLE: tuple[type[LLMError], ...] = (
    LLMTimeoutError,
    LLMTransportError,
    LLMRateLimitError,
    LLMServerError,
)


@dataclass(frozen=True)
class LLMCallResult:
    """Successful chat completion plus light observability fields (T-07)."""

    content: str
    model: str
    latency_ms: int
    attempts: int = 1
    usage: dict[str, int] | None = None

    def as_step_llm(self) -> dict[str, Any]:
        """Shape stored under StepRecord.output_json['llm']."""
        payload: dict[str, Any] = {
            "model": self.model,
            "latency_ms": self.latency_ms,
            "attempts": self.attempts,
            "status": "ok",
        }
        if self.usage:
            payload["usage"] = dict(self.usage)
        return payload


class LLMClient:
    """Thin sync client for chat.completions."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 60.0,
        temperature: float = 0.1,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        retry_backoff_max_seconds: float = DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max(0, int(max_retries))
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self.retry_backoff_max_seconds = float(retry_backoff_max_seconds)
        self._transport = transport
        self._sleep = sleep_fn or time.sleep

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def chat(
        self,
        *,
        system: str,
        user: str,
        temperature: float | None = None,
        timeout: float | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMCallResult:
        """Send a system+user chat completion; return content + usage metadata."""
        if not self.api_key:
            raise LLMConfigError("LLM_API_KEY is empty")

        temp = self.temperature if temperature is None else temperature
        to = self.timeout if timeout is None else timeout
        payload = self._build_payload(
            system=system,
            user=user,
            temperature=temp,
            response_format=response_format,
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        attempt = 0
        t0 = time.perf_counter()
        while True:
            try:
                content, usage = self._chat_once(
                    payload=payload, headers=headers, timeout=to
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)
                return LLMCallResult(
                    content=content,
                    model=self.model,
                    latency_ms=latency_ms,
                    attempts=attempt + 1,
                    usage=usage,
                )
            except _RETRYABLE as exc:
                if attempt >= self.max_retries:
                    logger.error(
                        "LLM max retries exceeded attempts=%d last_status=%s",
                        attempt + 1,
                        getattr(exc, "status_code", "?"),
                    )
                    raise
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "LLM request retrying attempt=%d/%d delay=%.1fs status=%s",
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                    getattr(exc, "status_code", "?"),
                )
                self._sleep(delay)
                attempt += 1

    def _chat_once(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> tuple[str, dict[str, int] | None]:
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                resp = client.post(self.chat_completions_url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError(f"LLM request timed out after {timeout}s") from exc
        except httpx.HTTPError as exc:
            raise LLMTransportError(f"LLM transport error: {exc}") from exc

        if resp.status_code >= 400:
            raise self._classify_http_error(resp)

        try:
            data = resp.json()
        except ValueError as exc:
            raise LLMResponseError(
                f"LLM response is not JSON: {resp.text[:500]!r}"
            ) from exc

        return self._parse_content(data), self._parse_usage(data)

    def _backoff_delay(self, attempt: int) -> float:
        """Exponential backoff with equal jitter. attempt=0 after first failure."""
        base = self.retry_backoff_seconds * (2**attempt)
        capped = min(base, self.retry_backoff_max_seconds)
        # Equal jitter: [0.5, 1.0] * capped
        return capped * (0.5 + random.random() * 0.5)

    def _build_payload(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    @staticmethod
    def _parse_content(data: Any) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(f"Unexpected LLM response: {data!r}") from exc
        if content is None:
            raise LLMResponseError(f"Unexpected LLM response: {data!r}")
        return str(content)

    @staticmethod
    def _parse_usage(data: Any) -> dict[str, int] | None:
        if not isinstance(data, dict):
            return None
        raw = data.get("usage")
        if not isinstance(raw, dict):
            return None
        out: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            val = raw.get(key)
            if val is None:
                continue
            try:
                out[key] = int(val)
            except (TypeError, ValueError):
                continue
        return out or None

    @staticmethod
    def _classify_http_error(resp: httpx.Response) -> LLMHTTPError:
        body = resp.text[:500]
        message = f"LLM HTTP {resp.status_code}: {body}"
        code = resp.status_code
        if code in (401, 403):
            return LLMAuthError(message, status_code=code, body=body)
        if code == 429:
            return LLMRateLimitError(message, status_code=code, body=body)
        if code >= 500:
            return LLMServerError(message, status_code=code, body=body)
        return LLMHTTPError(message, status_code=code, body=body)
