import asyncio

import utils.admin as admin_mod
from db.database import init_db, set_setting
from utils.admin import get_admin_id, set_admin_id, admin_is_env_locked


def _reset_db_admin():
    async def scenario():
        await init_db()
        await set_setting("admin_id", "")
    asyncio.run(scenario())


def test_no_admin_by_default(monkeypatch):
    monkeypatch.setattr(admin_mod, "_ENV_ADMIN", None)
    _reset_db_admin()
    assert asyncio.run(get_admin_id()) is None
    assert not admin_is_env_locked()


def test_claim_and_transfer(monkeypatch):
    monkeypatch.setattr(admin_mod, "_ENV_ADMIN", None)
    _reset_db_admin()

    asyncio.run(set_admin_id(111))
    assert asyncio.run(get_admin_id()) == 111

    # transfer overwrites
    asyncio.run(set_admin_id(222))
    assert asyncio.run(get_admin_id()) == 222


def test_env_admin_wins_over_db(monkeypatch):
    _reset_db_admin()
    asyncio.run(set_admin_id(111))
    monkeypatch.setattr(admin_mod, "_ENV_ADMIN", 999)
    assert asyncio.run(get_admin_id()) == 999
    assert admin_is_env_locked()
