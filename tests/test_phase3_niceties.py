import asyncio

from handlers.user_handlers import _ROLL_RE
from db.database import init_db, get_custom_prompt, set_custom_prompt


def _roll(expr):
    """Mirror of cmd_roll's parsing for a pure test."""
    import random
    m = _ROLL_RE.match(expr)
    if not m:
        return None
    count = int(m.group(1) or 1)
    sides = int(m.group(2))
    mod = int((m.group(3) or "0").replace(" ", ""))
    rolls = [random.randint(1, sides) for _ in range(count)]
    return rolls, sum(rolls) + mod, count, sides, mod


def test_roll_notation_parsing():
    assert _ROLL_RE.match("2d6")
    assert _ROLL_RE.match("d20+3")
    assert _ROLL_RE.match("d6")
    assert not _ROLL_RE.match("hello")
    assert not _ROLL_RE.match("6")
    for _ in range(50):
        rolls, total, count, sides, mod = _roll("2d6+1")
        assert count == 2 and sides == 6 and mod == 1
        assert all(1 <= r <= 6 for r in rolls)
        assert total == sum(rolls) + 1
    # d20 range
    for _ in range(50):
        rolls, total, *_ = _roll("d20")
        assert 1 <= rolls[0] <= 20


def test_8ball_answers_present():
    from utils.texts import _TEXTS
    for lang in ("en", "ru"):
        answers = _TEXTS[lang]["eightball_answers"].split("\n")
        assert len(answers) >= 5


def test_custom_prompt_roundtrip():
    async def scenario():
        await init_db()
        assert await get_custom_prompt(9500) is None
        await set_custom_prompt(9500, "отвечай кратко")
        assert await get_custom_prompt(9500) == "отвечай кратко"
        await set_custom_prompt(9500, None)  # /setprompt -
        assert await get_custom_prompt(9500) is None
    asyncio.run(scenario())
