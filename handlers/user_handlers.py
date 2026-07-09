import hashlib
import json
import os
import random
import re
from datetime import datetime
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import CommandStart, Command, CommandObject
from config import AVAILABLE_MODELS, TEXT_MODEL, PERSONAS, DB_PATH, IMAGEGEN_ENABLED, VOICE_REPLIES, RATE_LIMIT_PER_MINUTE, TZINFO
from db.database import add_message, clear_history, get_user_model, set_user_model, get_user_persona, set_user_persona, get_stats, list_reminders, delete_reminder, get_voice_pref, set_voice_pref, start_new_session, set_user_language, get_user_language, get_custom_prompt, set_custom_prompt, get_usage_summary, get_recent_usage
from task_queue.enqueue import enqueue_llm_job, over_rate_limit
from utils.tts_helper import synthesize_speech
from utils.admin import get_admin_id, set_admin_id, admin_is_env_locked
from utils.group import gate_group_message, history_key, should_chime_in, CHATTER_PROMPT
from utils.reminders import is_reminder_request, format_due
from utils.reactions import react_seen
from utils.imagegen_client import generate_image
from utils.llm_backend import list_installed_models
from utils.llm_client import _resolve_model
from utils.texts import t, set_current_language
from utils.web_search import gather_web_context

router = Router()

class MenuStates(StatesGroup):
    waiting_web_query = State()
    waiting_imagine_prompt = State()

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

@router.message(Command("new"))
async def cmd_new(message: Message):
    """Start a fresh context without deleting the old history."""
    await start_new_session(history_key(message))
    await message.answer(t("new_done"))

@router.message(Command("whoami"))
async def cmd_whoami(message: Message):
    uid = message.from_user.id
    model = await _resolve_model(await get_user_model(uid) or TEXT_MODEL)
    persona = await get_user_persona(uid) or "default"
    lang = await get_user_language(uid) or "—"
    voice = t("yes_word") if await get_voice_pref(uid) else t("no_word")
    custom = await get_custom_prompt(uid)
    await message.answer(
        t("whoami", id=uid, model=model, persona=t(f"persona_{persona}"),
          lang=lang, voice=voice, prompt=(custom or t("none_word"))),
        parse_mode="HTML",
    )

@router.message(Command("setprompt"))
async def cmd_setprompt(message: Message, command: CommandObject):
    """Personal custom instructions applied on top of the persona."""
    arg = (command.args or "").strip()
    if not arg:
        current = await get_custom_prompt(message.from_user.id)
        await message.answer(
            t("setprompt_current", text=current) if current else t("setprompt_none"),
            parse_mode="HTML",
        )
        return
    if arg == "-":
        await set_custom_prompt(message.from_user.id, None)
        await message.answer(t("setprompt_cleared"))
        return
    await set_custom_prompt(message.from_user.id, arg[:1000])
    await message.answer(t("setprompt_set"))

@router.message(Command("summary"))
async def cmd_summary(message: Message, redis):
    """On-demand summary of the current dialog (runs through the LLM queue)."""
    bot_message = await message.answer(t("summary_working"), parse_mode="HTML")
    await redis.rpush("llm_queue", json.dumps({
        "chat_id": message.chat.id,
        "user_id": message.from_user.id,
        "history_id": history_key(message),
        "context_type": "usersummary",
        "bot_message_id": bot_message.message_id,
        "prompt": "",
    }))

@router.callback_query(F.data == "tts")
async def cb_tts(callback: CallbackQuery, redis):
    """Speak a finished reply on demand (🔊 button)."""
    text = await redis.get(f"tts:{callback.message.chat.id}:{callback.message.message_id}")
    if not text:
        await callback.answer()
        return
    await callback.answer()
    audio = await synthesize_speech(text)
    if audio:
        await callback.message.answer_voice(BufferedInputFile(audio, filename="reply.ogg"))

@router.callback_query(F.data.startswith("stop:"))
async def cb_stop(callback: CallbackQuery, redis):
    """Signal the worker to cut the streaming reply short (checked each tick)."""
    mid = callback.data.split(":", 1)[1]
    await redis.set(f"stop:{callback.message.chat.id}:{mid}", "1", ex=120)
    await callback.answer(t("stopping"))

@router.callback_query(F.data == "regen")
async def cb_regen(callback: CallbackQuery, redis):
    """Re-run the user's last prompt to get a different answer."""
    hid = callback.from_user.id if callback.message.chat.type == "private" else callback.message.chat.id
    prompt = await redis.get(f"regen:{hid}")
    if not prompt:
        await callback.answer(t("regen_none"), show_alert=True)
        return
    if await over_rate_limit(redis, callback.from_user.id):
        await callback.answer(t("rate_limited", limit=RATE_LIMIT_PER_MINUTE), show_alert=True)
        return
    await callback.answer(t("regenerating"))
    # Drop the old reply's button so it can't be tapped twice
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    bot_message = await callback.message.answer(t("thinking"), parse_mode="HTML")
    await redis.rpush("llm_queue", json.dumps({
        "chat_id": callback.message.chat.id,
        "user_id": callback.from_user.id,
        "history_id": hid,
        "prompt": prompt,
        "history_content": prompt,
        "context_type": "text",
        "bot_message_id": bot_message.message_id,
    }))

@router.message(Command("dice"))
async def cmd_dice(message: Message, command: CommandObject):
    """Fair randomness: /dice, /dice coin, /dice N, /dice a, b, c."""
    await message.answer(_dice_result(command.args))

_ROLL_RE = re.compile(r"^\s*(\d*)d(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)

@router.message(Command("roll"))
async def cmd_roll(message: Message, command: CommandObject):
    """Dice notation: /roll 2d6, /roll d20+3."""
    m = _ROLL_RE.match(command.args or "d6")
    if not m:
        await message.answer(t("roll_usage"))
        return
    count = min(int(m.group(1) or 1), 100)
    sides = int(m.group(2))
    modifier = int((m.group(3) or "0").replace(" ", ""))
    if count < 1 or sides < 2:
        await message.answer(t("roll_usage"))
        return
    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier
    expr = f"{count}d{sides}" + (f"{modifier:+d}" if modifier else "")
    shown = " + ".join(map(str, rolls)) + (f" {modifier:+d}" if modifier else "")
    await message.answer(t("roll_result", expr=expr, rolls=shown, total=total), parse_mode="HTML")

@router.message(Command("8ball"))
async def cmd_8ball(message: Message):
    answer = random.choice(t("eightball_answers").split("\n"))
    await message.answer(t("eightball_prefix", answer=answer))

def _dice_result(args: str | None) -> str:
    arg = (args or "").strip()
    if "," in arg:
        options = [o.strip() for o in arg.split(",") if o.strip()]
        if options:
            return t("dice_choice", choice=random.choice(options))
    low = arg.lower()
    if low in ("coin", "монетка", "монета", "орёл", "решка", "орел"):
        side = t("dice_heads") if random.random() < 0.5 else t("dice_tails")
        return t("dice_coin", side=side)
    if arg.isdigit() and int(arg) >= 2:
        return t("dice_number", n=random.randint(1, int(arg)))
    return t("dice_number", n=random.randint(1, 6))

def _language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
    ]])

@router.message(Command("language"))
async def cmd_language(message: Message):
    await message.answer(t("language_prompt"), reply_markup=_language_keyboard())

@router.callback_query(F.data.startswith("lang:"))
async def cb_language(callback: CallbackQuery):
    lang = callback.data.split(":", 1)[1]
    if lang not in ("ru", "en"):
        await callback.answer()
        return
    await set_user_language(callback.from_user.id, lang)
    # Reflect the new language immediately in this same response
    set_current_language(lang)
    await callback.message.edit_text(t("language_set"))
    await callback.answer()

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
    """Owner-only bot statistics."""
    admin_id = await get_admin_id()
    if not admin_id or message.from_user.id != admin_id:
        await message.answer(t("stats_admin_only"))
        return
    await message.answer(await _stats_text(redis), parse_mode="HTML")

@router.message(Command("usage"))
async def cmd_usage(message: Message):
    """Owner-only LLM usage log: totals + the last requests with tokens."""
    admin_id = await get_admin_id()
    if not admin_id or message.from_user.id != admin_id:
        await message.answer(t("stats_admin_only"))
        return
    now = datetime.now(TZINFO)
    today_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    summary = await get_usage_summary(today_start)
    recent = await get_recent_usage(10)
    lines = [t("usage_header",
               today_req=summary["today_requests"], today_tok=summary["today_tokens"],
               total_req=summary["requests"], total_tok=summary["tokens"])]
    if recent:
        lines.append("")
        lines.append(t("usage_recent_title"))
        for r in recent:
            when = datetime.fromtimestamp(r["ts"], TZINFO).strftime("%d.%m %H:%M")
            model = (r["model"] or "?").split("/")[-1][:20]
            lines.append(t("usage_row", when=when, model=model, total=r["total_tokens"]))
    await message.answer("\n".join(lines), parse_mode="HTML")

@router.message(Command("admin"))
async def cmd_admin(message: Message, command: CommandObject):
    """Claim adminship when nobody is admin yet (owner skipped entering
    their ID during install), or transfer it as the current admin."""
    current = await get_admin_id()
    user_id = message.from_user.id

    if current is None:
        # Claiming is private-chat only: in a group ANY member could send
        # /admin and grab adminship before the actual owner does
        if message.chat.type != "private":
            await message.answer(t("admin_claim_private"))
            return
        await set_admin_id(user_id)
        await message.answer(t("admin_claimed"))
        return

    if user_id != current:
        await message.answer(t("stats_admin_only"))
        return

    arg = (command.args or "").strip()
    if not arg:
        await message.answer(t("admin_current", admin_id=current))
        return
    if admin_is_env_locked():
        await message.answer(t("admin_env_locked"))
        return
    if not arg.isdigit():
        await message.answer(t("admin_usage"))
        return
    await set_admin_id(int(arg))
    await message.answer(t("admin_transferred", admin_id=arg))

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
    """AVAILABLE_MODELS (friendly keys from MODEL_CHOICES in .env), filtered
    down to models actually installed on the backend, plus every installed
    model that isn't already one of those values - so switching between
    /model entries always works, and a freshly `ollama pull`-ed model shows
    up right away without editing .env and restarting the bot. If the
    backend is unreachable (empty list), show the configured choices as-is
    rather than hiding everything on a transient outage."""
    installed = await list_installed_models()
    if not installed:
        return dict(AVAILABLE_MODELS)
    installed_base = {name.split(":")[0] for name in installed}

    def _is_installed(name: str) -> bool:
        return name in installed or name.split(":")[0] in installed_base

    choices = {key: name for key, name in AVAILABLE_MODELS.items() if _is_installed(name)}
    known = set(choices.values())
    for name in installed:
        if name not in known:
            choices[_auto_key(name)] = name
    return choices

def _model_keyboard(current: str, choices: dict) -> InlineKeyboardMarkup:
    # "default" (the fallback when MODEL_CHOICES has no real aliases) isn't a
    # meaningful label on its own - just show the model. A genuine custom
    # alias like "coder"/"uncensored" is still worth showing alongside it.
    buttons = [
        [InlineKeyboardButton(
            text=("✅ " if model_name == current else "")
                 + (_short_label(model_name) if key in ("default",) or key.startswith("auto")
                    else f"{key}: {_short_label(model_name)}"),
            callback_data=f"model:{key}"
        )]
        for key, model_name in choices.items()
    ]
    buttons.append([InlineKeyboardButton(text=t("back"), callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("model"))
async def cmd_model(message: Message):
    """Show current text model and let the user switch it (photo analysis is unaffected - it always uses VISION_MODEL)."""
    current = await _resolve_model(await get_user_model(message.from_user.id) or TEXT_MODEL)
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

def _base_menu_buttons() -> list:
    # Two buttons per row reads nicer than one long column
    buttons = [
        [InlineKeyboardButton(text=t("menu_model"), callback_data="nav:model"),
         InlineKeyboardButton(text=t("menu_persona"), callback_data="nav:persona")],
        [InlineKeyboardButton(text=t("menu_web"), callback_data="nav:web"),
         InlineKeyboardButton(text=t("menu_reminders"), callback_data="nav:reminders")],
    ]
    # Only shown when the separate imagegen service is configured (see
    # imagegen/README.md) - otherwise it's just a button that always fails.
    if IMAGEGEN_ENABLED:
        buttons.append([InlineKeyboardButton(text=t("menu_imagine"), callback_data="nav:imagine")])
    buttons.append([InlineKeyboardButton(text=t("menu_new"), callback_data="nav:new"),
                    InlineKeyboardButton(text=t("menu_clear"), callback_data="nav:clear")])
    buttons.append([InlineKeyboardButton(text=t("menu_language"), callback_data="nav:language"),
                    InlineKeyboardButton(text=t("menu_help"), callback_data="nav:help")])
    return buttons

@router.callback_query(F.data == "nav:new")
async def cb_nav_new(callback: CallbackQuery):
    key = callback.from_user.id if callback.message.chat.type == "private" else callback.message.chat.id
    await start_new_session(key)
    await callback.message.edit_text(t("new_done"), reply_markup=_back_keyboard())
    await callback.answer()

@router.callback_query(F.data == "nav:language")
async def cb_nav_language(callback: CallbackQuery):
    await callback.message.edit_text(t("language_prompt"), reply_markup=_language_keyboard())
    await callback.answer()

def _reminders_keyboard(items) -> InlineKeyboardMarkup:
    def _label(r):
        rep = "" if r.get("repeat", "none") == "none" else " 🔁"
        return f"❌ {format_due(r['due_ts'])}{rep} — {r['text'][:28]}"
    buttons = [
        [InlineKeyboardButton(text=_label(r), callback_data=f"remdel:{r['id']}")]
        for r in items
    ]
    buttons.append([InlineKeyboardButton(text=t("back"), callback_data="nav:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def _reminders_view(user_id: int):
    items = await list_reminders(user_id)
    if not items:
        return t("remind_list_empty"), _back_keyboard()
    return t("remind_list_title"), _reminders_keyboard(items)

@router.message(Command("reminders"))
async def cmd_reminders(message: Message):
    text, keyboard = await _reminders_view(message.from_user.id)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

@router.message(Command("remind"))
async def cmd_remind(message: Message, command: CommandObject, redis):
    """Explicit reminder: /remind завтра в 15:00 проверить бэкапы"""
    query = (command.args or "").strip()
    if not query:
        await message.answer(t("remind_usage"))
        return
    bot_message = await message.answer(t("remind_parsing"), parse_mode="HTML")
    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=query,
        history_content="",
        context_type="remind",
        history_id=history_key(message),
    )

@router.callback_query(F.data.startswith("remdel:"))
async def cb_remdel(callback: CallbackQuery):
    reminder_id = callback.data.split(":", 1)[1]
    if reminder_id.isdigit():
        await delete_reminder(int(reminder_id), callback.from_user.id)
    await callback.answer(t("remind_deleted"))
    text, keyboard = await _reminders_view(callback.from_user.id)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data == "nav:voice")
async def cb_nav_voice(callback: CallbackQuery):
    """Toggle the personal 'answer voice with voice' preference."""
    new_state = not await get_voice_pref(callback.from_user.id)
    await set_voice_pref(callback.from_user.id, new_state)
    await callback.answer(t("voice_toggled_on" if new_state else "voice_toggled_off"))
    await callback.message.edit_text(
        t("menu_title"), parse_mode="HTML",
        reply_markup=await _main_menu_keyboard(callback.from_user.id)
    )

@router.callback_query(F.data == "nav:reminders")
async def cb_nav_reminders(callback: CallbackQuery):
    text, keyboard = await _reminders_view(callback.from_user.id)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

async def _main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = _base_menu_buttons()
    # Personal voice-reply toggle (only when the TTS feature is enabled)
    if VOICE_REPLIES:
        voice_on = await get_voice_pref(user_id)
        buttons.append([InlineKeyboardButton(
            text=t("menu_voice_on" if voice_on else "menu_voice_off"),
            callback_data="nav:voice",
        )])
    # The stats button is shown only to the actual admin - everyone else
    # would just get an "admins only" alert when tapping it
    if await get_admin_id() == user_id:
        buttons[-1].append(InlineKeyboardButton(text=t("menu_stats"), callback_data="nav:stats"))
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        t("menu_title"), parse_mode="HTML",
        reply_markup=await _main_menu_keyboard(message.from_user.id)
    )

@router.callback_query(F.data == "nav:main")
async def cb_nav_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        t("menu_title"), parse_mode="HTML",
        reply_markup=await _main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()

@router.callback_query(F.data == "nav:model")
async def cb_nav_model(callback: CallbackQuery):
    current = await _resolve_model(await get_user_model(callback.from_user.id) or TEXT_MODEL)
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
    admin_id = await get_admin_id()
    if not admin_id or callback.from_user.id != admin_id:
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
    await react_seen(message)
    bot_message = await message.answer(t("searching"), parse_mode="HTML")

    search_results = await gather_web_context(query)

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

@router.callback_query(F.data == "nav:imagine")
async def cb_nav_imagine(callback: CallbackQuery, state: FSMContext):
    if not IMAGEGEN_ENABLED:
        await callback.answer(t("image_gen_unavailable"), show_alert=True)
        return
    await state.set_state(MenuStates.waiting_imagine_prompt)
    await callback.message.edit_text(t("imagine_prompt"), reply_markup=_back_keyboard())
    await callback.answer()

async def _run_image_generation(message: Message, redis, prompt: str):
    # Image generation is GPU-heavy and serialized to one job at a time, so
    # it needs the same per-user rate limit as LLM jobs - otherwise one user
    # could flood /imagine and monopolize the GPU for everyone.
    if await over_rate_limit(redis, message.from_user.id):
        await message.answer(t("rate_limited", limit=RATE_LIMIT_PER_MINUTE))
        return
    status = await message.answer(t("generating_image"), parse_mode="HTML")
    image_bytes = await generate_image(prompt)
    if not image_bytes:
        await status.edit_text(t("image_gen_failed"))
        return
    await status.delete()
    await message.answer_photo(
        BufferedInputFile(image_bytes, filename="image.png"),
        caption=prompt[:1000]
    )

@router.message(Command("imagine"))
async def cmd_imagine(message: Message, command: CommandObject, redis):
    """Handler for explicit image generation (see imagegen/README.md)."""
    if not IMAGEGEN_ENABLED:
        await message.answer(t("image_gen_unavailable"))
        return
    prompt = (command.args or "").strip()
    if not prompt:
        await message.answer(t("imagine_usage"))
        return
    await _run_image_generation(message, redis, prompt)

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

    # Same idea, for "Generate an image" in /menu.
    if await state.get_state() == MenuStates.waiting_imagine_prompt.state:
        await state.clear()
        prompt = message.text.strip()
        if not prompt:
            await message.answer(t("imagine_usage"))
            return
        await _run_image_generation(message, redis, prompt)
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
    await react_seen(message)  # 👀 "seen, working on it"
    # "напомни завтра..." becomes a reminder, not a chat turn
    if is_reminder_request(text):
        bot_message = await message.answer(t("remind_parsing"), parse_mode="HTML")
        await enqueue_llm_job(
            redis, message, bot_message,
            prompt=text,
            history_content="",
            context_type="remind",
            history_id=history_key(message),
        )
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
