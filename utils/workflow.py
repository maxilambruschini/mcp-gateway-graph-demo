"""Workflow utilities for combining Discovery and Generation graphs.

This module provides:
- build_full_workflow(): Combines both graphs with checkpointing
"""

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from discovery import build_discovery_graph
from generation import build_generation_graph


def build_full_workflow():
    """Build complete workflow with both Discovery and Generation graphs.

    This function:
    - Creates an in-memory SQLite connection for checkpointing
    - Builds both graphs with SqliteSaver for state persistence
    - Configures interrupt points for human-in-the-loop

    Returns:
        Tuple of (discovery_graph, generation_graph) compiled workflows
    """
    # Initialize checkpointer - create connection directly
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    # Build both graphs
    discovery_graph = build_discovery_graph().compile(
        checkpointer=checkpointer, interrupt_before=["interrupt_for_selection"]
    )

    generation_graph = build_generation_graph().compile(
        checkpointer=checkpointer, interrupt_before=["interrupt_for_review"]
    )

    return discovery_graph, generation_graph
