# HTE Hackathon 

## Python

Use python3.12

### Environment Setup

1. Create a `.env` file in the project root:
```bash
export ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
export ANTHROPIC_API_KEY=sk-api-pX-J83ZFK4sVH33L7yB5JCsSD8KA2TXylwAFVagln-54frDjdUxIzOTLe7ZcyADOn-UtRcc4ZuYMRFO-0j7ZcN_gLCqlkX0fkeZ4bFvF8Vzeyeae96WBZ_A
export EXA_API_KEY=your_exa_api_key_here
```

2. Or create a `.env` file:
```env
ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
ANTHROPIC_API_KEY=sk-api-pX-J83ZFK4sVH33L7yB5JCsSD8KA2TXylwAFVagln-54frDjdUxIzOTLe7ZcyADOn-UtRcc4ZuYMRFO-0j7ZcN_gLCqlkX0fkeZ4bFvF8Vzeyeae96WBZ_A
EXA_API_KEY=your_exa_api_key_here
```

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
