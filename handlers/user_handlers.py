import asyncio
import hashlib
import json
import os
import re
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command, CommandObject
from config import AVAILABLE_MODELS, TEXT_MODEL, PERSONAS, ADMIN_USER_ID, DB_PATH
from db.database import add_message, clear_history, get_user_model, set_user_model, get_user_persona, set_user_persona, get_stats
from task_queue.enqueue import enqueue_llm_job
from utils.group import gate_group_message, history_key, should_chime_in, CHATTER_PROMPT
from utils.ollama import list_installed_models
from utils.texts import t
from utils.web_search import perform_web_search

router = Router()

class MenuStates(StatesGroup):
    waiting_web_query = State()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(t("start"))

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(t("help"), parse_mode="HTML")

@router.message(Command("clear"))
async def cmd_clear(message: Message):
    # In groups this clears the shared group history, in private - the user's
    await clear_history(history_key(message))
    await message.answer(t("cleared"))

async def _stats_text(redis) -> str:
    stats = await get_stats()
    queue_len = await redis.llen("llm_queue")
    try:
        db_size = os.path.getsize(DB_PATH)
    except OSError:
        db_size = 0
    return t(
        "stats",
        users=stats["users"],
        messages=stats["messages"],
        today=stats["today"],
        queue=queue_len,
        db_size=f"{db_size / 1024 / 1024:.2f} MB",
    )

@router.message(Command("stats"))
async def cmd_stats(message: Message, redis):
    """Owner-only bot statistics (admin = ADMIN_USER_ID or the first allowed ID)."""
    if not ADMIN_USER_ID or message.from_user.id != ADMIN_USER_ID:
        await message.answer(t("stats_admin_only"))
        return
    await message.answer(await _stats_text(redis), parse_mode="HTML")

def _auto_key(model_name: str) -> str:
    """Stable short key for a model discovered via Ollama (not one of the
    friendly MODEL_CHOICES aliases) - long HuggingFace-style names would
    blow Telegram's 64-byte callback_data limit if used directly."""
    return "auto" + hashlib.sha1(model_name.encode()).hexdigest()[:8]

_QUANT_SUFFIX_RE = re.compile(r":(?:[Qq]\d[\w.]*|latest|[Ff]16|[Ff]32)$")

def _short_label(model_name: str) -> str:
    """Readable button label for a model that has no MODEL_CHOICES alias:
    drop the 'hf.co/org/' prefix and the ':Q4_K_M'-style quantization tag,
    turn dashes/underscores into spaces."""
    label = model_name.rsplit("/", 1)[-1]
    label = _QUANT_SUFFIX_RE.sub("", label)
    label = label.replace("-", " ").replace("_", " ")
    return label if len(label) <= 40 else label[:37] + "…"

def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t("back"), callback_data="nav:main")]])

async def _build_model_choices() -> dict:
    """AVAILABLE_MODELS (friendly keys from MODEL_CHOICES in .env) plus every
    model actually installed in Ollama that isn't already one of those
    values - so a freshly `ollama pull`-ed model shows up in /model right
    away, without editing .env and restarting the bot."""
    choices = dict(AVAILABLE_MODELS)
    known = set(choices.values())
    for name in await list_installed_models():
        if name not in known:
            choices[_auto_key(name)] = name
    return choices

def _model_keyboard(current: str, choices: dict) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=("✅ " if model_name == current else "")
                 + (_short_label(model_name) if key.startswith("auto") else f"{key}: {_short_label(model_name)}"),
            callback_data=f"model:{key}"
        )]
        for key, model_name in choices.items()
    ]
    buttons.append([InlineKeyboardButton(text=t("back"), callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("model"))
async def cmd_model(message: Message):
    """Show current text model and let the user switch it (photo analysis is unaffected - it always uses VISION_MODEL)."""
    current = await get_user_model(message.from_user.id) or TEXT_MODEL
    choices = await _build_model_choices()
    await message.answer(
        t("current_model", model=current),
        parse_mode="HTML",
        reply_markup=_model_keyboard(current, choices)
    )

@router.callback_query(F.data.startswith("model:"))
async def cb_model(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    choices = await _build_model_choices()
    model_name = choices.get(key)
    if not model_name:
        await callback.answer(t("unknown_model"), show_alert=True)
        return
    await set_user_model(callback.from_user.id, model_name)
    await callback.message.edit_text(
        t("model_switched", model=model_name),
        parse_mode="HTML",
        reply_markup=_model_keyboard(model_name, choices)
    )
    await callback.answer(t("switched_to", key=key))

def _persona_label(key: str) -> str:
    """Translated display name for a persona - add a matching persona_<key>
    entry to utils/texts.py whenever a new persona is added to PERSONAS."""
    return t(f"persona_{key}")

def _persona_keyboard(current_key: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=("✅ " if key == current_key else "") + _persona_label(key),
            callback_data=f"persona:{key}"
        )]
        for key in PERSONAS
    ]
    buttons.append([InlineKeyboardButton(text=t("back"), callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("persona"))
async def cmd_persona(message: Message):
    """Show current persona and let the user switch it. Applies to every reply, including photo descriptions."""
    current = await get_user_persona(message.from_user.id) or "default"
    await message.answer(
        t("current_persona", persona=_persona_label(current)),
        parse_mode="HTML",
        reply_markup=_persona_keyboard(current)
    )

@router.callback_query(F.data.startswith("persona:"))
async def cb_persona(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    if key not in PERSONAS:
        await callback.answer(t("unknown_persona"), show_alert=True)
        return
    await set_user_persona(callback.from_user.id, key)
    await callback.message.edit_text(
        t("persona_switched", persona=_persona_label(key)),
        parse_mode="HTML",
        reply_markup=_persona_keyboard(key)
    )
    await callback.answer(t("switched_to", key=_persona_label(key)))

def _main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=t("menu_model"), callback_data="nav:model")],
        [InlineKeyboardButton(text=t("menu_persona"), callback_data="nav:persona")],
        [InlineKeyboardButton(text=t("menu_web"), callback_data="nav:web")],
        [InlineKeyboardButton(text=t("menu_clear"), callback_data="nav:clear")],
        [InlineKeyboardButton(text=t("menu_help"), callback_data="nav:help")],
    ]
    if ADMIN_USER_ID:
        buttons.append([InlineKeyboardButton(text=t("menu_stats"), callback_data="nav:stats")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(t("menu_title"), parse_mode="HTML", reply_markup=_main_menu_keyboard())

@router.callback_query(F.data == "nav:main")
async def cb_nav_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(t("menu_title"), parse_mode="HTML", reply_markup=_main_menu_keyboard())
    await callback.answer()

@router.callback_query(F.data == "nav:model")
async def cb_nav_model(callback: CallbackQuery):
    current = await get_user_model(callback.from_user.id) or TEXT_MODEL
    choices = await _build_model_choices()
    await callback.message.edit_text(
        t("current_model", model=current),
        parse_mode="HTML",
        reply_markup=_model_keyboard(current, choices)
    )
    await callback.answer()

@router.callback_query(F.data == "nav:persona")
async def cb_nav_persona(callback: CallbackQuery):
    current = await get_user_persona(callback.from_user.id) or "default"
    await callback.message.edit_text(
        t("current_persona", persona=_persona_label(current)),
        parse_mode="HTML",
        reply_markup=_persona_keyboard(current)
    )
    await callback.answer()

@router.callback_query(F.data == "nav:clear")
async def cb_nav_clear(callback: CallbackQuery):
    # Don't reuse history_key(callback.message) - that message was sent by
    # the bot, so its from_user is the bot itself, not the person who
    # clicked the button.
    key = callback.from_user.id if callback.message.chat.type == "private" else callback.message.chat.id
    await clear_history(key)
    await callback.message.edit_text(t("cleared"), reply_markup=_back_keyboard())
    await callback.answer()

@router.callback_query(F.data == "nav:help")
async def cb_nav_help(callback: CallbackQuery):
    await callback.message.edit_text(t("help"), parse_mode="HTML", reply_markup=_back_keyboard())
    await callback.answer()

@router.callback_query(F.data == "nav:stats")
async def cb_nav_stats(callback: CallbackQuery, redis):
    if not ADMIN_USER_ID or callback.from_user.id != ADMIN_USER_ID:
        await callback.answer(t("stats_admin_only"), show_alert=True)
        return
    await callback.message.edit_text(
        await _stats_text(redis), parse_mode="HTML", reply_markup=_back_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "nav:web")
async def cb_nav_web(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MenuStates.waiting_web_query)
    await callback.message.edit_text(t("web_prompt"), reply_markup=_back_keyboard())
    await callback.answer()

async def _run_web_search(message: Message, redis, query: str):
    bot_message = await message.answer(t("searching"), parse_mode="HTML")

    # Run the blocking DDGS network call in a thread so it doesn't stall the event loop
    search_results = await asyncio.to_thread(perform_web_search, query)

    prompt = f"User asked: {query}\n\nHere are some web search results:\n{search_results}\n\nPlease synthesize an answer based on these results."

    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=prompt,
        history_content=f"Searched web for: {query}",
        context_type="web_search",
        history_id=history_key(message),
    )

@router.message(Command("web"))
async def cmd_web(message: Message, command: CommandObject, redis):
    """Handler for explicit web search."""
    # CommandObject handles /web@botname and doesn't touch "/web" inside the query
    query = (command.args or "").strip()
    if not query:
        await message.answer(t("web_usage"))
        return
    await _run_web_search(message, redis, query)

@router.message(F.text)
async def handle_text(message: Message, redis, state: FSMContext):
    # Waiting for a search query typed after tapping "Search the web" in
    # /menu - treat this message as that query instead of normal chat.
    if await state.get_state() == MenuStates.waiting_web_query.state:
        await state.clear()
        query = message.text.strip()
        if not query:
            await message.answer(t("web_usage"))
            return
        await _run_web_search(message, redis, query)
        return

    is_group = message.chat.type != "private"
    # In groups: react only to @mentions or replies to the bot
    should_handle, text = await gate_group_message(message, message.text)

    if not should_handle:
        # Not addressed to the bot. Still remember the message so the bot
        # follows the group conversation, and - if chatter is enabled -
        # occasionally chime in on its own like a regular member.
        if is_group and message.text and not message.text.startswith("/"):
            author = message.from_user.first_name or "Someone"
            await add_message(history_key(message), "user", f"{author}: {message.text}")
            if await should_chime_in(redis, message.chat.id):
                # Bot-initiated: no placeholder message, no rate limit, and
                # empty history_content so the instruction itself is not
                # stored as a user message
                await redis.rpush("llm_queue", json.dumps({
                    "chat_id": message.chat.id,
                    "user_id": message.from_user.id,
                    "history_id": history_key(message),
                    "prompt": CHATTER_PROMPT,
                    "history_content": "",
                    "context_type": "group_chatter",
                }))
        return

    if not text:
        return
    # Unknown commands ("/typo") fall through to this handler - don't feed
    # them to the LLM, silence is less confusing than a hallucinated answer
    if text.startswith("/"):
        return
    bot_message = await message.answer(t("thinking"), parse_mode="HTML")
    # In groups prefix the author's name so the shared history stays readable
    history_content = f"{message.from_user.first_name}: {text}" if is_group else text
    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=text,
        history_content=history_content,
        context_type="text",
        history_id=history_key(message),
    )
