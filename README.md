# aibot-master

Telegram-бот на локальной LLM (Ollama), собранный на основе [m0wer/aibot](https://github.com/m0wer/aibot) с добавленными фичами из [mlloliveira/TelegramBot](https://github.com/mlloliveira/TelegramBot).

## Возможности

- **Текстовый чат** с историей диалога (SQLite, `bot_data.db`), не сбрасывается при рестарте.
- **Анализ изображений** — пришлите фото, бот опишет/ответит на вопрос по картинке (модель `VISION_MODEL`).
- **Голосовые сообщения** — распознавание речи через `faster-whisper`, транскрипция уходит в LLM.
- **Поиск в интернете** — бот сам решает через LLM-классификатор, нужны ли для ответа актуальные данные (новости, курсы, погода и т.п.), и в этом случае ищет через DuckDuckGo. Также доступна ручная команда `/web <запрос>`.
- **Очередь на Redis** — все запросы к LLM идут через Redis (`BLPOP`/`RPUSH`), что защищает от перегрузки при одновременных сообщениях.

## Требования

- Docker + Docker Compose.
- [Ollama](https://ollama.com), запущенная на хосте (порт `11434`), с загруженными моделями:
  ```
  ollama pull llama3
  ollama pull llama3.2-vision
  ```
- Токен Telegram-бота от [@BotFather](https://t.me/BotFather).

## Установка

```bash
git clone https://github.com/MondayDecember/aibot-master.pro.git aibot-master
cd aibot-master
copy .env.example .env   # на Linux/Mac: cp .env.example .env
```

Откройте `.env` и заполните:

```
BOT_TOKEN=<токен от BotFather>
OLLAMA_API_BASE=http://host.docker.internal:11434/v1
```

`host.docker.internal` — так контейнер бота обращается к Ollama, запущенной на хосте. Если Ollama крутится в докере на той же сети — укажите вместо этого имя её контейнера.

## Запуск

```bash
docker compose build --no-cache bot
docker compose up -d
docker compose logs -f bot
```

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
