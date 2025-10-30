#!/usr/bin/env python3
"""Main entry point for MCP Gateway workflows.

This module provides:
- CLI interface for running Discovery and Generation workflows
- Example workflow execution
- Interactive mode for endpoint selection and review
"""

import sys
from typing import Optional, Tuple

import click

from discovery.runners import run_discovery_from_files, run_discovery_from_url
from generation.runners import run_generation
from utils import build_full_workflow, save_tools_to_file, select_endpoints_interactively


@click.command(
    help="MCP Gateway: API Discovery and Tool Generation",
    epilog="""
Examples:

  \b
  # Run with OpenAPI spec file
  python main.py --vendor myapp --server-url https://api.example.com/v1 --files api_spec.json --output tools.json

  \b
  # Run with multiple spec files
  python main.py --vendor myapp --server-url https://api.example.com/v1 --files spec1.json --files spec2.yaml --output tools.json

  \b
  # Run with URL
  python main.py --vendor myapp --server-url https://api.example.com/v1 --url https://api.example.com/docs --output tools.json

  \b
  # Interactive mode (auto-select all endpoints)
  python main.py --vendor myapp --server-url https://api.example.com/v1 --files api_spec.json --auto-approve --output tools.json
    """,
)
@click.option(
    "--vendor",
    "-n",
    type=str,
    required=True,
    help="Name of the app or service being processed.",
)
@click.option(
    "--server-url",
    "-s",
    type=str,
    required=True,
    help="Base URL for all API endpoints (e.g., https://api.example.com/v1).",
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
def main(
    vendor: str,
    server_url: str,
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

    # Generate graphs
    discovery_graph, generation_graph = build_full_workflow()

    # Run discovery
    if files:
        disc_state = run_discovery_from_files(discovery_graph, list(files), server_url)
    else:
        disc_state = run_discovery_from_url(discovery_graph, url, server_url)

    # Get discovered endpoints
    endpoints = disc_state.values.get("discovery", {}).get("endpoints_normalized", [])

    if not endpoints:
        print("\n⚠️ No endpoints discovered. Exiting.")
        sys.exit(1)

    # Auto-select all endpoints or use interactive selection
    if auto_approve:
        selected_ids = [ep["id"] for ep in endpoints]
        print(f"\n✅ Auto-selecting all {len(selected_ids)} endpoints")
    else:
        try:
            selected_ids = select_endpoints_interactively(endpoints)
        except ValueError:
            print("\n❌ No valid endpoints selected. Exiting.")
            sys.exit(1)

    # Run generation to completion
    final_state = run_generation(
        generation_graph, selected_ids, endpoints, vendor=vendor, server_url=server_url
    )

    # Get final tools
    final_tools = final_state.values.get("generation", {}).get("tools", [])

    # Save to file
    save_tools_to_file(final_tools, output)

    print(f"\n🎉 Success! Generated {len(final_tools)} MCP tools")


if __name__ == "__main__":
    main()
