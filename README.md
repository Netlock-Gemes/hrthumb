# Telegram Thumbnail Bot

A minimal bot with two features:

1. `/setthumbnail` (as a reply to a photo) — sets the active thumbnail.
2. Any video sent to the bot is forwarded to a destination channel using that thumbnail.

## Important Pyrofork/Telegram limitation

The video is **never downloaded**: its existing `file_id` is reused directly
in `send_video`, so it goes server-to-server on Telegram's side.

However, Telegram's Bot API does **not** allow a video `thumb` to be reused
by `file_id` — a thumbnail must be uploaded as a fresh JPEG file on every
`send_video` call ("Thumbnails can't be reused and can be only uploaded as a
new file"). To respect this while avoiding repeated downloads, the bot
downloads the thumbnail **photo only** (a small image, not the video) a
single time — when `/setthumbnail` is used — and keeps those bytes in
memory. Every subsequent video re-uploads that same in-memory thumbnail.
This is the closest technically correct approach: zero video downloads,
one small one-time image download per thumbnail change.

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
