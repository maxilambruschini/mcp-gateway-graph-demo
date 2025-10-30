"""Node functions for the Discovery Graph.

This module contains all 6 node functions:
1. classify_input_node
2. parse_files_node
3. discover_from_web_node
4. endpoint_extractor_node
5. normalize_and_dedup_node
6. summarize_for_ui_node
"""

import hashlib
import json
import re

import yaml

from discovery.helpers import (
    calculate_confidence,
    extract_openapi_endpoints,
    llm_extract_endpoints,
    simple_crawl,
    try_sitemap,
)
from models import DiscoveryState


def classify_input_node(state: DiscoveryState) -> DiscoveryState:
    """Classify whether input is file-based or URL-based.

    Args:
        state: Current discovery state

    Returns:
        Updated state with input_type classification
    """
    input_data = state["input"]

    discovery = {
        "input_type": "file" if input_data.get("files") else "url",
        "pages": [],
        "endpoints_raw": [],
        "catalog": {},
    }

    print(f"📋 Input classified as: {discovery['input_type']}")

    return {**state, "discovery": discovery}


def parse_files_node(state: DiscoveryState) -> DiscoveryState:
    """Parse uploaded API spec files (JSON/YAML OpenAPI or free-form text).

    Args:
        state: Current discovery state

    Returns:
        Updated state with extracted endpoints from files
    """
    discovery = state["discovery"]
    files = state["input"].get("files", [])
    endpoints_raw = []

    for file_path in files:
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Try parsing as JSON/YAML OpenAPI
            try:
                if file_path.endswith(".json"):
                    spec = json.loads(content)
                else:
                    spec = yaml.safe_load(content)

                # Extract OpenAPI paths
                if "paths" in spec:
                    endpoints_raw.extend(extract_openapi_endpoints(spec))
                    print(f"✅ Parsed OpenAPI spec: {file_path}")
                else:
                    # Fall back to LLM parsing
                    endpoints_raw.extend(llm_extract_endpoints(content))
                    print(f"✅ LLM parsed non-OpenAPI file: {file_path}")

            except (json.JSONDecodeError, yaml.YAMLError):
                # Free-form text - use LLM
                endpoints_raw.extend(llm_extract_endpoints(content))
                print(f"✅ LLM parsed text file: {file_path}")

        except Exception as e:
            print(f"⚠️ Error parsing {file_path}: {e}")

    discovery["endpoints_raw"] = endpoints_raw
    return {**state, "discovery": discovery}


def discover_from_web_node(state: DiscoveryState) -> DiscoveryState:
    """Crawl documentation sites to discover endpoints.

    Args:
        state: Current discovery state

    Returns:
        Updated state with discovered web pages
    """
    discovery = state["discovery"]
    root_url = state["input"].get("root_url")
    if not root_url:
        return state

    print(f"🌐 Discovering from URL: {root_url}")

    # Try to find sitemap first
    pages = try_sitemap(root_url)

    if not pages:
        # Fallback to simple crawl
        pages = simple_crawl(root_url, max_pages=10)

    discovery["pages"] = pages
    print(f"✅ Discovered {len(pages)} pages")

    return {**state, "discovery": discovery}


def endpoint_extractor_node(state: DiscoveryState) -> DiscoveryState:
    """Extract endpoint information using regex + LLM.

    Args:
        state: Current discovery state

    Returns:
        Updated state with extracted endpoints from pages
    """
    input = state["input"]
    server_url = input.get("server_url", "")
    discovery = state["discovery"]
    pages = discovery.get("pages", [])

    if not pages:
        return state

    print(f"🔍 Extracting endpoints from {len(pages)} pages...")

    endpoints_raw = discovery.get("endpoints_raw", [])

    for page in pages:
        print("Extracting from page:", page.get("url", "N/A"))
        content = page.get("content", "")
        if not content:
            continue

        # Regex patterns for common API endpoint formats
        patterns = [
            r"(GET|POST|PUT|DELETE|PATCH)\s+(/api/[\w\-/{}]+)",
            r"(GET|POST|PUT|DELETE|PATCH)\s+(/v\d+/[\w\-/{}]+)",
            r"`(GET|POST|PUT|DELETE|PATCH)\s+([^`]+)`",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for method, path in matches:
                endpoints_raw.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "server": server_url,
                        "description": "",
                        "source": "regex",
                    }
                )

        # Also use LLM for structured extraction (sample pages to save tokens)
        llm_endpoints = llm_extract_endpoints(content)
        endpoints_raw.extend(llm_endpoints)

    discovery["endpoints_raw"] = endpoints_raw
    print(f"✅ Extracted {len(endpoints_raw)} raw endpoints")

    return {**state, "discovery": discovery}


def normalize_and_dedup_node(state: DiscoveryState) -> DiscoveryState:
    """Normalize and deduplicate endpoints.

    Args:
        state: Current discovery state

    Returns:
        Updated state with normalized and deduplicated endpoints
    """
    input = state["input"]
    server_url = input.get("server_url", "")
    discovery = state["discovery"]
    endpoints_raw = discovery.get("endpoints_raw", [])

    # Normalize and create unique keys
    seen = set()
    normalized = []

    for ep in endpoints_raw:
        # Create unique key
        method = ep.get("method", "GET").upper()
        path = ep.get("path", "").strip()

        if not path:
            continue

        # Normalize path
        path = path.split("?")[0]  # Remove query string
        path = re.sub(r"\s+", "", path)  # Remove whitespace

        unique_key = f"{server_url}|{method}|{path}"

        if unique_key not in seen:
            seen.add(unique_key)

            # Create normalized endpoint
            normalized_ep = {
                "id": hashlib.md5(unique_key.encode()).hexdigest()[:12],
                "method": method,
                "path": path,
                "server": server_url,
                "description": ep.get("description", "").strip(),
                "parameters": ep.get("parameters", []),
                "requestBody": ep.get("requestBody", {}),
                "source": ep.get("source", "unknown"),
            }

            normalized.append(normalized_ep)

    discovery["endpoints_normalized"] = normalized
    print(f"✅ Normalized to {len(normalized)} unique endpoints")

    return {**state, "discovery": discovery}


def summarize_for_ui_node(state: DiscoveryState) -> DiscoveryState:
    """Create concise summaries grouped by resource.

    Args:
        state: Current discovery state

    Returns:
        Updated state with catalog of grouped endpoints
    """
    discovery = state["discovery"]
    endpoints = discovery.get("endpoints_normalized", [])

    # Group by resource (first path segment after version)
    groups = {}

    for ep in endpoints:
        path = ep["path"]

        # Extract resource name
        parts = [
            p for p in path.split("/") if p and not p.startswith("v") and not p.startswith("{")
        ]
        resource = parts[0] if parts else "other"

        if resource not in groups:
            groups[resource] = []

        groups[resource].append(
            {
                "id": ep["id"],
                "method": ep["method"],
                "path": ep["path"],
                "description": ep["description"] or f"{ep['method']} {ep['path']}",
                "confidence": calculate_confidence(ep),
            }
        )

    # Create catalog
    catalog = {
        "total_endpoints": len(endpoints),
        "resources": groups,
        "resource_count": len(groups),
    }

    discovery["catalog"] = catalog
    print(f"✅ Created catalog with {len(groups)} resource groups")

    return {**state, "discovery": discovery}
