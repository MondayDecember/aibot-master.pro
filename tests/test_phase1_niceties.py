import asyncio

from task_queue.worker import _markdown_to_telegram_html
from handlers.user_handlers import _dice_result
from utils import texts
from utils.texts import t, set_current_language
from db.database import (
    init_db, add_message, get_history, start_new_session,
    get_user_language, set_user_language,
)


# --- code blocks (21) ---

def test_fenced_code_becomes_pre_and_is_escaped():
    out = _markdown_to_telegram_html("вот код:\n```python\nif a < b and c > d:\n    x = a & b\n```")
    assert "<pre>" in out and "</pre>" in out
    # angle brackets / ampersand inside code are escaped, not rendered as tags
    assert "&lt;" in out and "&gt;" in out and "&amp;" in out
    # markdown inside the fence is NOT processed
    assert "**" not in out  # (no bold markers introduced)


def test_markdown_outside_fence_still_works():
    out = _markdown_to_telegram_html("**жирный** и `код`")
    assert "<b>жирный</b>" in out
    assert "<code>код</code>" in out


# --- dice (22) ---

def test_dice_default_is_1_to_6():
    for _ in range(50):
        r = _dice_result(None)
        n = int(r.split()[-1])
        assert 1 <= n <= 6


def test_dice_custom_sides_and_coin_and_choice():
    for _ in range(50):
        assert 1 <= int(_dice_result("20").split()[-1]) <= 20
    coin = _dice_result("coin")
    assert coin.startswith("🪙")
    choice = _dice_result("кофе, чай, какао")
    assert any(x in choice for x in ("кофе", "чай", "какао"))


# --- per-user language (14) ---

def test_t_follows_current_language():
    set_current_language("en")
    assert t("cleared") == texts._TEXTS["en"]["cleared"]
    set_current_language("ru")
    assert t("cleared") == texts._TEXTS["ru"]["cleared"]
    # unknown code -> ignored, falls back to global default
    set_current_language("xx")
    assert t("cleared") in (texts._TEXTS["en"]["cleared"], texts._TEXTS["ru"]["cleared"])
    set_current_language(None)


def test_language_db_roundtrip():
    async def scenario():
        await init_db()
        assert await get_user_language(9100) is None
        await set_user_language(9100, "en")
        assert await get_user_language(9100) == "en"
    asyncio.run(scenario())


# --- /new session boundary (12) ---

def test_new_session_hides_old_history_but_keeps_rows():
    async def scenario():
        await init_db()
        uid = 9200
        await add_message(uid, "user", "старое 1")
        await add_message(uid, "assistant", "старое 2")
        assert len(await get_history(uid, limit=50)) == 2
        await start_new_session(uid)
        # context is now empty...
        assert await get_history(uid, limit=50) == []
        # ...but new messages show up
        await add_message(uid, "user", "новое")
        hist = await get_history(uid, limit=50)
        assert [m["content"] for m in hist] == ["новое"]
    asyncio.run(scenario())
