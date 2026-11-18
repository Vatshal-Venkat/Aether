"""Wiring the steps together with LangGraph.

Plain English: this is the flowchart. Each box is one of our small step functions; the
arrows say what comes next; the diamonds (conditional edges) decide between paths.

    contextualize (follow-up -> full question) ► route ─sql─► plan ─► inject_schema ► generate_sql ► validate ► row_filter ► execute ► next_step ─┐
      │                     ▲                ▲             │           │           │      │        │
      │                     │                └── retry ◄───┴───────────┴───────────┘      │        │
      │                     │                    (max 3 tries per step, then ► fail ► END) │        │
      │                     └────────────── another step (two-database plan) ◄─────────────┘        │
      │                                                                                             ▼
      │                                     merge ─(hybrid)─► retrieve ─┐
      │                                       └──────────────────────────┴─► synthesize ► verify_numbers ► END
      ├─rag─────► retrieve (FDA drug labels) ► synthesize ► verify_numbers ► END
      ├─hybrid──► same path as sql (clinical_db), then retrieve for the medicines in the rows
      ├─clarify─► clarify (ask back, with options) ► END
      ├─refuse──► refuse ► END
      └─out_of_scope──► out_of_scope ► END
"""

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.graph.deps import Deps
from app.graph.edges import after_execute, after_merge, after_next_step, after_row_filter, after_validate
from app.graph.nodes.contextualize import contextualize
from app.graph.nodes.execute import execute
from app.graph.nodes.generate_sql import generate_sql
from app.graph.nodes.inject_schema import inject_schema
from app.graph.nodes.merge import merge, next_step
from app.graph.nodes.plan import plan
from app.graph.nodes.retrieve import retrieve
from app.graph.nodes.route import route
from app.graph.nodes.row_filter import row_filter
from app.graph.nodes.simple_replies import clarify, fail, out_of_scope, refuse
from app.graph.nodes.synthesize import synthesize
from app.graph.nodes.validate import validate
from app.graph.nodes.verify_numbers import verify_numbers
from app.graph.state import ChatState


def build_graph(deps: Deps):
    g = StateGraph(ChatState)
    steps = {
        "contextualize": contextualize, "route": route, "plan": plan, "inject_schema": inject_schema, "generate_sql": generate_sql,
        "validate": validate, "row_filter": row_filter, "execute": execute, "next_step": next_step,
        "merge": merge, "retrieve": retrieve, "synthesize": synthesize, "verify_numbers": verify_numbers,
        "refuse": refuse, "out_of_scope": out_of_scope, "fail": fail, "clarify": clarify,
    }
    for name, fn in steps.items():
        g.add_node(name, partial(fn, deps=deps))

    max_attempts = deps.settings.max_sql_attempts
    g.add_edge(START, "contextualize")  # a follow-up becomes a full question first
    g.add_edge("contextualize", "route")
    g.add_conditional_edges("route", lambda s: s["route"].kind,
                            {"sql": "plan", "hybrid": "plan", "rag": "retrieve",
                             "clarify": "clarify", "refuse": "refuse", "out_of_scope": "out_of_scope"})
    g.add_edge("plan", "inject_schema")
    g.add_edge("inject_schema", "generate_sql")
    g.add_edge("generate_sql", "validate")
    g.add_conditional_edges("validate", partial(after_validate, max_attempts=max_attempts),
                            ["row_filter", "generate_sql", "fail"])
    g.add_conditional_edges("row_filter", partial(after_row_filter, max_attempts=max_attempts),
                            ["execute", "generate_sql", "fail"])
    g.add_conditional_edges("execute", partial(after_execute, max_attempts=max_attempts),
                            ["next_step", "generate_sql", "fail"])
    g.add_conditional_edges("next_step", after_next_step, ["inject_schema", "merge"])
    g.add_conditional_edges("merge", after_merge, ["retrieve", "synthesize"])
    g.add_edge("retrieve", "synthesize")
    g.add_edge("synthesize", "verify_numbers")
    for last in ("verify_numbers", "refuse", "out_of_scope", "fail", "clarify"):
        g.add_edge(last, END)
    return g.compile()
