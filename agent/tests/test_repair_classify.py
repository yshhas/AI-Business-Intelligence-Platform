"""Unit tests for agent.repair_classify — deterministic error classification.

Tests cover:
- All 7 RepairClass types
- Both stages (validate / execute)
- Priority ordering: multi-keyword conflicts
- Edge cases: None, empty, unknown, case insensitivity
- Caller integration: validate_sql Gate errors, execute_sql runtime errors
- RepairHint: classify_with_hint, action templates, is_repairable
"""

from __future__ import annotations

import pytest

from agent.repair_classify import (
    RepairClass,
    RepairHint,
    classify_repair_error,
    classify_with_hint,
)


# ── RepairClass type ───────────────────────────────────────────────────

class TestRepairClassType:
    """Verify the 7 valid RepairClass values."""

    VALID_CLASSES: set[RepairClass] = {
        "policy_keyword",
        "policy_allowlist",
        "policy_limit",
        "policy_other",
        "engine_syntax",
        "engine_runtime",
        "empty_result",
        "unknown",
    }

    def test_all_valid_classes(self):
        assert len(self.VALID_CLASSES) == 8

    def test_literal_type_accepts_all(self):
        """Simple compile-time check that the Literal is correctly typed."""
        # This is a runtime sanity check only
        classes: set[RepairClass] = {
            "policy_keyword",
            "policy_allowlist",
            "policy_limit",
            "policy_other",
            "engine_syntax",
            "engine_runtime",
            "empty_result",
            "unknown",
        }
        assert isinstance(list(classes)[0], str)


# ── Empty / None input ─────────────────────────────────────────────────

class TestEmptyInput:
    def test_none_message(self):
        assert classify_repair_error(None) == "unknown"

    def test_empty_string(self):
        assert classify_repair_error("") == "unknown"

    def test_whitespace_only(self):
        assert classify_repair_error("   \t\n  ") == "unknown"

    def test_none_with_execute_stage(self):
        assert classify_repair_error(None, stage="execute") == "unknown"

    def test_empty_with_execute_stage(self):
        assert classify_repair_error("", stage="execute") == "unknown"


# ── policy_allowlist ───────────────────────────────────────────────────

class TestPolicyAllowlist:
    def test_allowlist_keyword(self):
        assert classify_repair_error("Table not in allowlist") == "policy_allowlist"

    def test_not_in_allowlist_phrase(self):
        assert classify_repair_error("Table 'secret' is not in allowlist ['ds_test']") == "policy_allowlist"

    def test_unknown_table(self):
        assert classify_repair_error("unknown table: ds_secret") == "policy_allowlist"

    def test_allowlist_case_insensitive(self):
        assert classify_repair_error("ALLOWLIST violation") == "policy_allowlist"

    def test_allowlist_in_execute_stage(self):
        """Even in execute stage, allowlist errors are policy errors."""
        assert classify_repair_error("Table not in allowlist", stage="execute") == "policy_allowlist"


# ── policy_keyword ─────────────────────────────────────────────────────

class TestPolicyKeyword:
    def test_forbidden_keyword(self):
        assert classify_repair_error("Forbidden keyword detected") == "policy_keyword"

    def test_keyword_alone(self):
        assert classify_repair_error("suspicious keyword in query") == "policy_keyword"

    def test_ddl_detected(self):
        assert classify_repair_error("DDL detected in query") == "policy_keyword"

    def test_dml_detected(self):
        assert classify_repair_error("DML operation blocked") == "policy_keyword"

    def test_forbidden_case_insensitive(self):
        assert classify_repair_error("FORBIDDEN KEYWORD DETECTED") == "policy_keyword"

    def test_keyword_in_execute_stage(self):
        assert classify_repair_error("Forbidden keyword", stage="execute") == "policy_keyword"


# ── policy_limit ───────────────────────────────────────────────────────

class TestPolicyLimit:
    def test_limit_missing(self):
        assert classify_repair_error("LIMIT missing from query") == "policy_limit"

    def test_limit_required(self):
        assert classify_repair_error("LIMIT required for safety") == "policy_limit"

    def test_limit_exceeded(self):
        assert classify_repair_error("LIMIT exceeded maximum value") == "policy_limit"

    def test_limit_alone_not_enough(self):
        """'limit' alone without missing/required/exceed is not policy_limit."""
        # This would fall through to policy_other or unknown
        result = classify_repair_error("limit is too high")
        # "limit" alone doesn't trigger policy_limit (needs missing/required/exceed)
        assert result != "policy_limit"

    def test_limit_case_insensitive(self):
        assert classify_repair_error("LIMIT MISSING") == "policy_limit"


# ── policy_other ───────────────────────────────────────────────────────

class TestPolicyOther:
    def test_gate_rejection(self):
        assert classify_repair_error("Gate rejected query") == "policy_other"

    def test_policy_error(self):
        assert classify_repair_error("policy engine blocked statement") == "policy_other"

    def test_sql_policy(self):
        assert classify_repair_error("sql policy violation") == "policy_other"

    def test_gate_case_insensitive(self):
        assert classify_repair_error("GATE blocked") == "policy_other"

    def test_policy_in_execute_stage(self):
        assert classify_repair_error("gate: multiple statements", stage="execute") == "policy_other"


# ── engine_syntax ──────────────────────────────────────────────────────

class TestEngineSyntax:
    def test_syntax_error(self):
        assert classify_repair_error("syntax error in query") == "engine_syntax"

    def test_parse_error(self):
        assert classify_repair_error("parse error at line 1") == "engine_syntax"

    def test_unexpected_token(self):
        assert classify_repair_error("unexpected token at position 5") == "engine_syntax"

    def test_near_keyword(self):
        """Common SQL parser error: 'syntax error near DROP'."""
        assert classify_repair_error("syntax error near 'DROP'") == "engine_syntax"

    def test_token_error(self):
        assert classify_repair_error("token mismatch") == "engine_syntax"

    def test_malformed_query(self):
        assert classify_repair_error("malformed SQL statement") == "engine_syntax"

    def test_syntax_in_execute_stage(self):
        assert classify_repair_error("syntax error", stage="execute") == "engine_syntax"


# ── empty_result ───────────────────────────────────────────────────────

class TestEmptyResult:
    def test_no_rows(self):
        assert classify_repair_error("Query returned no rows", stage="execute") == "empty_result"

    def test_empty_result(self):
        assert classify_repair_error("empty result set", stage="execute") == "empty_result"

    def test_empty_not_in_validate(self):
        """'empty' in validate stage should NOT return empty_result."""
        result = classify_repair_error("empty SQL", stage="validate")
        # Stage is validate, so empty_result check is skipped
        # Falls to engine_syntax (no match) → unknown
        assert result != "empty_result"

    def test_no_rows_not_in_validate(self):
        result = classify_repair_error("no rows", stage="validate")
        assert result != "empty_result"

    def test_empty_case_insensitive(self):
        assert classify_repair_error("NO ROWS returned", stage="execute") == "empty_result"


# ── engine_runtime ─────────────────────────────────────────────────────

class TestEngineRuntime:
    def test_generic_execute_error(self):
        assert classify_repair_error("Something went wrong", stage="execute") == "engine_runtime"

    def test_type_error_in_execute(self):
        assert classify_repair_error("TypeError: unsupported operand", stage="execute") == "engine_runtime"

    def test_connection_error_in_execute(self):
        assert classify_repair_error("Connection refused", stage="execute") == "engine_runtime"

    def test_not_in_validate(self):
        """Stage=validate should NOT return engine_runtime for unknown errors."""
        result = classify_repair_error("Something went wrong", stage="validate")
        assert result != "engine_runtime"
        assert result == "unknown"


# ── unknown ────────────────────────────────────────────────────────────

class TestUnknown:
    def test_completely_unrecognized(self):
        assert classify_repair_error("xyz invalid message") == "unknown"

    def test_unknown_in_validate(self):
        assert classify_repair_error("internal error", stage="validate") == "unknown"

    def test_generic_exception_message(self):
        assert classify_repair_error("An error occurred") == "unknown"


# ── Priority ordering (multi-keyword conflicts) ────────────────────────

class TestPriorityOrdering:
    """Classification is order-dependent. Earlier matches win."""

    def test_allowlist_beats_keyword(self):
        """'allowlist' is checked before 'keyword'."""
        result = classify_repair_error(
            "Forbidden keyword: table not in allowlist"
        )
        assert result == "policy_allowlist"

    def test_keyword_beats_limit(self):
        """'keyword' is checked before 'limit'."""
        result = classify_repair_error(
            "Forbidden keyword detected: limit exceeded"
        )
        assert result == "policy_keyword"

    def test_gate_beats_syntax(self):
        """'gate' is checked before 'syntax'."""
        result = classify_repair_error(
            "gate: syntax error near 'DROP'"
        )
        assert result == "policy_other"

    def test_policy_beats_syntax(self):
        """'policy' is checked before 'syntax'."""
        result = classify_repair_error(
            "sql policy: syntax error in statement"
        )
        assert result == "policy_other"

    def test_empty_result_beats_allowlist(self):
        """'empty' + stage=execute is checked before 'allowlist'."""
        result = classify_repair_error(
            "empty result: table not in allowlist",
            stage="execute",
        )
        assert result == "empty_result"

    def test_allowlist_beats_engine_runtime_in_execute(self):
        """'allowlist' in execute still returns policy_allowlist, not engine_runtime."""
        result = classify_repair_error(
            "Table not in allowlist",
            stage="execute",
        )
        assert result == "policy_allowlist"

    def test_syntax_beats_engine_runtime_in_execute(self):
        """'syntax' in execute returns engine_syntax, not engine_runtime."""
        result = classify_repair_error(
            "syntax error in query",
            stage="execute",
        )
        assert result == "engine_syntax"


# ── Real-world Gate error messages ─────────────────────────────────────

class TestRealWorldGateErrors:
    """Test with actual error messages produced by sql_gate.py."""

    def test_empty_sql(self):
        assert classify_repair_error("Empty SQL") == "unknown"

    def test_multiple_statements(self):
        """'Multiple statements' message has no trigger keywords → unknown."""
        assert classify_repair_error("Multiple statements are not allowed") == "unknown"

    def test_forbidden_keyword_gate(self):
        assert classify_repair_error("Forbidden keyword detected (write/DDL/admin)") == "policy_keyword"

    def test_only_select_allowed(self):
        """'Only SELECT/WITH' message has no trigger keywords → unknown."""
        assert classify_repair_error("Only SELECT/WITH queries are allowed (got 'SHOW')") == "unknown"

    def test_could_not_resolve_table(self):
        assert classify_repair_error("Could not resolve table name from SQL") == "unknown"

    def test_table_not_in_allowlist_gate(self):
        assert classify_repair_error(
            "Table 'secret' is not in allowlist ['ds_test']"
        ) == "policy_allowlist"


# ── Real-world execute errors ──────────────────────────────────────────

class TestRealWorldExecuteErrors:
    """Test with error messages that DuckDB / PostgreSQL might produce."""

    def test_duckdb_syntax_error(self):
        assert classify_repair_error(
            "Parser Error: syntax error at or near \"FROM\"",
            stage="execute",
        ) == "engine_syntax"

    def test_duckdb_column_not_found(self):
        # "unknown" is not in the keyword list, no policy/engine match
        result = classify_repair_error(
            "Binder Error: Referenced column \"unknown_col\" not found",
            stage="execute",
        )
        # "unknown" appears in the message, but "unknown" is not a trigger keyword
        # Falls to engine_runtime (stage=execute)
        assert result == "engine_runtime"

    def test_postgres_relation_not_found(self):
        result = classify_repair_error(
            'relation "nonexistent" does not exist',
            stage="execute",
        )
        assert result == "engine_runtime"

    def test_division_by_zero(self):
        result = classify_repair_error(
            "Division by zero",
            stage="execute",
        )
        assert result == "engine_runtime"

    def test_no_rows_returned(self):
        assert classify_repair_error(
            "Query executed successfully but returned no rows",
            stage="execute",
        ) == "empty_result"


# ── Edge cases ─────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_very_long_message(self):
        msg = "Error: " + "very " * 100 + "long message"
        result = classify_repair_error(msg)
        # Should not crash
        assert result in ("unknown", "engine_runtime")

    def test_only_keyword_token(self):
        """Just the word 'allowlist' alone."""
        assert classify_repair_error("allowlist") == "policy_allowlist"

    def test_only_forbidden_token(self):
        assert classify_repair_error("forbidden") == "policy_keyword"

    def test_default_stage_is_validate(self):
        """Default stage parameter should be 'validate'."""
        result = classify_repair_error("Something")
        assert result == "unknown"
        # Same message with stage="execute" would be engine_runtime
        assert classify_repair_error("Something", stage="execute") == "engine_runtime"

    def test_stage_not_affecting_early_checks(self):
        """Stage only affects empty_result and engine_runtime checks."""
        assert classify_repair_error("syntax error", stage="validate") == "engine_syntax"
        assert classify_repair_error("syntax error", stage="execute") == "engine_syntax"


# ── RepairHint dataclass ────────────────────────────────────────────────

class TestRepairHintDataclass:
    """RepairHint construction, frozen, backward compat."""

    def test_construct(self):
        hint = RepairHint(
            repair_class="policy_allowlist",
            action="Use allowed tables",
            is_repairable=True,
        )
        assert hint.repair_class == "policy_allowlist"
        assert hint.action == "Use allowed tables"
        assert hint.is_repairable is True

    def test_frozen(self):
        hint = RepairHint(repair_class="unknown", action="x", is_repairable=False)
        with pytest.raises(Exception):
            hint.is_repairable = True  # type: ignore[misc]

    def test_as_tagged_error(self):
        hint = RepairHint(
            repair_class="policy_allowlist",
            action="x",
            is_repairable=True,
        )
        assert hint.as_tagged_error("Table not in allowlist") == (
            "[policy_allowlist] Table not in allowlist"
        )

    def test_as_tagged_error_preserves_message(self):
        hint = RepairHint(
            repair_class="unknown",
            action="x",
            is_repairable=True,
        )
        assert hint.as_tagged_error("Something went wrong") == (
            "[unknown] Something went wrong"
        )


# ── classify_with_hint — all 8 RepairClass types ────────────────────────

class TestClassifyWithHintAllTypes:
    """Verify classify_with_hint returns correct RepairHint for each class."""

    def test_policy_allowlist(self):
        hint = classify_with_hint("Table 'cte' is not in allowlist")
        assert hint.repair_class == "policy_allowlist"
        assert "allowed tables" in hint.action.lower()
        assert hint.is_repairable is True

    def test_policy_keyword(self):
        """policy_keyword is NOT in _REPAIRABLE by default."""
        hint = classify_with_hint("Forbidden keyword detected (DROP)")
        assert hint.repair_class == "policy_keyword"
        assert "forbidden" in hint.action.lower()
        assert hint.is_repairable is False

    def test_policy_keyword_override(self):
        """Override makes policy_keyword repairable."""
        hint = classify_with_hint(
            "Forbidden keyword detected",
            repairable_override={"policy_keyword": True},
        )
        assert hint.is_repairable is True

    def test_policy_limit(self):
        hint = classify_with_hint("LIMIT is required but missing")
        assert hint.repair_class == "policy_limit"
        assert "limit" in hint.action.lower()
        assert hint.is_repairable is True

    def test_policy_other(self):
        hint = classify_with_hint("SQL policy violation")
        assert hint.repair_class == "policy_other"
        assert "gate" in hint.action.lower()
        assert hint.is_repairable is True

    def test_engine_syntax(self):
        hint = classify_with_hint("syntax error at or near")
        assert hint.repair_class == "engine_syntax"
        assert "syntax" in hint.action.lower()
        assert hint.is_repairable is True

    def test_engine_runtime(self):
        hint = classify_with_hint("Division by zero", stage="execute")
        assert hint.repair_class == "engine_runtime"
        assert "column" in hint.action.lower()
        assert hint.is_repairable is True

    def test_empty_result(self):
        hint = classify_with_hint("no rows returned", stage="execute")
        assert hint.repair_class == "empty_result"
        assert "no rows" in hint.action.lower()
        assert hint.is_repairable is True

    def test_empty_result_validate_stage(self):
        """'no rows' at validate stage should NOT trigger empty_result."""
        hint = classify_with_hint("no rows", stage="validate")
        assert hint.repair_class == "unknown"
        assert hint.is_repairable is False

    def test_unknown(self):
        hint = classify_with_hint("some random error")
        assert hint.repair_class == "unknown"
        assert "unrecognized" in hint.action.lower()
        assert hint.is_repairable is False


# ── classify_with_hint — edge cases ─────────────────────────────────────

class TestClassifyWithHintEdgeCases:
    """Edge cases for classify_with_hint."""

    def test_none_message(self):
        hint = classify_with_hint(None)
        assert hint.repair_class == "unknown"
        assert hint.is_repairable is False

    def test_empty_message(self):
        hint = classify_with_hint("")
        assert hint.repair_class == "unknown"
        assert hint.is_repairable is False

    def test_whitespace_message(self):
        hint = classify_with_hint("   ")
        assert hint.repair_class == "unknown"
        assert hint.is_repairable is False

    def test_override_non_repairable(self):
        """Override can make unknown repairable."""
        hint = classify_with_hint(
            "random error",
            repairable_override={"unknown": True},
        )
        assert hint.is_repairable is True

    def test_override_does_not_affect_other(self):
        """Override on one class does not affect others."""
        hint = classify_with_hint(
            "Forbidden keyword detected",
            repairable_override={"policy_allowlist": True},
        )
        assert hint.repair_class == "policy_keyword"
        assert hint.is_repairable is False

    def test_classify_with_hint_vs_classify_repair_error_consistency(self):
        """classify_with_hint MUST produce same repair_class as classify_repair_error."""
        test_cases = [
            ("Table not in allowlist", "validate", "policy_allowlist"),
            ("Forbidden keyword", "validate", "policy_keyword"),
            ("LIMIT is required", "validate", "policy_limit"),
            ("Gate policy violation", "validate", "policy_other"),
            ("syntax error", "validate", "engine_syntax"),
            ("Division by zero", "execute", "engine_runtime"),
            ("no rows returned", "execute", "empty_result"),
            ("random", "validate", "unknown"),
        ]
        for msg, stage, expected in test_cases:
            rc = classify_repair_error(msg, stage=stage)
            hint = classify_with_hint(msg, stage=stage)
            assert hint.repair_class == rc == expected, f"mismatch on {msg!r}"


# ── classify_with_hint — real-world Gate errors ─────────────────────────

class TestClassifyWithHintRealWorld:
    """classify_with_hint with actual sql_gate.py error messages."""

    def test_gate_empty_sql(self):
        hint = classify_with_hint("Empty SQL")
        assert hint.repair_class == "unknown"
        assert hint.is_repairable is False

    def test_gate_multiple_statements(self):
        hint = classify_with_hint("Multiple statements are not allowed")
        assert hint.repair_class == "unknown"
        assert hint.is_repairable is False

    def test_gate_forbidden_keyword(self):
        hint = classify_with_hint("Forbidden keyword detected (write/DDL/admin)")
        assert hint.repair_class == "policy_keyword"
        assert hint.is_repairable is False

    def test_gate_allowlist(self):
        hint = classify_with_hint("Table 'secret' is not in allowlist ['ds_test']")
        assert hint.repair_class == "policy_allowlist"
        assert hint.is_repairable is True

    def test_duckdb_syntax(self):
        hint = classify_with_hint(
            'Parser Error: syntax error at or near "FROM"',
            stage="execute",
        )
        assert hint.repair_class == "engine_syntax"
        assert hint.is_repairable is True

    def test_duckdb_column_not_found(self):
        hint = classify_with_hint(
            'Binder Error: Referenced column "unknown_col" not found',
            stage="execute",
        )
        assert hint.repair_class == "engine_runtime"
        assert hint.is_repairable is True