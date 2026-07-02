import logging
from openai import AsyncOpenAI
from config import OLLAMA_API_BASE, OLLAMA_API_KEY, TEXT_MODEL, VISION_MODEL, HISTORY_LIMIT
from db.database import get_history
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
    messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + history
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

async def should_search_web(prompt: str, model_override: str = None) -> bool:
    """
    Ask the model whether answering `prompt` needs current/real-time information
    from the web (news, prices, weather, sports scores, recent releases, etc.).
    Defaults to False (no search) on any ambiguous answer or error. Uses
    `model_override` when given so the classifier runs on the same model that
    will generate the answer (avoids swapping two different models in/out of
    Ollama for a single message).
    """
    try:
        response = await client.chat.completions.create(
            model=model_override or TEXT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You decide whether answering the user's next message requires "
                        "searching the web for current or real-time information (news, prices, "
                        "weather, sports scores, recent releases, live events, facts that change "
                        "over time, etc.). General knowledge, coding help, and conversation do not "
                        "need a search. Reply with exactly one word: YES or NO."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=3
        )
        answer = (response.choices[0].message.content or "").strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        logger.error(f"Web search decision error: {e}")
        return False
