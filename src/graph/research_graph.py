"""
LangGraph araştırma pipeline'ı:
  START → planner → literature → embed → pdf_fetcher → synthesis → END
"""

from langgraph.graph import StateGraph, END

from src.graph.state import ResearchState
from src.agents.planner import planner_node
from src.agents.literature import literature_node
from src.agents.embed import embed_node
from src.agents.pdf_fetcher import pdf_fetcher_node
from src.agents.synthesis import synthesis_node


def build_graph():
    """Araştırma state machine'ini derle ve döndür."""
    graph = StateGraph(ResearchState)

    graph.add_node("planner", planner_node)
    graph.add_node("literature", literature_node)
    graph.add_node("embed", embed_node)
    graph.add_node("pdf_fetcher", pdf_fetcher_node)
    graph.add_node("synthesis", synthesis_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "literature")
    graph.add_edge("literature", "embed")
    graph.add_edge("embed", "pdf_fetcher")
    graph.add_edge("pdf_fetcher", "synthesis")
    graph.add_edge("synthesis", END)

    return graph.compile()
