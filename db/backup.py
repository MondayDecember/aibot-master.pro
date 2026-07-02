import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from config import DB_PATH, BACKUP_INTERVAL_HOURS, BACKUP_KEEP

logger = logging.getLogger(__name__)


def _backup_dir() -> str:
    return os.path.join(os.path.dirname(DB_PATH) or ".", "backups")


def create_backup() -> str:
    """
    Write a consistent snapshot of the database via sqlite's online backup
    API (safe to run while the bot is writing) and prune old snapshots.
    Blocking - call via asyncio.to_thread. Returns the snapshot path.
    """
    backup_dir = _backup_dir()
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest_path = os.path.join(backup_dir, f"bot_data-{stamp}.db")

    src = sqlite3.connect(DB_PATH)
    dest = sqlite3.connect(dest_path)
    try:
        with dest:
            src.backup(dest)
    finally:
        dest.close()
        src.close()

    # Keep only the newest BACKUP_KEEP snapshots
    snapshots = sorted(
        f for f in os.listdir(backup_dir)
        if f.startswith("bot_data-") and f.endswith(".db")
    )
    for old in snapshots[:-BACKUP_KEEP] if BACKUP_KEEP > 0 else []:
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError as e:
            logger.warning(f"Failed to remove old backup {old}: {e}")

    return dest_path


async def backup_loop():
    """Background task: snapshot the database every BACKUP_INTERVAL_HOURS."""
    if BACKUP_INTERVAL_HOURS <= 0:
        logger.info("Database backups disabled (BACKUP_INTERVAL_HOURS=0).")
        return
    while True:
        try:
            path = await asyncio.to_thread(create_backup)
            logger.info(f"Database backed up to {path}")
        except Exception as e:
            logger.error(f"Database backup failed: {e}")
        await asyncio.sleep(BACKUP_INTERVAL_HOURS * 3600)
