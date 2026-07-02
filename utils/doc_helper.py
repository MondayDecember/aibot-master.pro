import asyncio
import io
import logging

from aiogram import Bot
from aiogram.types import Document

logger = logging.getLogger(__name__)

# Telegram Bot API refuses to download files bigger than 20 MB
MAX_FILE_SIZE = 20 * 1024 * 1024

TEXT_EXTENSIONS = (
    ".txt", ".md", ".csv", ".tsv", ".log", ".json", ".xml", ".yaml", ".yml",
    ".html", ".htm", ".ini", ".cfg", ".toml", ".py", ".js", ".ts", ".sh",
    ".sql", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php",
)


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


async def extract_document_text(bot: Bot, document: Document):
    """
    Download a telegram document and extract plain text from it.
    Returns (text, None) on success or (None, user_facing_error) on failure.
    """
    name = (document.file_name or "").lower()
    if document.file_size and document.file_size > MAX_FILE_SIZE:
        return None, "The file is too large - telegram bots can only download files up to 20 MB."

    is_pdf = name.endswith(".pdf")
    if not is_pdf and not name.endswith(TEXT_EXTENSIONS):
        return None, (
            "Unsupported file type. Send a PDF or a plain-text file "
            "(.txt, .md, .csv, code files etc.)."
        )

    try:
        file_info = await bot.get_file(document.file_id)
        buf = io.BytesIO()
        await bot.download_file(file_info.file_path, buf)
        data = buf.getvalue()
    except Exception as e:
        logger.error(f"Failed to download document: {e}")
        return None, "Sorry, failed to download the file from telegram."

    try:
        if is_pdf:
            # PDF parsing is CPU-bound - keep it off the event loop
            text = await asyncio.to_thread(_extract_pdf, data)
        else:
            text = data.decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(f"Failed to extract text from document '{name}': {e}")
        return None, "Sorry, couldn't read this file - it may be corrupted."

    text = text.strip()
    if not text:
        return None, (
            "Couldn't extract any text from this file. If it's a scanned PDF, "
            "it contains images instead of text - try sending pages as photos."
        )
    return text, None
