import discord
from discord import app_commands
import os
import re
import asyncio
import hashlib
import shutil
from aiohttp import web

from downloader import download_audio
from metadata import clean_title_and_tag
from art_manager import ArtManager

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
GUILD_ID = int(os.environ["GUILD_ID"])
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ART_DIR = os.environ.get("ART_DIR", "/app/artist_art")
DOWNLOAD_BASE_URL = os.environ["DOWNLOAD_BASE_URL"]
SERVE_DIR = "/tmp/ytdl-serve"
FILE_TTL_HOURS = 24

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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

# Maps download_id -> {"filename": ...}
pending_downloads = {}


def stage_for_download(filepath: str, filename: str) -> str:
    """Copy file to serve directory and return a download ID."""
    os.makedirs(SERVE_DIR, exist_ok=True)
    download_id = hashlib.sha256(f"{filepath}{filename}".encode()).hexdigest()[:12]
    dest = os.path.join(SERVE_DIR, download_id)
    shutil.copy2(filepath, dest)
    pending_downloads[download_id] = {"filename": filename}
    return download_id


async def handle_download(request):
    """Serve a file with Content-Disposition: attachment to force download."""
    download_id = request.match_info["download_id"]
    filepath = os.path.join(SERVE_DIR, download_id)
    meta = pending_downloads.get(download_id)

    if not meta or not os.path.exists(filepath):
        return web.Response(status=404, text="File not found or expired")

    filename = meta["filename"]
    return web.FileResponse(
        filepath,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "audio/mpeg",
        },
    )


async def cleanup_old_files():
    """Periodically remove files older than FILE_TTL_HOURS."""
    while True:
        await asyncio.sleep(3600)
        if not os.path.exists(SERVE_DIR):
            continue
        import time
        cutoff = time.time() - (FILE_TTL_HOURS * 3600)
        for fname in os.listdir(SERVE_DIR):
            fpath = os.path.join(SERVE_DIR, fname)
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                pending_downloads.pop(fname, None)
                print(f"Cleaned up expired download: {fname}")


async def start_download_server():
    """Start the aiohttp download server on port 8080."""
    app = web.Application()
    app.router.add_get("/dl/{download_id}", handle_download)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    print(f"Download server listening on :8080")
    print(f"Public URL: {DOWNLOAD_BASE_URL}")


# --- Slash commands (ephemeral responses, only visible to the caller) ---

guild = discord.Object(id=GUILD_ID)


@tree.command(name="reload", description="Reload artist cover art from disk", guild=guild)
async def cmd_reload(interaction: discord.Interaction):
    art_manager.reload()
    artists = art_manager.list_artists()
    await interaction.response.send_message(
        f"Reloaded art for {len(artists)} artists: {', '.join(artists) or 'none'}",
        ephemeral=True,
    )


@tree.command(name="artists", description="List artists with cover art", guild=guild)
async def cmd_artists(interaction: discord.Interaction):
    artists = art_manager.list_artists()
    if artists:
        await interaction.response.send_message(
            f"**Artists with cover art:**\n" + "\n".join(f"- {a}" for a in artists),
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "No artist art loaded. Drop images in `artist_art/` and run `/reload`.",
            ephemeral=True,
        )


@client.event
async def on_interaction(interaction: discord.Interaction):
    await tree.process_commands(interaction)


@client.event
async def on_ready():
    await tree.sync(guild=guild)
    artists = art_manager.list_artists()
    print(f"yt-dl bot ready as {client.user}")
    print(f"Listening on channel {CHANNEL_ID}")
    print(f"Slash commands synced to guild {GUILD_ID}")
    print(f"Gemini: {'enabled' if GEMINI_API_KEY else 'disabled (no GEMINI_API_KEY, using regex fallback)'}")
    print(f"Artist art loaded: {len(artists)} artists")
    if artists:
        print(f"  Artists: {', '.join(artists)}")


@client.event
async def on_message(message):
    if message.author.bot or message.channel.id != CHANNEL_ID:
        return

    urls = URL_PATTERN.findall(message.content.strip())
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

        # Build filename
        if artist:
            filename = f"{artist} - {title}.mp3"
        else:
            filename = f"{title}.mp3"
        filename = re.sub(r'[<>:"/\\|?*]', "", filename)

        art_note = ""
        if artist and art_manager.get_art(artist):
            art_note = " | cover art embedded"

        label = f"**{artist + ' - ' if artist else ''}{title}**{art_note}"

        await status.edit(content=f"Uploading...")
        download_id = await asyncio.to_thread(stage_for_download, filepath, filename)
        download_url = f"{DOWNLOAD_BASE_URL.rstrip('/')}/dl/{download_id}"
        await message.channel.send(
            content=f"{label}\n[Download MP3]({download_url})",
            suppress_embeds=True,
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


async def main():
    await start_download_server()
    asyncio.create_task(cleanup_old_files())
    await client.start(DISCORD_TOKEN)


asyncio.run(main())
