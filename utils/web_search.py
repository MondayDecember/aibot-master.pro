import asyncio
import logging

import aiohttp
from duckduckgo_search import DDGS

from config import WEB_FETCH_PAGES, WEB_PAGE_MAX_CHARS

logger = logging.getLogger(__name__)

# A regular browser UA - some sites answer 403 to obvious bots/empty agents
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
# Hard cap on downloaded bytes per page - we only need the article text,
# not a 50 MB single-page app bundle
_MAX_PAGE_BYTES = 1_000_000


def _ddg_search(query: str, max_results: int = 3) -> list:
    """Blocking DuckDuckGo search - call via asyncio.to_thread."""
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


def _extract_page_text(html: str, max_chars: int) -> str:
    """Readable text from an HTML page: strip scripts/menus/footers, prefer
    the <main>/<article> node when the page marks one up."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg", "iframe",
                     "header", "footer", "nav", "aside", "form", "button"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = " ".join(main.get_text(" ", strip=True).split())
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "…"
    return text


async def _fetch_page(session: aiohttp.ClientSession, url: str, max_chars: int):
    """Download one result page and extract its text; None on any failure -
    the caller falls back to the search snippet."""
    try:
        async with session.get(url, allow_redirects=True) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if resp.status != 200 or ("html" not in content_type and "text" not in content_type):
                return None
            raw = await resp.content.read(_MAX_PAGE_BYTES)
        html = raw.decode(resp.charset or "utf-8", errors="replace")
        # bs4 parsing is CPU-bound - keep it off the event loop
        text = await asyncio.to_thread(_extract_page_text, html, max_chars)
        return text or None
    except Exception as e:
        logger.warning(f"Page fetch failed for {url}: {e}")
        return None


def perform_web_search(query: str, max_results: int = 3, max_body_chars: int = 300) -> str:
    """
    Snippets-only search (no page visits). Kept for WEB_FETCH_PAGES=0 and
    as the fallback when page fetching fails. Blocking - call via
    asyncio.to_thread. Snippets are capped: local models often run with a
    small context window, and uncapped DDG snippets on top of chat history
    were enough to blow past it with a 400 'exceeds context size' error.
    """
    logger.info(f"Performing web search for: {query}")
    try:
        results = _ddg_search(query, max_results)
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


async def gather_web_context(query: str) -> str:
    """
    Search DuckDuckGo and OPEN the top WEB_FETCH_PAGES result pages, feeding
    their actual text to the model instead of only the ~300-char search
    snippets. Pages that fail to load (paywall, 403, timeout) silently fall
    back to their snippet. WEB_FETCH_PAGES=0 = snippets-only behaviour.
    """
    logger.info(f"Performing web search for: {query}")
    try:
        results = await asyncio.to_thread(_ddg_search, query, 3)
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Error performing web search: {e}"
    if not results:
        return "No web search results found."

    page_texts = []
    if WEB_FETCH_PAGES > 0:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(
            timeout=timeout, headers={"User-Agent": _USER_AGENT}
        ) as session:
            page_texts = await asyncio.gather(*[
                _fetch_page(session, r.get("href", ""), WEB_PAGE_MAX_CHARS)
                for r in results[:WEB_FETCH_PAGES]
            ])

    formatted = "Web Search Results:\n\n"
    for idx, result in enumerate(results, 1):
        page_text = page_texts[idx - 1] if idx - 1 < len(page_texts) else None
        if page_text:
            body = f"Page content: {page_text}"
        else:
            body = (result.get("body") or "No snippet").strip()[:300]
        formatted += f"[{idx}] {result.get('title', 'No Title')}\n"
        formatted += f"Source: {result.get('href', 'No link')}\n{body}\n\n"
    return formatted
