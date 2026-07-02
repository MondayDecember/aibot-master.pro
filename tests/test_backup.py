import asyncio
import os
import sqlite3

import config
from db.backup import create_backup
from db.database import init_db, add_message


def test_backup_snapshot_and_rotation(monkeypatch):
    async def prepare():
        await init_db()
        await add_message(999, "user", "backup me")
    asyncio.run(prepare())

    # Freeze distinct filenames without sleeping between snapshots
    stamps = iter(f"20260101-00000{i}" for i in range(10))

    class FakeDatetime:
        @staticmethod
        def now():
            class _Stamp:
                @staticmethod
                def strftime(_fmt):
                    return next(stamps)
            return _Stamp()

    monkeypatch.setattr("db.backup.datetime", FakeDatetime)

    paths = [create_backup() for _ in range(5)]

    backup_dir = os.path.join(os.path.dirname(config.DB_PATH) or ".", "backups")
    left = sorted(os.listdir(backup_dir))
    # conftest sets BACKUP_KEEP=3
    assert len(left) == 3, left

    # the newest snapshot is a valid database with the data
    check = sqlite3.connect(paths[-1])
    count = check.execute(
        "SELECT COUNT(*) FROM history WHERE user_id = 999"
    ).fetchone()[0]
    check.close()
    assert count >= 1
