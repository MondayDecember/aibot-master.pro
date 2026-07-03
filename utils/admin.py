"""Runtime admin resolution.

The admin can come from two places, in priority order:
1. Static config: ADMIN_USER_ID in .env, or the first entry of
   ALLOWED_USER_IDS (see config.py). Can't be changed from Telegram.
2. Claimed at runtime via /admin and stored in the database - for installs
   where the owner skipped entering their ID during setup.
"""
from config import ADMIN_USER_ID as _ENV_ADMIN
from db.database import get_setting, set_setting


async def get_admin_id():
    """Effective admin's telegram id, or None when nobody is admin yet."""
    if _ENV_ADMIN:
        return _ENV_ADMIN
    value = await get_setting("admin_id")
    return int(value) if value and value.isdigit() else None


async def set_admin_id(user_id: int):
    await set_setting("admin_id", str(user_id))


def admin_is_env_locked() -> bool:
    """True when the admin comes from .env / ALLOWED_USER_IDS - transferring
    via /admin would silently not apply, so the command refuses instead."""
    return _ENV_ADMIN is not None
