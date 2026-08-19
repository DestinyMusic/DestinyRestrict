---
title: Sync & Bypass Engine
emoji: 🌟
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
app_port: 8080
---
<div align="center">
  
# 🌟 𝕿𝖍𝖊 𝖀𝖑𝖙𝖎𝖒𝖆𝖙𝖊 𝕿𝖊𝖑𝖊𝖌𝖗𝖆𝖒 𝕾𝖞𝖓𝖈 & 𝕭𝖞𝖕𝖆𝖘𝖘 𝕰𝖓𝖌𝖎𝖓𝖊 🌟
### 𝓨𝓸𝓾𝓻 𝓟𝓮𝓻𝓼𝓸𝓷𝓪𝓵, 𝓣𝓲𝓻𝓮𝓵𝓮𝓼𝓼 𝓓𝓪𝓽𝓪-𝓜𝓸𝓿𝓲𝓷𝓰 𝓢𝓾𝓹𝓮𝓻𝓱𝓮𝓻𝓸! 🦸‍♂️
<br>
[![Python Version](https://img.shields.io/badge/🐍_Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![MongoDB](https://img.shields.io/badge/🍃_Database-MongoDB_Atlas-green?style=for-the-badge&logo=mongodb)](https://www.mongodb.com/)
[![Pyrogram](https://img.shields.io/badge/✈️_Framework-Pyrogram_V2-red?style=for-the-badge&logo=telegram)](https://docs.pyrogram.org/)
[![License](https://img.shields.io/badge/📜_Licence-MIT-purple?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![Server](https://img.shields.io/badge/☁️_Server-Render_%7C_Koyeb-orange?style=for-the-badge)](https://render.com/)
[![Uptime](https://img.shields.io/badge/⚡_Uptime-99.9%25-brightgreen?style=for-the-badge)](https://uptimerobot.com/)
<br>
> *"Imagine possessing a robotic assistant that never sleeps, never complains, and can seamlessly shift colossal datasets for you with absolute zero errors. That is precisely what you are looking at right now."*
</div>
---
<br>
## 📖 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 1: 𝓦𝓱𝓪𝓽 𝓘𝓼 𝓣𝓱𝓲𝓼 𝓜𝓪𝓰𝓲𝓬? (Explained Simply) 🍼
Let us paint a picture. Imagine you have a massive treasure chest (a Telegram Channel) filled with countless gold coins (movies, documents, and files). You want to move absolutely all of these into your very own, brand-new VIP vault. 
However, you immediately face three massive headaches:
1. **The Vault is Locked (Restricted Content) 🔒:** The old channel has disabled forwarding. You cannot simply select and share the files. They are entirely trapped.
2. **The Coins are Filthy (Spam Filenames) 🗑️:** Every single file has a hideous name attached to it, filled with spam links, adverts, and rubbish text (e.g., `[Join @SpamHub] The_Matrix_1080p.mkv`).
3. **The Threat of Blackouts (Server Crashes) 😴:** If you start copying these manually or using a basic script, and your server crashes or loses power, you have to start all over again from file number one. It is an absolute nightmare!
**🔥 𝔈𝔫𝔱𝔢𝔯 𝔗𝔥𝔢 𝔖𝔶𝔫𝔠 𝔅𝔬𝔱! (Our Magical Solution) 🔥**
This bot is your bespoke digital superhero. It covertly infiltrates that restricted treasure chest, downloads each file directly from Telegram's servers, gives it a "smart wash" (scrubbing away all the spam and renaming it beautifully), and safely deposits it into your new channel. 
The most brilliant part? It has a photographic memory powered by **MongoDB**. If the server crashes halfway through, the bot doesn't panic. When it wakes up, it remembers *exactly* where it left off and resumes instantaneously. **No missing files. No duplicates. Total peace of mind.**
<br>
---
<br>
## ✨ 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 2: 𝓣𝓱𝓮 𝓢𝓾𝓹𝓮𝓻𝓹𝓸𝔀𝓮𝓻𝓼 (Deep Dive Into Features) 🦸‍♂️
This is not merely a script; it is a fully-fledged data ecosystem. Let us break down its core capabilities so you understand exactly what is happening under the bonnet.
### ❶ 🛡️ 𝕿𝖍𝖊 𝕭𝖞𝖕𝖆𝖘𝖘𝖊𝖗 𝕾𝖍𝖎𝖊𝖑𝖉 (Restricted Content Unlocker)
Telegram's privacy restrictions are notoriously strict. If an admin disables forwarding, standard users cannot even screen-record the content. 
*   **How it works:** This bot acts on behalf of your account (using a Userbot session). It streams the locked files directly from Telegram's binary data servers, bypassing the front-end restrictions entirely. Telegram remains completely unaware that the file has been cloned! 🕵️‍♂️
### ❷ 🧠 𝕿𝖍𝖊 𝕸𝖔𝖓𝖌𝖔𝕯𝕭 𝕭𝖗𝖆𝖎𝖓 (Stateful Auto-Resume)
Imagine transferring an immense dataset, only for your server to randomly restart right near the end. Older bots would force you to start from zero. 
*   **How it works:** After every single successful transfer, this bot logs a tiny note in its cloud brain (MongoDB): *"I have successfully processed this specific message ID."* 
*   When it boots back up, it asks the database, *"Where were we, mate?"* and resumes seamlessly from the very next ID. **100% Reliability.** 🧘‍♂️
### ❸ 🤖 𝕸𝖚𝖑𝖙𝖎-𝕮𝖑𝖔𝖓𝖊 𝕬𝖗𝖒𝖞 (Parallel Scaling Architecture)
If you attempt to move a monumental amount of files using just one account, Telegram will throw a fit and temporarily ban you (known as a `FloodWait` error).
*   **How it works:** You can deploy multiple clones of this bot across different servers. You assign Bot A to handle the first half of a channel, and Bot B to handle the second half. Because they are all connected to the same database, they work together in perfect harmony. It is scaling made simple! ⚡
### ❹ 🧼 𝕿𝖍𝖊 𝕿𝖆𝖌 𝕮𝖑𝖊𝖆𝖓𝖊𝖗 (Extreme Smart Renamer)
We have all seen horrendous filenames like: `@RubbishChannel_The_Dark_Knight_2008_Hindi_1080p_Join_Now.mkv` 🤢
*   **How it works:** Hidden within this bot is a highly advanced processing engine. It automatically scans the filthy filename and extracts the raw media components, stripping out unwanted advertisements and forwarding tags.
### ❺ 👀 𝕿𝖍𝖊 𝕷𝖎𝖛𝖊 𝖂𝖆𝖙𝖈𝖍𝖊𝖗 (Instant Auto-Routing)
*   **How it works:** You can command the bot to keep a permanent, 24/7 watch on any source channel. The very second a new file is uploaded there, your bot will detect it, clean the metadata, and instantly route it to your target channels. 
<br>
---
<br>
## 🔗 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 3: 𝓣𝓱𝓮 𝓓𝓮𝓿𝓮𝓵𝓸𝓹𝓮𝓻'𝓼 𝓣𝓸𝓸𝓵𝓴𝓲𝓽 (Useful Links & References) 🧰
To ensure you possess absolutely everything required to run this masterpiece efficiently, here is a curated list of all essential platforms, documentation, and tools. Bookmark these; they are your absolute best friends!
*   🐙 **GitHub (Version Control):** [github.com](https://github.com/) - *Host your glorious code here before deploying it to the cloud.*
*   ✈️ **Telegram API (Core Engine):** [my.telegram.org](https://my.telegram.org/) - *The portal to generate your vital API_ID and API_HASH.*
*   🤖 **BotFather (Bot Creation):** [@BotFather](https://t.me/BotFather) - *The official Telegram bot required to forge your BOT_TOKEN.*
*   🍃 **MongoDB (The Cloud Brain):** [mongodb.com](https://www.mongodb.com/) - *Set up your free M0 Cluster database here to power the bot's memory.*
*   ☁️ **Render (Hosting Platform):** [render.com](https://render.com/) - *Deploy your bot here for incredibly smooth, continuous operation.*
*   ☁️ **Koyeb (Alternative Hosting):** [koyeb.com](https://www.koyeb.com/) - *A brilliant, high-performance alternative hosting solution to Render.*
*   ⏱️ **UptimeRobot (Keep-Alive Monitor):** [uptimerobot.com](https://uptimerobot.com/) - *The bot has a built-in health-check server. Use UptimeRobot to ping it every 5 minutes and ensure it never falls asleep!*
*   📚 **Pyrogram Framework (Documentation):** [docs.pyrogram.org](https://docs.pyrogram.org/) - *The magnificent Python framework operating under the bonnet of this entire project.*
<br>
---
<br>
## 🎒 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 4: 𝓖𝓪𝓽𝓱𝓮𝓻𝓲𝓷𝓰 𝓣𝓱𝓮 𝓘𝓷𝓯𝓲𝓷𝓲𝓽𝔂 𝓢𝓽𝓸𝓷𝓮𝓼 (Prerequisites) 💎
Before we can awaken the bot, you need to collect three essential digital keys. Do not worry; this is incredibly straightforward. Just follow these steps:
### 🔴 Stone 1: API_ID & API_HASH (Your Telegram VIP Pass)
1. Open a web browser on your phone or PC and head over to: [👉 my.telegram.org](https://my.telegram.org/)
2. Log in using your mobile number (ensure you include the country code, e.g., `+447123456789`).
3. Telegram will send a login code to your app. Pop that code into the browser.
4. Click on the section titled **"API development tools"**.
5. You will see a form. Fill in the "App Title" and "Short Name" with anything you fancy (e.g., `MySyncBot`).
6. Click submit. You will instantly be rewarded with your `API_ID` (a short string of numbers) and your `API_HASH` (a long mix of letters and numbers). Keep these safe and secret! 🤫
### 🟢 Stone 2: BOT_TOKEN (The Remote Control)
1. Open your Telegram app and search for the official [👉 @BotFather](https://t.me/BotFather).
2. Start a chat with him and type the command: `/newbot`
3. He will ask you for a name. Call it something cool like: `Super Sync Engine`
4. Next, he wants a username (it MUST end in 'bot'). Try something like: `MySync_bot`
5. If successful, BotFather will hand you a long, secure token (e.g., `1234567:AAxyz...`). This is your **BOT_TOKEN**! 🔑
### 🍃 Stone 3: MongoDB URI (The Bot's Cloud Brain)
1. Head over to [👉 mongodb.com](https://www.mongodb.com/cloud/atlas/register) in your browser.
2. Sign up for a free account (using Google is the fastest way).
3. Create a new "Cluster" (ensure you select the `M0 Free` tier so you don't pay a penny).
4. It will prompt you to create a "Database User". Make a simple username and a password. **Write this password down!**
5. For "Network Access", select the option that says **"Allow Access from Anywhere"** (which looks like `0.0.0.0/0`). This ensures your bot can connect from any server in the world.
6. Finally, click **"Connect"** ➔ **"Drivers"** ➔ and copy the long connection string provided.
7. *Crucial step:* In that string, replace the word `<password>` with the actual password you just created. This entire link is your **DB_URI**! 🧠
<br>
---
<br>
## ⚙️ 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 5: 𝓣𝓱𝓮 𝓜𝓪𝓼𝓽𝓮𝓻 𝓒𝓸𝓷𝓽𝓻𝓸𝓵 𝓟𝓪𝓷𝓮𝓵 (Environment Variables) 🎛️
When you deploy this bot on a cloud service like Render, Koyeb, Heroku, or a VPS, you will be asked to fill in "Environment Variables". Think of this as the bot's settings menu. You must fill these out accurately!

| 𝕍𝕒𝕣𝕚𝕒𝕓𝕝𝕖 ℕ𝕒𝕞𝕖 | 𝕎𝕙𝕒𝕥 𝔼𝕩𝕒𝖼𝕥𝕝𝕪 𝕀𝕤 𝕀𝕥? (Description) | 𝔼𝕩𝕒𝕞𝕡𝕝𝕖 (What it looks like) |
| :--- | :--- | :--- |
| `API_ID` | Your VIP pass from Stone 1. | `2345678` |
| `API_HASH` | The long secret code from Stone 1. | `abcdef1234567890abcdef1234567890` |
| `BOT_TOKEN` | The remote control key from BotFather (Stone 2). | `1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ` |
| `DB_URI` | The brain connection link from MongoDB (Stone 3). | `mongodb+srv://admin:MyPass123@cluster0.abc.mongodb.net/?retryWrites=true` |
| `DB_NAME` | A unique name for this specific bot's memory sector. <br>**PRO TIP:** If running multiple bots, this MUST be different for each one! | `WorkerBot_1` |
| `ADMINS` | A list of user IDs who are authorised to control the bot. Separate multiple admins with a comma. | `123456789, 987654321` |
| `LOG_CHANNEL` | Create a private Telegram channel and add the bot as an admin. Put the channel ID here. The bot will send all its final invoices and crash reports here! | `-1001234567890` |

<br>
---
<br>
## 🪄 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 6: 𝓣𝓱𝓮 𝓜𝓪𝓰𝓲𝓬 𝓢𝓹𝓮𝓵𝓵𝓼 (Bot Commands In Detail) 📜
To command this robotic marvel, you must utilise specific instructions. Each command triggers a unique function within the ecosystem. 
### 👑 𝕿𝖍𝖊 𝕸𝖆𝖘𝖙𝖊𝖗 𝕶𝖊𝖞𝖘 (Admin Setup Commands)
These commands are strictly reserved for authorised administrators. If an unauthorised user attempts to use them, the bot will silently ignore them.
*   🔑 **`/login` (Present Your Credentials)**
    *   **Purpose:** To extract files from highly restricted private channels, you must log your Telegram account into the bot. This command will politely request your phone number and OTP to generate a secure Userbot session.
    *   **How To Use It:**
        1. Type `/login` and hit send.
        2. The bot will request your phone number. Include your country code (e.g., `+447987654321`).
        3. Telegram will send a 5-digit OTP to your app.
        4. **⚠️ CRUCIAL INSTRUCTION:** You MUST send the OTP with spaces. If the code is `12345`, you must type it as `1 2 3 4 5`. (If you send it without spaces, Telegram's security systems will block the attempt).
        5. If your account possesses a Two-Step Verification Password, the bot will request it. Enter it, and you are successfully authenticated! 🎉
*   🚪 **`/logout` (Terminate Session)**
    *   **Purpose:** If you wish to revoke the bot's access to your account, or if you simply wish to switch accounts, execute this command. It safely and permanently wipes your login credentials from the database. 🛡️
*   📊 **`/status` (Hardware Health Check)**
    *   **Purpose:** Curious about how the server is holding up? This command provides a real-time dashboard displaying:
        *   *RAM Usage:* Is the memory overflowing?
        *   *CPU Load:* Is the processor overheating?
        *   *Uptime:* How long has the bot been running continuously?
        *   *Active Tasks:* A live list of every ongoing download and upload.
*   📈 **`/botstats` (User Analytics)**
    *   **Purpose:** If you have permitted colleagues or friends to utilise the bot, this command will generate a comprehensive report of who is currently logged in and precisely what tasks they are executing. 👀
<br>
### 📥 𝕿𝖍𝖊 𝕿𝖗𝖆𝖓𝖘𝖕𝖔𝖗𝖙𝖊𝖗𝖘 (Processing Commands)
These are your primary tools for shifting vast quantities of data.
*   🚀 **`/dl` (Direct Download/Forward)**
    *   **Purpose:** Your absolute best friend. You can use this in two highly effective ways:
        *   **Single File:** Copy the link of any restricted file and send it to the bot (or reply to a link with `/dl`). The bot will instantly fetch it, clean it, and present it to you.
        *   **Batch Processing (The True Magic ✨):** If you require a massive sequential scrape! Simply send a link formatted with a numerical range:
            👉 `https://t.me/c/12345678/101 - 500`
        *   The bot will ask where you want the files deposited. Once selected, it will systematically harvest all 400 files, scrub their metadata, and deliver them. Put the kettle on and relax! ☕
*   🛑 **`/cancel` (Emergency Stop)**
    *   **Purpose:** Did you accidentally input the wrong channel link or specify an incorrect range? Do not panic. Simply type `/cancel`. A beautifully structured menu will appear, displaying all active tasks. Tap the one you wish to terminate, and the bot will safely halt the process. 🛑
<br>
### 🦉 𝕿𝖍𝖊 𝕾𝖎𝖑𝖊𝖓𝖙 𝕲𝖚𝖆𝖗𝖉𝖎𝖆𝖓𝖘 (Live Watcher Engine)
These commands allow for total automation. Set them up once, and the bot will work tirelessly in the background.
*   👀 **`/watch [Link]` (Install a Digital CCTV Camera)**
    *   **Purpose:** Provide the bot with a source channel link. The bot will embed itself as a silent listener. The absolute second an administrator uploads a new file, the bot will intercept it, clean it, and instantly route it to your specified destination!
    *   *During setup, you will configure:*
        1. The Target Destination.
        2. The Forwarding Delay (3 seconds is highly recommended to prevent bans).
        3. Content Filters (e.g., Ignore images and text, only forward Videos and Documents).
*   📋 **`/watchers` or `/list` (View Active Surveillance)**
    *   **Purpose:** Have you forgotten which channels you are currently monitoring? This command generates a pristine list of all active watchers and their corresponding routing configurations. 📷
*   🗑️ **`/unwatch [Source_ID]` (Dismantle Camera)**
    *   **Purpose:** If you wish to cease monitoring a specific channel, locate its ID via the `/watchers` command and execute `/unwatch -100XXXXX`. Surveillance terminated.
*   🎯 **`/removetarget` (Sever a Routing Path)**
    *   **Purpose:** If a single source channel was routing files to three separate destinations, and you wish to sever one of those connections, use `/removetarget [Source_ID] [Dest_ID]`. 
<br>
---
<br>
## 🏗️ 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 7: 𝓣𝓱𝓮 𝓒𝓵𝓸𝓷𝓮 𝓐𝓻𝓶𝔂 (Deployment Strategy) 🤖🤖🤖
Telegram enforces strict rate limits. A solitary account simply cannot transfer immense datasets in a single day. 
**The Solution?** We construct an Army of Bots! ⚔️
**𝔖𝔱𝔢𝔭-𝔟𝔶-𝔖𝔱𝔢𝔭 𝔐𝔲𝔩𝔱𝔦-𝔅𝔬𝔱 𝔊𝔲𝔦𝔡𝔢:**
1.  **Multiple Accounts:** Acquire access to 3-5 separate Telegram accounts. (Distributing the workload prevents any single account from facing a ban).
2.  **Multiple Bots:** Visit @BotFather and create distinct bots (Bot1, Bot2, Bot3). Keep their unique tokens handy.
3.  **Deploy Instances:** Wherever you are hosting (Render, VPS, Koyeb), create separate application instances for each bot.
4.  **The Secret Sauce (DB_NAME):** When filling out your Environment Variables, pay absolute attention to this:
    *   Use the **EXACT SAME** `DB_URI` for all of them (so they share a unified brain).
    *   However, give each app a **COMPLETELY DIFFERENT** `DB_NAME`. (e.g., `Cluster_Alpha`, `Cluster_Beta`). If they share a `DB_NAME`, they will overwrite each other's progress! 💥
5.  **Attack!** Instruct Bot 1 (using Account 1) to process files *1 to 50,000*. Instruct Bot 2 (using Account 2) to process *50,001 to 100,000*.
    *The Result:* Your cloning speed multiplies exponentially, completing weeks of processing in mere days! 🚀🚀
<br>
---
<br>
## 🚑 𝓒𝓱𝓪𝓹𝓽𝓮𝓻 8: 𝓣𝓱𝓮 𝓔𝓶𝓮𝓻𝓰𝓮𝓷𝓬𝔂 𝓚𝓲𝓽 (Troubleshooting & FAQs) 🛠️
Even the most advanced systems occasionally face hiccups. If something appears to go awry, consult this manual before panicking:
*   **❓ Question:** The bot has suddenly stopped transferring files and the progress bar is frozen. Is it broken?
    *   **💡 Answer:** Absolutely not. This is known as a **"FloodWait"**. When you request thousands of files consecutively, Telegram's servers politely demand that you slow down. The bot is highly intelligent; it will automatically put itself to sleep for the exact duration requested by Telegram, and seamlessly resume the moment the restriction lifts. Grab a biscuit and let it rest! 🍪
*   **❓ Question:** The Log Channel is repeatedly stating `⏭ DUPLICATE SKIPPED!`. What does this mean?
    *   **💡 Answer:** This is a feature, not a bug! If you restart the bot or accidentally submit a duplicate range, the MongoDB brain informs the bot: *"We have already successfully transferred this file."* The bot skips it to save bandwidth and time. Brilliant, isn't it? 👏
*   **❓ Question:** I am seeing a `🧹 CLEANUP ALERT: Deleted stuck files` message in the logs. Should I be worried?
    *   **💡 Answer:** Not at all. During the download process, files are temporarily cached on your server. If a massive file gets stuck or your server is running low on storage space, the built-in watchdog automatically deletes stagnant files to prevent a total server crash. It is actively protecting your infrastructure! ❤️
*   **❓ Question:** The bot is throwing an `AuthKeyUnregistered` or `Session Expired` error. How do I fix it?
    *   **💡 Answer:** This indicates that Telegram has forcefully terminated the Userbot session, or you manually logged the bot out via your active sessions menu. 
    *   *The Fix:* Simply type `/logout` to clear the old corrupted data, and then execute `/login` to generate a fresh, secure session. Done! ✅
<br>
---
<br>
<div align="center">
### 🏆 𝕿𝖍𝖊 𝕸𝖆𝖘𝖙𝖊𝖗𝖕𝖎𝖊𝖈𝖊 𝕮𝖔𝖓𝖈𝖑𝖚𝖘𝖎𝖔𝖓 🏆
*“In a digital landscape overflowing with data, this bot serves as the ultimate, unyielding bridge connecting restricted vaults directly to your open kingdom.”*
<br>
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg?style=for-the-badge)]()
[![Open Source Love svg1](https://img.shields.io/badge/Open%20Source-%E2%9D%A4%EF%B8%8F-red.svg?style=for-the-badge)]()
**Engineered with precision, immense dedication, and copious amounts of ☕ by a Professional Developer.**
<br>
*(You are entirely welcome to fork, clone, or deploy this code, but do prepare yourself to be absolutely astonished by its sheer velocity!)* 🚀🔥
</div>
