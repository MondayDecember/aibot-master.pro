import asyncio
import io
import logging

from config import OCR_ENABLED, OCR_LANGUAGES

logger = logging.getLogger(__name__)

# Ignore OCR output shorter than this - a couple of stray characters off a
# photo of a cat are noise, not text worth feeding the model.
_MIN_OCR_CHARS = 8
# Cap what we pass along so a dense document scan can't blow the context.
_MAX_OCR_CHARS = 4000


def _run_ocr(image_bytes: bytes) -> str:
    from PIL import Image
    import pytesseract

    with Image.open(io.BytesIO(image_bytes)) as img:
        text = pytesseract.image_to_string(img, lang=OCR_LANGUAGES)
    return " ".join(text.split()) if text else ""


async def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Best-effort OCR of a photo. Returns "" when disabled, when Tesseract
    isn't available, when the image has no readable text, or on any error -
    OCR is an enhancement, never a hard requirement for handling the photo.
    Runs in a thread (Tesseract is CPU-bound and blocking).
    """
    if not OCR_ENABLED or not image_bytes:
        return ""
    try:
        text = await asyncio.to_thread(_run_ocr, image_bytes)
    except Exception as e:
        logger.warning(f"OCR failed (is tesseract installed?): {e}")
        return ""
    text = text.strip()
    if len(text) < _MIN_OCR_CHARS:
        return ""
    return text[:_MAX_OCR_CHARS]
