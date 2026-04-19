"""
library.py - Music discovery via filesystem layout.

Scans the music directory once at startup and builds in-memory indexes.
All lookups and autocomplete queries run against memory — no disk I/O at
query time, which keeps autocomplete fast even on a Raspberry Pi Zero 2 W.

Expected directory structure:
  music/
    songs/
      mysong.mp3
    playlists/
      gym/
        track1.mp3
        track2.mp3
      chill/
        track3.mp3

Supported audio formats: .mp3, .mp4, .ogg, .flac, .wav
"""

import os
import logging

log = logging.getLogger(__name__)

MUSIC_DIR     = "music"
SONGS_DIR     = os.path.join(MUSIC_DIR, "songs")
PLAYLISTS_DIR = os.path.join(MUSIC_DIR, "playlists")

AUDIO_EXTENSIONS = {".mp3", ".mp4", ".ogg", ".flac", ".wav"}

# ---------------------------------------------------------------------------
# In-memory indexes — populated once by load()
# ---------------------------------------------------------------------------
_songs: dict[str, str] = {}            # lowercase stem -> full path
_song_names: list[str] = []            # display stems, sorted alphabetically
_playlists: dict[str, list[str]] = {}  # playlist name -> [full path, ...]


def _stem(filename: str) -> str:
    """Return the filename without its extension (used as the display name)."""
    return os.path.splitext(filename)[0]


def load() -> None:
    """
    Scan the music directory and build all in-memory indexes.
    Call this once at startup before the bot connects.
    """
    global _songs, _song_names, _playlists

    _songs = {}
    _playlists = {}

    # --- Individual songs ---
    if os.path.isdir(SONGS_DIR):
        for fname in os.listdir(SONGS_DIR):
            if os.path.splitext(fname)[1].lower() not in AUDIO_EXTENSIONS:
                continue
            full_path = os.path.join(SONGS_DIR, fname)
            name = _stem(fname)
            _songs[name.lower()] = full_path

    _song_names = sorted(_songs.keys())

    # --- Playlists (each subfolder is one playlist) ---
    if os.path.isdir(PLAYLISTS_DIR):
        for pl_name in os.listdir(PLAYLISTS_DIR):
            pl_path = os.path.join(PLAYLISTS_DIR, pl_name)
            if not os.path.isdir(pl_path):
                continue
            tracks = [
                os.path.join(pl_path, f)
                for f in os.listdir(pl_path)
                if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS
            ]
            if tracks:
                _playlists[pl_name] = tracks

    log.info(
        "Library loaded: %d songs, %d playlists (%s)",
        len(_songs),
        len(_playlists),
        ", ".join(_playlists.keys()) or "none",
    )


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def find_song(name: str) -> str | None:
    """Return the full path for a song name (case-insensitive), or None."""
    return _songs.get(name.lower())


def get_playlist_tracks(name: str) -> list[str]:
    """Return all track paths for a playlist (case-insensitive), or []."""
    for pl_name, tracks in _playlists.items():
        if pl_name.lower() == name.lower():
            return tracks
    return []


def song_display_name(path: str) -> str:
    """Extract a human-readable name from a full file path."""
    return _stem(os.path.basename(path))


# ---------------------------------------------------------------------------
# Autocomplete — called on every keystroke, must be near-instant
# ---------------------------------------------------------------------------

def autocomplete_songs(partial: str) -> list[str]:
    """Return up to 25 song names that contain the partial string."""
    partial = partial.lower()
    return [name for name in _song_names if partial in name][:25]


def autocomplete_playlists(partial: str) -> list[str]:
    """Return up to 25 playlist names that contain the partial string."""
    partial = partial.lower()
    return sorted(pl for pl in _playlists if partial in pl.lower())[:25]
