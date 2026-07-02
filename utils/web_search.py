import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

def perform_web_search(query: str, max_results: int = 3, max_body_chars: int = 300) -> str:
    """
    Perform a web search using DDGS and return a formatted string of results.
    Snippets are capped at max_body_chars - local models often run with a
    small context window (e.g. 4096 tokens), and uncapped DDG snippets on
    top of chat history + system prompt were enough to blow past it and
    fail the whole request with a 400 'exceeds context size' error.
    """
    logger.info(f"Performing web search for: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return "No web search results found."

        formatted_results = "Web Search Results:\n\n"
        for idx, result in enumerate(results, 1):
            body = (result.get('body') or 'No snippet').strip()
            if len(body) > max_body_chars:
                body = body[:max_body_chars].rstrip() + "…"
            formatted_results += f"[{idx}] {result.get('title', 'No Title')}\n"
            formatted_results += f"{body}\n"
            formatted_results += f"Source: {result.get('href', 'No link')}\n\n"

        return formatted_results
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Error performing web search: {e}"
