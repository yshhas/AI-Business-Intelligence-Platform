"""T-03/T-04 smoke: LLMClient mock call chain + retry policy (no live provider)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.llm import LLMError, chat_completion, extract_sql  # noqa: E402
from agent.llm_client import (  # noqa: E402
    LLMAuthError,
    LLMClient,
    LLMConfigError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
)


def _ok_handler(request: httpx.Request) -> httpx.Response:
    assert str(request.url).endswith("/chat/completions")
    assert request.headers.get("Authorization") == "Bearer test-key"
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": "```sql\nSELECT 1 AS n\n```"}}]},
    )


def _status_handler(code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, text=f"err-{code}")

    return handler


def main() -> None:
    sleeps: list[float] = []

    def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    # --- baseline content path ---
    client = LLMClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="mock-model",
        transport=httpx.MockTransport(_ok_handler),
        max_retries=0,
    )
    text = client.chat(system="sys", user="usr").content
    sql = extract_sql(text)
    assert sql == "SELECT 1 AS n", sql

    text2 = chat_completion(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="mock-model",
        system="sys",
        user="usr",
        transport=httpx.MockTransport(_ok_handler),
        max_retries=0,
    )
    assert extract_sql(text2) == "SELECT 1 AS n"

    try:
        chat_completion(
            api_key="",
            base_url="https://example.test/v1",
            model="m",
            system="s",
            user="u",
        )
        raise AssertionError("expected empty key to raise")
    except LLMConfigError as exc:
        assert str(exc) == "LLM_API_KEY is empty"
        assert isinstance(exc, LLMError)

    for code, exc_type in (
        (401, LLMAuthError),
        (429, LLMRateLimitError),
        (500, LLMServerError),
    ):
        c = LLMClient(
            api_key="k",
            base_url="https://example.test/v1",
            model="m",
            transport=httpx.MockTransport(_status_handler(code)),
            max_retries=0,
        )
        try:
            c.chat(system="s", user="u")
            raise AssertionError(f"expected {code} to raise")
        except exc_type as e:
            assert isinstance(e, LLMError)
            assert e.status_code == code

    bad = LLMClient(
        api_key="k",
        base_url="https://example.test/v1",
        model="m",
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"choices": []})
        ),
        max_retries=2,
    )
    try:
        bad.chat(system="s", user="u")
        raise AssertionError("expected response error")
    except LLMResponseError as exc:
        assert isinstance(exc, LLMError)

    # --- T-04: 500 then success → retry works ---
    calls = {"n": 0}

    def flaky_500_then_ok(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok-after-retry"}}]},
        )

    sleeps.clear()
    recovered = LLMClient(
        api_key="k",
        base_url="https://example.test/v1",
        model="m",
        transport=httpx.MockTransport(flaky_500_then_ok),
        max_retries=2,
        retry_backoff_seconds=0.1,
        sleep_fn=record_sleep,
    ).chat(system="s", user="u")
    assert recovered.content == "ok-after-retry"
    assert recovered.attempts == 2
    assert calls["n"] == 2
    assert len(sleeps) == 1
    assert sleeps[0] > 0
    print("RETRY_500_THEN_OK")

    # --- T-04: 401 must not retry ---
    auth_calls = {"n": 0}

    def always_401(request: httpx.Request) -> httpx.Response:
        auth_calls["n"] += 1
        return httpx.Response(401, text="nope")

    sleeps.clear()
    try:
        LLMClient(
            api_key="k",
            base_url="https://example.test/v1",
            model="m",
            transport=httpx.MockTransport(always_401),
            max_retries=3,
            sleep_fn=record_sleep,
        ).chat(system="s", user="u")
        raise AssertionError("expected 401")
    except LLMAuthError:
        pass
    assert auth_calls["n"] == 1
    assert sleeps == []
    print("NO_RETRY_ON_401")

    # --- T-04: continuous 429 → final type preserved ---
    rate_calls = {"n": 0}

    def always_429(request: httpx.Request) -> httpx.Response:
        rate_calls["n"] += 1
        return httpx.Response(429, text="slow down")

    sleeps.clear()
    try:
        LLMClient(
            api_key="k",
            base_url="https://example.test/v1",
            model="m",
            transport=httpx.MockTransport(always_429),
            max_retries=2,
            retry_backoff_seconds=0.05,
            sleep_fn=record_sleep,
        ).chat(system="s", user="u")
        raise AssertionError("expected 429")
    except LLMRateLimitError as exc:
        assert exc.status_code == 429
        assert isinstance(exc, LLMError)
    assert rate_calls["n"] == 3  # 1 initial + 2 retries
    assert len(sleeps) == 2
    print("RETRY_EXHAUST_PRESERVES_RATE_LIMIT")

    # --- T-05: JSON Mode payload + SqlDraft parse ---
    import json as _json

    from agent.schemas_llm import SqlDraft, parse_sql_draft

    assert SqlDraft.model_validate({"sql": "SELECT 1"}).sql == "SELECT 1"
    assert parse_sql_draft('{"sql":"SELECT region, SUM(amount) FROM t GROUP BY 1"}') == (
        "SELECT region, SUM(amount) FROM t GROUP BY 1"
    )
    assert parse_sql_draft("```sql\nSELECT 2\n```") == "SELECT 2"  # legacy fallback

    try:
        parse_sql_draft('{"sql":""}')
        raise AssertionError("empty sql should fail")
    except LLMResponseError:
        pass

    try:
        parse_sql_draft('{"nope":1}')
        raise AssertionError("missing sql key should fail")
    except LLMResponseError:
        pass

    json_calls = {"n": 0}

    def json_mode_handler(request: httpx.Request) -> httpx.Response:
        json_calls["n"] += 1
        body = _json.loads(request.content.decode("utf-8"))
        assert body.get("response_format") == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": _json.dumps(
                                {"sql": 'SELECT "region" AS dim FROM "t"'}
                            )
                        }
                    }
                ]
            },
        )

    content = chat_completion(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="mock-model",
        system="Return JSON with key sql",
        user="q",
        response_format={"type": "json_object"},
        transport=httpx.MockTransport(json_mode_handler),
        max_retries=0,
    )
    assert parse_sql_draft(content) == 'SELECT "region" AS dim FROM "t"'
    assert json_calls["n"] == 1
    print("SQL_JSON_MODE_OK")

    # --- T-07: usage metadata ---
    def usage_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 3,
                    "total_tokens": 14,
                },
            },
        )

    usage_result = LLMClient(
        api_key="k",
        base_url="https://example.test/v1",
        model="deepseek-chat",
        transport=httpx.MockTransport(usage_handler),
        max_retries=0,
    ).chat(system="s", user="u")
    assert usage_result.content == "hello"
    assert usage_result.usage == {
        "prompt_tokens": 11,
        "completion_tokens": 3,
        "total_tokens": 14,
    }
    step_llm = usage_result.as_step_llm()
    assert step_llm["model"] == "deepseek-chat"
    assert step_llm["status"] == "ok"
    assert step_llm["usage"]["total_tokens"] == 14
    assert "latency_ms" in step_llm and step_llm["attempts"] == 1

    # Heuristic generate_sql path records skipped llm meta
    from uuid import uuid4

    from agent.nodes.pipeline import generate_sql
    from agent.state import AnalysisContext

    steps: list = []

    def sink(step):
        steps.append(step)

    ctx = AnalysisContext(
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        question="preview",
        duckdb_table="t",
        schema=[{"name": "a", "type": "INTEGER"}],
        default_limit=10,
        max_retries=0,
        execute_select=lambda sql, limit: {"columns": ["a"], "rows": [], "row_count": 0},
        llm_api_key="",
        allow_heuristic_sql=True,
    )
    generate_sql({}, ctx=ctx, sink=sink)
    assert steps and steps[0].node_name == "generate_sql"
    assert steps[0].output_json is not None
    assert steps[0].output_json.get("llm", {}).get("mode") == "heuristic"
    print("LLM_USAGE_TRACE_OK")

    print("LLM_CLIENT_SMOKE_OK")
    print("content->extract_sql:", sql)


if __name__ == "__main__":
    main()
