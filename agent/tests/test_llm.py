"""Unit tests for agent.llm — LLM facade and helpers.

Tests the compatibility layer (chat_completion, chat_completion_result,
_build_client, extract_sql) without calling real LLM APIs.  All LLMClient
interactions are mocked.

Focuses on reliability paths interviewers care about:
  - What happens when the LLM service is unavailable?
  - How does the facade handle timeout / rate-limit errors?
  - Are retry defaults correctly wired?
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.llm import (
    chat_completion,
    chat_completion_result,
    extract_sql,
)
from agent.llm_client import (
    LLMCallResult,
    LLMError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
    LLMTransportError,
)


# ── _build_client (via chat_completion_result) ───────────────────────────

class TestBuildClient:
    """_build_client wires retry defaults and explicit overrides correctly."""

    def test_default_retry_values(self):
        """When max_retries/backoff not specified, defaults from llm_client
        constants are used."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_result = LLMCallResult(
                content="ok",
                model="gpt",
                latency_ms=100,
                usage=None,
                attempts=1,
            )
            mock_instance.chat.return_value = mock_result
            MockClient.return_value = mock_instance

            chat_completion_result(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
                model="test-model",
                system="S",
                user="U",
            )

        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["max_retries"] == 2          # DEFAULT_MAX_RETRIES
        assert call_kwargs["retry_backoff_seconds"] == 0.5
        assert call_kwargs["retry_backoff_max_seconds"] == 8.0

    def test_explicit_retry_overrides(self):
        """Explicit max_retries/backoff values override defaults."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = LLMCallResult(
                content="ok", model="gpt", latency_ms=100, usage=None, attempts=1,
            )
            MockClient.return_value = mock_instance

            chat_completion_result(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
                model="test-model",
                system="S",
                user="U",
                max_retries=5,
                retry_backoff_seconds=2.0,
                retry_backoff_max_seconds=30.0,
            )

        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["max_retries"] == 5
        assert call_kwargs["retry_backoff_seconds"] == 2.0
        assert call_kwargs["retry_backoff_max_seconds"] == 30.0

    def test_transport_passthrough(self):
        """Custom httpx transport is forwarded to LLMClient."""
        fake_transport = MagicMock()

        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = LLMCallResult(
                content="ok", model="gpt", latency_ms=100, usage=None, attempts=1,
            )
            MockClient.return_value = mock_instance

            chat_completion_result(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
                model="test-model",
                system="S",
                user="U",
                transport=fake_transport,
            )

        assert MockClient.call_args.kwargs["transport"] is fake_transport

    def test_sleep_fn_passthrough(self):
        """Custom sleep function is forwarded to LLMClient (testability)."""
        fake_sleep = MagicMock()

        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = LLMCallResult(
                content="ok", model="gpt", latency_ms=100, usage=None, attempts=1,
            )
            MockClient.return_value = mock_instance

            chat_completion_result(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
                model="test-model",
                system="S",
                user="U",
                sleep_fn=fake_sleep,
            )

        assert MockClient.call_args.kwargs["sleep_fn"] is fake_sleep

    def test_client_params_forwarded(self):
        """api_key, base_url, model, timeout, temperature forwarded correctly."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = LLMCallResult(
                content="ok", model="gpt", latency_ms=100, usage=None, attempts=1,
            )
            MockClient.return_value = mock_instance

            chat_completion_result(
                api_key="sk-test-key",
                base_url="https://custom.api.com/v1",
                model="deepseek-chat",
                system="You are helpful",
                user="What is SQL?",
                temperature=0.3,
                timeout=120.0,
            )

        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["api_key"] == "sk-test-key"
        assert call_kwargs["base_url"] == "https://custom.api.com/v1"
        assert call_kwargs["model"] == "deepseek-chat"
        assert call_kwargs["timeout"] == 120.0
        assert call_kwargs["temperature"] == 0.3


# ── chat_completion_result — error propagation ───────────────────────────

class TestChatCompletionResultErrors:
    """LLM failures must propagate through the facade to callers."""

    def test_timeout_error_propagates(self):
        """LLMTimeoutError raised by client → re-raised through facade."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = LLMTimeoutError("Request timeout")
            MockClient.return_value = mock_instance

            with pytest.raises(LLMTimeoutError, match="Request timeout"):
                chat_completion_result(
                    api_key="sk-test",
                    base_url="https://api.test.com/v1",
                    model="test-model",
                    system="S",
                    user="U",
                )

    def test_rate_limit_error_propagates(self):
        """LLMRateLimitError (429) raised by client → re-raised."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = LLMRateLimitError("Rate limited")
            MockClient.return_value = mock_instance

            with pytest.raises(LLMRateLimitError, match="Rate limited"):
                chat_completion_result(
                    api_key="sk-test",
                    base_url="https://api.test.com/v1",
                    model="test-model",
                    system="S",
                    user="U",
                )

    def test_server_error_propagates(self):
        """LLMServerError (5xx) raised by client → re-raised."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = LLMServerError("Internal server error")
            MockClient.return_value = mock_instance

            with pytest.raises(LLMServerError, match="Internal server error"):
                chat_completion_result(
                    api_key="sk-test",
                    base_url="https://api.test.com/v1",
                    model="test-model",
                    system="S",
                    user="U",
                )

    def test_transport_error_propagates(self):
        """LLMTransportError (connection refused) raised → re-raised."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = LLMTransportError("Connection refused")
            MockClient.return_value = mock_instance

            with pytest.raises(LLMTransportError, match="Connection refused"):
                chat_completion_result(
                    api_key="sk-test",
                    base_url="https://api.test.com/v1",
                    model="test-model",
                    system="S",
                    user="U",
                )

    def test_base_llm_error_propagates(self):
        """LLMError (base class) raised by client → re-raised."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = LLMError("Unknown LLM failure")
            MockClient.return_value = mock_instance

            with pytest.raises(LLMError, match="Unknown LLM failure"):
                chat_completion_result(
                    api_key="sk-test",
                    base_url="https://api.test.com/v1",
                    model="test-model",
                    system="S",
                    user="U",
                )

    def test_response_format_forwarded(self):
        """response_format dict is forwarded to client.chat()."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = LLMCallResult(
                content="ok", model="gpt", latency_ms=100, usage=None, attempts=1,
            )
            MockClient.return_value = mock_instance

            fmt = {"type": "json_object"}
            chat_completion_result(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
                model="test-model",
                system="S",
                user="U",
                response_format=fmt,
            )

        mock_instance.chat.assert_called_once()
        assert mock_instance.chat.call_args.kwargs["response_format"] == fmt


# ── chat_completion — backward compat wrapper ────────────────────────────

class TestChatCompletionWrapper:
    """chat_completion() returns content string only, propagates errors."""

    def test_returns_content_string(self):
        """Normal path: returns assistant content as a plain string."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = LLMCallResult(
                content="Hello, world!",
                model="gpt",
                latency_ms=100,
                usage=None,
                attempts=1,
            )
            MockClient.return_value = mock_instance

            result = chat_completion(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
                model="test-model",
                system="S",
                user="U",
            )

        assert result == "Hello, world!"
        assert isinstance(result, str)

    def test_error_propagates(self):
        """Errors from the client propagate to chat_completion callers."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.side_effect = LLMTimeoutError("Timeout")
            MockClient.return_value = mock_instance

            with pytest.raises(LLMTimeoutError, match="Timeout"):
                chat_completion(
                    api_key="sk-test",
                    base_url="https://api.test.com/v1",
                    model="test-model",
                    system="S",
                    user="U",
                )

    def test_parameters_forwarded_to_chat_completion_result(self):
        """All parameters are forwarded through to LLMClient."""
        with patch("agent.llm.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.chat.return_value = LLMCallResult(
                content="ok", model="gpt", latency_ms=100, usage=None, attempts=1,
            )
            MockClient.return_value = mock_instance

            chat_completion(
                api_key="sk-test",
                base_url="https://api.test.com/v1",
                model="test-model",
                system="S",
                user="U",
                temperature=0.7,
                timeout=90.0,
                max_retries=3,
            )

        call_kwargs = MockClient.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7
        assert call_kwargs["timeout"] == 90.0
        assert call_kwargs["max_retries"] == 3


# ── extract_sql ──────────────────────────────────────────────────────────

class TestExtractSqlEdgeCases:
    """Edge cases for SQL extraction from LLM output."""

    def test_empty_string(self):
        """Empty input returns empty string."""
        assert extract_sql("") == ""

    def test_whitespace_only(self):
        """Whitespace-only input returns empty string."""
        assert extract_sql("   \n  \t  ") == ""

    def test_multiple_fences_first_wins(self):
        """When multiple code blocks, first is extracted."""
        text = '```sql\nSELECT 1\n```\n\n```sql\nSELECT 2\n```'
        assert extract_sql(text) == "SELECT 1"

    def test_mysql_backtick_identifiers(self):
        """MySQL backtick identifiers inside SQL are preserved."""
        text = '```sql\nSELECT `region`, `amount` FROM `sales`\n```'
        assert extract_sql(text) == "SELECT `region`, `amount` FROM `sales`"

    def test_sql_without_newline_after_fence(self):
        """SQL immediately after opening fence (no newline)."""
        text = '```sql\nSELECT 1\n```'
        assert extract_sql(text) == "SELECT 1"

    def test_leading_trailing_whitespace_in_fence(self):
        """Whitespace around SQL inside fence is stripped."""
        text = '```sql\n\n  SELECT 1  \n\n```'
        assert extract_sql(text) == "SELECT 1"