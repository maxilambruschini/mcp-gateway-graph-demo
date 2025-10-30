from typing import List

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StateSnapshot


def run_discovery_from_files(
    discovery_graph: CompiledStateGraph,
    file_paths: List[str],
    server_url: str,
    thread_id: str = "discovery-session",
) -> StateSnapshot:
    """Run Discovery Graph with file inputs.

    Args:
        file_paths: List of paths to API spec files
        server_url: Base URL for all API endpoints
        thread_id: Unique thread ID for checkpointing

    Returns:
        Tuple of (discovery_graph, config, state)
    """
    print("\n" + "=" * 60)
    print("🔍 Running Discovery Graph (File Mode)")
    print("=" * 60 + "\n")

    discovery_input = {"input": {"files": file_paths, "server_url": server_url}, "discovery": {}}

    config = {"configurable": {"thread_id": thread_id}}

    # Run to completion
    for event in discovery_graph.stream(discovery_input, config):
        print(f"📋 Event: {list(event.keys())}")

    # Get state
    state = discovery_graph.get_state(config)
    catalog = state.values.get("discovery", {}).get("catalog", {})

    print("\n✅ Discovery complete!")
    print(f"📊 Found {catalog.get('total_endpoints', 0)} endpoints")
    print(f"📁 Resource groups: {catalog.get('resource_count', 0)}")

    return state


def run_discovery_from_url(
    discovery_graph: CompiledStateGraph,
    root_url: str,
    server_url: str,
    thread_id: str = "discovery-session",
) -> StateSnapshot:
    """Run Discovery Graph with URL input.

    Args:
        root_url: Root URL to crawl for API documentation
        server_url: Base URL for all API endpoints
        thread_id: Unique thread ID for checkpointing

    Returns:
        Tuple of (discovery_graph, config, state)
    """
    print("\n" + "=" * 60)
    print("🌐 Running Discovery Graph (URL Mode)")
    print("=" * 60 + "\n")

    discovery_input = {
        "input": {"root_url": root_url, "server_url": server_url},
        "discovery": {},
    }

    config = {"configurable": {"thread_id": thread_id}}

    # Run to completion
    for event in discovery_graph.stream(discovery_input, config):
        print(f"📋 Event: {list(event.keys())}")

    # Get state
    state = discovery_graph.get_state(config)
    catalog = state.values.get("discovery", {}).get("catalog", {})

    print("\n✅ Discovery complete!")
    print(f"📊 Found {catalog.get('total_endpoints', 0)} endpoints")
    print(f"📁 Resource groups: {catalog.get('resource_count', 0)}")

    return state
