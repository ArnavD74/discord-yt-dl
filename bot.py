import discord
import os
import re
import asyncio

from downloader import download_audio
from metadata import clean_title_and_tag
from art_manager import ArtManager

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
ART_DIR = os.environ.get("ART_DIR", "/app/artist_art")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

art_manager = ArtManager(ART_DIR)

# Match YouTube, YouTube Music, and SoundCloud URLs
URL_PATTERN = re.compile(
    r"(https?://(?:www\.|m\.)?(?:"
    r"youtube\.com/watch\?[^\s]*v=[^\s&]+"
    r"|youtu\.be/[^\s?]+"
    r"|music\.youtube\.com/watch\?[^\s]*v=[^\s&]+"
    r"|soundcloud\.com/[^\s]+"
    r")(?:[^\s]*)?)"
)

MAX_DISCORD_FILE_SIZE = 25 * 1024 * 1024  # 25MB


@client.event
async def on_ready():
    artists = art_manager.list_artists()
    print(f"yt-dl bot ready as {client.user}")
    print(f"Listening on channel {CHANNEL_ID}")
    print(f"Artist art loaded: {len(artists)} artists")
    if artists:
        print(f"  Artists: {', '.join(artists)}")


@client.event
async def on_message(message):
    if message.author.bot or message.channel.id != CHANNEL_ID:
        return

    text = message.content.strip()

    # Reload artist art on command
    if text.lower() == "!reload":
        art_manager.reload()
        artists = art_manager.list_artists()
        await message.reply(f"Reloaded art for {len(artists)} artists: {', '.join(artists) or 'none'}")
        return

    if text.lower() == "!artists":
        artists = art_manager.list_artists()
        if artists:
            await message.reply(f"**Artists with cover art:**\n" + "\n".join(f"- {a}" for a in artists))
        else:
            await message.reply("No artist art loaded. Drop MP3s in `mp3_inbox/` and run `extract_art.py`.")
        return

    urls = URL_PATTERN.findall(text)
    if not urls:
        return

    for url in urls:
        await process_url(message, url)


async def process_url(message, url):
    status = await message.reply(f"Downloading...")

    try:
        # Download audio (runs in thread to avoid blocking)
        filepath, video_title = await asyncio.to_thread(download_audio, url)

        await status.edit(content=f"Tagging metadata...")

        # Clean title via Gemini and write ID3 tags
        artist, title = await clean_title_and_tag(
            filepath, video_title, art_manager, GEMINI_API_KEY
        )

        # Check file size
        file_size = os.path.getsize(filepath)
        if file_size > MAX_DISCORD_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            await status.edit(content=f"File too large ({size_mb:.1f}MB, limit 25MB)")
            os.remove(filepath)
            return

        await status.edit(content=f"Uploading...")

        # Build filename
        if artist:
            filename = f"{artist} - {title}.mp3"
        else:
            filename = f"{title}.mp3"
        filename = re.sub(r'[<>:"/\\|?*]', "", filename)

        art_note = ""
        if artist and art_manager.get_art(artist):
            art_note = " | cover art embedded"

        # Upload to Discord (send as a new message, not a reply)
        await message.channel.send(
            content=f"**{artist + ' - ' if artist else ''}{title}**{art_note}",
            file=discord.File(filepath, filename=filename),
        )

        await status.delete()
        await message.delete()

    except Exception as e:
        import traceback
        traceback.print_exc()
        await status.edit(content=f"Error: {e}")

    finally:
        # Cleanup temp file
        if "filepath" in locals() and os.path.exists(filepath):
            os.remove(filepath)


client.run(DISCORD_TOKEN)
