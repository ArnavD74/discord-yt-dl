import json
import re
import asyncio
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, APIC, ID3NoHeaderError

from art_manager import ArtManager


GEMINI_PROMPT_TEMPLATE = """Given this YouTube video title, extract the primary artist name and song title.
Remove tags like [HQ], (Official Audio), (Official Video), (Lyrics), (Lyric Video),
(Visualizer), [Prod. by ...], (prod. ...), [Official Music Video], 4K, HD,
{{BEST QUALITY}}, (Unreleased), (NEW), and any similar non-title content.

Known artists: {artists}

Rules:
- "artist" MUST be set to one of the known artists above if the primary artist matches.
  Use exact spelling/capitalization from the list. Ignore featured artists for matching
  (e.g. "Playboi Carti ft. Swae Lee" -> "Playboi Carti").
- If the primary artist is not in the known list, return their name as-is.
- "title" should be the clean song title only, no artist name, no featured artists, no tags.

Return ONLY valid JSON with no markdown formatting:
{{"artist": "Artist Name", "title": "Song Title"}}

Video title: """


def _parse_gemini_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    return json.loads(raw)


def _clean_title_regex(video_title: str) -> tuple[str | None, str]:
    """Extract artist and title using regex. Fallback when Gemini is unavailable."""
    # Strip common YouTube junk tags
    cleaned = re.sub(
        r"\s*[\[\(]?\s*(?:Official\s+(?:Music\s+)?Video|Official\s+Audio|Official\s+Visualizer"
        r"|Lyrics?\s*(?:Video)?|Lyric\s+Video|Visualizer|Audio|HQ|HD|4K"
        r"|prod\.?\s*(?:by\s+)?\S+|BEST\s+QUALITY|Unreleased|NEW"
        r")\s*[\]\)]?\s*",
        "", video_title, flags=re.IGNORECASE
    ).strip()

    # Try "Artist - Title" split
    match = re.match(r"^(.+?)\s*[-–—]\s+(.+)$", cleaned)
    if match:
        artist = match.group(1).strip()
        title = match.group(2).strip()
        # Strip featured artists from title
        title = re.split(r"\s+(?:ft\.?|feat\.?|featuring)\s+", title, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        print(f"Regex: '{video_title}' -> artist='{artist}', title='{title}'")
        return artist, title

    print(f"Regex: '{video_title}' -> artist=None, title='{cleaned}'")
    return None, cleaned or video_title


async def clean_title_gemini(video_title: str, gemini_api_key: str,
                             known_artists: list[str]) -> tuple[str | None, str]:
    """Use Gemini to extract artist and clean song title from a video title."""
    import google.generativeai as genai

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

    prompt = GEMINI_PROMPT_TEMPLATE.format(artists=", ".join(known_artists))
    response = await asyncio.to_thread(
        model.generate_content, prompt + video_title
    )
    result = _parse_gemini_json(response.text)
    artist = result.get("artist")
    title = result.get("title", video_title)
    print(f"Gemini: '{video_title}' -> artist='{artist}', title='{title}'")
    return artist, title


def tag_mp3(filepath: str, artist: str | None, title: str,
            art_manager: ArtManager) -> None:
    """Write ID3 tags (artist, title, cover art) to an MP3 file."""
    try:
        audio = MP3(filepath, ID3=ID3)
    except Exception:
        audio = MP3(filepath)

    # Ensure ID3 tags exist
    try:
        audio.add_tags()
    except Exception:
        pass  # tags already exist

    tags = audio.tags
    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.delall("APIC")

    tags.add(TIT2(encoding=3, text=title))
    if artist:
        tags.add(TPE1(encoding=3, text=artist))

    # Embed cover art if we have it for this artist
    if artist:
        art_data = art_manager.get_art(artist)
        print(f"Art lookup: artist='{artist}', found={art_data is not None}")
        if art_data:
            mime = art_manager.get_art_mime(artist)
            tags.add(APIC(
                encoding=3,
                mime=mime,
                type=3,  # front cover
                desc="Cover",
                data=art_data,
            ))

    audio.save()


async def clean_title_and_tag(filepath: str, video_title: str,
                              art_manager: ArtManager,
                              gemini_api_key: str | None) -> tuple[str | None, str]:
    """Clean the title via Gemini (or regex fallback), then write ID3 tags. Returns (artist, title)."""
    if gemini_api_key:
        known_artists = art_manager.list_artists()
        artist, title = await clean_title_gemini(video_title, gemini_api_key, known_artists)
    else:
        artist, title = _clean_title_regex(video_title)
    await asyncio.to_thread(tag_mp3, filepath, artist, title, art_manager)
    return artist, title
