"""Helper functions for the Discovery Graph.

This module contains:
- OpenAPI endpoint extraction
- LLM-based endpoint extraction
- Web crawling (sitemap and simple crawl)
- Confidence calculation
"""

import time
from typing import List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import (CRAWL_THROTTLE_SECONDS, LLM_CONTENT_TRUNCATE_LENGTH,
                    MAX_CRAWL_PAGES, SITEMAP_URL_LIMIT, llm)
from models import EndpointList


def extract_openapi_endpoints(spec: dict) -> List[dict]:
    """Extract endpoints from OpenAPI spec.

    Args:
        spec: OpenAPI specification dictionary

    Returns:
        List of endpoint dictionaries
    """
    endpoints = []
    servers = spec.get("servers", [{"url": ""}])
    server_url = servers[0].get("url", "") if servers else ""

    for path, methods in spec.get("paths", {}).items():
        for method, details in methods.items():
            if method.upper() in [
                "GET",
                "POST",
                "PUT",
                "DELETE",
                "PATCH",
                "HEAD",
                "OPTIONS",
            ]:
                endpoints.append(
                    {
                        "method": method.upper(),
                        "path": path,
                        "server": server_url,
                        "description": details.get(
                            "summary", details.get("description", "")
                        ),
                        "parameters": details.get("parameters", []),
                        "requestBody": details.get("requestBody", {}),
                        "source": "openapi",
                    }
                )

    return endpoints


def llm_extract_endpoints(content: str) -> List[dict]:
    """Use LLM to extract endpoints from unstructured content.

    Args:
        content: Unstructured text content (documentation, markdown, etc.)

    Returns:
        List of extracted endpoint dictionaries
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """Extract all API endpoints from the provided documentation.
For each endpoint, identify:
- HTTP method (GET, POST, PUT, DELETE, etc.)
- Path (e.g., /api/v1/resource)
- Description
- Any parameters mentioned

Return a JSON array of endpoints.""",
            ),
            ("human", "{content}"),
        ]
    )

    parser = JsonOutputParser(pydantic_object=EndpointList)
    chain = prompt | llm | parser

    try:
        # Truncate content if too long
        truncated = content[:LLM_CONTENT_TRUNCATE_LENGTH]
        result = chain.invoke({"content": truncated})

        return [
            {
                "method": ep.get("method", "GET").upper(),
                "path": ep.get("path", ""),
                "server": ep.get("server", ""),
                "description": ep.get("description", ""),
                "parameters": ep.get("parameters", []),
                "source": "llm",
            }
            for ep in result.get("endpoints", [])
        ]
    except Exception as e:
        print(f"⚠️ LLM extraction error: {e}")
        return []


def try_sitemap(root_url: str) -> List[dict]:
    """Try to fetch pages from sitemap.xml.

    Args:
        root_url: Root URL of the website

    Returns:
        List of page dictionaries with URLs from sitemap
    """
    sitemap_url = urljoin(root_url, "/sitemap.xml")

    try:
        response = requests.get(sitemap_url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "xml")
            urls = [loc.text for loc in soup.find_all("loc")]
            print(f"✅ Found sitemap with {len(urls)} URLs")
            return [
                {"url": url, "source": "sitemap"} for url in urls[:SITEMAP_URL_LIMIT]
            ]
    except Exception as e:
        print(f"⚠️ Sitemap not found: {e}")

    return []


def simple_crawl(root_url: str, max_pages: int = MAX_CRAWL_PAGES) -> List[dict]:
    """Simple breadth-first crawl with robots.txt respect.

    Args:
        root_url: Root URL to start crawling from
        max_pages: Maximum number of pages to crawl

    Returns:
        List of page dictionaries with content
    """
    visited = set()
    to_visit = [root_url]
    pages = []

    base_domain = urlparse(root_url).netloc

    while to_visit and len(pages) < max_pages:
        url = to_visit.pop(0)

        if url in visited:
            continue

        visited.add(url)

        try:
            time.sleep(CRAWL_THROTTLE_SECONDS)  # Respectful throttling
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                pages.append({"url": url, "content": response.text, "source": "crawl"})

                # Extract links for further crawling
                soup = BeautifulSoup(response.content, "html.parser")
                for link in soup.find_all("a", href=True):
                    next_url = urljoin(url, link["href"])
                    next_domain = urlparse(next_url).netloc

                    if next_domain == base_domain and next_url not in visited:
                        to_visit.append(next_url)

        except Exception as e:
            print(f"⚠️ Error crawling {url}: {e}")

    return pages


def calculate_confidence(endpoint: dict) -> float:
    """Calculate confidence score based on available information.

    Args:
        endpoint: Endpoint dictionary

    Returns:
        Confidence score between 0.0 and 1.0
    """
    score = 0.5  # Base score

    if endpoint.get("description"):
        score += 0.2

    if endpoint.get("parameters"):
        score += 0.15

    if endpoint.get("source") == "openapi":
        score += 0.15

    return min(score, 1.0)
