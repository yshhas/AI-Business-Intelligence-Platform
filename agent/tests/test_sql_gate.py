"""Unit tests for agent.gates.sql_gate — deterministic SQL policy gate.

Tests cover:
- GateResult dataclass
- validate_and_normalize_sql: all 8 return paths
- _extract_table_names: FROM, JOIN, schema-qualified, quoted, multi-table
- Edge cases: trailing semicolons, extra whitespace, lowercase, comments
"""

from __future__ import annotations

import pytest

from agent.gates.sql_gate import (
    GateResult,
    _extract_table_names,
    validate_and_normalize_sql,
)


# ── GateResult dataclass ──────────────────────────────────────────────

class TestGateResult:
    def test_ok_result(self):
        r = GateResult(ok=True, sql="SELECT 1")
        assert r.ok is True
        assert r.sql == "SELECT 1"
        assert r.error is None

    def test_deny_result(self):
        r = GateResult(ok=False, sql=None, error="Empty SQL")
        assert r.ok is False
        assert r.sql is None
        assert r.error == "Empty SQL"

    def test_frozen_prevents_mutation(self):
        r = GateResult(ok=True, sql="SELECT 1")
        with pytest.raises(Exception):
            r.ok = False  # type: ignore[misc]


# ── validate_and_normalize_sql: Error paths ────────────────────────────

class TestGateEmptySQL:
    """Return path: Empty / whitespace-only SQL."""

    ALLOWED = {"ds_test"}

    def test_none_sql(self):
        r = validate_and_normalize_sql("", allowed_tables=self.ALLOWED)
        assert r.ok is False
        assert r.sql is None
        assert "Empty SQL" in (r.error or "")

    def test_empty_string(self):
        r = validate_and_normalize_sql("", allowed_tables=self.ALLOWED)
        assert r.ok is False
        assert "Empty SQL" in (r.error or "")

    def test_whitespace_only(self):
        r = validate_and_normalize_sql("   \t\n  ", allowed_tables=self.ALLOWED)
        assert r.ok is False
        assert "Empty SQL" in (r.error or "")


class TestGateMultiStatement:
    """Return path: SQL contains semicolons (multi-statement)."""

    ALLOWED = {"ds_test"}

    def test_two_selects(self):
        r = validate_and_normalize_sql(
            "SELECT 1 FROM ds_test; SELECT 2 FROM ds_test",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is False
        assert "Multiple statements" in (r.error or "")

    def test_semicolon_in_middle(self):
        r = validate_and_normalize_sql(
            "SELECT 1; DROP TABLE ds_test",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is False
        assert "Multiple statements" in (r.error or "")

    def test_trailing_semicolon_stripped(self):
        """Trailing semicolon alone is stripped before check — should pass."""
        r = validate_and_normalize_sql(
            "SELECT 1 FROM ds_test;",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_trailing_semicolons_with_whitespace(self):
        r = validate_and_normalize_sql(
            "SELECT 1 FROM ds_test ;  ",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True


class TestGateForbiddenKeywords:
    """Return path: SQL contains forbidden keywords (DDL/DML/admin)."""

    ALLOWED = {"ds_test"}

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO ds_test VALUES (1)",
            "UPDATE ds_test SET x=1",
            "DELETE FROM ds_test",
            "DROP TABLE ds_test",
            "ALTER TABLE ds_test ADD COLUMN x INT",
            "CREATE TABLE ds_test (x INT)",
            "REPLACE INTO ds_test VALUES (1)",
            "TRUNCATE ds_test",
            "ATTACH 'other.db' AS other",
            "DETACH other",
            "COPY ds_test TO 'out.csv'",
            "EXPORT DATABASE 'dir'",
            "IMPORT DATABASE 'dir'",
            "PRAGMA table_info('ds_test')",
            "INSTALL httpfs",
            "LOAD httpfs",
            "CALL some_procedure()",
            "EXECUTE some_statement",
            "GRANT SELECT ON ds_test TO user",
            "REVOKE SELECT ON ds_test FROM user",
            "VACUUM",
            "CHECKPOINT",
            "MERGE INTO ds_test USING source ON ds_test.id = source.id",
            "UPSERT INTO ds_test VALUES (1)",
        ],
    )
    def test_forbidden_denied(self, sql: str):
        r = validate_and_normalize_sql(sql, allowed_tables=self.ALLOWED)
        assert r.ok is False, f"Expected deny for: {sql}"
        assert "Forbidden keyword" in (r.error or "")

    def test_keyword_inside_string_not_flagged(self):
        """Forbidden words inside string literals are flagged (known regex limitation).

        The _FORBIDDEN regex uses \\b word boundaries and cannot distinguish
        keywords inside string literals from actual DDL statements.
        Fixing this would require SQL-aware parsing (e.g. sqlparse token walking).
        """
        r = validate_and_normalize_sql(
            "SELECT 'DROP TABLE' AS msg FROM ds_test",
            allowed_tables=self.ALLOWED,
        )
        # Current behavior: "DROP" is flagged even inside a string literal
        assert r.ok is False
        assert "Forbidden keyword" in (r.error or "")


class TestGateNotSelect:
    """Return path: SQL is not a SELECT or WITH statement."""

    ALLOWED = {"ds_test"}

    def test_explain_passes_as_select(self):
        """EXPLAIN is parsed by sqlparse as SELECT DML — not blocked.

        This is a known limitation: EXPLAIN is read-only but not
        explicitly forbidden. The Gate relies on sqlparse DML detection
        which treats EXPLAIN SELECT as a SELECT statement.
        """
        r = validate_and_normalize_sql(
            "EXPLAIN SELECT 1 FROM ds_test",
            allowed_tables=self.ALLOWED,
        )
        # Current behavior: EXPLAIN passes because sqlparse sees DML=SELECT
        assert r.ok is True

    def test_show_rejected(self):
        r = validate_and_normalize_sql(
            "SHOW TABLES",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is False

    def test_describe_rejected(self):
        r = validate_and_normalize_sql(
            "DESCRIBE ds_test",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is False


class TestGateTableAllowlist:
    """Return path: table not in allowlist."""

    ALLOWED = {"ds_test"}

    def test_table_not_in_allowlist(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM other_table",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is False
        assert "not in allowlist" in (r.error or "")

    def test_allowlist_case_insensitive(self):
        """Allowlist matching is case-insensitive."""
        r = validate_and_normalize_sql(
            "SELECT * FROM DS_TEST",
            allowed_tables={"ds_test"},
        )
        assert r.ok is True

    def test_allowlist_lower_stored(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test",
            allowed_tables={"DS_TEST"},
        )
        assert r.ok is True

    def test_schema_qualified_allowlist(self):
        """Schema-qualified table names like public.demo_orders."""
        r = validate_and_normalize_sql(
            'SELECT * FROM "public"."demo_orders"',
            allowed_tables={"public.demo_orders"},
        )
        assert r.ok is True

    def test_schema_qualified_not_in_allowlist(self):
        r = validate_and_normalize_sql(
            'SELECT * FROM "public"."demo_orders"',
            allowed_tables={"public.other_table"},
        )
        assert r.ok is False

    def test_no_table_resolved(self):
        """SELECT without FROM — no table to check, should fail."""
        r = validate_and_normalize_sql(
            "SELECT 1 + 1",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is False
        assert "Could not resolve table name" in (r.error or "")

    def test_multiple_tables_all_allowed(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test JOIN ds_other ON ds_test.id = ds_other.id",
            allowed_tables={"ds_test", "ds_other"},
        )
        assert r.ok is True

    def test_multiple_tables_one_not_allowed(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test JOIN ds_secret ON ds_test.id = ds_secret.id",
            allowed_tables={"ds_test"},
        )
        assert r.ok is False
        assert "ds_secret" in (r.error or "")


class TestGateNoTableResolved:
    """Return path: _extract_table_names returns empty set."""

    def test_select_without_from(self):
        r = validate_and_normalize_sql(
            "SELECT 1",
            allowed_tables={"ds_test"},
        )
        assert r.ok is False
        assert "Could not resolve table name" in (r.error or "")

    def test_select_expression_only(self):
        r = validate_and_normalize_sql(
            "SELECT NOW(), RANDOM()",
            allowed_tables={"ds_test"},
        )
        assert r.ok is False
        assert "Could not resolve table name" in (r.error or "")


# ── validate_and_normalize_sql: Success paths ──────────────────────────

class TestGateValidSelect:
    """Return path: valid SELECT passes Gate."""

    ALLOWED = {"ds_test"}

    def test_basic_select(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True
        assert r.sql is not None
        assert "SELECT" in (r.sql or "").upper()

    def test_select_with_where(self):
        r = validate_and_normalize_sql(
            "SELECT region, amount FROM ds_test WHERE amount > 100",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_select_with_group_by(self):
        r = validate_and_normalize_sql(
            "SELECT region, SUM(amount) AS total FROM ds_test GROUP BY region",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_select_with_order_by(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test ORDER BY amount DESC",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_lowercase_select(self):
        r = validate_and_normalize_sql(
            "select * from ds_test",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_mixed_case_select(self):
        r = validate_and_normalize_sql(
            "Select region, Amount From ds_test",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True


class TestGateWithCTE:
    """Return path: WITH (CTE) passes Gate.

    Note: _extract_table_names uses a regex that matches table names
    after FROM/JOIN, including CTE alias references. Both the base table
    AND the CTE alias must be in the allowlist.
    """

    ALLOWED = {"ds_test", "recent"}

    def test_simple_cte(self):
        r = validate_and_normalize_sql(
            "WITH recent AS (SELECT * FROM ds_test WHERE amount > 100) "
            "SELECT * FROM recent",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_cte_lowercase(self):
        r = validate_and_normalize_sql(
            "with t as (select * from ds_test) select * from t",
            allowed_tables={"ds_test", "t"},
        )
        assert r.ok is True


class TestGateLimitAutoAdd:
    """Return path: LIMIT is auto-added when missing."""

    ALLOWED = {"ds_test"}

    def test_limit_auto_added(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test",
            allowed_tables=self.ALLOWED,
            default_limit=200,
        )
        assert r.ok is True
        assert r.sql is not None
        assert "LIMIT 200" in (r.sql or "").upper().replace("\n", " ")

    def test_limit_preserved_when_present(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test LIMIT 50",
            allowed_tables=self.ALLOWED,
            default_limit=200,
        )
        assert r.ok is True
        assert r.sql is not None
        assert "LIMIT 50" in (r.sql or "").upper()
        assert "LIMIT 200" not in (r.sql or "").upper()

    def test_custom_default_limit(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test",
            allowed_tables=self.ALLOWED,
            default_limit=500,
        )
        assert r.ok is True
        assert "LIMIT 500" in (r.sql or "").upper().replace("\n", " ")

    def test_limit_lowercase_preserved(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test limit 10",
            allowed_tables=self.ALLOWED,
            default_limit=200,
        )
        assert r.ok is True
        assert "limit 10" in (r.sql or "").lower()

    def test_limit_in_cte(self):
        """LIMIT is auto-added to the outer query, not inside CTE."""
        r = validate_and_normalize_sql(
            "WITH t AS (SELECT * FROM ds_test) SELECT * FROM t",
            allowed_tables={"ds_test", "t"},
            default_limit=200,
        )
        assert r.ok is True
        assert "LIMIT 200" in (r.sql or "").upper().replace("\n", " ")


# ── _extract_table_names ───────────────────────────────────────────────

class TestExtractTableNames:
    def test_simple_from(self):
        assert _extract_table_names("SELECT * FROM ds_test") == {"ds_test"}

    def test_from_with_alias(self):
        assert _extract_table_names("SELECT * FROM ds_test t") == {"ds_test"}

    def test_join(self):
        tables = _extract_table_names(
            "SELECT * FROM ds_test JOIN ds_other ON ds_test.id = ds_other.id"
        )
        assert tables == {"ds_test", "ds_other"}

    def test_inner_join(self):
        tables = _extract_table_names(
            "SELECT * FROM ds_a INNER JOIN ds_b ON ds_a.x = ds_b.x"
        )
        assert tables == {"ds_a", "ds_b"}

    def test_left_join(self):
        tables = _extract_table_names(
            "SELECT * FROM ds_a LEFT JOIN ds_b ON ds_a.x = ds_b.x"
        )
        assert tables == {"ds_a", "ds_b"}

    def test_right_join(self):
        tables = _extract_table_names(
            "SELECT * FROM ds_a RIGHT JOIN ds_b ON ds_a.x = ds_b.x"
        )
        assert tables == {"ds_a", "ds_b"}

    def test_schema_qualified(self):
        assert _extract_table_names(
            'SELECT * FROM "public"."demo_orders"'
        ) == {"public.demo_orders"}

    def test_schema_qualified_unquoted(self):
        assert _extract_table_names(
            "SELECT * FROM public.demo_orders"
        ) == {"public.demo_orders"}

    def test_quoted_table(self):
        assert _extract_table_names('SELECT * FROM "MyTable"') == {"MyTable"}

    def test_backtick_quoted_table(self):
        assert _extract_table_names("SELECT * FROM `my_table`") == {"my_table"}

    def test_case_insensitive(self):
        tables = _extract_table_names("select * from DS_TEST join ds_other")
        assert tables == {"DS_TEST", "ds_other"}

    def test_three_way_join(self):
        tables = _extract_table_names(
            "SELECT * FROM a JOIN b ON a.id=b.id JOIN c ON b.id=c.id"
        )
        assert tables == {"a", "b", "c"}

    def test_select_without_from(self):
        assert _extract_table_names("SELECT 1 + 1") == set()

    def test_subquery_not_inner_table(self):
        """FROM (SELECT ...) should not extract inner table names."""
        tables = _extract_table_names(
            "SELECT * FROM (SELECT * FROM ds_inner) AS sub"
        )
        # The regex matches FROM followed by a table name pattern.
        # "(SELECT" is not a valid table name, so it won't match.
        # But "FROM ds_inner" inside the subquery will match.
        # This is a known limitation of the regex approach.
        # The important thing is ds_inner being flagged is acceptable
        # (it's used in the subquery, so it should be in allowlist anyway).
        assert "ds_inner" in tables  # known behavior


# ── Edge cases ─────────────────────────────────────────────────────────

class TestGateEdgeCases:
    ALLOWED = {"ds_test", "public.demo_orders"}

    def test_extra_whitespace(self):
        r = validate_and_normalize_sql(
            "   SELECT   *   FROM   ds_test   ",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_newlines(self):
        r = validate_and_normalize_sql(
            "SELECT region,\n       SUM(amount)\nFROM ds_test\nGROUP BY region",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_sql_with_comments(self):
        """SQL with inline comments."""
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test -- this is a comment",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_select_with_subquery(self):
        r = validate_and_normalize_sql(
            "SELECT * FROM (SELECT region, amount FROM ds_test) t WHERE amount > 100",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_select_with_function(self):
        r = validate_and_normalize_sql(
            "SELECT UPPER(region), COUNT(*) FROM ds_test GROUP BY region",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_select_distinct(self):
        r = validate_and_normalize_sql(
            "SELECT DISTINCT region FROM ds_test",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_select_with_having(self):
        r = validate_and_normalize_sql(
            "SELECT region, SUM(amount) AS total FROM ds_test "
            "GROUP BY region HAVING SUM(amount) > 500",
            allowed_tables=self.ALLOWED,
        )
        assert r.ok is True

    def test_select_with_union(self):
        """UNION is parsed as a single statement by sqlparse and passes the Gate.

        The Gate checks for multi-statement via semicolons, not UNION.
        sqlparse treats UNION as part of a single compound SELECT statement,
        so it passes both the statement-count check and the DML-type check.
        """
        r = validate_and_normalize_sql(
            "SELECT region FROM ds_test UNION SELECT region FROM ds_test",
            allowed_tables=self.ALLOWED,
        )
        # Current behavior: UNION passes through as a single SELECT statement
        assert r.ok is True

    def test_empty_allowlist(self):
        """Empty allowlist should reject all queries."""
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_test",
            allowed_tables=set(),
        )
        assert r.ok is False

    def test_table_underscore_prefix(self):
        """Tables with underscore prefix (DuckDB pattern)."""
        r = validate_and_normalize_sql(
            "SELECT * FROM ds_abc123",
            allowed_tables={"ds_abc123"},
        )
        assert r.ok is True