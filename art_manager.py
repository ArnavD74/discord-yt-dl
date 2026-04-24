import os
import re


class ArtManager:
    """Loads and looks up pre-extracted artist cover art."""

    def __init__(self, art_dir: str):
        self.art_dir = art_dir
        self.artists: dict[str, str] = {}  # normalized name -> file path
        self._load()

    def _normalize(self, name: str) -> str:
        return re.sub(r"[^a-z0-9]", "", name.lower())

    def _primary_artist(self, name: str) -> str:
        """Strip featured artists: 'X ft. Y' -> 'X'."""
        return re.split(r"\s+(?:ft\.?|feat\.?|featuring|&|,|x\s)\s*", name, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    def _load(self):
        if not os.path.isdir(self.art_dir):
            return
        for fname in os.listdir(self.art_dir):
            if not fname.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            artist_name = os.path.splitext(fname)[0]
            normalized = self._normalize(artist_name)
            self.artists[normalized] = os.path.join(self.art_dir, fname)
        print(f"ArtManager: loaded art for {len(self.artists)} artists")

    def reload(self):
        self.artists.clear()
        self._load()

    def _resolve_path(self, artist: str) -> str | None:
        """Find art path by full name, then by primary artist."""
        path = self.artists.get(self._normalize(artist))
        if path:
            return path
        primary = self._primary_artist(artist)
        if primary != artist:
            path = self.artists.get(self._normalize(primary))
        return path

    def get_art(self, artist: str) -> bytes | None:
        """Return cover art bytes for an artist, or None."""
        path = self._resolve_path(artist)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        return None

    def get_art_mime(self, artist: str) -> str:
        """Return MIME type of the art file."""
        path = self._resolve_path(artist)
        if path and path.lower().endswith(".png"):
            return "image/png"
        return "image/jpeg"

    def list_artists(self) -> list[str]:
        """Return list of artists with loaded art (original filenames)."""
        results = []
        for fname in os.listdir(self.art_dir):
            if fname.lower().endswith((".jpg", ".jpeg", ".png")):
                results.append(os.path.splitext(fname)[0])
        return sorted(results)
