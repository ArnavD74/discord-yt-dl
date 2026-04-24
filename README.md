# discord-yt-dl

Discord bot that monitors a channel for YouTube/SoundCloud links, downloads the audio as 320kbps MP3, cleans up the title, embeds ID3 tags + artist cover art, and uploads it back to Discord.

## Setup

### Prerequisites
- Python 3.12+ (or Docker)
- ffmpeg
- A [Discord bot](https://discord.com/developers/applications) with Message Content Intent enabled
- (Optional) A [Gemini API key](https://aistudio.google.com/apikey) for smarter title parsing

### Run with Docker (recommended)

```bash
cp .env.example .env
# Fill in your tokens in .env

docker compose up -d
```

### Run without Docker

```bash
cp .env.example .env
# Fill in your tokens in .env

pip install -r requirements.txt
python bot.py
```

When running outside Docker, the bot uses `./artist_art` and `/tmp/ytdl` by default. Override with env vars `ART_DIR` and `DOWNLOAD_DIR` if needed.

### Gemini (optional)

If `GEMINI_API_KEY` is set, the bot uses Gemini to intelligently parse artist/title from video titles and match against your known artist art. Without it, the bot falls back to regex parsing (splits `"Artist - Title"` patterns, strips common YouTube tags like `[Official Video]`, `(Lyrics)`, etc.). Both modes work fine -- Gemini just handles edge cases better.

## Artist Cover Art

The bot can embed cover art into downloaded MP3s. To set this up:

1. Drop MP3 files that already have cover art into `mp3_inbox/`
2. Run `python extract_art.py` to pull art into `artist_art/`
3. Or manually place images in `artist_art/` named `Artist Name.jpg`

The bot fuzzy-matches artist names and handles featured artist tags (`ft.`, `feat.`, etc.).

## Bot Commands

- **Send a YouTube/SoundCloud URL** in the configured channel - the bot downloads, tags, and uploads the MP3
- `!artists` - list artists with loaded cover art
- `!reload` - reload cover art from disk

## Utility Scripts

- `extract_art.py` - extract cover art from existing MP3s into `artist_art/`
- `apply_art.py` - batch-apply cover art from `artist_art/` to MP3s in `mp3_inbox/`
