"""
main.py - Discord music bot entry point.

Slash commands under /dj:
  /dj play song:<name>
  /dj play playlist:<name>
  /dj queue add song:<name>
  /dj queue list
  /dj queue clear
  /dj next
  /dj pause
  /dj resume
  /dj stop
  /dj help

Configuration via environment variables:
  DISCORD_TOKEN    - your bot token
  DISCORD_GUILD_ID - your server ID (integer)

Filesystem layout (no metadata file needed):
  music/
    songs/         <- individual tracks
    playlists/
      gym/         <- each subfolder is a playlist
      chill/

Optimised for Raspberry Pi Zero 2 W: single guild, minimal memory usage.
"""

import logging
import os
import random
import sys

import discord
from discord import app_commands

import library
import music_player

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — set these as environment variables, never hardcode them
# ---------------------------------------------------------------------------
TOKEN    = os.environ.get("DISCORD_TOKEN", "")
GUILD_ID = int(os.environ.get("DISCORD_GUILD_ID", "0"))

if not TOKEN or not GUILD_ID:
    log.error("Missing configuration. Please set DISCORD_TOKEN and DISCORD_GUILD_ID.")
    sys.exit(1)

GUILD = discord.Object(id=GUILD_ID)

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------
intents = discord.Intents.default()
intents.voice_states = True  # Required to detect users leaving voice channels

bot    = discord.Client(intents=intents)
tree   = app_commands.CommandTree(bot)
player = music_player.MusicPlayer()


# ---------------------------------------------------------------------------
# Helper: get the voice channel the command author is currently in
# ---------------------------------------------------------------------------
async def get_voice_channel(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    member = interaction.guild.get_member(interaction.user.id)
    if not member or not member.voice or not member.voice.channel:
        await interaction.response.send_message(
            "❌ You must be in a voice channel first.", ephemeral=True
        )
        return None
    return member.voice.channel


# ===========================================================================
# /dj command group
# ===========================================================================
dj = app_commands.Group(name="dj", description="Music bot controls")


# ---------------------------------------------------------------------------
# /dj play
# ---------------------------------------------------------------------------
play_group = app_commands.Group(name="play", description="Play music", parent=dj)


@play_group.command(name="song", description="Play or queue a single song")
@app_commands.describe(song="Song name (supports autocomplete)")
async def play_song(interaction: discord.Interaction, song: str) -> None:
    path = library.find_song(song)
    if not path:
        await interaction.response.send_message(f"❌ Song not found: **{song}**", ephemeral=True)
        return

    channel = await get_voice_channel(interaction)
    if not channel:
        return

    await interaction.response.defer()
    await player.join(channel)

    name = library.song_display_name(path)

    if player.is_playing or player.is_paused:
        if player.enqueue(path):
            await interaction.followup.send(
                f"➕ Added to queue: **{name}** (position {player.queue_size})"
            )
        else:
            await interaction.followup.send("❌ Queue is full (max 20 tracks).")
    else:
        await player.play(path)
        await interaction.followup.send(f"▶️ Now playing: **{name}**")


@play_song.autocomplete("song")
async def autocomplete_song(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=n, value=n) for n in library.autocomplete_songs(current)]


@play_group.command(name="playlist", description="Shuffle and queue an entire playlist")
@app_commands.describe(playlist="Playlist name (supports autocomplete)")
async def play_playlist(interaction: discord.Interaction, playlist: str) -> None:
    tracks = library.get_playlist_tracks(playlist)
    if not tracks:
        await interaction.response.send_message(
            f"❌ Playlist not found: **{playlist}**", ephemeral=True
        )
        return

    channel = await get_voice_channel(interaction)
    if not channel:
        return

    await interaction.response.defer()
    await player.join(channel)

    shuffled = tracks[:]
    random.shuffle(shuffled)

    added   = sum(1 for t in shuffled if player.enqueue(t))
    skipped = len(shuffled) - added

    msg = f"🎵 Added **{added}** track(s) from **{playlist}** to the queue."
    if skipped:
        msg += f" ({skipped} skipped — queue is full)"

    if not player.is_playing and not player.is_paused:
        await player.play_next()

    await interaction.followup.send(msg)


@play_playlist.autocomplete("playlist")
async def autocomplete_playlist(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=p, value=p) for p in library.autocomplete_playlists(current)]


# ---------------------------------------------------------------------------
# /dj queue
# ---------------------------------------------------------------------------
queue_group = app_commands.Group(name="queue", description="Manage the queue", parent=dj)


@queue_group.command(name="add", description="Add a song to the queue without playing it immediately")
@app_commands.describe(song="Song name (supports autocomplete)")
async def queue_add(interaction: discord.Interaction, song: str) -> None:
    path = library.find_song(song)
    if not path:
        await interaction.response.send_message(f"❌ Song not found: **{song}**", ephemeral=True)
        return

    if player.enqueue(path):
        await interaction.response.send_message(
            f"➕ Queued: **{library.song_display_name(path)}** (position {player.queue_size})"
        )
    else:
        await interaction.response.send_message("❌ Queue is full (max 20 tracks).")


@queue_add.autocomplete("song")
async def autocomplete_queue_add(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=n, value=n) for n in library.autocomplete_songs(current)]


@queue_group.command(name="list", description="Show what is currently playing and what is up next")
async def queue_list(interaction: discord.Interaction) -> None:
    items = player.list_queue()
    lines = []

    if player.current:
        lines.append(f"▶️ **Now playing:** {library.song_display_name(player.current)}\n")

    if not items:
        lines.append("📭 Queue is empty.")
    else:
        lines.append("**Up next:**")
        for i, name in enumerate(items, 1):
            lines.append(f"`{i}.` {name}")

    await interaction.response.send_message("\n".join(lines))


@queue_group.command(name="clear", description="Remove all songs from the queue")
async def queue_clear(interaction: discord.Interaction) -> None:
    player.clear_queue()
    await interaction.response.send_message("🗑️ Queue cleared.")


# ---------------------------------------------------------------------------
# /dj controls
# ---------------------------------------------------------------------------
@dj.command(name="next", description="Skip the current track and play the next one")
async def cmd_next(interaction: discord.Interaction) -> None:
    if not player.current and not player.is_playing and not player.is_paused:
        await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)
        return
    await interaction.response.defer()
    await player.skip()
    if player.current:
        await interaction.followup.send(
            f"⏭️ Now playing: **{library.song_display_name(player.current)}**"
        )
    else:
        await interaction.followup.send("⏭️ Skipped. Queue is now empty.")


@dj.command(name="pause", description="Pause the current track")
async def cmd_pause(interaction: discord.Interaction) -> None:
    if player.pause():
        await interaction.response.send_message("⏸️ Paused.")
    else:
        await interaction.response.send_message("❌ Nothing to pause.", ephemeral=True)


@dj.command(name="resume", description="Resume a paused track")
async def cmd_resume(interaction: discord.Interaction) -> None:
    if player.resume():
        await interaction.response.send_message("▶️ Resumed.")
    else:
        await interaction.response.send_message("❌ Nothing to resume.", ephemeral=True)


@dj.command(name="stop", description="Stop playback and clear the queue")
async def cmd_stop(interaction: discord.Interaction) -> None:
    player.stop()
    player.clear_queue()
    await interaction.response.send_message("⏹️ Stopped and queue cleared.")


@dj.command(name="help", description="Show how to use the bot")
async def cmd_help(interaction: discord.Interaction) -> None:
    embed = discord.Embed(title="🎵 DJ Bot — Command Reference", color=0x1db954)

    embed.add_field(name="▶️ Play", value=(
        "`/dj play song` — play or queue a single song\n"
        "`/dj play playlist` — shuffle a whole playlist into the queue"
    ), inline=False)

    embed.add_field(name="📋 Queue", value=(
        "`/dj queue add` — add a song to the queue\n"
        "`/dj queue list` — show currently playing and what's up next\n"
        "`/dj queue clear` — remove all songs from the queue"
    ), inline=False)

    embed.add_field(name="⏯️ Controls", value=(
        "`/dj next` — skip to the next track\n"
        "`/dj pause` — pause playback\n"
        "`/dj resume` — resume playback\n"
        "`/dj stop` — stop playback and clear the queue"
    ), inline=False)

    embed.set_footer(text="💡 All song and playlist fields support autocomplete — just start typing.")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ===========================================================================
# Auto-disconnect when the voice channel becomes empty
# ===========================================================================
@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if not player.voice_client or not player.voice_client.is_connected():
        return

    # Handle the bot itself being disconnected externally (e.g. kicked from VC)
    if member.id == bot.user.id and after.channel is None:
        log.info("Bot was disconnected externally — resetting state")
        player.stop()
        player.queue.clear()
        player.current = None
        player.voice_client = None
        return

    # Disconnect if no human listeners remain in the bot's channel
    humans = [m for m in player.voice_client.channel.members if not m.bot]
    if not humans:
        log.info("Voice channel is empty — disconnecting")
        await player.leave()


# ===========================================================================
# Bot startup
# ===========================================================================
@bot.event
async def on_ready() -> None:
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    synced = await tree.sync(guild=GUILD)
    log.info("Slash commands synced: %d commands", len(synced))


# Register the command group before starting the bot
tree.add_command(dj, guild=GUILD)

if __name__ == "__main__":
    library.load()
    bot.run(TOKEN, log_handler=None)
