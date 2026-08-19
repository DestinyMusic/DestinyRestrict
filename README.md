---
title: Destiny Bypass Engine
emoji: ⚡
colorFrom: gray
colorTo: red
sdk: docker
pinned: false
app_port: 8080
---
# ⚡ Destiny Bypass Engine
**High-Speed Telegram Restricted Content Bypasser & Auto-Sync System**
---
## 🚀 Core Infrastructure
A lightweight, high-performance engine designed to extract and route data from Telegram environments where content saving is restricted.
* **🔐 Bypass Protocol:** Seamlessly fetch files from channels with "Restrict Saving Content" enabled.
* **🧠 Stateful Memory:** Powered by MongoDB. If the server crashes or restarts, the engine remembers the relevant message state and resumes automatically.
* **📦 Heavy Lifting:** Dynamically handles large files and automatically splits them when they exceed Telegram's upload limits.
* **👁️ Live Surveillance:** Deploy 24/7 background watchers to automatically route new uploads from configured source channels to target channels.
---
## ⚙️ Environment Configuration
To boot the engine on Hugging Face Spaces, Render, Koyeb, or a similar Docker-based platform, configure the following environment variables. 
*(Click the links in the table to get your credentials)*

| Variable | Description | Get it Here |
| :--- | :--- | :--- |
| `API_ID` | Your Telegram API ID. | [my.telegram.org](https://my.telegram.org/apps) |
| `API_HASH` | Your Telegram API Hash. | [my.telegram.org](https://my.telegram.org/apps) |
| `BOT_TOKEN` | Telegram bot token obtained from @BotFather. | [@BotFather](https://t.me/BotFather) |
| `DB_URI` | MongoDB Atlas connection string. | [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) |
| `DB_NAME` | Database name (e.g., `RestrictBot_DB`). | *(Create in MongoDB)* |
| `ADMINS` | Comma-separated Telegram User IDs with admin access. | [@userinfobot](https://t.me/userinfobot) |
| `LOG_CHANNEL` | Telegram chat/channel ID used for backend error logs. | *(Your private channel ID)* |

---
## 🕹️ Master Commands

| Command | Description |
| :--- | :--- |
| `/login` | Bind a Telegram string session to the engine. |
| `/dl <link>` | Process a single file or a large batch (e.g., `link/101-500`). |
| `/watch <link>` | Set up a live auto-forwarder for a source channel. |
| `/watchers` | View active surveillance tasks. |
| `/cancel` | Open the interface for cancelling active tasks. |
| `/sos` | Display live server hardware, CPU, memory, and system metrics. |

---
## 🏗️ Deployment
The engine uses a Docker-based deployment model and can be hosted on platforms supporting Docker containers. Make sure the configured application port matches the platform configuration (Default: `8080`).
**Supported Platforms:**
* 🤗 Hugging Face Spaces
* 🚀 Render
* ⚡ Koyeb
* 🐳 Any Docker-compatible server
---
## 🔒 Security
Keep the following values completely private. **Never commit these credentials directly to the repository.**
* `API_HASH`
* `BOT_TOKEN`
* `DB_URI`
* Telegram Session Strings
* Any administrator credentials or secrets
*Always use environment variables or the platform's secret/environment-variable manager instead.*
---
## 📊 System Architecture
```text
┌──────────────────────┐
│       Telegram       │
│   Source Channels    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    Destiny Bypass    │
│        Engine        │
└──────────┬───────────┘
           │
  ┌────────┼────────┐
  │        │        │
  ▼        ▼        ▼
┌────┐  ┌─────┐  ┌─────┐
│/dl │  │/watch│  │Queue│
└────┘  └─────┘  └─────┘
  │        │        │
  └────────┼────────┘
           │
           ▼
┌──────────────────────┐
│       MongoDB        │
│   Persistent State   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│    Target Channel    │
└──────────────────────┘
