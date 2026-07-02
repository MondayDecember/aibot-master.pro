"""All user-facing bot strings in one place, switched by BOT_LANGUAGE in .env.

Model replies are not affected - the LLM answers in whatever language the
user writes in. This only covers the bot's own interface messages.
"""
from config import BOT_LANGUAGE

_TEXTS = {
    "en": {
        "start": (
            "Hello! I am your AI assistant. Send me text, voice messages, photos, "
            "or documents (PDF / plain text), use /web <query> to search the web, "
            "/model to switch the text model, or /persona to change my personality."
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
        "doc_truncated": "\n\n[The document was truncated to the first {n} characters]",
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
            "📊 <b>Bot stats</b>\n"
            "Users: {users}\n"
            "Messages total: {messages}\n"
            "Messages today: {today}\n"
            "Queue length: {queue}\n"
            "Database size: {db_size}"
        ),
        "help": (
            "🤖 <b>What I can do</b>\n"
            "• Text - just write me a message\n"
            "• Photos - I describe them or answer the question in the caption\n"
            "• Voice messages - I transcribe and answer\n"
            "• Documents (PDF / plain text) - I answer questions about the content\n\n"
            "<b>Commands</b>\n"
            "/web &lt;query&gt; - search the web\n"
            "/model - switch the text model\n"
            "/persona - change my personality\n"
            "/clear - clear conversation history\n"
            "/stats - bot statistics (admin only)\n\n"
            "In groups I answer @mentions and replies to my messages."
        ),
        "admin_alert": "⚠️ Bot error:\n{error}",
        "desc_help": "What the bot can do",
        "desc_clear": "Clear conversation history",
        "desc_web": "Search the web",
        "desc_model": "Switch the text model",
        "desc_persona": "Change the bot's personality",
        "desc_stats": "Bot statistics (admin)",
    },
    "ru": {
        "start": (
            "Привет! Я ваш ИИ-ассистент. Отправьте мне текст, голосовое сообщение, "
            "фото или документ (PDF / текстовый файл). Команды: /web <запрос> — поиск "
            "в интернете, /model — сменить модель, /persona — сменить характер бота."
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
        "doc_truncated": "\n\n[Документ обрезан до первых {n} символов]",
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
            "📊 <b>Статистика бота</b>\n"
            "Пользователей: {users}\n"
            "Сообщений всего: {messages}\n"
            "Сообщений сегодня: {today}\n"
            "В очереди: {queue}\n"
            "Размер базы: {db_size}"
        ),
        "help": (
            "🤖 <b>Что я умею</b>\n"
            "• Текст — просто напишите сообщение\n"
            "• Фото — опишу или отвечу на вопрос из подписи\n"
            "• Голосовые — распознаю речь и отвечу\n"
            "• Документы (PDF / текст) — отвечу по содержимому\n\n"
            "<b>Команды</b>\n"
            "/web &lt;запрос&gt; — поиск в интернете\n"
            "/model — сменить модель\n"
            "/persona — сменить характер бота\n"
            "/clear — очистить историю диалога\n"
            "/stats — статистика (для администратора)\n\n"
            "В группах отвечаю на @упоминания и реплаи на мои сообщения."
        ),
        "admin_alert": "⚠️ Ошибка бота:\n{error}",
        "desc_help": "Что умеет бот",
        "desc_clear": "Очистить историю диалога",
        "desc_web": "Поиск в интернете",
        "desc_model": "Сменить модель",
        "desc_persona": "Сменить характер бота",
        "desc_stats": "Статистика (админ)",
    },
}


def t(_key: str, **kwargs) -> str:
    # Parameter is named _key, not key: the "switched_to" template takes a
    # {key} placeholder, and t("switched_to", key=...) would otherwise
    # collide with a same-named positional parameter (TypeError: got
    # multiple values for argument 'key').
    lang = _TEXTS.get(BOT_LANGUAGE, _TEXTS["en"])
    template = lang.get(_key) or _TEXTS["en"][_key]
    return template.format(**kwargs) if kwargs else template
