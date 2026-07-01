import logging
from openai import AsyncOpenAI
from config import OLLAMA_API_BASE, OLLAMA_API_KEY, TEXT_MODEL, VISION_MODEL
from db.database import get_history

logger = logging.getLogger(__name__)

# Initialize OpenAI async client pointing to local API
client = AsyncOpenAI(
    base_url=OLLAMA_API_BASE,
    api_key=OLLAMA_API_KEY
)

async def generate_response(
    prompt: str,
    user_id: int,
    context_type: str = "text",
    model_override: str = None,
    system_prompt: str = None,
) -> str:
    """
    Generate response from the local LLM.
    Fetches the last 5 conversation items from SQLite database as context.
    `model_override` lets the caller use a user-selected model (see /model in
    the bot) instead of the default TEXT_MODEL. Ignored for vision - photo
    analysis always needs a multimodal model, so it always uses VISION_MODEL.
    `system_prompt`, if given, is prepended as a system message (see /persona).
    """
    # LLM client retrieves the conversation history from SQLite database
    history = await get_history(user_id, limit=5)
    messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + history

    # Add the current prompt
    if context_type == "text" or context_type == "voice" or context_type == "web_search":
        messages.append({"role": "user", "content": prompt})
        model = model_override or TEXT_MODEL
    elif context_type == "vision":
        # If it's vision, prompt is expected to be a list for the content with text and image_url
        messages.append({"role": "user", "content": prompt})
        model = VISION_MODEL
    else:
        messages.append({"role": "user", "content": prompt})
        model = model_override or TEXT_MODEL

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"LLM Client error: {e}")
        return "I'm sorry, I couldn't process that request at the moment."

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
