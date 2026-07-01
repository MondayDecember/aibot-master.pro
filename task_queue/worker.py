import asyncio
import json
import logging
from aiogram import Bot
from utils.llm_client import generate_response, should_search_web
from utils.web_search import perform_web_search
from db.database import get_history, add_message

logger = logging.getLogger(__name__)

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

                    # Let the model decide for itself if it needs to search the web
                    # (skip for explicit /web calls and non-text prompts like vision).
                    if context_type in ("text", "voice") and isinstance(prompt, str):
                        if await should_search_web(prompt):
                            if bot_message_id:
                                await bot.edit_message_text(
                                    chat_id=chat_id,
                                    message_id=bot_message_id,
                                    text="<i>Searching the web...</i>",
                                    parse_mode="HTML"
                                )
                            search_results = await asyncio.to_thread(perform_web_search, prompt)
                            final_prompt = (
                                f"User asked: {prompt}\n\n"
                                f"Here are some web search results:\n{search_results}\n\n"
                                f"Please synthesize an answer based on these results."
                            )
                            final_context_type = "web_search"

                    # Update status
                    if bot_message_id:
                        await bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=bot_message_id,
                            text="<i>Generating response...</i>",
                            parse_mode="HTML"
                        )

                    response_text = await generate_response(final_prompt, user_id, final_context_type)

                    # Persist the turn now, after history was fetched for generation,
                    # so the current message isn't duplicated into its own context.
                    history_content = job_data.get("history_content", prompt if isinstance(prompt, str) else "")
                    await add_message(user_id, "user", history_content)
                    await add_message(user_id, "assistant", response_text)
                    
                    # Edit telegram message with final response
                    if bot_message_id:
                        await bot.edit_message_text(
                            chat_id=chat_id, 
                            message_id=bot_message_id, 
                            text=response_text
                        )
                    else:
                        await bot.send_message(chat_id, response_text)
                except Exception as e:
                    logger.error(f"Error generating response: {e}")
                    if bot_message_id:
                        await bot.edit_message_text(
                            chat_id=chat_id, 
                            message_id=bot_message_id, 
                            text="Sorry, I encountered an error processing your request."
                        )
                    
        except asyncio.CancelledError:
            logger.info("Worker task cancelled.")
            break
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(1)
