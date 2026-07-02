import asyncio
import json
import logging
import time
from aiogram import Bot
from aiogram.utils.chat_action import ChatActionSender
from config import PERSONAS, AUTO_WEB_SEARCH, STREAM_RESPONSES
from utils.llm_client import generate_response, stream_response, should_search_web
from utils.web_search import perform_web_search
from db.database import get_history, add_message, get_user_model, get_user_persona

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096
# Minimum seconds between streaming edits of the same message - telegram
# throttles frequent edits, ~1/sec per chat is the safe zone.
STREAM_EDIT_INTERVAL = 1.5

def _split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into telegram-sized chunks, preferring newline boundaries."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", limit // 2, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    return chunks

async def _try_edit(bot: Bot, chat_id: int, message_id: int, text: str, parse_mode: str = None):
    """Best-effort message edit - a failed edit (e.g. the user deleted the
    placeholder message, or telegram throttled us) must not kill the job."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode=parse_mode
        )
    except Exception as e:
        logger.warning(f"Message edit failed: {e}")

async def _edit_status(bot: Bot, chat_id: int, message_id: int, text: str):
    await _try_edit(bot, chat_id, message_id, text, parse_mode="HTML")

async def process_queue(bot: Bot, redis_client):
    """Background worker to process LLM requests from Redis queue."""
    logger.info("Worker started, waiting for jobs...")
    while True:
        try:
            # BLPOP waits for an item in the queue (blocking pop)
            result = await redis_client.blpop("llm_queue", timeout=0)
            if result:
                _, data_json = result
                job_data = json.loads(data_json)
                
                chat_id = job_data["chat_id"]
                user_id = job_data["user_id"]
                prompt = job_data["prompt"]
                context_type = job_data.get("context_type", "text")
                bot_message_id = job_data.get("bot_message_id")
                
                # Fetch DB History is now handled directly by the LLM client
                
                try:
                    final_prompt = prompt
                    final_context_type = context_type
                    user_model = await get_user_model(user_id)  # None = use TEXT_MODEL default
                    persona_key = await get_user_persona(user_id) or "default"
                    system_prompt = PERSONAS.get(persona_key)

                    # Let the model decide for itself if it needs to search the web
                    # (skip for explicit /web calls and non-text prompts like vision).
                    if AUTO_WEB_SEARCH and context_type in ("text", "voice") and isinstance(prompt, str):
                        if await should_search_web(prompt, model_override=user_model):
                            if bot_message_id:
                                await _edit_status(bot, chat_id, bot_message_id, "<i>Searching the web...</i>")
                            search_results = await asyncio.to_thread(perform_web_search, prompt)
                            final_prompt = (
                                f"User asked: {prompt}\n\n"
                                f"Here are some web search results:\n{search_results}\n\n"
                                f"Please synthesize an answer based on these results."
                            )
                            final_context_type = "web_search"

                    # Update status
                    if bot_message_id:
                        await _edit_status(bot, chat_id, bot_message_id, "<i>Generating response...</i>")

                    # Show "typing..." in telegram for the whole generation;
                    # with streaming on, also grow the placeholder message as
                    # tokens arrive (the trailing ▌ marks an unfinished reply
                    # and guarantees the final edit differs from the last
                    # streamed preview).
                    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
                        if STREAM_RESPONSES and bot_message_id:
                            response_text = ""
                            last_edit = time.monotonic()
                            async for delta in stream_response(
                                final_prompt, user_id, final_context_type,
                                model_override=user_model, system_prompt=system_prompt
                            ):
                                response_text += delta
                                now = time.monotonic()
                                if (now - last_edit >= STREAM_EDIT_INTERVAL
                                        and response_text.strip()
                                        and len(response_text) < TELEGRAM_MESSAGE_LIMIT - 2):
                                    await _try_edit(bot, chat_id, bot_message_id, response_text + " ▌")
                                    last_edit = now
                        else:
                            response_text = await generate_response(
                                final_prompt, user_id, final_context_type,
                                model_override=user_model, system_prompt=system_prompt
                            )

                    # Persist the turn now, after history was fetched for generation,
                    # so the current message isn't duplicated into its own context.
                    history_content = job_data.get("history_content", prompt if isinstance(prompt, str) else "")
                    await add_message(user_id, "user", history_content)
                    await add_message(user_id, "assistant", response_text)
                    
                    # Edit telegram message with final response. Plain text on
                    # purpose: the bot's default parse_mode is HTML, and LLM
                    # output with < > & (code, math) would fail to parse.
                    # Telegram also caps messages at 4096 chars, so split.
                    chunks = _split_message(
                        (response_text or "").strip() or "The model returned an empty response."
                    )
                    if bot_message_id:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=bot_message_id,
                            text=chunks[0],
                            parse_mode=None
                        )
                        for chunk in chunks[1:]:
                            await bot.send_message(chat_id, chunk, parse_mode=None)
                    else:
                        for chunk in chunks:
                            await bot.send_message(chat_id, chunk, parse_mode=None)
                except Exception as e:
                    logger.error(f"Error generating response: {e}")
                    if bot_message_id:
                        await _edit_status(
                            bot, chat_id, bot_message_id,
                            "Sorry, I encountered an error processing your request."
                        )
                    
        except asyncio.CancelledError:
            logger.info("Worker task cancelled.")
            break
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(1)
