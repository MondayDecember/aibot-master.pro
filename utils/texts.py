"""All user-facing bot strings in one place, switched by BOT_LANGUAGE in .env.

Model replies are not affected - the LLM answers in whatever language the
user writes in. This only covers the bot's own interface messages.
"""
import contextvars

from config import BOT_LANGUAGE

_TEXTS = {
    "en": {
        "start": (
            "Hello! I am your AI assistant. Send me text, voice messages, photos, "
            "or documents (PDF / plain text), use /web &lt;query&gt; to search the web, "
            "/model to switch the text model, /persona to change my personality, "
            "or /menu to see all of that in one place."
        ),
        "cleared": "Conversation history cleared!",
        "current_model": "Current text model: <code>{model}</code>\nPick one:",
        "unknown_model": "Unknown model",
        "model_switched": "Text model switched to: <code>{model}</code>",
        "switched_to": "Switched to {key}",
        "current_persona": "Current persona: <b>{persona}</b>\nPick one:",
        "unknown_persona": "Unknown persona",
        "persona_switched": "Persona switched to: <b>{persona}</b>",
        "web_usage": "Please provide a search query. Example: /web current weather in London",
        "searching": "<i>Searching the web...</i>",
        "thinking": "<i>Thinking...</i>",
        "generating": "<i>Generating response...</i>",
        "processing_image": "<i>Processing image...</i>",
        "image_failed": "Sorry, failed to process the image.",
        "image_default_caption": "What's in this image?",
        "transcribing": "<i>Transcribing voice message...</i>",
        "heard": "<i>Heard:</i> {text}\n\n<i>Thinking...</i>",
        "voice_unavailable": "Voice transcription is currently unavailable (model not loaded).",
        "voice_error": "Error processing voice message: {error}",
        "voice_empty": "Couldn't recognize any speech in the voice message.",
        "reading_document": "<i>Reading document...</i>",
        "doc_default_caption": "Summarize this document.",
        "doc_too_large": "The file is too large - telegram bots can only download files up to 20 MB.",
        "doc_unsupported": (
            "Unsupported file type. Send a PDF or a plain-text file "
            "(.txt, .md, .csv, code files etc.)."
        ),
        "doc_download_failed": "Sorry, failed to download the file from telegram.",
        "doc_unreadable": "Sorry, couldn't read this file - it may be corrupted.",
        "doc_no_text": (
            "Couldn't extract any text from this file. If it's a scanned PDF, "
            "it contains images instead of text - try sending pages as photos."
        ),
        "doc_truncated": "\n\n[The document is too long for my context window ({n} chars) - showing excerpts from the beginning, middle, and end rather than the whole thing]",
        "error_generic": "Sorry, I encountered an error processing your request.",
        "llm_unavailable": "I'm sorry, I couldn't process that request at the moment.",
        "empty_response": "The model returned an empty response.",
        "access_denied_short": "Access denied.",
        "access_denied": (
            "Access denied. Your Telegram ID: {user_id}\n"
            "Ask the bot owner to add it to ALLOWED_USER_IDS in .env."
        ),
        "rate_limited": "Too many requests - you can send up to {limit} per minute. Try again in a bit.",
        "queue_position": "<i>Waiting in queue (position {n})...</i>",
        "stats_admin_only": "This command is only available to the bot admin (ADMIN_USER_ID).",
        "stats": (
            "📊 <b>Bot stats</b>\n\n"
            "👥 Users: <b>{users}</b>\n"
            "💬 Messages total: <b>{messages}</b>\n"
            "📅 Today: <b>{today}</b>\n"
            "⏳ Queue: <b>{queue}</b>\n"
            "💾 Database: <b>{db_size}</b>"
        ),
        "help": (
            "🤖 <b>What I can do</b>\n"
            "• Text - just write me a message\n"
            "• Photos - I describe them or answer the question in the caption\n"
            "• Voice messages - I transcribe and answer\n"
            "• Documents (PDF / plain text) - I answer questions about the content\n\n"
            "<b>Commands</b>\n"
            "/web &lt;query&gt; - search the web\n"
            "/reminders - my reminders (set one by just writing «remind me tomorrow at 10...»)\n"
            "/model - switch the text model\n"
            "/persona - change my personality\n"
            "/clear - clear conversation history\n"
            "/menu - all of the above as buttons\n"
            "/stats - bot statistics (admin only)\n"
            "/admin - become the admin (when none is set) or transfer adminship\n\n"
            "In groups I answer @mentions and replies to my messages."
        ),
        "remind_parsing": "<i>⏰ Setting up the reminder...</i>",
        "remind_set": "⏰ Done! I'll remind you on {when}:\n«{text}»\n\nYour reminders: /reminders",
        "remind_parse_failed": (
            "Couldn't figure out when to remind you. Say the time explicitly, "
            "e.g.: «remind me tomorrow at 15:00 to check the server»."
        ),
        "remind_usage": "Usage: /remind tomorrow at 15:00 check the backups",
        "reminder_fire": "🔔 Reminder: {text}",
        "remind_list_title": "⏰ <b>Your reminders</b>\nTap one to delete it:",
        "remind_list_empty": (
            "You have no active reminders. Just write or say: "
            "«remind me tomorrow at 10 to call the clinic»."
        ),
        "remind_deleted": "Reminder deleted.",
        "menu_reminders": "⏰ Reminders",
        "desc_reminders": "My reminders",
        "menu_voice_on": "🔊 Voice replies: on",
        "menu_voice_off": "🔇 Voice replies: off",
        "voice_toggled_on": "Now I'll answer voice messages with voice.",
        "voice_toggled_off": "Voice replies are off - text only.",
        "voice_reply_note": "🔊 Answered with a voice message ↓",
        "admin_alert": "⚠️ Bot error:\n{error}",
        "admin_claimed": (
            "👑 You are now the bot administrator!\n"
            "You get /stats and error alerts. Transfer: /admin &lt;user_id&gt;"
        ),
        "admin_current": "👑 Current administrator ID: <code>{admin_id}</code>\nTransfer: /admin &lt;user_id&gt;",
        "admin_usage": "Usage: /admin &lt;telegram user id&gt;",
        "admin_claim_private": "Adminship can only be claimed in a private chat with the bot.",
        "admin_env_locked": (
            "The administrator is set in .env (ADMIN_USER_ID / ALLOWED_USER_IDS) - "
            "change it there or via the configurator on the server."
        ),
        "admin_transferred": "👑 Administrator transferred to <code>{admin_id}</code>.",
        "desc_help": "What the bot can do",
        "desc_clear": "Clear conversation history",
        "desc_web": "Search the web",
        "desc_model": "Switch the text model",
        "desc_persona": "Change the bot's personality",
        "desc_stats": "Bot statistics (admin)",
        "desc_menu": "Open the menu",
        "desc_imagine": "Generate an image",
        "menu_title": (
            "✨ <b>Control panel</b>\n\n"
            "Pick a section — everything here is personal to you: "
            "your model, your persona, your history."
        ),
        "menu_model": "🤖 Switch model",
        "menu_persona": "🎭 Switch persona",
        "menu_clear": "🧹 Clear history",
        "menu_help": "❓ Help",
        "menu_stats": "📊 Stats",
        "menu_web": "🔍 Search the web",
        "menu_imagine": "🎨 Generate an image",
        "back": "◀ Back",
        "persona_default": "🙂 Default",
        "persona_pirate": "🏴‍☠️ Pirate",
        "persona_yoda": "🧙 Yoda",
        "persona_sarcastic": "😏 Sarcastic",
        "persona_scientist": "🔬 Scientist",
        "web_prompt": "What should I search for? Send it as your next message.",
        "imagine_usage": "Describe the image. Example: /imagine a lighthouse at sunset, watercolor",
        "imagine_prompt": "Describe the image you want. Send it as your next message.",
        "generating_image": "<i>Generating the image (can take a while on first request)...</i>",
        "image_gen_unavailable": (
            "Image generation isn't set up - see imagegen/README.md. "
            "It runs as a separate local service, not part of the bot itself."
        ),
        "image_gen_failed": "Sorry, image generation failed - the imagegen service may not be running.",
        "new_done": "🆕 Started a fresh dialog. I no longer use the earlier history (it's kept, not deleted).",
        "menu_new": "🆕 New dialog",
        "desc_new": "Start a fresh dialog",
        "menu_language": "🌐 Language / Язык",
        "language_prompt": "Choose the interface language:",
        "language_set": "Language switched to English.",
        "desc_language": "Interface language",
        "desc_dice": "Dice, coin, random pick",
        "dice_number": "🎲 {n}",
        "dice_coin": "🪙 {side}",
        "dice_heads": "Heads",
        "dice_tails": "Tails",
        "dice_choice": "🎯 {choice}",
        "roll_usage": "Format: /roll 2d6, /roll d20+3, /roll d6",
        "roll_result": "🎲 {expr}: {rolls} = <b>{total}</b>",
        "eightball_prefix": "🎱 {answer}",
        "eightball_answers": "It is certain\nYes\nMost likely\nSigns point to yes\nReply hazy, try again\nAsk again later\nDon't count on it\nMy answer is no\nVery doubtful",
        "desc_roll": "Dice notation roll (2d6, d20+3)",
        "desc_8ball": "Magic 8-ball",
        "btn_voice": "🔊 Voice",
        "whoami": (
            "🪪 <b>Your settings</b>\n"
            "ID: <code>{id}</code>\n"
            "Model: <code>{model}</code>\n"
            "Persona: {persona}\n"
            "Language: {lang}\n"
            "Voice replies: {voice}\n"
            "Personal instructions: {prompt}"
        ),
        "desc_whoami": "Your ID and settings",
        "yes_word": "on",
        "no_word": "off",
        "none_word": "—",
        "setprompt_usage": "Send: /setprompt your instructions. Show current: /setprompt. Remove: /setprompt -",
        "setprompt_current": "Your personal instructions:\n<i>{text}</i>\n\nChange: /setprompt <text>. Remove: /setprompt -",
        "setprompt_none": "No personal instructions yet. Set them: /setprompt <text> (e.g. \"answer briefly\").",
        "setprompt_set": "Done - I'll keep your instructions in mind.",
        "setprompt_cleared": "Personal instructions removed.",
        "desc_setprompt": "Personal instructions",
        "summary_working": "<i>📝 Summarizing...</i>",
        "summary_result": "📝 <b>Summary</b>\n{text}",
        "summary_empty": "Nothing to summarize yet - write a few messages first.",
        "desc_summary": "Summarize this dialog",
        "repeat_daily": "(every day)",
        "repeat_weekdays": "(on weekdays)",
        "repeat_weekly": "(every week)",
        "repeat_monthly": "(every month)",
        "btn_stop": "⏹ Stop",
        "btn_regen": "↻ Another answer",
        "stopped_note": "(stopped)",
        "regenerating": "Generating another answer...",
        "regen_none": "Nothing to regenerate - send a new message.",
        "stopping": "Stopping...",
    },
    "ru": {
        "start": (
            "Привет! Я ваш ИИ-ассистент. Отправьте мне текст, голосовое сообщение, "
            "фото или документ (PDF / текстовый файл). Команды: /web &lt;запрос&gt; — поиск "
            "в интернете, /model — сменить модель, /persona — сменить характер бота, "
            "/menu — открыть всё это одним меню."
        ),
        "cleared": "История диалога очищена!",
        "current_model": "Текущая модель: <code>{model}</code>\nВыберите:",
        "unknown_model": "Неизвестная модель",
        "model_switched": "Модель переключена на: <code>{model}</code>",
        "switched_to": "Выбрано: {key}",
        "current_persona": "Текущий персонаж: <b>{persona}</b>\nВыберите:",
        "unknown_persona": "Неизвестный персонаж",
        "persona_switched": "Персонаж переключён на: <b>{persona}</b>",
        "web_usage": "Укажите запрос. Пример: /web погода в Лондоне",
        "searching": "<i>Ищу в интернете...</i>",
        "thinking": "<i>Думаю...</i>",
        "generating": "<i>Генерирую ответ...</i>",
        "processing_image": "<i>Обрабатываю изображение...</i>",
        "image_failed": "Не удалось обработать изображение.",
        "image_default_caption": "Что на этом изображении?",
        "transcribing": "<i>Распознаю голосовое сообщение...</i>",
        "heard": "<i>Услышал:</i> {text}\n\n<i>Думаю...</i>",
        "voice_unavailable": "Распознавание речи сейчас недоступно (модель не загружена).",
        "voice_error": "Ошибка обработки голосового сообщения: {error}",
        "voice_empty": "Не удалось распознать речь в голосовом сообщении.",
        "reading_document": "<i>Читаю документ...</i>",
        "doc_default_caption": "Кратко перескажи этот документ.",
        "doc_too_large": "Файл слишком большой — Telegram позволяет ботам скачивать файлы до 20 МБ.",
        "doc_unsupported": (
            "Неподдерживаемый тип файла. Пришлите PDF или текстовый файл "
            "(.txt, .md, .csv, файлы кода и т.п.)."
        ),
        "doc_download_failed": "Не удалось скачать файл из Telegram.",
        "doc_unreadable": "Не удалось прочитать файл — возможно, он повреждён.",
        "doc_no_text": (
            "В файле не нашлось текста. Если это сканированный PDF, в нём картинки "
            "вместо текста — попробуйте прислать страницы как фото."
        ),
        "doc_truncated": "\n\n[Документ длиннее, чем позволяет контекст модели ({n} симв.) - показаны отрывки из начала, середины и конца, а не целиком]",
        "error_generic": "Извините, при обработке запроса произошла ошибка.",
        "llm_unavailable": "Извините, сейчас не получилось обработать запрос.",
        "empty_response": "Модель вернула пустой ответ.",
        "access_denied_short": "Доступ запрещён.",
        "access_denied": (
            "Доступ запрещён. Ваш Telegram ID: {user_id}\n"
            "Попросите владельца бота добавить его в ALLOWED_USER_IDS."
        ),
        "rate_limited": "Слишком много запросов — можно не больше {limit} в минуту. Попробуйте чуть позже.",
        "queue_position": "<i>В очереди (позиция {n})...</i>",
        "stats_admin_only": "Эта команда доступна только администратору бота (ADMIN_USER_ID).",
        "stats": (
            "📊 <b>Статистика бота</b>\n\n"
            "👥 Пользователей: <b>{users}</b>\n"
            "💬 Сообщений всего: <b>{messages}</b>\n"
            "📅 Сегодня: <b>{today}</b>\n"
            "⏳ В очереди: <b>{queue}</b>\n"
            "💾 База: <b>{db_size}</b>"
        ),
        "help": (
            "🤖 <b>Что я умею</b>\n"
            "• Текст — просто напишите сообщение\n"
            "• Фото — опишу или отвечу на вопрос из подписи\n"
            "• Голосовые — распознаю речь и отвечу\n"
            "• Документы (PDF / текст) — отвечу по содержимому\n\n"
            "<b>Команды</b>\n"
            "/web &lt;запрос&gt; — поиск в интернете\n"
            "/reminders — мои напоминания (поставить: просто напишите «напомни завтра в 10...»)\n"
            "/model — сменить модель\n"
            "/persona — сменить характер бота\n"
            "/clear — очистить историю диалога\n"
            "/menu — всё то же самое кнопками\n"
            "/stats — статистика (для администратора)\n"
            "/admin — стать администратором (если он не назначен) или передать права\n\n"
            "В группах отвечаю на @упоминания и реплаи на мои сообщения."
        ),
        "remind_parsing": "<i>⏰ Ставлю напоминание...</i>",
        "remind_set": "⏰ Готово! Напомню {when}:\n«{text}»\n\nВаши напоминания: /reminders",
        "remind_parse_failed": (
            "Не понял, когда напомнить. Скажите время явно, например: "
            "«напомни завтра в 15:00 проверить сервер»."
        ),
        "remind_usage": "Использование: /remind завтра в 15:00 проверить бэкапы",
        "reminder_fire": "🔔 Напоминаю: {text}",
        "remind_list_title": "⏰ <b>Ваши напоминания</b>\nНажмите на напоминание, чтобы удалить:",
        "remind_list_empty": (
            "У вас нет активных напоминаний. Просто напишите или наговорите: "
            "«напомни завтра в 10 позвонить в клинику»."
        ),
        "remind_deleted": "Напоминание удалено.",
        "menu_reminders": "⏰ Напоминания",
        "desc_reminders": "Мои напоминания",
        "menu_voice_on": "🔊 Голосовые ответы: вкл",
        "menu_voice_off": "🔇 Голосовые ответы: выкл",
        "voice_toggled_on": "Теперь на голосовые отвечаю голосом.",
        "voice_toggled_off": "Голосовые ответы выключены — отвечаю текстом.",
        "voice_reply_note": "🔊 Ответил голосовым ↓",
        "admin_alert": "⚠️ Ошибка бота:\n{error}",
        "admin_claimed": (
            "👑 Теперь вы администратор бота!\n"
            "Вам доступна /stats и оповещения об ошибках. Передать права: /admin &lt;id&gt;"
        ),
        "admin_current": "👑 Текущий администратор: <code>{admin_id}</code>\nПередать права: /admin &lt;id&gt;",
        "admin_usage": "Использование: /admin &lt;telegram id пользователя&gt;",
        "admin_claim_private": "Стать администратором можно только в личном чате с ботом.",
        "admin_env_locked": (
            "Администратор задан в настройках сервера (.env: ADMIN_USER_ID / ALLOWED_USER_IDS) — "
            "изменить его можно там или через конфигуратор."
        ),
        "admin_transferred": "👑 Права администратора переданы <code>{admin_id}</code>.",
        "desc_help": "Что умеет бот",
        "desc_clear": "Очистить историю диалога",
        "desc_web": "Поиск в интернете",
        "desc_model": "Сменить модель",
        "desc_persona": "Сменить характер бота",
        "desc_stats": "Статистика (админ)",
        "desc_menu": "Открыть меню",
        "desc_imagine": "Сгенерировать картинку",
        "menu_title": (
            "✨ <b>Панель управления</b>\n\n"
            "Выберите раздел — всё настраивается лично для вас: "
            "своя модель, свой персонаж, своя история."
        ),
        "menu_model": "🤖 Сменить модель",
        "menu_persona": "🎭 Сменить персонажа",
        "menu_clear": "🧹 Очистить историю",
        "menu_help": "❓ Помощь",
        "menu_stats": "📊 Статистика",
        "menu_web": "🔍 Поиск в интернете",
        "menu_imagine": "🎨 Сгенерировать картинку",
        "back": "◀ Назад",
        "persona_default": "🙂 Обычный",
        "persona_pirate": "🏴‍☠️ Пират",
        "persona_yoda": "🧙 Йода",
        "persona_sarcastic": "😏 Саркастичный",
        "persona_scientist": "🔬 Учёный",
        "web_prompt": "Что искать? Напишите запрос следующим сообщением.",
        "imagine_usage": "Опишите картинку. Пример: /imagine маяк на закате, акварель",
        "imagine_prompt": "Опишите картинку, которую хотите получить. Напишите следующим сообщением.",
        "generating_image": "<i>Генерирую картинку (первый раз может занять время)...</i>",
        "image_gen_unavailable": (
            "Генерация картинок не настроена — см. imagegen/README.md. "
            "Это отдельный локальный сервис, не часть самого бота."
        ),
        "image_gen_failed": "Не удалось сгенерировать картинку — возможно, сервис imagegen сейчас не запущен.",
        "new_done": "🆕 Начат новый диалог. Прошлую переписку я больше не учитываю (она сохранена, не удалена).",
        "menu_new": "🆕 Новый диалог",
        "desc_new": "Начать новый диалог",
        "menu_language": "🌐 Язык / Language",
        "language_prompt": "Выберите язык интерфейса:",
        "language_set": "Язык переключён на русский.",
        "desc_language": "Язык интерфейса",
        "desc_dice": "Кубик, монетка, случайный выбор",
        "dice_number": "🎲 {n}",
        "dice_coin": "🪙 {side}",
        "dice_heads": "Орёл",
        "dice_tails": "Решка",
        "dice_choice": "🎯 {choice}",
        "roll_usage": "Формат: /roll 2d6, /roll d20+3, /roll d6",
        "roll_result": "🎲 {expr}: {rolls} = <b>{total}</b>",
        "eightball_prefix": "🎱 {answer}",
        "eightball_answers": "Бесспорно\nДа\nСкорее всего\nЗнаки говорят «да»\nПока не ясно, спроси ещё раз\nСпроси позже\nНе рассчитывай на это\nМой ответ — нет\nОчень сомнительно",
        "desc_roll": "Бросок кубиков (2d6, d20+3)",
        "desc_8ball": "Магический шар",
        "btn_voice": "🔊 Озвучить",
        "whoami": (
            "🪪 <b>Ваши настройки</b>\n"
            "ID: <code>{id}</code>\n"
            "Модель: <code>{model}</code>\n"
            "Персонаж: {persona}\n"
            "Язык: {lang}\n"
            "Голосовые ответы: {voice}\n"
            "Личные инструкции: {prompt}"
        ),
        "desc_whoami": "Ваш ID и настройки",
        "yes_word": "вкл",
        "no_word": "выкл",
        "none_word": "—",
        "setprompt_usage": "Отправьте: /setprompt ваши инструкции. Показать текущие: /setprompt. Убрать: /setprompt -",
        "setprompt_current": "Ваши личные инструкции:\n<i>{text}</i>\n\nИзменить: /setprompt <текст>. Убрать: /setprompt -",
        "setprompt_none": "Личных инструкций нет. Задать: /setprompt <текст> (например: «отвечай кратко»).",
        "setprompt_set": "Готово — буду учитывать ваши инструкции.",
        "setprompt_cleared": "Личные инструкции убраны.",
        "desc_setprompt": "Личные инструкции",
        "summary_working": "<i>📝 Собираю выжимку...</i>",
        "summary_result": "📝 <b>Краткое содержание</b>\n{text}",
        "summary_empty": "Пока нечего суммировать — напишите пару сообщений.",
        "desc_summary": "Кратко о диалоге",
        "repeat_daily": "(каждый день)",
        "repeat_weekdays": "(по будням)",
        "repeat_weekly": "(каждую неделю)",
        "repeat_monthly": "(каждый месяц)",
        "btn_stop": "⏹ Остановить",
        "btn_regen": "↻ Другой ответ",
        "stopped_note": "(остановлено)",
        "regenerating": "Генерирую другой ответ...",
        "regen_none": "Нечего перегенерировать — отправьте новое сообщение.",
        "stopping": "Останавливаю...",
    },
}


# Per-request language override. A middleware sets this from the user's
# stored preference at the start of each update; the worker sets it per job.
# Unset -> the global BOT_LANGUAGE from .env.
_current_lang = contextvars.ContextVar("current_lang", default=None)


def set_current_language(lang):
    """Set the language for t() calls in the current async task (or reset
    with None)."""
    _current_lang.set(lang if lang in _TEXTS else None)


def t(_key: str, **kwargs) -> str:
    # Parameter is named _key, not key: the "switched_to" template takes a
    # {key} placeholder, and t("switched_to", key=...) would otherwise
    # collide with a same-named positional parameter (TypeError: got
    # multiple values for argument 'key').
    lang_code = _current_lang.get() or BOT_LANGUAGE
    lang = _TEXTS.get(lang_code, _TEXTS["en"])
    template = lang.get(_key) or _TEXTS["en"][_key]
    return template.format(**kwargs) if kwargs else template
