"""Compile LangGraph for Text-to-SQL + charts + short report (Phase 5)."""

from __future__ import annotations

from functools import partial
from typing import Callable

from langgraph.graph import END, StateGraph

from agent.nodes import pipeline as nodes
from agent.state import AnalysisContext, AnalysisState, StepRecord


def build_graph(ctx: AnalysisContext, sink: Callable[[StepRecord], None] | None = None):
    g: StateGraph = StateGraph(AnalysisState)

    g.add_node("load_context", partial(nodes.load_context, ctx=ctx, sink=sink))
    g.add_node("link_schema", partial(nodes.link_schema, ctx=ctx, sink=sink))
    g.add_node("generate_sql", partial(nodes.generate_sql, ctx=ctx, sink=sink))
    g.add_node("validate_sql", partial(nodes.validate_sql, ctx=ctx, sink=sink))
    g.add_node("execute_sql", partial(nodes.execute_sql, ctx=ctx, sink=sink))
    g.add_node("hitl_plan_done", partial(nodes.hitl_plan_done, ctx=ctx, sink=sink))
    g.add_node("summarize", partial(nodes.summarize, ctx=ctx, sink=sink))
    g.add_node("build_charts", partial(nodes.build_charts, ctx=ctx, sink=sink))
    g.add_node("write_report", partial(nodes.write_report, ctx=ctx, sink=sink))
    g.add_node("fail", _fail_node)

    g.set_entry_point("load_context")
    g.add_edge("load_context", "link_schema")
    g.add_conditional_edges(
        "link_schema",
        nodes.route_after_link,
        {
            "generate_sql": "generate_sql",
            "validate_sql": "validate_sql",  # HITL execute-only skips generate
            "fail": "fail",
        },
    )
    g.add_edge("generate_sql", "validate_sql")
    g.add_conditional_edges(
        "validate_sql",
        nodes.route_after_validate,
        {
            "execute_sql": "execute_sql",
            "hitl_plan_done": "hitl_plan_done",
            "generate_sql": "generate_sql",
            "fail": "fail",
        },
    )
    g.add_edge("hitl_plan_done", END)
    g.add_conditional_edges(
        "execute_sql",
        nodes.route_after_execute,
        {
            "summarize": "summarize",
            "generate_sql": "generate_sql",
            "fail": "fail",
        },
    )
    g.add_edge("summarize", "build_charts")
    g.add_edge("build_charts", "write_report")
    g.add_edge("write_report", END)
    g.add_edge("fail", END)
    return g.compile()


def _fail_node(state: AnalysisState) -> AnalysisState:
    err = state.get("gate_error") or state.get("error") or "Analysis failed"
    return {**state, "status": "failed", "error": err, "summary": ""}
