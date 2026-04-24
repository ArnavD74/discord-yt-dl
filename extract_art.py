#!/usr/bin/env python3
"""Extract artist names and cover art from existing MP3 files.

Usage:
    python extract_art.py [mp3_directory]

Scans the given directory (default: ./mp3_inbox) for MP3 files,
reads ID3 tags to get artist names, and saves embedded cover art
to ./artist_art/{Artist Name}.jpg

Drop your MP3 collection into mp3_inbox/ and run this once.
"""

import os
import sys
from mutagen.mp3 import MP3
from mutagen.id3 import ID3


def extract(mp3_dir: str = "mp3_inbox", art_dir: str = "artist_art"):
    os.makedirs(art_dir, exist_ok=True)

    # Walk subdirectories too (Music/Artist/song.mp3 layout)
    mp3_files = []
    for root, _dirs, files in os.walk(mp3_dir):
        for f in files:
            if f.lower().endswith(".mp3"):
                mp3_files.append(os.path.join(root, f))

    if not mp3_files:
        print(f"No MP3 files found in {mp3_dir}/")
        print("Drop your MP3s there and re-run this script.")
        return

    print(f"Scanning {len(mp3_files)} MP3 files...")

    artists_found = {}  # artist_name -> (art_bytes, art_ext, art_size)
    artists_no_art = set()

    for path in sorted(mp3_files):
        fname = os.path.basename(path)
        # Use parent directory as fallback artist name
        parent_dir = os.path.basename(os.path.dirname(path))
        try:
            audio = MP3(path, ID3=ID3)
        except Exception as e:
            print(f"  skip {fname}: {e}")
            continue

        tags = audio.tags
        if not tags:
            print(f"  skip {fname}: no ID3 tags")
            continue

        # Get artist
        artist = None
        for key in ("TPE1", "TPE2"):
            if key in tags:
                artist = str(tags[key])
                break

        if not artist:
            # Fall back to parent directory name if no ID3 artist tag
            if parent_dir and parent_dir != os.path.basename(mp3_dir):
                artist = parent_dir
            else:
                print(f"  skip {fname}: no artist tag")
                continue

        # Normalize artist name for dedup
        artist_clean = artist.strip()

        # Get cover art
        art_data = None
        art_ext = "jpg"
        for key in tags:
            if key.startswith("APIC"):
                apic = tags[key]
                art_data = apic.data
                if apic.mime == "image/png":
                    art_ext = "png"
                break

        if art_data:
            existing = artists_found.get(artist_clean)
            if not existing or len(art_data) > existing[2]:
                artists_found[artist_clean] = (art_data, art_ext, len(art_data))
                if not existing:
                    print(f"  {artist_clean}: extracted art from {fname}")
                else:
                    print(f"  {artist_clean}: found larger art in {fname}")
        else:
            if artist_clean not in artists_found:
                artists_no_art.add(artist_clean)
                print(f"  {artist_clean}: no cover art in {fname}")

    # Save art files
    saved = 0
    for artist_name, (data, ext, _size) in artists_found.items():
        # Use artist name as filename, sanitize for filesystem
        safe_name = "".join(c if c.isalnum() or c in " -_" else "" for c in artist_name)
        safe_name = safe_name.strip()
        if not safe_name:
            safe_name = "unknown"

        out_path = os.path.join(art_dir, f"{safe_name}.{ext}")
        with open(out_path, "wb") as f:
            f.write(data)
        saved += 1

    print(f"\nDone! Saved cover art for {saved} artists to {art_dir}/")

    no_art_only = artists_no_art - set(artists_found.keys())
    if no_art_only:
        print(f"\nArtists without cover art ({len(no_art_only)}):")
        for a in sorted(no_art_only):
            print(f"  - {a}")
        print("You can manually add art for these by placing a .jpg/.png")
        print(f"named after the artist in {art_dir}/")


if __name__ == "__main__":
    mp3_dir = sys.argv[1] if len(sys.argv) > 1 else "mp3_inbox"
    extract(mp3_dir)
