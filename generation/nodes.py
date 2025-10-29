"""Node functions for the Generation Graph.

This module contains all 8 node functions:
1. plan_work_node
2. fetch_docs_node
3. schema_synthesis_node
4. compose_tool_node
5. validate_node
6. aggregate_tools_node
7. interrupt_for_review_node
8. finalize_node
"""

import json

import jsonschema
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import interrupt

from config import llm
from discovery.helpers import calculate_confidence
from generation.helpers import (
    determine_verb,
    enhance_schema_with_metadata,
    extract_resource,
    extract_vendor,
    extract_version,
    fetch_with_retry,
    generate_display_name,
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


def fetch_docs_node(state: GenerationState) -> GenerationState:
    """Fetch full documentation for each endpoint (with retry).

    Args:
        state: Current generation state

    Returns:
        Updated state with full documentation
    """
    generation = state["generation"]
    work_items = generation["work_items"]

    for item in work_items:
        endpoint = item["endpoint"]

        # If we already have full spec, skip
        if endpoint.get("source") == "openapi" and endpoint.get("requestBody"):
            item["full_docs"] = endpoint
            continue

        # Try to fetch more details
        server = endpoint.get("server", "")
        if server.startswith("http"):
            full_docs = fetch_with_retry(server)
            item["full_docs"] = full_docs or endpoint
        else:
            item["full_docs"] = endpoint

    return {**state, "generation": generation}


def schema_synthesis_node(state: GenerationState) -> GenerationState:
    """Generate JSON Schema Draft-07 compliant parameter schemas using LLM.

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
  * "display_name": human-readable name
  * "description": human-readable description. Can be a little longer than display_name
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

Return ONLY valid JSON without markdown formatting.""",
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

    for item in work_items:
        endpoint = item["full_docs"]

        try:
            schema = chain.invoke(
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

    return {**state, "generation": generation}


def compose_tool_node(state: GenerationState) -> GenerationState:
    """Build final MCP tool objects with proper naming and structure.

    Args:
        state: Current generation state

    Returns:
        Updated state with composed MCP tools
    """
    generation = state["generation"]
    work_items = generation["work_items"]

    tools = []

    for item in work_items:
        if item["status"] != "schema_generated":
            continue

        endpoint = item["endpoint"]
        schema = item["schema"]

        # Extract vendor from server URL
        server = endpoint.get("server", "")
        vendor = extract_vendor(server)

        # Extract resource and verb from path
        path = endpoint["path"]
        resource = extract_resource(path)
        verb = determine_verb(endpoint["method"], path)

        # Compose tool name: VENDOR__RESOURCE__VERB
        tool_name = f"{vendor}__{resource}__{verb}".upper()

        # Generate display name
        description = endpoint.get("description", f"{endpoint['method']} {path}")
        display_name = generate_display_name(tool_name, description)

        # Build MCP tool
        tool = {
            "name": tool_name,
            "display_name": display_name,
            "description": description,
            "tags": [
                vendor,
                resource,
                extract_version(path),
                endpoint["method"].lower(),
            ],
            "visibility": "public",
            "active": True,
            "protocol": "rest",
            "protocol_data": {
                "method": endpoint["method"],
                "path": path,
                "server_url": server,
            },
            "parameters": schema,
            "metadata": {
                "source": endpoint.get("source", "unknown"),
                "confidence": calculate_confidence(endpoint),
            },
        }

        tools.append(tool)
        item["status"] = "composed"

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

        except jsonschema.exceptions.SchemaError as e:
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


def interrupt_for_review_node(state: GenerationState) -> GenerationState:
    """Interrupt for human review and editing.

    Args:
        state: Current generation state

    Returns:
        Updated state with reviewed tools (populated on resume)
    """
    generation = state["generation"]
    tools = generation["tools"]

    print("\n" + "=" * 60)
    print("🛑 INTERRUPT: Please review generated MCP tools")
    print("=" * 60)
    print(f"\nGenerated {len(tools)} tools:")

    for tool in tools[:5]:  # Show first 5
        print(f"\n📦 {tool['name']}")
        print(f"   Description: {tool['description'][:80]}...")
        print(f"   Tags: {', '.join(tool['tags'])}")

    if len(tools) > 5:
        print(f"\n... and {len(tools) - 5} more")

    # Trigger interrupt
    review_result = interrupt(
        value={
            "tools": tools,
            "message": "Provide 'approved': true to finalize, or 'edited_tools' to update",
        }
    )

    # Apply any edits
    if review_result and review_result.get("edited_tools"):
        generation["tools"] = review_result["edited_tools"]

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
