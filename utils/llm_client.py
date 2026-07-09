import logging
from datetime import datetime
from openai import AsyncOpenAI
from config import OLLAMA_API_BASE, OLLAMA_API_KEY, TEXT_MODEL, VISION_MODEL, HISTORY_LIMIT, LONG_TERM_MEMORY, TIMEZONE, TZINFO, MODEL_NUM_CTX
from db.database import get_history, get_memory
from utils.texts import t

logger = logging.getLogger(__name__)

# Initialize OpenAI async client pointing to local API
client = AsyncOpenAI(
    base_url=OLLAMA_API_BASE,
    api_key=OLLAMA_API_KEY
)

# Extra options passed through to Ollama's OpenAI-compatible endpoint. num_ctx
# raises the context window (Ollama's default is a small 2048/4096 that
# truncates history). Other backends (LM Studio) ignore unknown options.
_EXTRA_BODY = {"options": {"num_ctx": MODEL_NUM_CTX}} if MODEL_NUM_CTX > 0 else None


_missing_model_warned = set()

async def _resolve_model(name: str) -> str:
    """Fall back to an actually-installed model if `name` isn't available,
    so a stale TEXT_MODEL/VISION_MODEL (never pulled, or pulled then
    removed) degrades to a working answer instead of erroring on every
    single request. Local import to avoid a circular import - llm_backend
    imports `client` from this module."""
    from utils.llm_backend import list_installed_models
    installed = await list_installed_models()
    if not installed:
        return name  # backend unreachable - nothing to fall back to
    installed_base = {m.split(":")[0] for m in installed}
    if name in installed or name.split(":")[0] in installed_base:
        return name
    fallback = installed[0]
    if name not in _missing_model_warned:
        _missing_model_warned.add(name)
        logger.warning(f"Model '{name}' isn't installed on the LLM backend - falling back to '{fallback}'.")
    return fallback

def _fill_usage(stats, response):
    """Copy token counts from an API response into the caller's stats dict."""
    if stats is None:
        return
    usage = getattr(response, "usage", None)
    if usage:
        stats["prompt_tokens"] = getattr(usage, "prompt_tokens", 0) or 0
        stats["completion_tokens"] = getattr(usage, "completion_tokens", 0) or 0
        stats["total_tokens"] = getattr(usage, "total_tokens", 0) or 0

async def _build_request(prompt, user_id, context_type, model_override, system_prompt):
    """
    Assemble the message list (last HISTORY_LIMIT history items from SQLite +
    optional persona system prompt + current prompt) and pick the model.
    `model_override` lets the caller use a user-selected model (see /model in
    the bot) instead of the default TEXT_MODEL. Ignored for vision - photo
    analysis always needs a multimodal model, so it always uses VISION_MODEL.
    For vision, prompt is a list of content dicts (text + image_url).
    """
    history = await get_history(user_id, limit=HISTORY_LIMIT)
    system_parts = []
    if system_prompt:
        system_parts.append(system_prompt)
    # The model has no clock - tell it, so "what day is it", "how long
    # until new year" and similar just work.
    system_parts.append(
        "Current date and time: "
        + datetime.now(TZINFO).strftime("%A, %Y-%m-%d %H:%M")
        + f" ({TIMEZONE})"
    )
    if LONG_TERM_MEMORY:
        summary, _ = await get_memory(user_id)
        if summary:
            system_parts.append(
                "Long-term memory - summary of the earlier conversation:\n" + summary
            )
    system_messages = (
        [{"role": "system", "content": "\n\n".join(system_parts)}] if system_parts else []
    )
    messages = system_messages + history
    messages.append({"role": "user", "content": prompt})
    model = VISION_MODEL if context_type == "vision" else (model_override or TEXT_MODEL)
    model = await _resolve_model(model)
    return messages, model

async def generate_response(
    prompt: str,
    user_id: int,
    context_type: str = "text",
    model_override: str = None,
    system_prompt: str = None,
    stats: dict = None,
) -> str:
    """Generate a complete response from the local LLM (non-streaming).
    If `stats` is given, it's filled with prompt/completion/total tokens
    and the actually-used model name (post _resolve_model fallback)."""
    messages, model = await _build_request(prompt, user_id, context_type, model_override, system_prompt)
    if stats is not None:
        stats["model"] = model
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            extra_body=_EXTRA_BODY,
        )
        _fill_usage(stats, response)
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM Client error: {e}")
        return t("llm_unavailable")

async def stream_response(
    prompt,
    user_id: int,
    context_type: str = "text",
    model_override: str = None,
    system_prompt: str = None,
    stats: dict = None,
):
    """
    Async generator yielding response text deltas as the LLM produces them.
    Unlike generate_response, errors propagate to the caller - the worker
    turns them into a user-facing error message. If `stats` is given, request
    a usage summary and fill it from the final (choices-less) chunk.
    """
    messages, model = await _build_request(prompt, user_id, context_type, model_override, system_prompt)
    if stats is not None:
        stats["model"] = model
    kwargs = {"model": model, "messages": messages, "temperature": 0.7, "stream": True,
              "extra_body": _EXTRA_BODY}
    if stats is not None:
        kwargs["stream_options"] = {"include_usage": True}
    stream = await client.chat.completions.create(**kwargs)
    async for chunk in stream:
        if getattr(chunk, "usage", None):
            _fill_usage(stats, chunk)
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

async def plan_web_search(prompt: str, model_override: str = None) -> str | None:
    """
    Deprecated thin wrapper kept for compatibility - see route_message().
    """
    action, query = await route_message(prompt, model_override)
    return query if action == "search" else None

_ROUTER_SYSTEM = (
    "You are the intent router of a telegram assistant. Look at the user's "
    "next message and decide what it needs. Reply with exactly ONE of:\n"
    "REMIND - the user ASKS to be reminded of something, or to set a "
    "reminder / note / alarm for later, in any phrasing (\"напомни...\", "
    "\"поставь заметку...\", \"сделай пометку чтоб я не забыл...\", \"не дай "
    "мне забыть...\", \"remind me...\"). Only actual requests count - "
    "statements ABOUT reminders are not requests.\n"
    "SEARCH: <query> - answering needs current or real-time information "
    "from the web (news, prices, weather, sports scores, recent releases, "
    "live events, facts that change over time). The query must be plain "
    "keywords a search engine understands well - no question words, no "
    "question mark - in the same language as the user's message.\n"
    "NO - anything else: general knowledge, coding help, conversation.\n"
    "Reply with only REMIND, SEARCH: <query>, or NO."
)

async def route_message(prompt: str, model_override: str = None):
    """
    One cheap classification pass per message deciding what it needs:
      ("remind", None)  - create a reminder (catches phrasings the fast
                          keyword regex in utils/reminders.py missed)
      ("search", query) - web search, with the question rewritten into
                          search-engine keywords (the raw question is a bad
                          query: "какая сейчас погода в Томске?" used to
                          return grammar pages about the word "какая")
      ("none", None)    - just answer normally
    Uses `model_override` when given so this runs on the same model that
    will generate the answer (avoids swapping two different models in/out
    of Ollama for a single message). Any error degrades to ("none", None).
    """
    try:
        response = await client.chat.completions.create(
            model=await _resolve_model(model_override or TEXT_MODEL),
            messages=[
                {"role": "system", "content": _ROUTER_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            # Reasoning models (Qwen3.5, DeepSeek-R1-style, etc.) put their
            # chain-of-thought in a separate `reasoning` field and only write
            # the final answer into `content` afterwards - a tiny max_tokens
            # cut them off mid-thought, so this always saw empty content and
            # returned "no search needed", no matter the question. Non-reasoning
            # models still stop right after their answer on their own, so this
            # ceiling doesn't add latency for them.
            max_tokens=500
        )
        answer = (response.choices[0].message.content or "").strip()
        upper = answer.upper()
        if upper.startswith("REMIND"):
            return "remind", None
        # YES: kept for models that answer in the old pre-router format
        if upper.startswith("SEARCH") or upper.startswith("YES"):
            _, _, query = answer.partition(":")
            return "search", (query.strip() or prompt)
        return "none", None
    except Exception as e:
        logger.error(f"Message routing error: {e}")
        return "none", None
