# Telegram Thumbnail Bot

A minimal bot with two features:

1. `/setthumbnail` (as a reply to a photo) — sets the active thumbnail.
2. Any video sent to the bot is forwarded to a destination channel using that thumbnail.

## Important Pyrofork/Telegram limitation

The video is **never downloaded**: its existing `file_id` is decoded into a
raw document reference and reused directly, so the video bytes never touch
this server.

Telegram's underlying protocol has **no way to attach a custom thumbnail to
a reused video reference** — the classic `thumb` field only exists on the
"upload a new video" media type, so it's silently ignored whenever a video
is resent by `file_id` (this was verified directly against pyrofork's
source and Telegram's raw API schema). The closest correct equivalent for a
*reused* video is Telegram's **video cover** field, which a reused
reference does support, and that's what this bot sets instead — it's the
custom image shown before playback, functionally the same as what you'd
expect a "thumbnail" to do.

The cover image itself can't be reused by `file_id` either — Telegram
requires a fresh upload of it on every send. To satisfy that without any
extra downloads, the bot downloads the small cover/thumbnail JPEG (not the
video) exactly once, when `/setthumbnail` is used, and keeps those bytes in
memory. Every subsequent video re-uploads that same in-memory image as its
cover.

The thumbnail is kept in memory only (no database, no disk). It resets if
the bot restarts, and is overwritten each time `/setthumbnail` is used.

## 1. Create Telegram API credentials

Go to https://my.telegram.org, log in, open "API development tools", and
create an application to get your `API_ID` and `API_HASH`.

## 2. Create the bot

Message [@BotFather](https://t.me/BotFather) on Telegram, use `/newbot`,
and follow the prompts to get your `BOT_TOKEN`.

## 3. Add the bot to the destination channel

Add the bot to your destination channel and give it permission to post
messages. Then get the channel's numeric ID (it looks like
`-1001234567890`) — for example by forwarding a message from the channel
to [@userinfobot](https://t.me/userinfobot), or via any similar tool.

## 4. Configure `.env`

Copy `.env.example` to `.env` and fill in your values:

```
API_ID=12345678
API_HASH=xxxxxxxxxxxxxxxx
BOT_TOKEN=123456:xxxxxxxx
DESTINATION_CHANNEL_ID=-1001234567890
```

## 5. Start

```
docker compose up -d --build
```

## 6. Logs

```
docker compose logs -f
```

## 7. Stop

```
docker compose down
```
