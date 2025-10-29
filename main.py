#!/usr/bin/env python3
"""Main entry point for MCP Gateway workflows.

This module provides:
- CLI interface for running Discovery and Generation workflows
- Example workflow execution
- Interactive mode for endpoint selection and review
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple

import click
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StateSnapshot

from utils import build_full_workflow


def run_discovery_from_files(
    file_paths: List[str], thread_id: str = "discovery-session"
) -> Tuple[Any, Dict[str, Any], StateSnapshot]:
    """Run Discovery Graph with file inputs.

    Args:
        file_paths: List of paths to API spec files
        thread_id: Unique thread ID for checkpointing

    Returns:
        Tuple of (discovery_graph, config, state)
    """
    print("\n" + "=" * 60)
    print("🔍 Running Discovery Graph (File Mode)")
    print("=" * 60 + "\n")

    discovery_graph, _ = build_full_workflow()

    discovery_input = {"input": {"files": file_paths}, "discovery": {}, "selection": {}}

    config = {"configurable": {"thread_id": thread_id}}

    # Run until interrupt
    for event in discovery_graph.stream(discovery_input, config):
        print(f"📋 Event: {list(event.keys())}")

    # Get state
    state = discovery_graph.get_state(config)
    catalog = state.values.get("discovery", {}).get("catalog", {})

    print("\n✅ Discovery complete!")
    print(f"📊 Found {catalog.get('total_endpoints', 0)} endpoints")
    print(f"📁 Resource groups: {catalog.get('resource_count', 0)}")

    return discovery_graph, config, state


def run_discovery_from_url(
    root_url: str, thread_id: str = "discovery-session"
) -> Tuple[Any, Dict[str, Any], StateSnapshot]:
    """Run Discovery Graph with URL input.

    Args:
        root_url: Root URL to crawl for API documentation
        thread_id: Unique thread ID for checkpointing

    Returns:
        Tuple of (discovery_graph, config, state)
    """
    print("\n" + "=" * 60)
    print("🌐 Running Discovery Graph (URL Mode)")
    print("=" * 60 + "\n")

    discovery_graph, _ = build_full_workflow()

    discovery_input = {
        "input": {"root_url": root_url},
        "discovery": {},
        "selection": {},
    }

    config = {"configurable": {"thread_id": thread_id}}

    # Run until interrupt
    for event in discovery_graph.stream(discovery_input, config):
        print(f"📋 Event: {list(event.keys())}")

    # Get state
    state = discovery_graph.get_state(config)
    catalog = state.values.get("discovery", {}).get("catalog", {})

    print("\n✅ Discovery complete!")
    print(f"📊 Found {catalog.get('total_endpoints', 0)} endpoints")
    print(f"📁 Resource groups: {catalog.get('resource_count', 0)}")

    return discovery_graph, config, state


def resume_discovery_with_selection(
    discovery_graph: CompiledStateGraph, config: Dict[str, Any], endpoint_ids: List[str]
) -> Any:
    """Resume Discovery Graph with user-selected endpoints.

    Args:
        discovery_graph: Compiled discovery graph
        config: Configuration with thread_id
        endpoint_ids: List of selected endpoint IDs

    Returns:
        Final state with selected endpoints
    """
    print(f"\n🔹 Resuming with {len(endpoint_ids)} selected endpoints")

    discovery_graph.update_state(
        config,
        {"selection": {"endpoint_ids": endpoint_ids}},
        as_node="interrupt_for_selection",
    )

    # Complete discovery
    for event in discovery_graph.stream(None, config):
        pass

    return discovery_graph.get_state(config)


def run_generation(
    selected_ids: List[str],
    endpoints: List[Dict[str, Any]],
    thread_id: str = "generation-session",
) -> Tuple[Any, Dict[str, Any], StateSnapshot]:
    """Run Generation Graph with selected endpoints.

    Args:
        selected_ids: List of selected endpoint IDs
        endpoints: List of normalized endpoint dictionaries
        thread_id: Unique thread ID for checkpointing

    Returns:
        Tuple of (generation_graph, config, state)
    """
    print("\n" + "=" * 60)
    print("🔧 Running Generation Graph")
    print("=" * 60 + "\n")

    _, generation_graph = build_full_workflow()

    generation_input = {
        "selection": {"endpoint_ids": selected_ids, "endpoints": endpoints},
        "generation": {},
    }

    config = {"configurable": {"thread_id": thread_id}}

    # Run until interrupt
    for event in generation_graph.stream(generation_input, config):
        print(f"📋 Event: {list(event.keys())}")

    # Get state
    state = generation_graph.get_state(config)
    tools = state.values.get("generation", {}).get("tools", [])

    print("\n✅ Generation complete!")
    print(f"🛠️  Generated {len(tools)} MCP tools")

    return generation_graph, config, state


def resume_generation_with_approval(
    generation_graph: CompiledStateGraph,
    config: Dict[str, Any],
    approved: bool = True,
    edited_tools: Optional[List[Dict[str, Any]]] = None,
) -> Any:
    """Resume Generation Graph with user approval or edits.

    Args:
        generation_graph: Compiled generation graph
        config: Configuration with thread_id
        approved: Whether tools are approved
        edited_tools: Optional edited tools list

    Returns:
        Final state with finalized tools
    """
    print(f"\n🔹 Resuming generation (approved={approved})")

    update_data = {"approved": approved}
    if edited_tools:
        update_data["edited_tools"] = edited_tools

    generation_graph.update_state(config, update_data, as_node="interrupt_for_review")

    # Complete generation
    for event in generation_graph.stream(None, config):
        pass

    return generation_graph.get_state(config)


def save_tools_to_file(tools: List[Dict[str, Any]], output_path: str) -> None:
    """Save MCP tools to JSON file.

    Args:
        tools: List of MCP tool dictionaries
        output_path: Path to save the output file
    """
    with open(output_path, "w") as f:
        json.dump(tools, f, indent=2)
    print(f"\n💾 Tools saved to: {output_path}")


@click.command(
    help="MCP Gateway: API Discovery and Tool Generation",
    epilog="""
Examples:

  \b
  # Run with OpenAPI spec file
  python main.py --files api_spec.json --output tools.json

  \b
  # Run with multiple spec files
  python main.py --files spec1.json --files spec2.yaml --output tools.json

  \b
  # Run with URL
  python main.py --url https://api.example.com/docs --output tools.json

  \b
  # Run example workflow
  python main.py --example

  \b
  # Interactive mode (auto-select all endpoints)
  python main.py --files api_spec.json --auto-approve --output tools.json

  \b
  # Debug mode with verbose logging
  python main.py --files api_spec.json --debug
    """,
)
@click.option(
    "--files",
    "-f",
    multiple=True,
    type=click.Path(exists=True),
    help="Path(s) to API specification file(s). Can be used multiple times.",
)
@click.option(
    "--url",
    "-u",
    type=str,
    help="Root URL to crawl for API documentation.",
)
@click.option(
    "--output",
    "-o",
    default="mcp_tools.json",
    type=click.Path(),
    help="Output file path for generated tools.",
    show_default=True,
)
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Automatically approve all endpoints and tools (non-interactive).",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode with verbose logging and full tracebacks.",
)
def main(
    files: Tuple[str, ...],
    url: Optional[str],
    output: str,
    auto_approve: bool,
) -> None:
    """Main CLI entry point."""

    # Validate input
    if not files and not url:
        click.echo(
            click.style(
                "❌ Error: Either --files or --url must be provided (or use --example)",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    if files and url:
        click.echo(
            click.style("❌ Error: Cannot use both --files and --url together", fg="red"),
            err=True,
        )
        sys.exit(1)

    # Run discovery
    if files:
        discovery_graph, disc_config, disc_state = run_discovery_from_files(list(files))
    else:
        discovery_graph, disc_config, disc_state = run_discovery_from_url(url)

    # Get discovered endpoints
    endpoints = disc_state.values.get("discovery", {}).get("endpoints_normalized", [])

    if not endpoints:
        print("\n⚠️ No endpoints discovered. Exiting.")
        sys.exit(1)

    # Auto-select all endpoints or wait for user input
    if auto_approve:
        selected_ids = [ep["id"] for ep in endpoints]
        print(f"\n✅ Auto-selecting all {len(selected_ids)} endpoints")
    else:
        print("\n📋 Discovered endpoints:")
        for i, ep in enumerate(endpoints):
            print(f"  {i+1}. [{ep['id']}] {ep['method']} {ep['path']}")
        print("\nℹ️  Auto-selecting all endpoints (use --auto-approve to skip this message)")
        selected_ids = [ep["id"] for ep in endpoints]

    # Resume discovery with selection
    final_disc_state = resume_discovery_with_selection(discovery_graph, disc_config, selected_ids)

    # Run generation
    generation_graph, gen_config, gen_state = run_generation(selected_ids, endpoints)

    # Get generated tools
    tools = gen_state.values.get("generation", {}).get("tools", [])

    # Auto-approve or wait for user input
    if auto_approve:
        print(f"\n✅ Auto-approving all {len(tools)} tools")
    else:
        print("\n📦 Generated tools:")
        for i, tool in enumerate(tools):
            print(f"  {i+1}. {tool['name']}: {tool['description'][:60]}...")
        print("\nℹ️  Auto-approving all tools (use --auto-approve to skip this message)")

    # Resume generation with approval
    final_gen_state = resume_generation_with_approval(generation_graph, gen_config, approved=True)

    # Get final tools
    final_tools = final_gen_state.values.get("generation", {}).get("tools", [])

    # Save to file
    save_tools_to_file(final_tools, output)

    print(f"\n🎉 Success! Generated {len(final_tools)} MCP tools")


if __name__ == "__main__":
    main()
