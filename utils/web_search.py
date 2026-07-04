import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import aiohttp
from yarl import URL
from duckduckgo_search import DDGS

from config import WEB_FETCH_PAGES, WEB_PAGE_MAX_CHARS

logger = logging.getLogger(__name__)

# SSRF guard. Result URLs (and their redirect targets) are attacker-influenced
# - a malicious page or a "site:192.168.1.1" style query could point the
# fetcher at internal services reachable from inside the docker network
# (ollama, redis, the router admin panel, cloud metadata at 169.254.169.254).
# We resolve the host and refuse any address that isn't publicly routable.
_MAX_REDIRECTS = 3


def _is_public_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        return False
    if not infos:
        return False
    for *_, sockaddr in infos:
        try:
            ip = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return False
        # Blocks private, loopback, link-local (incl. cloud metadata),
        # reserved, multicast and unspecified addresses.
        if not ip.is_global or ip.is_multicast:
            return False
    return True

# Last line of defense against context-window overflow: WEB_FETCH_PAGES x
# WEB_PAGE_MAX_CHARS can add up to ~4300 chars on its own (2 pages x 2000
# chars + a third result's snippet) - on top of chat history and the system
# prompt that was enough to blow a 4096-token model context and fail the
# whole request with a 400 'exceeds context size' error. This caps the
# *total* assembled context regardless of how those two settings are tuned.
MAX_TOTAL_WEB_CONTEXT_CHARS = 2500

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
    the caller falls back to the search snippet. Redirects are followed
    manually so every hop is re-checked against the SSRF guard (a public URL
    that 302s to an internal one would otherwise slip through)."""
    try:
        for _ in range(_MAX_REDIRECTS + 1):
            if not _is_public_url(url):
                logger.warning(f"Blocked non-public URL in web fetch: {url}")
                return None
            async with session.get(url, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        return None
                    url = str(resp.url.join(URL(location)))
                    continue
                content_type = resp.headers.get("Content-Type", "")
                if resp.status != 200 or ("html" not in content_type and "text" not in content_type):
                    return None
                raw = await resp.content.read(_MAX_PAGE_BYTES)
                html = raw.decode(resp.charset or "utf-8", errors="replace")
                # bs4 parsing is CPU-bound - keep it off the event loop
                text = await asyncio.to_thread(_extract_page_text, html, max_chars)
                return text or None
        logger.warning(f"Too many redirects fetching {url}")
        return None
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
    if len(formatted) > MAX_TOTAL_WEB_CONTEXT_CHARS:
        formatted = formatted[:MAX_TOTAL_WEB_CONTEXT_CHARS].rstrip() + "…"
    return formatted
