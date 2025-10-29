"""Helper functions for the Generation Graph.

This module contains:
- Schema enhancement with metadata
- Display name generation
- Vendor, resource, verb extraction
- Version extraction
- Fetch with retry
- Custom field removal for validation
"""

import copy
import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests

from config import FETCH_TIMEOUT_SECONDS, MAX_FETCH_RETRIES


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


def generate_display_name(tool_name: str, description: str) -> str:
    """Generate a human-readable display name from tool name or description.

    Examples:
        DUFFEL__AIR__GET_AIRLINE -> "Get Airline"
        EXAMPLE__FLIGHTS__SEARCH -> "Search Flights"

    Args:
        tool_name: Tool name in VENDOR__RESOURCE__VERB format
        description: Description text

    Returns:
        Human-readable display name
    """
    # Try to extract from description first
    if description:
        # Use first sentence or first 50 chars
        first_sentence = description.split(".")[0].strip()
        if len(first_sentence) <= 50 and first_sentence:
            return first_sentence

    # Fall back to parsing the tool name
    parts = tool_name.split("__")
    if len(parts) >= 3:
        resource = parts[1].replace("_", " ").title()
        verb = parts[2].replace("_", " ").title()
        return f"{verb} {resource}"

    # Last resort: just title-case the name
    return tool_name.replace("_", " ").title()


def extract_vendor(server: str) -> str:
    """Extract vendor name from server URL.

    Args:
        server: Server URL (e.g., https://api.example.com)

    Returns:
        Vendor name (e.g., "example")
    """
    if not server:
        return "api"

    domain = urlparse(server).netloc
    parts = domain.split(".")

    # Get the main domain name
    if len(parts) >= 2:
        return parts[-2]
    return parts[0] if parts else "api"


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


def extract_version(path: str) -> str:
    """Extract version from path.

    Args:
        path: API path (e.g., /api/v1/resource)

    Returns:
        Version string (e.g., "v1")
    """
    match = re.search(r"v(\d+)", path, re.IGNORECASE)
    return f"v{match.group(1)}" if match else "v1"


def fetch_with_retry(url: str, max_retries: int = MAX_FETCH_RETRIES) -> Optional[dict]:
    """Fetch URL with exponential backoff.

    Args:
        url: URL to fetch
        max_retries: Maximum number of retry attempts

    Returns:
        Dictionary with 'content' key or None on failure
    """
    for attempt in range(max_retries):
        try:
            time.sleep(2**attempt)  # Exponential backoff
            response = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return {"content": response.text}
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"⚠️ Failed to fetch {url}: {e}")
    return None


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
