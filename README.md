---
title: Destiny Bypass Engine
emoji: ⚡
colorFrom: gray
colorTo: red
sdk: docker
pinned: false
app_port: 8080
---
<div align="center">
  <h1>⚡ Destiny Bypass Engine</h1>
  <p><b>High-Speed Telegram Restricted Content Bypasser & Auto-Sync System</b></p>
  <p>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python"></a>
    <a href="https://www.mongodb.com/"><img src="https://img.shields.io/badge/Database-MongoDB-green?style=for-the-badge&logo=mongodb" alt="MongoDB"></a>
    <a href="https://docs.pyrogram.org/"><img src="https://img.shields.io/badge/Framework-Pyrogram-red?style=for-the-badge&logo=telegram" alt="Pyrogram"></a>
  </p>
</div>
---
## 🚀 Core Infrastructure
A lightweight, bulletproof engine designed to covertly extract and route data from highly restricted Telegram environments.
*   **Bypass Protocol:** Seamlessly fetches files from channels with "Restrict Saving Content" enabled.
*   **Stateful Memory:** Powered by MongoDB. If the server crashes, the bot remembers the exact message ID and resumes automatically.
*   **Heavy Lifting:** Dynamically handles massive files, automatically splitting standard >2GB limits (or >4GB with a Premium Session).
*   **Live Surveillance:** Deploy 24/7 background watchers to instantly auto-route new uploads to your target channels.
## ⚙️ Environment Configuration
To boot the engine on Hugging Face Spaces (or Render/Koyeb), plug in these environment variables:

| Variable | Description |
| :--- | :--- |
| `API_ID` | Your Telegram API ID. |
| `API_HASH` | Your Telegram API Hash. |
| `BOT_TOKEN` | Remote control token from @BotFather. |
| `DB_URI` | MongoDB Atlas connection string. |
| `DB_NAME` | Database name (e.g., `RestrictBot_DB`). |
| `ADMINS` | Comma-separated Telegram User IDs. |
| `LOG_CHANNEL` | Chat ID for automated backend error logs. |

## 🕹️ Master Commands
*   `/login` - Bind your Telegram string session to the engine.
*   `/dl <link>` - Extract a single file or a massive batch (e.g., `link/101-500`).
*   `/watch <link>` - Setup a live auto-forwarder from a source channel.
*   `/watchers` - View your active surveillance tasks.
*   `/cancel` - Open the UI to kill active tasks.
*   `/sos` - Live server hardware and RAM metrics.
---
<div align="center">
  <i>Engineered for pure speed and zero data loss.</i>
</div>
