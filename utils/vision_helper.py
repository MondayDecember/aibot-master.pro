import base64
import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

async def get_image_base64(bot: Bot, file_id: str) -> str:
    """
    Downloads an image from Telegram by file_id and returns it as a base64 string.
    """
    try:
        file_info = await bot.get_file(file_id)
        file_path = file_info.file_path
        
        # Download the file to a BytesIO object
        import io
        file_bytes = io.BytesIO()
        await bot.download_file(file_path, file_bytes)
        
        # Convert to base64
        base64_img = base64.b64encode(file_bytes.getvalue()).decode("utf-8")
        return base64_img
    except Exception as e:
        logger.error(f"Error converting image to base64: {e}")
        return ""
