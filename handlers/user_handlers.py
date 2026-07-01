import asyncio
import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from config import AVAILABLE_MODELS, TEXT_MODEL
from db.database import clear_history, get_user_model, set_user_model
from utils.web_search import perform_web_search

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Hello! I am your AI assistant. Send me text, voice messages, or photos, "
        "use /web <query> to search the web, or /model to switch the text model."
    )

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    await clear_history(message.from_user.id)
    await message.answer("Conversation history cleared!")

def _model_keyboard(current: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=("✅ " if model_name == current else "") + key,
            callback_data=f"model:{key}"
        )]
        for key, model_name in AVAILABLE_MODELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("model"))
async def cmd_model(message: Message):
    """Show current text model and let the user switch it (photo analysis is unaffected - it always uses VISION_MODEL)."""
    current = await get_user_model(message.from_user.id) or TEXT_MODEL
    await message.answer(
        f"Current text model: <code>{current}</code>\nPick one:",
        parse_mode="HTML",
        reply_markup=_model_keyboard(current)
    )

@router.callback_query(F.data.startswith("model:"))
async def cb_model(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    model_name = AVAILABLE_MODELS.get(key)
    if not model_name:
        await callback.answer("Unknown model", show_alert=True)
        return
    await set_user_model(callback.from_user.id, model_name)
    await callback.message.edit_text(
        f"Text model switched to: <code>{model_name}</code>",
        parse_mode="HTML",
        reply_markup=_model_keyboard(model_name)
    )
    await callback.answer(f"Switched to {key}")

@router.message(Command("web"))
async def cmd_web(message: Message, redis):
    """Handler for explicit web search."""
    query = message.text.replace("/web", "").strip()
    if not query:
        await message.answer("Please provide a search query. Example: /web current weather in London")
        return
        
    bot_message = await message.answer("<i>Searching the web...</i>", parse_mode="HTML")

    # Run the blocking DDGS network call in a thread so it doesn't stall the event loop
    search_results = await asyncio.to_thread(perform_web_search, query)

    prompt = f"User asked: {query}\n\nHere are some web search results:\n{search_results}\n\nPlease synthesize an answer based on these results."

    # Queue job (user message is persisted by the worker, after it fetches history)
    job_data = {
        "chat_id": message.chat.id,
        "user_id": message.from_user.id,
        "prompt": prompt,
        "history_content": f"Searched web for: {query}",
        "context_type": "web_search",
        "bot_message_id": bot_message.message_id
    }
    await redis.rpush("llm_queue", json.dumps(job_data))

@router.message(F.text)
async def handle_text(message: Message, redis):
    bot_message = await message.answer("<i>Thinking...</i>", parse_mode="HTML")

    # Queue job (user message is persisted by the worker, after it fetches history)
    job_data = {
        "chat_id": message.chat.id,
        "user_id": message.from_user.id,
        "prompt": message.text,
        "history_content": message.text,
        "context_type": "text",
        "bot_message_id": bot_message.message_id
    }
    await redis.rpush("llm_queue", json.dumps(job_data))
