"""Unit tests for LLM Client — LLMClient, LLMCallResult, providers, facade.

Tests cover configuration, request construction, success/error responses,
retry logic (exponential backoff), and error classification.
All HTTP calls are mocked via httpx.Client — no real LLM API calls.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from agent.llm import (
    LLMError,
    chat_completion,
    chat_completion_result,
    extract_sql,
)
from agent.llm_client import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF_MAX_SECONDS,
    DEFAULT_RETRY_BACKOFF_SECONDS,
    LLMAuthError,
    LLMCallResult,
    LLMClient,
    LLMConfigError,
    LLMHTTPError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
    LLMTimeoutError,
    LLMTransportError,
)
from agent.llm_providers import resolve_llm_config


# ── Helpers ──────────────────────────────────────────────────────────────

def _mock_response(
    status_code: int = 200,
    content: str | None = None,
    json_body: dict | None = None,
) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = json.dumps(json_body) if json_body is not None else (content or "")
    if json_body is not None:
        resp.json.return_value = json_body
    else:
        resp.json.side_effect = ValueError("not JSON")
    return resp


_DEFAULT_USAGE = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}


def _success_body(content: str, model: str = "deepseek-chat", usage: object = _DEFAULT_USAGE) -> dict:
    body: dict = {
        "choices": [{"message": {"content": content, "role": "assistant"}}],
        "model": model,
    }
    if usage is not _DEFAULT_USAGE:
        body["usage"] = usage
    else:
        body["usage"] = _DEFAULT_USAGE
    return body


def _patch_httpx(resp: MagicMock) -> MagicMock:
    """Patch httpx.Client to return resp on post()."""
    mock_client = MagicMock()
    mock_client.post.return_value = resp
    patcher = patch("httpx.Client")
    mock_cls = patcher.start()
    mock_cls.return_value.__enter__.return_value = mock_client
    return mock_client


def _make_client(**overrides: object) -> LLMClient:
    kwargs: dict = {
        "api_key": "sk-test-key",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "timeout": 30.0,
        "max_retries": 2,
        "retry_backoff_seconds": 0.1,
        "retry_backoff_max_seconds": 1.0,
        "sleep_fn": MagicMock(),
    }
    kwargs.update({k: v for k, v in overrides.items() if v is not None})
    return LLMClient(**kwargs)


# ── LLMClient: Configuration ─────────────────────────────────────────────

class TestLLMClientConfig:
    """LLMClient constructor validation and defaults."""

    def test_empty_api_key_raises(self):
        client = _make_client(api_key="")
        with pytest.raises(LLMConfigError, match="empty"):
            client.chat(system="S", user="U")

    def test_default_retries(self):
        client = LLMClient(api_key="k", base_url="http://x", model="m")
        assert client.max_retries == DEFAULT_MAX_RETRIES

    def test_negative_retries_clamped(self):
        client = LLMClient(api_key="k", base_url="http://x", model="m", max_retries=-5)
        assert client.max_retries == 0

    def test_base_url_trailing_slash_stripped(self):
        client = LLMClient(api_key="k", base_url="http://x/v1/", model="m")
        assert client.chat_completions_url == "http://x/v1/chat/completions"


# ── LLMClient: Payload ───────────────────────────────────────────────────

class TestLLMClientPayload:
    """Request payload construction."""

    def test_basic_payload(self):
        client = _make_client()
        payload = client._build_payload(system="Be helpful", user="Hello", temperature=0.1)
        assert payload["model"] == "deepseek-chat"
        assert payload["temperature"] == 0.1
        assert len(payload["messages"]) == 2
        assert payload["messages"][0] == {"role": "system", "content": "Be helpful"}
        assert payload["messages"][1] == {"role": "user", "content": "Hello"}
        assert "response_format" not in payload

    def test_payload_with_response_format(self):
        client = _make_client()
        payload = client._build_payload(
            system="S", user="U", temperature=0.0, response_format={"type": "json_object"}
        )
        assert payload["response_format"] == {"type": "json_object"}


# ── LLMClient: Success ───────────────────────────────────────────────────

class TestLLMClientSuccess:
    """Successful chat completions."""

    def test_chat_success(self):
        body = _success_body("SELECT * FROM t")
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        client = _make_client()
        result = client.chat(system="S", user="U")

        assert result.content == "SELECT * FROM t"
        assert result.model == "deepseek-chat"
        assert result.attempts == 1
        assert result.usage == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}

    def test_chat_with_response_format(self):
        body = _success_body('{"sql":"SELECT 1"}')
        mock_resp = _mock_response(status_code=200, json_body=body)
        mock_client = _patch_httpx(mock_resp)

        client = _make_client()
        result = client.chat(system="S", user="U", response_format={"type": "json_object"})

        assert result.content == '{"sql":"SELECT 1"}'
        call_args = mock_client.post.call_args
        sent_payload = call_args.kwargs["json"]
        assert sent_payload["response_format"] == {"type": "json_object"}

    def test_usage_parsing_null(self):
        body = _success_body("ok", usage=None)
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        client = _make_client()
        result = client.chat(system="S", user="U")
        assert result.usage is None

    def test_usage_parsing_partial(self):
        body = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 5},
        }
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        client = _make_client()
        result = client.chat(system="S", user="U")
        assert result.usage == {"prompt_tokens": 5}


# ── LLMClient: Response Errors ───────────────────────────────────────────

class TestLLMClientResponseErrors:
    """Malformed / unexpected response bodies."""

    def test_non_json_response(self):
        mock_resp = _mock_response(status_code=200, content="not JSON at all")
        _patch_httpx(mock_resp)

        client = _make_client()
        with pytest.raises(LLMResponseError, match="not JSON"):
            client.chat(system="S", user="U")

    def test_missing_choices(self):
        body = {"model": "m"}
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        client = _make_client()
        with pytest.raises(LLMResponseError, match="Unexpected"):
            client.chat(system="S", user="U")

    def test_null_content(self):
        body = {"choices": [{"message": {"content": None}}]}
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        client = _make_client()
        with pytest.raises(LLMResponseError, match="Unexpected"):
            client.chat(system="S", user="U")

    def test_response_not_dict(self):
        body = ["not", "a", "dict"]
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        client = _make_client()
        with pytest.raises(LLMResponseError):
            client.chat(system="S", user="U")


# ── LLMClient: HTTP Errors ───────────────────────────────────────────────

class TestLLMClientHTTPErrors:
    """HTTP status code → error classification."""

    def test_401_raises_auth_error(self):
        mock_resp = _mock_response(status_code=401, content="Unauthorized")
        _patch_httpx(mock_resp)

        client = _make_client()
        with pytest.raises(LLMAuthError) as exc_info:
            client.chat(system="S", user="U")
        assert exc_info.value.status_code == 401

    def test_403_raises_auth_error(self):
        mock_resp = _mock_response(status_code=403, content="Forbidden")
        _patch_httpx(mock_resp)

        client = _make_client()
        with pytest.raises(LLMAuthError):
            client.chat(system="S", user="U")

    def test_429_raises_rate_limit_error(self):
        mock_resp = _mock_response(status_code=429, content="Rate limited")
        _patch_httpx(mock_resp)

        client = _make_client(max_retries=0)
        with pytest.raises(LLMRateLimitError):
            client.chat(system="S", user="U")

    def test_500_raises_server_error(self):
        mock_resp = _mock_response(status_code=500, content="Internal error")
        _patch_httpx(mock_resp)

        client = _make_client(max_retries=0)
        with pytest.raises(LLMServerError):
            client.chat(system="S", user="U")

    def test_503_raises_server_error(self):
        mock_resp = _mock_response(status_code=503, content="Unavailable")
        _patch_httpx(mock_resp)

        client = _make_client(max_retries=0)
        with pytest.raises(LLMServerError):
            client.chat(system="S", user="U")

    def test_400_raises_generic_http_error(self):
        mock_resp = _mock_response(status_code=400, content="Bad request")
        _patch_httpx(mock_resp)

        client = _make_client(max_retries=0)
        with pytest.raises(LLMHTTPError) as exc_info:
            client.chat(system="S", user="U")
        assert exc_info.value.status_code == 400
        # 400 is NOT retryable
        assert not isinstance(exc_info.value, (LLMRateLimitError, LLMServerError))


# ── LLMClient: Transport Errors ──────────────────────────────────────────

class TestLLMClientTransportErrors:
    """Network / timeout errors."""

    def test_timeout_raises_timeout_error(self):
        with patch("httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.TimeoutException("timed out")
            mock_cls.return_value.__enter__.return_value = mock_client

            client = _make_client(max_retries=0)
            with pytest.raises(LLMTimeoutError, match="timed out"):
                client.chat(system="S", user="U")

    def test_transport_error(self):
        with patch("httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("connection refused")
            mock_cls.return_value.__enter__.return_value = mock_client

            client = _make_client(max_retries=0)
            with pytest.raises(LLMTransportError, match="connection refused"):
                client.chat(system="S", user="U")


# ── LLMClient: Retry Logic ───────────────────────────────────────────────

class TestLLMClientRetry:
    """Retry logic: backoff, max_retries, retryable vs non-retryable."""

    def test_retry_429_success(self):
        """429 → retry → 200 success."""
        bad = _mock_response(status_code=429, content="rate limited")
        good = _mock_response(status_code=200, json_body=_success_body("ok"))

        with patch("httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = [bad, good]
            mock_cls.return_value.__enter__.return_value = mock_client

            sleep_mock = MagicMock()
            client = _make_client(max_retries=2, sleep_fn=sleep_mock)
            result = client.chat(system="S", user="U")

        assert result.content == "ok"
        assert result.attempts == 2
        sleep_mock.assert_called_once()

    def test_retry_503_success(self):
        """503 → retry → success."""
        bad = _mock_response(status_code=503, content="unavailable")
        good = _mock_response(status_code=200, json_body=_success_body("ok"))

        with patch("httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = [bad, good]
            mock_cls.return_value.__enter__.return_value = mock_client

            client = _make_client(max_retries=2, sleep_fn=MagicMock())
            result = client.chat(system="S", user="U")

        assert result.attempts == 2

    def test_retry_timeout_success(self):
        """Timeout → retry → success."""
        bad = httpx.TimeoutException("timed out")
        good = _mock_response(status_code=200, json_body=_success_body("ok"))

        with patch("httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = [bad, good]
            mock_cls.return_value.__enter__.return_value = mock_client

            client = _make_client(max_retries=2, sleep_fn=MagicMock())
            result = client.chat(system="S", user="U")

        assert result.attempts == 2

    def test_max_retries_exhausted(self):
        """429 × 3 → exhaust max_retries=2 → raise."""
        bad = _mock_response(status_code=429, content="rate limited")

        with patch("httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = bad
            mock_cls.return_value.__enter__.return_value = mock_client

            client = _make_client(max_retries=2, sleep_fn=MagicMock())
            with pytest.raises(LLMRateLimitError):
                client.chat(system="S", user="U")

        assert mock_client.post.call_count == 3  # 1 initial + 2 retries

    def test_non_retryable_no_retry(self):
        """401 is NOT retryable — should fail immediately."""
        bad = _mock_response(status_code=401, content="unauthorized")

        with patch("httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_client.post.return_value = bad
            mock_cls.return_value.__enter__.return_value = mock_client

            client = _make_client(max_retries=2, sleep_fn=MagicMock())
            with pytest.raises(LLMAuthError):
                client.chat(system="S", user="U")

        # Only 1 attempt — no retry
        assert mock_client.post.call_count == 1

    def test_backoff_delay(self):
        """Exponential backoff with equal jitter."""
        client = _make_client(
            retry_backoff_seconds=0.5,
            retry_backoff_max_seconds=8.0,
        )

        # attempt 0: base = 0.5 * 2^0 = 0.5, jitter in [0.25, 0.5]
        d0 = client._backoff_delay(0)
        assert 0.25 <= d0 <= 0.5

        # attempt 1: base = 0.5 * 2^1 = 1.0, jitter in [0.5, 1.0]
        d1 = client._backoff_delay(1)
        assert 0.5 <= d1 <= 1.0

        # attempt 5: base = 0.5 * 2^5 = 16.0, capped to 8.0
        d5 = client._backoff_delay(5)
        assert 4.0 <= d5 <= 8.0  # jitter: [0.5, 1.0] * 8.0


# ── LLMCallResult ────────────────────────────────────────────────────────

class TestLLMCallResult:
    """LLMCallResult dataclass and serialization."""

    def test_basic_construction(self):
        r = LLMCallResult(content="hello", model="m", latency_ms=100)
        assert r.content == "hello"
        assert r.model == "m"
        assert r.latency_ms == 100
        assert r.attempts == 1
        assert r.usage is None

    def test_as_step_llm(self):
        r = LLMCallResult(
            content="x",
            model="m",
            latency_ms=200,
            attempts=2,
            usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        )
        step = r.as_step_llm()
        assert step["model"] == "m"
        assert step["latency_ms"] == 200
        assert step["attempts"] == 2
        assert step["status"] == "ok"
        assert step["usage"]["total_tokens"] == 30

    def test_as_step_llm_no_usage(self):
        r = LLMCallResult(content="x", model="m", latency_ms=100)
        step = r.as_step_llm()
        assert "usage" not in step


# ── LLM Providers ────────────────────────────────────────────────────────

class TestResolveLLMConfig:
    """resolve_llm_config applies provider defaults."""

    def test_openai_compatible_defaults(self):
        url, model = resolve_llm_config("openai_compatible", "", "")
        assert url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini"

    def test_custom_values_override(self):
        url, model = resolve_llm_config(
            "openai_compatible",
            "https://api.deepseek.com/v1",
            "deepseek-chat",
        )
        assert url == "https://api.deepseek.com/v1"
        assert model == "deepseek-chat"

    def test_unknown_provider_fallback(self):
        url, model = resolve_llm_config("unknown_provider", "", "")
        assert url == "https://api.openai.com/v1"
        assert model == "gpt-4o-mini"

    def test_emptyish_values(self):
        for empty in ("", "auto", "default", "none"):
            url, model = resolve_llm_config("openai_compatible", empty, empty)
            assert url == "https://api.openai.com/v1"
            assert model == "gpt-4o-mini"


# ── Facade: chat_completion_result / chat_completion ─────────────────────

class TestChatCompletionFacade:
    """Integration through the llm.py facade."""

    def test_chat_completion_result(self):
        body = _success_body("SELECT 1")
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        result = chat_completion_result(
            api_key="sk-test",
            base_url="https://api.test.com/v1",
            model="test-model",
            system="S",
            user="U",
        )
        assert result.content == "SELECT 1"
        assert result.model == "test-model"

    def test_chat_completion_backward_compat(self):
        body = _success_body("result text")
        mock_resp = _mock_response(status_code=200, json_body=body)
        _patch_httpx(mock_resp)

        content = chat_completion(
            api_key="sk-test",
            base_url="https://api.test.com/v1",
            model="test-model",
            system="S",
            user="U",
        )
        assert content == "result text"


# ── extract_sql ──────────────────────────────────────────────────────────

class TestExtractSQL:
    """SQL extraction from LLM output."""

    def test_fenced_sql(self):
        text = '```sql\nSELECT * FROM t\n```'
        assert extract_sql(text) == "SELECT * FROM t"

    def test_fenced_no_lang(self):
        text = '```\nSELECT * FROM t\n```'
        assert extract_sql(text) == "SELECT * FROM t"

    def test_raw_text(self):
        assert extract_sql("SELECT * FROM t") == "SELECT * FROM t"

    def test_whitespace_trimmed(self):
        assert extract_sql("  SELECT 1  ") == "SELECT 1"