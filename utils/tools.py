import json
from typing import Any, Dict, List

import questionary


def save_tools_to_file(tools: List[Dict[str, Any]], output_path: str) -> None:
    """Save MCP tools to JSON file.

    Args:
        tools: List of MCP tool dictionaries
        output_path: Path to save the output file
    """
    with open(output_path, "w") as f:
        json.dump(tools, f, indent=2)
    print(f"\n💾 Tools saved to: {output_path}")


def select_endpoints_interactively(endpoints: List[Dict[str, Any]]) -> List[str]:
    """Interactive endpoint selection using questionary checkbox.

    Args:
        endpoints: List of endpoint dictionaries with 'id', 'method', and 'path' keys

    Returns:
        List of selected endpoint IDs
    """
    print(
        "\n📋 Discovered endpoints - Use arrow keys to navigate, Space to select/deselect, Enter to confirm"  # noqa: E501
    )

    # Create choices with formatted display names
    choices = []
    for ep in endpoints:
        # Format: [METHOD] /path/to/endpoint
        display = f"[{ep['method']:6}] {ep['path']}"
        choices.append(
            questionary.Choice(
                title=display,
                value=ep["id"],
                checked=False,  # Start with nothing selected
            )
        )

    # Show checkbox prompt
    selected_ids = questionary.checkbox(
        "Select endpoints to generate tools from (use Space to toggle, Enter to confirm):",
        choices=choices,
        validate=lambda x: len(x) > 0 or "You must select at least one endpoint",
    ).ask()

    # Handle cancellation (Ctrl+C)
    if selected_ids is None:
        raise ValueError("Selection cancelled by user")

    if not selected_ids:
        raise ValueError("No endpoints selected")

    print(f"\n✅ Selected {len(selected_ids)} endpoint(s)")
    return selected_ids
