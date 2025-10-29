"""Configuration module for MCP Gateway workflows.

This module contains:
- Environment variable loading
- LLM initialization
- Global constants and settings
"""

import os

from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI

# Load environment variables
load_dotenv()

# Model configuration
DEFAULT_MODEL = "gpt-4.1"

# Initialize LLM
llm = AzureChatOpenAI(
    deployment_name=DEFAULT_MODEL,
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ["AZURE_OPENAI_API_VERSION"],
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    temperature=0,
)

# Web crawling settings
MAX_CRAWL_PAGES = 20
CRAWL_THROTTLE_SECONDS = 0.5
SITEMAP_URL_LIMIT = 50

# LLM extraction settings
LLM_CONTENT_TRUNCATE_LENGTH = 8000
LLM_PAGE_SAMPLE_LENGTH = 4000

# Retry settings
MAX_FETCH_RETRIES = 3
FETCH_TIMEOUT_SECONDS = 10

print(f"✅ Configuration loaded: LLM={DEFAULT_MODEL}")
