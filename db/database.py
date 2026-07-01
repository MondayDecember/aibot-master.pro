import aiosqlite
import logging
from typing import List, Dict

DB_NAME = "bot_data.db"
logger = logging.getLogger(__name__)

async def init_db():
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
        await db.commit()
        logger.info("Database initialized.")

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
