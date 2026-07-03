import asyncio
import json
import logging
import re
import time
from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.utils.chat_action import ChatActionSender
from config import build_system_prompt, AUTO_WEB_SEARCH, STREAM_RESPONSES, STREAM_EDIT_INTERVAL, VOICE_REPLIES
from utils.alerts import notify_admin
from utils.llm_client import generate_response, stream_response, plan_web_search
from utils.memory import needs_summary, update_summary
from utils.texts import t
from utils.tts_helper import synthesize_speech
from utils.web_search import gather_web_context
from db.database import get_history, add_message, get_user_model, get_user_persona

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 4096

_MD_TABLE_SEP_RE = re.compile(r"^\|?[\s:|-]+\|?\s*$", re.MULTILINE)
_MD_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$", re.MULTILINE)
_MD_HEADER_RE = re.compile(r"^#{1,6}\s*(.+)$", re.MULTILINE)
_MD_HR_RE = re.compile(r"^(?:-{3,}|\*{3,})\s*$", re.MULTILINE)
_MD_QUOTE_RE = re.compile(r"^>\s?(.*)$", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_MD_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)|(?<!_)_([^_\n]+?)_(?!_)")
_MD_CODE_RE = re.compile(r"`([^`\n]+?)`")
_BLANK_RUN_RE = re.compile(r"\n{3,}")

def _markdown_to_telegram_html(text: str) -> str:
    """
    Local models keep writing Markdown (headers, tables, bold/italic) no
    matter what the system prompt asks - so instead of relying on that,
    convert whatever comes back into Telegram HTML. This actually renders
    (real bold instead of literal **) and, unlike blindly deleting table/
    header lines, turns them into plain readable text instead of silently
    dropping content.

    Blockquote detection ('>' at line start) has to run before HTML-escaping,
    since escaping turns every '>' into '&gt;' - including the ones the quote
    regex is looking for. Placeholder sentinels stand in for the <i> tags
    across the escaping step so they don't get escaped themselves.
    """
    _Q_OPEN, _Q_CLOSE = "\x00Q1\x00", "\x00Q2\x00"
    text = _MD_TABLE_SEP_RE.sub("", text)
    text = _MD_TABLE_ROW_RE.sub(
        lambda m: " — ".join(c.strip() for c in m.group(1).split("|") if c.strip()), text
    )
    text = _MD_QUOTE_RE.sub(lambda m: f"{_Q_OPEN}{m.group(1)}{_Q_CLOSE}", text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace(_Q_OPEN, "<i>").replace(_Q_CLOSE, "</i>")
    text = _MD_HEADER_RE.sub(lambda m: f"<b>{m.group(1).strip()}</b>", text)
    text = _MD_HR_RE.sub("", text)
    text = _MD_BOLD_RE.sub(lambda m: f"<b>{m.group(1) or m.group(2)}</b>", text)
    text = _MD_ITALIC_RE.sub(lambda m: f"<i>{m.group(1) or m.group(2)}</i>", text)
    text = _MD_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", text)
    text = _BLANK_RUN_RE.sub("\n\n", text)
    return text.strip()

def _split_message(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Split text into telegram-sized chunks, preferring newline boundaries."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", limit // 2, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    chunks.append(text)
    return chunks

async def _try_edit(bot: Bot, chat_id: int, message_id: int, text: str, parse_mode: str = None):
    """Best-effort message edit - a failed edit (e.g. the user deleted the
    placeholder message, or telegram throttled us) must not kill the job."""
    try:
        await bot.edit_message_text(
            chat_id=chat_id, message_id=message_id, text=text, parse_mode=parse_mode
        )
    except Exception as e:
        logger.warning(f"Message edit failed: {e}")

async def _edit_status(bot: Bot, chat_id: int, message_id: int, text: str):
    await _try_edit(bot, chat_id, message_id, text, parse_mode="HTML")

_HTML_TAG_RE = re.compile(r"<[^>]+>")

async def _send_or_edit_html(bot: Bot, chat_id: int, message_id: int, text_html: str, edit: bool):
    """Send/edit one chunk as HTML; fall back to tag-stripped plain text if
    Telegram rejects the markup (e.g. an unclosed tag from a Markdown token
    that got split across message chunks)."""
    try:
        if edit:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text_html, parse_mode="HTML")
        else:
            await bot.send_message(chat_id, text_html, parse_mode="HTML")
    except Exception as e:
        logger.warning(f"HTML send failed, falling back to plain text: {e}")
        plain = _HTML_TAG_RE.sub("", text_html)
        if edit:
            await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=plain)
        else:
            await bot.send_message(chat_id, plain)

async def process_queue(bot: Bot, redis_client):
    """Background worker to process LLM requests from Redis queue."""
    logger.info("Worker started, waiting for jobs...")
    while True:
        try:
            # Short-polling BLPOP: Docker Desktop's Windows/WSL2 network layer
            # has been observed silently resetting idle container-to-container
            # sockets after ~6s, which turns a long blocking read into a
            # TimeoutError. socket_keepalive alone doesn't help here (its
            # default first probe is ~2h, far too slow). Polling well under
            # that window means BLPOP returns None (normal, not an exception)
            # before the reset can happen - the loop just tries again.
            result = await redis_client.blpop("llm_queue", timeout=4)
            if result:
                _, data_json = result
                job_data = json.loads(data_json)
                context_type = job_data.get("context_type", "text")

                # Internal job: refresh long-term memory. Queued like any
                # other job so it never competes with a user reply for the LLM.
                if context_type == "summarize":
                    try:
                        await update_summary(job_data["history_id"])
                    except Exception as e:
                        logger.error(f"Long-term memory update failed: {e}")
                    continue

                chat_id = job_data["chat_id"]
                user_id = job_data["user_id"]
                # History key: chat id in groups, user id in private chats
                history_id = job_data.get("history_id", user_id)
                prompt = job_data["prompt"]
                bot_message_id = job_data.get("bot_message_id")
                
                # Fetch DB History is now handled directly by the LLM client
                
                try:
                    final_prompt = prompt
                    final_context_type = context_type
                    user_model = await get_user_model(user_id)  # None = use TEXT_MODEL default
                    persona_key = await get_user_persona(user_id) or "default"
                    system_prompt = build_system_prompt(persona_key)

                    # Let the model decide for itself if it needs to search the web,
                    # and have it write the actual search query (skip for explicit
                    # /web calls and non-text prompts like vision) - the raw
                    # question is often a bad search query on its own.
                    if AUTO_WEB_SEARCH and context_type in ("text", "voice") and isinstance(prompt, str):
                        search_query = await plan_web_search(prompt, model_override=user_model)
                        if search_query:
                            if bot_message_id:
                                await _edit_status(bot, chat_id, bot_message_id, t("searching"))
                            search_results = await gather_web_context(search_query)
                            final_prompt = (
                                f"User asked: {prompt}\n\n"
                                f"Here are some web search results for \"{search_query}\":\n{search_results}\n\n"
                                f"Please synthesize an answer based on these results."
                            )
                            final_context_type = "web_search"

                    # Update status
                    if bot_message_id:
                        await _edit_status(bot, chat_id, bot_message_id, t("generating"))

                    # Show "typing..." in telegram for the whole generation;
                    # with streaming on, also grow the placeholder message as
                    # tokens arrive (the trailing ▌ marks an unfinished reply
                    # and guarantees the final edit differs from the last
                    # streamed preview).
                    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
                        if STREAM_RESPONSES and bot_message_id:
                            response_text = ""
                            last_edit = time.monotonic()
                            async for delta in stream_response(
                                final_prompt, history_id, final_context_type,
                                model_override=user_model, system_prompt=system_prompt
                            ):
                                response_text += delta
                                now = time.monotonic()
                                if (now - last_edit >= STREAM_EDIT_INTERVAL
                                        and response_text.strip()
                                        and len(response_text) < TELEGRAM_MESSAGE_LIMIT - 2):
                                    # Render markdown as we stream, so the text
                                    # looks formatted while it grows instead of
                                    # visibly "re-drawing" on the final edit.
                                    # Unclosed markup in a partial text stays
                                    # literal (regexes need both delimiters),
                                    # and _try_edit swallows a rejected edit.
                                    preview = _markdown_to_telegram_html(response_text)
                                    await _try_edit(bot, chat_id, bot_message_id,
                                                    preview + " ▌", parse_mode="HTML")
                                    last_edit = now
                        else:
                            response_text = await generate_response(
                                final_prompt, history_id, final_context_type,
                                model_override=user_model, system_prompt=system_prompt
                            )
                    # Persist the turn now, after history was fetched for generation,
                    # so the current message isn't duplicated into its own context.
                    # Raw (un-converted) text goes into history - it's fed back to
                    # the model as prior turns, and it shouldn't learn to imitate
                    # HTML tags from its own past replies.
                    history_content = job_data.get("history_content", prompt if isinstance(prompt, str) else "")
                    # Empty history_content = bot-initiated job (group chatter):
                    # only the bot's own remark goes into the history
                    if history_content:
                        await add_message(history_id, "user", history_content)
                    await add_message(history_id, "assistant", response_text)

                    # Enough new messages piled up? Queue a memory refresh.
                    if await needs_summary(history_id):
                        await redis_client.rpush("llm_queue", json.dumps({
                            "context_type": "summarize",
                            "history_id": history_id,
                        }))
                    
                    # Split the RAW text first (on newline boundaries), THEN
                    # convert each chunk to HTML separately - converting
                    # before splitting risks cutting a message in half right
                    # inside an HTML tag. Telegram caps messages at 4096 chars.
                    chunks = _split_message(
                        (response_text or "").strip() or t("empty_response")
                    )
                    html_chunks = [_markdown_to_telegram_html(c) for c in chunks]

                    if bot_message_id:
                        try:
                            await _send_or_edit_html(bot, chat_id, bot_message_id, html_chunks[0], edit=True)
                        except Exception as edit_error:
                            # Placeholder gone (user deleted it)? Don't lose
                            # the generated reply - send it as a new message.
                            logger.warning(f"Final edit failed, sending anew: {edit_error}")
                            await _send_or_edit_html(bot, chat_id, bot_message_id, html_chunks[0], edit=False)
                        for chunk in html_chunks[1:]:
                            await _send_or_edit_html(bot, chat_id, bot_message_id, chunk, edit=False)
                    else:
                        for chunk in html_chunks:
                            await _send_or_edit_html(bot, chat_id, bot_message_id, chunk, edit=False)

                    # Voice in, voice out: reply with a synthesized voice note
                    # too when the incoming message was itself a voice message.
                    # `context_type` here is the *original* value from the job -
                    # unlike final_context_type it doesn't flip to "web_search".
                    if VOICE_REPLIES and context_type == "voice":
                        tts_text = _HTML_TAG_RE.sub("", " ".join(html_chunks))
                        audio = await synthesize_speech(tts_text)
                        if audio:
                            try:
                                await bot.send_voice(chat_id, BufferedInputFile(audio, filename="reply.ogg"))
                            except Exception as e:
                                logger.warning(f"Failed to send voice reply: {e}")
                except Exception as e:
                    logger.error(f"Error generating response: {e}")
                    await notify_admin(bot, e)
                    if bot_message_id:
                        await _edit_status(bot, chat_id, bot_message_id, t("error_generic"))
                    
        except asyncio.CancelledError:
            logger.info("Worker task cancelled.")
            break
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await notify_admin(bot, e)
            await asyncio.sleep(1)
