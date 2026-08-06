"""Unit tests for agent.guardrails — output redaction of secrets/PII patterns.

Tests cover:
- redact_text: email / bearer token / API key / long token redaction
- _redact_cell: string cell redaction
- redact_table_preview: table data redaction (columns + rows)
- redact_preview_payload: Dataset preview response
- apply_output_guardrails: full result_json redaction
- Empty / None / non-string inputs
- Edge cases: partial matches, boundary lengths, special characters
"""

from __future__ import annotations

import pytest

from agent.guardrails import (
    apply_output_guardrails,
    redact_preview_payload,
    redact_table_preview,
    redact_text,
)


# ── redact_text ────────────────────────────────────────────────────────

class TestRedactText:
    # --- Email ---

    def test_email_simple(self):
        assert redact_text("Contact: user@example.com") == "Contact: [REDACTED_EMAIL]"

    def test_email_with_dots(self):
        assert redact_text("first.last@company.co.uk") == "[REDACTED_EMAIL]"

    def test_email_with_plus(self):
        assert redact_text("user+tag@example.com") == "[REDACTED_EMAIL]"

    def test_email_with_numbers(self):
        assert redact_text("user123@domain99.org") == "[REDACTED_EMAIL]"

    def test_email_uppercase(self):
        assert redact_text("USER@EXAMPLE.COM") == "[REDACTED_EMAIL]"

    def test_multiple_emails(self):
        result = redact_text("To: a@x.com, b@y.com")
        assert result == "To: [REDACTED_EMAIL], [REDACTED_EMAIL]"

    # --- Bearer / API key ---

    def test_bearer_token(self):
        assert "bearer" in redact_text("Authorization: Bearer abc123def456ghi789").lower()
        assert "[REDACTED]" in redact_text("Authorization: Bearer abc123def456ghi789")

    def test_bearer_case_insensitive(self):
        result = redact_text("authorization: BEARER secret_token_12345678")
        assert "[REDACTED]" in result

    def test_api_key_header(self):
        result = redact_text("api-key: abcdef1234567890")
        assert "[REDACTED]" in result

    def test_api_key_with_underscore(self):
        result = redact_text("api_key=abcdef1234567890")
        assert "[REDACTED]" in result

    def test_sk_prefix(self):
        """sk- prefix tokens match _LONG_TOKEN (sk-dash-16+chars) → [REDACTED_TOKEN]."""
        result = redact_text("sk-abcdef1234567890abcdef")
        # sk- with 20 alphanumeric chars → matches _LONG_TOKEN
        assert "[REDACTED_TOKEN]" in result

    # --- Long token (sk_/pk_/rk_) ---

    def test_sk_underscore_token(self):
        result = redact_text("sk_abcdef1234567890")
        assert "[REDACTED_TOKEN]" in result

    def test_pk_underscore_token(self):
        result = redact_text("pk_1234567890abcdef")
        assert "[REDACTED_TOKEN]" in result

    def test_rk_underscore_token(self):
        result = redact_text("rk_abcdef1234567890")
        assert "[REDACTED_TOKEN]" in result

    def test_token_with_dash_separator(self):
        """sk-live-... has a dash in the middle → NOT matched by _LONG_TOKEN.

        _LONG_TOKEN requires [A-Za-z0-9]{16,} after the sk-/pk-/rk- prefix.
        'sk-live-1234567890abcdef' has a dash in 'live-', breaking the char class.
        This is a known limitation of the regex.
        """
        result = redact_text("sk-live-1234567890abcdef")
        # Not redacted because the dash breaks the alphanumeric sequence
        assert result == "sk-live-1234567890abcdef"

    # --- No redaction needed ---

    def test_plain_text_unchanged(self):
        assert redact_text("Hello world") == "Hello world"

    def test_short_sk_underscore_not_redacted(self):
        """sk_ with fewer than 16 chars should NOT be redacted."""
        result = redact_text("sk_short")
        # "sk_short" is only 8 chars, below the 16-char threshold
        assert "[REDACTED_TOKEN]" not in result

    def test_exactly_16_chars_token(self):
        """Exactly 16 chars should be redacted."""
        result = redact_text("sk_1234567890abcdef")  # 16 chars after sk_
        assert "[REDACTED_TOKEN]" in result

    def test_15_chars_token_not_redacted(self):
        """15 chars should NOT be redacted."""
        result = redact_text("sk_1234567890abcde")  # 15 chars after sk_
        assert "[REDACTED_TOKEN]" not in result

    def test_sk_not_followed_by_underscore(self):
        """sk without underscore is not a token match."""
        result = redact_text("sk1234567890abcdef")
        # sk without _ is not matched by _LONG_TOKEN
        # But sk- prefix is matched by _BEARER if followed by >=8 chars
        # "sk-1234567890abcdef" would match, but "sk1234..." has no separator
        # Let's check: _BEARER matches "sk-" prefix, but "sk1234" has no dash
        assert result == "sk1234567890abcdef"  # unchanged

    # --- Empty / None ---

    def test_empty_string(self):
        assert redact_text("") == ""

    def test_none_text(self):
        assert redact_text(None) is None  # type: ignore[arg-type]

    # --- Boundary cases ---

    def test_token_at_end_of_string(self):
        result = redact_text("Key: sk_1234567890abcdef")
        assert "[REDACTED_TOKEN]" in result

    def test_token_at_start_of_string(self):
        result = redact_text("sk_1234567890abcdef is the key")
        assert "[REDACTED_TOKEN]" in result

    def test_email_within_longer_text(self):
        result = redact_text("Please contact user@example.com for details")
        assert "[REDACTED_EMAIL]" in result
        assert "for details" in result

    def test_multiple_redaction_types(self):
        result = redact_text(
            "Email: user@example.com, Token: sk_1234567890abcdef, API: api-key=secret12345678"
        )
        assert "[REDACTED_EMAIL]" in result
        assert "[REDACTED_TOKEN]" in result
        assert "[REDACTED]" in result

    def test_numbers_in_text_not_redacted(self):
        result = redact_text("Order total: $123.45")
        assert "[REDACTED]" not in result

    def test_short_bearer_value_not_redacted(self):
        """Bearer token with fewer than 8 chars in the value."""
        result = redact_text("Bearer abc")  # "abc" is only 3 chars
        # _BEARER requires >=8 chars in the value part
        assert "[REDACTED]" not in result


# ── redact_table_preview ───────────────────────────────────────────────

class TestRedactTablePreview:
    def test_redacts_columns(self):
        preview = {
            "columns": ["region", "email", "amount"],
            "rows": [],
        }
        result = redact_table_preview(preview)
        assert result["columns"] == ["region", "email", "amount"]

    def test_redacts_columns_with_email(self):
        preview = {
            "columns": ["user@example.com", "region"],
            "rows": [],
        }
        result = redact_table_preview(preview)
        assert result["columns"] == ["[REDACTED_EMAIL]", "region"]

    def test_redacts_dict_rows(self):
        preview = {
            "columns": ["name", "email"],
            "rows": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@test.org"},
            ],
        }
        result = redact_table_preview(preview)
        assert result["rows"][0]["email"] == "[REDACTED_EMAIL]"
        assert result["rows"][1]["email"] == "[REDACTED_EMAIL]"
        assert result["rows"][0]["name"] == "Alice"  # unchanged

    def test_redacts_list_rows(self):
        preview = {
            "columns": ["id", "contact"],
            "rows": [
                [1, "admin@corp.com"],
                [2, "support@corp.com"],
            ],
        }
        result = redact_table_preview(preview)
        assert result["rows"][0][1] == "[REDACTED_EMAIL]"
        assert result["rows"][1][1] == "[REDACTED_EMAIL]"
        assert result["rows"][0][0] == 1  # unchanged

    def test_redacts_tuple_rows(self):
        preview = {
            "columns": ["id", "token"],
            "rows": [
                (1, "sk_1234567890abcdef"),
            ],
        }
        result = redact_table_preview(preview)
        assert result["rows"][0][1] == "[REDACTED_TOKEN]"

    def test_redacts_scalar_rows(self):
        preview = {
            "columns": ["value"],
            "rows": [
                "user@example.com",
                "normal text",
                123,
            ],
        }
        result = redact_table_preview(preview)
        assert result["rows"][0] == "[REDACTED_EMAIL]"
        assert result["rows"][1] == "normal text"
        assert result["rows"][2] == 123

    def test_non_dict_preview_unchanged(self):
        preview = ["not", "a", "dict"]
        result = redact_table_preview(preview)
        assert result == ["not", "a", "dict"]

    def test_empty_rows_and_columns(self):
        preview = {"columns": [], "rows": []}
        result = redact_table_preview(preview)
        assert result == {"columns": [], "rows": []}

    def test_missing_rows_key(self):
        preview = {"columns": ["col1"]}
        result = redact_table_preview(preview)
        assert result["columns"] == ["col1"]

    def test_non_list_columns(self):
        """Non-list columns are passed through unchanged."""
        preview = {"columns": "not_a_list", "rows": []}
        result = redact_table_preview(preview)
        assert result["columns"] == "not_a_list"

    def test_table_with_token_in_cells(self):
        preview = {
            "columns": ["key", "value"],
            "rows": [
                {"key": "API_KEY", "value": "sk-abcdef1234567890abcdef"},
            ],
        }
        result = redact_table_preview(preview)
        # sk- with 20 alphanumeric chars → matches _LONG_TOKEN → [REDACTED_TOKEN]
        assert "[REDACTED_TOKEN]" in result["rows"][0]["value"]


# ── redact_preview_payload ─────────────────────────────────────────────

class TestRedactPreviewPayload:
    def test_redacts_preview(self):
        data = {
            "columns": ["email", "name"],
            "rows": [{"email": "test@example.com", "name": "Test"}],
            "row_count": 1,
        }
        result = redact_preview_payload(data)
        assert result["rows"][0]["email"] == "[REDACTED_EMAIL]"

    def test_extra_keys_preserved(self):
        data = {
            "columns": ["col"],
            "rows": [],
            "row_count": 0,
            "extra_meta": "keep_me",
        }
        result = redact_preview_payload(data)
        assert result["extra_meta"] == "keep_me"

    def test_non_dict_input(self):
        result = redact_preview_payload("not_a_dict")
        assert result == "not_a_dict"


# ── apply_output_guardrails ────────────────────────────────────────────

class TestApplyOutputGuardrails:
    def test_redacts_summary(self):
        result = apply_output_guardrails(
            {"summary": "Contact admin@corp.com for help"}
        )
        assert result["summary"] == "Contact [REDACTED_EMAIL] for help"

    def test_redacts_report_markdown(self):
        result = apply_output_guardrails(
            {
                "report": {
                    "markdown": "Key: sk_1234567890abcdef",
                    "title": "Report",
                }
            }
        )
        assert "[REDACTED_TOKEN]" in result["report"]["markdown"]

    def test_redacts_report_title(self):
        result = apply_output_guardrails(
            {"report": {"title": "Report for user@example.com"}}
        )
        assert result["report"]["title"] == "Report for [REDACTED_EMAIL]"

    def test_redacts_limitations(self):
        result = apply_output_guardrails(
            {"limitations": ["Contact admin@corp.com", "Normal note"]}
        )
        assert result["limitations"][0] == "Contact [REDACTED_EMAIL]"
        assert result["limitations"][1] == "Normal note"

    def test_redacts_table_preview_in_result(self):
        result = apply_output_guardrails(
            {
                "table_preview": {
                    "columns": ["email"],
                    "rows": [{"email": "test@example.com"}],
                }
            }
        )
        assert result["table_preview"]["rows"][0]["email"] == "[REDACTED_EMAIL]"

    def test_adds_platform_guardrails_marker(self):
        result = apply_output_guardrails({"summary": "test"})
        assert "platform" in result
        assert result["platform"]["guardrails"]["applied"] is True
        assert result["platform"]["guardrails"]["schema_version"] == 1
        assert "summary" in result["platform"]["guardrails"]["covers"]

    def test_preserves_existing_platform_keys(self):
        result = apply_output_guardrails(
            {
                "summary": "test",
                "platform": {"existing": "value"},
            }
        )
        assert result["platform"]["existing"] == "value"
        assert result["platform"]["guardrails"]["applied"] is True

    def test_non_dict_input(self):
        result = apply_output_guardrails("not_a_dict")
        assert result == "not_a_dict"

    def test_empty_dict(self):
        result = apply_output_guardrails({})
        assert result["platform"]["guardrails"]["applied"] is True

    def test_no_summary_no_report(self):
        result = apply_output_guardrails({"other_key": "value"})
        assert result["platform"]["guardrails"]["applied"] is True
        assert result["other_key"] == "value"

    def test_non_string_limitations(self):
        result = apply_output_guardrails(
            {"limitations": [123, None, "note"]}
        )
        assert result["limitations"][0] == 123
        assert result["limitations"][1] is None
        assert result["limitations"][2] == "note"

    def test_no_table_preview_not_added(self):
        result = apply_output_guardrails({"summary": "test"})
        assert "table_preview" not in result


# ── Integration scenarios ──────────────────────────────────────────────

class TestGuardrailsIntegration:
    """Tests that simulate real output flows."""

    def test_full_analysis_result(self):
        """Simulate a complete analysis result JSON."""
        result = apply_output_guardrails(
            {
                "summary": "Analysis shows admin@corp.com has highest sales",
                "report": {
                    "title": "Report for admin@corp.com",
                    "markdown": "Key metrics. Token: sk_1234567890abcdef",
                },
                "limitations": [
                    "Data excludes admin@corp.com records",
                    "Based on 2024 data only",
                ],
                "table_preview": {
                    "columns": ["region", "email", "amount"],
                    "rows": [
                        {"region": "East", "email": "east@corp.com", "amount": 100},
                        {"region": "West", "email": "west@corp.com", "amount": 200},
                    ],
                },
            }
        )
        # Check summary redaction
        assert "admin@corp.com" not in result["summary"]
        assert "[REDACTED_EMAIL]" in result["summary"]

        # Check report redaction
        assert "admin@corp.com" not in result["report"]["title"]
        assert "sk_1234567890abcdef" not in result["report"]["markdown"]

        # Check limitations redaction
        assert "admin@corp.com" not in result["limitations"][0]
        assert result["limitations"][1] == "Based on 2024 data only"

        # Check table preview redaction
        assert result["table_preview"]["rows"][0]["email"] == "[REDACTED_EMAIL]"
        assert result["table_preview"]["rows"][1]["email"] == "[REDACTED_EMAIL]"

        # Check platform marker
        assert result["platform"]["guardrails"]["applied"] is True