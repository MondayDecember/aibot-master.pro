"""Reminders: "напомни завтра в 15:00 проверить бэкапы".

The LLM has no clock, so parsing works by TELLING it the current local date
and time and asking it to resolve relative expressions ("завтра", "через два
часа", "в пятницу") into an absolute timestamp, returned as strict JSON.
A background scheduler polls the db and delivers due reminders.
"""
import asyncio
import json
import logging
import re
import time
from datetime import datetime

from config import TEXT_MODEL, SUMMARY_MODEL, TIMEZONE, TZINFO
from db.database import get_due_reminders, mark_reminder_sent
from utils.llm_client import client
from utils.texts import t

logger = logging.getLogger(__name__)

# What counts as a reminder request. Anchored to the start (plus the
# "поставь/создай напоминание" phrasing anywhere) so ordinary chat like
# "он мне напомнил про..." doesn't trigger it.
_TRIGGER_RE = re.compile(
    r"^\s*(напомни|напоминание\b|remind\b)|(поставь|создай|сделай)\s+напоминание",
    re.IGNORECASE,
)

_JSON_RE = re.compile(r"\{.*\}", re.S)

_PARSE_SYSTEM = (
    "You convert a reminder request into JSON.\n"
    "Current local date and time: {now} ({tz}).\n"
    "Reply with ONLY a JSON object and nothing else:\n"
    '{{"text": "<what to remind about, short, in the language of the request>", '
    '"datetime": "YYYY-MM-DD HH:MM"}}\n'
    "Resolve relative expressions (tomorrow, in 2 hours, on Friday, завтра, "
    "через час, в пятницу) against the current date/time above. If a time of "
    "day is not given, use 09:00. If the request contains no usable date or "
    'time at all, reply {{"error": "no_time"}}.'
)


def is_reminder_request(text) -> bool:
    return bool(text and _TRIGGER_RE.search(text))


def now_local() -> datetime:
    return datetime.now(TZINFO)


def format_due(due_ts: int) -> str:
    return datetime.fromtimestamp(due_ts, TZINFO).strftime("%d.%m.%Y %H:%M")


def _extract_json(raw):
    match = _JSON_RE.search(raw or "")
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except ValueError:
        return None


async def parse_reminder(text: str, model: str = None):
    """(reminder_text, due_unix_ts) or None when the time can't be parsed."""
    now = now_local()
    response = await client.chat.completions.create(
        model=model or SUMMARY_MODEL or TEXT_MODEL,
        messages=[
            {
                "role": "system",
                "content": _PARSE_SYSTEM.format(
                    now=now.strftime("%A, %Y-%m-%d %H:%M"), tz=TIMEZONE
                ),
            },
            {"role": "user", "content": text},
        ],
        temperature=0,
        max_tokens=500,
    )
    data = _extract_json(response.choices[0].message.content)
    if not data or data.get("error") or not data.get("text") or not data.get("datetime"):
        return None
    try:
        due = datetime.strptime(data["datetime"], "%Y-%m-%d %H:%M").replace(tzinfo=TZINFO)
    except ValueError:
        return None
    if due <= now:
        return None
    return data["text"].strip(), int(due.timestamp())


async def reminder_loop(bot):
    """Background task: deliver due reminders. Marked sent even if delivery
    fails (user blocked the bot etc.) so one dead chat can't clog the loop."""
    logger.info("Reminder scheduler started.")
    while True:
        try:
            for reminder in await get_due_reminders(int(time.time())):
                try:
                    await bot.send_message(
                        reminder["chat_id"],
                        t("reminder_fire", text=reminder["text"]),
                        parse_mode=None,
                    )
                    logger.info(f"Delivered reminder {reminder['id']}")
                except Exception as e:
                    logger.warning(f"Reminder {reminder['id']} delivery failed: {e}")
                await mark_reminder_sent(reminder["id"])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")
        await asyncio.sleep(30)
