import asyncio

from utils import web_search
from utils.web_search import _extract_page_text

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
