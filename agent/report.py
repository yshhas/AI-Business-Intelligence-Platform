"""Short analysis report builder (markdown + sections)."""

from __future__ import annotations

from typing import Any, Callable

from agent.contracts import ReportDoc


def build_report(
    *,
    question: str,
    summary: str,
    sql: str,
    preview: dict[str, Any],
    charts: list[dict[str, Any]],
    limitations: list[str],
    llm_fn: Callable[..., str] | None = None,
) -> ReportDoc:
    rows = preview.get("rows") or []
    cols = preview.get("columns") or []
    n = len(rows) if isinstance(rows, list) else 0
    chart_titles = [
        str(c.get("title") or c.get("id") or "chart")
        for c in charts
        if isinstance(c, dict)
    ]

    if llm_fn is not None:
        try:
            md = llm_fn(
                question=question,
                summary=summary,
                sql=sql,
                columns=cols,
                row_count=n,
                chart_titles=chart_titles,
                limitations=limitations,
            )
            if md and md.strip():
                return {
                    "title": "分析简报",
                    "markdown": md.strip(),
                    "sections": _sections_from_markdown_fallback(
                        question, summary, sql, n, chart_titles, limitations
                    ),
                }
        except Exception:  # noqa: BLE001
            pass

    return _template_report(
        question=question,
        summary=summary,
        sql=sql,
        row_count=n,
        columns=[str(c) for c in cols] if isinstance(cols, list) else [],
        chart_titles=chart_titles,
        limitations=limitations,
    )


def _template_report(
    *,
    question: str,
    summary: str,
    sql: str,
    row_count: int,
    columns: list[str],
    chart_titles: list[str],
    limitations: list[str],
) -> ReportDoc:
    sections = _sections_from_markdown_fallback(
        question, summary, sql, row_count, chart_titles, limitations
    )
    md_parts = [f"## {s['heading']}\n\n{s['body']}" for s in sections]
    return {
        "title": "分析简报",
        "markdown": "\n\n".join(md_parts),
        "sections": sections,
    }


def _sections_from_markdown_fallback(
    question: str,
    summary: str,
    sql: str,
    row_count: int,
    chart_titles: list[str],
    limitations: list[str],
) -> list[dict[str, str]]:
    charts_line = (
        "、".join(chart_titles) if chart_titles else "（本次未生成图表）"
    )
    lim = "\n".join(f"- {x}" for x in limitations) if limitations else "- 无额外局限说明"
    return [
        {
            "heading": "结论",
            "body": summary or f"针对问题「{question[:120]}」已完成查询，返回 {row_count} 行。",
        },
        {
            "heading": "关键发现",
            "body": (
                f"问题：{question[:200]}\n\n"
                f"结果行数：{row_count}\n\n"
                f"图表：{charts_line}\n\n"
                f"SQL：\n```sql\n{(sql or '')[:800]}\n```"
            ),
        },
        {
            "heading": "局限与下一步",
            "body": lim,
        },
    ]
