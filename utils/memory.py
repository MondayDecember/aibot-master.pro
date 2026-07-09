import logging

from config import TEXT_MODEL, SUMMARY_MODEL, LONG_TERM_MEMORY, SUMMARIZE_EVERY, SUMMARY_MAX_CHARS
from db.database import get_memory, set_memory, count_messages, get_history
from utils.llm_client import client, _resolve_model

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = (
    "You maintain the long-term memory of a chat assistant. Given the previous "
    "memory summary and the recent messages, produce an updated summary. Keep "
    "stable facts about the user (name, preferences, projects), ongoing topics "
    "and unresolved questions; drop small talk. Be concise - at most {max_chars} "
    "characters. Write the summary in the language predominantly used in the "
    "conversation. Reply with ONLY the summary text."
)


_ONDEMAND_SYSTEM = (
    "Summarize the following conversation for the user in a few short bullet "
    "points: the main topics discussed and any decisions or open questions. "
    "Write in the language of the conversation. Reply with only the summary."
)


async def summarize_history(history_id: int) -> str | None:
    """One-off summary of the current dialog for /summary. Returns None when
    there's nothing to summarize. Not stored - unlike update_summary."""
    recent = await get_history(history_id, limit=40)
    convo = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in recent
        if isinstance(m.get("content"), str) and m["content"]
    )
    if not convo.strip():
        return None
    response = await client.chat.completions.create(
        model=await _resolve_model(SUMMARY_MODEL or TEXT_MODEL),
        messages=[
            {"role": "system", "content": _ONDEMAND_SYSTEM},
            {"role": "user", "content": convo},
        ],
        temperature=0.3,
    )
    return (response.choices[0].message.content or "").strip() or None


async def needs_summary(history_id: int) -> bool:
    """True when enough new messages piled up since the last refresh."""
    if not LONG_TERM_MEMORY:
        return False
    _, at_count = await get_memory(history_id)
    total = await count_messages(history_id)
    return total - at_count >= SUMMARIZE_EVERY


async def update_summary(history_id: int):
    """
    Fold recent messages into the running summary. Runs as a queued worker
    job, so it shares the single LLM pipeline and never runs concurrently
    with a user reply. Re-checks the threshold because duplicate jobs may
    have been queued.
    """
    old_summary, at_count = await get_memory(history_id)
    total = await count_messages(history_id)
    if total - at_count < SUMMARIZE_EVERY:
        return

    recent = await get_history(history_id, limit=SUMMARIZE_EVERY + 10)
    convo = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in recent
        if isinstance(m.get("content"), str) and m["content"]
    )
    messages = [
        {"role": "system", "content": _SUMMARY_SYSTEM.format(max_chars=SUMMARY_MAX_CHARS)},
        {
            "role": "user",
            "content": (
                f"Previous memory summary:\n{old_summary or '(none)'}\n\n"
                f"Recent messages:\n{convo}"
            ),
        },
    ]
    response = await client.chat.completions.create(
        model=await _resolve_model(SUMMARY_MODEL or TEXT_MODEL), messages=messages, temperature=0.3
    )
    new_summary = (response.choices[0].message.content or "").strip()[:SUMMARY_MAX_CHARS]
    if new_summary:
        await set_memory(history_id, new_summary, total)
        logger.info(f"Long-term memory refreshed for {history_id} ({total} messages)")
