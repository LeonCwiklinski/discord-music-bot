"""
music_player.py - Queue management and audio playback.

One instance per bot. Handles the FFmpeg subprocess lifecycle carefully
to keep memory and CPU usage low (important for Raspberry Pi Zero 2 W).

Tracks are identified by their full file path — no metadata dict needed.
"""

import asyncio
import logging
from collections import deque

import discord

import library

log = logging.getLogger(__name__)

# FFmpeg audio options:
#   -vn              skip any video stream (handles .mp4 audio files)
#   aresample=48000  resample to Discord's native rate (avoids double conversion)
#   -ac 2            force stereo output
#   -loglevel quiet  suppress FFmpeg console noise
FFMPEG_OPTIONS = {
    "executable": "ffmpeg",
    "options": "-vn -af aresample=48000 -ac 2 -loglevel quiet",
}

MAX_QUEUE = 20


class MusicPlayer:
    def __init__(self) -> None:
        self.queue: deque[str] = deque()            # full file paths, FIFO
        self.current: str | None = None              # path of track currently playing
        self.voice_client: discord.VoiceClient | None = None
        self._lock = asyncio.Lock()                  # prevents concurrent play calls

    # ------------------------------------------------------------------
    # Voice channel management
    # ------------------------------------------------------------------

    async def join(self, channel: discord.VoiceChannel) -> None:
        """Connect to a voice channel, or move if already in a different one."""
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()
        log.info("Connected to voice channel: %s", channel.name)

    async def leave(self) -> None:
        """Stop playback, clear state, and disconnect from voice."""
        self.stop()
        self.queue.clear()
        self.current = None
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        log.info("Disconnected from voice channel")

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def enqueue(self, path: str) -> bool:
        """Add a track to the queue. Returns False if the queue is full."""
        if len(self.queue) >= MAX_QUEUE:
            return False
        self.queue.append(path)
        log.info(
            "Queued: %s (queue size: %d)",
            library.song_display_name(path),
            len(self.queue),
        )
        return True

    def clear_queue(self) -> None:
        """Remove all pending tracks. Does not stop the current track."""
        self.queue.clear()
        log.info("Queue cleared")

    def list_queue(self) -> list[str]:
        """Return the queue as a list of display names."""
        return [library.song_display_name(p) for p in self.queue]

    # ------------------------------------------------------------------
    # Playback control
    # ------------------------------------------------------------------

    async def play(self, path: str) -> None:
        """Play a track immediately, interrupting whatever is currently playing."""
        async with self._lock:
            self._stop_current()
            self.current = path
            self._start_ffmpeg(path)

    async def play_next(self) -> None:
        """Advance to the next track in the queue."""
        async with self._lock:
            if not self.queue:
                self.current = None
                log.info("Queue empty — playback stopped")
                return
            path = self.queue.popleft()
            self.current = path
            self._start_ffmpeg(path)

    def pause(self) -> bool:
        """Pause playback. Returns True if successful."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            log.info("Playback paused")
            return True
        return False

    def resume(self) -> bool:
        """Resume paused playback. Returns True if successful."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            log.info("Playback resumed")
            return True
        return False

    def stop(self) -> None:
        """Stop the current track. Does not clear the queue."""
        self._stop_current()
        self.current = None

    async def skip(self) -> None:
        """Stop the current track and immediately play the next one."""
        self._stop_current()
        self.current = None
        await self.play_next()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_ffmpeg(self, path: str) -> None:
        """Spawn an FFmpeg process and begin streaming audio to Discord."""
        if not self.voice_client or not self.voice_client.is_connected():
            log.warning("Cannot play — not connected to a voice channel")
            return

        name = library.song_display_name(path)
        try:
            source = discord.FFmpegPCMAudio(path, **FFMPEG_OPTIONS)
            self.voice_client.play(source, after=self._after_track)
            log.info("Now playing: %s", name)
        except Exception as e:
            # If FFmpeg fails (missing file, bad format, etc.) skip and continue
            log.error("FFmpeg failed for %s: %s — skipping", name, e)
            loop = self.voice_client.loop
            asyncio.run_coroutine_threadsafe(self.play_next(), loop)

    def _stop_current(self) -> None:
        """Stop the voice client. discord.py cleans up the FFmpeg process."""
        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()

    def _after_track(self, error: Exception | None) -> None:
        """
        Called by discord.py in a background thread after a track finishes.
        Schedules play_next() safely back on the event loop.
        """
        if error:
            log.error("Playback error: %s", error)
        if self.voice_client and self.voice_client.loop:
            asyncio.run_coroutine_threadsafe(self.play_next(), self.voice_client.loop)

    # ------------------------------------------------------------------
    # Status properties
    # ------------------------------------------------------------------

    @property
    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())

    @property
    def is_paused(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_paused())

    @property
    def queue_size(self) -> int:
        return len(self.queue)
