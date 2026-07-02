from aiogram import Router, F
from aiogram.types import Message

from config import DOC_MAX_CHARS
from task_queue.enqueue import enqueue_llm_job
from utils.doc_helper import extract_document_text
from utils.group import gate_group_message, history_key
from utils.texts import t

router = Router()


@router.message(F.document)
async def handle_document(message: Message, redis):
    # In groups: react only when the caption mentions the bot or the file
    # replies to one of its messages
    should_handle, caption_text = await gate_group_message(message, message.caption)
    if not should_handle:
        return
    bot_message = await message.answer(t("reading_document"), parse_mode="HTML")

    text, error = await extract_document_text(message.bot, message.document)
    if error:
        await bot_message.edit_text(error)
        return

    file_name = message.document.file_name or "document"
    caption = caption_text or t("doc_default_caption")
    truncated = text[:DOC_MAX_CHARS]
    note = t("doc_truncated", n=DOC_MAX_CHARS) if len(text) > DOC_MAX_CHARS else ""
    prompt = f'{caption}\n\nDocument "{file_name}":\n{truncated}{note}'

    # context_type "document" uses the text model and skips the automatic
    # web-search classifier (pointless for an attached file).
    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=prompt,
        history_content=f"[Sent a document: {file_name}] {caption}",
        context_type="document",
        history_id=history_key(message),
    )
