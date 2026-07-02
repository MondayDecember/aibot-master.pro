import json
from aiogram import Router, F
from aiogram.types import Message

from config import DOC_MAX_CHARS
from utils.doc_helper import extract_document_text

router = Router()


@router.message(F.document)
async def handle_document(message: Message, redis):
    bot_message = await message.answer("<i>Reading document...</i>", parse_mode="HTML")

    text, error = await extract_document_text(message.bot, message.document)
    if error:
        await bot_message.edit_text(error)
        return

    file_name = message.document.file_name or "document"
    caption = message.caption or "Summarize this document."
    truncated = text[:DOC_MAX_CHARS]
    note = (
        f"\n\n[The document was truncated to the first {DOC_MAX_CHARS} characters]"
        if len(text) > DOC_MAX_CHARS else ""
    )
    prompt = f'{caption}\n\nDocument "{file_name}":\n{truncated}{note}'

    # context_type "document" uses the text model and skips the automatic
    # web-search classifier (pointless for an attached file).
    job_data = {
        "chat_id": message.chat.id,
        "user_id": message.from_user.id,
        "prompt": prompt,
        "history_content": f"[Sent a document: {file_name}] {caption}",
        "context_type": "document",
        "bot_message_id": bot_message.message_id
    }
    await redis.rpush("llm_queue", json.dumps(job_data))
