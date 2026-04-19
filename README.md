# 🎵 Local Discord Music Bot

A lightweight Discord music bot built to run permanently on a **Raspberry Pi Zero 2 W** (512MB RAM). No database, no web dashboard, no unnecessary dependencies — just FFmpeg, discord.py, and your music files.

---

## Features

- Slash commands with **autocomplete** for song and playlist names
- Plays local audio files via FFmpeg (MP3, MP4, OGG, FLAC, WAV)
- Playlist support — just drop files into a folder
- Auto-disconnects when the voice channel empties
- Queue up to 50 tracks (artifically limited)
- Skips broken files automatically without crashing
- Runs as a systemd service — survives reboots and crashes

---

## File Structure

```
discord-music-bot/
├── main.py            # Bot startup and all slash commands
├── music_player.py    # Queue and playback logic
├── library.py         # In-memory music index
├── requirements.txt   # Python dependencies
├── .env.example       # Template for your secrets
└── music/
    ├── songs/         # Individual tracks
    │   ├── my song.mp3
    │   └── another track.mp3
    └── playlists/
        ├── gym/       # Each folder is a playlist
        │   ├── track1.mp3
        │   └── track2.mp3
        └── chill/
            └── track3.mp3
```

> The folder structure **is** the library. No metadata file needed.  
> To add music: drop files in the right folder and restart the bot.  
> A song can appear in multiple playlists — just copy or symlink it.

---

## Commands

| Command | Description |
|---|---|
| `/dj play song` | Play or queue a single song |
| `/dj play playlist` | Shuffle an entire playlist into the queue |
| `/dj queue add` | Add a song to the queue |
| `/dj queue list` | Show what is playing and what is up next |
| `/dj queue clear` | Remove all songs from the queue |
| `/dj next` | Skip the current track |
| `/dj pause` | Pause playback |
| `/dj resume` | Resume playback |
| `/dj stop` | Stop playback and clear the queue |
| `/dj help` | Show command reference in Discord |

All `song` and `playlist` fields support **autocomplete** — just start typing.

---

## Full Setup Guide — From Empty SD Card to Working Bot

This guide covers everything from flashing Raspberry Pi OS to having the bot running as a permanent background service.

---

### Part 1 — Set Up the Raspberry Pi

#### 1.1 Flash Raspberry Pi OS

1. Download **Raspberry Pi Imager** from https://www.raspberrypi.com/software/
2. Insert your SD card
3. Open Imager → **Choose Device** → Raspberry Pi Zero 2 W
4. **Choose OS** → Raspberry Pi OS Lite (64-bit) ← no desktop needed
5. **Choose Storage** → your SD card
6. Click the **gear icon (⚙️)** before writing to pre-configure:
   - Set a **hostname** (e.g. `discordbot`)
   - Enable **SSH**
   - Set a **username and password**
   - Configure your **Wi-Fi** (SSID + password)
7. Click **Write** and wait for it to finish

#### 1.2 Boot and Connect

Insert the SD card into the Pi and power it on. Wait about 60 seconds for first boot, then SSH in from your computer:

```bash
ssh youruser@discordbot.local
```

If `.local` doesn't resolve, find the IP address from your router's device list and use that instead:

```bash
ssh youruser@192.168.1.xxx
```

---

### Part 2 — Discord Developer Portal

#### 2.1 Create the Application

1. Go to https://discord.com/developers/applications
2. Click **New Application** → give it a name → **Create**

#### 2.2 Create the Bot

1. Left sidebar → **Bot**
2. Click **Add Bot** → confirm
3. Scroll down to **Privileged Gateway Intents** and enable **Voice States**
4. Click **Save Changes**
5. Click **Reset Token** → copy and save your token somewhere safe

> ⚠️ Your token is like a password. Never share it or commit it to git.

#### 2.3 Invite the Bot to Your Server

1. Left sidebar → **OAuth2** → **URL Generator**
2. Under **Scopes**, check:
   - `bot`
   - `applications.commands`
3. Under **Bot Permissions**, check:
   - `Connect`
   - `Speak`
4. Copy the generated URL at the bottom and open it in your browser
5. Select your server and click **Authorise**

#### 2.4 Get Your Server ID

1. Open Discord → **Settings** → **Advanced** → enable **Developer Mode**
2. Right-click your server name in the sidebar → **Copy Server ID**

---

### Part 3 — Install the Bot on the Pi

SSH into your Pi and run the following commands.

#### 3.1 Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv ffmpeg libopus-dev libffi-dev git
```

Verify FFmpeg installed correctly:

```bash
ffmpeg -version
```

#### 3.2 Clone the Repository

```bash
git clone https://github.com/LeonCwiklinski/discord-music-bot.git
cd discord-music-bot
```

Or if you're copying files manually via WinSCP/SCP, create the folder and copy everything in:

```bash
mkdir ~/discord-music-bot
```

#### 3.3 Create the Virtual Environment

```bash
cd ~/discord-music-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3.4 Configure Your Secrets

```bash
cp .env.example .env
nano .env
```

Fill in your values:

```
DISCORD_TOKEN=your-bot-token-here
DISCORD_GUILD_ID=your-server-id-here
```

Save with `Ctrl+O` → Enter → `Ctrl+X`

#### 3.5 Add Your Music

Create the music directories if they don't exist:

```bash
mkdir -p music/songs
mkdir -p music/playlists/myfirstplaylist
```

Copy your audio files in via WinSCP, SCP, or a USB drive. For example with SCP from your Windows machine:

```bash
scp "C:\Users\you\Music\mysong.mp3" youruser@discordbot.local:~/discord-music-bot/music/songs/
```

#### 3.6 Test Run

Before setting up the service, make sure everything works:

```bash
source venv/bin/activate
export $(cat .env | xargs)
python3 main.py
```

You should see:

```
12:00:00 [INFO] library: Library loaded: X songs, X playlists
12:00:01 [INFO] __main__: Logged in as YourBot#1234 (id=...)
12:00:01 [INFO] __main__: Slash commands synced: 1 commands
```

Try `/dj help` in Discord. If it works, stop the bot with `Ctrl+C` and continue.

---

### Part 4 — Run as a Permanent Service

This makes the bot start automatically on boot and restart if it crashes.

#### 4.1 Create the Service File

```bash
sudo nano /etc/systemd/system/musicbot.service
```

Paste the following, replacing the placeholders with your actual values:

```ini
[Unit]
Description=Discord Music Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/discord-music-bot
Environment=DISCORD_TOKEN=your-bot-token-here
Environment=DISCORD_GUILD_ID=your-server-id-here
ExecStart=/home/youruser/discord-music-bot/venv/bin/python3 main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

> Replace `youruser` with your actual Pi username (e.g. `discordbot` or `pi`).

Save with `Ctrl+O` → Enter → `Ctrl+X`

#### 4.2 Enable and Start

```bash
sudo systemctl daemon-reload
sudo systemctl enable musicbot
sudo systemctl start musicbot
```

#### 4.3 Check It Is Running

```bash
sudo systemctl status musicbot
```

You should see `Active: active (running)`.

#### 4.4 View Live Logs

```bash
journalctl -u musicbot -f
```

Press `Ctrl+C` to stop following logs.

---

### Part 5 — Managing the Bot

| Task | Command |
|---|---|
| Start the bot | `sudo systemctl start musicbot` |
| Stop the bot | `sudo systemctl stop musicbot` |
| Restart the bot | `sudo systemctl restart musicbot` |
| View status | `sudo systemctl status musicbot` |
| View live logs | `journalctl -u musicbot -f` |
| Add new music | Copy files into `music/songs/` or `music/playlists/name/`, then restart |

---

## Troubleshooting

**`/dj` doesn't appear in Discord**  
→ Make sure the bot is running and you see "Slash commands synced" in the logs.  
→ Try closing and reopening Discord — it can take a moment to show new commands.  
→ Verify your `DISCORD_GUILD_ID` matches the server you're in.

**Bot joins but plays nothing / skips all tracks**  
→ Test a file directly: `ffmpeg -i "music/songs/mysong.mp3" -f null -`  
→ If FFmpeg reports an error, the file is corrupted or in an unsupported format. Re-download it.

**`ffmpeg was not found` error**  
→ Run `ffmpeg -version` to confirm it's installed. If not: `sudo apt install ffmpeg`

**`PyNaCl` or `davey` warning**  
→ Run `pip install discord.py[voice]` inside your venv to install all voice dependencies.

**Service fails to start (status=203/EXEC)**  
→ Check the `ExecStart` path in your service file. Run `which python3` inside your activated venv to confirm the correct path.

**Service fails to start (status=200/CHDIR)**  
→ The `WorkingDirectory` path is wrong. Double-check it with `pwd` while inside your bot folder.

---

## Resource Usage (Raspberry Pi Zero 2 W)

| Component | Approximate RAM |
|---|---|
| Python + discord.py | ~35 MB |
| FFmpeg (one process per track) | ~10 MB |
| Music index (1000 songs) | ~1 MB |
| **Total** | **~50 MB** |

Well within the 512 MB available, leaving plenty of headroom for the OS and any other services.
