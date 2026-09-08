"""
Minimal Telegram bot: set a thumbnail, then forward incoming videos to a
destination channel using that thumbnail — without downloading, re-encoding,
or running the video through FFmpeg.

Runtime notes (see README.md for the full explanation):
- The video itself is never downloaded. Its existing `file_id` is decoded
  into a raw Telegram document reference and reused directly — the video
  bytes never touch this server.
- Telegram's MTProto protocol has NO way to attach a custom `thumb` to a
  reused/referenced video (the `thumb` field only exists on the "uploaded"
  media type, used when uploading fresh bytes). The closest correct
  equivalent for a reused video is Telegram's "video cover" field, which
  IS supported on a reused document reference. The bot uploads the small
  cover/thumbnail JPEG (not the video) and attaches it as that video's
  cover via a raw `messages.SendMedia` call.
- The cover JPEG itself can't be reused by file_id either — Telegram
  requires a fresh upload of it on every send. It's downloaded ONCE (when
  `/setthumbnail` is used) and kept in memory; each video re-uploads those
  same in-memory bytes as the cover — no disk writes, no re-downloading.
"""

import io
import logging
import os
import sys

from dotenv import load_dotenv
from pyrogram import Client, filters, raw, utils
from pyrogram.file_id import FileId
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
        peer = await client.resolve_peer(DESTINATION_CHANNEL_ID)

        # Reuse Telegram's existing document reference for the video — the
        # video bytes are never downloaded or re-uploaded.
        decoded = FileId.decode(video.file_id)
        input_video = raw.types.InputDocument(
            id=decoded.media_id,
            access_hash=decoded.access_hash,
            file_reference=decoded.file_reference,
        )

        # The cover image can't be reused by file_id — Telegram requires a
        # fresh upload of it on every send. It's re-uploaded here from the
        # in-memory bytes captured at /setthumbnail time (no re-download).
        cover_stream = io.BytesIO(current_thumbnail)
        cover_stream.name = "thumbnail.jpg"
        uploaded_cover = await client.save_file(cover_stream)
        uploaded_cover_media = await client.invoke(
            raw.functions.messages.UploadMedia(
                peer=peer,
                media=raw.types.InputMediaUploadedPhoto(file=uploaded_cover),
            )
        )
        video_cover = raw.types.InputPhoto(
            id=uploaded_cover_media.photo.id,
            access_hash=uploaded_cover_media.photo.access_hash,
            file_reference=uploaded_cover_media.photo.file_reference,
        )

        media = raw.types.InputMediaDocument(
            id=input_video,
            video_cover=video_cover,
        )

        text_kwargs = await utils.parse_text_entities(client, message.caption or "", None, None)

        await client.invoke(
            raw.functions.messages.SendMedia(
                peer=peer,
                media=media,
                random_id=client.rnd_id(),
                **text_kwargs,
            )
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
