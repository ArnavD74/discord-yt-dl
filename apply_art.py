#!/usr/bin/env python3
"""Apply cover art from artist_art/ to MP3 files in mp3_inbox/.

Walks mp3_inbox/, reads each MP3's artist tag (or falls back to parent dir name),
and embeds the matching cover art from artist_art/ if available.
"""

import os
import sys
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC


def apply_art(mp3_dir: str = "mp3_inbox", art_dir: str = "artist_art",
              artists_filter: set[str] | None = None):
    # Load available art
    art_map = {}  # normalized artist -> (path, mime)
    for fname in os.listdir(art_dir):
        if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        artist_name = os.path.splitext(fname)[0]
        ext = os.path.splitext(fname)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        art_map[artist_name.lower()] = (os.path.join(art_dir, fname), mime)

    # Walk MP3s
    updated = 0
    skipped = 0
    for root, _dirs, files in os.walk(mp3_dir):
        for fname in sorted(files):
            if not fname.lower().endswith(".mp3"):
                continue
            path = os.path.join(root, fname)
            parent_dir = os.path.basename(root)

            try:
                audio = MP3(path, ID3=ID3)
            except Exception:
                continue

            tags = audio.tags
            if not tags:
                try:
                    audio.add_tags()
                    tags = audio.tags
                except Exception:
                    continue

            # Get artist from tags or parent dir
            artist = None
            for key in ("TPE1", "TPE2"):
                if key in tags:
                    artist = str(tags[key]).strip()
                    break
            if not artist and parent_dir != os.path.basename(mp3_dir):
                artist = parent_dir

            if not artist:
                continue

            # Filter to specific artists if requested
            if artists_filter and artist.lower() not in artists_filter:
                continue

            # Check if art exists for this artist
            art_entry = art_map.get(artist.lower())
            if not art_entry:
                continue

            art_path, mime = art_entry

            # Skip if already has cover art
            has_art = any(k.startswith("APIC") for k in tags)
            if has_art:
                skipped += 1
                continue

            # Embed art
            with open(art_path, "rb") as f:
                art_data = f.read()

            tags.delall("APIC")
            tags.add(APIC(
                encoding=3,
                mime=mime,
                type=3,  # front cover
                desc="Cover",
                data=art_data,
            ))
            audio.save()
            updated += 1
            print(f"  + {artist}: {fname}")

    print(f"\nDone! Updated {updated} files, skipped {skipped} (already had art)")


if __name__ == "__main__":
    # Optional: pass artist names to filter
    if len(sys.argv) > 1:
        artists = {a.lower() for a in sys.argv[1:]}
        apply_art(artists_filter=artists)
    else:
        apply_art()
