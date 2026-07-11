from aiogram import Router, F
from aiogram.types import Message

from config import DOC_MAX_CHARS
from task_queue.enqueue import enqueue_llm_job
from utils.doc_helper import extract_document_text
from utils.group import gate_group_message, history_key
from utils.reactions import react_seen
from utils.telegram_helpers import answer_resilient
from utils.texts import t

router = Router()


def _sample_document(text: str, max_chars: int) -> tuple[str, bool]:
    """
    If the text already fits, return it untouched. Otherwise take three
    excerpts - beginning, middle, end - instead of a single hard cutoff, so
    a long document (a novel, a report) gives the model at least some sense
    of the whole arc rather than only ever seeing the opening page.
    """
    if len(text) <= max_chars:
        return text, False
    part = max_chars // 3
    start = text[:part]
    mid = len(text) // 2
    middle = text[mid - part // 2: mid + part // 2]
    end = text[-part:]
    sampled = (
        f"[Beginning]\n{start}\n\n[Middle excerpt]\n{middle}\n\n[End]\n{end}"
    )
    return sampled, True


@router.message(F.document)
async def handle_document(message: Message, redis):
    # In groups: react only when the caption mentions the bot or the file
    # replies to one of its messages
    should_handle, caption_text = await gate_group_message(message, message.caption)
    if not should_handle:
        return
    await react_seen(message)
    bot_message = await answer_resilient(message, t("reading_document"), parse_mode="HTML")

    text, error = await extract_document_text(message.bot, message.document)
    if error:
        await bot_message.edit_text(error)
        return

    file_name = message.document.file_name or "document"
    caption = caption_text or t("doc_default_caption")
    sampled, was_truncated = _sample_document(text, DOC_MAX_CHARS)
    note = t("doc_truncated", n=DOC_MAX_CHARS) if was_truncated else ""
    prompt = f'{caption}\n\nDocument "{file_name}":\n{sampled}{note}'

    # context_type "document" uses the text model and skips the automatic
    # web-search classifier (pointless for an attached file).
    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=prompt,
        history_content=f"[Sent a document: {file_name}] {caption}",
        context_type="document",
        history_id=history_key(message),
    )
