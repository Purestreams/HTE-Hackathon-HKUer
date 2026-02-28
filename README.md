# HTE Hackathon 

## Notion Board

https://www.notion.so/HTE-Topics-31512e50c12980678949f994815c84be?source=copy_link

### Environment Setup

1. Create a `.env` file (do not commit it) or export env vars in your shell.

2. Example `.env` (copy from `.env.example`):
```env
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
ANTHROPIC_API_KEY=your_anthropic_key_here
EXA_API_KEY=your_exa_key_here
ARK_API_KEY=your_ark_key_here
```

Security note: never put real API keys in the repo (README, code, or committed `.env`).

## Web Search Module

The `websearch.py` module provides integration with **Exa API** for real-time web search:

### Features
- **Auto search type**: Balanced relevance and speed (~1 second)
- **Compact content**: Highlights only (max 4000 characters)
- **Multiple search categories**: News, research papers, people, companies
- **Function calling support**: Compatible with OpenAI and Anthropic agents

### Quick Start

```python
from app.websearch import web_search

# Basic web search
results = web_search("latest AI safety research")
for result in results:
    print(result['title'], result['url'])

# Search specific categories
from app.websearch import search_news, search_research_papers
news = search_news("OpenAI announcements", num_results=5)
papers = search_research_papers("transformer improvements", num_results=10)
```

### Configuration
- **Search Type**: `auto` (balanced) or `fast` (speed-focused)
- **Content**: Highlights limited to 4000 characters for cost efficiency
- **API Key**: Set `EXA_API_KEY` in environment variables

See `.env.example` for environment variable template.
