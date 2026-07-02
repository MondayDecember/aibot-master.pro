import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from redis.asyncio import Redis

from config import BOT_TOKEN, REDIS_URL, OLLAMA_API_BASE, TEXT_MODEL, VISION_MODEL, AVAILABLE_MODELS
from db.database import init_db
from task_queue.worker import process_queue

# Handlers
from handlers.user_handlers import router as user_router
from handlers.vision_handlers import router as vision_router
from handlers.voice_handlers import router as voice_router
from handlers.document_handlers import router as document_router
from middlewares.access import AccessMiddleware

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def check_ollama():
    """
    Warn early if Ollama is unreachable or required models are missing, so the
    user sees an actionable message in the logs instead of a traceback on the
    first request. Non-fatal: Ollama may simply not be up yet.
    """
    # OLLAMA_API_BASE points to the OpenAI-compatible endpoint (".../v1"),
    # the native API with /api/tags lives one level up.
    base = OLLAMA_API_BASE.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{base}/api/tags") as resp:
                data = await resp.json()
    except Exception as e:
        logger.warning(
            f"Ollama is not reachable at {OLLAMA_API_BASE} ({e}). "
            "The bot will start, but it can't reply until Ollama is up. "
            "Check OLLAMA_API_BASE in .env."
        )
        return
    installed = set()
    for m in data.get("models", []):
        name = m.get("name", "")
        installed.add(name)
        installed.add(name.split(":")[0])
    required = {TEXT_MODEL, VISION_MODEL} | set(AVAILABLE_MODELS.values())
    for model in sorted(required):
        if model not in installed and model.split(":")[0] not in installed:
            logger.warning(f"Model '{model}' is not installed in Ollama. Run: ollama pull {model}")
    logger.info(f"Ollama is reachable at {OLLAMA_API_BASE}")

async def main():
    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN is not set. Copy .env.example to .env and fill in the "
            "token from @BotFather."
        )
        return

    # 1. Init Database
    await init_db()

    # 2. Check Ollama (warns but does not abort)
    await check_ollama()

    # 3. Init Redis Queue
    try:
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
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

    # 5. Start Background Worker for LLM tasks
    worker_task = asyncio.create_task(process_queue(bot, redis_client))

    # 6. Start Polling
    logger.info("Starting bot polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        worker_task.cancel()
        await redis_client.close()
        await bot.session.close()
        logger.info("Bot shut down gracefully.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
