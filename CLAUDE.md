# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MCP Gateway: Discovery + Generation LangGraph Workflows**

This project implements two composable LangGraph workflows for the MCP Gateway platform:

1. **DiscoveryGraph** - Discovers API endpoints from uploaded specs or documentation URLs
2. **GenerationGraph** - Generates JSON Draft-07 compliant MCP tool definitions

The system uses LangGraph for workflow orchestration, LangChain for LLM operations, and includes human-in-the-loop interrupt handling for endpoint selection and review.

## Project Structure

The project is organized as a modular Python application:

```
mcp-gateway-graph-demo/
├── config.py                    # Configuration, LLM setup, constants
├── main.py                      # CLI entry point (using Click)
├── models/
│   ├── __init__.py
│   └── schemas.py              # State schemas, Pydantic models
├── discovery/
│   ├── __init__.py
│   ├── nodes.py                # 7 discovery node functions
│   ├── helpers.py              # OpenAPI parsing, LLM extraction, web crawling
│   └── graph.py                # build_discovery_graph()
├── generation/
│   ├── __init__.py
│   ├── nodes.py                # 8 generation node functions
│   ├── helpers.py              # Schema enhancement, vendor extraction, validation
│   └── graph.py                # build_generation_graph()
├── utils/
│   ├── __init__.py
│   └── workflow.py             # build_full_workflow(), checkpointing
├── tests/
│   ├── __init__.py
│   ├── test_data.py            # Mock OpenAPI spec generation
│   └── test_workflow.py        # Full workflow test
└── graph-demo.ipynb            # Original notebook (reference only)
```

## Development Setup

This project uses **uv** for Python package management with Python 3.12+.

### Install Dependencies
```bash
uv sync
```

### Run the CLI
```bash
# Show help
uv run python main.py --help

# Run with OpenAPI spec file
uv run python main.py --files api_spec.json --output tools.json

# Run with multiple files
uv run python main.py --files spec1.json --files spec2.yaml

# Run with URL
uv run python main.py --url https://api.example.com/docs --output tools.json

# Run example workflow
uv run python main.py --example

# Auto-approve mode (non-interactive)
uv run python main.py --files api_spec.json --auto-approve --output tools.json
```

### Run Tests
```bash
uv run python tests/test_workflow.py
```

### Work with the Jupyter Notebook
The original implementation is preserved in `graph-demo.ipynb` for reference. The production code is now in the modular Python files. Use Jupyter or VS Code's notebook interface to explore the notebook.

## Environment Configuration

Required environment variables (configured in `.env`):
- `AZURE_OPENAI_API_KEY` - Required for LLM operations
- `AZURE_OPENAI_API_VERSION` - API version (e.g., "2024-02-15")
- `AZURE_OPENAI_ENDPOINT` - Azure endpoint URL
- `LANGSMITH_API_KEY` - Optional, for LangSmith tracing
- `LANGSMITH_TRACING` - Set to "true" to enable tracing
- `LANGSMITH_PROJECT` - Project name for LangSmith (default: "mcp-gateway")

## Architecture

### Two-Graph Workflow

**DiscoveryGraph Flow:**
```
classify_input → parse_files → discover_from_web → endpoint_extractor
→ normalize_and_dedup → summarize_for_ui → interrupt_for_selection → END
```

**GenerationGraph Flow:**
```
plan_work → fetch_docs → schema_synthesis → compose_tool → validate
→ aggregate_tools → interrupt_for_review → finalize → END
```

### Key Architectural Patterns

1. **State Management**: Uses TypedDict for state schemas (`DiscoveryState`, `GenerationState`)
2. **Checkpointing**: SqliteSaver provides state persistence and resume capability
3. **Interrupts**: Human-in-the-loop decision points use `interrupt()` from LangGraph
4. **Dual Input Sources**: Handles both file-based (OpenAPI specs) and URL-based (web crawling) discovery
5. **LLM + Regex Hybrid**: Combines regex pattern matching with LLM extraction for robustness

### State Structure

**DiscoveryState:**
- `input`: Input configuration (files or root_url)
- `discovery`: Discovered endpoints and catalog
- `selection`: User-selected endpoint IDs

**GenerationState:**
- `selection`: Selected endpoints from Discovery
- `generation`: Work items, generated tools, and errors

### Tool Naming Convention

Generated MCP tools follow the pattern: `VENDOR__RESOURCE__VERB`

Examples:
- `EXAMPLE__FLIGHTS__SEARCH`
- `EXAMPLE__BOOKINGS__GET`
- `EXAMPLE__BOOKINGS__DELETE`

## Important Implementation Details

### Pydantic Version Compatibility

**IMPORTANT**: This codebase was created with `langchain_core.pydantic_v1` imports, which are now deprecated in LangChain v0.3+.

When working with Pydantic models:
- Use `from pydantic import BaseModel, Field` (Pydantic v2)
- OR use `from pydantic.v1 import BaseModel, Field` for v1 compatibility

Do not use `from langchain_core.pydantic_v1 import ...` as this module has been removed.

### Endpoint Extraction Strategy

The system uses a three-pronged approach:
1. **OpenAPI Parsing**: Direct extraction from structured specs
2. **Regex Patterns**: Pattern matching for common API formats
3. **LLM Extraction**: Structured extraction from unstructured docs using `JsonOutputParser`

### Web Discovery Features

- Attempts sitemap.xml discovery first for efficient crawling
- Falls back to breadth-first crawl with respectful throttling (0.5s delay)
- Respects domain boundaries (doesn't crawl external links)
- Limits crawl to 20 pages by default

### Schema Generation

Schemas are generated using LLM with explicit requirements for:
- JSON Schema Draft-07 compliance
- Nested organization (headers, path, query, body)
- Type constraints and formats
- Enum values for restricted fields
- Required field specifications

### Validation

All generated tools are validated using `jsonschema.Draft7Validator.check_schema()` before finalization.

## Module Organization

### config.py
- Loads environment variables using `python-dotenv`
- Initializes Azure OpenAI LLM (AzureChatOpenAI)
- Defines global constants for crawling, retry settings, and LLM parameters
- Configuration: `DEFAULT_MODEL = "gpt-4.1"`

### models/
- **schemas.py**: TypedDict state schemas (`DiscoveryState`, `GenerationState`) and Pydantic models (`EndpointInfo`, `EndpointList`)

### discovery/
- **nodes.py**: 7 node functions (classify_input, parse_files, discover_from_web, endpoint_extractor, normalize_and_dedup, summarize_for_ui, interrupt_for_selection)
- **helpers.py**: Helper functions for OpenAPI parsing, LLM extraction, web crawling (sitemap + simple crawl), confidence calculation
- **graph.py**: `build_discovery_graph()` function that creates the workflow

### generation/
- **nodes.py**: 8 node functions (plan_work, fetch_docs, schema_synthesis, compose_tool, validate, aggregate_tools, interrupt_for_review, finalize)
- **helpers.py**: Schema enhancement, display name generation, vendor/resource/verb extraction, validation utilities
- **graph.py**: `build_generation_graph()` function that creates the workflow

### utils/
- **workflow.py**: `build_full_workflow()` combines both graphs with SqliteSaver checkpointing

### tests/
- **test_data.py**: Mock OpenAPI spec generation and cleanup utilities
- **test_workflow.py**: Complete end-to-end test suite

### main.py
- CLI interface using **Click** (not argparse)
- Commands: `--files`, `--url`, `--output`, `--auto-approve`, `--example`
- Orchestrates discovery and generation workflows
- Handles interrupt resumption for human-in-the-loop

## Testing Pattern

The test suite (`tests/test_workflow.py`) includes:

1. Creating mock API specifications
2. Running Discovery Graph to interrupt
3. Simulating user selection
4. Resuming with selected endpoints
5. Running Generation Graph to interrupt
6. Simulating user approval
7. Validating final output

Run tests:
```bash
uv run python tests/test_workflow.py
```

Or run the example workflow via CLI:
```bash
uv run python main.py --example
```

## Common Operations

### Using the CLI
The primary way to interact with the system is through the CLI:

```bash
# Basic usage
uv run python main.py --files api_spec.json

# With custom output
uv run python main.py --files api_spec.json --output my_tools.json

# Auto-approve (skip confirmations)
uv run python main.py --files api_spec.json --auto-approve
```

### Programmatic Usage
You can also import and use the modules directly:

```python
from utils import build_full_workflow
from discovery import build_discovery_graph
from generation import build_generation_graph

# Build both graphs
discovery_graph, generation_graph = build_full_workflow()

# Or build individually
discovery_graph = build_discovery_graph().compile(
    checkpointer=checkpointer,
    interrupt_before=["interrupt_for_selection"]
)
```

### Running Discovery Only
```python
from utils import build_full_workflow

discovery_graph, _ = build_full_workflow()
config = {"configurable": {"thread_id": "unique-id"}}
input_data = {"input": {"files": ["/path/to/spec.json"]}, "discovery": {}, "selection": {}}

for event in discovery_graph.stream(input_data, config):
    print(event)
```

### Resuming After Interrupt
```python
# Update state with user input
discovery_graph.update_state(
    config,
    {"selection": {"endpoint_ids": ["id1", "id2"]}},
    as_node="interrupt_for_selection"
)

# Continue execution
for event in discovery_graph.stream(None, config):
    pass
```

### Composing Both Graphs
The graphs are designed to be composed - Discovery output feeds directly into Generation input via the `selection` state. The CLI (`main.py`) demonstrates this pattern.

## Dependencies

Key packages (see `pyproject.toml` for full list):
- **Workflow & LLM**:
  - `langgraph>=1.0.1` - Workflow orchestration
  - `langchain>=1.0.2` - LLM operations
  - `langchain-openai>=1.0.1` - Azure OpenAI integration
  - `langgraph-checkpoint-sqlite>=3.0.0` - State persistence
- **CLI & Utilities**:
  - `click>=8.1.0` - Modern CLI framework
  - `python-dotenv` (via `dotenv>=0.9.9`) - Environment variable management
- **Data Processing**:
  - `beautifulsoup4>=4.14.2` - HTML/XML parsing for web discovery
  - `jsonschema>=4.25.1` - Schema validation
  - `pyyaml>=6.0.3` - YAML parsing
  - `requests>=2.32.5` - HTTP requests
- **Development Tools**:
  - `black>=25.9.0` - Code formatting
  - `isort>=7.0.0` - Import sorting
  - `flake8>=7.3.0` - Linting

## Output Format

Generated MCP tools include:
- `name`: Following VENDOR__RESOURCE__VERB convention (uppercase)
- `display_name`: Human-readable display name (generated from description or name)
- `description`: Human-readable description
- `parameters`: JSON Schema Draft-07 compliant parameter schema (with custom `visible` arrays)
- `tags`: Array of [vendor, resource, version, method]
- `visibility`: "public" (default)
- `active`: true (default)
- `protocol`: "rest"
- `protocol_data`: Object with `method`, `path`, and `server_url`
- `metadata`: Object with `source` (openapi/llm/regex) and `confidence` score

Example tool structure:
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
    "path": "/flights/search",
    "server_url": "https://api.example.com/v1"
  },
  "parameters": {
    "header": { "type": "object", "properties": {}, "required": [], "visible": [] },
    "path": { "type": "object", "properties": {}, "required": [], "visible": [] },
    "query": { "type": "object", "properties": {...}, "required": [...], "visible": [...] },
    "body": { "type": "object", "properties": {...}, "required": [...], "visible": [...] }
  },
  "metadata": {
    "source": "openapi",
    "confidence": 0.85
  }
}
```

## CLI Usage

The main CLI provides several commands via Click:

```bash
# Get help
python main.py --help

# Options:
#   -f, --files PATH     Path(s) to API specification file(s) (multiple allowed)
#   -u, --url TEXT       Root URL to crawl for API documentation
#   -o, --output PATH    Output file path (default: mcp_tools.json)
#   --auto-approve       Automatically approve all endpoints and tools
#   --example            Run example workflow with mock data
```

## Important Notes

1. **Azure OpenAI**: This project uses Azure OpenAI, not standard OpenAI. Configure the required Azure environment variables.
2. **Click CLI**: The CLI uses Click (not argparse) for a modern, decorator-based interface.
3. **Modular Structure**: All code is organized into packages. Import from `config`, `models`, `discovery`, `generation`, `utils`, or `tests` as needed.
4. **Type Hints**: All functions include comprehensive type hints using Python's `typing` module.
5. **Custom Schema Fields**: The `visible` field is a custom extension used for UI rendering. It's removed during validation.
6. **Checkpointing**: Uses in-memory SQLite by default. Can be changed to file-based in `utils/workflow.py`.
7. **Interrupt Handling**: Both graphs have interrupt points. The CLI automatically handles resumption.
