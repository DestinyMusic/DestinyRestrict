---
title: Destiny Bypass Engine
emoji: ⚡
colorFrom: gray
colorTo: red
sdk: docker
pinned: false
app_port: 8080
---
# ⚡ Destiny Bypass Engine & Universal Media Theater
**Ultimate High-Speed Telegram Restricted Content Bypasser, Web Streamer & Auto-Sync System**
---
## 🚀 Core Infrastructure
A lightweight, hyper-optimized engine designed to extract, route, and stream data from Telegram environments where content saving is restricted.
* **🔐 Bypass Protocol:** Seamlessly fetch files from channels with "Restrict Saving Content" enabled via MTProto native byte-read targeting.
* **🧠 Stateful MongoDB Memory:** If the server crashes or restarts, the engine remembers the exact message ID state and resumes batch downloads automatically.
* **🤖 Multi-Bot Worker Pool:** Link auxiliary Bot Tokens to enable parallel chunk downloading. Bypasses single-connection speed limits to eliminate 1080p/4K buffering.
* **👁️ Live Surveillance:** Deploy 24/7 background Watchers to automatically catch and route new uploads from source channels (or Bot PMs) to target channels.
* **📦 Split & ZIP Handling:** Dynamically handles large files, automatic splitting, and native streaming from uncompressed (STORED) `.zip` archives.
---
## 🍿 Universal Web Dashboard & Media Theater
The engine features a built-in **Full-Stack Progressive Web App (PWA)** accessible via your server URL. 
* **Direct Browser Streaming:** Stream raw Telegram MKV/MP4 files directly to your browser without downloading them first.
* **On-the-Fly Transcoding:** Automatically detects unsupported browser formats (like `HEVC/x265` or `5.1 Surround Sound`) and transcodes them to `H.264/Stereo` in real-time using FFmpeg, while keeping original resolutions.
* **External Player Integration:** Instantly route Telegram streams to **VLC, MX Player, MPV, Infuse, or Outplayer** with full metadata, dual-audio, and subtitle support.
* **Advanced Subtitle Engine:** Load external `.vtt` subtitles via URL or local file, with full customization (size, color, weight, sync delays, and SDH top-screen routing).
* **3D Anaglyph WebGL:** Built-in shader pipeline to convert SBS/OU 3D videos into Red/Cyan anaglyph formats on the fly.
* **Fluid Glassmorphism UI:** Fully responsive Apple Music/Netflix-style UI with multiple AMOLED, Obsidian, and Cinematic themes.
---
## 📉 Forensic Audio DSP & Media Analysis
Built-in tools for audiophiles and server admins to inspect media quality.
* **Audio Spectrograms (`/spec`):** Downloads an audio snippet and generates a precise high-frequency spectrogram using SoX and SciPy to detect fake lossless upscales, brick-wall cutoffs, and spectral holes.
* **Mastering Diagnostics:** Calculates LUFS, Dynamic Range (DR), Peak dBFS, RMS, and clipping events natively.
* **MediaInfo Inspector (`/mi`):** Extracts complete internal multiplex headers (Codecs, Bitrates, Audio Channels) directly from Telegram and pushes a beautiful HTML report to Telegraph.
---
## ⚙️ Environment Configuration
To boot the engine on Hugging Face Spaces, Render, Koyeb, or a similar Docker-based platform, configure the following environment variables.

| Variable | Description | Get it Here |
| :--- | :--- | :--- |
| `API_ID` | Your Telegram API ID. | [my.telegram.org](https://my.telegram.org/apps) |
| `API_HASH` | Your Telegram API Hash. | [my.telegram.org](https://my.telegram.org/apps) |
| `BOT_TOKEN` | Telegram bot token obtained from @BotFather. | [@BotFather](https://t.me/BotFather) |
| `DB_URI` | MongoDB Atlas connection string. | [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) |
| `DB_NAME` | Database name (e.g., `RestrictBot_DB`). | *(Create in MongoDB)* |
| `ADMINS` | Comma-separated Telegram User IDs with admin access. | [@userinfobot](https://t.me/userinfobot) |
| `SUDOS` | Comma-separated secondary Admin IDs. | [@userinfobot](https://t.me/userinfobot) |
| `LOG_CHANNEL` | Telegram chat/channel ID used for backend error logs. | *(Your private channel ID)* |
| `PORT` | Port for the Web Dashboard (Default: `8080`). | *(Platform Specific)* |

*Note: Auxiliary Worker Bot Tokens are added dynamically via the Web Dashboard settings tab, not environment variables.*
---
## 🕹️ Master Commands
### 🟢 User Commands

| Command | Description |
| :--- | :--- |
| `/start` | Check if bot is alive and get Web Dashboard Link. |
| `/login` | Securely bind your Telegram Session (handles 2FA & OTP). |
| `/logout` | Safely disconnect your Telegram Session and clear active tasks. |
| `/dl <link>` | Smart Downloader. Process a single file or batch (e.g., `link/101-500`). |
| `/watch <link>` | Setup a live auto-forwarder for a specific channel or PM. |
| `/unwatch <id>` | Stop a specific watcher task. |
| `/watchers` | Open interactive menu managing all active surveillance watchers. |
| `/cancel` | Stop a specific active batch download safely. |
| `/chats` | Dialog Explorer: Extract Chat, Group, Bot, and Channel IDs. |

### 🔴 Admin & System Commands

| Command | Description |
| :--- | :--- |
| `/status` | Live dashboard of RAM, CPU, disk space, and active streams. |
| `/sos` | Deep diagnostics (Kernel, Bandwidth usage, Uptime). |
| `/botstats` | Detailed task tracking (who is downloading what). |
| `/broadcast` | Reply to a message to send it to all database users. |
| `/log` | Pulls the backend `bot.log` file. |
| `/pixel` | Bypasses Pixeldrain limits, generates direct CDN links. |
| `/speedtest` | Runs a secure server bandwidth test with image generation. |
| `/mi <link>` | MediaInfo Technical Inspector (Outputs to Telegraph). |
| `/spec <link>` | Audio DSP, LUFS, DR, and Spectrogram image generation. |

---
## 🏗️ Deployment
The engine uses a robust Docker-based deployment model mapping `aiohttp`, `uvloop`, `ffmpeg`, and `sox`. Make sure the configured application port matches the platform configuration (Default: `8080`).
**Supported Platforms:**
* 🤗 Hugging Face Spaces
* 🚀 Render
* ⚡ Koyeb
* 🐳 Any Docker-compatible VPS/Dedicated Server
---
## 🔒 Security
Keep the following values completely private. **Never commit these credentials directly to the repository.**
* `API_HASH`
* `BOT_TOKEN`
* `DB_URI`
* Telegram Session Strings
*Any administrator credentials or secrets should only be set via the deployment platform's Environment Variable Secrets manager.*
---
## 📊 System Architecture
```text
┌────────────────────────────────────────────────────────┐
│                   TELEGRAM SERVERS                     │
│         (Source Channels, DMs, Private Groups)         │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│              ⚡ DESTINY BYPASS ENGINE ⚡               │
│                                                        │
│  ┌────────────────┐ ┌────────────────┐ ┌─────────────┐ │
│  │ Primary Client │ │  Worker Bots   │ │ Auto-Resume │ │
│  │ (User Session) │ │ (Parallel DL)  │ │   Engine    │ │
│  └───────┬────────┘ └───────┬────────┘ └──────┬──────┘ │
└──────────┼──────────────────┼─────────────────┼────────┘
           │                  │                 │
           ▼                  ▼                 ▼
┌────────────────────────────────────────────────────────┐
│                    AIOHTTP WEB SERVER                  │
│                      (Port 8080)                       │
│                                                        │
│  ┌────────────────┐ ┌────────────────┐ ┌─────────────┐ │
│  │ Web Dashboard  │ │ FFmpeg Wrapper │ │ Media Probe │ │
│  │  (Liquid UI)   │ │  (Transcoder)  │ │  (ffprobe)  │ │
│  └───────┬────────┘ └───────┬────────┘ └─────────────┘ │
└──────────┼──────────────────┼──────────────────────────┘
           │                  │
           ▼                  ▼
┌──────────────────┐ ┌───────────────────────────────────┐
│     MONGODB      │ │           CLIENT ENDPOINT         │
│ (State, Configs, │ │ (Web Browser, VLC, Target Channel)│
│    Watchers)     │ │                                   │
└──────────────────┘ └───────────────────────────────────┘
