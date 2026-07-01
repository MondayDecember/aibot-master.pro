import json
from aiogram import Router, F
from aiogram.types import Message
from utils.vision_helper import get_image_base64

router = Router()

@router.message(F.photo)
async def handle_photo(message: Message, redis):
    bot_message = await message.answer("<i>Processing image...</i>", parse_mode="HTML")
    
    # Get highest quality photo
    photo = message.photo[-1]
    
    # Convert to base64
    base64_image = await get_image_base64(message.bot, photo.file_id)
    if not base64_image:
        await bot_message.edit_text("Sorry, failed to process the image.")
        return
        
    caption = message.caption or "What's in this image?"
    
    # Open WebUI / Ollama expects vision input format (list of dicts for content)
    # The exact format might vary based on your specific Ollama/OpenWebUI configuration.
    # Here is a generic format commonly used for multimodal messages in OpenAI API.
    prompt = [
        {"type": "text", "text": caption},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
    ]
    
    job_data = {
        "chat_id": message.chat.id,
        "user_id": message.from_user.id,
        "prompt": prompt,
        "history_content": f"[Sent an Image] {caption}",
        "context_type": "vision",
        "bot_message_id": bot_message.message_id
    }
    
    await redis.rpush("llm_queue", json.dumps(job_data))
