"""Wiring the steps together with LangGraph.

Plain English: this is the flowchart. Each box is one of our small step functions; the
arrows say what comes next; the diamonds (conditional edges) decide between paths.

    route ──sql──► inject_schema ► generate_sql ► validate ─ok─► execute ─ok─► synthesize ► verify_numbers ► END
      │                               ▲              │             │
      ├─refuse──► refuse ► END        └── retry ◄────┴─────────────┘  (max 3 tries, then ► fail ► END)
      └─out_of_scope──► out_of_scope ► END
"""

from functools import partial

from langgraph.graph import END, START, StateGraph

from app.graph.deps import Deps
from app.graph.edges import after_execute, after_validate
from app.graph.nodes.execute import execute
from app.graph.nodes.generate_sql import generate_sql
from app.graph.nodes.inject_schema import inject_schema
from app.graph.nodes.route import route
from app.graph.nodes.simple_replies import fail, out_of_scope, refuse
from app.graph.nodes.synthesize import synthesize
from app.graph.nodes.validate import validate
from app.graph.nodes.verify_numbers import verify_numbers
from app.graph.state import ChatState


def build_graph(deps: Deps):
    g = StateGraph(ChatState)
    steps = {
        "route": route, "inject_schema": inject_schema, "generate_sql": generate_sql, "validate": validate,
        "execute": execute, "synthesize": synthesize, "verify_numbers": verify_numbers,
        "refuse": refuse, "out_of_scope": out_of_scope, "fail": fail,
    }
    for name, fn in steps.items():
        g.add_node(name, partial(fn, deps=deps))

    max_attempts = deps.settings.max_sql_attempts
    g.add_edge(START, "route")
    g.add_conditional_edges("route", lambda s: s["route"].kind,
                            {"sql": "inject_schema", "refuse": "refuse", "out_of_scope": "out_of_scope"})
    g.add_edge("inject_schema", "generate_sql")
    g.add_edge("generate_sql", "validate")
    g.add_conditional_edges("validate", partial(after_validate, max_attempts=max_attempts),
                            ["execute", "generate_sql", "fail"])
    g.add_conditional_edges("execute", partial(after_execute, max_attempts=max_attempts),
                            ["synthesize", "generate_sql", "fail"])
    g.add_edge("synthesize", "verify_numbers")
    for last in ("verify_numbers", "refuse", "out_of_scope", "fail"):
        g.add_edge(last, END)
    return g.compile()
