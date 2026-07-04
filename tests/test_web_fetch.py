import asyncio

from utils import web_search
from utils.web_search import _extract_page_text, _is_public_url


# --- SSRF guard ---

def test_ssrf_guard_blocks_internal_targets(monkeypatch):
    # Don't hit real DNS: map every hostname to whatever ip the test wants
    def fake_getaddrinfo(host, port, **kwargs):
        table = {
            "example.com": "93.184.216.34",     # public
            "ollama": "172.18.0.2",             # docker private
            "redis": "10.0.0.5",                # private
            "router.local": "192.168.1.1",      # private
            "metadata": "169.254.169.254",      # cloud metadata (link-local)
            "loop": "127.0.0.1",                # loopback
        }
        ip = table.get(host)
        if ip is None:
            raise __import__("socket").gaierror("no such host")
        return [(2, 1, 6, "", (ip, port or 80))]

    monkeypatch.setattr(web_search.socket, "getaddrinfo", fake_getaddrinfo)

    assert web_search._is_public_url("https://example.com/page")
    assert not web_search._is_public_url("http://ollama:11434/api/tags")
    assert not web_search._is_public_url("http://redis:6379")
    assert not web_search._is_public_url("http://router.local/admin")
    assert not web_search._is_public_url("http://metadata/latest/meta-data/")
    assert not web_search._is_public_url("http://loop:7861/generate")


def test_fetch_page_blocks_before_connecting(monkeypatch):
    # _fetch_page must reject a non-public URL WITHOUT ever calling session.get
    monkeypatch.setattr(web_search, "_is_public_url", lambda url: False)

    class _Boom:
        def get(self, *a, **k):
            raise AssertionError("session.get must not be called for a blocked URL")

    result = asyncio.run(web_search._fetch_page(_Boom(), "http://ollama:11434", 100))
    assert result is None


def test_ssrf_guard_rejects_bad_schemes_and_literals():
    # non-http schemes
    assert not _is_public_url("file:///etc/passwd")
    assert not _is_public_url("ftp://example.com/x")
    assert not _is_public_url("not a url")
    # raw private IP literals resolve to themselves
    assert not _is_public_url("http://127.0.0.1:6379")
    assert not _is_public_url("http://192.168.0.1/")
    assert not _is_public_url("http://[::1]:8080/")

_SAMPLE_HTML = """
<html><head><title>Test</title><style>body{color:red}</style>
<script>alert("junk")</script></head>
<body>
<nav>Меню Главная Контакты</nav>
<header>Шапка сайта</header>
<main>
  <h1>Погода в Томске</h1>
  <p>Сегодня в Томске +25, солнечно.</p>
  <p>Завтра ожидается дождь.</p>
</main>
<footer>Подвал © 2026</footer>
</body></html>
"""


def test_extracts_main_content_only():
    text = _extract_page_text(_SAMPLE_HTML, 500)
    assert "Погода в Томске" in text
    assert "+25" in text and "дождь" in text
    # chrome/junk stripped
    assert "alert" not in text
    assert "Меню" not in text
    assert "Подвал" not in text


def test_extraction_respects_char_cap():
    text = _extract_page_text(_SAMPLE_HTML, 30)
    assert len(text) <= 31  # cap + ellipsis


def test_extraction_survives_broken_html():
    text = _extract_page_text("<div><p>обрыв <b>тега", 100)
    assert "обрыв" in text


def test_gather_falls_back_to_snippets_when_pages_fail(monkeypatch):
    monkeypatch.setattr(
        web_search, "_ddg_search",
        lambda q, n=3: [
            {"title": "T1", "href": "http://a", "body": "snippet one"},
            {"title": "T2", "href": "http://b", "body": "snippet two"},
        ],
    )

    async def failing_fetch(session, url, max_chars):
        return None

    monkeypatch.setattr(web_search, "_fetch_page", failing_fetch)
    monkeypatch.setattr(web_search, "WEB_FETCH_PAGES", 2)

    result = asyncio.run(web_search.gather_web_context("query"))
    assert "snippet one" in result and "snippet two" in result
    assert "http://a" in result


def test_gather_uses_page_text_when_available(monkeypatch):
    monkeypatch.setattr(
        web_search, "_ddg_search",
        lambda q, n=3: [{"title": "T1", "href": "http://a", "body": "short snippet"}],
    )

    async def ok_fetch(session, url, max_chars):
        return "полный текст страницы про погоду"

    monkeypatch.setattr(web_search, "_fetch_page", ok_fetch)
    monkeypatch.setattr(web_search, "WEB_FETCH_PAGES", 1)

    result = asyncio.run(web_search.gather_web_context("query"))
    assert "полный текст страницы" in result
    assert "short snippet" not in result
