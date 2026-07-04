import asyncio

from db.database import init_db, get_voice_pref, set_voice_pref


def test_voice_pref_defaults_off_and_toggles():
    async def scenario():
        await init_db()
        # off by default - text replies, no duplicates
        assert not await get_voice_pref(7001)
        await set_voice_pref(7001, True)
        assert await get_voice_pref(7001)
        await set_voice_pref(7001, False)
        assert not await get_voice_pref(7001)
        # independent per user
        await set_voice_pref(7002, True)
        assert await get_voice_pref(7002)
        assert not await get_voice_pref(7001)
    asyncio.run(scenario())
