import asyncio
import time
from types import SimpleNamespace

import utils.reminders as rem
from db.database import (
    init_db, add_reminder, get_due_reminders, list_reminders,
    delete_reminder, mark_reminder_sent,
)
from utils.reminders import is_reminder_request, _extract_json, parse_reminder, format_due


# --- trigger detection ---

def test_trigger_detection():
    assert is_reminder_request("напомни завтра в 15:00 проверить сервер")
    assert is_reminder_request("Напомнить в пятницу про сертификаты")
    assert is_reminder_request("remind me tomorrow to call")
    assert is_reminder_request("поставь напоминание на 9 утра")
    # notes/alarms phrasings (real complaint: this one used to fall
    # through to the LLM which claimed it can't set notes)
    assert is_reminder_request("Поставь пожалуйста заметку на 16:00 чтобы я пошёл погулять")
    assert is_reminder_request("запиши мне заметку купить хлеб вечером")
    assert is_reminder_request("сделай будильник на 7 утра")
    # ordinary chat must not trigger
    assert not is_reminder_request("он мне напомнил про встречу")
    assert not is_reminder_request("ты поставила напоминание, чтобы я пошёл погулять")
    assert not is_reminder_request("посоветуй фильм на вечер")
    assert not is_reminder_request("")
    assert not is_reminder_request(None)


# --- json extraction ---

def test_extract_json_tolerates_noise():
    assert _extract_json('Sure! {"text": "x", "datetime": "2030-01-01 09:00"} done') == {
        "text": "x", "datetime": "2030-01-01 09:00"
    }
    assert _extract_json("no json here") is None
    assert _extract_json(None) is None


# --- llm parsing with a faked client ---

def _fake_client(reply_content):
    async def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply_content))]
        )
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_parse_reminder_happy_path(monkeypatch):
    monkeypatch.setattr(rem, "client", _fake_client(
        '{"text": "проверить сервер", "datetime": "2030-06-01 15:00", "repeat": "none"}'
    ))
    result = asyncio.run(parse_reminder("напомни 1 июня 2030 в 15:00 проверить сервер"))
    assert result is not None
    text, due_ts, repeat = result
    assert text == "проверить сервер"
    assert repeat == "none"
    assert format_due(due_ts).startswith("01.06.2030 15:00")


def test_parse_reminder_recurring(monkeypatch):
    monkeypatch.setattr(rem, "client", _fake_client(
        '{"text": "таблетки", "datetime": "2030-06-01 09:00", "repeat": "daily"}'
    ))
    _, _, repeat = asyncio.run(parse_reminder("напоминай каждый день в 9 про таблетки"))
    assert repeat == "daily"
    # unknown/garbage repeat value is sanitised to "none"
    monkeypatch.setattr(rem, "client", _fake_client(
        '{"text": "x", "datetime": "2030-06-01 09:00", "repeat": "sometimes"}'
    ))
    assert asyncio.run(parse_reminder("напомни"))[2] == "none"


def test_parse_reminder_rejects_past_and_errors(monkeypatch):
    monkeypatch.setattr(rem, "client", _fake_client(
        '{"text": "x", "datetime": "2001-01-01 09:00"}'
    ))
    assert asyncio.run(parse_reminder("напомни вчера")) is None

    monkeypatch.setattr(rem, "client", _fake_client('{"error": "no_time"}'))
    assert asyncio.run(parse_reminder("напомни как-нибудь")) is None

    monkeypatch.setattr(rem, "client", _fake_client("мусор без json"))
    assert asyncio.run(parse_reminder("напомни завтра")) is None


# --- lenient datetime parsing (models format it inconsistently) ---

def test_parse_datetime_accepts_common_shapes():
    from utils.reminders import _parse_datetime
    variants = [
        "2030-06-01 15:00",
        "2030-06-01T15:00",
        "2030-06-01 15:00:00",
        "2030-06-01T15:00:00",
        "01.06.2030 15:00",
    ]
    for v in variants:
        dt = _parse_datetime(v)
        assert dt is not None, v
        assert dt.year == 2030 and dt.month == 6 and dt.day == 1 and dt.hour == 15
    assert _parse_datetime("не дата") is None


# --- recurrence math ---

def test_next_occurrence():
    from datetime import datetime
    from config import TZINFO
    from utils.reminders import next_occurrence
    d = datetime(2030, 1, 31, 9, 0, tzinfo=TZINFO)  # Thursday
    assert next_occurrence(d, "daily").day == 1 and next_occurrence(d, "daily").month == 2
    assert (next_occurrence(d, "weekly") - d).days == 7
    # monthly from Jan 31 -> Feb 28 (clamped)
    m = next_occurrence(d, "monthly")
    assert m.month == 2 and m.day == 28
    # weekdays: Friday -> Monday (skip weekend)
    fri = datetime(2030, 2, 1, 9, 0, tzinfo=TZINFO)  # Friday
    assert next_occurrence(fri, "weekdays").weekday() == 0  # Monday
    assert next_occurrence(d, "none") is None


# --- db lifecycle ---

def test_reminder_db_lifecycle():
    async def scenario():
        await init_db()
        now = int(time.time())
        past_id = await add_reminder(50, 50, "уже пора", now - 60)
        future_id = await add_reminder(50, 50, "ещё рано", now + 3600)

        due = await get_due_reminders(now)
        due_ids = {r["id"] for r in due}
        assert past_id in due_ids and future_id not in due_ids

        # delivery marks it sent - it leaves both "due" and the user's list
        await mark_reminder_sent(past_id)
        assert past_id not in {r["id"] for r in await get_due_reminders(now)}

        pending = await list_reminders(50)
        assert [r["id"] for r in pending] == [future_id]

        # ownership check: another user can't delete it
        assert not await delete_reminder(future_id, user_id=999)
        assert await delete_reminder(future_id, user_id=50)
        assert await list_reminders(50) == []
    asyncio.run(scenario())


def test_recurring_reminder_reschedules_not_marks_sent():
    from db.database import reschedule_reminder
    async def scenario():
        await init_db()
        now = int(time.time())
        rid = await add_reminder(60, 60, "таблетки", now - 60, repeat="daily")
        due = await get_due_reminders(now)
        row = next(r for r in due if r["id"] == rid)
        assert row["repeat"] == "daily"
        # simulate the scheduler advancing it a day
        await reschedule_reminder(rid, now + 86400)
        # still pending (not sent), now in the future
        assert rid not in {r["id"] for r in await get_due_reminders(now)}
        assert rid in {r["id"] for r in await list_reminders(60)}
    asyncio.run(scenario())
