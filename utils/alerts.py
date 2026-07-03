import logging
import time

from utils.admin import get_admin_id
from utils.texts import t

logger = logging.getLogger(__name__)

# Don't repeat the same alert more often than this (seconds) - a crashing
# loop must not flood the admin's telegram.
ALERT_COOLDOWN = 1800

_last_sent = {}


async def notify_admin(bot, error: Exception):
    """Best-effort private message to the admin about a bot error.
    Deduplicated per error type+text within ALERT_COOLDOWN."""
    admin_id = await get_admin_id()
    if not admin_id:
        return
    key = f"{type(error).__name__}:{str(error)[:100]}"
    now = time.time()
    if now - _last_sent.get(key, 0) < ALERT_COOLDOWN:
        return
    _last_sent[key] = now
    try:
        await bot.send_message(
            admin_id,
            t("admin_alert", error=f"{type(error).__name__}: {str(error)[:500]}"),
            parse_mode=None,
        )
    except Exception as e:
        logger.warning(f"Failed to notify admin: {e}")
