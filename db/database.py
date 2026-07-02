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
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT role, content FROM history WHERE user_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

async def clear_history(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        await db.commit()
