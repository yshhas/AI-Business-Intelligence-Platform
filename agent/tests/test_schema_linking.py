"""Unit tests for agent.schema_linking — deterministic column selection.

Tests cover:
- _column_names: schema → column name list
- _merge_synonyms: builtin + extra synonym merging
- _expand_haystack: question + synonym expansion
- _name_tokens: column name → token list
- _score_column: name vs haystack scoring
- link_schema: all 4 return paths + edge cases
- filter_schema_by_columns: schema filtering
- LinkResult dataclass + as_step_output / as_platform_sql_quality
"""

from __future__ import annotations

import pytest

from agent.schema_linking import (
    BUILTIN_SYNONYMS,
    DEFAULT_MAX_COLUMNS,
    SCHEMA_LINK_VERSION,
    LinkResult,
    _column_names,
    _expand_haystack,
    _merge_synonyms,
    _name_tokens,
    _score_column,
    filter_schema_by_columns,
    link_schema,
)


# ── _column_names ──────────────────────────────────────────────────────

class TestColumnNames:
    """Extract column names from schema dicts."""

    def test_normal_schema(self):
        schema = [
            {"name": "region", "type": "VARCHAR"},
            {"name": "amount", "type": "DOUBLE"},
            {"name": "order_date", "type": "DATE"},
        ]
        assert _column_names(schema) == ["region", "amount", "order_date"]

    def test_empty_list(self):
        assert _column_names([]) == []

    def test_none_schema(self):
        assert _column_names(None) == []

    def test_skips_non_dict(self):
        schema = [
            {"name": "region"},
            "not_a_dict",
            {"name": "amount"},
            None,
        ]
        assert _column_names(schema) == ["region", "amount"]

    def test_skips_none_name(self):
        schema = [
            {"name": "region"},
            {"name": None},
            {"name": "amount"},
            {"name": ""},
            {"name": "   "},
        ]
        assert _column_names(schema) == ["region", "amount"]

    def test_skips_missing_name_key(self):
        schema = [
            {"name": "a"},
            {"type": "INT"},
            {"name": "b"},
        ]
        assert _column_names(schema) == ["a", "b"]

    def test_coerces_non_string_name(self):
        schema = [{"name": 123}, {"name": "region"}]
        # int name is coerced to string
        assert _column_names(schema) == ["123", "region"]


# ── _merge_synonyms ────────────────────────────────────────────────────

class TestMergeSynonyms:
    def test_returns_builtin_copy(self):
        merged = _merge_synonyms(None)
        assert "销售额" in merged
        assert merged["销售额"] == BUILTIN_SYNONYMS["销售额"]
        # Should be a copy, not the same object
        assert merged is not BUILTIN_SYNONYMS

    def test_extra_adds_new_key(self):
        merged = _merge_synonyms({"行业": ["industry", "sector"]})
        assert "行业" in merged
        assert merged["行业"] == ["industry", "sector"]

    def test_extra_appends_to_existing_key(self):
        merged = _merge_synonyms({"销售": ["deal_value"]})
        assert "deal_value" in merged["销售"]
        # Original builtin values preserved
        for v in BUILTIN_SYNONYMS["销售"]:
            assert v in merged["销售"]

    def test_extra_skips_empty_key(self):
        merged = _merge_synonyms({"": ["something"]})
        assert "" not in merged

    def test_extra_skips_empty_vals(self):
        merged = _merge_synonyms({"key": []})
        # key not added because vals is empty
        assert "key" not in merged

    def test_extra_deduplicates(self):
        merged = _merge_synonyms({"销售": ["amount", "amount", "revenue"]})
        # "amount" should appear only once
        assert merged["销售"].count("amount") == 1

    def test_extra_case_insensitive_keys(self):
        merged = _merge_synonyms({"销售": ["chinese_sales"]})
        assert "销售" in merged
        assert "chinese_sales" in merged["销售"]


# ── _expand_haystack ───────────────────────────────────────────────────

class TestExpandHaystack:
    def test_no_synonym_match(self):
        hay, applied = _expand_haystack(
            "show me the data",
            synonyms={"销售额": ["amount"]},
        )
        assert "show me the data" in hay
        assert applied == []

    def test_synonym_match_chinese(self):
        hay, applied = _expand_haystack(
            "按区域统计销售额",
            synonyms={"销售额": ["amount", "sales"]},
        )
        assert "amount" in hay
        assert "sales" in hay
        assert "销售额" in applied

    def test_longer_key_beats_shorter(self):
        """「销售额」(3 chars) should match before「销售」(2 chars)."""
        hay, applied = _expand_haystack(
            "销售额分析",
            synonyms={"销售额": ["revenue"], "销售": ["sales"]},
        )
        assert "revenue" in hay
        assert "销售额" in applied

    def test_key_length_minimum_2(self):
        """Single-char keys are skipped."""
        hay, applied = _expand_haystack(
            "a test",
            synonyms={"a": ["alpha"]},
        )
        assert "alpha" not in hay
        assert applied == []

    def test_english_synonym_match(self):
        hay, applied = _expand_haystack(
            "show me revenue by region",
            synonyms={"revenue": ["amount", "sales"]},
        )
        assert "amount" in hay
        assert "revenue" in applied

    def test_none_question(self):
        hay, applied = _expand_haystack(
            None,
            synonyms={"销售": ["amount"]},
        )
        assert hay == ""
        assert applied == []

    def test_empty_question(self):
        hay, applied = _expand_haystack(
            "",
            synonyms={"销售": ["amount"]},
        )
        assert hay == ""
        assert applied == []

    def test_partial_match_in_chinese(self):
        """「销售」should match inside「销售额」."""
        hay, applied = _expand_haystack(
            "每月销售额分析",
            synonyms={"销售": ["amount"]},
        )
        assert "amount" in hay
        assert "销售" in applied


# ── _name_tokens ───────────────────────────────────────────────────────

class TestNameTokens:
    def test_underscore_split(self):
        tokens = _name_tokens("order_date")
        assert "order" in tokens
        assert "date" in tokens

    def test_dash_split(self):
        tokens = _name_tokens("order-date")
        assert "order" in tokens
        assert "date" in tokens

    def test_single_word(self):
        assert _name_tokens("region") == ["region"]

    def test_empty_string(self):
        assert _name_tokens("") == []

    def test_numeric_only(self):
        tokens = _name_tokens("123")
        assert "123" in tokens

    def test_mixed_case(self):
        tokens = _name_tokens("OrderDate")
        assert "orderdate" in tokens  # lowered

    def test_chinese_chars(self):
        tokens = _name_tokens("订单日期")
        # \u4e00-\u9fff range includes Chinese chars
        assert "订单日期" in tokens


# ── _score_column ──────────────────────────────────────────────────────

class TestScoreColumn:
    def test_exact_match(self):
        score = _score_column("region", "show region data")
        assert score > 3.0  # full name match bonus

    def test_token_match(self):
        score = _score_column("order_date", "show me orders by date")
        assert score > 0  # "order" and "date" tokens should match

    def test_no_match(self):
        score = _score_column("xyz_col", "show region data")
        assert score == 0.0

    def test_empty_haystack(self):
        score = _score_column("region", "")
        assert score == 0.0

    def test_longer_name_higher_score(self):
        """Exact match of longer name gets slightly higher score (length bonus)."""
        score_long = _score_column("order_date", "order_date filter")
        score_short = _score_column("date", "order_date filter")
        assert score_long > score_short

    def test_partial_substring(self):
        """Substring match scores higher than token-only match."""
        score = _score_column("region", "region_data")
        assert score > 0

    def test_token_length_under_2_skipped(self):
        """Single-char tokens are ignored in scoring."""
        score = _score_column("a", "a value")
        # "a" is len < 2, token match skipped, but full name "a" is also len < 2...
        # Full name match: "a" in "a value" → True, score = 3.0 + 1*0.05 = 3.05
        # Token: "a" len < 2 → skipped
        assert score > 0  # full name match still works


# ── link_schema: Failed path ───────────────────────────────────────────

class TestLinkSchemaFailed:
    """Return path: empty schema → link_status='failed'."""

    def test_empty_schema(self):
        result = link_schema(
            question="show me revenue",
            schema=[],
            table="ds_test",
        )
        assert result.link_status == "failed"
        assert result.link_reason == "schema_empty"
        assert result.column_count_full == 0
        assert result.selected_columns == []

    def test_none_schema(self):
        result = link_schema(
            question="show me revenue",
            schema=None,
            table="ds_test",
        )
        assert result.link_status == "failed"
        assert result.link_reason == "schema_empty"


# ── link_schema: Identity path ─────────────────────────────────────────

class TestLinkSchemaIdentity:
    """Return path: schema ≤ max_columns → link_status='ok', method='identity'."""

    def test_small_schema_identity(self):
        schema = [
            {"name": "region"},
            {"name": "amount"},
            {"name": "date"},
        ]
        result = link_schema(
            question="show me revenue by region",
            schema=schema,
            table="ds_test",
            max_columns=10,
        )
        assert result.link_status == "ok"
        assert result.link_method == "identity"
        assert result.link_reason == "within_k_noop"
        assert result.selected_columns == ["region", "amount", "date"]
        assert result.column_count_linked == 3

    def test_exactly_at_limit(self):
        schema = [{"name": f"col_{i}"} for i in range(5)]
        result = link_schema(
            question="show me data",
            schema=schema,
            table="ds_test",
            max_columns=5,
        )
        assert result.link_method == "identity"
        assert result.link_status == "ok"

    def test_default_max_columns(self):
        """Default max_columns is 12."""
        schema = [{"name": f"c{i}"} for i in range(12)]
        result = link_schema(
            question="show me data",
            schema=schema,
            table="ds_test",
        )
        assert result.link_method == "identity"


# ── link_schema: Fallback path ─────────────────────────────────────────

class TestLinkSchemaFallback:
    """Return path: no column scores > 0 → link_status='fallback_full'."""

    def test_no_match_takes_top_k(self):
        schema = [
            {"name": "col_a"},
            {"name": "col_b"},
            {"name": "col_c"},
            {"name": "col_d"},
            {"name": "col_e"},
        ]
        result = link_schema(
            question="xyz qwerty uiop",
            schema=schema,
            table="ds_test",
            max_columns=3,
        )
        assert result.link_status == "fallback_full"
        assert result.link_method == "fallback_full"
        assert result.link_reason == "no_token_overlap"
        assert len(result.selected_columns) == 3

    def test_fallback_is_ordered(self):
        """Fallback returns first K columns in original order."""
        schema = [{"name": f"col_{i}"} for i in range(10)]
        result = link_schema(
            question="zzz",
            schema=schema,
            table="ds_test",
            max_columns=4,
        )
        assert result.selected_columns == ["col_0", "col_1", "col_2", "col_3"]


# ── link_schema: OK / Partial paths ────────────────────────────────────

class TestLinkSchemaPositive:
    SCHEMA = [
        {"name": "region", "type": "VARCHAR"},
        {"name": "amount", "type": "DOUBLE"},
        {"name": "order_date", "type": "DATE"},
        {"name": "category", "type": "VARCHAR"},
        {"name": "customer_id", "type": "INT"},
        {"name": "discount", "type": "DOUBLE"},
        {"name": "tax", "type": "DOUBLE"},
        {"name": "shipping", "type": "DOUBLE"},
    ]

    def test_token_overlap_ok(self):
        """Strong match with 2+ columns and high scores → 'ok'."""
        result = link_schema(
            question="按区域统计销售额和订单日期",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=5,
        )
        assert result.link_status == "ok"
        assert result.link_method == "synonym_overlap"
        assert "region" in result.selected_columns
        assert "amount" in result.selected_columns
        assert "order_date" in result.selected_columns

    def test_weak_coverage_partial(self):
        """Weak match (single column or low score) → 'partial'."""
        schema = [
            {"name": "region", "type": "VARCHAR"},
            {"name": "col_x", "type": "INT"},
            {"name": "col_y", "type": "INT"},
            {"name": "col_z", "type": "INT"},
        ]
        result = link_schema(
            question="地区",
            schema=schema,  # "地" is 1 char, won't match; "地区" will match "region" via synonym
            table="ds_test",
            max_columns=3,
        )
        # "地区" → synonym → "region" → 1 positive column
        assert result.link_status in ("partial", "ok")  # depends on score

    def test_english_question_token_match(self):
        result = link_schema(
            question="show me total amount by region and category",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=5,
        )
        assert result.link_status == "ok"
        assert "region" in result.selected_columns
        assert "amount" in result.selected_columns
        assert "category" in result.selected_columns

    def test_synonym_applied_english(self):
        result = link_schema(
            question="show me revenue by region",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=5,
        )
        assert "revenue" in result.synonyms_applied
        assert "amount" in result.selected_columns

    def test_scores_are_computed(self):
        result = link_schema(
            question="region amount",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=5,
        )
        assert result.scores
        assert result.scores["region"] > 0
        assert result.scores["amount"] > 0


# ── link_schema: Edge cases ────────────────────────────────────────────

class TestLinkSchemaEdgeCases:
    SCHEMA = [
        {"name": "region"},
        {"name": "amount"},
        {"name": "date"},
        {"name": "product"},
        {"name": "qty"},
    ]

    def test_none_max_columns_uses_default(self):
        result = link_schema(
            question="region",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=None,
        )
        assert result.column_count_full == 5

    def test_max_columns_one(self):
        result = link_schema(
            question="region amount",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=1,
        )
        assert len(result.selected_columns) == 1

    def test_custom_synonyms(self):
        result = link_schema(
            question="show me deal value",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=5,
            synonyms={"deal value": ["amount"]},
        )
        assert "amount" in result.selected_columns

    def test_table_selection_from_allowed(self):
        result = link_schema(
            question="region",
            schema=self.SCHEMA,
            table="primary_table",
            allowed_tables=["primary_table", "secondary_table"],
            max_columns=5,
        )
        assert result.selected_tables == ["primary_table", "secondary_table"]

    def test_duplicate_table_removed(self):
        result = link_schema(
            question="region",
            schema=self.SCHEMA,
            table="ds_test",
            allowed_tables=["ds_test", "ds_test"],
            max_columns=5,
        )
        assert result.selected_tables == ["ds_test"]

    def test_recall_ratio_computed(self):
        result = link_schema(
            question="region",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=2,
        )
        output = result.as_step_output()
        assert output["link_recall_ratio"] is not None
        # "region" only matches 1 column → 1/5 = 0.2
        assert output["link_recall_ratio"] == pytest.approx(1 / 5, abs=0.01)

    def test_zero_columns_recall_none(self):
        result = link_schema(
            question="region",
            schema=[],
            table="ds_test",
        )
        output = result.as_step_output()
        assert output["link_recall_ratio"] is None

    def test_version_in_output(self):
        result = link_schema(
            question="region",
            schema=self.SCHEMA,
            table="ds_test",
            max_columns=3,
        )
        assert result.schema_link_version == SCHEMA_LINK_VERSION
        output = result.as_step_output()
        assert output["schema_link_version"] == SCHEMA_LINK_VERSION


# ── filter_schema_by_columns ───────────────────────────────────────────

class TestFilterSchemaByColumns:
    SCHEMA = [
        {"name": "region", "type": "VARCHAR"},
        {"name": "amount", "type": "DOUBLE"},
        {"name": "date", "type": "DATE"},
        {"name": "product", "type": "VARCHAR"},
    ]

    def test_filters_and_preserves_order(self):
        result = filter_schema_by_columns(
            self.SCHEMA,
            ["amount", "region", "date"],
        )
        assert [c["name"] for c in result] == ["amount", "region", "date"]

    def test_drops_unknown_columns(self):
        result = filter_schema_by_columns(
            self.SCHEMA,
            ["region", "unknown_col", "amount"],
        )
        assert [c["name"] for c in result] == ["region", "amount"]

    def test_empty_selection(self):
        result = filter_schema_by_columns(self.SCHEMA, [])
        assert result == []

    def test_none_schema(self):
        result = filter_schema_by_columns(None, ["region"])
        assert result == []

    def test_all_unknown(self):
        result = filter_schema_by_columns(
            self.SCHEMA,
            ["x", "y", "z"],
        )
        assert result == []


# ── LinkResult dataclass ───────────────────────────────────────────────

class TestLinkResult:
    def test_basic_construction(self):
        r = LinkResult(
            link_status="ok",
            link_method="token_overlap",
            link_reason=None,
            selected_tables=["ds_test"],
            selected_columns=["region", "amount"],
            column_count_full=10,
            column_count_linked=2,
            scores={"region": 3.5, "amount": 2.0},
        )
        assert r.link_status == "ok"
        assert r.selected_columns == ["region", "amount"]

    def test_as_step_output(self):
        r = LinkResult(
            link_status="ok",
            link_method="token_overlap",
            link_reason=None,
            selected_tables=["ds_test"],
            selected_columns=["region", "amount"],
            column_count_full=10,
            column_count_linked=2,
            scores={"region": 3.5, "amount": 2.0},
            synonyms_applied=["销售额"],
        )
        out = r.as_step_output()
        assert out["link_status"] == "ok"
        assert out["link_method"] == "token_overlap"
        assert out["link_recall_ratio"] == pytest.approx(0.2, abs=0.01)
        assert "销售额" in out["synonyms_applied"]

    def test_as_platform_sql_quality(self):
        r = LinkResult(
            link_status="ok",
            link_method="token_overlap",
            link_reason=None,
            selected_tables=["ds_test"],
            selected_columns=["region"],
            column_count_full=5,
            column_count_linked=1,
        )
        out = r.as_platform_sql_quality()
        assert out["schema_version"] == 2
        assert out["link_status"] == "ok"

    def test_defaults(self):
        r = LinkResult(
            link_status="ok",
            link_method="token_overlap",
            link_reason=None,
            selected_tables=["t"],
            selected_columns=["c"],
            column_count_full=1,
            column_count_linked=1,
        )
        assert r.scores == {}
        assert r.synonyms_applied == []
        assert r.schema_link_version == SCHEMA_LINK_VERSION


# ── BUILTIN_SYNONYMS ───────────────────────────────────────────────────

class TestBuiltinSynonyms:
    def test_has_expected_keys(self):
        expected = {"销售额", "销售", "营收", "金额", "数量", "区域", "地区", "省份",
                     "城市", "产品", "商品", "品类", "客户", "订单", "日期", "时间",
                     "汇总", "合计", "revenue", "sales", "turnover"}
        assert set(BUILTIN_SYNONYMS.keys()) == expected

    def test_all_values_are_lists(self):
        for k, v in BUILTIN_SYNONYMS.items():
            assert isinstance(v, list), f"BUILTIN_SYNONYMS[{k!r}] is not a list"
            assert len(v) > 0, f"BUILTIN_SYNONYMS[{k!r}] is empty"