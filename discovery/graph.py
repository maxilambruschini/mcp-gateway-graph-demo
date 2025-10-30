"""Discovery Graph builder.

This module builds the Discovery Graph workflow that:
- Classifies input (file vs URL)
- Routes conditionally to parse_files OR discover_from_web
- Extracts endpoints using regex + LLM
- Normalizes and deduplicates results
- Creates a catalog grouped by resource

The graph uses conditional edges to route based on input_type,
ensuring only the relevant branch (file or URL) executes.
"""

from langgraph.graph import END, StateGraph

from discovery.nodes import (
    classify_input_node,
    discover_from_web_node,
    endpoint_extractor_node,
    normalize_and_dedup_node,
    parse_files_node,
    summarize_for_ui_node,
)
from models import DiscoveryState


def route_by_input_type(state: DiscoveryState) -> str:
    """Route to either parse_files or discover_from_web based on input_type.

    Args:
        state: Current discovery state with classified input_type

    Returns:
        Name of the next node to execute ("file" or "url")
    """
    input_type = state["discovery"].get("input_type", "file")
    return input_type


def build_discovery_graph():
    """Build and return the Discovery Graph.

    Returns:
        StateGraph workflow for discovery
    """
    workflow = StateGraph(DiscoveryState)

    # Add nodes
    workflow.add_node("classify_input", classify_input_node)
    workflow.add_node("parse_files", parse_files_node)
    workflow.add_node("discover_from_web", discover_from_web_node)
    workflow.add_node("endpoint_extractor", endpoint_extractor_node)
    workflow.add_node("normalize_and_dedup", normalize_and_dedup_node)
    workflow.add_node("summarize_for_ui", summarize_for_ui_node)

    # Add edges
    workflow.set_entry_point("classify_input")

    # Conditional routing from classify_input based on input_type
    workflow.add_conditional_edges(
        source="classify_input",
        path=route_by_input_type,
        path_map={"file": "parse_files", "url": "discover_from_web"},
    )

    # Both branches converge at endpoint_extractor
    workflow.add_edge("parse_files", "endpoint_extractor")
    workflow.add_edge("discover_from_web", "endpoint_extractor")

    # Continue linear flow after convergence
    workflow.add_edge("endpoint_extractor", "normalize_and_dedup")
    workflow.add_edge("normalize_and_dedup", "summarize_for_ui")
    workflow.add_edge("summarize_for_ui", END)

    return workflow
