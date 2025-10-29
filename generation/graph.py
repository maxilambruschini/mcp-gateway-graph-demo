"""Generation Graph builder.

This module builds the Generation Graph workflow that:
- Plans work items for selected endpoints
- Fetches full documentation
- Synthesizes JSON Schema parameters
- Composes MCP tool definitions
- Validates schemas
- Aggregates tools
- Interrupts for review
- Finalizes output
"""

from langgraph.graph import END, StateGraph

from generation.nodes import (aggregate_tools_node, compose_tool_node,
                              fetch_docs_node, finalize_node,
                              interrupt_for_review_node, plan_work_node,
                              schema_synthesis_node, validate_node)
from models import GenerationState


def build_generation_graph():
    """Build and return the Generation Graph.

    Returns:
        StateGraph workflow for generation
    """
    workflow = StateGraph(GenerationState)

    # Add nodes
    workflow.add_node("plan_work", plan_work_node)
    workflow.add_node("fetch_docs", fetch_docs_node)
    workflow.add_node("schema_synthesis", schema_synthesis_node)
    workflow.add_node("compose_tool", compose_tool_node)
    workflow.add_node("validate", validate_node)
    workflow.add_node("aggregate_tools", aggregate_tools_node)
    workflow.add_node("interrupt_for_review", interrupt_for_review_node)
    workflow.add_node("finalize", finalize_node)

    # Add edges
    workflow.set_entry_point("plan_work")
    workflow.add_edge("plan_work", "fetch_docs")
    workflow.add_edge("fetch_docs", "schema_synthesis")
    workflow.add_edge("schema_synthesis", "compose_tool")
    workflow.add_edge("compose_tool", "validate")
    workflow.add_edge("validate", "aggregate_tools")
    workflow.add_edge("aggregate_tools", "interrupt_for_review")
    workflow.add_edge("interrupt_for_review", "finalize")
    workflow.add_edge("finalize", END)

    return workflow
