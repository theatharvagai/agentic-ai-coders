"""
haco/graph.py
Constructs and compiles the LangGraph StateGraph for HACO.

Graph topology (updated with accept_or_reject gate)
------------------------------------------------------
bug_agent → hw_analyst_agent → optimizer_agent → accept_or_reject → test_agent
                                      ↑                                  ↓ (retry if fail & retries<2)
                                      └──────────────────────────────────┘
test_agent → convergence_check → (loop) → hw_analyst_agent
                               → (done) → END
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from haco.state import HACOState
from haco.agents import (
    bug_agent,
    llvm_analysis_agent,
    hw_analyst_agent,
    optimizer_agent,
    accept_or_reject,
    test_agent,
)


# ── Routing functions ──────────────────────────────────────────────────────────

def _route_after_test(state: HACOState) -> str:
    """
    After the test agent:
    - If validation failed and retries remain → go back to test generation
    - If validation passed → run convergence check
    """
    if not state.get("validation_passed", True):
        return "test_agent"
    return "convergence_check"


def convergence_check(state: HACOState) -> HACOState:
    """Increments iteration counter. Pass-through node."""
    return {**state, "iteration": state["iteration"] + 1}


def _route_after_convergence(state: HACOState) -> str:
    """
    Loop condition:
      continue if iteration < max_iterations AND latest improvement seen
      else finish
    """
    iteration = state["iteration"]
    max_iter = state.get("max_iterations", 3)

    if iteration >= max_iter:
        return "__end__"

    # With real QEMU metrics, we always try to optimize further if iterations remain
    return "llvm_analysis_agent"


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    builder = StateGraph(HACOState)

    # Add nodes
    builder.add_node("bug_agent",           bug_agent)
    builder.add_node("llvm_analysis_agent", llvm_analysis_agent)
    builder.add_node("hw_analyst_agent",    hw_analyst_agent)
    builder.add_node("optimizer_agent",     optimizer_agent)
    builder.add_node("accept_or_reject",    accept_or_reject)
    builder.add_node("test_agent",          test_agent)
    builder.add_node("convergence_check",   convergence_check)

    # Entry point
    builder.set_entry_point("bug_agent")

    # Linear edges
    builder.add_edge("bug_agent",           "llvm_analysis_agent")
    builder.add_edge("llvm_analysis_agent", "hw_analyst_agent")
    builder.add_edge("hw_analyst_agent",    "optimizer_agent")
    builder.add_edge("optimizer_agent",     "accept_or_reject")
    builder.add_edge("accept_or_reject",    "test_agent")

    # Conditional: test result → retry test agent or convergence check
    builder.add_conditional_edges(
        "test_agent",
        _route_after_test,
        {
            "test_agent":        "test_agent",
            "convergence_check": "convergence_check",
        },
    )

    # Conditional: convergence → loop or finish
    builder.add_conditional_edges(
        "convergence_check",
        _route_after_convergence,
        {
            "llvm_analysis_agent": "llvm_analysis_agent",
            "__end__":             END,
        },
    )

    return builder.compile()


# Compiled graph singleton
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
