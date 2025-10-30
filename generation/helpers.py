"""Helper functions for the Generation Graph.

This module contains:
- Schema enhancement with metadata
- Display name generation
- Resource, verb extraction
- Version extraction
- Custom field removal for validation
"""

import copy
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import llm_mini


def enhance_schema_with_metadata(schema: dict, endpoint: dict) -> dict:
    """Enhance schema with required metadata fields.

    Adds:
    - 'required' arrays at all levels
    - 'visible' arrays at all levels
    - 'additionalProperties' boolean at all object levels

    Args:
        schema: Base JSON schema
        endpoint: Endpoint information for context

    Returns:
        Enhanced schema with metadata
    """

    def process_object(obj: dict, is_flexible: bool = False) -> dict:
        """Recursively process object schemas."""
        if not isinstance(obj, dict):
            return obj

        # If this is an object type schema
        if obj.get("type") == "object" or (
            isinstance(obj.get("type"), list) and "object" in obj.get("type")
        ):
            properties = obj.get("properties", {})

            # Add 'visible' array if not present (list all properties)
            if "visible" not in obj and properties:
                obj["visible"] = list(properties.keys())

            # Add 'required' array if not present
            if "required" not in obj:
                obj["required"] = []

            # Add 'additionalProperties' if not present
            # Default to false for strict validation, unless context suggests flexibility
            if "additionalProperties" not in obj:
                obj["additionalProperties"] = is_flexible

            # Recursively process nested properties
            for prop_name, prop_schema in properties.items():
                properties[prop_name] = process_object(prop_schema, is_flexible=False)

        # If this is an array type schema
        elif obj.get("type") == "array" and "items" in obj:
            items = obj["items"]
            if isinstance(items, dict):
                obj["items"] = process_object(items, is_flexible=False)

        # Process nested schemas in allOf, oneOf, anyOf
        for key in ["allOf", "oneOf", "anyOf"]:
            if key in obj and isinstance(obj[key], list):
                obj[key] = [process_object(item, is_flexible) for item in obj[key]]

        return obj

    # Determine if endpoint might need flexible schemas
    # Heuristic: if endpoint has 'requestBody' with complex structure, it might be flexible
    is_flexible_endpoint = bool(endpoint.get("requestBody", {}).get("content"))

    return process_object(schema, is_flexible=is_flexible_endpoint)


def generate_display_name_with_llm(method: str, path: str, description: str) -> str:
    """Generate a human-readable display name using LLM.

    Uses llm_mini to generate concise, action-oriented display names.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., /api/v1/flights/search)
        description: Endpoint description

    Returns:
        Human-readable display name (e.g., "Search Flights")

    Raises:
        Exception: If LLM call fails (caller should handle with fallback)
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an API documentation expert. Generate concise, action-oriented display names for API endpoints."),
        ("human", """Generate a display name for this API endpoint.

HTTP Method: {method}
Path: {path}
Description: {description}

Requirements:
- 2-5 words maximum
- Imperative/action style (e.g., "Search Flights", "Create Booking", "Get User Profile")
- Clear and user-friendly
- No special characters or underscores

Display name:""")
    ])

    chain = prompt | llm_mini | StrOutputParser()

    result = chain.invoke({
        "method": method,
        "path": path,
        "description": description or f"{method} {path}"
    })

    # Clean up the result (remove quotes, extra whitespace)
    display_name = result.strip().strip('"').strip("'").strip()

    if not display_name:
        raise ValueError("LLM returned empty display name")

    return display_name


def generate_display_name_fallback(method: str, path: str, description: str) -> str:
    """Generate a human-readable display name using heuristics (fallback logic).

    This is used when LLM-based generation fails.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., /api/v1/flights/search)
        description: Endpoint description

    Returns:
        Human-readable display name
    """
    # Try to extract from description first
    if description:
        # Use first sentence or first 50 chars
        first_sentence = description.split(".")[0].strip()
        if len(first_sentence) <= 50 and first_sentence:
            return first_sentence

    # Fall back to parsing the path and method
    resource = extract_resource(path)
    verb = determine_verb(method, path)

    # Format: "Verb Resource" (e.g., "Search Flights")
    resource_formatted = resource.replace("_", " ").title()
    verb_formatted = verb.replace("_", " ").title()

    return f"{verb_formatted} {resource_formatted}"


def generate_display_name(method: str, path: str, description: str) -> str:
    """Generate a human-readable display name with LLM and fallback.

    Tries LLM-based generation first, falls back to heuristics on failure.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path (e.g., /api/v1/flights/search)
        description: Endpoint description

    Returns:
        Human-readable display name
    """
    try:
        return generate_display_name_with_llm(method, path, description)
    except Exception as e:
        # Log the error and fall back to heuristic approach
        print(f"⚠️  LLM display name generation failed: {e}. Using fallback.")
        return generate_display_name_fallback(method, path, description)


def generate_tool_name_from_display(vendor: str, resource: str, display_name: str) -> str:
    """Generate tool name from vendor, resource, and display name.

    Format: VENDOR__RESOURCE__SANITIZED_DISPLAY_NAME

    Args:
        vendor: Vendor/service name (e.g., "example", "duffel")
        resource: Resource extracted from path (e.g., "flights", "bookings")
        display_name: Human-readable display name (e.g., "Search Flights")

    Returns:
        Tool name in VENDOR__RESOURCE__ACTION format (e.g., "EXAMPLE__FLIGHTS__SEARCH_FLIGHTS")
    """
    # Sanitize display name: remove special chars, convert spaces to underscores
    sanitized = re.sub(r'[^a-zA-Z0-9\s]', '', display_name)
    sanitized = sanitized.strip().replace(' ', '_')

    # Construct tool name
    tool_name = f"{vendor}__{resource}__{sanitized}".upper()

    return tool_name


def extract_resource(path: str) -> str:
    """Extract resource name from path.

    Args:
        path: API path (e.g., /api/v1/flights/{id})

    Returns:
        Resource name (e.g., "flights")
    """
    parts = [p for p in path.split("/") if p and not p.startswith("v") and not p.startswith("{")]
    return parts[0] if parts else "resource"


def determine_verb(method: str, path: str) -> str:
    """Determine semantic verb from method and path.

    Args:
        method: HTTP method (GET, POST, etc.)
        path: API path

    Returns:
        Semantic verb (get, list, create, update, delete, search, etc.)
    """
    method = method.upper()

    # Check for specific patterns in path
    if re.search(r"/(search|find)", path, re.IGNORECASE):
        return "search"
    if re.search(r"/list", path, re.IGNORECASE):
        return "list"

    # Method-based defaults
    verb_map = {
        "GET": "get" if "{" in path else "list",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }

    return verb_map.get(method, "execute")


def remove_custom_fields(schema: dict) -> dict:
    """Recursively remove custom fields that are not part of JSON Schema Draft-07.

    Custom fields like 'visible' are removed to create a schema suitable for validation.

    Args:
        schema: Schema with custom fields

    Returns:
        Cleaned schema copy without custom fields
    """

    def clean_object(obj):
        if not isinstance(obj, dict):
            return obj

        cleaned = {}
        for key, value in obj.items():
            # Skip custom fields
            if key == "visible":
                continue

            # Recursively clean nested objects
            if isinstance(value, dict):
                cleaned[key] = clean_object(value)
            elif isinstance(value, list):
                cleaned[key] = [
                    clean_object(item) if isinstance(item, dict) else item for item in value
                ]
            else:
                cleaned[key] = value

        return cleaned

    return clean_object(copy.deepcopy(schema))
