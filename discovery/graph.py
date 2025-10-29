"""Discovery Graph builder.

This module builds the Discovery Graph workflow that:
- Classifies input (file vs URL)
- Parses files or discovers from web
- Extracts endpoints using regex + LLM
- Normalizes and deduplicates results
- Creates a catalog grouped by resource
- Interrupts for user selection
"""

from langgraph.graph import END, StateGraph

from discovery.nodes import (classify_input_node, discover_from_web_node,
                             endpoint_extractor_node,
                             interrupt_for_selection_node,
                             normalize_and_dedup_node, parse_files_node,
                             summarize_for_ui_node)
from models import DiscoveryState


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
    workflow.add_node("interrupt_for_selection", interrupt_for_selection_node)

    # Add edges
    workflow.set_entry_point("classify_input")
    workflow.add_edge("classify_input", "parse_files")
    workflow.add_edge("parse_files", "discover_from_web")
    workflow.add_edge("discover_from_web", "endpoint_extractor")
    workflow.add_edge("endpoint_extractor", "normalize_and_dedup")
    workflow.add_edge("normalize_and_dedup", "summarize_for_ui")
    workflow.add_edge("summarize_for_ui", "interrupt_for_selection")
    workflow.add_edge("interrupt_for_selection", END)

    return workflow
