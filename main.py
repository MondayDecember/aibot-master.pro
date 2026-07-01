import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from redis.asyncio import Redis

from config import BOT_TOKEN, REDIS_URL
from db.database import init_db
from task_queue.worker import process_queue

# Handlers
from handlers.user_handlers import router as user_router
from handlers.vision_handlers import router as vision_router
from handlers.voice_handlers import router as voice_router

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set in .env")
        return

    # 1. Init Database
    await init_db()

    # 2. Init Redis Queue
    try:
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
        await redis_client.ping()
        logger.info("Connected to Redis successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return
    
    # 3. Init Bot & Dispatcher
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Pass redis client to all handlers via workflow data
    dp["redis"] = redis_client

    # Include routers
    dp.include_router(user_router)
    dp.include_router(vision_router)
    dp.include_router(voice_router)

    # 4. Start Background Worker for LLM tasks
    worker_task = asyncio.create_task(process_queue(bot, redis_client))

    # 5. Start Polling
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
