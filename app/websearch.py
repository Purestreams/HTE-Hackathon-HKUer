
"""
Exa API Web Search Module
Configuration: Auto search type with balanced relevance and speed (~1 second)
Content: Compact highlights (max 4000 characters)
"""

import os
import json
from typing import Optional, List, Dict
from dotenv import load_dotenv
from exa_py import Exa

# Load environment variables from .env file
load_dotenv()

# Initialize Exa client with API key from environment variable
EXA_API_KEY = os.environ.get("EXA_API_KEY")
if not EXA_API_KEY:
    raise ValueError(
        "EXA_API_KEY environment variable not set. "
        "Please set it in your .env file or as an environment variable."
    )

exa = Exa(api_key=EXA_API_KEY)


# ============================================================================
# Basic Web Search
# ============================================================================

def web_search(
    query: str,
    num_results: int = 10,
    search_type: str = "auto",
    include_highlights: bool = True,
    max_characters: int = 4000,
) -> List[Dict]:
    """
    Perform a web search using Exa API.
    
    Args:
        query: Search query
        num_results: Number of results to return (default: 10)
        search_type: Search type - "auto" for balanced, "fast" for speed (default: "auto")
        include_highlights: Include text highlights in results (default: True)
        max_characters: Max characters for highlights (default: 4000)
    
    Returns:
        List of search results with title, URL, and optional highlights
    """
    try:
        contents = {}
        if include_highlights:
            contents = {"highlights": {"max_characters": max_characters}}
        
        results = exa.search(
            query=query,
            type=search_type,
            num_results=num_results,
            contents=contents if contents else None # type: ignore
        )
        
        # Format results
        formatted_results = []
        for result in results.results:
            formatted_result = {
                "title": result.title,
                "url": result.url,
                "id": result.id,
            }
            if include_highlights and hasattr(result, "highlights"):
                formatted_result["highlights"] = result.highlights
            formatted_results.append(formatted_result)
        
        return formatted_results
    
    except Exception as e:
        print(f"Search error: {e}")
        return []


# ============================================================================
# Specialized Search Functions
# ============================================================================

def search_news(query: str, num_results: int = 10) -> List[Dict]:
    """Search for news articles."""
    try:
        results = exa.search(
            query=query,
            category="news",
            type="auto",
            num_results=num_results,
            contents={"highlights": {"max_characters": 4000}}
        )
        return [
            {
                "title": r.title,
                "url": r.url,
                "highlights": getattr(r, "highlights", None),
            }
            for r in results.results
        ]
    except Exception as e:
        print(f"News search error: {e}")
        return []


def search_research_papers(query: str, num_results: int = 10) -> List[Dict]:
    """Search for academic research papers."""
    try:
        results = exa.search(
            query=query,
            category="research paper",
            type="auto",
            num_results=num_results,
            contents={"highlights": {"max_characters": 4000}}
        )
        return [
            {
                "title": r.title,
                "url": r.url,
                "highlights": getattr(r, "highlights", None),
            }
            for r in results.results
        ]
    except Exception as e:
        print(f"Research paper search error: {e}")
        return []


def search_people(query: str, num_results: int = 10) -> List[Dict]:
    """Search for people by role or expertise."""
    try:
        results = exa.search(
            query=query,
            category="people",
            type="auto",
            num_results=num_results,
            contents={"highlights": {"max_characters": 4000}}
        )
        return [
            {
                "title": r.title,
                "url": r.url,
                "highlights": getattr(r, "highlights", None),
            }
            for r in results.results
        ]
    except Exception as e:
        print(f"People search error: {e}")
        return []


def search_companies(query: str, num_results: int = 10) -> List[Dict]:
    """Search for companies by industry or attributes."""
    try:
        results = exa.search(
            query=query,
            category="company",
            type="auto",
            num_results=num_results,
        )
        return [
            {
                "title": r.title,
                "url": r.url,
            }
            for r in results.results
        ]
    except Exception as e:
        print(f"Company search error: {e}")
        return []


# ============================================================================
# Function Calling / Tool Use for AI Agents
# ============================================================================

def get_exa_search_tool() -> Dict:
    """
    Get the Exa search tool definition for OpenAI/Anthropic function calling.
    
    Returns:
        Tool definition for function calling
    """
    return {
        "name": "exa_search",
        "description": "Search the web for current information.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query"
                }
            },
            "required": ["query"]
        }
    }


def exa_search_tool(query: str) -> str:
    """
    Tool function for AI agent function calling.
    
    Args:
        query: Search query
    
    Returns:
        Formatted search results as string
    """
    results = web_search(query=query, num_results=10)
    return "\n".join([f"{r['title']}: {r['url']}" for r in results])


# ============================================================================
# Example Usage
# ============================================================================

if __name__ == "__main__":
    # Example 1: Basic web search
    print("=" * 60)
    print("Example 1: Basic Web Search")
    print("=" * 60)
    results = web_search("latest developments in AI safety research", num_results=5)
    for result in results:
        print(f"\nTitle: {result['title']}")
        print(f"URL: {result['url']}")
        if "highlights" in result:
            print(f"Highlights: {result['highlights']}")
    
    # Example 2: News search
    print("\n" + "=" * 60)
    print("Example 2: News Search")
    print("=" * 60)
    news_results = search_news("OpenAI announcements", num_results=5)
    for result in news_results:
        print(f"\nTitle: {result['title']}")
        print(f"URL: {result['url']}")
    
    # Example 3: Research papers
    print("\n" + "=" * 60)
    print("Example 3: Research Papers")
    print("=" * 60)
    papers = search_research_papers("transformer architecture improvements", num_results=5)
    for result in papers:
        print(f"\nTitle: {result['title']}")
        print(f"URL: {result['url']}")

