#!/usr/bin/env python3
"""Interactive .env configurator.

Runs INSIDE the bot container (it always has python) via configure.sh /
configure.ps1, which mount the host .env into /app/.env and restart the bot
after the changes are saved. No python needed on the host.
"""
import argparse
import re
import sys

AUTOUPDATE_VALUE = "docker-compose.yml{sep}docker-compose.autoupdate.yml"

# (key, title, kind, hint)
SETTINGS = [
    ("BOT_TOKEN", "Токен бота (@BotFather)", "str",
     "Без него бот не запустится. Получить: напишите /newbot боту @BotFather в Telegram."),
    ("BOT_LANGUAGE", "Язык интерфейса бота", "choice:ru,en",
     "ru — русский, en — английский. На ответы нейросети не влияет."),
    ("ALLOWED_USER_IDS", "Кто может пользоваться ботом", "ids",
     "Telegram ID через запятую; пусто = открыт всем. Свой ID покажет @userinfobot."),
    ("ADMIN_USER_ID", "Администратор (/stats и ошибки)", "int_opt",
     "Пусто = первый ID из списка выше."),
    ("RATE_LIMIT_PER_MINUTE", "Лимит запросов в минуту на человека", "int",
     "0 = без лимита."),
    ("AUTO_WEB_SEARCH", "Автоматический поиск в интернете", "bool",
     "false = ответы примерно вдвое быстрее; команда /web работает всегда."),
    ("STREAM_RESPONSES", "Показывать ответ по мере генерации", "bool", ""),
    ("REACT_ON_SEEN", "Реакция 👀 на сообщение («увидел»)", "bool",
     "Ставит эмодзи-реакцию, когда бот принял сообщение в работу."),
    ("HISTORY_LIMIT", "Сколько последних сообщений бот видит целиком", "int",
     "Больше = лучше память, но медленнее ответы."),
    ("LONG_TERM_MEMORY", "Долгая память (выжимка старых сообщений)", "bool", ""),
    ("GROUP_CHATTINESS", "Болтливость в группах, %", "int",
     "Шанс вкинуть реплику в беседу без обращения. 0 = молчит, 5-10 — комфортно."),
    ("TEXT_MODEL", "Текстовая модель", "str",
     "Модель должна быть скачана в Ollama: ollama pull <модель>."),
    ("MODEL_NUM_CTX", "Размер контекста модели (токенов)", "int",
     "0 = по умолчанию модели. Больше (напр. 8192) = помнит больше, но нужно больше памяти."),
    ("SHOW_TOKENS", "Показывать счётчик токенов под ответом", "bool", ""),
    ("USAGE_STATS", "Вести журнал обращений к нейросети (/usage)", "bool", ""),
    ("VISION_MODEL", "Модель для картинок", "str", ""),
    ("MODEL_CHOICES", "Список моделей для /model", "str",
     "Формат: имя=модель,имя=модель. Пусто = только основная модель."),
    ("WHISPER_MODEL", "Распознавание речи", "str",
     "base (быстро) / small / medium / large-v3 (точно)."),
    ("SUMMARY_MODEL", "Модель для памяти и напоминаний", "str",
     "Пусто = основная. Лёгкая (llama3.2:3b) делает фоновые задачи быстрее."),
    ("TIMEZONE", "Часовой пояс (напоминания, «сейчас»)", "str",
     "IANA-имя, например Europe/Moscow или Asia/Tomsk."),
    ("VOICE_REPLIES", "Голосовые ответы на голосовые сообщения", "bool",
     "Локальный TTS (Piper), без GPU. false = бот всегда отвечает только текстом."),
    ("TTS_VOICE", "Голос для TTS", "str",
     "Имя из https://github.com/rhasspy/piper/blob/master/VOICES.md, напр. ru_RU-dmitri-medium."),
    ("TTS_MAX_CHARS", "Макс. длина ответа для озвучки, символов", "int",
     "Длинные ответы обрезаются перед синтезом речи."),
    ("IMAGEGEN_ENABLED", "Генерация картинок (/imagine)", "bool",
     "Нужен отдельный запущенный сервис imagegen/ на хосте - см. imagegen/README.md."),
    ("IMAGEGEN_API_BASE", "Адрес сервиса генерации картинок", "str",
     "По умолчанию http://host.docker.internal:7861 - меняйте только если запустили imagegen на другом порту/хосте."),
]


def read_env(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def get_value(lines, key):
    """Value of an active (non-commented) KEY= line, or None."""
    pattern = re.compile(rf"\s*{re.escape(key)}=(.*)")
    for line in lines:
        if line.lstrip().startswith("#"):
            continue
        m = pattern.match(line)
        if m:
            return m.group(1).strip()
    return None


def set_value(lines, key, value):
    """Replace the active KEY= line; else uncomment a '# KEY=' example line;
    else append. Returns the modified list."""
    new_line = f"{key}={value}"
    active = re.compile(rf"\s*{re.escape(key)}=")
    commented = re.compile(rf"\s*#\s*{re.escape(key)}=")
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("#") and active.match(line):
            lines[i] = new_line
            return lines
    for i, line in enumerate(lines):
        if commented.match(line):
            lines[i] = new_line
            return lines
    lines.append(new_line)
    return lines


def comment_out(lines, key):
    """Comment the active KEY= line (used to switch auto-update off)."""
    for i, line in enumerate(lines):
        if not line.lstrip().startswith("#") and re.match(rf"\s*{re.escape(key)}=", line):
            lines[i] = "# " + line.strip()
    return lines


def _ask(prompt):
    """Returns the stripped input, or None when stdin is closed (no TTY) -
    the caller must treat None as 'quit', otherwise the menu loops forever."""
    try:
        return input(prompt).strip()
    except EOFError:
        return None


def _edit_setting(lines, key, title, kind, hint):
    current = get_value(lines, key)
    print(f"\n{title}")
    if hint:
        print(f"  {hint}")
    print(f"  Сейчас: {current if current not in (None, '') else '(не задано)'}")
    raw = _ask("  Новое значение (Enter = не менять): ")
    if raw is None or not raw:
        return lines
    if kind.startswith("choice:"):
        options = kind.split(":", 1)[1].split(",")
        if raw.lower() not in options:
            print(f"  ! Допустимо только: {', '.join(options)}")
            return lines
        raw = raw.lower()
    elif kind == "bool":
        if raw.lower() in ("true", "да", "y", "yes", "1", "вкл"):
            raw = "true"
        elif raw.lower() in ("false", "нет", "n", "no", "0", "выкл"):
            raw = "false"
        else:
            print("  ! Введите true или false (да/нет)")
            return lines
    elif kind == "int":
        if not raw.isdigit():
            print("  ! Нужно число")
            return lines
    elif kind == "int_opt":
        if raw != "-" and not raw.isdigit():
            print("  ! Нужно число (или '-' чтобы очистить)")
            return lines
        if raw == "-":
            raw = ""
    elif kind == "ids":
        if raw == "-":
            raw = ""
        elif not re.fullmatch(r"\d+(\s*,\s*\d+)*", raw):
            print("  ! Нужны числа через запятую (или '-' чтобы открыть бота всем)")
            return lines
    return set_value(lines, key, raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env")
    parser.add_argument("--sep", default=":",
                        help="COMPOSE_FILE path separator on the HOST (':' linux/mac, ';' windows)")
    args = parser.parse_args()

    try:
        lines = read_env(args.env)
    except OSError as e:
        print(f"Не удалось открыть {args.env}: {e}")
        return 1

    autoupdate_value = AUTOUPDATE_VALUE.format(sep=args.sep)

    while True:
        print("\n=== Настройки aibot-master ===")
        for idx, (key, title, _kind, _hint) in enumerate(SETTINGS, 1):
            current = get_value(lines, key)
            if key == "BOT_TOKEN" and current == "your_telegram_bot_token_here":
                current = None  # untouched .env.example placeholder = not set
            shown = current if current not in (None, "") else "(не задано)"
            if key == "BOT_TOKEN" and current and len(current) > 12:
                # Don't print the whole secret on screen
                shown = current[:6] + "…" + current[-4:]
            print(f" {idx:2}. {title:<48} : {shown}")
        auto_on = bool(get_value(lines, "COMPOSE_FILE"))
        auto_idx = len(SETTINGS) + 1
        print(f" {auto_idx:2}. {'Автообновление (Watchtower)':<48} : {'включено' if auto_on else 'выключено'}")
        print("  0. Сохранить и выйти")
        print("  q. Выйти без сохранения")

        choice = _ask("\nЧто изменить? ")
        if choice is None or choice == "q":
            print("Изменения отброшены.")
            return 2
        if choice == "0":
            try:
                with open(args.env, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(lines) + "\n")
            except OSError as e:
                print(f"Не удалось сохранить: {e}")
                return 1
            print("Настройки сохранены.")
            return 0
        if choice == str(auto_idx):
            if auto_on:
                lines = comment_out(lines, "COMPOSE_FILE")
                print("  Автообновление выключено (после выхода бот пересоберётся локально).")
            else:
                lines = set_value(lines, "COMPOSE_FILE", autoupdate_value)
                print("  Автообновление включено: бот перейдёт на готовый образ и будет")
                print("  сам обновляться в течение ~10 минут после каждого обновления на GitHub.")
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(SETTINGS):
            key, title, kind, hint = SETTINGS[int(choice) - 1]
            lines = _edit_setting(lines, key, title, kind, hint)
        else:
            print("Введите номер пункта, 0 или q.")


if __name__ == "__main__":
    sys.exit(main())
