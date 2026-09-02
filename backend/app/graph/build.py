"""Graph wiring.

The graph is pure: it takes a parsed score's features and returns a plan.
Supabase writes stay in the processor so the whole pipeline is testable
without a database.

No checkpointer. Resume was never wired up — thread_id is the piece_id and
the frontend mints a fresh UUID per upload, so no run ever loaded a prior
checkpoint. It saved nothing and destroyed two paid runs (a pgbouncer param
psycopg rejects, then a music21 Fraction msgpack couldn't pack). Recovery is
a retry from scratch, which is a few minutes of Audiveris and one fan-out.
"""

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import PlanState


def build():
    graph = StateGraph(PlanState)

    graph.add_node("segment", nodes.segment)
    graph.add_node("analyze_section", nodes.analyze_section)
    graph.add_node("validate_plan", nodes.validate_plan)
    graph.add_node("critique", nodes.critique)
    graph.add_node("apply_feedback", nodes.apply_feedback)

    graph.add_edge(START, "segment")

    # Fan-out: one Send per section, run in parallel, merged by the state
    # reducer. Reached from both the first pass and each revision pass.
    graph.add_conditional_edges("segment", nodes.fan_out, ["analyze_section"])
    graph.add_edge("analyze_section", "validate_plan")
    graph.add_edge("validate_plan", "critique")
    graph.add_conditional_edges(
        "critique",
        nodes.route_after_critique,
        {"revise": "apply_feedback", "persist": END},
    )
    graph.add_conditional_edges("apply_feedback", nodes.fan_out, ["analyze_section"])

    return graph.compile()
