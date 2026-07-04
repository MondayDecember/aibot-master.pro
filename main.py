import asyncio
import logging
import os
import tempfile
import time
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand
from redis.asyncio import Redis

from utils.texts import t
from utils.llm_backend import list_installed_models

from config import BOT_TOKEN, REDIS_URL, OLLAMA_API_BASE, TEXT_MODEL, VISION_MODEL, AVAILABLE_MODELS, IMAGEGEN_ENABLED
from db.database import init_db
from db.backup import backup_loop
from task_queue.worker import process_queue

# Handlers
from handlers.user_handlers import router as user_router
from handlers.vision_handlers import router as vision_router
from handlers.voice_handlers import router as voice_router
from handlers.document_handlers import router as document_router
from middlewares.access import AccessMiddleware

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_llm_backend():
    """
    Warn early if the LLM backend (Ollama, LM Studio, or any other
    OpenAI-compatible server at OLLAMA_API_BASE) is unreachable or required
    models are missing, so the user sees an actionable message in the logs
    instead of a traceback on the first request. Non-fatal: it may simply
    not be up yet.
    """
    names = await list_installed_models()
    if not names:
        logger.warning(
            f"No LLM backend reachable at {OLLAMA_API_BASE} (or it has no models "
            "loaded) - checked via /v1/models. The bot will start, but it can't "
            "reply until it's up. Ollama: 'ollama serve' + 'ollama pull <model>'. "
            "LM Studio: enable the local server (port 1234 by default) and load a model."
        )
        return
    installed = set()
    for name in names:
        installed.add(name)
        installed.add(name.split(":")[0])
    required = {TEXT_MODEL, VISION_MODEL} | set(AVAILABLE_MODELS.values())
    for model in sorted(required):
        if model not in installed and model.split(":")[0] not in installed:
            logger.warning(f"Model '{model}' isn't loaded on the LLM backend at {OLLAMA_API_BASE}.")
    logger.info(f"LLM backend reachable at {OLLAMA_API_BASE} with {len(names)} model(s) available.")

# The container healthcheck looks at this file's mtime (see docker-compose.yml)
HEARTBEAT_FILE = os.getenv(
    "HEARTBEAT_FILE", os.path.join(tempfile.gettempdir(), "aibot_healthy")
)

async def heartbeat_loop():
    """Touch the heartbeat file so docker can tell a live bot from a hung one."""
    while True:
        try:
            with open(HEARTBEAT_FILE, "w") as f:
                f.write(str(time.time()))
        except OSError as e:
            logger.warning(f"Heartbeat write failed: {e}")
        await asyncio.sleep(30)

async def setup_commands(bot: Bot):
    """Register the command menu shown by the '/' button in telegram."""
    commands = [
        BotCommand(command="menu", description=t("desc_menu")),
        BotCommand(command="help", description=t("desc_help")),
        BotCommand(command="clear", description=t("desc_clear")),
        BotCommand(command="web", description=t("desc_web")),
        BotCommand(command="model", description=t("desc_model")),
        BotCommand(command="persona", description=t("desc_persona")),
        BotCommand(command="stats", description=t("desc_stats")),
    ]
    # Only advertised when the separate imagegen service is configured -
    # otherwise it's a menu entry that always fails (see imagegen/README.md)
    if IMAGEGEN_ENABLED:
        commands.append(BotCommand(command="imagine", description=t("desc_imagine")))
    await bot.set_my_commands(commands)

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "your_telegram_bot_token_here":
        # Idle instead of exiting: with restart:unless-stopped an exit would
        # put the container into a restart loop. The user enters the token
        # via configure.sh / .env and restarts; the heartbeat stays off on
        # purpose so the container honestly shows as unhealthy meanwhile.
        logger.error(
            "BOT_TOKEN is not set. Enter it via configure.sh / configure.ps1 "
            "(option 1) or in .env, then restart: docker compose up -d"
        )
        while True:
            await asyncio.sleep(600)
            logger.error("Still waiting for BOT_TOKEN (configure.sh or .env, then restart).")

    # 1. Init Database
    await init_db()

    # 2. Check the LLM backend (warns but does not abort)
    await check_llm_backend()

    # 3. Init Redis Queue
    try:
        # socket_keepalive: without it, idle connections get silently reset
        # by Docker Desktop's Windows/WSL2 network layer, which surfaced as
        # periodic "Timeout reading from redis" errors from the worker.
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True, socket_keepalive=True)
        await redis_client.ping()
        logger.info("Connected to Redis successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return
    
    # 4. Init Bot & Dispatcher
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Pass redis client to all handlers via workflow data
    dp["redis"] = redis_client

    # Access control (no-op when ALLOWED_USER_IDS is empty)
    dp.message.outer_middleware(AccessMiddleware())
    dp.callback_query.outer_middleware(AccessMiddleware())

    # Include routers
    dp.include_router(user_router)
    dp.include_router(vision_router)
    dp.include_router(voice_router)
    dp.include_router(document_router)

    # 5. Start Background Worker for LLM tasks, periodic DB backups and
    #    the healthcheck heartbeat
    worker_task = asyncio.create_task(process_queue(bot, redis_client))
    backup_task = asyncio.create_task(backup_loop())
    heartbeat_task = asyncio.create_task(heartbeat_loop())

    # 6. Start Polling
    logger.info("Starting bot polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await setup_commands(bot)
        await dp.start_polling(bot)
    finally:
        worker_task.cancel()
        backup_task.cancel()
        heartbeat_task.cancel()
        await redis_client.aclose()
        await bot.session.close()
        logger.info("Bot shut down gracefully.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
