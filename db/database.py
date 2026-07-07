import os
import aiosqlite
import logging
from typing import List, Dict

from config import DB_PATH as DB_NAME

logger = logging.getLogger(__name__)

async def init_db():
    db_dir = os.path.dirname(DB_NAME)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                model TEXT,
                persona TEXT
            )
        ''')
        try:
            # Migration for DBs created before the persona column existed.
            await db.execute("ALTER TABLE user_settings ADD COLUMN persona TEXT")
        except aiosqlite.OperationalError:
            pass
        try:
            # Per-user voice-reply preference (0 = text replies, default).
            await db.execute(
                "ALTER TABLE user_settings ADD COLUMN voice_replies INTEGER DEFAULT 0"
            )
        except aiosqlite.OperationalError:
            pass
        try:
            # Per-user interface language ("ru"/"en"); NULL = use BOT_LANGUAGE.
            await db.execute("ALTER TABLE user_settings ADD COLUMN language TEXT")
        except aiosqlite.OperationalError:
            pass
        try:
            # /new starts a fresh context: get_history only reads rows with
            # id > session_start, so old messages stay in the db (export,
            # stats) but no longer feed the model.
            await db.execute(
                "ALTER TABLE user_settings ADD COLUMN session_start INTEGER DEFAULT 0"
            )
        except aiosqlite.OperationalError:
            pass
        # get_history filters by user_id on every message - without an index
        # that's a full table scan that keeps growing with the history.
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id, id)"
        )
        # Long-term memory: one running summary per history key (user id in
        # private chats, chat id in groups). message_count = how many history
        # rows existed when the summary was last refreshed.
        await db.execute('''
            CREATE TABLE IF NOT EXISTS memory (
                history_id INTEGER PRIMARY KEY,
                summary TEXT,
                message_count INTEGER DEFAULT 0
            )
        ''')
        # Bot-level key/value settings changed at runtime (e.g. the admin
        # claimed via /admin), as opposed to the static .env configuration.
        await db.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # Reminders ("напомни завтра в 15:00 ..."). due_ts = unix timestamp;
        # the scheduler in utils/reminders.py polls for due unsent rows.
        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                due_ts INTEGER NOT NULL,
                sent INTEGER DEFAULT 0
            )
        ''')
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(sent, due_ts)"
        )
        await db.commit()
        logger.info("Database initialized.")

async def get_user_model(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT model FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_user_model(user_id: int, model: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO user_settings (user_id, model) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET model = excluded.model",
            (user_id, model)
        )
        await db.commit()

async def get_user_persona(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT persona FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_user_persona(user_id: int, persona: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO user_settings (user_id, persona) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET persona = excluded.persona",
            (user_id, persona)
        )
        await db.commit()

async def add_message(user_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO history (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content)
        )
        await db.commit()

async def get_history(user_id: int, limit: int = 10) -> List[Dict[str, str]]:
    # Only rows after the last /new boundary (session_start); no settings row
    # -> COALESCE gives 0 -> all history, i.e. unchanged default behaviour.
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT role, content FROM history WHERE user_id = ? "
            "AND id > COALESCE((SELECT session_start FROM user_settings WHERE user_id = ?), 0) "
            "ORDER BY timestamp DESC, id DESC LIMIT ?",
            (user_id, user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

async def start_new_session(history_id: int):
    """/new: move the context boundary to the newest message, so the model
    stops seeing earlier ones. History rows are kept (export, stats)."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT COALESCE(MAX(id), 0) FROM history WHERE user_id = ?", (history_id,)
        ) as cursor:
            max_id = (await cursor.fetchone())[0]
        await db.execute(
            "INSERT INTO user_settings (user_id, session_start) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET session_start = excluded.session_start",
            (history_id, max_id)
        )
        await db.commit()

async def get_user_language(user_id: int) -> str | None:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT language FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_user_language(user_id: int, lang: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO user_settings (user_id, language) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET language = excluded.language",
            (user_id, lang)
        )
        await db.commit()

async def get_voice_pref(user_id: int) -> bool:
    """Per-user 'reply with voice to voice messages' preference (default off)."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT voice_replies FROM user_settings WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row and row[0] is not None else False

async def set_voice_pref(user_id: int, enabled: bool):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO user_settings (user_id, voice_replies) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET voice_replies = excluded.voice_replies",
            (user_id, int(enabled))
        )
        await db.commit()

async def add_reminder(user_id: int, chat_id: int, text: str, due_ts: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO reminders (user_id, chat_id, text, due_ts) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, text, due_ts)
        )
        await db.commit()
        return cursor.lastrowid

async def get_due_reminders(now_ts: int) -> List[Dict]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id, user_id, chat_id, text, due_ts FROM reminders "
            "WHERE sent = 0 AND due_ts <= ?", (now_ts,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [
        {"id": r[0], "user_id": r[1], "chat_id": r[2], "text": r[3], "due_ts": r[4]}
        for r in rows
    ]

async def list_reminders(user_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id, text, due_ts FROM reminders "
            "WHERE user_id = ? AND sent = 0 ORDER BY due_ts", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
    return [{"id": r[0], "text": r[1], "due_ts": r[2]} for r in rows]

async def delete_reminder(reminder_id: int, user_id: int) -> bool:
    """Delete a pending reminder; the user_id check stops one user from
    deleting another user's reminders via forged callback data."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?",
            (reminder_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def mark_reminder_sent(reminder_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
        await db.commit()

async def get_setting(key: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT value FROM bot_settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO bot_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )
        await db.commit()

async def get_memory(history_id: int):
    """Returns (summary, message_count_at_last_refresh) for a history key."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT summary, message_count FROM memory WHERE history_id = ?", (history_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return (row[0], row[1] or 0) if row else (None, 0)

async def set_memory(history_id: int, summary: str, message_count: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO memory (history_id, summary, message_count) VALUES (?, ?, ?) "
            "ON CONFLICT(history_id) DO UPDATE SET summary = excluded.summary, "
            "message_count = excluded.message_count",
            (history_id, summary, message_count)
        )
        await db.commit()

async def count_messages(history_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM history WHERE user_id = ?", (history_id,)
        ) as cursor:
            return (await cursor.fetchone())[0]

async def get_stats() -> Dict[str, int]:
    """Aggregate numbers for the owner-only /stats command."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(DISTINCT user_id) FROM history") as cursor:
            users = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM history") as cursor:
            messages = (await cursor.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM history WHERE timestamp >= datetime('now', 'start of day')"
        ) as cursor:
            today = (await cursor.fetchone())[0]
    return {"users": users, "messages": messages, "today": today}

async def clear_history(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        await db.commit()
