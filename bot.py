"""
Minimal Telegram bot: set a thumbnail, then forward incoming videos to a
destination channel using that thumbnail — without downloading, re-encoding,
or running the video through FFmpeg.

Runtime notes (see README.md for full explanation):
- The video itself is never downloaded. We reuse Telegram's existing
  `file_id` for the video and pass it straight to `send_video`.
- Telegram/Pyrofork does NOT allow reusing a `file_id` (or a previously
  downloaded buffer) as a video's `thumb` across multiple send_video calls
  forever without a fresh upload — thumbnails must be (re-)uploaded as raw
  JPEG bytes on every call. To satisfy that with zero repeated downloads,
  the thumbnail image (a small JPEG, not the video) is downloaded ONCE, the
  moment `/setthumbnail` is used, and its bytes are kept in memory. Every
  subsequent video reuses those same in-memory bytes as the `thumb` — no
  disk writes, no re-downloading, no FFmpeg.
"""

import io
import logging
import os
import sys

from dotenv import load_dotenv
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import RPCError

# --------------------------------------------------------------------------
# Setup
# --------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("thumbnail-bot")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DESTINATION_CHANNEL_ID = os.getenv("DESTINATION_CHANNEL_ID")

_missing = [
    name
    for name, value in (
        ("API_ID", API_ID),
        ("API_HASH", API_HASH),
        ("BOT_TOKEN", BOT_TOKEN),
        ("DESTINATION_CHANNEL_ID", DESTINATION_CHANNEL_ID),
    )
    if not value
]
if _missing:
    logger.error("Missing required environment variable(s): %s", ", ".join(_missing))
    sys.exit(1)

try:
    API_ID = int(API_ID)
except ValueError:
    logger.error("API_ID must be an integer.")
    sys.exit(1)

try:
    DESTINATION_CHANNEL_ID = int(DESTINATION_CHANNEL_ID)
except ValueError:
    logger.error("DESTINATION_CHANNEL_ID must be an integer (e.g. -1001234567890).")
    sys.exit(1)

app = Client(
    "thumbnail_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,  # no session file written to disk
)

# In-memory state: raw JPEG bytes of the currently configured thumbnail.
# No database, no disk persistence — resets if the bot restarts, by design.
current_thumbnail: bytes | None = None


# --------------------------------------------------------------------------
# Handlers
# --------------------------------------------------------------------------

@app.on_message(filters.command("setthumbnail"))
async def set_thumbnail(client: Client, message: Message):
    global current_thumbnail

    replied = message.reply_to_message
    if not replied or not replied.photo:
        await message.reply_text(
            "Usage: reply to a photo with /setthumbnail to set it as the active thumbnail."
        )
        return

    try:
        # The photo is small (Telegram photos used as thumbnails are tiny),
        # so downloading it into memory here is cheap and is the ONE
        # download this bot ever performs. Videos are never downloaded.
        thumb_bytes = await client.download_media(replied.photo.file_id, in_memory=True)
        current_thumbnail = thumb_bytes.getvalue()
    except RPCError as e:
        logger.error("Failed to download thumbnail image: %s", e)
        await message.reply_text("❌ Could not read that image. Please try again.")
        return
    except Exception as e:
        logger.error("Unexpected error while setting thumbnail: %s", e)
        await message.reply_text("❌ Something went wrong setting the thumbnail.")
        return

    logger.info("Thumbnail updated by user %s", message.from_user.id if message.from_user else "unknown")
    await message.reply_text("✅ Thumbnail updated.")


@app.on_message(filters.video)
async def handle_video(client: Client, message: Message):
    if current_thumbnail is None:
        await message.reply_text(
            "⚠️ No thumbnail configured yet. Reply to a photo with /setthumbnail first."
        )
        return

    video = message.video
    try:
        # Reuse Telegram's existing file reference for the video — this does
        # NOT download the video to this server. The thumbnail bytes were
        # already downloaded once when /setthumbnail was used, and are
        # re-uploaded here from memory (Telegram does not allow reusing a
        # thumbnail file_id, so a fresh upload of the same in-memory bytes
        # is the closest zero-extra-download approach).
        thumb_stream = io.BytesIO(current_thumbnail)
        thumb_stream.name = "thumbnail.jpg"

        await client.send_video(
            chat_id=DESTINATION_CHANNEL_ID,
            video=video.file_id,
            thumb=thumb_stream,
            caption=message.caption or None,
            duration=video.duration,
            width=video.width,
            height=video.height,
            supports_streaming=video.supports_streaming,
        )
    except RPCError as e:
        logger.error("Telegram API error while sending video: %s", e)
        await message.reply_text("❌ Failed to send the video to the destination channel.")
        return
    except Exception as e:
        logger.error("Unexpected error while sending video: %s", e)
        await message.reply_text("❌ Something went wrong sending the video.")
        return

    logger.info("Video forwarded to destination channel %s", DESTINATION_CHANNEL_ID)


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting Telegram thumbnail bot...")
    app.run()
