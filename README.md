# MCP Gateway: Discovery + Generation LangGraph Workflows

**Demo Repository**: This project is a demonstration of LangGraph workflow orchestration for API endpoint discovery and MCP tool generation. It is intended for educational and reference purposes only.

A powerful two-stage workflow system that automatically discovers API endpoints from specifications or documentation and generates JSON Schema Draft-07 compliant MCP (Model Context Protocol) tool definitions.

## Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [Workflow Details](#-workflow-details)
- [Installation](#-installation)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Output Format](#-output-format)
- [Development](#-development)

---

## Overview

This project implements two composable LangGraph workflows:

1. **DiscoveryGraph** - Intelligently discovers API endpoints from:
   - OpenAPI/Swagger specifications (JSON/YAML)
   - Documentation websites (via web crawling)
   - Free-form text files (via LLM extraction)

2. **GenerationGraph** - Generates production-ready MCP tool definitions with:
   - JSON Schema Draft-07 compliant parameter schemas
   - Comprehensive validation and error handling
   - Automated workflow from endpoint to tool

The system leverages **LangGraph** for workflow orchestration and **LangChain** for LLM operations. Both graphs run to completion without interrupts, with endpoint selection handled in the orchestration layer.

---

## Key Features

- **Multi-Source Discovery**: Handles OpenAPI specs, web documentation, and unstructured text
- **Hybrid Extraction**: Combines regex pattern matching with LLM-powered extraction
- **Smart Web Crawling**: Sitemap-aware crawling with domain boundaries and rate limiting
- **Intelligent Deduplication**: Normalizes and deduplicates discovered endpoints
- **Schema Validation**: JSON Schema Draft-07 compliance checking
- **State Persistence**: SQLite-based checkpointing for workflow resumption
- **Standardized Naming**: Consistent `VENDOR__RESOURCE__VERB` tool naming convention

---

## Architecture

### Two-Graph Workflow System

```
+-------------------------------------------------------------------+
|                        INPUT SOURCES                              |
|  * OpenAPI/Swagger Specs (JSON/YAML)                              |
|  * Documentation URLs                                             |
|  * Free-form text files                                           |
+-----------------------------+-------------------------------------+
                              |
                              v
+-------------------------------------------------------------------+
|                     DISCOVERY GRAPH                               |
|  Discovers and catalogs API endpoints                             |
+-----------------------------+-------------------------------------+
                              |
                              v
                   [Orchestration Layer]
                    (Endpoint Selection)
                              |
                              v
+-------------------------------------------------------------------+
|                    GENERATION GRAPH                               |
|  Generates MCP tool definitions                                   |
+-----------------------------+-------------------------------------+
                              |
                              v
                  >> MCP Tools (JSON) <<
```

### State Management

The system uses **TypedDict** schemas for type-safe state management:

**DiscoveryState**:
- `input`: Input configuration (files or root_url)
- `discovery`: Discovered endpoints, pages, and catalog

**GenerationState**:
- `selection`: Selected endpoints from Discovery
- `generation`: Work items, generated tools, and errors

### Orchestration Pattern

Both graphs are designed to run to completion without interrupts:

1. **Discovery Graph** runs fully and outputs all discovered endpoints in the catalog
2. **Orchestration Layer** (in `main.py`) handles endpoint selection:
   - Displays discovered endpoints to user
   - Collects user's endpoint selection
   - Passes selected endpoints to Generation Graph
3. **Generation Graph** runs fully and outputs validated MCP tool definitions

This design separates concerns: graphs handle workflow logic, while the orchestration layer handles user interaction.

---

## Workflow Details

### Discovery Graph Flow

The Discovery Graph uses **conditional branching** to route input through one of two mutually exclusive paths:

```
                    classify_input
                         |
                         v
                 [Route by input_type]
                    /         \
                   /           \
                file           url
                 /               \
                v                 v
          parse_files      discover_from_web
                 \               /
                  \             /
                   v           v
                endpoint_extractor
                       |
                       v
              normalize_and_dedup
                       |
                       v
               summarize_for_ui
                       |
                       v
                      END
```

**Conditional Routing Logic**:
- After `classify_input` determines the `input_type` ("file" or "url")
- The graph routes to **either** `parse_files` OR `discover_from_web` (never both)
- Both branches converge at `endpoint_extractor` for unified processing
- This ensures only the relevant path executes, improving efficiency and clarity

#### Node Breakdown

| Node | Purpose | Input | Output |
|------|---------|-------|--------|
| **classify_input** | Determines if input is file-based or URL-based | Raw input configuration | Classified input type |
| **parse_files** | Parses OpenAPI specs (JSON/YAML) or extracts from text | File paths | Raw endpoints from files |
| **discover_from_web** | Crawls documentation websites via sitemap or BFS | Root URL | Discovered web pages |
| **endpoint_extractor** | Extracts endpoints using regex patterns + LLM | Web pages content | Raw endpoint list |
| **normalize_and_dedup** | Normalizes paths, methods, and removes duplicates | Raw endpoints | Unique normalized endpoints |
| **summarize_for_ui** | Groups endpoints by resource and calculates confidence | Normalized endpoints | Organized catalog |

#### Discovery Node Details

**1. classify_input_node** (`discovery/nodes.py:28`)
- Examines input configuration
- Sets `input_type` to "file" or "url"
- Initializes empty discovery state structure

**2. parse_files_node** (`discovery/nodes.py:51`)
- Only executes when input_type is "file" (via conditional routing)
- Attempts to parse as JSON/YAML OpenAPI spec
- Falls back to LLM extraction for free-form text
- Extracts endpoints from OpenAPI `paths` section
- Handles multiple file formats gracefully

**3. discover_from_web_node** (`discovery/nodes.py:97`)
- Only executes when input_type is "url" (via conditional routing)
- First attempts sitemap.xml discovery
- Falls back to breadth-first crawl (max 10 pages)
- Respects domain boundaries (no external links)
- Implements throttling between requests
- Stores page content for extraction

**4. endpoint_extractor_node** (`discovery/nodes.py:126`)
- Applies regex patterns for common API formats:
  - `GET|POST|PUT|DELETE|PATCH /api/...`
  - `GET|POST|PUT|DELETE|PATCH /v1/...`
  - Backtick-wrapped endpoints
- Uses LLM for structured extraction from unstructured docs
- Stores source ("regex" or "llm") for confidence calculation

**5. normalize_and_dedup_node** (`discovery/nodes.py:183`)
- Creates unique keys: `server|method|path`
- Removes query strings and whitespace
- Generates 12-character MD5-based IDs
- Preserves descriptions, parameters, and request bodies
- Tracks source for confidence scoring

**6. summarize_for_ui_node** (`discovery/nodes.py:238`)
- Groups endpoints by resource (first path segment)
- Calculates confidence scores (0.0-1.0) based on:
  - Source type (OpenAPI > regex > LLM)
  - Presence of description
  - Parameter completeness
- Creates hierarchical catalog structure
- Provides summary statistics
- Completes the Discovery Graph workflow

---

### Generation Graph Flow

The Generation Graph consists of 6 nodes that transform selected endpoints into validated MCP tools:

```
plan_work -> schema_synthesis -> compose_tool -> validate
    -> aggregate_tools -> finalize -> END
```

#### Node Breakdown

| Node | Purpose | Input | Output |
|------|---------|-------|--------|
| **plan_work** | Creates work items for each selected endpoint | Selected endpoint IDs | Work item queue |
| **schema_synthesis** | Generates JSON Schema parameters using LLM | Endpoint details | Parameter schemas |
| **compose_tool** | Builds complete MCP tool structure with naming | Schemas + endpoints | MCP tool objects |
| **validate** | Validates schemas against JSON Schema Draft-07 | Tool definitions | Validated tools only |
| **aggregate_tools** | Sorts and aggregates all validated tools | Individual tools | Sorted tool collection |
| **finalize** | Marks completion and provides summary | Validated tools | Final tool list |

#### Generation Node Details

**1. plan_work_node** (`generation/nodes.py:34`)
- Creates work items from selected endpoint IDs
- Filters endpoints to only include selected ones
- Initializes status tracking ("pending", "schema_generated", etc.)
- Sets up error collection structure

**2. schema_synthesis_node** (`generation/nodes.py:60`)
- Uses LLM with structured prompt for each endpoint
- Generates nested parameter schema with 4 groups:
  - `header` - HTTP headers
  - `path` - Path parameters
  - `query` - Query string parameters
  - `body` - Request body
- Enforces JSON Schema features:
  - Type constraints and formats
  - Enum values for restricted fields
  - Min/max length and value constraints
  - Required field specifications
  - Nullable types using array notation
- Enhances schema with custom metadata:
  - `visible`: Array of UI-visible fields
  - `required`: Required field names
  - `additionalProperties`: Boolean for strict validation
- Handles errors gracefully, marking failed items

**3. compose_tool_node** (`generation/nodes.py:153`)
- Extracts vendor from server URL (domain or "unknown")
- Extracts resource from path (first segment after version)
- Determines verb from method + path analysis
- Composes tool name: `VENDOR__RESOURCE__VERB` (uppercase)
- Generates human-readable display name from description
- Builds complete MCP tool structure:
  - Name, display name, description
  - Tags: [vendor, resource, version, method]
  - Protocol: "rest"
  - Protocol data: method, path, server_url
  - Parameters: nested schema
  - Metadata: source and confidence score

**4. validate_node** (`generation/nodes.py:225`)
- Creates cleaned copy of schema (removes custom `visible` field)
- Validates against JSON Schema Draft-07 using `jsonschema` library
- Uses `Draft7Validator.check_schema()` for validation
- Filters out invalid tools
- Logs validation errors to errors array
- Keeps original schema with custom fields for valid tools

**5. aggregate_tools_node** (`generation/nodes.py:264`)
- Collects all validated tools
- Sorts alphabetically by tool name
- Provides consistent ordering for output

**6. finalize_node** (`generation/nodes.py:284`)
- Marks generation as "completed"
- Provides final tool count
- Reports any errors encountered
- Returns complete tool list for output

---

## Installation

This project uses **uv** for Python package management with Python 3.12+.

### Prerequisites

- Python 3.12 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd mcp-gateway-graph-demo
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Configure environment variables**:

   Create a `.env` file in the project root (use `.env.example` as template):

   ```bash
   # Required for LLM operations
   AZURE_OPENAI_API_KEY=your_api_key_here
   AZURE_OPENAI_API_VERSION=2024-02-15
   AZURE_OPENAI_ENDPOINT=https://your-endpoint.openai.azure.com/

   # Optional: LangSmith tracing
   LANGSMITH_API_KEY=your_langsmith_key
   LANGSMITH_TRACING=true
   LANGSMITH_PROJECT=mcp-gateway
   ```

---

## Usage

### Command Line Interface

The main CLI provides several commands via Click:

```bash
# Show help
uv run python main.py --help

# Run with OpenAPI spec file
uv run python main.py --files api_spec.json --output tools.json

# Run with multiple files
uv run python main.py --files spec1.json --files spec2.yaml

# Run with documentation URL
uv run python main.py --url https://api.example.com/docs --output tools.json

# Run example workflow with mock data
uv run python main.py --example

# Auto-approve mode (non-interactive)
uv run python main.py --files api_spec.json --auto-approve --output tools.json
```

### CLI Options

| Option | Description |
|--------|-------------|
| `-f, --files PATH` | Path(s) to API specification file(s) (multiple allowed) |
| `-u, --url TEXT` | Root URL to crawl for API documentation |
| `-o, --output PATH` | Output file path (default: `mcp_tools.json`) |
| `--auto-approve` | Automatically select all discovered endpoints (non-interactive) |
| `--example` | Run example workflow with mock data |

### Programmatic Usage

You can also import and use the modules directly:

```python
from utils import build_full_workflow

# Build both graphs with checkpointing
discovery_graph, generation_graph = build_full_workflow()

# Run discovery (runs to completion)
config = {"configurable": {"thread_id": "unique-session-id"}}
input_data = {
    "input": {"files": ["/path/to/spec.json"]},
    "discovery": {}
}

for event in discovery_graph.stream(input_data, config):
    print(event)

# Get discovered endpoints from final state
final_state = discovery_graph.get_state(config)
endpoints = final_state.values.get("discovery", {}).get("endpoints_normalized", [])

# Endpoint selection happens in orchestration layer (not in graph)
# Then pass selected endpoints to Generation Graph
```

---

## Project Structure

```
mcp-gateway-graph-demo/
├── config.py                    # Configuration, LLM setup, constants
├── main.py                      # CLI entry point (using Click)
├── .env                         # Environment variables (not in git)
├── .env.example                 # Environment template
├── models/
│   ├── __init__.py
│   └── schemas.py              # State schemas, Pydantic models
├── discovery/
│   ├── __init__.py
│   ├── nodes.py                # 6 discovery node functions
│   ├── helpers.py              # OpenAPI parsing, LLM extraction, web crawling
│   ├── graph.py                # build_discovery_graph()
│   └── runners.py              # Runner utilities
├── generation/
│   ├── __init__.py
│   ├── nodes.py                # 6 generation node functions
│   ├── helpers.py              # Schema enhancement, vendor extraction, validation
│   ├── graph.py                # build_generation_graph()
│   └── runners.py              # Runner utilities
├── utils/
│   ├── __init__.py
│   ├── workflow.py             # build_full_workflow(), checkpointing
│   └── tools.py                # Utility functions
├── tests/
│   ├── __init__.py
│   ├── test_data.py            # Mock OpenAPI spec generation
│   └── test_workflow.py        # Full workflow test
└── graph-demo.ipynb            # Original notebook (reference only)
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_API_KEY` | Yes | Azure OpenAI API key for LLM operations |
| `AZURE_OPENAI_API_VERSION` | Yes | API version (e.g., "2024-02-15") |
| `AZURE_OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint URL |
| `LANGSMITH_API_KEY` | No | LangSmith API key for tracing |
| `LANGSMITH_TRACING` | No | Enable tracing ("true"/"false") |
| `LANGSMITH_PROJECT` | No | LangSmith project name (default: "mcp-gateway") |

### Constants (config.py)

- `DEFAULT_MODEL = "gpt-4.1"` - LLM model for extraction and generation
- `MAX_CRAWL_PAGES = 20` - Maximum pages to crawl per domain
- `CRAWL_DELAY = 0.5` - Seconds between crawl requests
- `LLM_PAGE_SAMPLE_LENGTH = 3000` - Characters to sample from long pages

---

## Output Format

Generated MCP tools follow a standardized JSON structure:

```json
{
  "name": "EXAMPLE__FLIGHTS__SEARCH",
  "display_name": "Search for available flights",
  "description": "Search for flights based on origin, destination, and dates",
  "tags": ["example", "flights", "v1", "post"],
  "visibility": "public",
  "active": true,
  "protocol": "rest",
  "protocol_data": {
    "method": "POST",
    "path": "/api/v1/flights/search",
    "server_url": "https://api.example.com"
  },
  "parameters": {
    "header": {
      "type": "object",
      "properties": {
        "Authorization": {
          "type": "string",
          "description": "Bearer token for authentication"
        }
      },
      "required": ["Authorization"],
      "visible": ["Authorization"]
    },
    "path": {
      "type": "object",
      "properties": {},
      "required": [],
      "visible": []
    },
    "query": {
      "type": "object",
      "properties": {
        "limit": {
          "type": "integer",
          "description": "Maximum results to return",
          "minimum": 1,
          "maximum": 100,
          "default": 10
        }
      },
      "required": [],
      "visible": ["limit"]
    },
    "body": {
      "type": "object",
      "properties": {
        "origin": {
          "type": "string",
          "description": "Origin airport code",
          "pattern": "^[A-Z]{3}$"
        },
        "destination": {
          "type": "string",
          "description": "Destination airport code",
          "pattern": "^[A-Z]{3}$"
        },
        "date": {
          "type": "string",
          "format": "date",
          "description": "Departure date"
        }
      },
      "required": ["origin", "destination", "date"],
      "visible": ["origin", "destination", "date"]
    }
  },
  "metadata": {
    "source": "openapi",
    "confidence": 0.95
  }
}
```

### Tool Naming Convention

Tools follow the pattern: **`VENDOR__RESOURCE__VERB`** (uppercase)

Examples:
- `STRIPE__PAYMENTS__CREATE`
- `GITHUB__REPOSITORIES__LIST`
- `EXAMPLE__BOOKINGS__DELETE`

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique tool identifier (VENDOR__RESOURCE__VERB) |
| `display_name` | string | Human-readable name for UI display |
| `description` | string | Clear description of tool functionality |
| `tags` | array | [vendor, resource, version, method] |
| `visibility` | string | Always "public" |
| `active` | boolean | Always true |
| `protocol` | string | Always "rest" |
| `protocol_data` | object | Contains method, path, and server_url |
| `parameters` | object | Nested schemas for header/path/query/body |
| `metadata` | object | Source type and confidence score |

---

## Development

### Running Tests

```bash
# Run full workflow test
uv run python tests/test_workflow.py

# Run with example data
uv run python main.py --example
```

### Code Quality

The project uses **Ruff** for code formatting, import sorting, and linting.

```bash
# Format code
uv run ruff format .

# Sort imports and fix issues
uv run ruff check --fix .

# Lint code (check only)
uv run ruff check .
```

### Important Implementation Notes

1. **Pydantic Version Compatibility**:
   - Use `from pydantic import BaseModel, Field` (Pydantic v2)
   - Do NOT use deprecated `langchain_core.pydantic_v1` imports

2. **Azure OpenAI**:
   - This project uses Azure OpenAI, not standard OpenAI
   - Configure all required Azure environment variables

3. **Custom Schema Fields**:
   - The `visible` field is a custom extension for UI rendering
   - It's automatically removed during JSON Schema validation

4. **Checkpointing**:
   - Uses in-memory SQLite by default
   - Can be changed to file-based in `utils/workflow.py`

5. **Type Hints**:
   - All functions include comprehensive type hints
   - Uses Python's `typing` module throughout

---

## Dependencies

Key packages (see `pyproject.toml` for full list):

### Workflow & LLM
- `langgraph>=1.0.1` - Workflow orchestration
- `langchain>=1.0.2` - LLM operations
- `langchain-openai>=1.0.1` - Azure OpenAI integration
- `langgraph-checkpoint-sqlite>=3.0.0` - State persistence

### CLI & Utilities
- `click>=8.1.0` - Modern CLI framework
- `python-dotenv` - Environment variable management

### Data Processing
- `beautifulsoup4>=4.14.2` - HTML/XML parsing for web discovery
- `jsonschema>=4.25.1` - Schema validation
- `pyyaml>=6.0.3` - YAML parsing
- `requests>=2.32.5` - HTTP requests

### Development Tools
- `ruff>=0.14.3` - Code formatting, import sorting, and linting

---

## Learning Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Documentation](https://python.langchain.com/)
- [JSON Schema Specification](https://json-schema.org/)
- [OpenAPI Specification](https://swagger.io/specification/)

---

## License

This is a demo project for educational and reference purposes. Please adapt for your specific use case.

---

## Contributing

This is a demonstration repository. For questions or suggestions, please open an issue.

---

## Disclaimer

**This repository is for demonstration purposes only.** It showcases workflow orchestration patterns with LangGraph and should be adapted and hardened for production use cases. The code demonstrates architectural concepts and may require additional error handling, security considerations, and performance optimizations for real-world applications.

---

<div align="center">

**Built with** [LangGraph](https://langchain-ai.github.io/langgraph/) [LangChain](https://python.langchain.com/) [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service)

</div>
