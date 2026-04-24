import os
import re
from urllib.parse import urlparse, parse_qs
import yt_dlp


DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/ytdl")


def _clean_url(url: str) -> str:
    """Strip playlist params and tracking junk, keep only the video ID."""
    parsed = urlparse(url)
    if "youtube.com" in parsed.hostname or "music.youtube.com" in parsed.hostname:
        params = parse_qs(parsed.query)
        if "v" in params:
            clean = f"https://www.youtube.com/watch?v={params['v'][0]}"
            print(f"URL cleaned: {url} -> {clean}")
            return clean
    elif "youtu.be" in parsed.hostname:
        # youtu.be/VIDEO_ID?list=... -> strip query
        clean = f"https://youtu.be{parsed.path}"
        print(f"URL cleaned: {url} -> {clean}")
        return clean
    return url


def download_audio(url: str) -> tuple[str, str]:
    """Download best audio from URL, convert to 320kbps MP3.

    Returns (filepath, video_title).
    """
    url = _clean_url(url)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ],
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info["id"]
        title = info.get("title", video_id)

    filepath = os.path.join(DOWNLOAD_DIR, f"{video_id}.mp3")
    if not os.path.exists(filepath):
        # yt-dlp sometimes uses .webm -> .mp3 naming; find the actual file
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(video_id) and f.endswith(".mp3"):
                filepath = os.path.join(DOWNLOAD_DIR, f)
                break

    return filepath, title
