# aibot-master

Telegram-бот на локальной LLM (Ollama), собранный на основе [m0wer/aibot](https://github.com/m0wer/aibot) с добавленными фичами из [mlloliveira/TelegramBot](https://github.com/mlloliveira/TelegramBot).

## Возможности

- **Текстовый чат** с историей диалога (SQLite, `data/bot_data.db`), не сбрасывается при рестарте.
- **Анализ изображений** — пришлите фото, бот опишет/ответит на вопрос по картинке (модель `VISION_MODEL`).
- **Голосовые сообщения** — распознавание речи через `faster-whisper`, транскрипция уходит в LLM.
- **Поиск в интернете** — бот сам решает через LLM-классификатор, нужны ли для ответа актуальные данные (новости, курсы, погода и т.п.), и в этом случае ищет через DuckDuckGo. Также доступна ручная команда `/web <запрос>`. Автоматическая проверка — это дополнительный запрос к LLM перед каждым ответом; если ответы кажутся медленными, поставьте `AUTO_WEB_SEARCH=false` в `.env` (ручной `/web` продолжит работать) и перезапустите: `docker compose up -d --build`.
- **Очередь на Redis** — все запросы к LLM идут через Redis (`BLPOP`/`RPUSH`), что защищает от перегрузки при одновременных сообщениях.

## Требования

- Docker + Docker Compose v2.
- Токен Telegram-бота от [@BotFather](https://t.me/BotFather).
- [Ollama](https://ollama.com) — либо уже запущенная на хосте (порт `11434`), либо установщик сам поднимет её в docker-контейнере.

## Быстрая установка (одна команда)

Установщик проверит Docker, спросит токен бота, сам найдёт Ollama на хосте (или запустит её в докере и скачает модели) и поднимет все контейнеры.

**Linux / macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/MondayDecember/aibot-master.pro/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/MondayDecember/aibot-master.pro/main/install.ps1 | iex
```

## Установка вручную

```bash
git clone https://github.com/MondayDecember/aibot-master.pro.git aibot-master
cd aibot-master
mkdir -p data          # папка для БД; создайте её ДО запуска, иначе docker создаст её от root
cp .env.example .env   # на Windows: copy .env.example .env
```

Откройте `.env` и заполните:

```
BOT_TOKEN=<токен от BotFather>
OLLAMA_API_BASE=http://host.docker.internal:11434/v1
```

`host.docker.internal` — так контейнер бота обращается к Ollama, запущенной на хосте. Убедитесь, что модели скачаны:
```
ollama pull llama3
ollama pull llama3.2-vision
```

Если своей Ollama нет — раскомментируйте в `.env` строку `COMPOSE_PROFILES=ollama` и укажите `OLLAMA_API_BASE=http://ollama:11434/v1`: тогда Ollama поднимется docker-контейнером вместе с ботом (модели скачайте через `docker compose exec ollama ollama pull llama3` и т.д.).

## Запуск

```bash
docker compose up -d --build
docker compose logs -f bot
```

База данных бота хранится в `./data/bot_data.db`. Если вы обновляетесь со старой версии, где файл лежал в корне (`./bot_data.db`), перенесите его: `mkdir -p data && mv bot_data.db data/` (установщик делает это автоматически).

В логах должно появиться:
```
Database initialized.
Connected to Redis successfully.
Starting bot polling...
```

## Команды бота

| Команда | Описание |
|---|---|
| `/start` | приветствие |
| `/clear` | очистить историю диалога |
| `/web <запрос>` | явный поиск в интернете |
| `/model` | выбрать текстовую модель (кнопками), персонально для каждого пользователя |
| `/persona` | сменить "характер" бота (кнопками), персонально для каждого пользователя |
| текст / фото / голосовое | обрабатываются автоматически |

### Выбор модели (`/model`)

Список моделей на выбор задаётся в `.env` через `MODEL_CHOICES` (формат `ключ=модель`, через запятую):
```
MODEL_CHOICES=default=qwen2.5vl:7b,coder=qwen3-coder:30b,uncensored=hf.co/OBLITERATUS/Gemma-4-12B-OBLITERATED:Q4_K_M
```
Выбор сохраняется в SQLite отдельно для каждого Telegram-пользователя и используется для текста/голосовых/веб-поиска. На анализ фото не влияет — оно всегда идёт через `VISION_MODEL`, так как остальные модели картинки не понимают.

### Персонажи (`/persona`)

Готовые варианты (правятся в [config.py](config.py), словарь `PERSONAS`): `default` (обычный ассистент), `pirate`, `yoda`, `sarcastic`, `scientist`. Выбранный персонаж добавляется системным промптом ко всем ответам — тексту, голосу, веб-поиску и даже описаниям фото.

## Структура проекта

```
main.py                 # точка входа: бот + воркер в одном asyncio-процессе
config.py                # чтение .env
db/database.py            # SQLite: история диалогов
handlers/                # aiogram-хендлеры (текст, фото, голос)
task_queue/worker.py      # фоновый воркер, разбирает очередь Redis, ходит в LLM
utils/llm_client.py       # клиент Ollama (OpenAI-совместимый API) + классификатор web-поиска
utils/vision_helper.py    # скачивание и кодирование фото в base64
utils/voice_helper.py     # транскрипция голосовых через faster-whisper
utils/web_search.py       # поиск через DuckDuckGo
```
