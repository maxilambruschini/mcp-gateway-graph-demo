from typing import Any, Dict, List

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StateSnapshot


def run_generation(
    generation_graph: CompiledStateGraph,
    selected_ids: List[str],
    endpoints: List[Dict[str, Any]],
    vendor: str,
    server_url: str,
    thread_id: str = "generation-session",
) -> StateSnapshot:
    """Run Generation Graph with selected endpoints to completion.

    Args:
        generation_graph: Compiled generation graph
        selected_ids: List of selected endpoint IDs
        endpoints: List of normalized endpoint dictionaries
        vendor: Vendor name for tool naming (from CLI --name parameter)
        server_url: Base URL for all API endpoints
        thread_id: Unique thread ID for checkpointing

    Returns:
        Final state with generated tools
    """
    print("\n" + "=" * 60)
    print("🔧 Running Generation Graph")
    print("=" * 60 + "\n")

    generation_input = {
        "selection": {
            "endpoint_ids": selected_ids,
            "endpoints": endpoints,
            "vendor": vendor,
            "server_url": server_url,
        },
        "generation": {},
    }

    config = {"configurable": {"thread_id": thread_id}}

    # Run to completion
    for event in generation_graph.stream(generation_input, config):
        print(f"📋 Event: {list(event.keys())}")

    # Get final state
    state = generation_graph.get_state(config)
    tools = state.values.get("generation", {}).get("tools", [])

    print("\n✅ Generation complete!")
    print(f"🛠️  Generated {len(tools)} MCP tools")

    return state
