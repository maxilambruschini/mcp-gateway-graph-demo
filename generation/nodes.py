"""Node functions for the Generation Graph.

This module contains all 6 node functions:
1. plan_work_node
2. schema_synthesis_node
3. compose_tool_node
4. validate_node
5. aggregate_tools_node
6. finalize_node
"""

import asyncio
import json

import jsonschema
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import llm
from discovery.helpers import calculate_confidence
from generation.helpers import (
    enhance_schema_with_metadata,
    generate_display_name,
    generate_tool_name_from_display,
    remove_custom_fields,
)
from models import GenerationState


def plan_work_node(state: GenerationState) -> GenerationState:
    """Create work items for each selected endpoint.

    Args:
        state: Current generation state

    Returns:
        Updated state with work items
    """
    selection = state["selection"]
    endpoint_ids = selection.get("endpoint_ids", [])
    endpoints = selection.get("endpoints", [])

    # Create work items
    work_items = []
    for endpoint in endpoints:
        if endpoint["id"] in endpoint_ids:
            work_items.append({"id": endpoint["id"], "endpoint": endpoint, "status": "pending"})

    generation = {"work_items": work_items, "tools": [], "errors": []}

    print(f"📋 Created {len(work_items)} work items")

    return {**state, "generation": generation}


def schema_synthesis_node(state: GenerationState) -> GenerationState:
    """Generate JSON Schema Draft-07 compliant parameter schemas using LLM.

    Uses async processing with ainvoke() for concurrent schema generation.
    Wraps async logic in asyncio.run() for sync compatibility.

    Args:
        state: Current generation state

    Returns:
        Updated state with generated schemas
    """
    generation = state["generation"]
    work_items = generation["work_items"]

    schema_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """Generate a JSON Schema parameter schema for the given API endpoint.

IMPORTANT STRUCTURE REQUIREMENTS:
- Organize parameters as nested objects with these top-level groups:
  * "header" (singular) - for HTTP headers
  * "path" - for path parameters
  * "query" - for query string parameters
  * "body" - for request body
- Do NOT include a "$schema" field
- Each property object MUST include:
  * "type": the JSON type
  * "description": human-readable description
  * "properties": nested properties (for objects)
  * "required": array of required field names (can be empty [])
  * "visible": array of visible field names (list all properties)
  * "additionalProperties": boolean (false for strict schemas, true only if API accepts extra fields)

SCHEMA FEATURES TO INCLUDE:
- Use "enum" arrays for fields with restricted values
- Include "minLength", "maxLength" for strings
- Include "minimum", "maximum" for integers
- Include "minItems", "maxItems" for arrays
- Include "pattern" for regex validation
- Include "format" (date, date-time, email, uri, etc.)
- Include "default" values where applicable
- Use array notation for nullable types: ["string", "null"]
- Use "allOf", "oneOf", "anyOf" for complex validation when needed

Return ONLY valid JSON without markdown formatting.""",  # noqa: E501
            ),
            (
                "human",
                """Endpoint: {method} {path}
Description: {description}
Parameters: {parameters}
Request Body: {request_body}""",
            ),
        ]
    )

    parser = JsonOutputParser()
    chain = schema_prompt | llm | parser

    async def process_all_items():
        """Process all work items concurrently."""

        async def process_item(item):
            """Process a single work item asynchronously."""
            endpoint = item["endpoint"]

            try:
                schema = await chain.ainvoke(
                    {
                        "method": endpoint["method"],
                        "path": endpoint["path"],
                        "description": endpoint.get("description", ""),
                        "parameters": json.dumps(endpoint.get("parameters", [])),
                        "request_body": json.dumps(endpoint.get("requestBody", {})),
                    }
                )

                # Enhance schema with metadata (required, visible, additionalProperties)
                schema = enhance_schema_with_metadata(schema, endpoint)

                item["schema"] = schema
                item["status"] = "schema_generated"

            except Exception as e:
                print(f"⚠️ Schema generation failed for {endpoint['id']}: {e}")
                generation["errors"].append(
                    {
                        "endpoint_id": endpoint["id"],
                        "error": str(e),
                        "stage": "schema_synthesis",
                    }
                )
                item["status"] = "error"

        # Process all items concurrently
        await asyncio.gather(*[process_item(item) for item in work_items])

    # Run async logic in sync context
    asyncio.run(process_all_items())

    return {**state, "generation": generation}


def compose_tool_node(state: GenerationState) -> GenerationState:
    """Build final MCP tool objects with proper naming and structure.

    Uses async processing for concurrent display name generation.

    Args:
        state: Current generation state

    Returns:
        Updated state with composed MCP tools
    """
    generation = state["generation"]
    work_items = generation["work_items"]

    tools = []

    # Get vendor and server_url from selection state
    selection = state["selection"]
    vendor = selection["vendor"]
    user_server_url = selection.get("server_url", "")

    async def process_all_items():
        """Process all work items concurrently."""

        async def process_item(item):
            """Process a single work item asynchronously."""
            if item["status"] != "schema_generated":
                return None

            endpoint = item["endpoint"]
            schema = item["schema"]

            # Extract components
            path = endpoint["path"]
            method = endpoint["method"]
            description = endpoint.get("description", f"{method} {path}")

            # User-provided server_url takes precedence over discovered server
            server = user_server_url or endpoint.get("server", "")

            # Generate display name first (using LLM - async)
            display_name = await generate_display_name(method, path, description)

            # Generate tool name from vendor, resource, and display name
            tool_name = generate_tool_name_from_display(vendor, display_name)

            # Build MCP tool
            tool = {
                "name": tool_name,
                "display_name": display_name,
                "description": description,
                "tags": [
                    vendor,
                    method.lower(),
                ],
                "visibility": "public",
                "active": True,
                "protocol": "rest",
                "protocol_data": {
                    "method": method,
                    "path": path,
                    "server_url": server,
                },
                "parameters": schema,
                "metadata": {
                    "source": endpoint.get("source", "unknown"),
                    "confidence": calculate_confidence(endpoint),
                },
            }

            item["status"] = "composed"
            return tool

        # Process all items concurrently
        results = await asyncio.gather(*[process_item(item) for item in work_items])

        # Filter out None results (items that were skipped)
        return [tool for tool in results if tool is not None]

    # Run async logic in sync context
    tools = asyncio.run(process_all_items())

    generation["tools"] = tools
    print(f"✅ Composed {len(tools)} MCP tools")

    return {**state, "generation": generation}


def validate_node(state: GenerationState) -> GenerationState:
    """Validate each tool's schema using JSON Schema Draft-07.

    Args:
        state: Current generation state

    Returns:
        Updated state with validated tools only
    """
    generation = state["generation"]
    tools = generation["tools"]

    validated_tools = []

    for tool in tools:
        try:
            # Create a copy of the schema without custom fields for validation
            schema = tool["parameters"]
            cleaned_schema = remove_custom_fields(schema)

            # Validate the cleaned schema against Draft-07
            jsonschema.Draft7Validator.check_schema(cleaned_schema)

            # Mark as validated (keep original schema with custom fields)
            tool["validated"] = True
            validated_tools.append(tool)

        except jsonschema.SchemaError as e:
            print(f"⚠️ Schema validation failed for {tool['name']}: {e}")
            generation["errors"].append(
                {"tool_name": tool["name"], "error": str(e), "stage": "validation"}
            )

    generation["tools"] = validated_tools
    print(f"✅ Validated {len(validated_tools)} tools")

    return {**state, "generation": generation}


def aggregate_tools_node(state: GenerationState) -> GenerationState:
    """Aggregate all validated tools into final list.

    Args:
        state: Current generation state

    Returns:
        Updated state with sorted tools
    """
    generation = state["generation"]
    tools = generation["tools"]

    # Sort by name for consistency
    tools.sort(key=lambda t: t["name"])

    print(f"✅ Aggregated {len(tools)} tools")

    return {**state, "generation": generation}


def finalize_node(state: GenerationState) -> GenerationState:
    """Finalize and return the complete tool list.

    Args:
        state: Current generation state

    Returns:
        Updated state with finalization status
    """
    generation = state["generation"]
    tools = generation["tools"]
    errors = generation.get("errors", [])

    print(f"\n✅ FINALIZED: {len(tools)} MCP tools ready")
    if errors:
        print(f"⚠️ {len(errors)} errors encountered during generation")

    generation["status"] = "completed"
    generation["final_count"] = len(tools)

    return {**state, "generation": generation}
