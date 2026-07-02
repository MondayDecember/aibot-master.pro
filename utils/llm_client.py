import logging
from openai import AsyncOpenAI
from config import OLLAMA_API_BASE, OLLAMA_API_KEY, TEXT_MODEL, VISION_MODEL, HISTORY_LIMIT, LONG_TERM_MEMORY
from db.database import get_history, get_memory
from utils.texts import t

logger = logging.getLogger(__name__)

# Initialize OpenAI async client pointing to local API
client = AsyncOpenAI(
    base_url=OLLAMA_API_BASE,
    api_key=OLLAMA_API_KEY
)

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
    return messages, model

async def generate_response(
    prompt: str,
    user_id: int,
    context_type: str = "text",
    model_override: str = None,
    system_prompt: str = None,
) -> str:
    """Generate a complete response from the local LLM (non-streaming)."""
    messages, model = await _build_request(prompt, user_id, context_type, model_override, system_prompt)
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )
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
):
    """
    Async generator yielding response text deltas as the LLM produces them.
    Unlike generate_response, errors propagate to the caller - the worker
    turns them into a user-facing error message.
    """
    messages, model = await _build_request(prompt, user_id, context_type, model_override, system_prompt)
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
        stream=True
    )
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content

async def plan_web_search(prompt: str, model_override: str = None) -> str | None:
    """
    Ask the model whether answering `prompt` needs current/real-time
    information from the web, and if so, what to actually search for.
    Returns None when no search is needed, or a short search-engine-ready
    query string.

    The raw user question is usually a bad search query - question words
    ("какая", "what", "how") and a trailing "?" make search engines latch
    onto the wrong part of the sentence (e.g. "какая сейчас погода в
    Томске?" returned dictionary/grammar pages about the word "какая"
    instead of anything about Tomsk's weather). So the model is asked to
    rewrite the question into plain keywords in the same pass as the
    yes/no decision, instead of the raw prompt being used as the query.

    Uses `model_override` when given so this runs on the same model that
    will generate the answer (avoids swapping two different models in/out
    of Ollama for a single message).
    """
    try:
        response = await client.chat.completions.create(
            model=model_override or TEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Decide whether answering the user's next message requires "
                        "searching the web for current or real-time information (news, prices, "
                        "weather, sports scores, recent releases, live events, facts that change "
                        "over time, etc.). General knowledge, coding help, and conversation do not "
                        "need a search.\n"
                        "If no search is needed, reply with exactly: NO\n"
                        "If a search is needed, reply with: YES: <search query>\n"
                        "The query must be plain keywords a search engine understands well - no "
                        "question words, no question mark - in the same language as the user's message."
                    )
                },
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
        if not answer.upper().startswith("YES"):
            return None
        _, _, query = answer.partition(":")
        return query.strip() or prompt
    except Exception as e:
        logger.error(f"Web search planning error: {e}")
        return None
