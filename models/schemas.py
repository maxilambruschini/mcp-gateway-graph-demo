"""State schemas and Pydantic models for MCP Gateway workflows.

This module contains:
- TypedDict state schemas for Discovery and Generation graphs
- Pydantic models for structured data extraction
"""

from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field

# ============================================================================
# TypedDict State Schemas
# ============================================================================


class DiscoveryState(TypedDict):
    """State for the Discovery Graph."""

    input: Dict[str, Any]  # {"files": [paths], "server_url": str}
    discovery: Dict[
        str, Any
    ]  # {"pages": [], "endpoints_raw": [], "catalog": {}, "endpoints_normalized": []}


class GenerationState(TypedDict):
    """State for the Generation Graph."""

    selection: Dict[str, Any]  # {"endpoint_ids": [...], "endpoints": [...], "vendor": str}
    generation: Dict[str, Any]  # {"work_items": [], "tools": [], "errors": []}


# ============================================================================
# Pydantic Models for Structured Extraction
# ============================================================================


class EndpointInfo(BaseModel):
    """Structured endpoint information."""

    method: str = Field(description="HTTP method (GET, POST, etc.)")
    path: str = Field(description="API path like /api/v1/resource")
    server: Optional[str] = Field(default="", description="Base server URL")
    description: str = Field(description="Human-readable description")
    parameters: Optional[List[Dict[str, Any]]] = Field(default=[], description="Parameter details")


class EndpointList(BaseModel):
    """List of endpoints extracted from content."""

    endpoints: List[EndpointInfo]
