from aiogram import Router, F
from aiogram.types import Message
from task_queue.enqueue import enqueue_llm_job
from utils.group import gate_group_message, history_key
from utils.texts import t
from utils.vision_helper import get_image_base64

router = Router()

@router.message(F.photo)
async def handle_photo(message: Message, redis):
    # In groups: react only when the caption mentions the bot or the photo
    # replies to one of its messages
    should_handle, caption_text = await gate_group_message(message, message.caption)
    if not should_handle:
        return
    bot_message = await message.answer(t("processing_image"), parse_mode="HTML")

    # Get highest quality photo
    photo = message.photo[-1]

    # Convert to base64
    base64_image = await get_image_base64(message.bot, photo.file_id)
    if not base64_image:
        await bot_message.edit_text(t("image_failed"))
        return

    caption = caption_text or t("image_default_caption")

    # Open WebUI / Ollama expects vision input format (list of dicts for content)
    # The exact format might vary based on your specific Ollama/OpenWebUI configuration.
    # Here is a generic format commonly used for multimodal messages in OpenAI API.
    prompt = [
        {"type": "text", "text": caption},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
    ]

    await enqueue_llm_job(
        redis, message, bot_message,
        prompt=prompt,
        history_content=f"[Sent an Image] {caption}",
        context_type="vision",
        history_id=history_key(message),
    )
