# -*- coding: utf-8 -*-
import os
import psutil
import time
import uvloop
uvloop.install()
import asyncio
import re
import shutil
import subprocess
import gc
import datetime
import uuid
from pathlib import Path
from collections import defaultdict
import motor.motor_asyncio
from pyrogram import Client, filters, enums, idle
import pyromod.listen
from pyrogram.errors import (
    FloodWait, UserIsBlocked, InputUserDeactivated, UserAlreadyParticipant,
    InviteHashExpired, UsernameNotOccupied, FileReferenceExpired, UserNotParticipant,
    ApiIdInvalid, PhoneNumberInvalid, PhoneCodeInvalid, PhoneCodeExpired,
    SessionPasswordNeeded, PasswordHashInvalid, PeerIdInvalid, AuthKeyUnregistered, UserDeactivated
)
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, Message, 
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat, CallbackQuery
)
from concurrent.futures import ThreadPoolExecutor
import traceback                        
import html
import math
import aiohttp
from urllib.parse import unquote, urlparse
import platform
import socket
import logging                          
from telegraph import Telegraph
from bson.objectid import ObjectId      # <-- REQUIRED FOR UNIQUE ROUTING
import speedtest                        # <-- REQUIRED FOR SPEEDTEST

# --- MASTER LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"), 
        logging.StreamHandler()                           
    ]
)
logger = logging.getLogger("BotLogger")
# ----------------------------

# --- TELEGRAPH SETUP FOR MEDIAINFO ---
telegraph = Telegraph(domain="graph.org") # Bypasses Cloudflare Datacenter IP Blocks!

def load_telegraph_token():
    token_file = Path("./telegraph_token.txt")
    if token_file.exists():
        with open(token_file, "r") as f:
            return f.read().strip()
    try:
        response = telegraph.create_account(short_name='MediaInfoBot')
        token = response.get('access_token')
        if token:
            tmp = token_file.with_suffix(".tmp")
            with open(tmp, "w") as f:
                f.write(token)
            tmp.replace(token_file)
            return token
    except Exception as e:
        logger.error(f"[Telegraph] Failed to create account: {e}", exc_info=True)
    return None

saved_token = load_telegraph_token()
if saved_token:
    try:
        telegraph.access_token = saved_token
    except Exception:
        pass

# ==============================================================================
# --- CONFIGURATION ---
# ==============================================================================

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

# Load the variables from .env or config.env file
load_dotenv() 

# --------------------------------------------------------------------------
# 🔴 COMPULSORY (Core Bot Credentials & Database)
# --------------------------------------------------------------------------
# The "or 0" and "or ''" prevent crashes if a variable is accidentally left blank
API_ID = int(os.environ.get("API_ID") or 0)
API_HASH = (os.environ.get("API_HASH") or "").strip()
BOT_TOKEN = (os.environ.get("BOT_TOKEN") or "").strip()

DB_URI = (os.environ.get("DB_URI") or "").strip()
DB_NAME = (os.environ.get("DB_NAME") or "").strip()

if not DB_URI:
    print("CRITICAL ERROR: DB_URI is empty! Please check your Render Environment Variables.")

# --------------------------------------------------------------------------
# 🟡 OPTIONAL: LOG CHANNEL
# --------------------------------------------------------------------------
_raw_log = (os.environ.get("LOG_CHANNEL") or "").strip()
if _raw_log:
    LOG_CHANNEL = _raw_log if "/" in _raw_log else (int(_raw_log) if _raw_log.replace("-", "").isdigit() else 0)
else:
    LOG_CHANNEL = 0

# --------------------------------------------------------------------------
# ⚙️ OPTIONAL: SETTINGS
# --------------------------------------------------------------------------
PORT = int(os.environ.get("PORT") or 8080)
LOGIN_SYSTEM = str(os.environ.get("LOGIN_SYSTEM", "True")).strip().lower() == "true"
ERROR_MESSAGE = str(os.environ.get("ERROR_MESSAGE", "True")).strip().lower() == "true"
WAITING_TIME = int(os.environ.get("WAITING_TIME") or 3)

# --------------------------------------------------------------------------
# 👥 ACCESS CONTROL (Comma-Separated User IDs)
# --------------------------------------------------------------------------
ADMINS = [int(x) for x in str(os.environ.get("ADMINS", "")).split(",") if x.strip().isdigit()]
SUDOS = [int(x) for x in str(os.environ.get("SUDOS", "")).split(",") if x.strip().isdigit()]

# --------------------------------------------------------------------------
# --- APPLICATION STATE ---
# --------------------------------------------------------------------------
TASK_QUEUE = defaultdict(list) 
io_executor = ThreadPoolExecutor(max_workers=min(16, (os.cpu_count() or 2) * 4))

HELP_TXT = """<b>📚 ULTIMATE BOT USAGE GUIDE</b>

Welcome! This bot helps you download restricted files and auto-forward messages. Here is everything you need to know:

▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬
<blockquote expandable>
<b>🟢 CORE COMMANDS</b>
• <code>/start</code> - <b>Wake Up & Welcome:</b> Greets you and registers your account.
• <code>/help</code> - <b>The Master Guide:</b> Opens this exact menu.
• <code>/cancel</code> - <b>Stop Everything:</b> Cleanly cancels any active setup process or massive downloading task.

<b>📥 DOWNLOADING & FORWARDING</b>
• <code>/dl</code> - <b>The Smart Downloader:</b> Manually downloads/copies media from a link. 
  ├ Reply to any Telegram link with <code>/dl</code>
  ├ Or type: <code>/dl https://t.me/channel/100</code>
  └ <i>Batch DL:</i> <code>/dl https://t.me/channel/101 - 120</code>

<b>🤖 DOWNLOADING FROM BOTS OR USER PMs</b>
To extract restricted files sent to you by other Bots or Users in Direct Messages:
1. Open the PM in Plus Messenger (or similar app) to get the Message ID.
2. Format the link using their username (without the @) and the message ID.
  ├ <b>Bot Example:</b> <code>/dl https://t.me/SaveRestrictedBot/150</code>
  └ <b>User Example:</b> <code>/dl https://t.me/JohnDoe/45</code>

<b>👀 LIVE AUTO-FORWARDER (WATCHERS)</b>
• <code>/watch</code> - <b>Set It and Forget It:</b> Auto-monitor a source and forward NEW messages instantly to your chosen destination.
  ├ <i>Channel:</i> <code>/watch https://t.me/channel/123</code>
  └ <i>Bot PM:</i> <code>/watch https://t.me/AnyBotUsername/123</code>
• <code>/watchers</code> - <b>Your Active List:</b> Interactive menu showing all your live monitors.
• <code>/unwatch</code> - <b>Turn Off a Watcher:</b> Instantly stops a specific monitor.
  └ <i>Usage:</i> <code>/unwatch SOURCE_ID</code> (Use the ID it comes <i>from</i>).

<b>🔑 ACCOUNT & SESSION</b>
• <code>/login</code> - <b>Link Your Account:</b> Securely connects your personal account session so the bot can bypass "Saving Restricted" limits and read your PMs.
• <code>/logout</code> - <b>Disconnect Safely:</b> Terminates your saved session and cleans up active watchers.
• <code>/chats</code> - <b>Chats & Channel Explorer:</b> Extract IDs of all your private chats, groups, channels, or bots with expandable quotes and filters.
</blockquote>
▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬"""

ADMIN_HELP_TXT = """<b>🛠️ ADMIN & SYSTEM COMMANDS</b>

These commands are strictly reserved for Bot Admins and Sudo users.

▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬
<blockquote expandable>
<b>🖥 SYSTEM HEALTH</b>
• <code>/status</code> - <b>Health Check:</b> Quick dashboard of live RAM, CPU, free disk space, and active downloads.
• <code>/sos</code> - <b>Deep Server Stats:</b> Detailed report of OS, uptime, storage breakdown, and monthly bandwidth.
• <code>/botstats</code> - <b>User Tracker:</b> Displays total users, who is logged in, and live breakdown of their tasks.
• <code>/log</code> - <b>Backend Logs:</b> Sends the live <code>bot.log</code> file to troubleshoot errors.

<b>🧰 UTILITIES</b>
• <code>/pixel</code> - <b>Pixeldrain Bypasser:</b> Converts Pixeldrain links into high-speed CDN direct-download links.
  └ <i>Usage:</i> <code>/pixel https://pixeldrain.com/u/xxxx</code>
• <code>/mediainfo</code> (or <code>/mi</code>) - <b>Technical Inspector:</b> Analyzes a media file (by link or reply) and publishes a Telegraph report of codecs, bitrates, etc.
• <code>/broadcast</code> - <b>Mass Announcements:</b> Reply to a message with this to forward it to EVERY registered user.
</blockquote>
▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬"""

# ==============================================================================
# --- DATABASE ---
# ==============================================================================

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(
            uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            maxPoolSize=50
        )
        self.db = self._client[database_name]
        self.col = self.db.users

    def new_user(self, id, name):
        return dict(
            id = id,
            name = name,
            session = None,
            api_id = None,
            api_hash = None,
        )

    async def add_user(self, id, name):
        user = self.new_user(id, name)
        await self.col.update_one(
            {'id': int(id)},
            {'$setOnInsert': user},
            upsert=True
        )

    async def is_user_exist(self, id):
        user = await self.col.find_one({'id':int(id)})
        return bool(user)

    async def total_users_count(self):
        count = await self.col.count_documents({})
        return count

    async def get_all_users(self):
        cursor = self.col.find({})
        return cursor

    async def delete_user(self, user_id):
        await self.col.delete_many({'id': int(user_id)})

    async def set_session(self, id, session):
        await self.col.update_one({'id': int(id)}, {'$set': {'session': session}})

    async def get_session(self, id):
        user = await self.col.find_one({'id': int(id)})
        return user.get('session') if user else None

    async def set_api_id(self, id, api_id):
        await self.col.update_one({'id': int(id)}, {'$set': {'api_id': api_id}})

    async def get_api_id(self, id):
        user = await self.col.find_one({'id': int(id)})
        return user.get('api_id') if user else None

    async def set_api_hash(self, id, api_hash):
        await self.col.update_one({'id': int(id)}, {'$set': {'api_hash': api_hash}})

    async def get_api_hash(self, id):
        user = await self.col.find_one({'id': int(id)})
        return user.get('api_hash') if user else None

    async def total_session_users_count(self):
        count = await self.col.count_documents({"session": {"$ne": None}})
        return count

    async def get_monthly_bandwidth(self):
        """Tracks, persists, and auto-resets monthly bandwidth usage in MongoDB across server reboots."""
        current_month = datetime.datetime.now().strftime("%Y-%m")
        month_display = datetime.datetime.now().strftime("%B %Y")
        
        net = psutil.net_io_counters()
        cur_raw_rx = net.bytes_recv
        cur_raw_tx = net.bytes_sent
        
        doc = await self.db.config.find_one({"_id": "monthly_bandwidth"})
        
        if not doc or doc.get("month") != current_month:
            new_data = {
                "month": current_month,
                "rx_bytes": 0,
                "tx_bytes": 0,
                "last_raw_rx": cur_raw_rx,
                "last_raw_tx": cur_raw_tx
            }
            await self.db.config.update_one({"_id": "monthly_bandwidth"}, {"$set": new_data}, upsert=True)
            return 0, 0, 0, month_display
            
        last_raw_rx = doc.get("last_raw_rx", cur_raw_rx)
        last_raw_tx = doc.get("last_raw_tx", cur_raw_tx)
        
        delta_rx = cur_raw_rx if cur_raw_rx < last_raw_rx else (cur_raw_rx - last_raw_rx)
        delta_tx = cur_raw_tx if cur_raw_tx < last_raw_tx else (cur_raw_tx - last_raw_tx)
        
        rx_total = doc.get("rx_bytes", 0) + max(0, delta_rx)
        tx_total = doc.get("tx_bytes", 0) + max(0, delta_tx)
        
        await self.db.config.update_one(
            {"_id": "monthly_bandwidth"},
            {"$set": {
                "rx_bytes": rx_total,
                "tx_bytes": tx_total,
                "last_raw_rx": cur_raw_rx,
                "last_raw_tx": cur_raw_tx
            }}
        )
        return rx_total, tx_total, (rx_total + tx_total), month_display
        
    # --- WATCHER METHODS ---
    async def add_watcher(
        self,
        user_id,
        source_id,
        dest_id,
        source_thread=None,
        dest_thread=None,
        delay=0,
        is_restricted=False,
        source_title=None,
        dest_title=None,
        allowed_types=None,
        dashboard_chat=None,
        dashboard_msg=None,
        last_msg_id=0     # 🟢 ADD THIS PARAMETER
    ):
        if allowed_types is None:
            allowed_types = ["Video", "Document"]

        query = {
            "user_id": int(user_id),
            "source_id": int(source_id),
            "source_thread": int(source_thread) if source_thread is not None else None,
            "dest_id": int(dest_id),                                             # <-- ADDED
            "dest_thread": int(dest_thread) if dest_thread is not None else None # <-- ADDED
        }
        
        update_data = {
            "user_id": int(user_id),
            "source_id": int(source_id),
            "dest_id": int(dest_id),
            "source_thread": int(source_thread) if source_thread is not None else None,
            "dest_thread": int(dest_thread) if dest_thread is not None else None,
            "delay": int(delay),
            "is_restricted": bool(is_restricted),
            "source_title": source_title,
            "dest_title": dest_title,
            "allowed_types": allowed_types,
            "dashboard_chat": dashboard_chat,
            "dashboard_msg": dashboard_msg,
            "created_at": datetime.datetime.now()
        }

        # $setOnInsert ensures stats are created only on the first run and not reset on updates
        await self.db.watchers.update_one(
            query, 
            {
                "$set": update_data,
                "$setOnInsert": {
                    "stats": {"detected": 0, "success": 0, "skipped": 0, "failed": 0},
                    "last_msg_id": last_msg_id   # 🟢 SAVE THE STARTING ID
                }
            }, 
            upsert=True
        )

    async def get_user_watchers(self, user_id):
        return self.db.watchers.find({"user_id": int(user_id)})

    async def get_watchers_for_source(self, source_id, source_thread=None):
        query = {"source_id": int(source_id)}
        if source_thread is None:
            query["source_thread"] = None
        else:
            query["source_thread"] = int(source_thread)
        return self.db.watchers.find(query)

    async def get_all_watchers(self):
        return self.db.watchers.find({})

    async def remove_watcher(self, user_id, source_id, source_thread=None):
        query = {
            "user_id": int(user_id),
            "source_id": int(source_id)
        }

        if source_thread is None:
            result = await self.db.watchers.delete_many({
                "$or": [
                    {**query, "source_thread": None},
                    {**query, "source_thread": {"$exists": False}}
                ]
            })
        else:
            query["source_thread"] = int(source_thread)
            result = await self.db.watchers.delete_many(query)

        return result.deleted_count > 0

    # ==========================================
    # --- BATCH TASKS (AUTO-RESUME) METHODS ---
    # ==========================================
    async def add_active_task(self, task_uuid, user_id, link, dest_chat_id, dest_thread_id, dest_title, delay, is_restricted, allowed_types, source_title, current_msg_id, to_id):
        task_data = {
            "task_uuid": task_uuid, "user_id": user_id, "link": link,
            "dest_chat_id": dest_chat_id, "dest_thread_id": dest_thread_id,
            "dest_title": dest_title, "delay": delay, "is_restricted": is_restricted,
            "allowed_types": allowed_types, "source_title": source_title,
            "current_msg_id": current_msg_id, "to_id": to_id
        }
        await self.db.active_tasks.update_one({"task_uuid": task_uuid}, {"$set": task_data}, upsert=True)

    async def update_task_progress(self, task_uuid, current_msg_id):
        await self.db.active_tasks.update_one({"task_uuid": task_uuid}, {"$set": {"current_msg_id": current_msg_id}})

    async def remove_active_task(self, task_uuid):
        await self.db.active_tasks.delete_one({"task_uuid": task_uuid})

    async def get_all_active_tasks(self):
        return self.db.active_tasks.find({})

db = Database(DB_URI, DB_NAME)

# ==============================================================================
# --- CLIENT & GLOBAL STATE ---
# ==============================================================================

app = Client(
    "RestrictedBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=min(32, (os.cpu_count() or 2) * 8), # Increased workers
    max_concurrent_transmissions=10,            # <--- NATIVE PARALLEL CHUNKING
    sleep_threshold=20,
    ipv6=False                    
)

import random

REACTIONS = [
    "👍", "👎", "❤", "🔥", "🥰", "👏", "😁", "🤔", "🤯", "😱", 
    "🤬", "😢", "🎉", "🤩", "🤮", "💩", "🙏", "👌", "🕊", "🤡", 
    "🥱", "🥴", "😍", "🐳", "❤‍🔥", "🌚", "🌭", "💯", "🤣", "⚡", 
    "🍌", "🏆", "💔", "🤨", "😐", "🍓", "🍾", "💋", "🖕", "😈", 
    "😴", "😭", "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈", "😇", "😨", 
    "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", "🤪", "🗿", 
    "🆒", "💘", "🙉", "🦄", "😘", "💊", "🙊", "😎", "👾", "🤷‍♂️", 
    "🤷", "🤷‍♀️", "😡"
]

ALL_COMMANDS = [
    "start", "help", "login", "logout", "dl", "watch", "unwatch", 
    "watchers", "cancel", "broadcast", "botstats", "status", 
    "log", "pixel", "sos", "mediainfo", "mi", "chats", "speedtest"
]

@app.on_message(filters.command(ALL_COMMANDS), group=-1)
async def global_command_reactor(client: Client, message: Message):
    try:
        await message.react(emoji=random.choice(REACTIONS), big=True)
    except Exception as e:
        logger.debug(f"Reaction failed for msg {message.id}: {e}")

BOT_START_TIME = time.time()
WATCHER_LAST_RUN = {} # Tracks strict delays between live watcher messages
ACTIVE_PROCESSES = defaultdict(dict)  
CANCEL_FLAGS = {} 

def cleanup_task_memory(user_id, task_uuid):
    CANCEL_FLAGS.pop(task_uuid, None)
    if user_id in ACTIVE_PROCESSES:
        ACTIVE_PROCESSES[user_id].pop(task_uuid, None)
        if not ACTIVE_PROCESSES[user_id]:
            ACTIVE_PROCESSES.pop(user_id, None)

batch_temp = type("BT", (), {})()
batch_temp.ACTIVE_TASKS = defaultdict(int)
batch_temp.IS_BATCH = defaultdict(bool)
batch_temp.SKIP_IDS = defaultdict(set) # ALBUM BATCHING TRACKER
WATCHER_MEDIA_GROUPS = {}              # ALBUM WATCHER TRACKER

SERVER_UPLOAD_LIMIT = asyncio.Semaphore(int(os.environ.get("SERVER_UPLOAD_LIMIT", 30))) 
USER_SEMAPHORE_LIMIT = 3 
USER_SEMAPHORES = defaultdict(lambda: asyncio.Semaphore(USER_SEMAPHORE_LIMIT))
USER_DOWNLOAD_SEMAPHORES = defaultdict(lambda: asyncio.Semaphore(3))

from collections import defaultdict

class FloodController:
    def __init__(self):
        self.locked_until = 0

    async def wait_if_locked(self):
        now = time.time()
        if now < self.locked_until:
            wait_time = self.locked_until - now
            print(f"🚦 User Rate Limit! Task pausing for {wait_time:.1f}s.")
            await asyncio.sleep(wait_time)

    def set_lock(self, wait_seconds):
        unlock_time = time.time() + wait_seconds
        if unlock_time > self.locked_until:
            self.locked_until = unlock_time

USER_FLOOD_LOCKS = defaultdict(FloodController)

# --- PAUSE & WAIT INTERCEPTOR ---
from pyrogram.errors import ChatWriteForbidden, ChatAdminRequired, ChannelPrivate, UserBannedInChannel, PeerIdInvalid, FloodWait

BOT_WARNING_SENT = set() # Remembers if we already warned you about a broken destination

async def check_dest_access(client_to_use, dest_chat_id):
    """Silently tests if the client still has access to the destination."""
    if str(dest_chat_id).startswith("-"):
        try:
            await client_to_use.get_chat(dest_chat_id)
            return True
        except Exception:
            return False
    return True

async def wait_for_access(client_to_use, dest_chat_id, user_id, error_str, task_uuid=None):
    warning_msg = (
        f"🛑 **CRITICAL: User Session Disconnected!**\n\n"
        f"Task fully paused because your **User Session** ALSO lost Admin rights or was removed from the destination (`{dest_chat_id}`).\n"
        f"**Error:** `{error_str}`\n\n"
        f"🔄 **Action Required:** Please ensure your account has access and Admin rights in the destination. The task will resume automatically."
    )
    notify = None
    try: notify = await app.send_message(user_id, warning_msg)
    except: pass

    while True:
        if task_uuid and CANCEL_FLAGS.get(task_uuid): raise Exception("CANCELLED_BY_USER")
        if batch_temp.IS_BATCH.get(user_id): raise Exception("CANCELLED_BY_USER")
            
        await asyncio.sleep(10)
        if await check_dest_access(client_to_use, dest_chat_id): break 
            
    try:
        if notify: await notify.edit_text("✅ **User Session Access Restored! Resuming task...**")
    except: pass

async def safe_send(client_to_use, user_id, dest_chat_id, task_uuid, is_bot, coro_func, *args, **kwargs):
    """Wraps Pyrogram methods. Falls back to User Session if Bot fails. Pauses if User Session fails."""
    while True:
        try:
            res = await coro_func(*args, **kwargs)
            
            # If the Bot successfully sent it, check if we were previously broken.
            warning_key = f"{user_id}_{dest_chat_id}"
            if is_bot and warning_key in BOT_WARNING_SENT:
                BOT_WARNING_SENT.remove(warning_key) # Clear the warning flag
                try: await app.send_message(user_id, f"✅ **Bot Access Restored to `{dest_chat_id}`!**\nResuming high-speed Bot routing.")
                except: pass
                
            return res
            
        except Exception as e:
            if isinstance(e, FloodWait):
                raise e # Let FloodWaits be handled safely by the outer loops
                
            err_str = str(e)
            has_dest_access = await check_dest_access(client_to_use, dest_chat_id)
            
            # If we lost destination access, OR we got a write error (kicked/demoted)
            if not has_dest_access or isinstance(e, (ChatWriteForbidden, ChatAdminRequired, UserBannedInChannel)):
                if is_bot:
                    warning_key = f"{user_id}_{dest_chat_id}"
                    if warning_key not in BOT_WARNING_SENT:
                        msg = (f"⚠️ **Bot Removed or Demoted!**\n\n"
                               f"I lost Admin rights or was removed from `{dest_chat_id}`. I am smoothly falling back to your **User Session** to continue forwarding!\n\n"
                               f"🔄 **Note:** I will keep testing the Bot in the background. If you promote me back to Admin, I will instantly switch back to high-speed Bot routing.")
                        try: await app.send_message(user_id, msg)
                        except: pass
                        BOT_WARNING_SENT.add(warning_key)
                    # Bubble the error up so the main script immediately triggers the User Session Fallback!
                    raise e 
                else:
                    # The User Session ALSO failed. Now we must TRULY pause.
                    await wait_for_access(client_to_use, dest_chat_id, user_id, err_str, task_uuid)
                    continue
            else:
                # Source error (ChannelPrivate). Bubble up to User Session.
                raise e
# --------------------------------

PENDING_TASKS = {}
PROGRESS = {}
LAST_UI_EDIT = {}  # 🟢 NEW: Global UI Clock
SESSION_STRING_SIZE = 351

MAX_CONCURRENT_TASKS_PER_USER = int(os.environ.get("MAX_TASKS_PER_USER", "3"))
USER_CLIENTS = {}
ALL_MSG_TYPES = ["Video", "Document", "Text", "Audio", "Photo", "Voice", "Animation", "Sticker"]

# ==============================================================================
# --- HELPERS ---
# ==============================================================================

def parse_chat_topic(value):
    if not value:
        return None, None
    value = str(value).strip()
    if "/" in value:
        chat_id, topic_id = value.split("/", 1)
        return int(chat_id), int(topic_id)
    return int(value), None

def _parse_chat_target(text: str):
    text = text.strip()
    if text.startswith("https://t.me/") or text.startswith("http://t.me/"):
        text = text.replace("https://", "").replace("http://", "")
        text = text.split("t.me/", 1)[-1].split("?", 1)[0].strip("/")
    if text.startswith("@"):
        return text, None
    if "/" in text:
        chat_part, topic_part = text.split("/", 1)
        chat_part = chat_part.strip()
        topic_part = topic_part.strip()
        return int(chat_part), int(topic_part) if topic_part.isdigit() else None
    if text.lstrip("-").isdigit():
        return int(text), None
    return text, None

def _parse_source_link(src_link: str):
    raw = (src_link or "").strip()
    raw = raw.replace("https://", "").replace("http://", "")
    raw = raw.replace("t.me/", "")
    raw = raw.split("?", 1)[0].strip("/")

    is_private_c = raw.startswith("c/")
    if is_private_c:
        clean = raw[2:]
        parts = clean.split("/")
        source_id = int("-100" + parts[0])
        topic_id = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else None
        msg_id = int(parts[-1]) if parts[-1].isdigit() else None
        return {
            "kind": "private_c",
            "join_target": None,
            "chat_id": source_id,
            "topic_id": topic_id,
            "msg_id": msg_id,
        }

    parts = raw.split("/")
    username = parts[0]
    topic_id = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else None
    msg_id = int(parts[-1]) if parts[-1].isdigit() else None

    if username.startswith("+") or "joinchat" in username:
        return {
            "kind": "invite",
            "join_target": f"https://t.me/{raw}",
            "chat_id": None,
            "topic_id": topic_id,
            "msg_id": msg_id,
        }

    return {
        "kind": "public",
        "join_target": username,
        "chat_id": username,
        "topic_id": topic_id,
        "msg_id": msg_id,
    }

def _pretty_bytes(n: float) -> str:
    try:
        n = float(n)
    except Exception:
        return "0 B"
    if n == 0: return "0 B"
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    unit = units[i]
    if unit == "B": return f"{int(n)} {unit}"
    else: return f"{n:.1f} {unit}"

import unicodedata

def get_readable_time(seconds: int) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = 0
    if seconds <= 0: return "0s"
    
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    
    time_parts = []
    if days > 0: time_parts.append(f"{days}d")
    if hours > 0: time_parts.append(f"{hours}h")
    if minutes > 0: time_parts.append(f"{minutes}m")
    if seconds > 0 or not time_parts: time_parts.append(f"{seconds}s")
    return " ".join(time_parts)

def generate_bar(percent: float, length: int = 12) -> str:
    percent = max(0.0, min(100.0, percent)) 
    filled_length = int(length * percent / 100)
    fraction = (percent / 100 * length) - filled_length
    has_half = fraction >= 0.5
    
    bar = '⬤' * filled_length
    if has_half and filled_length < length:
        bar += '◔'
        bar += '○' * (length - filled_length - 1)
    else:
        bar += '○' * (length - filled_length)
        
    return f"〘{bar}〙 {percent:.1f}%"
    
def sanitize_filename(filename: str) -> str:
    if not filename: return "unnamed_file"
    filename = unicodedata.normalize("NFC", filename)
    filename = re.sub(r'[:]', "-", filename)
    filename = re.sub(r'[\\/*?"<>|\[\]]', "", filename)
    name, ext = os.path.splitext(filename)
    if len(name) > 60:
        name = name[:60]
        
    reserved = {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"}
    if name.upper() in reserved:
        name += "_"
        
    if not ext:
        ext = ".dat"
    return f"{name}{ext}"

async def get_topic_title(client, chat_id, topic_id):
    """Dynamically fetches the real name of a Telegram Forum Topic."""
    if not topic_id: return ""
    
    # 1. High-Level Method (Kurigram/Pyrofork Native)
    try:
        if hasattr(client, "get_forum_topic"):
            topic = await client.get_forum_topic(chat_id, int(topic_id))
            if isinstance(topic, list) and topic and getattr(topic[0], "title", None): 
                return f" ({topic[0].title})"
            elif getattr(topic, "title", None):
                return f" ({topic.title})"
    except Exception: pass

    # 2. Raw MTProto API Method (Bulletproof for all topics)
    try:
        from pyrogram.raw.functions.channels import GetForumTopicsByID
        peer = await client.resolve_peer(chat_id)
        res = await client.invoke(GetForumTopicsByID(channel=peer, topics=[int(topic_id)]))
        if getattr(res, "topics", None) and len(res.topics) > 0:
            return f" ({res.topics[0].title})"
    except Exception: pass

    # 3. Last-Resort Message Fallback
    try:
        msg = await client.get_messages(chat_id, int(topic_id))
        if msg:
            if getattr(msg, "forum_topic", None) and getattr(msg.forum_topic, "title", None):
                return f" ({msg.forum_topic.title})"
            if getattr(msg, "action", None) and getattr(msg.action, "title", None):
                return f" ({msg.action.title})"
            if getattr(msg, "reply_to_message", None) and getattr(msg.reply_to_message, "forum_topic", None):
                if getattr(msg.reply_to_message.forum_topic, "title", None):
                    return f" ({msg.reply_to_message.forum_topic.title})"
    except Exception: pass

    return f" (Topic {topic_id})"

async def check_link_restriction(user_id, link_text):
    raw = (link_text or "").strip()
    raw = raw.replace("https://", "").replace("http://", "")
    raw = raw.replace("t.me/", "")
    raw = raw.split("?", 1)[0].strip("/")

    if raw.startswith("+") or "joinchat" in raw:
        return False, "🔗 **Invite link detected.** Join the chat first before checking restrictions."

    clean_text = raw.replace("c/", "")
    if "-" in clean_text:
        clean_text = clean_text.split("-", 1)[0].strip()

    parts = clean_text.split("/")
    
    is_private = False
    chat_id = None
    msg_id = None

    try:
        # 1. Handle Bot DMs cleanly (Routes to User Session)
        if "t.me/b/" in link_text or str(parts[0]).lower().endswith("bot"):
            is_private = True
            if "t.me/b/" in link_text:
                chat_id = parts[1] if len(parts) > 1 else parts[0]
            else:
                chat_id = parts[0]
            
            chat_id = chat_id.strip().replace("@", "")
            if len(parts) > 1 and parts[-1].strip().isdigit():
                msg_id = int(parts[-1].strip())

        # 2. Handle Private Channels/Groups
        elif "t.me/c/" in link_text:
            is_private = True
            chat_id = int("-100" + parts[0].strip())
            if len(parts) > 1 and parts[-1].strip().isdigit():
                msg_id = int(parts[-1].strip())
                
        # 3. Handle Public Channels/Groups
        else:
            chat_id = parts[0].strip().replace("@", "")
            if len(parts) > 1 and parts[-1].strip().isdigit():
                msg_id = int(parts[-1].strip())
            
            if str(chat_id).isdigit():
                is_private = True
                chat_id = int(chat_id)
            
    except Exception as e:
        return None, f"⚠️ **Could not analyze link.** Error: {e}"

    is_temp_client = False
    check_client = app 
    user_session = await db.get_session(user_id)
    
    if is_private:
        existing_client = USER_CLIENTS.get(user_id)
        if existing_client and existing_client.is_connected:
            check_client = existing_client
        elif user_session:
            api_id = await db.get_api_id(user_id) or API_ID
            api_hash = await db.get_api_hash(user_id) or API_HASH
            check_client = Client(":memory:", session_string=user_session, api_id=api_id, api_hash=api_hash, no_updates=True, ipv6=False)
            is_temp_client = True
    
    is_restricted = False
    status_msg = ""

    try:
        if is_temp_client:
            await check_client.connect()

        # PYROGRAM NATIVE MAGIC: Feed the string chat_id directly.
        # It handles public usernames and bots without joining!
        if msg_id:
            try:
                msg = await check_client.get_messages(chat_id, msg_id)
            except Exception as bot_err:
                if check_client == app and user_session:
                    api_id = await db.get_api_id(user_id) or API_ID
                    api_hash = await db.get_api_hash(user_id) or API_HASH
                    check_client = Client(":memory:", session_string=user_session, api_id=api_id, api_hash=api_hash, no_updates=True, ipv6=False)
                    await check_client.connect()
                    is_temp_client = True
                    try:
                        msg = await check_client.get_messages(chat_id, msg_id)
                    except Exception as user_err:
                        raise user_err
                else:
                    raise bot_err

            if not msg or msg.empty:
                raise Exception("Message not found or inaccessible.")

            if getattr(msg.chat, "has_protected_content", False) or getattr(msg, "has_protected_content", False):
                is_restricted = True
                status_msg = "🔒 **Source is RESTRICTED** (Will use Download Mode)"
            else:
                is_restricted = False
                status_msg = "🔓 **Source is PUBLIC/UNRESTRICTED** (Will use Fast Forward)"
        else:
            try:
                chat = await check_client.get_chat(chat_id)
            except Exception as bot_err:
                if check_client == app and user_session:
                    api_id = await db.get_api_id(user_id) or API_ID
                    api_hash = await db.get_api_hash(user_id) or API_HASH
                    check_client = Client(":memory:", session_string=user_session, api_id=api_id, api_hash=api_hash, no_updates=True, ipv6=False)
                    await check_client.connect()
                    is_temp_client = True
                    try:
                        chat = await check_client.get_chat(chat_id)
                    except Exception as user_err:
                        raise user_err
                else:
                    raise bot_err

            if getattr(chat, "has_protected_content", False):
                is_restricted = True
                status_msg = "🔒 **Channel is RESTRICTED** (Will use Download Mode)"
            else:
                is_restricted = False
                status_msg = "🔓 **Channel is PUBLIC/UNRESTRICTED**"

    except Exception as e:
        err_str = str(e)
        if "CHANNEL_PRIVATE" in err_str or "USER_NOT_PARTICIPANT" in err_str:
            status_msg = "⚠️ **Private Chat:** I can't check yet (You need to join first)."
        elif "USERNAME_NOT_OCCUPIED" in err_str or "USERNAME_INVALID" in err_str or "PEER_ID_INVALID" in err_str:
            if check_client != app:
                return None, f"❌ **Telegram Blocked Access:** Even your logged account cannot see this! It may be geo-blocked or deleted."
            else:
                return None, f"❌ **Bot Blocked:** The bot cannot see this public channel. \n\n💡 **FIX:** Please use `/login` to link your account, and I will resolve it using your session!"
        elif "AuthKeyUnregistered" in err_str or "SessionRevoked" in err_str:
            return None, f"❌ **Session Expired:** Your login session is invalid. Please run `/logout` and then `/login` again."
        else:
            return None, f"❌ **Check Failed:** `{err_str[:50]}...`\nPlease ensure the link is active and valid."
    finally:
        if is_temp_client:
            try: await check_client.disconnect()
            except: pass
        
    return is_restricted, status_msg

async def split_file_python(file_path, chunk_size=2000*1024*1024):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(io_executor, _split_file_smart, file_path, chunk_size)

def _split_file_smart(file_path, chunk_size):
    file_path = Path(file_path)
    if not file_path.exists():
        return []

    file_size = os.path.getsize(file_path)
    if file_size <= chunk_size:
        return [file_path]

    if shutil.which("split"):
        try:
            output_prefix = f"{file_path}.part"
            cmd = ["split", "-b", str(chunk_size), "-d", "-a", "3", str(file_path), output_prefix]
            subprocess.run(cmd, check=True, capture_output=True)
            parts = sorted(list(file_path.parent.glob(f"{file_path.name}.part*")))
            if parts: return parts
        except Exception as e: 
            logger.debug(f"Linux 'split' failed, falling back... Error: {e}")

    seven_z_exe = shutil.which("7z") or shutil.which("7za")
    if seven_z_exe:
        try:
            output_archive = f"{file_path}.7z"
            cmd = [seven_z_exe, "a", f"-v{chunk_size}b", "-mx0", output_archive, str(file_path)]
            subprocess.run(cmd, check=True, capture_output=True)
            parts = sorted(list(file_path.parent.glob(f"{file_path.name}.7z.*")))
            if parts: return parts
        except Exception as e: 
            logger.debug(f"7z split failed, falling back... Error: {e}")

    part_num = 0
    parts = []
    buffer_size = 2 * 1024 * 1024 
    
    with open(file_path, 'rb') as source:
        while True:
            part_name = file_path.parent / f"{file_path.name}.part{part_num:03d}"
            current_chunk_size = 0
            with open(part_name, 'wb') as dest:
                while current_chunk_size < chunk_size:
                    read_size = min(buffer_size, chunk_size - current_chunk_size)
                    data = source.read(read_size)
                    if not data: break
                    dest.write(data)
                    current_chunk_size += len(data)
            if current_chunk_size == 0:
                if part_name.exists(): part_name.unlink()
                break
            parts.append(part_name)
            part_num += 1
    return parts
    
def progress(current, total, message, typ, task_uuid=None):
    if task_uuid and CANCEL_FLAGS.get(task_uuid):
        raise Exception("CANCELLED_BY_USER")

    try:
        msg_id = int(message.id)
    except:
        try:
            msg_id = int(message)
        except:
            return
    key = f"{msg_id}:{typ}"
    now = time.time()
    if key not in PROGRESS:
        PROGRESS[key] = {
            "current": 0, "total": int(total), "percent": 0.0,
            "last_time": now, "last_current": 0, "speed": 0.0, "eta": None
        }
    rec = PROGRESS[key]
    rec["current"] = int(current)
    rec["total"] = int(total)
    if total > 0:
        rec["percent"] = (current / total) * 100.0
    dt = now - rec["last_time"]
    if dt >= 1 or current == total:
        delta_bytes = current - rec["last_current"]
        if dt <= 0: dt = 0.1
        speed = delta_bytes / dt
        rec["speed"] = speed
        rec["last_time"] = now
        rec["last_current"] = current
        if speed > 0 and total > current:
            rec["eta"] = (total - current) / speed
            
async def downstatus(client: Client, status_message: Message, chat, index: int, total_count: int, header_text: str = ""):
    msg_id = status_message.id
    key = f"{msg_id}:down"
    last_text = ""
    while True:
        rec = PROGRESS.get(key)
        if not rec:
            await asyncio.sleep(1)
            continue
        if rec["current"] == rec["total"] and rec["total"] > 0:
            break
            
        now = time.time()
        last_edit = LAST_UI_EDIT.get(msg_id, 0)
        time_since_edit = now - last_edit

        # 🟢 Global Clock: Has it been 30 seconds across the entire batch?
        if time_since_edit >= 30 or last_edit == 0:
            header_section = f"{header_text}\n" if header_text else ""
            status = (
                f"📥 **Downloading File ({index}/{total_count})**\n"
                f"└ 📂 `{max(0, total_count-index)}` remaining\n\n"
                f"**{rec.get('percent', 0):.1f}%** │ `{generate_bar(rec.get('percent', 0), length=12)}`\n\n"
                f"{header_section}"
                f"🚀 **Speed:** `{_pretty_bytes(rec.get('speed', 0))}/s`\n"
                f"💾 **Size:** `{_pretty_bytes(rec.get('current', 0))} / {_pretty_bytes(rec.get('total', 0))}`\n"
                f"⏳ **ETA:** `{get_readable_time(int(rec.get('eta', 0)) if rec.get('eta') else 0)}`"
            )

            if status != last_text:
                try:
                    await client.edit_message_text(chat, msg_id, status)
                    last_text = status
                    LAST_UI_EDIT[msg_id] = time.time()
                except FloodWait as e:
                    logger.warning(f"UI Rate Limit ({e.value}s). Pushing next UI update to future.")
                    LAST_UI_EDIT[msg_id] = time.time() + e.value
                except Exception as e:
                    logger.debug(f"Progress bar edit skipped: {e}")
        
        await asyncio.sleep(2)
            
async def upstatus(client: Client, status_message: Message, chat, index: int, total_count: int, header_text: str = ""):
    msg_id = status_message.id
    key = f"{msg_id}:up"
    last_text = ""
    while True:
        rec = PROGRESS.get(key)
        if not rec:
            await asyncio.sleep(1)
            continue
        if rec["current"] == rec["total"] and rec["total"] > 0:
            break
            
        now = time.time()
        last_edit = LAST_UI_EDIT.get(msg_id, 0)
        time_since_edit = now - last_edit

        # 🟢 Global Clock: Has it been 30 seconds across the entire batch?
        if time_since_edit >= 30 or last_edit == 0:
            header_section = f"{header_text}\n" if header_text else ""
            status = (
                f"☁️ **Uploading File ({index}/{total_count})**\n"
                f"└ 📤 `{max(0, total_count-index)}` remaining\n\n"
                f"**{rec.get('percent', 0):.1f}%** │ `{generate_bar(rec.get('percent', 0), length=12)}`\n\n"
                f"{header_section}"
                f"🚀 **Speed:** `{_pretty_bytes(rec.get('speed', 0))}/s`\n"
                f"💾 **Size:** `{_pretty_bytes(rec.get('current', 0))} / {_pretty_bytes(rec.get('total', 0))}`\n"
                f"⏳ **ETA:** `{get_readable_time(int(rec.get('eta', 0)) if rec.get('eta') else 0)}`"
            )

            if status != last_text:
                try:
                    await client.edit_message_text(chat, msg_id, status)
                    last_text = status
                    LAST_UI_EDIT[msg_id] = time.time()
                except FloodWait as e:
                    logger.warning(f"UI Rate Limit ({e.value}s). Pushing next UI update to future.")
                    LAST_UI_EDIT[msg_id] = time.time() + e.value
                except Exception as e:
                    logger.debug(f"Progress bar edit skipped: {e}")
        
        await asyncio.sleep(2)
            
def get_message_type(msg: Message):
    if msg.document: return "Document"
    if msg.video: return "Video"
    if msg.animation: return "Animation"
    if msg.sticker: return "Sticker"
    if msg.voice: return "Voice"
    if msg.audio: return "Audio"
    if msg.photo: return "Photo"
    if msg.text: return "Text"
    return None

# ==============================================================================
# --- HANDLERS (START/HELP/STATUS/CANCEL/etc.) ---
# ==============================================================================

@app.on_message(filters.command(["start"]) & (filters.private | filters.group))
async def send_start(client: Client, message: Message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    if message.from_user.last_name:
        user_name += f" {message.from_user.last_name}"
    
    try:
        if not await db.is_user_exist(user_id):
            await db.add_user(user_id, user_name)
            logger.info(f"New user {user_id} saved to database.") 
        else:
            await db.col.update_one({"id": int(user_id)}, {"$set": {"name": user_name}})
    except Exception as e:
        logger.error(f"Failed to save user {user_id}: {e}", exc_info=True)

    welcome_video_url = "https://files.catbox.moe/o9azww.mp4"
    
    # 🟢 UNIVERSAL URL AUTO-DETECTOR (HuggingFace, Render, Koyeb, Railway, Custom)
    raw_url = (
        os.environ.get("WEB_URL") or 
        os.environ.get("SPACE_HOST") or 
        os.environ.get("RENDER_EXTERNAL_URL") or 
        os.environ.get("KOYEB_PUBLIC_DOMAIN") or
        os.environ.get("RAILWAY_STATIC_URL")
    )
    
    if raw_url:
        raw_url = raw_url.rstrip("/")
        # Force HTTP/HTTPS prefix to prevent Telegram inline button crash
        if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
            web_url = f"https://{raw_url}"
        else:
            web_url = raw_url
    else:
        # Failsafe for Localhost or VPS without domain set
        web_url = f"http://127.0.0.1:{PORT}"

    welcome_text = (
        f"<b>👋 Hi {message.from_user.mention}, I am the Restricted Content Bot.</b>\n\n"
        "<blockquote expandable>"
        "<b>🛡 Features:</b>\n"
        "• Download Restricted Content\n"
        "• Setup Live Auto-Forwarders (Watchers)\n"
        "• Fast, Multi-Threaded Processing\n\n"
        "<b>🔑 Note:</b> For downloading private restricted content, you need to <code>/login</code> first.\n\n"
        "<b>📚 Know how to use the bot by sending /help</b>\n"
        "</blockquote>\n\n"
        f"<b>🌐 Web Dashboard:</b>\n"
        f"Control the bot, add tasks, and monitor active downloads directly from your browser:\n"
        f"🔗 <code>{web_url}</code>"
    )
    
    buttons = [
        [InlineKeyboardButton("🌐 Open Web Dashboard", url=web_url)],
        [InlineKeyboardButton("❣️ Developer", url="https://t.me/DestinyM66"), InlineKeyboardButton('🔍 Support', url='https://t.me/DestinyM66')]
    ]

    try:
        await client.send_video(
            chat_id=message.chat.id, 
            video=welcome_video_url, 
            caption=welcome_text, 
            reply_markup=InlineKeyboardMarkup(buttons),
            reply_to_message_id=message.id,
            parse_mode=enums.ParseMode.HTML
        )
    except FloodWait as e:
        logger.warning(f"Blocked /start video due to FloodWait: {e.value}s")
    except Exception:
        try:
            await client.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=InlineKeyboardMarkup(buttons),
                reply_to_message_id=message.id,
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
        except FloodWait: pass

@app.on_message(filters.command(["help"]) & (filters.private | filters.group))
async def send_help(client: Client, message: Message):
    user_id = message.from_user.id
    
    # 1. The bot checks if the user is an Admin
    is_admin = user_id in ADMINS or user_id in SUDOS

    try:
        # 2. It sends the normal help guide to everyone
        await client.send_message(
            message.chat.id, 
            text=HELP_TXT,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        # 3. IF the user is an admin, it sends this secret menu too!
        if is_admin:
            await client.send_message(
                message.chat.id, 
                text=ADMIN_HELP_TXT,  # <--- Here is where your text gets used!
                parse_mode=enums.ParseMode.HTML,
                disable_web_page_preview=True
            )
    except FloodWait as e:
        logger.warning(f"Blocked /help due to FloodWait: {e.value}s")

@app.on_message(filters.command(["cancel"]) & (filters.private | filters.group))
async def send_cancel(client: Client, message: Message):
    user_id = message.from_user.id

    try:
        if user_id in PENDING_TASKS:
            del PENDING_TASKS[user_id]
            await message.reply("✅ **Setup process cancelled.** You can send a new link now.")
            return

        user_tasks = ACTIVE_PROCESSES.get(user_id, {})
        if not user_tasks:
            await message.reply(
                "✅ **Nothing to cancel!**\n\n"
                "You currently have no active downloads, setups, or background tasks running.\n\n"
                "💡 **Tip:** If you want to start a new download, just send `/dl <link>`."
            )
            return

        buttons = []
        for tid, info in list(user_tasks.items()):
            label = info.get("item", "Task")
            label_short = (label[:26] + "...") if len(label) > 29 else label
            buttons.append([InlineKeyboardButton(f"🛑 {label_short}", callback_data=f"cancel_task:{tid}")])
        buttons.append([InlineKeyboardButton("🛑 Cancel ALL My Tasks", callback_data="cancel_all")])
        buttons.append([InlineKeyboardButton("❌ Close Menu", callback_data="close_menu")])

        await message.reply(
            "**🚫 Cancel Tasks**\n\nSelect the task you want to cancel:",
            reply_markup=InlineKeyboardMarkup(buttons),
            quote=True
        )
    except FloodWait as e:
        logger.warning(f"Blocked /cancel menu due to FloodWait: {e.value}s")
    
@app.on_callback_query(filters.regex(r"^cancel_") | filters.regex(r"^cancel_task:"))
async def cancel_callback(client: Client, query):
    user_id = query.from_user.id
    data = query.data

    if data == "cancel_setup":
        if user_id in PENDING_TASKS:
            del PENDING_TASKS[user_id]
        cancel_text = (
            "❌ **Task Setup Cancelled**\n\n"
            "**What happened?**\n"
            "The configuration for this link has been discarded and cleared from my memory. No files were downloaded.\n\n"
            "💡 **Next Steps:**\n"
            "• Reply to a new link with `/dl` to start a new download.\n"
            "• Use `/watch` to set up an auto-forwarder.\n"
            "• Type `/help` for the master guide."
        )
        try: await query.message.edit(cancel_text)
        except Exception: pass
        return

    if data == "cancel_all":
        user_tasks = list(ACTIVE_PROCESSES.get(user_id, {}).keys())
        if not user_tasks:
            await query.answer("No active tasks to cancel.", show_alert=True)
            try: await query.message.delete()
            except: pass
            return
            
        for tid in user_tasks:
            CANCEL_FLAGS[tid] = True
        batch_temp.IS_BATCH[user_id] = True
        
        # 🟢 [DB WIPE] Failsafe: instantly remove from auto-resume DB
        try: await db.db.active_tasks.delete_many({"user_id": user_id})
        except: pass
        
        cancel_all_text = (
            "🛑 **Cancelling ALL Active Tasks...**\n\n"
            "**What is happening?**\n"
            "I am intercepting all your active downloads and uploads. It may take a few seconds to safely sever the TCP connections to Telegram's servers.\n\n"
            "🛡 **Why is this useful?**\n"
            "Cancelling heavy, stuck, or accidental batches frees up the server's bandwidth and clears your queue so you can start fresh."
        )
        try: await query.message.edit(cancel_all_text)
        except Exception: pass
        return

    if data.startswith("cancel_task:"):
        task_uuid = data.split(":",1)[1]
        user_tasks = ACTIVE_PROCESSES.get(user_id, {})
        if task_uuid not in user_tasks:
            await query.answer("Task not found or already finished.", show_alert=True)
            try: await query.message.delete()
            except: pass
            return
            
        CANCEL_FLAGS[task_uuid] = True
        task_name = user_tasks[task_uuid].get('item','Unknown Task')
        
        # 🟢 [DB WIPE] Failsafe: instantly remove this specific task from DB
        try: await db.remove_active_task(task_uuid)
        except: pass
        
        cancel_single_text = (
            f"🛑 **Task Cancelled Successfully!**\n\n"
            f"**Target:** `{task_name}`\n\n"
            f"**What happens now?**\n"
            f"The current file chunk will finish, and then the process will cleanly abort. Your other queued tasks (if any) will now speed up!"
        )
        try: await query.message.edit(cancel_single_text)
        except Exception: pass
        return
        
@app.on_callback_query(filters.regex("^close_menu"))
async def close_menu(client, query):
    try:
        await query.message.delete()
    except Exception:
        help_text = (
            "❌ **Menu Closed.**\n\n"
            "💡 **Quick Tips:**\n"
            "• `/dl` - Download from a link\n"
            "• `/watchers` - Manage live forwards\n"
            "• `/help` - Open the master guide"
        )
        try: await query.message.edit(help_text)
        except Exception: pass
    try: await query.answer("Closed.", show_alert=False)
    except Exception: pass

@app.on_message(filters.command(["log"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def send_log_handler(client: Client, message: Message):
    try:
        if os.path.exists("bot.log"):
            await message.reply_document("bot.log", caption="📄 **Bot Logs**\n(Updates automatically)")
        else:
            await message.reply("⚠️ Log file not found yet.")
    except FloodWait as e:
        logger.warning(f"Blocked /log due to FloodWait: {e.value}s")

@app.on_message(filters.command(["pixel"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def pixel_bypass_handler(client: Client, message: Message):
    if len(message.command) < 2:
        try:
            return await message.reply(
                "❌ **How to bypass Pixeldrain links:**\n\n"
                "Send a valid Pixeldrain link to get a high-speed direct download link that bypasses limits.\n\n"
                "**Examples:**\n"
                "• Single Link: `/pixel https://pixeldrain.com/u/xxxx`\n"
                "• Multiple Links: `/pixel link1, link2, link3`"
            )
        except FloodWait: return

    input_text = message.text.split(None, 1)[1]
    matches = re.findall(r"pixeldrain\.com/u/([a-zA-Z0-9_-]+)", input_text)
    
    if not matches:
        try:
            return await message.reply(
                "❌ **No valid Pixeldrain links found.**\n"
                "Please ensure the links follow the format: `https://pixeldrain.com/u/XXXX`"
            )
        except FloodWait: return

    lines = []
    for match in matches:
        orig = f"https://pixeldrain.com/u/{match}"
        byp = f"https://cdn.pixeldrain.eu.cc/{match}"
        lines.append(f"🔗 **Original:** {orig}\n🔓 **Bypassed:** `{byp}`\n")
        
    bypassed_text = "\n".join(lines)
    
    reply_text = (
        "✨ **Pixeldrain Bypass Successful!** ✨\n\n"
        "**📥 Bypassed Links:**\n\n"
        f"{bypassed_text}\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "🌐 **Original Bypass Website:** [Click Here](https://pixeldrain-bypass.gamedrive.org/)\n"
        "📜 **Userscript:** [Install Script](https://pixeldrain-bypass.gamedrive.org/pixeldrain-bypass.user.js)"
    )
    try: await message.reply(reply_text, disable_web_page_preview=True)
    except FloodWait: pass

# ==============================================================================
# --- SPEEDTEST HANDLER ---
# ==============================================================================

@app.on_message(filters.command(["speedtest"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def speedtest_handler(client: Client, message: Message):
    try:
        status_msg = await message.reply("<i>Initiating Speedtest...</i>", parse_mode=enums.ParseMode.HTML)
    except FloodWait as e:
        return logger.warning(f"Silently blocked /speedtest init due to FloodWait: {e.value}s")
    
    def run_speedtest_sync():
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            st.download()
            st.upload()
            st.results.share() # Generates the image link
            return st.results.dict(), None
        except Exception as e:
            return None, str(e)

    try:
        # Run blocking speedtest in a separate thread to avoid freezing bot
        result, error = await asyncio.to_thread(run_speedtest_sync)
        
        if error or not result:
            await status_msg.edit_text(f"<b>ERROR:</b> <i>Can't connect to Server.</i>\n<code>{error}</code>", parse_mode=enums.ParseMode.HTML)
            return

        # --- THE FIX: Convert directly to Mbps to match the generated image exactly! ---
        dl_mbps = result['download'] / 1_000_000
        ul_mbps = result['upload'] / 1_000_000
        ping_ms = result['ping']
        
        string_speed = (
            f"➲ <b><i>SPEEDTEST INFO</i></b>\n"
            f"┠ <b>Download:</b> <code>{dl_mbps:.2f} Mbps</code>\n"
            f"┠ <b>Upload:</b> <code>{ul_mbps:.2f} Mbps</code>\n"
            f"┠ <b>Ping:</b> <code>{ping_ms} ms</code>\n"
            f"┖ <b>Data Sent/Recv:</b> <code>{_pretty_bytes(result['bytes_sent'])} / {_pretty_bytes(result['bytes_received'])}</code>\n\n"
            f"➲ <b><i>SPEEDTEST SERVER</i></b>\n"
            f"┠ <b>Name:</b> <code>{result['server']['name']}</code>\n"
            f"┠ <b>Location:</b> <code>{result['server']['country']}, {result['server']['cc']}</code>\n"
            f"┖ <b>Sponsor:</b> <code>{result['server']['sponsor']}</code>"
        )

        try:
            if result.get("share"):
                await message.reply_photo(photo=result["share"], caption=string_speed, parse_mode=enums.ParseMode.HTML)
                await status_msg.delete()
            else:
                await status_msg.edit_text(string_speed, parse_mode=enums.ParseMode.HTML)
        except FloodWait: pass

    except Exception as e:
        logger.error(f"Speedtest error: {e}")
        try: await status_message.edit_text(f"❌ An error occurred: {e}")
        except: pass
        
@app.on_message(filters.command(["status"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def status_style_handler(client, message):
    uptime_seconds = int(time.time() - BOT_START_TIME)
    uptime_str = get_readable_time(uptime_seconds)
    mem = psutil.virtual_memory().percent
    cpu = psutil.cpu_percent()
    
    total, used, free = shutil.disk_usage(".")
    disk_free = free / (1024**3)
    
    active_count = 0
    queue_list = []
    
    for uid, tasks in ACTIVE_PROCESSES.items():
        for t_id, info in tasks.items():
            active_count += 1
            src = info.get("source_title", "Source")
            dst = info.get("dest_title_name", "Destination")
            queue_list.append(f"• {src} → {dst}")
    
    watcher_count = await db.db.watchers.count_documents({})
    queue_text = "\n".join(queue_list) if queue_list else "😴 No active downloads."

    msg = (
        f"<b>🔰 SYSTEM DASHBOARD</b>\n\n"
        f"<blockquote>"
        f"⏱ <b>Uptime:</b> <code>{uptime_str}</code>\n"
        f"🧠 <b>RAM:</b> <code>{mem}%</code>  │  ⚙️ <b>CPU:</b> <code>{cpu}%</code> \n"
        f"💿 <b>Disk Free:</b> <code>{disk_free:.1f} GB</code> \n\n"
        f"👀 <b>Live Watchers:</b> <code>{watcher_count}</code> running\n"
        f"📉 <b>Active Downloads ({active_count})</b>\n"
        f"{queue_text}"
        f"</blockquote>"
    )
    try:
        await message.reply(msg, quote=True, parse_mode=enums.ParseMode.HTML)
    except FloodWait as e:
        logger.warning(f"Silently blocked /status reply due to FloodWait: {e.value}s")
    
@app.on_message(filters.command(["botstats"]) & filters.user(ADMINS))
async def bot_stats_handler(client: Client, message: Message):
    try:
        wait = await message.reply("<b>📊 Generating detailed stats...</b>", parse_mode=enums.ParseMode.HTML)
    except FloodWait as e:
        logger.warning(f"Silently blocked /botstats init due to FloodWait: {e.value}s")
        return

    total_users = await db.total_users_count()
    all_users_cursor = await db.get_all_users()
    
    logged_in_list = []
    async for user in all_users_cursor:
        if user.get("session"):
            user_id = user['id']
            name = user.get("name") or f"User:{user_id}"
            user_tasks = ACTIVE_PROCESSES.get(user_id, {})
            
            if user_tasks:
                task_details = []
                for t_id, info in user_tasks.items():
                    src = info.get("source_title", "Source")
                    dst = info.get("dest_title", "Dest")
                    tot = info.get("total", 0)
                    curr = info.get("current", 0)
                    start_t = info.get("started", time.time())
                    
                    percent = (curr / tot * 100) if tot > 0 else 0
                    
                    elapsed = time.time() - start_t
                    eta_str = "Calculating..."
                    if curr > 0 and elapsed > 0:
                        eta_str = get_readable_time(int(((tot - curr) / (curr / elapsed))))

                    task_details.append(
                        f"      └ 🏃 {src} → {info.get('dest_title_name', 'Destination')}"
                    )
                    
                tasks_str = "\n" + "\n".join(task_details)
                logged_in_list.append(f"• <b>{name}</b> [<code>{user_id}</code>]{tasks_str}")
            else:
                logged_in_list.append(f"• <b>{name}</b> [<code>{user_id}</code>] (IDLE 😴)")

    logged_in_text = "\n\n".join(logged_in_list) if logged_in_list else "No users logged in."
    stats_msg = (
        "<b>📊 DETAILED BOT STATISTICS</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n"
        "<blockquote expandable>\n"
        f"👥 <b>Total Users:</b> <code>{total_users}</code>\n"
        f"🔑 <b>Logged-in Users:</b> <code>{len(logged_in_list)}</code>\n\n"
        f"📝 <b>User & Task Breakdown:</b>\n\n{logged_in_text}\n"
        "</blockquote>"
    )
    try:
        await wait.edit(stats_msg, parse_mode=enums.ParseMode.HTML)
    except FloodWait:
        pass # UI rate-limited, safely ignore

# ==============================================================================
# --- SOS SYSTEM STATS COMMAND ---
# ==============================================================================

def generate_sos_text(m_down=0, m_up=0, m_total=0, month_name=""):
    def make_bar(percent, length=12):
        filled = int((percent / 100) * length)
        filled = max(0, min(length, filled))
        return f"[{'◙' * filled}{'◘' * (length - filled)}]"

    try:
        with open("/etc/os-release") as f:
            os_info = dict(line.strip().split("=", 1) for line in f if "=" in line)
        os_name = os_info.get("PRETTY_NAME", f'"{platform.system()} {platform.release()}"').strip('"')
    except Exception:
        os_name = f"{platform.system()} {platform.release()}"

    host = socket.gethostname()
    kernel = platform.uname().release
    
    os_uptime_seconds = time.time() - psutil.boot_time()
    os_uptime = get_readable_time(os_uptime_seconds)
    
    try:
        b_uptime = time.time() - BOT_START_TIME
    except NameError:
        b_uptime = os_uptime_seconds
    bot_uptime = get_readable_time(b_uptime)

    try:
        pkg_count = subprocess.check_output("dpkg-query -f '.\\n' -W | wc -l", shell=True).decode().strip()
        pkg_str = f"{pkg_count} (dpkg)"
    except Exception:
        pkg_str = "Unknown"
    shell = os.environ.get('SHELL', 'bash')

    try:
        with open("/proc/cpuinfo") as f:
            cpu_name = [line.split(":")[1].strip() for line in f if "model name" in line][0]
    except Exception:
        cpu_name = platform.processor() or "Unknown Processor"
    
    cpu_percent = psutil.cpu_percent(interval=0.2)
    cpu_cores = psutil.cpu_count(logical=False) or 0
    cpu_logical = psutil.cpu_count(logical=True) or 0
    
    freq = psutil.cpu_freq()
    freq_str = f"{round(freq.current)} MHz" if freq and getattr(freq, 'current', None) else "Disabled"

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage('/')

    net = psutil.net_io_counters()
    down_bw = net.bytes_recv
    up_bw = net.bytes_sent
    total_bw = down_bw + up_bw

    try:
        with open("/etc/timezone") as f:
            tz = f.read().strip()
    except Exception:
        tz = "UTC"

    return (
        f"<b>🖥 SYSTEM STATISTICS</b>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬\n"
        f"<blockquote expandable>\n"
        f"<b>OS:</b> <code>{os_name}</code>\n"
        f"<b>Host:</b> <code>{host}</code>\n"
        f"<b>Kernel:</b> <code>{kernel}</code>\n"
        f"<b>Uptime:</b> <code>{os_uptime}</code>\n"
        f"<b>Packages:</b> <code>{pkg_str}</code>\n"
        f"<b>Shell:</b> <code>{shell}</code>\n"
        f"<b>CPU:</b> <code>{cpu_name}</code>\n\n"
        
        f"<b>SERVER AREA:</b> <code>{tz}</code>\n"
        f"<b>BOT UPTIME :</b> <code>{bot_uptime}</code>\n\n"
        
        f"「 <b>DISK</b> 」\n"
        f"<code>{make_bar(disk.percent)}</code> | {disk.percent}%\n"
        f"Available : <code>{_pretty_bytes(disk.free)}</code>\n"
        f"Used      : <code>{_pretty_bytes(disk.used)}</code> of <code>{_pretty_bytes(disk.total)}</code>\n\n"
        
        f"「 <b>CPU</b> 」\n"
        f"<code>{make_bar(cpu_percent)}</code> | {cpu_percent}%\n"
        f"Cores     : <code>{cpu_cores}</code>\n"
        f"Logical   : <code>{cpu_logical}</code>\n"
        f"Frequency : <code>{freq_str}</code>\n\n"
        
        f"「 <b>MEMORY</b> 」\n"
        f"<code>{make_bar(mem.percent)}</code> | {mem.percent}%\n"
        f"Available : <code>{_pretty_bytes(mem.available)}</code>\n"
        f"Used      : <code>{_pretty_bytes(mem.used)}</code> of <code>{_pretty_bytes(mem.total)}</code>\n\n"
        
        f"「 <b>SWAP</b> 」\n"
        f"Total     : <code>{_pretty_bytes(swap.total) if swap.total > 0 else 'Not Set'}</code>\n"
        f"Used      : <code>{_pretty_bytes(swap.used) if swap.total > 0 else 'Not Set'}</code>\n\n"
        
        f"「 <b>CURRENT BOOT BANDWIDTH</b> 」\n"
        f"Download  : <code>{_pretty_bytes(down_bw)}</code>\n"
        f"Upload    : <code>{_pretty_bytes(up_bw)}</code>\n"
        f"Boot Total: <code>{_pretty_bytes(total_bw)}</code>\n\n"
        
        f"「 <b>MONTHLY BANDWIDTH ({month_name})</b> 」\n"
        f"Downloaded: <code>{_pretty_bytes(m_down)}</code>\n"
        f"Uploaded  : <code>{_pretty_bytes(m_up)}</code>\n"
        f"Total Used: <code>{_pretty_bytes(m_total)} / 10.00 TB</code>\n"
        f"</blockquote>\n"
        f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬"
    )

@app.on_message(filters.command(["sos"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def sos_handler(client: Client, message: Message):
    try:
        status_msg = await message.reply("<i>Fetching System Stats...</i>", parse_mode=enums.ParseMode.HTML)
    except FloodWait as e:
        return logger.warning(f"Silently blocked /sos init due to FloodWait: {e.value}s")
        
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_sos"),
            InlineKeyboardButton("❌ Cancel", callback_data="close_sos")
        ]
    ])
    try:
        m_down, m_up, m_total, month_name = await db.get_monthly_bandwidth()
        text = await asyncio.to_thread(generate_sos_text, m_down, m_up, m_total, month_name)
        await status_msg.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)
    except FloodWait: pass
    except Exception as e:
        try: await status_msg.edit_text(f"❌ Error fetching system stats: {e}")
        except: pass

@app.on_callback_query(filters.regex("^refresh_sos$"))
async def refresh_sos_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.from_user.id not in ADMINS and callback_query.from_user.id not in SUDOS:
        return await callback_query.answer("❌ Admins only.", show_alert=True)
        
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="refresh_sos"),
            InlineKeyboardButton("❌ Cancel", callback_data="close_sos")
        ]
    ])
    try:
        m_down, m_up, m_total, month_name = await db.get_monthly_bandwidth()
        text = await asyncio.to_thread(generate_sos_text, m_down, m_up, m_total, month_name)
        await callback_query.message.edit_text(text, parse_mode=enums.ParseMode.HTML, reply_markup=keyboard)
        await callback_query.answer("✅ System Stats Refreshed!")
    except Exception:
        await callback_query.answer("⚠️ Stats are exactly the same or an error occurred.")

@app.on_callback_query(filters.regex("^close_sos$"))
async def close_sos_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.from_user.id not in ADMINS and callback_query.from_user.id not in SUDOS:
        return await callback_query.answer("❌ Admins only.", show_alert=True)
    await callback_query.message.delete()
    await callback_query.answer()
        
# ==============================================================================
# --- LOGIN / LOGOUT (async login handler inserted) ---
# ==============================================================================

@app.on_message(filters.private & ~filters.forwarded & filters.command(["logout"]))
async def logout_cmd(client, message):
    user_id = message.from_user.id
    
    if not await db.is_user_exist(user_id):
        return await message.reply_text("You are not logged in.")
        
    user_session = await db.get_session(user_id)
    if not user_session:
        return await message.reply_text("You are not currently logged in. Nothing to log out of!")

    # 🎛 Create the Inline Confirmation Buttons
    buttons = [
        [InlineKeyboardButton("✅ Yes, Logout", callback_data="confirm_logout")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_logout")]
    ]

    await message.reply(
        "⚠️ **Confirm Logout**\n\n"
        "Are you sure you want to log out? This will terminate your session and stop any active live watchers you have running.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex("^cancel_logout$"))
async def cancel_logout_cb(client, query):
    cancel_logout_text = (
        "✅ **Logout Cancelled!**\n\n"
        "**What does this mean?**\n"
        "Your Telegram session remains securely linked to the bot's database. \n\n"
        "🔒 **Security Note:** Because you did not log out, your active `/watch` monitors will continue running seamlessly in the background without interruption."
    )
    try: await query.message.edit(cancel_logout_text)
    except Exception: pass
    try: await query.answer("Session kept active.", show_alert=False)
    except Exception: pass

@app.on_callback_query(filters.regex("^confirm_logout$"))
async def confirm_logout_cb(client, query):
    user_id = query.from_user.id
    
    try: await query.message.edit("📡 **Connecting to Telegram to terminate session...**")
    except Exception: pass

    session_string = await db.get_session(user_id)
    api_id = await db.get_api_id(user_id)
    api_hash = await db.get_api_hash(user_id)

    if session_string:
        user_client = None
        try:
            use_api_id = int(api_id) if api_id else API_ID
            use_api_hash = api_hash if api_hash else API_HASH
            
            user_client = Client(
                ":memory:", 
                session_string=session_string, 
                api_id=use_api_id, 
                api_hash=use_api_hash,
                no_updates=True
            )
            
            await user_client.connect()
            
            try:
                await user_client.log_out()
                try: await query.message.edit("✅ **Session successfully removed from Telegram Devices.**")
                except Exception: pass
            except Exception as e:
                if "terminated" in str(e) or "Connection" in str(e):
                    try: await query.message.edit("✅ **Session terminated successfully.**")
                    except Exception: pass
                else:
                    raise e
            
        except AuthKeyUnregistered:
            try: await query.message.edit("⚠️ **Session was already invalid.** Cleaning local database...")
            except Exception: pass
        except Exception as e:
            logger.warning(f"Remote logout warning for {user_id}: {e}")
            try: await query.message.edit("✅ **Local session cleared.** (Remote session might already be gone)")
            except Exception: pass
        finally:
            try:
                if user_client and user_client.is_connected:
                    await user_client.disconnect()
            except Exception as e:
                logger.debug(f"Logout disconnect cleanup failed for {user_id}: {e}")

    # Shut down the running Pyrogram client if it's currently actively listening
    runtime_client = USER_CLIENTS.pop(user_id, None)
    if runtime_client:
        try:
            await runtime_client.stop()
        except Exception: pass

    # 🟢 Cancel all active batch tasks in memory
    user_tasks = list(ACTIVE_PROCESSES.get(user_id, {}).keys())
    for tid in user_tasks:
        CANCEL_FLAGS[tid] = True
    batch_temp.IS_BATCH[user_id] = True

    # 🟢 Wipe auto-resume tasks from the database so they don't resurrect
    try:
        await db.db.active_tasks.delete_many({"user_id": user_id})
    except Exception:
        pass

    # Clear the database
    await db.set_session(user_id, session=None)
    await db.set_api_id(user_id, api_id=None)
    await db.set_api_hash(user_id, api_hash=None)
    
    try: await query.message.reply("**Logout Complete** ♦\n(You are now disconnected. All active batch tasks have been cleanly cancelled.)")
    except Exception: pass
    try: await query.answer()
    except Exception: pass

from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyromod.exceptions import ListenerStopped

@app.on_callback_query(filters.regex("^cancel_login$"))
async def cancel_login_cb(client, query):
    user_id = query.from_user.id
    
    # Attempt to kill the Pyromod .ask() listener instantly
    try:
        if hasattr(client, "cancel_listener"):
            client.cancel_listener(user_id)
        elif hasattr(client, "listen") and hasattr(client.listen, "cancel"):
            client.listen.cancel(user_id)
    except Exception:
        pass
        
    cancel_login_text = (
        "<b>❌ Login Process Aborted</b>\n\n"
        "<i>What happened?</i>\n"
        "You stopped the login setup. I have stopped waiting for your phone number or OTP. Your account remains completely safe, and no data was saved to the database.\n\n"
        "<i>What next?</i>\n"
        "You can continue using public bot features, or send <code>/login</code> whenever you are ready to try linking your account again."
    )
    try: await query.message.edit(cancel_login_text, parse_mode=enums.ParseMode.HTML)
    except Exception: pass
    try: await query.answer("Login Cancelled", show_alert=False)
    except Exception: pass
    
@app.on_message(filters.private & ~filters.forwarded & filters.command(["login"]))
async def login_handler(bot: Client, message: Message):
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        
    user_data = await db.get_session(message.from_user.id)
    if user_data is not None:
        await message.reply("⚠️ **You are already logged in!**\nPlease run `/logout` first if you want to switch accounts.")
        return  
        
    user_id = int(message.from_user.id)
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_login")]])
    client_auth = None

    try:
        # --- API CREDENTIALS ---
        if API_ID != 0 and API_HASH:
            await message.reply("🔑 **Specific API ID and HASH found in variables. Using them automatically...**")
            api_id, api_hash = API_ID, API_HASH
        else:
            api_id_msg = await bot.ask(user_id, "<b>Send Your API ID.</b>", filters=filters.text, timeout=300, reply_markup=cancel_kb)
            if api_id_msg.text.startswith('/'): return await api_id_msg.reply('<b>Process cancelled!</b>')
            try:
                api_id = int(api_id_msg.text)
                if api_id < 1000000 or api_id > 99999999:
                    return await api_id_msg.reply("**❌ Invalid API ID**\n\nPlease start again with /login.", quote=True)
            except ValueError:
                return await api_id_msg.reply("**❌ API ID must be a number!** Start over with /login.", quote=True)
            
            api_hash_msg = await bot.ask(user_id, "**Now Send Me Your API HASH**", filters=filters.text, timeout=300, reply_markup=cancel_kb)
            if api_hash_msg.text.startswith('/'): return await api_hash_msg.reply('<b>Process cancelled!</b>')
            api_hash = api_hash_msg.text.strip()
            
            if not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
                return await api_hash_msg.reply("**❌ Invalid API HASH (Must be 32 Hex Characters)**\n\nPlease start again with /login.", quote=True)

        # --- PHONE NUMBER ---
        login_text = (
            "🔐 **Login Process Initiated**\n\n"
            "Please send your **Phone Number** in international format.\n"
            "Example: `+1234567890`\n\n"
            "🛡️ *Your session is stored securely locally.*"
        )
        phone_number_msg = await bot.ask(chat_id=user_id, text=login_text, filters=filters.text, timeout=300, reply_markup=cancel_kb)
        if phone_number_msg.text.startswith('/'): return await phone_number_msg.reply('<b>Process cancelled!</b>')
        
        phone_number = phone_number_msg.text.strip()
        if not re.fullmatch(r"\+\d{8,15}", phone_number):
            return await phone_number_msg.reply('❌ **Invalid phone number format.** Use international format (e.g., +1234567890).')
        
        # --- CONNECT TO TELEGRAM ---
        client_auth = Client(":memory:", api_id=api_id, api_hash=api_hash)
        await client_auth.connect()
        await phone_number_msg.reply("🔄 **Sending OTP request to Telegram...**")
        
        try:
            code = await client_auth.send_code(phone_number)
        except PhoneNumberInvalid:
            await phone_number_msg.reply('❌ **Phone Number is invalid!** Start over with /login.')
            await client_auth.disconnect()
            return
            
        # --- OTP RETRY LOOP ---
        while True:
            phone_code_msg = await bot.ask(
                user_id, 
                "Please check for an OTP in your official Telegram account. If you got it, send OTP here after reading the below format. \n\nIf OTP is `12345`, **please send it as** `1 2 3 4 5`.", 
                filters=filters.text, 
                timeout=300, 
                reply_markup=cancel_kb
            )
            
            if phone_code_msg.text.startswith('/'):
                await client_auth.disconnect()
                return await phone_code_msg.reply('<b>Process cancelled!</b>')
                
            raw_code = phone_code_msg.text.strip()
            
            # Catch the Telegram expiration instantly without the hacking explanation
            if raw_code.isdigit() and len(raw_code) >= 4:
                await phone_code_msg.reply("❌ **You sent the code without spaces!**\nTelegram has expired your code. You must run `/login` again to get a new code, and remember to use spaces (e.g., `1 2 3 4 5`).")
                await client_auth.disconnect()
                return
                
            phone_code = raw_code.replace(" ", "")
            
            try:
                await client_auth.sign_in(phone_number, code.phone_code_hash, phone_code)
                break # Success! Exit the OTP loop.
                
            except PhoneCodeInvalid:
                await phone_code_msg.reply('❌ **OTP is incorrect!** Please double-check the code and try again (with spaces).')
                continue # Loops back to ask for OTP again!
                
            except PhoneCodeExpired:
                await phone_code_msg.reply('⏳ **OTP Expired!** The official Telegram API only keeps auth codes valid for 5 minutes. Please run /login again to get a new code.')
                await client_auth.disconnect()
                return
                
            except SessionPasswordNeeded:
                # --- 2FA RETRY LOOP ---
                while True:
                    two_step_msg = await bot.ask(user_id, '**🔒 Account is protected by 2FA. Please enter your Two-Step Verification Password:**', filters=filters.text, timeout=300, reply_markup=cancel_kb)
                    
                    if two_step_msg.text.startswith('/'):
                        await client_auth.disconnect()
                        return await two_step_msg.reply('<b>Process cancelled!</b>')
                        
                    password = two_step_msg.text
                    try:
                        await client_auth.check_password(password=password)
                        break # Success! Exit 2FA loop.
                    except PasswordHashInvalid:
                        await two_step_msg.reply('❌ **Incorrect Password!** Please try again.')
                        continue # Loops back to ask for 2FA again!
                break # Break out of outer OTP loop since we solved 2FA

        # --- SUCCESSFUL LOGIN ---
        string_session = await client_auth.export_session_string()
        await client_auth.disconnect()
        
        if len(string_session) < SESSION_STRING_SIZE:
            return await bot.send_message(user_id, '❌ **Fatal Error:** Invalid session string generated.')
            
        is_prem = False
        first_name = "User"
        try:
            uclient = Client(":memory:", session_string=string_session, api_id=api_id, api_hash=api_hash)
            await uclient.connect()
            me = await uclient.get_me()
            is_prem = getattr(me, "is_premium", False)
            first_name = me.first_name or "User"
            try: await uclient.disconnect()
            except: pass
        except Exception:
            pass
            
        await db.set_session(user_id, session=string_session)
        await db.set_api_id(user_id, api_id=api_id)
        await db.set_api_hash(user_id, api_hash=api_hash)
        
        prem_text = "⭐ <b>Telegram Premium:</b> <code>Active (4GB Uploads Enabled)</code>" if is_prem else "🔹 <b>Account Type:</b> <code>Standard (2GB Upload Limit)</code>"

        success_msg = (
            f"✅ <b>Account Login Successful!</b>\n\n"
            f"👤 <b>Logged in as:</b> <code>{first_name}</code>\n"
            f"{prem_text}\n\n"
            f"<i>If you encounter any AUTH KEY errors later, run /logout and /login again.</i>"
        )
        await bot.send_message(user_id, success_msg, parse_mode=enums.ParseMode.HTML)

    # --- ERROR HANDLERS ---
    except ListenerStopped:
        # Silently caught when Cancel button is pressed
        if client_auth and client_auth.is_connected:
            try: await client_auth.disconnect()
            except: pass
        return
        
    except asyncio.TimeoutError:
        # 5 Minute Limit Reached
        timeout_msg = (
            "⏱ **Login Session Timed Out!**\n\n"
            "**Why did this happen?**\n"
            "You took longer than 5 minutes to reply to a prompt. To save server RAM and maintain security, the bot automatically closed the login listener.\n\n"
            "🔄 **Fix:** Please gather your API ID, Hash, and Phone Number, and send `/login` to start fresh."
        )
        await bot.send_message(user_id, timeout_msg)
        if client_auth and client_auth.is_connected:
            try: await client_auth.disconnect()
            except: pass
        return
        
    except Exception as e:
        await bot.send_message(user_id, f"<b>❌ ERROR IN LOGIN:</b> `{e}`", parse_mode=enums.ParseMode.HTML)
        if client_auth and client_auth.is_connected:
            try: await client_auth.disconnect()
            except: pass

# ==============================================================================
# --- BROADCAST ---
# ==============================================================================

async def broadcast_messages(user_id, message):
    start_time = time.time()
    try:
        await USER_FLOOD_LOCKS[user_id].wait_if_locked()
        await message.copy(chat_id=user_id)
        elapsed = time.time() - start_time
        await asyncio.sleep(max(0, 1.5 - elapsed)) 
        return True, "Success"
    except FloodWait as e:
        if e.value > 60:
            return False, "Error"
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
        return await broadcast_messages(user_id, message)
    except InputUserDeactivated:
        await db.delete_user(int(user_id))
        return False, "Deleted"
    except UserIsBlocked:
        await db.delete_user(int(user_id))
        return False, "Blocked"
    except PeerIdInvalid:
        await db.delete_user(int(user_id))
        return False, "Error"
    except Exception as e:
        logger.error(f"Broadcast completely failed for user {user_id}: {e}", exc_info=True)
        return False, "Error"

@app.on_message(filters.command("broadcast") & filters.user(ADMINS) & filters.reply)
async def broadcast(bot, message):
    users = await db.get_all_users()
    b_msg = message.reply_to_message
    if not b_msg:
        try:
            return await message.reply_text(
                "❌ **How to Broadcast:**\n\n"
                "1. Send the message you want to broadcast (text, photo, or video).\n"
                "2. **Reply** to that specific message with `/broadcast`.\n\n"
                "The bot will then copy that message and send it to every user in the database."
            )
        except FloodWait: return
        
    try:
        sts = await message.reply_text(text='Broadcasting your messages...')
    except FloodWait as e:
        return logger.warning(f"Silently blocked broadcast init due to FloodWait: {e.value}s")
    start_time = time.time()
    total_users = await db.total_users_count()
    done = 0
    blocked = 0
    deleted = 0
    failed = 0
    success = 0
    async for user in users:
        if 'id' in user:
            pti, sh = await broadcast_messages(int(user['id']), b_msg)
            if pti:
                success += 1
            elif pti == False:
                if sh == "Blocked":
                    blocked += 1
                elif sh == "Deleted":
                    deleted += 1
                elif sh == "Error":
                    failed += 1
            done += 1
            if not done % 20:
                await sts.edit(f"Broadcast in progress:\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nSuccess: {success}\nBlocked: {blocked}\nDeleted: {deleted}")
        else:
            done += 1
            failed += 1
            if not done % 20:
                await sts.edit(f"Broadcast in progress:\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nSuccess: {success}\nBlocked: {blocked}\nDeleted: {deleted}")

    time_taken = str(datetime.timedelta(seconds=int(time.time()-start_time)))
    await sts.edit(f"Broadcast Completed:\nCompleted in {time_taken} seconds.\n\nTotal Users {total_users}\nCompleted: {done} / {total_users}\nSuccess: {success}\nBlocked: {blocked}\nDeleted: {deleted}")

# ==============================================================================
# --- WATCHER SETUP WIZARD ---
# ==============================================================================

@app.on_message(filters.command(["watch"]) & filters.private)
async def watch_setup(client: Client, message: Message):
    user_id = message.from_user.id
    if len(message.command) < 2:
        try:
            return await message.reply(
                "❌ **How to set up a Watcher:**\n\n"
                "This command tells the bot to monitor a channel, group, or PM and auto-forward new messages instantly.\n\n"
                "**Examples:**\n"
                "• Public Channel: `/watch https://t.me/channelname`\n"
                "• Private Chat: `/watch https://t.me/c/1234567890/1`\n"
                "• Bot/User PM: `/watch https://t.me/username/123` *(No @ symbol!)*\n"
                "• Specific Topic: `/watch https://t.me/channelname/5`"
            )
        except FloodWait: return
    
    link_text = message.command[1]
    try:
        wait_msg = await message.reply("🔎 **Analyzing Source...**", quote=True)
    except FloodWait as e:
        logger.warning(f"Silently blocked /watch init due to FloodWait: {e.value}s")
        return
        
    is_restricted, status_text = await check_link_restriction(user_id, link_text)
    try: await wait_msg.delete()
    except Exception: pass

    if is_restricted is None:
        return await message.reply(status_text, quote=True)
    
    source_thread_id = None
    clean_text = link_text.replace("https://", "").replace("http://", "").replace("t.me/", "").replace("c/", "").split("?")[0]
    parts = clean_text.strip("/").split("/")
    if len(parts) >= 3 and parts[1].isdigit():
         source_thread_id = int(parts[1])
    
    PENDING_TASKS[user_id] = {
        "mode": "WATCHER", 
        "link": link_text,
        "source_thread_id": source_thread_id,
        "is_restricted": is_restricted,
        "status": "waiting_choice"
    }
    
    buttons = [
        [InlineKeyboardButton("📂 Send to DM (Here)", callback_data="dest_dm")],
        [InlineKeyboardButton("📢 Send to Channel/Group", callback_data="dest_custom")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_setup")]
    ]
    
    await message.reply(
        f"👀 **Watcher Setup**\n\n"
        f"{status_text}\n"
        f"{(f'🔹 **Source Topic:** `{source_thread_id}` detected!' if source_thread_id else '')}\n\n"
        "**Where should new messages go?**",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )

@app.on_message(filters.command(["unwatch"]) & filters.private)
async def unwatch_handler(client, message):
    if len(message.command) not in (2, 3):
        try:
            return await message.reply(
                "❌ **How to stop a Live Watcher:**\n\n"
                "You need to provide the **Source ID** (the chat the bot is copying *from*).\n"
                "*(You can easily find this ID by sending the `/watchers` command!)*\n\n"
                "**Examples:**\n"
                "• Stop a channel/group: `/unwatch -100123456789`\n"
                "• Stop a specific topic: `/unwatch -100123456789 5`"
            )
        except FloodWait: return
    try:
        source_id = int(message.command[1])
        source_thread = int(message.command[2]) if len(message.command) == 3 else None
        user_id = message.from_user.id

        query = {"user_id": user_id, "source_id": source_id}
        if source_thread is not None:
            query["source_thread"] = source_thread
        else:
            query["$or"] = [{"source_thread": None}, {"source_thread": {"$exists": False}}]
            
        watcher = await db.db.watchers.find_one(query)

        if watcher and await db.remove_watcher(user_id, source_id, source_thread):
            stats = watcher.get("stats", {})
            cancelled_tasks = 0
            if user_id in ACTIVE_PROCESSES:
                for tid, info in list(ACTIVE_PROCESSES[user_id].items()):
                    if info.get("is_watcher") and info.get("source_id") == source_id:
                        CANCEL_FLAGS[tid] = True
                        cancelled_tasks += 1

            msg = (
                f"🛑 **Watcher Stopped & Removed!**\n\n"
                f"📊 **Final Session Statistics:**\n"
                f"├ 📡 **Total Detected:** `{stats.get('detected', 0)}`\n"
                f"├ ✅ **Successfully Processed:** `{stats.get('success', 0)}`\n"
                f"├ ⏭ **Skipped (Filtered):** `{stats.get('skipped', 0)}`\n"
                f"└ ❌ **Failed:** `{stats.get('failed', 0)}`"
            )
            if cancelled_tasks > 0:
                msg += f"\n\n🛑 Also intercepted and cancelled `{cancelled_tasks}` ongoing downloads from this watcher."
            try: await message.reply(msg)
            except FloodWait: pass
        else:
            try: await message.reply("⚠️ **Watcher not found.**\nMake sure you are providing the **Source ID** (where messages come *from*), not the Destination ID!")
            except FloodWait: pass
    except Exception as e:
        logger.error(f"Unwatch failed with input {message.command}: {e}", exc_info=True)
        try: await message.reply("❌ Invalid ID or Database Error.")
        except FloodWait: pass

@app.on_message(filters.command(["watchers"]) & filters.private)
async def list_watchers(client, message):
    user_id = message.from_user.id
    
    if user_id in ADMINS:
        cursor = await db.get_all_watchers()
    else:
        cursor = await db.get_user_watchers(user_id)
        
    user_watchers = await cursor.to_list(length=100)
    if not user_watchers:
        try: return await message.reply("💤 **No active watchers found.**")
        except FloodWait: return
    
    text = "**👀 Active Watchers Manager**\n\nSelect a watcher to remove:"
    buttons = []
    
    for w in user_watchers:
        src_id = w['source_id']
        src_display = w.get('source_title') or str(src_id)
        
        dest_id = w['dest_id']
        dst_display = w.get('dest_title') or str(dest_id)
        
        # 🟢 AUTO-RESOLVE DESTINATION NAME IF IT'S JUST A NUMERIC ID
        if dst_display == str(dest_id) or str(dst_display).lstrip("-").isdigit():
            if dest_id == user_id:
                dst_display = "Saved Messages"
            else:
                try:
                    chat_info = await client.get_chat(dest_id)
                    dst_display = chat_info.title or chat_info.first_name or "Target Chat"
                    # Silently update DB so the name stays cached
                    await db.db.watchers.update_one({"_id": w["_id"]}, {"$set": {"dest_title": dst_display}})
                except:
                    pass
        
        if len(src_display) > 15: src_display = src_display[:12] + "..."
        if len(dst_display) > 15: dst_display = dst_display[:12] + "..."
        
        label = f"{src_display} ➔ {dst_display}"
        
        wid = str(w["_id"]) # Get unique DB ID
        callback = f"unwatch_{wid}"
        
        buttons.append([InlineKeyboardButton(f"🗑 {label}", callback_data=callback)])
    
    buttons.append([InlineKeyboardButton("🧨 Cancel All Watchers", callback_data="unwatch_all")])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_menu")])
    
    try: await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
    except FloodWait as e: logger.warning(f"Blocked /watchers list due to FloodWait: {e.value}s")
    
@app.on_callback_query(filters.regex("^unwatch_"))
async def unwatch_callback(client, query):
    if query.data == "unwatch_all":
        user_id = query.from_user.id
        
        # Calculate combined stats before deleting
        cursor = db.db.watchers.find({'user_id': int(user_id)})
        t_det = t_suc = t_skip = t_fail = 0
        async for w in cursor:
            s = w.get("stats", {})
            t_det += s.get("detected", 0)
            t_suc += s.get("success", 0)
            t_skip += s.get("skipped", 0)
            t_fail += s.get("failed", 0)
            
        result = await db.db.watchers.delete_many({'user_id': int(user_id)})
        
        # Intercept and Cancel ALL Active Watcher Downloads
        cancelled_tasks = 0
        if user_id in ACTIVE_PROCESSES:
            for tid, info in list(ACTIVE_PROCESSES[user_id].items()):
                if info.get("is_watcher"):
                    CANCEL_FLAGS[tid] = True
                    cancelled_tasks += 1
                    
        msg = (
            f"🧨 **ALL Watchers Stopped & Removed!**\n"
            f"🗑 Removed `{result.deleted_count}` active watchers.\n\n"
            f"📊 **Combined Final Statistics:**\n"
            f"├ 📡 **Total Detected:** `{t_det}`\n"
            f"├ ✅ **Successfully Processed:** `{t_suc}`\n"
            f"├ ⏭ **Skipped (Filtered):** `{t_skip}`\n"
            f"└ ❌ **Failed:** `{t_fail}`"
        )
        if cancelled_tasks > 0:
            msg += f"\n\n🛑 Intercepted and Cancelled `{cancelled_tasks}` active watcher downloads."
        try: await query.message.edit(msg)
        except Exception: pass
        return

    # --- Delete Single Route by Unique MongoDB ID ---
    wid = query.data.split("_")[1]
    
    try:
        watcher = await db.db.watchers.find_one({"_id": ObjectId(wid)})
    except Exception:
        try: return await query.answer("Watcher not found or invalid ID.", show_alert=True)
        except Exception: return
        
    if not watcher:
        try: return await query.answer("Watcher already removed.", show_alert=True)
        except Exception: return

    owner_id = watcher["user_id"]
    source_id = watcher["source_id"]
    src_name = watcher.get('source_title') or str(source_id)
    dest_name = watcher.get('dest_title') or str(watcher.get('dest_id'))
    stats = watcher.get("stats", {})

    # Delete JUST this specific route!
    await db.db.watchers.delete_one({"_id": ObjectId(wid)})

    # Intercept and Cancel ongoing downloads tied to this source
    cancelled_tasks = 0
    if owner_id in ACTIVE_PROCESSES:
        for tid, info in list(ACTIVE_PROCESSES[owner_id].items()):
            if info.get("is_watcher") and info.get("source_id") == source_id:
                CANCEL_FLAGS[tid] = True
                cancelled_tasks += 1

    msg = (
        f"🛑 **Watcher Stopped & Removed!**\n\n"
        f"**From:** `{src_name}`\n"
        f"**To:** `{dest_name}`\n\n"
        f"📊 **Final Session Statistics:**\n"
        f"├ 📡 **Total Detected:** `{stats.get('detected', 0)}`\n"
        f"├ ✅ **Successfully Processed:** `{stats.get('success', 0)}`\n"
        f"├ ⏭ **Skipped (Filtered):** `{stats.get('skipped', 0)}`\n"
        f"└ ❌ **Failed:** `{stats.get('failed', 0)}`"
    )
    if cancelled_tasks > 0:
        msg += f"\n\n🛑 **Cancelled `{cancelled_tasks}` active ongoing downloads** originating from this watcher."
        
    try: await query.message.edit(msg)
    except Exception: pass

# ==============================================================================
# --- CORE: receive links / start tasks / processing / cancel checks ---
# ==============================================================================

@app.on_message((filters.text | filters.caption) & filters.private & ~filters.command(ALL_COMMANDS))
async def save(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in PENDING_TASKS:
        if PENDING_TASKS[user_id].get("status") == "waiting_id":
            await process_custom_destination(client, message)
            return
        if PENDING_TASKS[user_id].get("status") == "waiting_speed_input": # <<< FIX
            await process_speed_input(client, message)
            return

    link_text = message.text or message.caption
    if not link_text or "https://t.me/" not in link_text:
        return

    try:
        wait_msg = await message.reply("🔎 **Analyzing Link...**", quote=True)
    except FloodWait as e:
        logger.warning(f"Silently blocked link analysis due to FloodWait: {e.value}s")
        return

    is_restricted, status_text = await check_link_restriction(user_id, link_text)
    try: await wait_msg.delete()
    except Exception: pass

    if is_restricted is None:
        return await message.reply(status_text, quote=True)

    PENDING_TASKS[user_id] = {
        "link": link_text, 
        "status": "waiting_choice",
        "is_restricted": is_restricted 
    }
    
    buttons = [
        [InlineKeyboardButton("📂 Send to DM (Here)", callback_data="dest_dm")],
        [InlineKeyboardButton("📢 Send to Channel/Group", callback_data="dest_custom")],
        [InlineKeyboardButton("❌ Cancel Setup", callback_data="cancel_setup")]
    ]
    
    await message.reply(
        f"✨ **Link Detected!**\n\n"
        f"{status_text}\n\n"
        "Where should I send the files?",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )

@app.on_message(filters.command(["chats"]) & filters.private)
async def chats_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    args = message.command[1:] if len(message.command) > 1 else []
    
    # 🟢 1. CLEAN WARNING IF NOT LOGGED IN / NO SESSION IN DB
    session_str = await db.get_session(user_id)
    if not session_str:
        not_logged_in_text = (
            "<b>⚠️ TELEGRAM SESSION NOT CONNECTED</b>\n\n"
            "<blockquote expandable>"
            "You cannot fetch your chat IDs because your personal Telegram account is not linked to this bot yet!\n\n"
            "💡 <b>How to Connect:</b>\n"
            "• <b>Via Telegram:</b> Send <code>/login</code> and follow the prompts.\n"
            "• <b>Via Web Portal:</b> Open <b>Settings</b> and enter your phone number to sign in.\n\n"
            "<i>Once connected, send <code>/chats</code> again to explore all your chat IDs.</i>"
            "</blockquote>"
        )
        return await message.reply(not_logged_in_text, parse_mode=enums.ParseMode.HTML)

    # 🟢 2. BEAUTIFUL HELP MENU (WHEN RUN WITHOUT ARGUMENTS)
    if not args:
        help_menu = (
            "<b>💬 CHATS & CHANNELS EXPLORER</b>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬\n"
            "<blockquote expandable>"
            "Quickly extract chat, channel, group, and bot IDs associated with your logged-in account. You can copy these IDs directly to use in <code>/watch</code> or <code>/dl</code>!\n\n"
            "<b>📑 COMMAND ARGUMENTS</b>\n"
            "• <code>/chats all</code> - <i>Fetch all categories</i>\n"
            "• <code>/chats group</code> - <i>Fetch Groups & Supergroups only</i>\n"
            "• <code>/chats channel</code> - <i>Fetch Broadcast Channels only</i>\n"
            "• <code>/chats bot</code> - <i>Fetch Direct Bots only</i>\n"
            "• <code>/chats user</code> - <i>Fetch Direct User PMs only</i>\n\n"
            "🛡 <b>Flood Protection:</b> Results are delivered in pages of 50 with an automated 6-second interval between pages."
            "</blockquote>\n"
            "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬"
        )
        return await message.reply(help_menu, parse_mode=enums.ParseMode.HTML)

    filter_type = args[0].lower()
    if filter_type not in ["all", "user", "bot", "group", "channel"]:
        return await message.reply("❌ **Invalid argument.** Please use: `all`, `group`, `channel`, `bot`, or `user`.")

    uclient = USER_CLIENTS.get(user_id)
    
    # 🟢 3. DYNAMIC WAKE-UP FOR INTERRUPTED SESSIONS
    if not uclient or not uclient.is_connected:
        status = await message.reply("🔄 <b>Connecting your Telegram session...</b>", parse_mode=enums.ParseMode.HTML)
        try:
            api_id = await db.get_api_id(user_id) or API_ID
            api_hash = await db.get_api_hash(user_id) or API_HASH
            uclient = Client(f"User_{user_id}", session_string=session_str, api_id=api_id, api_hash=api_hash, workers=4, ipv6=False)
            uclient.add_handler(MessageHandler(user_watcher_handler, filters.channel | filters.group | filters.private))
            await uclient.start()
            USER_CLIENTS[user_id] = uclient
            await status.edit("🔄 <b>Session Active! Fetching your dialogs...</b>", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            return await status.edit(f"❌ <b>Session Expired or Broken:</b> <code>{e}</code>\nPlease run <code>/logout</code> and <code>/login</code> again.")
    else:
        status = await message.reply("🔄 <b>Fetching your chats... Please wait</b>", parse_mode=enums.ParseMode.HTML)

    users, groups, channels, bots = [], [], [], []
    
    try:
        async for d in uclient.get_dialogs():
            name = html.escape(d.chat.title or d.chat.first_name or "Unknown")
            cid = d.chat.id
            line = f"• <b>{name}</b> │ <code>{cid}</code>"
            
            if d.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                groups.append(line)
            elif d.chat.type == enums.ChatType.CHANNEL:
                channels.append(line)
            elif d.chat.type == enums.ChatType.BOT:
                bots.append(line)
            elif d.chat.type == enums.ChatType.PRIVATE:
                users.append(line)
    except Exception as e:
        return await status.edit(f"❌ <b>Error reading dialogs:</b> <code>{e}</code>", parse_mode=enums.ParseMode.HTML)
        
    await status.delete()

    def chunk_list(items, chunk_size=50):
        return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
        
    categories = []
    if filter_type in ["all", "group"]: categories.append(("👥 Groups & Supergroups List", "👥", groups))
    if filter_type in ["all", "channel"]: categories.append(("📢 Channels List", "📢", channels))
    if filter_type in ["all", "bot"]: categories.append(("🤖 Telegram Bots List", "🤖", bots))
    if filter_type in ["all", "user"]: categories.append(("👤 Users List", "👤", users))

    found_any = False
    for title, emoji, items in categories:
        if not items:
            continue
        found_any = True
        chunks = chunk_list(items, 50)
        total_pages = len(chunks)
        
        for i, chunk in enumerate(chunks, 1):
            text = (
                f"<b>{emoji} {title} (Page {i}/{total_pages})</b>\n"
                f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬\n"
                f"<blockquote expandable>\n"
                + "\n".join(chunk) +
                f"\n</blockquote>\n"
                f"▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬"
            )
            await message.reply(text, parse_mode=enums.ParseMode.HTML)
            if i < total_pages or len(categories) > 1:
                await asyncio.sleep(6) # Safe 6-second rate limit pause

    if not found_any:
        await message.reply(f"⚠️ No active dialogs found matching filter: <b>{filter_type}</b>", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.command(["dl"]) & (filters.private | filters.group))
async def dl_handler(client: Client, message: Message):
    user_id = message.from_user.id
    link_text = ""
    
    reply = message.reply_to_message
    if reply and (reply.text or reply.caption):
        link_text = reply.text or reply.caption
    elif len(message.command) > 1:
        link_text = message.text.split(None, 1)[1]
        
    if not link_text or "https://t.me/" not in link_text:
        try:
            await message.reply_text(
                "❌ **How to use the Downloader:**\n\n"
                "Use this command to download or forward files from any Telegram link.\n\n"
                "**Examples:**\n"
                "• Channel File: `/dl https://t.me/channel/100`\n"
                "• Batch Files: `/dl https://t.me/channel/101 - 120`\n"
                "• Bot/User PM: `/dl https://t.me/username/123` *(No @ symbol!)*\n"
                "• Quick Reply: Just **reply** to any message containing a link with `/dl`"
            )
        except FloodWait: pass
        return

    try:
        wait_msg = await message.reply("🔎 **Analyzing Link...**", quote=True)
    except FloodWait as e:
        logger.warning(f"Silently blocked /dl init due to FloodWait: {e.value}s")
        return

    is_restricted, status_text = await check_link_restriction(user_id, link_text)
    try: await wait_msg.delete()
    except Exception: pass

    if is_restricted is None:
        return await message.reply(status_text, quote=True)

    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        dest_title = message.chat.title or "This Group"
        if message.message_thread_id:
            dest_title += await get_topic_title(client, message.chat.id, message.message_thread_id)
            
        PENDING_TASKS[user_id] = {
            "link": link_text,
            "dest_chat_id": message.chat.id,
            "dest_thread_id": message.message_thread_id,
            "dest_title": dest_title,
            "status": "waiting_speed_choice", # <<< FIX
            "is_restricted": is_restricted
        }
        await message.reply(f"✨ **Link Analyzed!**\n{status_text}", quote=True)
        await ask_for_speed(message)
        return

    PENDING_TASKS[user_id] = {
        "link": link_text, 
        "status": "waiting_choice",
        "is_restricted": is_restricted
    }
    
    buttons = [
        [InlineKeyboardButton("📂 Send to DM (Here)", callback_data="dest_dm")],
        [InlineKeyboardButton("📢 Send to Channel/Group", callback_data="dest_custom")],
        [InlineKeyboardButton("❌ Cancel Setup", callback_data="cancel_setup")] 
    ]
    
    await message.reply(
        f"✨ **Link Detected!**\n\n"
        f"{status_text}\n\n"
        "I am ready to process this content. Please tell me where you want the files sent:",
        reply_markup=InlineKeyboardMarkup(buttons),
        quote=True
    )
    
@app.on_callback_query(filters.regex("^dest_"))
async def destination_callback(client: Client, query):
    user_id = query.from_user.id
    if user_id not in PENDING_TASKS:
        try: return await query.answer("❌ Task expired. Send link again.", show_alert=True)
        except Exception: return
    choice = query.data
    
    if choice == "dest_dm":
        PENDING_TASKS[user_id]["dest_chat_id"] = user_id
        PENDING_TASKS[user_id]["dest_thread_id"] = None
        PENDING_TASKS[user_id]["dest_title"] = "Saved Messages"
        PENDING_TASKS[user_id]["status"] = "waiting_speed_choice" # <<< FIX
        await ask_for_speed(query)
    elif choice == "dest_custom":
        PENDING_TASKS[user_id]["status"] = "waiting_id"
        buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_setup")]]
        try:
            await query.message.edit_text(
                "📝 **Send the Target Chat ID**\n\n"
                "Examples:\n"
                "• Channel/Group: `-100123456789`\n"
                "• Specific Topic: `-100123456789/5`\n\n"
                "⚠️ __Make sure I am an admin in that chat!__",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
        except Exception: pass

def get_filter_keyboard(current_types):
    buttons = []
    row = []
    for t in ALL_MSG_TYPES:
        icon = "✅" if t in current_types else "❌"
        row.append(InlineKeyboardButton(f"{icon} {t}", callback_data=f"filter_toggle:{t}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([
        InlineKeyboardButton("✅ Select All", callback_data="filter_all"), 
        InlineKeyboardButton("❌ Clear All", callback_data="filter_none")
    ])
    buttons.append([InlineKeyboardButton("🚀 Proceed / Save Setup", callback_data="filter_start")])
    buttons.append([InlineKeyboardButton("🛑 Cancel Setup", callback_data="cancel_setup")])
    return InlineKeyboardMarkup(buttons)

async def show_filter_menu(message_or_query, user_id):
    task_data = PENDING_TASKS.get(user_id)
    if not task_data:
        return

    if "allowed_types" not in task_data:
        task_data["allowed_types"] = ["Video", "Document"]
    task_data["status"] = "waiting_filter"

    kb = get_filter_keyboard(task_data["allowed_types"])
    text = "🎛 **Content Filter**\n\nSelect the media types you want to forward or download.\n*(Default: Strictly Videos & Documents)*"

    if hasattr(message_or_query, "message") and hasattr(message_or_query, "data"):
        await message_or_query.message.edit_text(text, reply_markup=kb)
    else:
        await message_or_query.reply(text, reply_markup=kb, quote=True)

@app.on_callback_query(filters.regex("^filter_toggle:(.+)"))
async def filter_toggle_cb(client, query):
    user_id = query.from_user.id
    if user_id not in PENDING_TASKS: return await query.answer("Expired.", show_alert=True)
    mtype = query.data.split(":")[1]
    allowed = PENDING_TASKS[user_id].get("allowed_types", ["Video", "Document"])
    if mtype in allowed: allowed.remove(mtype)
    else: allowed.append(mtype)
    PENDING_TASKS[user_id]["allowed_types"] = allowed
    try: await query.message.edit_reply_markup(get_filter_keyboard(allowed))
    except: pass
    await query.answer()

@app.on_callback_query(filters.regex("^filter_all$"))
async def filter_all_cb(client, query):
    user_id = query.from_user.id
    if user_id not in PENDING_TASKS: return await query.answer("Expired.", show_alert=True)
    PENDING_TASKS[user_id]["allowed_types"] = ALL_MSG_TYPES.copy()
    try: await query.message.edit_reply_markup(get_filter_keyboard(ALL_MSG_TYPES))
    except: pass
    await query.answer()

@app.on_callback_query(filters.regex("^filter_none$"))
async def filter_none_cb(client, query):
    user_id = query.from_user.id
    if user_id not in PENDING_TASKS: return await query.answer("Expired.", show_alert=True)
    PENDING_TASKS[user_id]["allowed_types"] = []
    try: await query.message.edit_reply_markup(get_filter_keyboard([]))
    except: pass
    await query.answer()

@app.on_callback_query(filters.regex("^filter_start$"))
async def filter_start_cb(client, query):
    user_id = query.from_user.id
    if user_id not in PENDING_TASKS: return await query.answer("Expired.", show_alert=True)
    
    task_data = PENDING_TASKS.pop(user_id)
    allowed_types = task_data.get("allowed_types", ["Video", "Document"])
    
    if not allowed_types: 
        PENDING_TASKS[user_id] = task_data 
        return await query.answer("❌ Select at least one type!", show_alert=True)
        
    delay = task_data.get("delay", 3)
    if task_data.get("mode") == "WATCHER":
        await finalize_watcher_setup(client, query.message, task_data, delay, user_id=user_id)
    else:
        await start_task_final(client, query.message, task_data, delay, user_id=user_id)

async def process_custom_destination(client: Client, message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    try:
        if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self:
            await message.reply_to_message.delete()
    except Exception:
        pass

    try:
        dest_chat_id, dest_thread_id = _parse_chat_target(text)

        try:
            chat = await client.get_chat(dest_chat_id)
            title = chat.title or chat.first_name or "Target Chat"
            if dest_thread_id: 
                title += await get_topic_title(client, dest_chat_id, dest_thread_id)

            bot_member = await client.get_chat_member(chat.id, "me")
            if bot_member.status not in [enums.ChatMemberStatus.ADMINISTRATOR, enums.ChatMemberStatus.OWNER]:
                await message.reply(
                    "❌ **Destination Error:** I am not an admin in that chat!\n\n"
                    "Please add me to the destination chat/channel, promote me to an **Admin**, and then send the ID again."
                )
                return
            
            # --- NEW: ACTIVE DESTINATION TEST ---
            try:
                test_msg = await client.send_message(
                    chat_id=dest_chat_id,
                    text="🔄 Testing Destination Accessibility...\n*(This message will self-destruct)*",
                    message_thread_id=dest_thread_id
                )
                await asyncio.sleep(2)
                await test_msg.delete()
            except Exception as e:
                await message.reply(f"❌ **Destination Write Error:** I am an admin, but I cannot send messages to that specific topic/chat! (Check topic permissions)\nError: `{e}`")
                return
            # ------------------------------------
            
        except Exception as e:
            await message.reply(f"❌ **Could not access Destination.**\nMake sure I am added to the chat and given admin rights.\nError: `{e}`")
            return

        PENDING_TASKS[user_id]["dest_chat_id"] = chat.id
        PENDING_TASKS[user_id]["dest_thread_id"] = dest_thread_id
        PENDING_TASKS[user_id]["dest_title"] = title
        PENDING_TASKS[user_id]["status"] = "waiting_speed_choice" # <<< FIX
        await ask_for_speed(message)

    except ValueError:
        await message.reply("❌ Invalid ID format. Send `-100...`, `-100.../5`, `@username`, or a `t.me` link.")

async def ask_for_speed(message_or_query):
    user_id = message_or_query.from_user.id
    task_data = PENDING_TASKS.get(user_id, {})
    mode = task_data.get("mode")

    buttons = []
    if mode == "WATCHER":
        buttons.append([InlineKeyboardButton("⚡ Instant (0s)", callback_data="speed_0")])
        buttons.append([InlineKeyboardButton("⏳ Default (3s)", callback_data="speed_3")])
    else:
        buttons.append([InlineKeyboardButton("⚡ Default (3s)", callback_data="speed_3")])
        
    buttons.append([InlineKeyboardButton("⚙️ Manual Speed", callback_data="speed_manual")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_setup")])
    
    text = "**🚀 Select Forwarding Speed**\n\nHow fast should I process messages?"

    if hasattr(message_or_query, "message") and hasattr(message_or_query, "data"):
        await message_or_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await message_or_query.reply(text, reply_markup=InlineKeyboardMarkup(buttons), quote=True)

@app.on_callback_query(filters.regex("^speed_"))
async def speed_callback(client: Client, query):
    user_id = query.from_user.id
    if user_id not in PENDING_TASKS:
        try: await query.answer("❌ Task expired.", show_alert=True)
        except Exception: pass
        return
    
    choice = query.data
    task_data = PENDING_TASKS[user_id]
    
    if choice == "speed_manual":
        PENDING_TASKS[user_id]["status"] = "waiting_speed_input"
        try:
            await query.message.edit(
                "⏱ **Enter Delay (Seconds)**\n\n"
                "Every time a new message arrives, I will wait this long before forwarding it.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_setup")]])
            )
        except Exception: pass
        return

    if choice == "speed_0":
        PENDING_TASKS[user_id]["delay"] = 0
        await show_filter_menu(query, user_id)
        return
        
    if choice in ["speed_3", "speed_default"]:
        PENDING_TASKS[user_id]["delay"] = 3
        await show_filter_menu(query, user_id)
        return

async def process_speed_input(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text.isdigit(): return await message.reply("❌ Numbers only.")
    
    delay = max(0, min(int(text), 3600)) 
    if user_id in PENDING_TASKS:
        PENDING_TASKS[user_id]["delay"] = delay
        await show_filter_menu(message, user_id)

async def finalize_watcher_setup(client, message, data, delay, user_id=None):
    if user_id is None:
        user_id = message.from_user.id if message.from_user else message.chat.id
    src_link = data["link"]

    user_session = await db.get_session(user_id)
    
    api_id = await db.get_api_id(user_id) or API_ID
    api_hash = await db.get_api_hash(user_id) or API_HASH

    if user_session and user_id not in USER_CLIENTS:
        status_msg = await message.reply("🔄 **Starting your Listener Client...**")
        try:
            u_api = api_id or API_ID
            u_hash = api_hash or API_HASH

            new_client = Client(
                f"User_{user_id}",
                session_string=user_session,
                api_id=u_api,
                api_hash=u_hash,
                workers=4,
                ipv6=False
            )
            new_client.add_handler(MessageHandler(user_watcher_handler, filters.channel | filters.group | filters.private))
            await new_client.start()
            USER_CLIENTS[user_id] = new_client
            await status_msg.delete()
        except Exception as e:
            return await status_msg.edit(f"❌ **Session Error:** `{e}`\n\nTry /logout and /login again.")

    # Use user session if available, otherwise default to the Bot!
    user_client = USER_CLIENTS.get(user_id, app) 
    
    try:
        parsed = _parse_source_link(src_link)
        source_id = parsed["chat_id"]
        source_title = "Unknown Source"

        if parsed["kind"] == "invite":
            try: await user_client.join_chat(parsed["join_target"])
            except: pass
            chat = await user_client.get_chat(parsed["join_target"])
            source_id = chat.id
            source_title = chat.title or str(source_id)

        elif parsed["kind"] == "public":
            try:
                # Try Bot first
                chat = await app.get_chat(parsed["join_target"])
            except Exception:
                # Fallback to User Session
                chat = await user_client.get_chat(parsed["join_target"])
                
            source_id = chat.id
            source_title = chat.title or str(source_id)
            try: await user_client.join_chat(parsed["join_target"])
            except: pass

        else:
            chat = await user_client.get_chat(source_id)
            source_title = chat.title or str(source_id)

        if parsed.get("topic_id"):
            source_title += await get_topic_title(user_client, source_id, parsed["topic_id"])

    except Exception as e:
        is_pub = parsed.get("kind") == "public" if 'parsed' in locals() else False
        reason = "The public username might be incorrect/banned." if is_pub else "I am not inside this private chat."
        return await message.reply(
            f"❌ **Could not access Source.**\n\n"
            f"You are not logged in, and I cannot read this chat directly.\n"
            f"💡 **Reason:** {reason}\n"
            f"**Fix:** Please use `/login` to route through your own account, OR add me to the source chat (**as an Admin for Channels, or a normal Member for Groups**).\n\n"
            f"**Error:** `{e}`"
        )

    # 🟢 Fetch the latest message ID to serve as our starting point
    last_msg_id = 0
    try:
        async for m in user_client.get_chat_history(source_id, limit=1):
            last_msg_id = m.id
    except Exception:
        try:
            async for m in app.get_chat_history(source_id, limit=1):
                last_msg_id = m.id
        except: pass

    await db.add_watcher(
        user_id=user_id,
        source_id=source_id,
        dest_id=data.get("dest_chat_id"),
        source_thread=data.get("source_thread_id"),
        dest_thread=data.get("dest_thread_id"),
        delay=delay,
        is_restricted=data["is_restricted"],
        source_title=source_title,
        dest_title=data.get("dest_title", str(data.get("dest_chat_id"))),
        allowed_types=data.get("allowed_types"),
        dashboard_chat=message.chat.id,
        dashboard_msg=message.id,
        last_msg_id=last_msg_id   # 🟢 PASS THE ID HERE
    )

    initial_text = (
        f"👀 **Live Watcher Dashboard**\n\n"
        f"**Source:** `{source_title}`\n"
        f"**Destination:** `{data.get('dest_title', str(data.get('dest_chat_id')))}`\n"
        f"**Delay:** `{delay}s` | **Restricted:** `{'Yes' if data['is_restricted'] else 'No'}`\n"
        f"**Filters:** `{', '.join(data.get('allowed_types', []))}`\n\n"
        f"📊 **Session Statistics:**\n"
        f"├ 📡 **Detected:** `0`\n"
        f"├ ✅ **Success:** `0`\n"
        f"├ ⏭ **Skipped:** `0`\n"
        f"└ ❌ **Failed:** `0`\n\n"
        f"*(Updates dynamically every 30s)*"
    )
    
    try:
        if hasattr(message, "edit_text"):
            await message.edit_text(initial_text)
        else:
            new_msg = await message.reply(initial_text)
            # Failsafe if it couldn't edit
            await db.db.watchers.update_one(
                {
                    "user_id": user_id, 
                    "source_id": source_id, 
                    "source_thread": data.get("source_thread_id"),
                    "dest_id": data.get("dest_chat_id"),
                    "dest_thread": data.get("dest_thread_id")
                },
                {"$set": {"dashboard_chat": new_msg.chat.id, "dashboard_msg": new_msg.id}}
            )
    except Exception:
        pass
    
# ==============================================================================
# --- NEW ROBUSTNESS HELPERS ---
# ==============================================================================

async def send_log(text):
    if not LOG_CHANNEL:
        return
    try:
        chat_id, topic_id = parse_chat_topic(LOG_CHANNEL)
        await app.send_message(chat_id, text, message_thread_id=topic_id, disable_web_page_preview=True)
    except Exception as e:
        print(f"❌ Failed to send log: {e}")

# --- SMART LOG ROUTING ---
USER_LOG_CACHE = {}

async def get_fallback_log_chat(client_to_use, client_identifier, bot_id=None):
    """Finds the best available scratchpad chat. Tries LOG_CHANNEL -> ADMINS -> Bot's PM."""
    if client_identifier in USER_LOG_CACHE:
        return USER_LOG_CACHE[client_identifier]
        
    targets = []
    if LOG_CHANNEL:
        c_id, t_id = parse_chat_topic(LOG_CHANNEL)
        targets.append((c_id, t_id))
        
    for admin in ADMINS:
        targets.append((admin, None))
        
    # 🟢 If all else fails, use the DM between the User and the Bot!
    if bot_id and client_to_use != app:
        targets.append((bot_id, None))
    else:
        targets.append(("me", None)) # Failsafe for bot itself
    
    for c_id, t_id in targets:
        try:
            # 🟢 Pre-flight check to ensure write access BEFORE doing heavy uploads
            msg = await client_to_use.send_message(chat_id=c_id, text="🔄", message_thread_id=t_id)
            await msg.delete()
            USER_LOG_CACHE[client_identifier] = (c_id, t_id)
            return c_id, t_id
        except Exception:
            continue
            
    return "me", None

async def check_disk_space():
    try:
        total, used, free = shutil.disk_usage(".")
        free_mb = free / (1024 * 1024)
        if free_mb < 500: 
            return False
        return True
    except:
        return True

async def cleanup_watchdog():
    while True:
        await asyncio.sleep(600) 
        try:
            download_path = Path(f"./downloads_{INSTANCE_ID}")
            if not download_path.exists(): continue
            
            current_time = time.time()
            max_age = 2 * 60 * 60 
            
            for user_folder in download_path.iterdir():
                if not user_folder.is_dir():
                    continue

                for task_folder in user_folder.iterdir():
                    if not task_folder.is_dir():
                        continue

                    folder_time = task_folder.stat().st_mtime
                    if (current_time - folder_time) > max_age:
                        shutil.rmtree(task_folder)
                        await send_log(f"🧹 **Auto-Cleanup:** Deleted stuck folder `{task_folder.name}` (Older than 2h)")
        except Exception as e:
            logger.error(f"Watchdog Error: {e}", exc_info=True)
            
async def start_task_final(client: Client, message_context: Message, task_data: dict, delay: int, user_id: int):
    if not await check_disk_space():
        msg = "⚠️ **Server Busy:** Disk is almost full. Please wait for other tasks to finish."
        if isinstance(message_context, Message):
             await message_context.reply(msg, quote=True)
        await send_log("🚨 **Critical:** Disk Space Low (<500MB). Tasks rejected.")
        return

    if user_id not in ADMINS and batch_temp.ACTIVE_TASKS[user_id] >= MAX_CONCURRENT_TASKS_PER_USER:
        TASK_QUEUE[user_id].append({
            "client": client,
            "message": message_context,
            "data": dict(task_data), 
            "delay": delay
        })
        position = len(TASK_QUEUE[user_id])
        await message_context.reply(
            f"⏳ **Added to Queue:** Position #{position}\n"
            f"Task will start automatically when your current tasks finish.",
            quote=True
        )
        return

    task_uuid = uuid.uuid4().hex
    dest = task_data.get("dest_title", "Direct Message")
    
    batch_temp.ACTIVE_TASKS[user_id] += 1
    batch_temp.IS_BATCH[user_id] = False

    start_msg = f"✅ **Task Started!**\nDestination: `{dest}`\nSpeed: `{delay}s` delay\nTask ID: `{task_uuid[:8]}`"
    try:
        if isinstance(message_context, Message):
            if message_context.from_user.is_bot:
                await message_context.edit(start_msg)
            else:
                await message_context.reply(start_msg)
    except: pass

    if user_id not in ACTIVE_PROCESSES:
        ACTIVE_PROCESSES[user_id] = {}
    ACTIVE_PROCESSES[user_id][task_uuid] = {
        "user": task_data.get("dest_title", f"User({user_id})"),
        "dest_title_name": task_data.get("dest_title", "Direct Message"), 
        "item": task_data.get("link", "Unknown"),
        "started": time.time()
    }
    
    is_restricted = task_data.get("is_restricted", False)
    task_snapshot = dict(task_data)

    asyncio.create_task(
        process_links_logic(
            client,
            message_context,
            task_snapshot["link"],
            dest_chat_id=task_snapshot.get("dest_chat_id"),
            dest_thread_id=task_snapshot.get("dest_thread_id"),
            dest_title=dest,
            delay=delay,
            acc_user_id=user_id,
            task_uuid=task_uuid,
            is_restricted=is_restricted,
            allowed_types=task_snapshot.get("allowed_types")
        )
    )   

async def handle_public_unrestricted(client: Client, acc, chatid: str, msgid: int, dest_chat_id, dest_thread_id, user_id, task_uuid, filter_thread_id, allowed_types):
    """Isolated function ONLY for Public Unrestricted links. Returns SUCCESS, SKIPPED, or FAILED."""

    try:
        # Uses native string resolution directly!
        fetcher = acc if acc else client
        msg = await fetcher.get_messages(chatid, msgid)
    except Exception as e:
        logger.error(f"Failed to fetch msg {msgid}: {e}")
        return "FAILED"

    if not msg or msg.empty: 
        return "SKIPPED"

    # Strict Topic Filtering
    if filter_thread_id is not None:
        actual_thread = getattr(msg, "message_thread_id", None)
        if actual_thread is None:
            if getattr(msg, "reply_to_top_message_id", None) != filter_thread_id and getattr(msg, "reply_to_message_id", None) != filter_thread_id and msg.id != filter_thread_id:
                return "SKIPPED"
        elif actual_thread != filter_thread_id:
            return "SKIPPED"

    # Strict Type Filtering
    msg_type = get_message_type(msg)
    if not msg_type or (allowed_types and msg_type not in allowed_types):
        return "SKIPPED"

    if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)):
        return "FAILED"

    # Fast-Forwarding
    if msg_type == "Text":
        try:
            await client.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return "SUCCESS"
        except Exception as e:
            logger.warning(f"Bot text forward failed: {e}. Falling back to User Session...")
            try:
                await acc.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                return "SUCCESS"
            except Exception as e2:
                logger.error(f"User Session text forward failed for {msgid}: {e2}")
                return "FAILED"

    try:
        await USER_FLOOD_LOCKS[user_id].wait_if_locked()
        try:
            # Bot copies using raw chatid
            copy_res = await client.copy_message(chat_id=dest_chat_id, from_chat_id=chatid, message_id=msgid, message_thread_id=dest_thread_id)
            if not copy_res: 
                raise ValueError("Bot copy returned None (Bot lacks direct access)")
            return "SUCCESS"
        except Exception as e1:
            logger.warning(f"Bot copy failed for {msgid}: {e1}. Falling back to User Session...")
            # Fallback to User Session copying
            try:
                owner_copy = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=chatid, message_id=msgid, message_thread_id=dest_thread_id)
                return "SUCCESS" if owner_copy else "FAILED"
            except Exception as e2:
                logger.error(f"User Session copy also failed for {msgid}: {e2}")
                return "FAILED"
    except FloodWait as e:
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
        try:
            owner_copy = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=chatid, message_id=msgid, message_thread_id=dest_thread_id)
            return "SUCCESS" if owner_copy else "FAILED"
        except Exception as e3:
            logger.error(f"FloodWait recovery copy failed for {msgid}: {e3}")
            return "FAILED"
    except Exception as e:
        logger.error(f"Total copy failure for {msgid}: {e}")
        return "FAILED"

async def process_links_logic(client: Client, message: Message, text: str, dest_chat_id=None, dest_thread_id=None, dest_title="Direct Message", delay=3, acc_user_id=None, task_uuid=None, is_restricted=False, allowed_types=None, resume_from_id=None, saved_source_title=None):
    user_id = acc_user_id or (message.from_user.id if message and message.from_user else 0)
    
    # 🟢 Resolve Real User Name (Not Bot Name)
    real_user_name = None
    if message and message.from_user and not message.from_user.is_bot:
        real_user_name = message.from_user.first_name
        if message.from_user.last_name:
            real_user_name += f" {message.from_user.last_name}"
            
    if not real_user_name and user_id:
        user_doc = await db.col.find_one({"id": int(user_id)})
        if user_doc and user_doc.get("name") and not str(user_doc.get("name")).startswith("User "):
            real_user_name = user_doc.get("name")
            
    if not real_user_name and user_id:
        try:
            tg_user = await client.get_users(user_id)
            if tg_user:
                real_user_name = tg_user.first_name or "User"
                if tg_user.last_name:
                    real_user_name += f" {tg_user.last_name}"
                await db.col.update_one({"id": int(user_id)}, {"$set": {"name": real_user_name}})
        except Exception:
            real_user_name = "User"
            
    if not real_user_name:
        real_user_name = "User"

    user_mention = f"[{real_user_name}](tg://user?id={user_id})"
    msg_chat_id = message.chat.id if message else user_id
    msg_id = message.id if message else None
    
    if user_id not in ACTIVE_PROCESSES: ACTIVE_PROCESSES[user_id] = {}
    if not task_uuid: task_uuid = uuid.uuid4().hex
    
    ACTIVE_PROCESSES[user_id][task_uuid] = {
        "user": user_mention, 
        "dest_title_name": dest_title,
        "item": text[:50]+"...", 
        "started": time.time()
    }

    if dest_chat_id is None: dest_chat_id = msg_chat_id
    if dest_thread_id is None: dest_thread_id = message.message_thread_id if message else None

    if "t.me/" in text:
        acc = None
        success_count = 0
        failed_count = 0
        skipped_count = 0
        total_count = 0
        status_message = None

        parsed_source = _parse_source_link(text)
        filter_thread_id = parsed_source.get("topic_id")
        msg_id_hint = parsed_source.get("msg_id")

        start_time = time.time()
        source_title = "Unknown Source"

        try:
            was_cancelled = False
            range_match = re.search(r"(\d+)\s*-\s*(\d+)", text)
            if range_match:
                fromID, toID = int(range_match.group(1)), int(range_match.group(2))
            elif msg_id_hint is not None:
                fromID = toID = int(msg_id_hint)
            else:
                if message: return await message.reply("❌ Invalid link format. Send a valid Telegram post link with a message ID.")
                return

            if resume_from_id:
                fromID = resume_from_id

            total_count = max(1, toID - fromID + 1)

            user_data = await db.get_session(user_id)
            acc = None
            is_temp_acc = False
            
            if user_data:
                api_id = await db.get_api_id(user_id) or API_ID
                api_hash = await db.get_api_hash(user_id) or API_HASH
                
                acc = Client(
                    ":memory:", 
                    session_string=user_data, 
                    api_hash=api_hash, 
                    api_id=api_id, 
                    no_updates=True,
                    workers=8,                              # <--- Give it more async threads
                    max_concurrent_transmissions=10,        # <--- NATIVE PARALLEL CHUNKING
                    sleep_threshold=60,
                    ipv6=False
                )
                await acc.start()
                is_temp_acc = True
            
            try:
                source_ref = parsed_source.get("chat_id")
                if source_ref is None:
                    return await message.reply("❌ Could not resolve source chat.")

                # 🟢 Attempt to get the REAL name of the channel
                try:
                    source_chat = await client.get_chat(source_ref)
                    source_title = source_chat.title or source_chat.first_name or str(source_ref)
                    ACTUAL_CHAT_ID = source_chat.id
                except Exception:
                    if acc:
                        try:
                            source_chat = await acc.get_chat(source_ref)
                            source_title = source_chat.title or source_chat.first_name or str(source_ref)
                            ACTUAL_CHAT_ID = source_chat.id
                        except Exception:
                            # Force fallback for public strings if get_chat fails
                            ACTUAL_CHAT_ID = source_ref
                            source_title = str(source_ref)
                    else:
                        ACTUAL_CHAT_ID = source_ref
                        source_title = str(source_ref)
                        
            except Exception as e: 
                if not acc:
                    is_pub = isinstance(source_ref, str) and not str(source_ref).lstrip('-').isdigit()
                    reason = "The public username might be incorrect/banned." if is_pub else "I am not inside this private chat."
                    return await message.reply(
                        f"❌ **Could not access Source.**\n\n"
                        f"You are not logged in, and I cannot read this chat directly.\n"
                        f"💡 **Reason:** {reason}\n"
                        f"**Fix:** Please use `/login` to route through your own account, OR add me to the source chat (**as an Admin for Channels, or a normal Member for Groups**).\n\n"
                        f"**Error:** `{e}`"
                    )
                logger.warning(f"Could not fetch chat title for {source_ref}: {e}")
                ACTUAL_CHAT_ID = source_ref 

            if saved_source_title and source_title == "Unknown Source":
                source_title = saved_source_title

            t_name = ""
            if filter_thread_id:
                fetcher = acc if acc else client
                topic_addon = await get_topic_title(fetcher, ACTUAL_CHAT_ID, filter_thread_id)
                source_title += topic_addon
                t_name = topic_addon.strip(" ()")

            ACTIVE_PROCESSES[user_id][task_uuid].update({"source_title": source_title, "total": total_count, "current": 0})
            
            # 🟢 [DB SAVE] Register task for Auto-Resume with the CORRECT fetched source title
            await db.add_active_task(
                task_uuid=task_uuid, user_id=user_id, link=text, dest_chat_id=dest_chat_id,
                dest_thread_id=dest_thread_id, dest_title=dest_title, delay=delay,
                is_restricted=is_restricted, allowed_types=allowed_types,
                source_title=source_title, current_msg_id=fromID, to_id=toID
            )

            # 🟢 [DETAILED LOGGING] Cleaned up to prevent double Topic IDs!
            log_user_link = f"[{real_user_name}](tg://user?id={user_id})"
            log_dst_display = f"{dest_chat_id}" + (f"/{dest_thread_id}" if dest_thread_id else "")
            
            detailed_log = (
                f"▶️ **Task Started**\n"
                f"**User:** {log_user_link} (`{user_id}`)\n"
                f"**Task:** {source_title} -> {dest_title}\n"
                f"**Link:** {text} -> `{log_dst_display}`"
            )
            await send_log(detailed_log)
            
            status_text_header = f"**Batch Task Started!** 🚀\n"
            inner_header = ""
            if filter_thread_id:
                status_text_header += f"**Filter:** `{t_name} Only` 🎯\n"
                inner_header = f"Filter: {t_name} Only 🎯"

            kwargs_status = {"chat_id": msg_chat_id}
            if msg_id: 
                kwargs_status["reply_to_message_id"] = msg_id
            if message and message.message_thread_id:
                kwargs_status["message_thread_id"] = message.message_thread_id

            if is_restricted:
                status_message = await client.send_message(
                    text=f"⚡ **Initializing Task...**\n{status_text_header}\nSource: {source_title}\nTotal Files: {total_count}",
                    **kwargs_status
                )
            else:
                status_message = await client.send_message(
                    text=f"{status_text_header}\n\n{generate_bar(0)}\n\n"
                    f"**Source:** {source_title}\n**Destination :** {dest_title}\n"
                    f"**Total:** {total_count}\n**Processed:** 0\n**Success:** 0 | **Skipped:** 0\n**Failed:** 0\n**ETA:** ...",
                    **kwargs_status
                )

            last_update_time = time.time()
            # 🟢 Deleted the old hardcoded inner_header line here!

            for index, msgid in enumerate(range(fromID, toID+1), start=1):
                loop_start_time = time.time()
                
                # 🟢 [DB UPDATE] Tick progress so if server crashes, it resumes here
                await db.update_task_progress(task_uuid, msgid)

                if task_uuid in ACTIVE_PROCESSES.get(user_id, {}):
                    ACTIVE_PROCESSES[user_id][task_uuid]["current"] = index

                if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)):
                    was_cancelled = True; break

                # --- ALBUM SKIP LOGIC ---
                if msgid in batch_temp.SKIP_IDS.get(task_uuid, set()):
                    success_count += 1
                    continue 
                # ------------------------

                is_success = False
                task_result = "FAILED"  # 🟢 Failsafe: Prevents UnboundLocalError loop crashes
                try:
                    chatid = ACTUAL_CHAT_ID
                    
                    # 🟢 Rely completely on the universal router built into handle_private!
                    task_result = await handle_private(
                        client, acc, message, chatid, msgid, index, total_count, 
                        status_message, dest_chat_id, dest_thread_id, delay, 
                        user_id, task_uuid, 
                        is_restricted=is_restricted, 
                        header_text=inner_header,
                        filter_thread_id=filter_thread_id, 
                        allowed_types=allowed_types 
                    )
                
                except FloodWait as e:
                    if e.value > 300:
                        print(f"FloodWait too long ({e.value}s). Stopping task.")
                        try: await status_message.edit_text(f"❌ **Task Cancelled automatically**\nReason: FloodWait too long ({e.value}s).")
                        except Exception: pass # Ignore UI crash if it's already rate limited
                        was_cancelled = True
                        break

                    try: 
                        if not is_restricted: await status_message.edit_text(f"⏳ **Rate Limiting Detected**\nSleeping for {e.value} seconds...")
                    except Exception: pass
                    
                    USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5) 
                    await asyncio.sleep(e.value + 5)
                    
                except Exception as e: 
                    logger.error(f"Error processing {msgid} for user {user_id}", exc_info=True)
                    await send_log(f"❌ **Task Error:** Message `{msgid}` failed.\nUser: `{user_id}`\nError: `{e}`")

                # Accurately map results to Skipped vs Failed
                if task_result == "SUCCESS" or task_result is True: 
                    success_count += 1
                    is_success = True
                elif task_result == "SKIPPED": 
                    skipped_count += 1
                    is_success = False
                else: 
                    failed_count += 1
                    is_success = False

                if index < total_count:
                    if is_success:
                        elapsed_time = time.time() - loop_start_time
                        actual_sleep = max(0, delay - elapsed_time)
                        await asyncio.sleep(actual_sleep)
                    else:
                        await asyncio.sleep(0.05)

                if not is_restricted:
                    current_now = time.time()
                    if (current_now - last_update_time >= 30) or index == total_count:
                        elapsed = current_now - start_time
                        percent = (index / total_count) * 100
                        eta_str = get_readable_time(int(((total_count - index) / (index / elapsed)))) if index > 0 else "..."
                        
                        try:
                            await status_message.edit_text(
                                f"{status_text_header}\n\n{generate_bar(percent)}\n\n"
                                f"**Source:** {source_title}\n**Destination :** {dest_title}\n"
                                f"**Total:** {total_count}\n**Processed:** {index}\n"
                                f"**Success:** {success_count} | **Skipped:** {skipped_count}\n"
                                f"**Failed:** {failed_count}\n**ETA:** {eta_str}"
                            )
                            last_update_time = current_now
                        except FloodWait as e:
                            logger.warning(f"Dashboard UI rate-limited. Silently skipping update to protect transfer.")
                            # Push the next UI update check far into the future so it stops spamming
                            last_update_time = current_now + min(e.value, 600)
                        except Exception as e: 
                            logger.debug(f"Failed to edit master dashboard: {e}")
                    
        except Exception as e:
            await send_log(f"❌ **Task Crashed**\nUser: `{user_id}`\nError: `{e}`")

        finally:
            # 🟢 [DB DELETE] Task completed successfully or was explicitly cancelled by user
            await db.remove_active_task(task_uuid)
            
            cleanup_task_memory(user_id, task_uuid)
            batch_temp.SKIP_IDS.pop(task_uuid, None) # Clear RAM
            
            batch_temp.ACTIVE_TASKS[user_id] = max(0, batch_temp.ACTIVE_TASKS.get(user_id, 0) - 1)

            if TASK_QUEUE[user_id]:
                next_item = TASK_QUEUE[user_id].pop(0)
                asyncio.create_task(
                    start_task_final(
                        next_item["client"],
                        next_item["message"],
                        dict(next_item["data"]),
                        next_item["delay"],
                        user_id
                    )
                )

            if acc and is_temp_acc:
                try: await acc.stop()
                except: pass

            duration = time.time() - start_time
            time_taken_str = get_readable_time(int(duration))
            
            if 'was_cancelled' in locals() and was_cancelled:
                header = f"Batch was Cancelled! 🛑 {user_mention} ✨"
            else:
                header = f"Batch was Completed! ✅ {user_mention} ✨"

            final_text = (
                f"{header}\n"
                f"📝 **Task :** {source_title} → {dest_title}\n"
                f"⏱ **Time Taken:** `{time_taken_str}`\n"
                f"📊 **Statistics:**\n"
                f"├ 📥 **Total Requested:** `{total_count}`\n"
                f"├ ✅ **Successful:** `{success_count}`\n"
                f"├ ⏭ **Skipped:** `{skipped_count}`\n"
                f"└ ❌ **Failed:** `{failed_count}`"
            )
            
            try: 
                kwargs_final = {"chat_id": msg_chat_id, "text": final_text}
                if msg_id: kwargs_final["reply_to_message_id"] = msg_id
                await client.send_message(**kwargs_final)
            except: pass
            try: await status_message.delete()
            except: pass

# ==============================================================================
# --- 2. MESSAGE FETCHER & VALIDATOR ---
# ==============================================================================
async def _fetch_and_validate_msg(client, acc, chatid, msgid, user_id, filter_thread_id, allowed_types, task_uuid):
    fetcher = acc if acc else client
    try:
        msg = await fetcher.get_messages(chatid, msgid)
    except Exception:
        return None, None

    if not msg or msg.empty: return None, None

    if filter_thread_id is not None:
        actual_thread = getattr(msg, "message_thread_id", None)
        if actual_thread is None:
            if getattr(msg, "reply_to_top_message_id", None) != filter_thread_id and getattr(msg, "reply_to_message_id", None) != filter_thread_id and msg.id != filter_thread_id:
                return None, None
        elif actual_thread != filter_thread_id:
            return None, None

    msg_type = get_message_type(msg)
    if not msg_type: return None, None
    if allowed_types is not None and msg_type not in allowed_types: return None, None
    if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): return None, None

    return msg, msg_type

# ==============================================================================
# --- 3. THE ROUTER (Replaces handle_private) ---
# ==============================================================================

async def handle_private(client: Client, acc, message: Message, chatid, msgid: int, index: int, total_count: int, status_message: Message, dest_chat_id, dest_thread_id, delay, user_id, task_uuid=None, is_restricted=False, header_text="", filter_thread_id=None, allowed_types=None):
    fetcher = acc if acc else client

    # 1. Determine link type
    is_public = isinstance(chatid, str) and not chatid.lstrip('-').isdigit()
    is_live_watch = (delay == 0 and status_message and "Watcher" in getattr(status_message, "text", ""))

    # 2. Pre-fetch and validate message natively
    msg, msg_type = await _fetch_and_validate_msg(client, acc, chatid, msgid, user_id, filter_thread_id, allowed_types, task_uuid)
    if not msg:
        return "SKIPPED" 

    kwargs = {
        "msg": msg, "msg_type": msg_type, "index": index, "total_count": total_count, 
        "status_message": status_message, "dest_chat_id": dest_chat_id, "dest_thread_id": dest_thread_id,
        "delay": delay, "user_id": user_id, "task_uuid": task_uuid, "header_text": header_text
    }

    # 3. Route the task
    is_content_protected = is_restricted or getattr(msg, "has_protected_content", False) or getattr(msg.chat, "has_protected_content", False)
    
    if not is_content_protected:
        if is_live_watch:
            return await handle_unrestricted_live(client, acc, chatid, msgid, **kwargs)
        elif is_public:
            return await handle_unrestricted_public(client, acc, chatid, msgid, **kwargs)
        else:
            return await handle_unrestricted_private(client, acc, chatid, msgid, **kwargs)
    else:
        if is_live_watch:
            return await handle_restricted_live(client, acc, chatid, msgid, **kwargs)
        elif is_public:
            return await handle_restricted_public(client, acc, chatid, msgid, **kwargs)
        else:
            return await handle_restricted_private(client, acc, chatid, msgid, **kwargs)

# ==============================================================================
# --- 🟢 UNRESTRICTED ROUTES (WITH ALBUM SUPPORT) ---
# ==============================================================================

async def _execute_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, user_id, task_uuid, delay):
    if msg_type == "Text":
        try:
            await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_message, chat_id=dest_chat_id, text=msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return True
        except Exception:
            if acc:
                try:
                    await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_message, chat_id=dest_chat_id, text=msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                    return True
                except: return False
            return False
            
    try:
        await USER_FLOOD_LOCKS[user_id].wait_if_locked()
        
        # Album Logic (Private)
        if msg.media_group_id:
            fetcher = acc if acc else client
            try:
                m_group = await fetcher.get_media_group(chat_id, msgid)
                group_size = len(m_group)
                if task_uuid:
                    for m in m_group: batch_temp.SKIP_IDS[task_uuid].add(m.id)
            except: group_size = 1

            try:
                copy_res = await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.copy_media_group, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            except Exception:
                if acc:
                    copy_res = await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.copy_media_group, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                else: copy_res = False
            
            if copy_res:
                if delay > 0 and group_size > 1: await asyncio.sleep(delay * (group_size - 1))
                return True
            return False

        # Single Copy
        try:
            await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.copy_message, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            return True
        except Exception:
            if acc:
                owner_copy = await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.copy_message, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                return bool(owner_copy)
            return False
    except FloodWait as e:
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
        if acc:
            try:
                await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.copy_message, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                return True
            except: return False
        return False
    except Exception: return False

async def _execute_public_live_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, user_id, task_uuid, delay):
    if msg_type == "Text":
        try:
            await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_message, chat_id=dest_chat_id, text=msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return True
        except Exception:
            if acc:
                try:
                    await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_message, chat_id=dest_chat_id, text=msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                    return True
                except: return False
            return False
            
    try:
        await USER_FLOOD_LOCKS[user_id].wait_if_locked()
        
        # Album Logic (Public)
        if msg.media_group_id:
            try: m_group = await client.get_media_group(chat_id, msgid)
            except:
                if acc:
                    try: m_group = await acc.get_media_group(chat_id, msgid)
                    except: m_group = [msg]
                else: m_group = [msg]
            group_size = len(m_group)
            
            if task_uuid:
                for m in m_group: batch_temp.SKIP_IDS[task_uuid].add(m.id)

            try:
                copy_res = await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.copy_media_group, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                if not copy_res: raise ValueError("Bot copy None")
            except Exception:
                if acc:
                    copy_res = await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.copy_media_group, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                else: copy_res = False
            
            if copy_res:
                if delay > 0 and group_size > 1: await asyncio.sleep(delay * (group_size - 1))
                return True
            return False

        # Single Copy
        try:
            copy_res = await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.copy_message, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            if not copy_res: raise ValueError("Bot copy returned None")
            return True
        except Exception:
            if acc:
                owner_copy = await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.copy_message, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                return bool(owner_copy)
            return False
    except FloodWait as e:
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
        if acc:
            try:
                owner_copy = await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.copy_message, chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                return bool(owner_copy)
            except: return False
        return False
    except Exception: return False

# 1 Public Link
async def handle_unrestricted_public(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, **kwargs):
    return await _execute_public_live_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, kwargs.get("user_id"), kwargs.get("task_uuid"), kwargs.get("delay", 3))

# 2 Pvt link
async def handle_unrestricted_private(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, **kwargs):
    return await _execute_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, kwargs.get("user_id"), kwargs.get("task_uuid"), kwargs.get("delay", 3))

# 3 Live watch
async def handle_unrestricted_live(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, **kwargs):
    return await _execute_public_live_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, kwargs.get("user_id"), kwargs.get("task_uuid"), kwargs.get("delay", 3))

# ==============================================================================
# --- 🔴 RESTRICTED ROUTES ---
# ==============================================================================

# 1 Public Link
async def handle_restricted_public(client, acc, chat_id, msgid, **kwargs):
    return await _execute_restricted_download_upload(client, acc, chat_id, msgid, **kwargs)

# 2 Pvt link
async def handle_restricted_private(client, acc, chat_id, msgid, **kwargs):
    return await _execute_restricted_download_upload(client, acc, chat_id, msgid, **kwargs)

# 3 Live watch
async def handle_restricted_live(client, acc, chat_id, msgid, **kwargs):
    return await _execute_restricted_download_upload(client, acc, chat_id, msgid, **kwargs)

async def build_rich_caption(file_path, msg_type, msg):
    try:
        file_name = "Unknown"
        if msg_type == "Audio" and getattr(msg, "audio", None): file_name = getattr(msg.audio, "file_name", "Audio.m4a")
        elif msg_type == "Video" and getattr(msg, "video", None): file_name = getattr(msg.video, "file_name", "Video.mp4")
        elif getattr(msg, "document", None): file_name = getattr(msg.document, "file_name", "File.dat")
        
        if not file_path or not os.path.exists(file_path):
            return None
            
        size_bytes = os.path.getsize(file_path)
        size_str = _pretty_bytes(size_bytes)
        
        if msg_type == "Audio":
            bitrate_str = "16Bit - 44.1kHz" # Fallback Default
            try:
                cmd = ["mediainfo", "--Inform=Audio;%BitDepth%Bit - %SamplingRate/String%", str(file_path)]
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, _ = await proc.communicate()
                out = stdout.decode().strip()
                if out and "Bit" in out:
                    bitrate_str = out.replace(".1", "").replace(" kHz", "kHz")
            except: pass
            
            return f"<b>{html.escape(file_name)}</b>\n\n🗂 <code>{size_str}</code>\n🎧 <code>{bitrate_str}</code>"
            
        elif msg_type == "Video":
            w = getattr(msg.video, "width", 0) if getattr(msg, "video", None) else 0
            h = getattr(msg.video, "height", 0) if getattr(msg, "video", None) else 0
            dur = getattr(msg.video, "duration", 0) if getattr(msg, "video", None) else 0
            dur_str = f"{dur//60}m{dur%60}s" if dur else "Unknown"
            
            audio_lng = "Unknown"
            sub_lng = "None"
            try:
                cmd = ["mediainfo", "--Inform=General;%Audio_Language_List%|%Text_Language_List%", str(file_path)]
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, _ = await proc.communicate()
                out = stdout.decode().strip().split('|')
                if len(out) == 2:
                    a_list, s_list = out[0].strip(), out[1].strip()
                    # 🟢 FIX: Replace MediaInfo's ' / ' separator with a clean comma
                    if a_list: audio_lng = a_list.replace(" / ", ", ")
                    if s_list: sub_lng = s_list.replace(" / ", ", ")
                elif len(out) == 1 and out[0].strip():
                    audio_lng = out[0].strip().replace(" / ", ", ")
            except: pass
            
            return f"<b>{html.escape(file_name)}</b>\n\n🗂 <code>{size_str}</code> 💎 <code>{w}x{h}</code>\n⏳ <code>{dur_str}</code> 💬 <code>{sub_lng}</code>\n🔊 <code>{audio_lng}</code>"
            
    except Exception as e:
        logger.debug(f"Rich caption generation failed: {e}")
    return None
    
# ==============================================================================
# --- CORE RESTRICTED DOWNLOAD / UPLOAD ENGINE ---
# ==============================================================================

async def _execute_restricted_download_upload(client, acc, chatid, msgid, dest_chat_id, dest_thread_id, msg, msg_type, index, total_count, status_message, delay, user_id, task_uuid, header_text):
    
    if msg_type == "Text":
        try:
            await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_message, chat_id=dest_chat_id, text=msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return True
        except Exception:
            if acc:
                try:
                    await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_message, chat_id=dest_chat_id, text=msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                    return True
                except: return False
            return False

    folder_name = task_uuid if task_uuid else str(getattr(status_message, "id", "dummy"))
    task_folder_path = Path(f"./downloads_{INSTANCE_ID}/{user_id}/{folder_name}/")
    task_folder_path.mkdir(parents=True, exist_ok=True)

    original_filename = "unknown_file"
    if msg.document and msg.document.file_name: original_filename = msg.document.file_name
    elif msg.video and msg.video.file_name: original_filename = msg.video.file_name
    elif msg.audio and msg.audio.file_name: original_filename = msg.audio.file_name
    elif msg_type == "Photo": original_filename = f"{msgid}.jpg"
    elif msg_type == "Voice": original_filename = f"{msgid}.ogg"

    safe_filename = sanitize_filename(original_filename)
    if not safe_filename.strip(): safe_filename = f"{msgid}.dat"
    file_path_to_save = task_folder_path / safe_filename

    # 🟢 [FIX] Wipe previous file's progress so stale numbers NEVER carry over!
    if status_message:
        PROGRESS.pop(f"{status_message.id}:down", None)
        PROGRESS.pop(f"{status_message.id}:up", None)

    down_task = None
    if status_message:
        down_task = asyncio.create_task(downstatus(client, status_message, status_message.chat.id, index, total_count, header_text))
        
    file_path = None
    ph_path = None
    download_success = False

    split_limit = 2000 * 1024 * 1024 
    is_premium = False
    fetcher = acc if acc else client
    try:
        if acc:
            me = acc.me if acc.me else await acc.get_me()
            if me.is_premium: is_premium = True
    except Exception: pass

    try: 
        for attempt in range(3):
            if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): return False
            try:
                msg_fresh = await fetcher.get_messages(chatid, msgid)
                if msg_fresh.empty: return False
                
                file_size = 0
                if msg_fresh.document: file_size = msg_fresh.document.file_size
                elif msg_fresh.video: file_size = msg_fresh.video.file_size
                elif msg_fresh.audio: file_size = msg_fresh.audio.file_size

                if file_size > split_limit:
                    if is_premium and acc:
                        if USER_DOWNLOAD_SEMAPHORES[user_id].locked():
                            try:
                                if status_message: await status_message.edit_text(f"🚀 **Large File ({_pretty_bytes(file_size)})**\n⏳ Waiting in Download Queue...")
                            except FloodWait: pass
                        async with USER_DOWNLOAD_SEMAPHORES[user_id]:
                            file_path = await fetcher.download_media(msg_fresh, file_name=str(file_path_to_save), progress=progress, progress_args=[status_message, "down", task_uuid])
                        if down_task and not down_task.done(): down_task.cancel()
                        
                        try:
                            if status_message: await status_message.edit_text(f"☁️ **Uploading via Premium Session...**")
                        except FloodWait: pass
                        
                        bot_id = client.me.id if getattr(client, "me", None) else int(BOT_TOKEN.split(":")[0])
                        log_chat_id, log_topic_id = await get_fallback_log_chat(acc, user_id, bot_id=bot_id)
                        
                        up_task = asyncio.create_task(upstatus(client, status_message, status_message.chat.id, index, total_count, header_text)) if status_message else None
                        
                        # --- 🟢 RICH CAPTION EXTRACTION ---
                        custom_cap = await build_rich_caption(file_path, msg_type, msg_fresh)
                        if custom_cap:
                            caption = custom_cap
                            caption_entities = None
                            p_mode = enums.ParseMode.HTML
                        else:
                            caption = msg_fresh.caption if getattr(msg_fresh, "caption", None) else ""
                            caption_entities = msg_fresh.caption_entities if getattr(msg_fresh, "caption_entities", None) else None
                            p_mode = None

                        a_dur = getattr(msg_fresh.audio, "duration", 0) if getattr(msg_fresh, "audio", None) else 0
                        a_perf = getattr(msg_fresh.audio, "performer", None) if getattr(msg_fresh, "audio", None) else None
                        a_tit = getattr(msg_fresh.audio, "title", None) if getattr(msg_fresh, "audio", None) else None

                        # 🟢 SMART AUDIO TAG EXTRACTOR: Fixes <unknown> artists!
                        if msg_type == "Audio":
                            if not a_perf or a_perf.lower() in ["unknown", "<unknown>"]:
                                clean_name = os.path.splitext(safe_filename)[0]
                                if " - " in clean_name:
                                    parts = clean_name.split(" - ", 1)
                                    a_perf = parts[0].strip() # Artist is before the dash
                                    if not a_tit or a_tit.lower() in ["unknown", "<unknown>", clean_name.lower()]:
                                        a_tit = parts[1].strip() # Title is after the dash
                                else:
                                    a_perf = "Unknown Artist"
                            if not a_tit or a_tit.lower() in ["unknown", "<unknown>"]:
                                a_tit = os.path.splitext(safe_filename)[0]

                        v_dur = getattr(msg_fresh.video, "duration", 0) if getattr(msg_fresh, "video", None) else 0
                        v_w = getattr(msg_fresh.video, "width", 0) if getattr(msg_fresh, "video", None) else 0
                        v_h = getattr(msg_fresh.video, "height", 0) if getattr(msg_fresh, "video", None) else 0

                        sent_msg = None
                        
                        try:
                            kwargs = {"chat_id": log_chat_id, "caption": caption}
                            if log_topic_id: kwargs["message_thread_id"] = log_topic_id
                            if caption_entities: kwargs["caption_entities"] = caption_entities
                            if p_mode: kwargs["parse_mode"] = p_mode
                            p_args = [status_message, "up", task_uuid]
                            
                            if "Document" == msg_type: sent_msg = await acc.send_document(document=file_path, progress=progress, progress_args=p_args, **kwargs)
                            elif "Video" == msg_type: sent_msg = await acc.send_video(video=file_path, duration=v_dur, width=v_w, height=v_h, progress=progress, progress_args=p_args, **kwargs)
                            elif "Audio" == msg_type: sent_msg = await acc.send_audio(audio=file_path, duration=a_dur, performer=a_perf, title=a_tit, progress=progress, progress_args=p_args, **kwargs)
                            else: sent_msg = await acc.send_document(document=file_path, progress=progress, progress_args=p_args, **kwargs)
                            
                            if sent_msg:
                                try:
                                    bot_read_chat_id = user_id if log_chat_id == bot_id else log_chat_id
                                    await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.copy_message, chat_id=dest_chat_id, from_chat_id=bot_read_chat_id, message_id=sent_msg.id, message_thread_id=dest_thread_id)
                                except Exception:
                                    await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.copy_message, chat_id=dest_chat_id, from_chat_id=log_chat_id, message_id=sent_msg.id, message_thread_id=dest_thread_id)
                        except Exception as up_err:
                            raise up_err
                        finally:
                            if up_task and not up_task.done(): up_task.cancel()
                            try:
                                if file_path and os.path.exists(file_path): os.remove(file_path)
                            except Exception: pass
                        return True
                    else:
                        if USER_DOWNLOAD_SEMAPHORES[user_id].locked():
                            try:
                                if status_message: await status_message.edit_text(f"✂️ **Large File ({_pretty_bytes(file_size)})**\n⏳ Waiting in Download Queue...")
                            except FloodWait: pass
                        async with USER_DOWNLOAD_SEMAPHORES[user_id]:
                            file_path = await fetcher.download_media(msg_fresh, file_name=str(file_path_to_save), progress=progress, progress_args=[status_message, "down", task_uuid])
                        if down_task and not down_task.done(): down_task.cancel()
                        
                        try:
                            if status_message: await status_message.edit_text(f"✂️ **Splitting large file ({_pretty_bytes(file_size)})...**")
                        except FloodWait: pass

                        # --- 🟢 RICH CAPTION EXTRACTION FOR SPLIT PARTS ---
                        custom_cap = await build_rich_caption(file_path, msg_type, msg_fresh)
                        if custom_cap:
                            caption = custom_cap
                            caption_entities = None
                            p_mode = enums.ParseMode.HTML
                        else:
                            caption = msg_fresh.caption if getattr(msg_fresh, "caption", None) else ""
                            caption_entities = msg_fresh.caption_entities if getattr(msg_fresh, "caption_entities", None) else None
                            p_mode = None

                        parts = await split_file_python(file_path, chunk_size=1900*1024*1024)
                        
                        if status_message and f"{status_message.id}:up" in PROGRESS: del PROGRESS[f"{status_message.id}:up"]

                        up_task = asyncio.create_task(upstatus(client, status_message, status_message.chat.id, index, total_count, header_text)) if status_message else None
                    
                    async with USER_SEMAPHORES[user_id]:
                        async with SERVER_UPLOAD_LIMIT:
                            for part in parts:
                                if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): raise Exception("CANCELLED")
                                while True:
                                    await USER_FLOOD_LOCKS[user_id].wait_if_locked() 
                                    try:
                                        kwargs = {"chat_id": dest_chat_id, "document": str(part), "caption": caption}
                                        if caption_entities: kwargs["caption_entities"] = caption_entities
                                        if p_mode: kwargs["parse_mode"] = p_mode
                                        if dest_thread_id: kwargs["message_thread_id"] = dest_thread_id
                                        
                                        try:
                                            await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_document, **kwargs)
                                        except Exception:
                                            if acc: await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_document, **kwargs)
                                        break
                                    except FloodWait as e: 
                                        if e.value > 300: raise e
                                        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5) 
                                        await asyncio.sleep(e.value + 5)
                                    except Exception: break
                                try: 
                                    if os.path.exists(part): os.remove(part)
                                except Exception: pass
                    
                    if up_task and not up_task.done(): up_task.cancel()
                    try:
                        if file_path and os.path.exists(file_path): os.remove(file_path)
                    except Exception: pass
                    return True 
                else:
                    try:
                        if USER_DOWNLOAD_SEMAPHORES[user_id].locked():
                            try:
                                if status_message: await status_message.edit_text(f"⏳ **Queued...**\nWaiting for active download to finish...")
                            except FloodWait: pass
                        async with USER_DOWNLOAD_SEMAPHORES[user_id]:
                            file_path = await asyncio.wait_for(
                                fetcher.download_media(msg_fresh, file_name=str(file_path_to_save), progress=progress, progress_args=[status_message, "down", task_uuid]),
                                timeout=1200
                            )
                    except asyncio.TimeoutError:
                        return False
                
                try:
                    thumb = None
                    if msg_fresh.document and msg_fresh.document.thumbs: thumb = msg_fresh.document.thumbs[0]
                    elif msg_fresh.video and msg_fresh.video.thumbs: thumb = msg_fresh.video.thumbs[0]
                    elif msg_fresh.audio and msg_fresh.audio.thumbs: thumb = msg_fresh.audio.thumbs[0]
                    if thumb: ph_path = await fetcher.download_media(thumb.file_id, file_name=str(task_folder_path / "thumb.jpg"))
                except Exception: pass

                download_success = True
                break
            except FloodWait as e: 
                if e.value > 300: raise e
                USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5) 
                await asyncio.sleep(e.value + 5)
            except Exception as e:
                if "CANCELLED" in str(e): return False
                await asyncio.sleep(5)

        if down_task and not down_task.done(): down_task.cancel()
        
        if not download_success: return False
        if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): return False

        if status_message:
            PROGRESS.pop(f"{status_message.id}:up", None)
            PROGRESS.pop(f"{status_message.id}:down", None)
        up_task = asyncio.create_task(upstatus(client, status_message, status_message.chat.id, index, total_count, header_text)) if status_message else None
        
        # --- 🟢 RICH CAPTION EXTRACTION FOR NORMAL FILES ---
        custom_cap = await build_rich_caption(file_path, msg_type, msg_fresh)
        if custom_cap:
            caption = custom_cap
            caption_entities = None
            p_mode = enums.ParseMode.HTML
        else:
            caption = msg_fresh.caption if getattr(msg_fresh, "caption", None) else None
            caption_entities = msg_fresh.caption_entities if getattr(msg_fresh, "caption_entities", None) else None
            p_mode = None
        
        upload_success = False
        
        async with SERVER_UPLOAD_LIMIT:
            async with USER_SEMAPHORES[user_id]:
                while True:
                    if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): break
                    
                    await USER_FLOOD_LOCKS[user_id].wait_if_locked() 
                    try:
                        kwargs = {"chat_id": dest_chat_id, "message_thread_id": dest_thread_id, "caption": caption}
                        if caption_entities: kwargs["caption_entities"] = caption_entities
                        if p_mode: kwargs["parse_mode"] = p_mode
                        if ph_path and os.path.exists(ph_path): kwargs["thumb"] = ph_path
                            
                        p_args = [status_message, "up", task_uuid] if status_message else None
                        p_func = progress if status_message else None

                        a_dur = getattr(msg_fresh.audio, "duration", 0) if getattr(msg_fresh, "audio", None) else 0
                        a_perf = getattr(msg_fresh.audio, "performer", None) if getattr(msg_fresh, "audio", None) else None
                        a_tit = getattr(msg_fresh.audio, "title", None) if getattr(msg_fresh, "audio", None) else None

                        # 🟢 SMART AUDIO TAG EXTRACTOR: Fixes <unknown> artists!
                        if msg_type == "Audio":
                            if not a_perf or a_perf.lower() in ["unknown", "<unknown>"]:
                                clean_name = os.path.splitext(safe_filename)[0]
                                if " - " in clean_name:
                                    parts = clean_name.split(" - ", 1)
                                    a_perf = parts[0].strip() # Artist is before the dash
                                    if not a_tit or a_tit.lower() in ["unknown", "<unknown>", clean_name.lower()]:
                                        a_tit = parts[1].strip() # Title is after the dash
                                else:
                                    a_perf = "Unknown Artist"
                            if not a_tit or a_tit.lower() in ["unknown", "<unknown>"]:
                                a_tit = os.path.splitext(safe_filename)[0]

                        v_dur = getattr(msg_fresh.video, "duration", 0) if getattr(msg_fresh, "video", None) else 0
                        v_w = getattr(msg_fresh.video, "width", 0) if getattr(msg_fresh, "video", None) else 0
                        v_h = getattr(msg_fresh.video, "height", 0) if getattr(msg_fresh, "video", None) else 0

                        try:
                            if msg_type == "Document": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_document, document=file_path, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Video": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_video, video=file_path, duration=v_dur, width=v_w, height=v_h, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Audio": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_audio, audio=file_path, duration=a_dur, performer=a_perf, title=a_tit, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Photo": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_photo, photo=file_path, **kwargs)
                            elif msg_type == "Voice": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_voice, voice=file_path, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Animation": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_animation, animation=file_path, **kwargs)
                            elif msg_type == "Sticker": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_sticker, chat_id=dest_chat_id, sticker=file_path, message_thread_id=dest_thread_id)
                        except Exception:
                            if acc:
                                if msg_type == "Document": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_document, document=file_path, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Video": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_video, video=file_path, duration=v_dur, width=v_w, height=v_h, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Audio": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_audio, audio=file_path, duration=a_dur, performer=a_perf, title=a_tit, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Photo": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_photo, photo=file_path, **kwargs)
                                elif msg_type == "Voice": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_voice, voice=file_path, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Animation": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_animation, animation=file_path, **kwargs)
                                elif msg_type == "Sticker": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_sticker, chat_id=dest_chat_id, sticker=file_path, message_thread_id=dest_thread_id)
                        
                        upload_success = True
                        break 
                    except FloodWait as e:
                        if e.value > 300: raise e
                        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5) 
                        await asyncio.sleep(e.value + 5)
                    except Exception as e:
                        if "CANCELLED" in str(e): break
                        break
        
        if up_task and not up_task.done(): up_task.cancel()
        return upload_success

    finally:
        try:
            if 'task_folder_path' in locals() and task_folder_path.exists():
                shutil.rmtree(task_folder_path)
        except Exception: pass
        gc.collect()

# ==============================================================================
# --- FULL-STACK STREMIO WEB ENGINE & AUTHENTICATION BRIDGE ---
# ==============================================================================
try:
    from aiohttp import web
except ImportError:
    web = None

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en" data-theme="amoled">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Destiny TG Forwarder</title>

    <!-- PWA Web App Meta Tags -->
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#000000">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="TG Portal">
    <link rel="apple-touch-icon" href="https://cdn-icons-png.flaticon.com/512/2111/2111646.png">
    <style>
        :root { 
            --liquid-width: 50%;
            --bg: #000000; --card: #0a0a0a; --card-border: #1f2937; --text: #f1f5f9; --subtext: #94a3b8;
            --accent: #38bdf8; --glow: rgba(56, 189, 248, 0.4); --danger: #ef4444; --sidebar: #050505; 
        }

        /* --- 🌑 DARK THEMES --- */
        [data-theme="amoled"] { --bg: #000000; --card: #0a0a0a; --card-border: #1f2937; --text: #f1f5f9; --subtext: #94a3b8; --accent: #38bdf8; --glow: rgba(56, 189, 248, 0.4); --sidebar: #050505; }
        [data-theme="graphite"] { --bg: #141416; --card: #1c1c20; --card-border: #2e2e36; --text: #f3f4f6; --subtext: #9ca3af; --accent: #f59e0b; --glow: rgba(245, 158, 11, 0.4); --sidebar: #0e0e10; }
        [data-theme="obsidian"] { --bg: #090e17; --card: #111827; --card-border: #1e293b; --text: #f1f5f9; --subtext: #94a3b8; --accent: #10b981; --glow: rgba(16, 185, 129, 0.4); --sidebar: #070a12; }
        [data-theme="royal"] { --bg: #0b0914; --card: #151124; --card-border: #2d244a; --text: #f5f3ff; --subtext: #a78bfa; --accent: #8b5cf6; --glow: rgba(139, 92, 246, 0.4); --sidebar: #07050d; }
        [data-theme="slate"] { --bg: #0f172a; --card: #1e293b; --card-border: #334155; --text: #f8fafc; --subtext: #94a3b8; --accent: #0ea5e9; --glow: rgba(14, 165, 233, 0.4); --sidebar: #090d16; }
        [data-theme="charcoal"] { --bg: #12140e; --card: #1b1e15; --card-border: #2c3322; --text: #f7fee7; --subtext: #bef264; --accent: #a3e635; --glow: rgba(163, 230, 53, 0.4); --sidebar: #0c0e09; }
        [data-theme="fresh-canopy"] { --bg: #0c1410; --card: #14201a; --card-border: #20352b; --text: #ecfdf5; --subtext: #6ee7b7; --accent: #bef264; --glow: rgba(190, 242, 100, 0.4); --sidebar: #080d0a; }
        [data-theme="tiffany-noir"] { --bg: #071415; --card: #0f2022; --card-border: #19383b; --text: #f0fdfa; --subtext: #5eead4; --accent: #2dd4bf; --glow: rgba(45, 212, 191, 0.4); --sidebar: #040d0e; }
        [data-theme="bridal-blush"] { --bg: #170d12; --card: #24141d; --card-border: #3d1e2e; --text: #fff1f2; --subtext: #fda4af; --accent: #fb7185; --glow: rgba(251, 113, 133, 0.4); --sidebar: #0f080c; }

        /* --- ☀️ LIGHT / WHITE THEMES --- */
        [data-theme="rose-quartz"] { --bg: #fff1f3; --card: #ffffff; --card-border: #fecdd3; --text: #4c0519; --subtext: #9f1239; --accent: #f43f5e; --glow: rgba(244, 63, 94, 0.25); --sidebar: #ffe4e6; }
        [data-theme="daylight-sky"] { --bg: #f0f7ff; --card: #ffffff; --card-border: #bfdbfe; --text: #0f172a; --subtext: #1e40af; --accent: #2563eb; --glow: rgba(37, 99, 235, 0.25); --sidebar: #e0f2fe; }
        [data-theme="sage-linen"] { --bg: #f4f7f4; --card: #ffffff; --card-border: #ccfbf1; --text: #134e4a; --subtext: #0f766e; --accent: #0d9488; --glow: rgba(13, 148, 136, 0.25); --sidebar: #e6f4f1; }
        [data-theme="golden-hour"] { --bg: #fffbeb; --card: #ffffff; --card-border: #fde68a; --text: #451a03; --subtext: #92400e; --accent: #d97706; --glow: rgba(217, 119, 6, 0.25); --sidebar: #fef3c7; }

        * { box-sizing: border-box; }
        /* 🌊 Apple Music Liquid Flow Animations - Slow & Elegant */
        @keyframes flowPrimary {
            0% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(15vw, -10vh) scale(1.1); }
            66% { transform: translate(-15vw, 15vh) scale(0.9); }
            100% { transform: translate(0, 0) scale(1); }
        }
        @keyframes flowSecondary {
            0% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(-20vw, 15vh) scale(1.2); }
            66% { transform: translate(20vw, -15vh) scale(0.8); }
            100% { transform: translate(0, 0) scale(1); }
        }

        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; overflow-x: hidden; transition: background 0.5s ease; position: relative; z-index: 0; }
        
        /* 120px blur creates the smooth mesh gradient without washing out the screen */
        body::before, body::after { 
            content: ''; position: fixed; border-radius: 50%; 
            filter: blur(120px); -webkit-filter: blur(120px); z-index: -1; 
            /* Deep, subtle base (0.08) so the black theme stays gorgeously dark */
            opacity: calc(0.08 + var(--blob-opacity, 0)); 
            transition: opacity 0.8s ease; pointer-events: none; 
            will-change: transform; 
            background: var(--accent); /* Both use solid accent for maximum richness */
        }
        
        body::before { 
            width: 70vw; height: 70vh; 
            top: -10vh; left: -10vw; 
            animation: flowPrimary 40s infinite ease-in-out; 
        }
        body::after { 
            width: 75vw; height: 75vh; 
            bottom: -10vh; right: -10vw; 
            animation: flowSecondary 48s infinite ease-in-out reverse; 
        }

        .view-section { display: none; padding-bottom: 40px; }
        .view-section.active { display: block; }

        #login-view { display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; background: transparent; }
        .login-card { background: color-mix(in srgb, var(--card) var(--glass-bg, 100%), transparent); backdrop-filter: blur(var(--glass-blur, 0px)); -webkit-backdrop-filter: blur(var(--glass-blur, 0px)); border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); border-radius: 28px; width: 100%; max-width: 420px; padding: 36px 28px; box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 8px 32px rgba(0, 0, 0, var(--glass-shadow, 0)); text-align: center; transition: 0.3s; }
        .login-logo { width: 56px; height: 56px; background: var(--accent); border-radius: 50%; margin: 0 auto 20px auto; display: flex; align-items: center; justify-content: center; font-size: 24px; box-shadow: 0 0 25px var(--glow); color: #fff; }
        .login-title { font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 6px; }
        .login-subtitle { font-size: 13px; color: #94a3b8; margin-bottom: 28px; }

        .navbar { display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: color-mix(in srgb, rgba(10, 10, 10, 0.85) var(--glass-bg, 100%), transparent); backdrop-filter: blur(calc(12px + var(--glass-blur, 0px))); -webkit-backdrop-filter: blur(calc(12px + var(--glass-blur, 0px))); border-bottom: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); position: sticky; top: 0; z-index: 100; }
        .nav-brand { display: flex; align-items: center; gap: 12px; font-size: 18px; font-weight: 800; }
        .nav-brand-icon { width: 34px; height: 34px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 15px var(--glow); color: white; font-size: 14px; }
        .nav-controls { display: flex; align-items: center; gap: 12px; }
        .icon-btn { background: var(--card); border: 1px solid var(--card-border); color: #fff; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s; }
        .icon-btn:hover { border-color: var(--accent); }

        .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); backdrop-filter: blur(4px); z-index: 200; opacity: 0; pointer-events: none; transition: 0.3s; }
        .sidebar { position: fixed; top: 0; left: -300px; width: 280px; height: 100%; background: color-mix(in srgb, var(--sidebar) var(--glass-bg, 100%), transparent); backdrop-filter: blur(var(--glass-blur, 0px)); -webkit-backdrop-filter: blur(var(--glass-blur, 0px)); z-index: 201; border-right: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); box-shadow: 5px 0 30px rgba(0, 0, 0, var(--glass-shadow, 0)); transition: left 0.3s cubic-bezier(0.4, 0, 0.2, 1), background 0.3s, backdrop-filter 0.3s; padding: 20px 0; overflow-y: auto; }
        .sidebar.open { left: 0; }
        .sidebar-overlay.open { opacity: 1; pointer-events: auto; }
        .menu-item { padding: 16px 24px; display: flex; align-items: center; gap: 16px; color: #cbd5e1; font-weight: 600; cursor: pointer; transition: 0.2s; }
        .menu-item:hover, .menu-item.active { background: rgba(59, 130, 246, 0.1); color: #fff; border-left: 4px solid var(--accent); }
        
        .profile-menu { 
            position: absolute; top: 65px; right: 15px; 
            background: color-mix(in srgb, var(--card) var(--glass-bg, 100%), transparent); 
            backdrop-filter: blur(var(--glass-blur, 0px)); -webkit-backdrop-filter: blur(var(--glass-blur, 0px));
            border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); 
            border-radius: 18px; padding: 15px; width: 260px; display: none; z-index: 105; 
            box-shadow: 0 15px 40px rgba(0,0,0,0.8); max-height: 85vh; overflow-y: auto; 
        }
        .profile-menu.show { display: block; }
        .user-info { display: flex; flex-direction: column; gap: 2px; padding-bottom: 10px; border-bottom: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); margin-bottom: 12px; }
        .theme-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 15px; }
        .theme-btn { background: var(--bg); border: 1px solid var(--card-border); padding: 8px 10px; border-radius: 10px; font-size: 11px; color: #fff; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: 0.2s; }
        .theme-btn.active { border-color: var(--accent); background: rgba(59,130,246,0.1); }
        .dot { width: 10px; height: 10px; border-radius: 50%; }

        :root { --liquid-width: 50%; }
        .container { 
            width: var(--liquid-width); 
            min-width: 320px; /* Prevents the UI from completely vanishing if you slide to 0% */
            max-width: 100%; 
            margin: 0 auto; 
            padding: 20px; 
            transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1); 
        }
        .section-title { font-size: 20px; font-weight: 800; margin: 25px 0 15px 0; color: var(--text); display: flex; justify-content: space-between; align-items: center; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .card { background: color-mix(in srgb, var(--card) var(--glass-bg, 100%), transparent); backdrop-filter: blur(var(--glass-blur, 0px)); -webkit-backdrop-filter: blur(var(--glass-blur, 0px)); border-radius: 20px; padding: 20px; border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); box-shadow: 0 8px 32px rgba(0, 0, 0, var(--glass-shadow, 0)); transition: 0.3s; }
        .card-stat { font-size: 24px; font-weight: 800; color: var(--text); margin-top: 5px; }
        .card-label { font-size: 11px; color: var(--subtext); text-transform: uppercase; font-weight: 700; letter-spacing: 1px; }

        .primary-btn { width: 100%; padding: 15px; background: var(--accent); border: none; border-radius: 14px; color: #fff; font-size: 14px; font-weight: 700; cursor: pointer; transition: 0.3s; box-shadow: 0 4px 20px var(--glow); text-transform: uppercase; letter-spacing: 0.5px; }
        .primary-btn:hover { transform: translateY(-2px); box-shadow: 0 6px 25px var(--glow); }
        .input-group { margin-bottom: 18px; text-align: left; }
        .input-group label { display: block; font-size: 11px; color: var(--subtext); margin-bottom: 6px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }
        .input-group input, .input-group select { width: 100%; padding: 14px 16px; border-radius: 14px; border: 1px solid var(--card-border); background: var(--bg); color: var(--text); font-size: 14px; outline: none; transition: 0.2s; }
        .input-group input:focus { border-color: var(--accent); box-shadow: 0 0 10px var(--glow); }

        .task-row { background: color-mix(in srgb, var(--card) var(--glass-bg, 100%), transparent); border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); border-radius: 16px; padding: 16px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 15px; transition: 0.3s; }
        .task-kill { background: rgba(239, 68, 68, 0.1); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.2); padding: 8px 16px; border-radius: 10px; font-size: 12px; font-weight: 700; cursor: pointer; transition: 0.2s; }
        .task-kill:hover { background: var(--danger); color: #fff; box-shadow: 0 0 15px rgba(239, 68, 68, 0.4); }

        .filter-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 18px; }
        .filter-checkbox { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text); background: var(--bg); padding: 10px 12px; border-radius: 10px; border: 1px solid var(--card-border); cursor: pointer; }
        .filter-checkbox input { accent-color: var(--accent); width: 16px; height: 16px; }

        .modal { position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 300; display: none; align-items: center; justify-content: center; backdrop-filter: blur(6px); padding: 20px; }
        .modal.show { display: flex; }
        .modal-content { background: color-mix(in srgb, var(--card) var(--glass-bg, 100%), transparent); backdrop-filter: blur(var(--glass-blur, 0px)); -webkit-backdrop-filter: blur(var(--glass-blur, 0px)); width: 100%; max-width: 460px; border-radius: 24px; padding: 28px; border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); box-shadow: 0 25px 60px rgba(0,0,0,0.8), 0 8px 32px rgba(0, 0, 0, var(--glass-shadow, 0)); max-height: 90vh; overflow-y: auto; transition: 0.3s; }
        .modal-actions { display: flex; gap: 12px; margin-top: 24px; }
        .btn-cancel { flex: 1; padding: 14px; border-radius: 12px; font-weight: 700; cursor: pointer; border: 1px solid var(--card-border); background: var(--bg); color: var(--text); }

        /* Pill theme button layout */
        .theme-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
        .theme-pill { 
            padding: 7px 10px; border-radius: 999px; font-size: 11px; font-weight: 700; cursor: pointer; 
            display: flex; align-items: center; gap: 6px; transition: 0.2s; border: 1.5px solid transparent; 
            text-decoration: none; user-select: none;
        }
        .theme-pill.active { border-color: var(--accent); box-shadow: 0 0 10px var(--glow); }
        .theme-pill .dots-group { display: flex; align-items: center; gap: 3px; }
        .theme-pill .dot { width: 6px; height: 6px; border-radius: 50%; box-shadow: 0 0 4px currentColor; }
        .theme-pill .pill-label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .theme-pill .check { font-size: 10px; margin-left: 2px; }
    </style>
</head>
<body>

    <div id="login-view">
        <div class="login-card">
            <div class="login-logo">▶</div>
            <div class="login-title">Destiny TG Forwarder</div>
            <div class="login-subtitle">Enter your Telegram ID & Web Password</div>
            <form onsubmit="handleLogin(event)">
                <div class="input-group">
                    <label>Telegram User ID</label>
                    <input type="number" id="login-uid" placeholder="e.g. 123456789" required>
                </div>
                <div class="input-group">
                    <label>Web Password (Signup/Login)</label>
                    <input type="password" id="login-pwd" placeholder="••••••••" required>
                </div>
                <button type="submit" class="primary-btn" style="margin-top: 10px;">Sign In / Register</button>
                <div style="margin-top: 15px; font-size: 12px; font-weight: 700;">
                    <a href="#" onclick="forgotPassword(event)" style="color: var(--accent); text-decoration: none; transition: 0.2s;">Forgot Password?</a>
                </div>
            </form>
        </div>
    </div>

    <div id="app-view" style="display: none;">
        <div class="navbar">
            <div class="nav-brand">
                <div class="icon-btn" onclick="toggleSidebar()" style="border:none;">☰</div>
                <div class="nav-brand-icon">▶</div>
                <span id="nav-title">Home</span>
            </div>
            <div class="nav-controls">
                <div class="icon-btn" onclick="toggleProfile()">👤</div>
            </div>
        </div>

        <div class="sidebar-overlay" onclick="toggleSidebar()"></div>
        <div class="sidebar" id="sidebar">
            <div class="menu-item active" onclick="switchView('home', 'Home')">🏠 Home</div>
            <div class="menu-item" onclick="switchView('downloads', 'Downloads')">📥 Downloads</div>
            <div class="menu-item" onclick="switchView('watchers', 'Watchers')">📡 Watchers</div>
            <div class="menu-item" onclick="switchView('chats', 'Chats & IDs')">💬 Chats & IDs</div>
            <div class="menu-item" onclick="switchView('speedtest', 'Speedtest')">🚀 Speedtest</div>
            <div class="menu-item" onclick="switchView('sos', 'System SOS')">🖥 System SOS</div>
            <div class="menu-item" onclick="switchView('logs', 'Logs')">📋 System Logs</div>
            <div class="menu-item" onclick="switchView('settings', 'Settings')">⚙️ Settings</div>
        </div>

        <div class="profile-menu" id="profile-menu">
            <div class="user-info">
                <strong id="profile-name">User</strong>
                <span id="profile-id" style="color: #64748b; font-size: 11px;">ID: ...</span>
                <span style="color: #10b981; font-size: 12px; margin-top: 4px;">● ONLINE</span>
            </div>
            <!-- PWA Install Button -->
            <button id="pwa-install-btn" class="primary-btn" style="display: none; background: linear-gradient(135deg, var(--accent), #6366f1); margin-bottom: 15px; padding: 12px;" onclick="triggerPwaInstall()">📲 Install as App</button>

            <div style="font-size: 11px; color: var(--subtext); margin-bottom: 10px; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px;">App Theme</div>
            <div class="theme-grid">
                <!-- DARK THEMES -->
                <div class="theme-pill active" style="background: #09090b; color: #fff;" onclick="setTheme('amoled', this)">
                    <div class="dots-group"><span class="dot" style="background:#38bdf8; color:#38bdf8;"></span><span class="dot" style="background:#818cf8; color:#818cf8;"></span></div>
                    <span class="pill-label">AMOLED</span><span class="check">✓</span>
                </div>
                <div class="theme-pill" style="background: #18181b; color: #fff;" onclick="setTheme('graphite', this)">
                    <div class="dots-group"><span class="dot" style="background:#f59e0b; color:#f59e0b;"></span><span class="dot" style="background:#fbbf24; color:#fbbf24;"></span></div>
                    <span class="pill-label">Graphite</span>
                </div>
                <div class="theme-pill" style="background: #0b131f; color: #fff;" onclick="setTheme('obsidian', this)">
                    <div class="dots-group"><span class="dot" style="background:#10b981; color:#10b981;"></span><span class="dot" style="background:#34d399; color:#34d399;"></span></div>
                    <span class="pill-label">Obsidian</span>
                </div>
                <div class="theme-pill" style="background: #130e22; color: #fff;" onclick="setTheme('royal', this)">
                    <div class="dots-group"><span class="dot" style="background:#8b5cf6; color:#8b5cf6;"></span><span class="dot" style="background:#a78bfa; color:#a78bfa;"></span></div>
                    <span class="pill-label">Royal Violet</span>
                </div>
                <div class="theme-pill" style="background: #0d1a2d; color: #fff;" onclick="setTheme('slate', this)">
                    <div class="dots-group"><span class="dot" style="background:#0ea5e9; color:#0ea5e9;"></span><span class="dot" style="background:#38bdf8; color:#38bdf8;"></span></div>
                    <span class="pill-label">Slate Ocean</span>
                </div>
                <div class="theme-pill" style="background: #14170e; color: #fff;" onclick="setTheme('charcoal', this)">
                    <div class="dots-group"><span class="dot" style="background:#a3e635; color:#a3e635;"></span><span class="dot" style="background:#bef264; color:#bef264;"></span></div>
                    <span class="pill-label">Charcoal</span>
                </div>
                <div class="theme-pill" style="background: #0f1c16; color: #fff;" onclick="setTheme('fresh-canopy', this)">
                    <div class="dots-group"><span class="dot" style="background:#bef264; color:#bef264;"></span><span class="dot" style="background:#a7f3d0; color:#a7f3d0;"></span></div>
                    <span class="pill-label">Fresh Canopy</span>
                </div>
                <div class="theme-pill" style="background: #0a1b1d; color: #fff;" onclick="setTheme('tiffany-noir', this)">
                    <div class="dots-group"><span class="dot" style="background:#2dd4bf; color:#2dd4bf;"></span><span class="dot" style="background:#5eead4; color:#5eead4;"></span></div>
                    <span class="pill-label">Tiffany Noir</span>
                </div>
                <div class="theme-pill" style="background: #1c0e15; color: #fff;" onclick="setTheme('bridal-blush', this)">
                    <div class="dots-group"><span class="dot" style="background:#fda4af; color:#fda4af;"></span><span class="dot" style="background:#fb7185; color:#fb7185;"></span></div>
                    <span class="pill-label">Bridal Blush</span>
                </div>

                <!-- WHITE / LIGHT THEMES -->
                <div class="theme-pill" style="background: #fff0f3; color: #881337; border-color: #fecdd3;" onclick="setTheme('rose-quartz', this)">
                    <div class="dots-group"><span class="dot" style="background:#f43f5e; color:#f43f5e;"></span><span class="dot" style="background:#fb7185; color:#fb7185;"></span></div>
                    <span class="pill-label">Rose Quartz</span>
                </div>
                <div class="theme-pill" style="background: #eff6ff; color: #1e3a8a; border-color: #bfdbfe;" onclick="setTheme('daylight-sky', this)">
                    <div class="dots-group"><span class="dot" style="background:#2563eb; color:#2563eb;"></span><span class="dot" style="background:#60a5fa; color:#60a5fa;"></span></div>
                    <span class="pill-label">Daylight Sky</span>
                </div>
                <div class="theme-pill" style="background: #f0fdfa; color: #134e4a; border-color: #99f6e4;" onclick="setTheme('sage-linen', this)">
                    <div class="dots-group"><span class="dot" style="background:#0d9488; color:#0d9488;"></span><span class="dot" style="background:#2dd4bf; color:#2dd4bf;"></span></div>
                    <span class="pill-label">Sage Linen</span>
                </div>
                <div class="theme-pill" style="background: #fffbeb; color: #78350f; border-color: #fde68a;" onclick="setTheme('golden-hour', this)">
                    <div class="dots-group"><span class="dot" style="background:#ea580c; color:#ea580c;"></span><span class="dot" style="background:#f59e0b; color:#f59e0b;"></span></div>
                    <span class="pill-label">Golden Hour</span>
                </div>
            </div>
            <button class="primary-btn" style="background: rgba(239, 68, 68, 0.1); color: var(--danger); padding: 12px; margin-top: 5px;" onclick="logout()">Logout</button>
        </div>

        <div class="container">
            <div id="view-home" class="view-section active">
                <button class="primary-btn" onclick="openTaskModal()" style="margin-bottom: 25px;">➕ CREATE NEW TASK / WATCHER</button>
                <div class="section-title">System Overview</div>
                <div class="grid">
                    <div class="card">
                        <div class="card-label">Server Uptime</div>
                        <div class="card-stat" id="uptime">Loading...</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Your Active Tasks</div>
                        <div class="card-stat" id="active-tasks">Loading...</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Your Live Watchers</div>
                        <div class="card-stat" id="active-watchers">Loading...</div>
                    </div>
                    <div class="card">
                        <div class="card-label">Hardware (RAM / CPU)</div>
                        <div class="card-stat" id="hardware">Loading...</div>
                    </div>
                    <div class="card" style="grid-column: span 2;">
                        <div class="card-label">Telegram Session Status</div>
                        <div class="card-stat" id="tg-status" style="font-size: 15px; margin-top: 6px;">Checking...</div>
                    </div>
                </div>
            </div>

            <div id="view-downloads" class="view-section">
                <div class="section-title">
                    <span>Downloads & Forwarding Tasks</span>
                    <button class="primary-btn" style="width: auto; padding: 8px 16px; font-size: 12px;" onclick="openTaskModal()">+ Add</button>
                </div>
                <div id="downloads-list"><div style="color: #64748b;">Loading downloads...</div></div>
            </div>

            <div id="view-watchers" class="view-section">
                <div class="section-title">
                    <span>Live Auto-Watchers</span>
                    <button class="primary-btn" style="width: auto; padding: 8px 16px; font-size: 12px;" onclick="openTaskModal()">+ Add Watcher</button>
                </div>
                <div id="watchers-list"><div style="color: #64748b;">Loading watchers...</div></div>
            </div>

            <div id="view-chats" class="view-section">
                <div class="section-title">
                    <span>Your Telegram Dialogs</span>
                    <button id="refresh-chats-btn" class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px;" onclick="loadWebChats(true)">🔄 Refresh</button>
                </div>
                
                <div id="web-chats-warning" class="card" style="display:none; border-color: var(--danger); margin-bottom: 20px;">
                    <strong style="color: var(--danger);">⚠️ Telegram Session Not Connected</strong>
                    <p style="font-size: 12px; color: #94a3b8; margin: 6px 0 0 0;">Please connect your Telegram account in the <b>Settings</b> tab or run <code>/login</code> in the bot to view your dialog list.</p>
                </div>

                <div id="web-chats-content">
                    <div class="input-group">
                        <input type="text" id="web-chat-search" placeholder="🔍 Search by name or chat ID..." oninput="renderFilteredChats()">
                    </div>
                    
                    <div style="display: flex; gap: 8px; margin-bottom: 16px; overflow-x: auto; padding-bottom: 4px;">
                        <button class="theme-btn active" id="filter-btn-all" onclick="filterChatsCategory('All', this)">All</button>
                        <button class="theme-btn" id="filter-btn-group" onclick="filterChatsCategory('Group', this)">👥 Groups</button>
                        <button class="theme-btn" id="filter-btn-channel" onclick="filterChatsCategory('Channel', this)">📢 Channels</button>
                        <button class="theme-btn" id="filter-btn-bot" onclick="filterChatsCategory('Bot', this)">🤖 Bots</button>
                        <button class="theme-btn" id="filter-btn-user" onclick="filterChatsCategory('User', this)">👤 Users</button>
                    </div>

                    <div id="web-chats-list">
                        <div style="color: #64748b;">Loading dialogs...</div>
                    </div>
                </div>
            </div>

            <!-- SPEEDTEST VIEW -->
            <div id="view-speedtest" class="view-section">
                <div class="section-title">
                    <span>Network Speed Diagnostic</span>
                    <button class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px; background: #3b82f6;" onclick="runWebSpeedtest()">🚀 Run Speedtest</button>
                </div>
                <div class="card" style="text-align: center; padding: 30px;">
                    <div id="speedtest-status" style="color: #94a3b8; font-size: 14px; margin-bottom: 20px;">Click the button above to measure server bandwidth and latency.</div>
                    <div id="speedtest-results" style="display: none; text-align: left;">
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
                            <div style="background: var(--bg); padding: 16px; border-radius: 14px; border: 1px solid var(--card-border);">
                                <div class="card-label">Download Speed</div>
                                <div class="card-stat" id="st-dl" style="color: #10b981;">0 Mbps</div>
                            </div>
                            <div style="background: var(--bg); padding: 16px; border-radius: 14px; border: 1px solid var(--card-border);">
                                <div class="card-label">Upload Speed</div>
                                <div class="card-stat" id="st-ul" style="color: #38bdf8;">0 Mbps</div>
                            </div>
                        </div>
                        <div style="font-size: 13px; color: #cbd5e1; line-height: 1.6;">
                            <div>🏓 <b>Ping:</b> <span id="st-ping">-</span></div>
                            <div>🏢 <b>Server:</b> <span id="st-server">-</span></div>
                            <div>🤝 <b>Sponsor:</b> <span id="st-sponsor">-</span></div>
                        </div>
                        <div id="st-img-container" style="margin-top: 20px; text-align: center;"></div>
                    </div>
                </div>
            </div>

            <!-- SOS VIEW -->
            <div id="view-sos" class="view-section">
                <div class="section-title">
                    <span>Deep System Diagnostics (SOS)</span>
                    <button class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px;" onclick="loadSosStats()">🔄 Refresh Stats</button>
                </div>
                <div class="grid" id="sos-grid">
                    <div class="card"><div class="card-label">Operating System</div><div class="card-stat" id="sos-os" style="font-size: 14px; margin-top:8px;">Loading...</div></div>
                    <div class="card"><div class="card-label">Kernel Release</div><div class="card-stat" id="sos-kernel" style="font-size: 14px; margin-top:8px;">Loading...</div></div>
                    <div class="card"><div class="card-label">RAM Usage</div><div class="card-stat" id="sos-ram" style="font-size: 16px; margin-top:8px;">Loading...</div></div>
                    <div class="card"><div class="card-label">Disk Space Free</div><div class="card-stat" id="sos-disk" style="font-size: 16px; margin-top:8px;">Loading...</div></div>
                    <div class="card" style="grid-column: span 2;"><div class="card-label">Current Boot Bandwidth (Recv / Sent)</div><div class="card-stat" id="sos-boot-bw" style="font-size: 15px; margin-top:8px;">Loading...</div></div>
                    <div class="card" style="grid-column: span 2;"><div class="card-label" id="sos-month-label">Monthly Bandwidth</div><div class="card-stat" id="sos-month-bw" style="font-size: 15px; margin-top:8px;">Loading...</div></div>
                </div>
            </div>

            <div id="view-logs" class="view-section">
                <div class="section-title">
                    <span>System & Maintenance Logs</span>
                    <div style="display: flex; gap: 8px;">
                        <button class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px;" onclick="fetchLogs()">🔄 Refresh</button>
                        <a id="download-log-btn" href="/api/logs/download" class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px; text-decoration: none; text-align: center; background: #10b981;" download="bot.log">📥 Download</a>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                    <input type="checkbox" id="live-logs-toggle" style="width: 16px; height: 16px; accent-color: var(--accent);" onchange="toggleLiveLogs(this.checked)">
                    <label for="live-logs-toggle" style="font-size: 12px; color: #94a3b8; font-weight: 700; cursor: pointer;">LIVE TAIL (Auto-refresh every 3s)</label>
                </div>
                <div style="background: #000; border: 1px solid var(--card-border); border-radius: 16px; padding: 16px; font-family: monospace; font-size: 11px; color: #38bdf8; height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;" id="log-terminal">Loading logs...</div>
            </div>

            <div id="view-settings" class="view-section">
                
                <div class="section-title">Interface Settings</div>
                <div class="card" style="margin-bottom: 20px;">
                    <h3 style="margin-top: 0; font-size: 16px; color: #fff;">Liquid UI (Fluid Width)</h3>
                    <p style="font-size: 12px; color: #94a3b8; margin-bottom: 15px;">Adjust how wide and fluid the dashboard feels. (50% to 100%)</p>
                    <div class="input-group" style="margin-bottom: 25px;">
                        <label>Current Width: <span id="liquid-val">50</span>%</label>
                        <input type="range" id="liquid-slider" min="0" max="100" value="50" oninput="applyLiquidUI(this.value)" style="width: 100%; accent-color: var(--accent); cursor: pointer;">
                    </div>
                    
                    <h3 style="margin-top: 0; font-size: 16px; color: #fff;">Glass Effect (Liquid Transparency)</h3>
                    <p style="font-size: 12px; color: #94a3b8; margin-bottom: 15px;">Adjust the transparency and blur of panels to create a frosted glass aesthetic.</p>
                    <div class="input-group">
                        <label>Glass Intensity: <span id="glass-val">0</span>%</label>
                        <input type="range" id="glass-slider" min="0" max="100" value="0" oninput="applyLiquidGlass(this.value)" style="width: 100%; accent-color: var(--accent); cursor: pointer;">
                    </div>
                </div>

                <div class="section-title">Telegram Session Management</div>
                <div class="card" style="margin-bottom: 20px;">
                    <h3 style="margin-top: 0; font-size: 16px; color: #fff;">Connect Telegram via Web</h3>
                    <p style="font-size: 12px; color: #94a3b8; margin-bottom: 15px;">Link your account directly from your browser to enable downloading and fetch your chat list.</p>
                    
                    <div id="tg-login-step1">
                        <div class="input-group">
                            <label>Phone Number (with country code)</label>
                            <input type="text" id="tg-phone" placeholder="e.g. +1234567890">
                        </div>
                        <button class="primary-btn" style="padding: 12px; background: #10b981;" onclick="tgSendCode()">Send OTP Code</button>
                    </div>

                    <div id="tg-login-step2" style="display: none;">
                        <div class="input-group">
                            <label>Telegram OTP Code (Check your app)</label>
                            <input type="text" id="tg-code" placeholder="12345">
                        </div>
                        <button class="primary-btn" style="padding: 12px; background: #10b981;" onclick="tgVerifyCode()">Verify Code</button>
                    </div>

                    <div id="tg-login-step3" style="display: none;">
                        <div class="input-group">
                            <label>Two-Step Verification Password</label>
                            <input type="password" id="tg-2fa" placeholder="••••••••">
                        </div>
                        <button class="primary-btn" style="padding: 12px; background: #10b981;" onclick="tgVerify2FA()">Submit Password</button>
                    </div>
                    
                    <button id="tg-logout-btn" class="primary-btn" style="padding: 12px; background: rgba(239, 68, 68, 0.1); color: var(--danger); margin-top: 15px; display: none;" onclick="tgLogout()">Disconnect Telegram Session</button>
                </div>

                <div class="section-title">Security & Credentials</div>
                <div class="card" style="margin-bottom: 20px;">
                    <h3 style="margin-top: 0; font-size: 16px; color: #fff;">Change Web Password</h3>
                    <form onsubmit="changePassword(event)">
                        <div class="input-group">
                            <label>New Password</label>
                            <input type="password" id="new-pwd" placeholder="Enter new password" required>
                        </div>
                        <button type="submit" class="primary-btn" style="padding: 12px;">Update Password</button>
                    </form>
                </div>
            </div>

        </div>
    </div>

    <div class="modal" id="taskModal">
        <div class="modal-content">
            <h3 style="margin-top: 0; color: #fff; font-size: 18px; margin-bottom: 20px;">Create Task or Watcher</h3>
            <form onsubmit="submitTask(event)">
                <div class="input-group">
                    <label>Task Mode</label>
                    <select id="m-type" onchange="toggleMode(this.value)">
                        <option value="dl">Download / Clone Batch (/dl)</option>
                        <option value="watch">Live Auto-Forwarder (/watch)</option>
                    </select>
                </div>
                <div class="input-group">
                    <label>Telegram Source Link</label>
                    <input type="text" id="t-link" placeholder="https://t.me/channel/100 or 101-120" required>
                </div>
                <!-- 🟢 UPDATED: Destination now uses Datalist for Web Dropdown Search -->
                <div class="input-group">
                    <label>Destination Chat ID / Topic</label>
                    <input type="text" id="t-dest" list="tg-chats-list" placeholder="Select your chat or enter ID (-100...)">
                    <datalist id="tg-chats-list"></datalist>
                </div>
                <div class="input-group" id="delay-group">
                    <label>Forward Delay (Seconds)</label>
                    <input type="number" id="t-delay" value="3" min="0">
                </div>
                <div class="input-group">
                    <label>Media Filters (Allowed Types)</label>
                    <div class="filter-grid">
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Video" checked> Video</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Document" checked> Document</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Audio"> Audio</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Photo"> Photo</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Voice"> Voice</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Text"> Text</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Animation"> Animation</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Sticker"> Sticker</label>
                    </div>
                </div>
                <div class="modal-actions">
                    <button type="button" class="btn-cancel" onclick="closeTaskModal()">Cancel</button>
                    <button type="submit" class="primary-btn" style="flex:1; margin:0;">Launch Task</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        let currentUser = localStorage.getItem('tg_uid') || null;
        let chatsLoaded = false;

        function applyLiquidUI(val) {
            document.getElementById('liquid-val').innerText = val;
            document.documentElement.style.setProperty('--liquid-width', val + '%');
            localStorage.setItem('liquid_ui_val', val);
        }

        function applyLiquidGlass(val) {
            document.getElementById('glass-val').innerText = val;
            
            const blurPx = (val / 100) * 24; 
            // Keep cards darker! Lowest opacity is now 55% so they stay beautifully tinted
            const bgAlpha = 100 - (val / 100 * 45);       
            const borderAlpha = 100 - (val / 100 * 60);   
            // Keep blobs subtle! Max boost is only 0.25 so the screen stays comfortably dark
            const blobOpacity = (val / 100) * 0.25;       
            const shadowAlpha = (val / 100) * 0.5;        

            document.documentElement.style.setProperty('--glass-blur', blurPx + 'px');
            document.documentElement.style.setProperty('--glass-bg', bgAlpha + '%');
            document.documentElement.style.setProperty('--glass-border', borderAlpha + '%');
            document.documentElement.style.setProperty('--blob-opacity', blobOpacity);
            document.documentElement.style.setProperty('--glass-shadow', shadowAlpha);
            
            localStorage.setItem('liquid_glass_val', val);
        }

        if (currentUser) {
            document.getElementById('login-view').style.display = 'none';
            document.getElementById('app-view').style.display = 'block';
            document.getElementById('profile-id').innerText = "ID: " + currentUser;
            
            // Apply Liquid UI Settings instantly on load
            const savedLiquid = localStorage.getItem('liquid_ui_val') || "50";
            applyLiquidUI(savedLiquid);
            
            const savedGlass = localStorage.getItem('liquid_glass_val') || "0";
            applyLiquidGlass(savedGlass);

            setTimeout(() => { 
                if (document.getElementById('liquid-slider')) document.getElementById('liquid-slider').value = savedLiquid; 
                if (document.getElementById('glass-slider')) document.getElementById('glass-slider').value = savedGlass; 
            }, 100);

            fetchStats();
            setInterval(fetchStats, 5000);
        }

        async function handleLogin(e) {
            e.preventDefault();
            const uid = document.getElementById('login-uid').value;
            const pwd = document.getElementById('login-pwd').value;
            
            const btn = e.target.querySelector('button');
            const originalText = btn.innerText;
            btn.innerText = "Authenticating...";
            btn.style.opacity = "0.7";
            
            try {
                const res = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: uid, password: pwd})
                });
                const data = await res.json();
                if (data.status === 'success') {
                    localStorage.setItem('tg_uid', uid);
                    currentUser = uid;
                    document.getElementById('login-view').style.display = 'none';
                    document.getElementById('app-view').style.display = 'block';
                    document.getElementById('profile-id').innerText = "ID: " + uid;
                    fetchStats();
                } else {
                    alert("Login Failed: " + data.message);
                }
            } finally {
                btn.innerText = originalText;
                btn.style.opacity = "1";
            }
        }

        async function forgotPassword(e) {
            e.preventDefault();
            const uid = document.getElementById('login-uid').value;
            if (!uid) return alert("Please enter your Telegram User ID first!");
            
            const link = e.target;
            link.innerText = "Sending to Telegram PM...";
            
            try {
                const res = await fetch('/api/auth/forgot', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: uid})
                });
                const data = await res.json();
                alert(data.message);
            } catch(err) {
                alert("Error connecting to server.");
            } finally {
                link.innerText = "Forgot Password?";
            }
        }

        function logout() {
            localStorage.removeItem('tg_uid');
            location.reload();
        }

        function toggleSidebar() {
            document.getElementById('sidebar').classList.toggle('open');
            document.querySelector('.sidebar-overlay').classList.toggle('open');
        }
        function toggleProfile() { document.getElementById('profile-menu').classList.toggle('show'); }
        function switchView(viewId, title) {
            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            document.getElementById('view-' + viewId).classList.add('active');
            document.querySelectorAll('.menu-item').forEach(el => el.classList.remove('active'));
            event.currentTarget.classList.add('active');
            document.getElementById('nav-title').innerText = title;
            toggleSidebar();

            if (viewId === 'chats') loadWebChats();
            if (viewId === 'sos') loadSosStats();
        }

        async function runWebSpeedtest() {
            const statusEl = document.getElementById('speedtest-status');
            const resultsEl = document.getElementById('speedtest-results');
            statusEl.innerHTML = "<i>⏱ Running Speedtest... This takes about 10-15 seconds to measure ping, download, and upload speeds. Please wait...</i>";
            resultsEl.style.display = 'none';

            try {
                const res = await fetch(`/api/speedtest?user_id=${currentUser}`);
                const data = await res.json();
                
                if (data.status === 'success') {
                    statusEl.innerHTML = "✅ <b>Speedtest Completed Successfully!</b>";
                    resultsEl.style.display = 'block';
                    document.getElementById('st-dl').innerText = data.download;
                    document.getElementById('st-ul').innerText = data.upload;
                    document.getElementById('st-ping').innerText = data.ping;
                    document.getElementById('st-server').innerText = data.server;
                    document.getElementById('st-sponsor').innerText = data.sponsor;
                    
                    const imgContainer = document.getElementById('st-img-container');
                    if (data.share_image) {
                        imgContainer.innerHTML = `<img src="${data.share_image}" alt="Speedtest Result" style="max-width: 100%; border-radius: 14px; border: 1px solid var(--card-border);">`;
                    } else {
                        imgContainer.innerHTML = '';
                    }
                } else {
                    statusEl.innerHTML = `<span style="color: var(--danger);">❌ Error: ${data.message}</span>`;
                }
            } catch(e) {
                statusEl.innerHTML = `<span style="color: var(--danger);">❌ Network connection error while running speedtest.</span>`;
            }
        }

        async function loadSosStats() {
            if (!currentUser) return;
            try {
                const res = await fetch(`/api/sos?user_id=${currentUser}`);
                const data = await res.json();
                
                if (data.status === 'success') {
                    document.getElementById('sos-os').innerText = data.os;
                    document.getElementById('sos-kernel').innerText = data.kernel;
                    document.getElementById('sos-ram').innerText = `${data.ram_percent}% (${data.ram_used} / ${data.ram_total})`;
                    document.getElementById('sos-disk').innerText = `${data.disk_percent}% free (${data.disk_free} / ${data.disk_total})`;
                    document.getElementById('sos-boot-bw').innerText = `📥 ${data.boot_download}  │  📤 ${data.boot_upload}`;
                    document.getElementById('sos-month-label').innerText = `Monthly Bandwidth (${data.month_name})`;
                    document.getElementById('sos-month-bw').innerText = `Downloaded: ${data.month_download}  │  Uploaded: ${data.month_upload}  │  Total: ${data.month_total}`;
                }
            } catch(e) {}
        }

        function setTheme(themeName, el) {
            document.documentElement.setAttribute('data-theme', themeName);
            document.querySelectorAll('.theme-pill').forEach(b => {
                b.classList.remove('active');
                const chk = b.querySelector('.check');
                if (chk) chk.remove();
            });
            el.classList.add('active');
            el.insertAdjacentHTML('beforeend', '<span class="check">✓</span>');
            localStorage.setItem('app_theme', themeName);
        }

        const savedTheme = localStorage.getItem('app_theme') || 'amoled';
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.querySelectorAll('.theme-pill').forEach(b => {
            const oc = b.getAttribute('onclick') || '';
            if (oc.includes(`'${savedTheme}'`)) {
                b.classList.add('active');
                if (!b.querySelector('.check')) b.insertAdjacentHTML('beforeend', '<span class="check">✓</span>');
            } else {
                b.classList.remove('active');
            }
        });

        /* --- 📲 PWA INSTALLATION ENGINE --- */
        let deferredPwaPrompt = null;
        window.addEventListener('beforeinstallprompt', (e) => {
            e.preventDefault();
            deferredPwaPrompt = e;
            const btn = document.getElementById('pwa-install-btn');
            if (btn) btn.style.display = 'block';
        });

        async function triggerPwaInstall() {
            if (deferredPwaPrompt) {
                deferredPwaPrompt.prompt();
                const choice = await deferredPwaPrompt.userChoice;
                if (choice.outcome === 'accepted') {
                    document.getElementById('pwa-install-btn').style.display = 'none';
                }
                deferredPwaPrompt = null;
            } else {
                alert("To install, tap your browser's menu (⋮ on Chrome, or Share on Safari) and select 'Install app' or 'Add to Home Screen'.");
            }
        }

        // Register Service Worker for PWA
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register('/sw.js').catch(() => {});
        }

        function openTaskModal() { document.getElementById('taskModal').classList.add('show'); }
        function closeTaskModal() { document.getElementById('taskModal').classList.remove('show'); }
        function toggleMode(val) { document.getElementById('delay-group').style.display = 'block'; }

        let allLoadedChats = [];
        let currentChatCat = 'All';

        async function loadWebChats(force = false) {
            if (!currentUser) return;
            const container = document.getElementById('web-chats-list');
            const warnBox = document.getElementById('web-chats-warning');
            const refreshBtn = document.getElementById('refresh-chats-btn');
            
            if (force) {
                container.innerHTML = '<div style="color: var(--subtext);">⏳ Refreshing dialogs from Telegram... (Please wait)</div>';
                if (refreshBtn) { refreshBtn.innerText = "⏳ Loading..."; refreshBtn.style.opacity = "0.5"; refreshBtn.style.pointerEvents = "none"; }
            }

            try {
                const res = await fetch(`/api/chats?user_id=${currentUser}`);
                const data = await res.json();
                
                if (data.status === 'success') {
                    warnBox.style.display = 'none';
                    allLoadedChats = data.chats || [];
                    
                    // High-Performance datalist building
                    const dl = document.getElementById('tg-chats-list');
                    if (dl) {
                        dl.innerHTML = '';
                        const frag = document.createDocumentFragment();
                        allLoadedChats.forEach(c => {
                            const opt = document.createElement('option');
                            opt.value = c.id;
                            opt.text = c.name;
                            frag.appendChild(opt);
                        });
                        dl.appendChild(frag);
                    }

                    renderFilteredChats();
                } else {
                    warnBox.style.display = 'block';
                    container.innerHTML = '<div style="color: var(--subtext);">No chats available. Connect session first.</div>';
                }
            } catch(e) {
                container.innerHTML = '<div style="color: var(--danger);">Failed to load dialogs.</div>';
            } finally {
                // Restore button instantly
                if (refreshBtn) { refreshBtn.innerText = "🔄 Refresh"; refreshBtn.style.opacity = "1"; refreshBtn.style.pointerEvents = "auto"; }
            }
        }

        function filterChatsCategory(cat, btn) {
            currentChatCat = cat;
            document.querySelectorAll('#web-chats-content .theme-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderFilteredChats();
        }

        function renderFilteredChats() {
            const query = (document.getElementById('web-chat-search').value || '').toLowerCase();
            const listEl = document.getElementById('web-chats-list');
            
            const filtered = allLoadedChats.filter(c => {
                let catMatchStr = '';
                if (currentChatCat === 'Group') catMatchStr = '👥 group';
                if (currentChatCat === 'Channel') catMatchStr = '📢 channel';
                if (currentChatCat === 'Bot') catMatchStr = '🤖 bot';
                if (currentChatCat === 'User') catMatchStr = '👤 user';

                const matchesCat = currentChatCat === 'All' || c.name.toLowerCase().includes(catMatchStr);
                const matchesQuery = c.name.toLowerCase().includes(query) || c.id.includes(query);
                return matchesCat && matchesQuery;
            });

            if (!filtered.length) {
                listEl.innerHTML = '<div style="color: var(--subtext); padding: 12px 0;">No matching dialogs found.</div>';
                return;
            }

            // High-Performance DOM Rendering (NO innerHTML += in a loop!)
            let htmlBuffer = "";
            filtered.forEach(c => {
                htmlBuffer += `
                    <div class="task-row" style="margin-bottom: 8px;">
                        <div>
                            <div style="font-weight: 700; color: var(--text); font-size: 13px;">${c.name}</div>
                            <div style="font-size: 11px; color: var(--accent); margin-top: 2px;">ID: <code>${c.id}</code></div>
                        </div>
                        <button class="task-kill" style="color: var(--accent); border-color: var(--card-border); background: var(--bg);" onclick="copyChatId('${c.id}')">📋 COPY ID</button>
                    </div>
                `;
            });
            
            // Assign the massive string exactly once. Browser renders instantly.
            listEl.innerHTML = htmlBuffer;
        }

        function copyChatId(id) {
            navigator.clipboard.writeText(id);
            alert("Copied ID: " + id);
        }

        async function fetchChatsList() {
            await loadWebChats();
        }

        async function fetchStats() {
            if (!currentUser) return;
            try {
                const res = await fetch(`/api/stats?user_id=${currentUser}`);
                const data = await res.json();
                
                if (data.user_name) document.getElementById('profile-name').innerText = data.user_name;
                document.getElementById('uptime').innerText = data.uptime;
                document.getElementById('active-tasks').innerText = data.active_tasks;
                document.getElementById('active-watchers').innerText = data.active_watchers;
                document.getElementById('hardware').innerText = data.ram + "% / " + data.cpu + "%";
                
                const tgStatusEl = document.getElementById('tg-status');
                if (data.tg_session_active) {
                    tgStatusEl.innerHTML = '<span style="color: #10b981;">✅ Active (Ready for Restricted Files)</span>';
                    document.getElementById('tg-login-step1').style.display = 'none';
                    document.getElementById('tg-login-step2').style.display = 'none';
                    document.getElementById('tg-login-step3').style.display = 'none';
                    document.getElementById('tg-logout-btn').style.display = 'block';
                    
                    if (!chatsLoaded) {
                        fetchChatsList();
                        chatsLoaded = true;
                    }
                } else {
                    tgStatusEl.innerHTML = '<span style="color: #ef4444;">❌ Not Connected — Login below!</span>';
                    document.getElementById('tg-login-step1').style.display = 'block';
                    document.getElementById('tg-logout-btn').style.display = 'none';
                    chatsLoaded = false;
                }

                if (document.getElementById('view-logs').classList.contains('active')) fetchLogs();
                
                const dlList = document.getElementById('downloads-list');
                dlList.innerHTML = data.tasks.length ? '' : '<div style="color: #64748b;">No active downloads.</div>';
                data.tasks.forEach(t => {
                    dlList.innerHTML += `
                        <div class="task-row">
                            <div>
                                <div style="font-weight: 700; color: #fff; font-size: 14px; word-break: break-all;">${t.name}</div>
                                <div style="font-size: 11px; color: var(--accent); margin-top: 4px;">Destination: ${t.dest} | Progress: ${t.current}/${t.total} (${t.percent}%)</div>
                            </div>
                            <button class="task-kill" onclick="cancelTask('${t.id}')">CANCEL</button>
                        </div>
                    `;
                });

                const wList = document.getElementById('watchers-list');
                wList.innerHTML = data.watchers.length ? '' : '<div style="color: #64748b;">No active watchers.</div>';
                data.watchers.forEach(w => {
                    wList.innerHTML += `
                        <div class="task-row">
                            <div>
                                <div style="font-weight: 700; color: #fff; font-size: 14px;">📡 ${w.source}</div>
                                <div style="font-size: 11px; color: #64748b; margin-top: 4px;">To: ${w.dest} | Detected: ${w.detected} | Success: ${w.success}</div>
                            </div>
                            <button class="task-kill" onclick="cancelWatcher('${w.id}')">REMOVE</button>
                        </div>
                    `;
                });
            } catch(e) {}
        }

        async function tgSendCode() {
            const phone = document.getElementById('tg-phone').value;
            const res = await fetch('/api/tg/send_code', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: currentUser, phone: phone}) });
            const data = await res.json();
            if (data.status === 'success') {
                document.getElementById('tg-login-step1').style.display = 'none';
                document.getElementById('tg-login-step2').style.display = 'block';
            } else alert("Error: " + data.message);
        }

        async function tgVerifyCode() {
            const code = document.getElementById('tg-code').value;
            const res = await fetch('/api/tg/verify', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: currentUser, code: code}) });
            const data = await res.json();
            if (data.status === 'success') {
                alert("Telegram Logged In Successfully!");
                fetchStats();
            } else if (data.status === '2fa_required') {
                document.getElementById('tg-login-step2').style.display = 'none';
                document.getElementById('tg-login-step3').style.display = 'block';
            } else alert("Error: " + data.message);
        }

        async function tgVerify2FA() {
            const pwd = document.getElementById('tg-2fa').value;
            const res = await fetch('/api/tg/verify_2fa', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: currentUser, password: pwd}) });
            const data = await res.json();
            if (data.status === 'success') {
                alert("Telegram Logged In Successfully!");
                fetchStats();
            } else alert("Error: " + data.message);
        }

        async function tgLogout() {
            if (!confirm("Are you sure you want to disconnect Telegram? Active watchers will be stopped.")) return;
            await fetch('/api/tg/logout', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: currentUser}) });
            fetchStats();
        }

        async function submitTask(e) {
            e.preventDefault();
            const mode = document.getElementById('m-type').value;
            const link = document.getElementById('t-link').value;
            const dest = document.getElementById('t-dest').value;
            const delay = document.getElementById('t-delay').value;
            
            const filtersArr = [];
            document.querySelectorAll('input[name="ftype"]:checked').forEach(cb => filtersArr.push(cb.value));

            const endpoint = mode === 'watch' ? '/api/watcher/add' : '/api/task/add';
            const res = await fetch(endpoint, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: currentUser, link, dest, delay, filters: filtersArr}) });
            const data = await res.json();
            if (data.status === 'success') {
                alert("Task started successfully!");
                closeTaskModal();
                fetchStats();
            } else alert("Error: " + data.message);
        }

        async function cancelTask(taskId) {
            if (!confirm("Cancel this task?")) return;
            await fetch('/api/task/cancel', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({task_id: taskId, user_id: currentUser}) });
            fetchStats();
        }

        async function cancelWatcher(watcherId) {
            if (!confirm("Remove this watcher?")) return;
            await fetch('/api/watcher/cancel', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({watcher_id: watcherId, user_id: currentUser}) });
            fetchStats();
        }

        async function changePassword(e) {
            e.preventDefault();
            const pwd = document.getElementById('new-pwd').value;
            const res = await fetch('/api/auth/password', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: currentUser, password: pwd}) });
            const data = await res.json();
            if (data.status === 'success') {
                alert("Password updated successfully!");
                document.getElementById('new-pwd').value = '';
            } else alert("Failed to update password.");
        }

        let liveLogInterval = null;
        let isFetchingLogs = false; // Lock variable to prevent overlapping request freezes
        
        async function fetchLogs() {
            if (isFetchingLogs) return; // Prevent freeze if you click refresh 10 times fast
            isFetchingLogs = true;
            try {
                const res = await fetch('/api/logs');
                const data = await res.json();
                const term = document.getElementById('log-terminal');
                term.innerText = data.logs || "No logs generated yet.";
                term.scrollTop = term.scrollHeight;
            } catch(e) {} finally {
                isFetchingLogs = false;
            }
        }

        function toggleLiveLogs(isChecked) {
            if (isChecked) { fetchLogs(); liveLogInterval = setInterval(fetchLogs, 3000); } 
            else clearInterval(liveLogInterval);
        }
    </script>
</body>
</html>
"""

async def _dashboard_ui_handler(request):
    return web.Response(text=HTML_DASHBOARD, content_type='text/html', status=200)

async def _api_login_handler(request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        password = data.get("password")
        
        user = await db.col.find_one({"id": user_id})
        if not user:
            return web.json_response({"status": "error", "message": "Account not found! Please go to Telegram and send /start to the bot first."})

        stored_pwd = user.get("web_password")
        if not stored_pwd:
            # First time web signup for an existing bot user
            await db.col.update_one({"id": user_id}, {"$set": {"web_password": password}})
            return web.json_response({"status": "success"})
        
        if stored_pwd == password:
            return web.json_response({"status": "success"})
        else:
            return web.json_response({"status": "error", "message": "Incorrect password!"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

async def _api_forgot_password_handler(request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        
        user = await db.col.find_one({"id": user_id})
        if not user:
            return web.json_response({"status": "error", "message": "Account not found! Please send /start to the bot in Telegram."})
            
        stored_pwd = user.get("web_password")
        if not stored_pwd:
            return web.json_response({"status": "error", "message": "You haven't set a web password yet. Just enter a new password to register!"})
            
        try:
            await app.send_message(
                chat_id=user_id,
                text=f"🔐 **Web Portal Password Recovery**\n\nYour current web dashboard password is: `{stored_pwd}`\n\n_If you did not request this, please change your password in the dashboard settings._"
            )
            return web.json_response({"status": "success", "message": "Your password has been sent to your Telegram PM!"})
        except Exception as e:
            return web.json_response({"status": "error", "message": "Failed to send PM. Please ensure you have started the bot in Telegram and haven't blocked it!"})
            
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=400)

async def _api_password_handler(request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        password = data.get("password")
        await db.col.update_one({"id": user_id}, {"$set": {"web_password": password}})
        return web.json_response({"status": "success"})
    except Exception:
        return web.json_response({"status": "error"}, status=400)

async def _api_stats_handler(request):
    try:
        user_id = int(request.query.get("user_id", 0))
    except:
        user_id = 0

    uptime_seconds = int(time.time() - BOT_START_TIME)
    days, rem = divmod(uptime_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_str = f"{days}d, {hours:02d}h: {minutes:02d}m" if days > 0 else f"{hours:02d}h: {minutes:02d}m"
    
    # User-specific tasks
    user_tasks = ACTIVE_PROCESSES.get(user_id, {})
    task_details = []
    for t_id, info in user_tasks.items():
        tot = info.get("total", 0)
        curr = info.get("current", 0)
        pct = round((curr / tot * 100), 1) if tot > 0 else 0
        
        # 🟢 Use Real Source Name instead of Raw Link
        src_name = info.get("source_title")
        if not src_name or src_name == "Unknown Source":
            src_name = info.get("item", "Task")
            
        task_details.append({
            "id": t_id,
            "name": src_name,
            "dest": info.get("dest_title_name", "DM"),
            "current": curr,
            "total": tot,
            "percent": pct
        })

    # User-specific watchers
    watcher_cursor = db.db.watchers.find({"user_id": user_id})
    watcher_details = []
    async for w in watcher_cursor:
        stats = w.get("stats", {})
        watcher_details.append({
            "id": str(w["_id"]),
            "source": w.get("source_title", "Source"),
            "dest": w.get("dest_title", "Destination"),
            "detected": stats.get("detected", 0),
            "success": stats.get("success", 0)
        })

    total_watchers = await db.db.watchers.count_documents({"user_id": user_id})
    
    # Check if user session exists in DB
    user_doc = await db.col.find_one({"id": user_id})
    tg_session_active = bool(user_doc and user_doc.get("session"))
    user_name = user_doc.get("name", "User") if user_doc else "User"

    return web.json_response({
        "uptime": uptime_str,
        "user_name": user_name,
        "ram": psutil.virtual_memory().percent,
        "cpu": psutil.cpu_percent(),
        "active_tasks": len(user_tasks),
        "active_watchers": total_watchers,
        "tg_session_active": tg_session_active,
        "tasks": task_details,
        "watchers": watcher_details
    })

async def _api_add_task(request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        link = data.get("link")
        dest_str = data.get("dest", "")
        delay = int(data.get("delay", 3))
        allowed_types = data.get("filters", ["Video", "Document"])

        if not link: return web.json_response({"status": "error", "message": "No link provided"})

        dest_chat_id = user_id
        dest_thread_id = None
        dest_title = "Saved Messages"
        
        if dest_str:
            dest_chat_id, dest_thread_id = _parse_chat_target(dest_str)
            # 🟢 Auto-Resolve Destination & Topic for Web Tasks
            uclient = USER_CLIENTS.get(user_id, app)
            try:
                d_chat = await uclient.get_chat(dest_chat_id)
                dest_title = d_chat.title or d_chat.first_name or str(dest_chat_id)
                if dest_thread_id: 
                    dest_title += await get_topic_title(uclient, dest_chat_id, dest_thread_id)
            except:
                dest_title = str(dest_chat_id)

        is_restricted, _ = await check_link_restriction(user_id, link)
        if is_restricted is None: is_restricted = False

        task_uuid = uuid.uuid4().hex
        if user_id not in ACTIVE_PROCESSES: ACTIVE_PROCESSES[user_id] = {}
        ACTIVE_PROCESSES[user_id][task_uuid] = {
            "user": f"WebUI({user_id})",
            "dest_title_name": dest_title,
            "item": link,
            "started": time.time(),
            "total": 0,
            "current": 0
        }

        asyncio.create_task(
            process_links_logic(
                client=app,
                message=None,
                text=link,
                dest_chat_id=dest_chat_id,
                dest_thread_id=dest_thread_id,
                dest_title=dest_title,
                delay=delay,
                acc_user_id=user_id,
                task_uuid=task_uuid,
                is_restricted=is_restricted,
                allowed_types=allowed_types
            )
        )
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def _api_cancel_task(request):
    try:
        data = await request.json()
        task_id = data.get("task_id")
        user_id = int(data.get("user_id", 0))
        if task_id:
            CANCEL_FLAGS[task_id] = True
            try: await db.remove_active_task(task_id)
            except: pass
            return web.json_response({"status": "success"})
    except: pass
    return web.json_response({"status": "error"}, status=400)

async def _api_add_watcher(request):
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        link = data.get("link")
        dest_str = data.get("dest", "")
        allowed_types = data.get("filters", ["Video", "Document"])

        dest_chat_id = user_id
        dest_thread_id = None
        if dest_str:
            dest_chat_id, dest_thread_id = _parse_chat_target(dest_str)

        is_restricted, _ = await check_link_restriction(user_id, link)
        if is_restricted is None: is_restricted = False

        parsed = _parse_source_link(link)
        
        # 🟢 FIX 1: Safely resolve Source & Destination Names (WITH TOPICS)
        user_client = USER_CLIENTS.get(user_id, app)
        try:
            if parsed["kind"] == "public":
                chat = await user_client.get_chat(parsed["join_target"])
            else:
                chat = await user_client.get_chat(parsed["chat_id"])
            source_id = chat.id
            source_title = chat.title or str(source_id)
            if parsed.get("topic_id"): 
                source_title += await get_topic_title(user_client, source_id, parsed["topic_id"])
        except Exception:
            source_id = parsed.get("chat_id")
            source_title = "Watched Source"
            
        dest_title = "Saved Messages" if dest_chat_id == user_id else str(dest_chat_id)
        if dest_chat_id != user_id:
            try:
                d_chat = await user_client.get_chat(dest_chat_id)
                dest_title = d_chat.title or d_chat.first_name or str(dest_chat_id)
                if dest_thread_id: 
                    dest_title += await get_topic_title(user_client, dest_chat_id, dest_thread_id)
            except: pass

        # 🟢 FIX 2: Dynamically start the background listener if it's inactive
        if user_id not in USER_CLIENTS:
            user_session = await db.get_session(user_id)
            if user_session:
                u_api = await db.get_api_id(user_id) or API_ID
                u_hash = await db.get_api_hash(user_id) or API_HASH
                new_client = Client(f"User_{user_id}", session_string=user_session, api_id=u_api, api_hash=u_hash, workers=4, ipv6=False)
                new_client.add_handler(MessageHandler(user_watcher_handler, filters.channel | filters.group | filters.private))
                await new_client.start()
                USER_CLIENTS[user_id] = new_client

        # 🟢 FIX 3: Fetch the accurate last_msg_id to prevent catch-up floods
        last_msg_id = 0
        try:
            async for m in USER_CLIENTS.get(user_id, app).get_chat_history(source_id, limit=1):
                last_msg_id = m.id
        except: pass

        await db.add_watcher(
            user_id=user_id,
            source_id=source_id,
            dest_id=dest_chat_id,
            source_thread=parsed.get("topic_id"),
            dest_thread=dest_thread_id,
            delay=0,
            is_restricted=is_restricted,
            source_title=source_title,
            dest_title=dest_title,
            allowed_types=allowed_types,
            last_msg_id=last_msg_id
        )
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def _api_cancel_watcher(request):
    try:
        data = await request.json()
        watcher_id = data.get("watcher_id")
        user_id = int(data.get("user_id", 0))
        if watcher_id:
            await db.db.watchers.delete_one({"_id": ObjectId(watcher_id), "user_id": user_id})
            return web.json_response({"status": "success"})
    except: pass
    return web.json_response({"status": "error"}, status=400)

def _read_logs_sync():
    """Reads logs safely in a background thread so the server doesn't freeze."""
    if not os.path.exists("bot.log"): return "Log file not created yet."
    with open("bot.log", "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    return "".join(lines[-150:])

async def _api_logs_handler(request):
    try:
        logs = await asyncio.to_thread(_read_logs_sync)
        return web.json_response({"logs": logs})
    except Exception as e:
        return web.json_response({"logs": f"Error reading logs: {e}"})

async def _api_download_log_handler(request):
    try:
        if os.path.exists("bot.log"):
            return web.FileResponse("bot.log", headers={"Content-Disposition": "attachment; filename=bot.log"})
        return web.Response(text="Log file not found.", status=404)
    except Exception:
        return web.Response(text="Error downloading logs.", status=500)

WEB_AUTH_CACHE = {}

async def _api_tg_send_code(request):
    data = await request.json()
    uid = int(data.get("user_id"))
    phone = data.get("phone")
    
    client = Client(f":memory:", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await client.connect()
    try:
        code = await client.send_code(phone)
        WEB_AUTH_CACHE[uid] = {"client": client, "phone": phone, "hash": code.phone_code_hash}
        return web.json_response({"status": "success"})
    except Exception as e:
        await client.disconnect()
        return web.json_response({"status": "error", "message": str(e)})

async def _api_tg_verify_code(request):
    data = await request.json()
    uid = int(data.get("user_id"))
    code = data.get("code")
    
    cache = WEB_AUTH_CACHE.get(uid)
    if not cache: return web.json_response({"status": "error", "message": "Session expired. Try again."})
    
    client = cache["client"]
    try:
        await client.sign_in(cache["phone"], cache["hash"], code)
        session_str = await client.export_session_string()
        await client.disconnect()
        del WEB_AUTH_CACHE[uid]
        
        await db.set_session(uid, session_str)
        await db.set_api_id(uid, API_ID)
        await db.set_api_hash(uid, API_HASH)
        return web.json_response({"status": "success"})
        
    except SessionPasswordNeeded:
        return web.json_response({"status": "2fa_required"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

async def _api_tg_verify_2fa(request):
    data = await request.json()
    uid = int(data.get("user_id"))
    pwd = data.get("password")
    
    cache = WEB_AUTH_CACHE.get(uid)
    if not cache: return web.json_response({"status": "error", "message": "Session expired."})
    
    client = cache["client"]
    try:
        await client.check_password(pwd)
        session_str = await client.export_session_string()
        await client.disconnect()
        del WEB_AUTH_CACHE[uid]
        
        await db.set_session(uid, session_str)
        await db.set_api_id(uid, API_ID)
        await db.set_api_hash(uid, API_HASH)
        return web.json_response({"status": "success"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

async def _api_tg_logout(request):
    data = await request.json()
    uid = int(data.get("user_id", 0))
    
    uclient = USER_CLIENTS.pop(uid, None)
    if uclient:
        try: await uclient.log_out()
        except: pass
        try: await uclient.stop()
        except: pass
        
    await db.set_session(uid, None)
    await db.set_api_id(uid, None)
    await db.set_api_hash(uid, None)
    
    user_tasks = list(ACTIVE_PROCESSES.get(uid, {}).keys())
    for tid in user_tasks: CANCEL_FLAGS[tid] = True
    batch_temp.IS_BATCH[uid] = True
    try: await db.db.active_tasks.delete_many({"user_id": uid})
    except: pass
    
    return web.json_response({"status": "success"})

async def _api_chats_handler(request):
    uid = int(request.query.get("user_id", 0))
    uclient = USER_CLIENTS.get(uid)
    
    # 🟢 DYNAMIC WAKE-UP FOR WEB DASHBOARD
    if not uclient or not uclient.is_connected:
        session_str = await db.get_session(uid)
        if not session_str:
            return web.json_response({"status": "error", "message": "Not connected to Telegram. Please login."})
        
        try:
            api_id = await db.get_api_id(uid) or API_ID
            api_hash = await db.get_api_hash(uid) or API_HASH
            uclient = Client(f"User_{uid}", session_string=session_str, api_id=api_id, api_hash=api_hash, workers=4, ipv6=False)
            uclient.add_handler(MessageHandler(user_watcher_handler, filters.channel | filters.group | filters.private))
            await uclient.start()
            USER_CLIENTS[uid] = uclient
        except Exception as e:
            return web.json_response({"status": "error", "message": f"Session invalid: {e}"})

    chat_list = []
    count = 0
    try:
        # Limited to 500 so the API doesn't crash, and yields to the server every 25 chats so nothing freezes.
        async for d in uclient.get_dialogs(limit=500):
            name = d.chat.title or d.chat.first_name or "Unknown"
            c_type = d.chat.type
            
            cat = "👤 User" if c_type == enums.ChatType.PRIVATE else ("📢 Channel" if c_type == enums.ChatType.CHANNEL else ("🤖 Bot" if c_type == enums.ChatType.BOT else "👥 Group"))
            chat_list.append({"id": str(d.chat.id), "name": f"[{cat}] {name}"})
            
            count += 1
            if count % 25 == 0:
                await asyncio.sleep(0) # This tells the server to breathe!
    except Exception as e: 
        return web.json_response({"status": "error", "message": str(e)})
        
    return web.json_response({"status": "success", "chats": chat_list})

async def _api_speedtest_handler(request):
    try:
        uid = int(request.query.get("user_id", 0))
    except:
        uid = 0
    
    session_str = await db.get_session(uid)
    if not session_str and uid not in ADMINS:
        return web.json_response({"status": "error", "message": "Unauthorized"})

    def run_speedtest_sync():
        try:
            st = speedtest.Speedtest()
            st.get_best_server()
            st.download()
            st.upload()
            st.results.share()
            return st.results.dict(), None
        except Exception as e:
            return None, str(e)

    result, error = await asyncio.to_thread(run_speedtest_sync)
    if error or not result:
        return web.json_response({"status": "error", "message": error or "Speedtest failed"})

    dl_mbps = result['download'] / 1_000_000
    ul_mbps = result['upload'] / 1_000_000
    
    return web.json_response({
        "status": "success",
        "download": f"{dl_mbps:.2f} Mbps",
        "upload": f"{ul_mbps:.2f} Mbps",
        "ping": f"{result['ping']} ms",
        "server": f"{result['server']['name']} ({result['server']['country']})",
        "sponsor": result['server']['sponsor'],
        "share_image": result.get("share", "")
    })

def _get_sos_sync():
    """Fetches system OS and IO stats safely in a background thread."""
    try:
        with open("/etc/os-release") as f:
            os_info = dict(line.strip().split("=", 1) for line in f if "=" in line)
        os_name = os_info.get("PRETTY_NAME", f'"{platform.system()} {platform.release()}"').strip('"')
    except Exception:
        os_name = f"{platform.system()} {platform.release()}"
    return os_name, psutil.virtual_memory(), psutil.disk_usage('/'), psutil.net_io_counters()

async def _api_sos_handler(request):
    try:
        uid = int(request.query.get("user_id", 0))
    except:
        uid = 0
        
    session_str = await db.get_session(uid)
    if not session_str and uid not in ADMINS:
        return web.json_response({"status": "error", "message": "Unauthorized"})

    m_down, m_up, m_total, month_name = await db.get_monthly_bandwidth()
    os_name, mem, disk, net = await asyncio.to_thread(_get_sos_sync)

    return web.json_response({
        "status": "success",
        "os": os_name,
        "hostname": socket.gethostname(),
        "kernel": platform.uname().release,
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_percent": mem.percent,
        "ram_used": _pretty_bytes(mem.used),
        "ram_total": _pretty_bytes(mem.total),
        "disk_percent": disk.percent,
        "disk_free": _pretty_bytes(disk.free),
        "disk_total": _pretty_bytes(disk.total),
        "boot_download": _pretty_bytes(net.bytes_recv),
        "boot_upload": _pretty_bytes(net.bytes_sent),
        "month_name": month_name,
        "month_download": _pretty_bytes(m_down),
        "month_upload": _pretty_bytes(m_up),
        "month_total": _pretty_bytes(m_total)
    })

PWA_MANIFEST = {
    "name": "Destiny TG Forwarder",
    "short_name": "TG Portal",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#000000",
    "theme_color": "#000000",
    "orientation": "portrait-primary",
    "icons": [
        {
            "src": "https://cdn-icons-png.flaticon.com/512/2111/2111646.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "https://cdn-icons-png.flaticon.com/512/2111/2111646.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ]
}

async def _manifest_handler(request):
    return web.json_response(PWA_MANIFEST)

async def _sw_handler(request):
    sw_code = "self.addEventListener('fetch', function(e) {});"
    return web.Response(text=sw_code, content_type='application/javascript')

async def start_koyeb_health_check(host: str = "0.0.0.0"):
    if web is None: return
    global PORT
    app_web = web.Application()
    app_web.router.add_get("/manifest.json", _manifest_handler)
    app_web.router.add_get("/sw.js", _sw_handler)
    app_web.router.add_get("/", _dashboard_ui_handler)
    app_web.router.add_get("/health", _dashboard_ui_handler)
    app_web.router.add_get("/api/stats", _api_stats_handler)
    app_web.router.add_get("/api/logs", _api_logs_handler)
    app_web.router.add_get("/api/chats", _api_chats_handler)
    app_web.router.add_get("/api/speedtest", _api_speedtest_handler)
    app_web.router.add_get("/api/sos", _api_sos_handler)
    app_web.router.add_get("/api/logs/download", _api_download_log_handler)
    app_web.router.add_post("/api/auth/login", _api_login_handler)
    app_web.router.add_post("/api/auth/forgot", _api_forgot_password_handler)
    app_web.router.add_post("/api/auth/password", _api_password_handler)
    app_web.router.add_post("/api/tg/send_code", _api_tg_send_code)
    app_web.router.add_post("/api/tg/verify", _api_tg_verify_code)
    app_web.router.add_post("/api/tg/verify_2fa", _api_tg_verify_2fa)
    app_web.router.add_post("/api/tg/logout", _api_tg_logout)
    app_web.router.add_post("/api/task/add", _api_add_task)
    app_web.router.add_post("/api/task/cancel", _api_cancel_task)
    app_web.router.add_post("/api/watcher/add", _api_add_watcher)
    app_web.router.add_post("/api/watcher/cancel", _api_cancel_watcher)
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, host, PORT)
    await site.start()
    logger.info(f"🌐 Full-Stack Destiny TG Forwarder started on port {PORT}...")

# ==============================================================================
# --- MEDIAINFO HANDLER (Admin Only) ---
# ==============================================================================

section_dict = {"General": "🗒", "Video": "🎞", "Audio": "🔊", "Text": "🔠", "Menu": "🗃"}

def parseinfo(out, size):
    tc, trigger = "", False
    size_mb = size / (1024 * 1024)
    size_line = f"File size                                 : {size_mb:.2f} MiB"
    
    lines = out.split("\n")
    for line in lines:
        line = line.strip()
        if not line: continue
        
        found_section = False
        for section, emoji in section_dict.items():
            if line.startswith(section):
                trigger = True
                found_section = True
                if not line.startswith("General"):
                    tc += "</pre><br>"
                tc += f"<h4>{emoji} {line.replace('Text', 'Subtitle')}</h4>"
                break
        
        if found_section: continue

        if line.startswith("File size"):
            line = size_line
            
        if trigger:
            tc += "<br><pre>"
            trigger = False
        else:
            tc += html.escape(line) + "\n"
            
    tc += "</pre><br>"
    return tc

async def partial_download_tg(client, message, file_path, limit_mb=15):
    media_obj = message.document or message.video or message.audio or message.photo
    file_size = getattr(media_obj, 'file_size', 0)
    
    if file_size <= limit_mb * 1024 * 1024:
        await message.download(file_name=str(file_path))
    else:
        chunk_size = 1048576
        total_chunks = math.ceil(file_size / chunk_size)
        
        with open(file_path, "wb") as f:
            async for chunk in client.stream_media(message, limit=5):
                f.write(chunk)
            if total_chunks > 5:
                offset = total_chunks - 5
                f.seek(offset * chunk_size)
                async for chunk in client.stream_media(message, offset=offset, limit=5):
                    f.write(chunk)

async def partial_download_http(url, file_path, limit_mb=15):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=20) as resp:
            resp.raise_for_status()
            detected_name = "Stream_File.dat"
            cd = resp.headers.get("Content-Disposition")
            if cd:
                fname_match = re.search(r'filename="?([^"]+)"?', cd)
                if fname_match: detected_name = fname_match.group(1)
            
            if detected_name == "Stream_File.dat":
                parsed = urlparse(url)
                path_name = os.path.basename(parsed.path)
                if path_name: detected_name = unquote(path_name)
            
            file_size = int(resp.headers.get("Content-Length", 0))

        limit_bytes = limit_mb * 1024 * 1024
        if 0 < file_size <= limit_bytes:
            async with session.get(url, headers=headers) as resp:
                with open(file_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
        elif file_size > limit_bytes:
            with open(file_path, "wb") as f:
                h_start = headers.copy()
                h_start["Range"] = "bytes=0-5000000"
                async with session.get(url, headers=h_start) as resp:
                    f.write(await resp.read())
                h_end = headers.copy()
                h_end["Range"] = f"bytes={file_size - 5000000}-{file_size}"
                async with session.get(url, headers=h_end) as resp:
                    f.seek(file_size - 5000000)
                    f.write(await resp.read())
        else:
            async with session.get(url, headers=headers) as resp:
                with open(file_path, "wb") as f:
                    current_bytes = 0
                    async for chunk in resp.content.iter_chunked(1024 * 1024):
                        f.write(chunk)
                        current_bytes += len(chunk)
                        if current_bytes > limit_bytes: break
        return file_size, detected_name

@app.on_message(filters.command(["mediainfo", "mi"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def mediainfo_handler(client: Client, message: Message):
    url = None
    media_msg = None
    
    if len(message.command) > 1:
        potential_url = message.command[1]
        if potential_url.startswith("http"): url = potential_url

    if not url and message.reply_to_message:
        replied = message.reply_to_message
        if replied.text:
            match = re.search(r'https?://\S+', replied.text)
            if match: url = match.group(0)
        elif replied.document or replied.video or replied.audio or replied.photo:
            media_msg = replied

    if not url and not media_msg:
        try:
            return await message.reply(
                "❌ **How to use MediaInfo:**\n\n"
                "This command analyzes a media file and gives you a technical breakdown (resolution, codec, bitrate, etc.) published to Telegraph.\n\n"
                "**Examples:**\n"
                "• Quick Reply: Reply to any video or document with `/mi`\n"
                "• Direct Link: `/mi https://example.com/video.mp4`"
            )
        except FloodWait: return

    try:
        status_msg = await message.reply(f"<i>Generating MediaInfo...</i>", parse_mode=enums.ParseMode.HTML)
    except FloodWait as e:
        return logger.warning(f"Silently blocked /mi init due to FloodWait: {e.value}s")
    
    temp_filename = f"partial_{message.id}_{int(time.time())}.dat"
    file_path = Path(os.getcwd()) / temp_filename
    
    file_name_display = "Unknown File"
    file_size_display = 0

    try:
        if url:
            try:
                file_size_display, detected_name = await partial_download_http(url, file_path, limit_mb=15)
                file_name_display = detected_name
            except Exception as e:
                await status_msg.edit_text(f"❌ Link download failed: {e}")
                return
        else:
            media_obj = media_msg.document or media_msg.video or media_msg.audio or media_msg.photo
            file_name_display = getattr(media_obj, 'file_name', 'Telegram_Media')
            file_size_display = getattr(media_obj, 'file_size', 0)
            
            try:
                await partial_download_tg(client, media_msg, file_path, limit_mb=15)
            except Exception as e:
                logger.warning(f"MediaInfo stream failed, attempting full download: {e}", exc_info=True)
                await status_msg.edit_text("⚠️ Stream failed, trying full download...")
                await media_msg.download(file_name=str(file_path))

        real_ext = Path(file_name_display).suffix
        if real_ext:
            new_path = file_path.with_suffix(real_ext)
            file_path.rename(new_path)
            file_path = new_path

        cmd = ["mediainfo", str(file_path)]
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        raw_output = stdout.decode('utf-8', errors='ignore').strip()

        if not raw_output:
            await status_msg.edit_text("❌ Could not read metadata.")
            return

        raw_output = raw_output.replace(str(file_path), file_name_display)
        raw_output = raw_output.replace(str(file_path.absolute()), file_name_display)

        safe_file_name = html.escape(file_name_display)
        formatted_html = f"<h4>📌 {safe_file_name}</h4><br><br>"
        formatted_html += parseinfo(raw_output, file_size_display)

        try:
            token = load_telegraph_token()
            if not token:
                raise Exception("Telegraph token missing from config.")
                
            from telegraph.utils import html_to_nodes
            import socket
            import json # Ensure json is imported for dumps
            
            conn = aiohttp.TCPConnector(family=socket.AF_INET, force_close=True, enable_cleanup_closed=True)
            async with aiohttp.ClientSession(connector=conn) as session:
                
                # FIX 1 & 2: Telegraph strictly requires Form-Data (data=) 
                # and the 'content' field MUST be a stringified JSON array!
                payload = {
                    "access_token": token,
                    "title": "MediaInfo X",
                    "content": json.dumps(html_to_nodes(formatted_html)), # <-- THE MAGIC FIX
                    "return_content": "false"
                }
                
                max_retries = 4
                resp_data = None
                for attempt in range(max_retries):
                    try:
                        # FIX 3: Route directly to api.graph.org to bypass server IP Blocks
                        async with session.post("https://api.graph.org/createPage", data=payload, timeout=30) as resp:
                            resp_data = await resp.json()
                            if resp_data.get("ok"):
                                break
                            else:
                                err_msg = resp_data.get("error", "Unknown Telegraph Error")
                                # FIX 4: Handle FloodWait Gracefully (Like WZML)
                                if "FLOOD_WAIT" in err_msg:
                                    wait_time = int(err_msg.split("_")[-1])
                                    await asyncio.sleep(wait_time + 1)
                                    continue # Retry the loop!
                                raise Exception(err_msg)
                    except Exception as api_err:
                        if attempt == max_retries - 1:
                            raise api_err
                        await asyncio.sleep(2)
                
                # No string replacement needed since we directly uploaded to graph.org!
                final_link = resp_data["result"]["url"]
                    
            await status_msg.edit_text(
                f"✅ <b>MediaInfo Generated</b> 🦥\n\n"
                f"📄 <b>File:</b> {safe_file_name}\n"
                f"➲ <b>Link :</b> {final_link}",
                disable_web_page_preview=False,
                parse_mode=enums.ParseMode.HTML
            )

        except Exception as e:
            txt_path = file_path.with_suffix(".txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(raw_output)
            
            await client.send_document(
                chat_id=message.chat.id,
                document=str(txt_path),
                caption=f"✅ **MediaInfo Generated** 🦥\n(Telegraph API rejected connection. Sent as file)",
                reply_to_message_id=message.id
            )
            await status_msg.delete()
            if txt_path.exists(): os.remove(txt_path)

    except Exception as e:
        logger.error(f"MediaInfo generation crashed: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Error: {e}")
    finally:
        if file_path.exists():
            try: os.remove(file_path)
            except Exception as e: logger.debug(f"MediaInfo cleanup failed: {e}")

# ==============================================================================
# --- LIVE WATCHER ENGINE (WITH UNIVERSAL QUEUE & CATCH-UP) ---
# ==============================================================================

from pyrogram.handlers import MessageHandler

WATCHER_QUEUES = defaultdict(asyncio.Queue)
WATCHER_WORKERS = {}

async def start_watcher_worker(wid_str):
    if wid_str not in WATCHER_WORKERS:
        WATCHER_WORKERS[wid_str] = asyncio.create_task(watcher_worker_loop(wid_str))

async def watcher_worker_loop(wid_str):
    queue = WATCHER_QUEUES[wid_str]
    while True:
        try:
            msg_id = await queue.get()
            
            try: # 🟢 NESTED TRY-FINALLY: Guarantees task_done() is called exactly once
                watcher = await db.db.watchers.find_one({"_id": ObjectId(wid_str)})
                if not watcher:
                    continue

                owner_id = watcher["user_id"]
                watcher_db_id = watcher["_id"]
                source_id = watcher["source_id"]
                dest_id = watcher["dest_id"]
                dest_thread = watcher.get("dest_thread")
                delay = watcher.get("delay", 0)
                is_restricted = watcher.get("is_restricted", False)
                allowed_types = watcher.get("allowed_types", ["Video", "Document"])
                
                # Fetch fresh message object
                owner_client = USER_CLIENTS.get(owner_id)
                fetcher = owner_client if (owner_client and owner_client.is_connected) else app
                
                try:
                    msg = await fetcher.get_messages(source_id, msg_id)
                except Exception:
                    msg = None

                # 🟢 [CRUCIAL] Always advance the DB pointer
                await db.db.watchers.update_one({"_id": watcher_db_id}, {"$set": {"last_msg_id": msg_id}})

                if not msg or msg.empty:
                    continue

                msg_type = get_message_type(msg)
                if not msg_type:
                    continue

                is_content_protected = getattr(msg, "has_protected_content", False) or getattr(msg.chat, "has_protected_content", False)

                await db.db.watchers.update_one({"_id": watcher_db_id}, {"$inc": {"stats.detected": 1}})

                # 🟢 FILTER ENFORCEMENT
                if msg_type not in allowed_types:
                    await db.db.watchers.update_one({"_id": watcher_db_id}, {"$inc": {"stats.skipped": 1}})
                    continue

                # 🟢 DELAY ENFORCEMENT (Maintains exact chronological order)
                if delay > 0:
                    await asyncio.sleep(delay)

                processed_successfully = False

                if not is_restricted and not is_content_protected:
                    # --- UNRESTRICTED FAST FORWARDING ---
                    if getattr(msg, "media_group_id", None):
                        group_cache_key = f"{owner_id}_{msg.media_group_id}_{dest_id}"
                        if group_cache_key in WATCHER_MEDIA_GROUPS:
                            continue 
                        WATCHER_MEDIA_GROUPS[group_cache_key] = True

                    try:
                        await USER_FLOOD_LOCKS[owner_id].wait_if_locked()
                        
                        if getattr(msg, "media_group_id", None):
                            try: m_group = await fetcher.get_media_group(source_id, msg.id)
                            except: m_group = [msg]
                            group_size = len(m_group)

                            try:
                                copy_res = await safe_send(app, owner_id, dest_id, None, True, app.copy_media_group, chat_id=dest_id, from_chat_id=source_id, message_id=msg.id, message_thread_id=dest_thread)
                            except Exception:
                                if owner_client: copy_res = await safe_send(owner_client, owner_id, dest_id, None, False, owner_client.copy_media_group, chat_id=dest_id, from_chat_id=source_id, message_id=msg.id, message_thread_id=dest_thread)
                                else: copy_res = False
                            
                            if copy_res:
                                processed_successfully = True
                                if delay > 0 and group_size > 1: await asyncio.sleep(delay * (group_size - 1))
                                
                        else:
                            try:
                                copy_res = await safe_send(app, owner_id, dest_id, None, True, app.copy_message, chat_id=dest_id, from_chat_id=source_id, message_id=msg.id, message_thread_id=dest_thread)
                            except Exception:
                                if owner_client: copy_res = await safe_send(owner_client, owner_id, dest_id, None, False, owner_client.copy_message, chat_id=dest_id, from_chat_id=source_id, message_id=msg.id, message_thread_id=dest_thread)
                                else: copy_res = False
                            if copy_res: processed_successfully = True

                    except FloodWait as e:
                        USER_FLOOD_LOCKS[owner_id].set_lock(e.value + 5)
                        await asyncio.sleep(e.value + 5)
                        # 🟢 RETRY COPY AFTER SLEEP (Prevents instant fail to download mode)
                        try:
                            if getattr(msg, "media_group_id", None):
                                if owner_client: copy_res = await safe_send(owner_client, owner_id, dest_id, None, False, owner_client.copy_media_group, chat_id=dest_id, from_chat_id=source_id, message_id=msg.id, message_thread_id=dest_thread)
                            else:
                                if owner_client: copy_res = await safe_send(owner_client, owner_id, dest_id, None, False, owner_client.copy_message, chat_id=dest_id, from_chat_id=source_id, message_id=msg.id, message_thread_id=dest_thread)
                            if copy_res: processed_successfully = True
                        except: pass
                    except Exception as e:
                        logger.warning(f"Watcher fast copy failed: {e}. Falling back to download.")

                if processed_successfully:
                    await db.db.watchers.update_one({"_id": watcher_db_id}, {"$inc": {"stats.success": 1}})
                    continue

                # --- FALLBACK TO HEAVY DOWNLOAD/UPLOAD MODE ---
                try:
                    log_chat_id, log_topic_id = await get_fallback_log_chat(app, "BOT")
                    kwargs_status = {"chat_id": log_chat_id, "text": f"⬇️ **Watcher:** Processing ID `{msg.id}`..."}
                    if log_topic_id: kwargs_status["message_thread_id"] = log_topic_id
                    dummy_status = await app.send_message(**kwargs_status)

                    task_uuid = uuid.uuid4().hex
                    if owner_id not in ACTIVE_PROCESSES: ACTIVE_PROCESSES[owner_id] = {}
                    ACTIVE_PROCESSES[owner_id][task_uuid] = {
                        "user": "Watcher", "dest_title_name": watcher.get("dest_title", "Destination"),
                        "source_title": watcher.get("source_title", "Source"), "item": f"Live Watcher ID: {msg.id}", 
                        "started": time.time(), "is_watcher": True, "source_id": source_id
                    }

                    result = await handle_private(
                        client=app, acc=owner_client, message=msg, chatid=source_id, msgid=msg.id, index=1, total_count=1,
                        status_message=dummy_status, dest_chat_id=dest_id, dest_thread_id=dest_thread, delay=0,
                        user_id=owner_id, task_uuid=task_uuid, is_restricted=True, allowed_types=allowed_types
                    )
                    
                    if result == "SUCCESS" or result is True: await db.db.watchers.update_one({"_id": watcher_db_id}, {"$inc": {"stats.success": 1}})
                    elif result == "SKIPPED": await db.db.watchers.update_one({"_id": watcher_db_id}, {"$inc": {"stats.skipped": 1}})
                    else: await db.db.watchers.update_one({"_id": watcher_db_id}, {"$inc": {"stats.failed": 1}})

                    cleanup_task_memory(owner_id, task_uuid)
                    try: await dummy_status.delete()
                    except: pass
                except Exception as e:
                    logger.error(f"Watcher Fail for {owner_id}: {e}")
                    await db.db.watchers.update_one({"_id": watcher_db_id}, {"$inc": {"stats.failed": 1}})

            except Exception as outer_e:
                logger.error(f"Fatal error in worker loop for {wid_str}: {outer_e}")
            finally:
                # 🟢 CRITICAL: This is now the ONLY place task_done() is called
                queue.task_done()
        except Exception as loop_e:
            logger.error(f"Queue get error: {loop_e}")

async def process_watcher_message(client, message):
    chat_id = message.chat.id
    topic_id = getattr(message, "message_thread_id", None)

    cursor = await db.get_watchers_for_source(chat_id, topic_id)
    watchers = await cursor.to_list(length=100)

    # 🟢 FIX: Always merge global chat watchers (source_thread = None)
    # This prevents the bot from ignoring messages inside topics when the whole group is watched.
    if topic_id is not None:
        cursor_global = await db.get_watchers_for_source(chat_id, None)
        watchers.extend(await cursor_global.to_list(length=100))

    # 🟢 Live Listener ONLY pushes IDs to the queue now!
    for w in watchers:
        wid = str(w["_id"])
        await WATCHER_QUEUES[wid].put(message.id)
        await start_watcher_worker(wid)

async def user_watcher_handler(client, message):
    await process_watcher_message(client, message)

# ==============================================================================
# --- DASHBOARD UPDATER ---
# ==============================================================================
import datetime

WATCHER_RENDER_CACHE = {}
WATCHER_LAST_EDIT = {}

async def watcher_dashboard_updater():
    while True:
        await asyncio.sleep(30)
        try:
            # Find all watchers that have a linked dashboard message
            cursor = db.db.watchers.find({"dashboard_chat": {"$ne": None}, "dashboard_msg": {"$ne": None}})
            async for w in cursor:
                wid = str(w["_id"])
                current_stats = w.get("stats", {})
                
                now = time.time()
                last_edit = WATCHER_LAST_EDIT.get(wid, 0)
                
                # Compare to memory cache
                cached = WATCHER_RENDER_CACHE.get(wid)
                stats_changed = (cached != current_stats)
                
                # Only edit message if stats changed, OR force a heartbeat edit every 3 minutes
                if not stats_changed and (now - last_edit) < 180:
                    continue 

                WATCHER_RENDER_CACHE[wid] = dict(current_stats)
                WATCHER_LAST_EDIT[wid] = now
                
                time_str = datetime.datetime.now().strftime("%I:%M:%S %p")

                text = (
                    f"👀 **Live Watcher Dashboard**\n\n"
                    f"**Source:** `{w.get('source_title')}`\n"
                    f"**Destination:** `{w.get('dest_title')}`\n"
                    f"**Delay:** `{w.get('delay')}s` | **Restricted:** `{'Yes' if w.get('is_restricted') else 'No'}`\n"
                    f"**Filters:** `{', '.join(w.get('allowed_types', []))}`\n\n"
                    f"📊 **Session Statistics:**\n"
                    f"├ 📡 **Detected:** `{current_stats.get('detected', 0)}`\n"
                    f"├ ✅ **Success:** `{current_stats.get('success', 0)}`\n"
                    f"├ ⏭ **Skipped:** `{current_stats.get('skipped', 0)}`\n"
                    f"└ ❌ **Failed:** `{current_stats.get('failed', 0)}`\n\n"
                    f"*(📡 Listening for new messages...)*\n"
                    f"⏱ **Last Synced:** `{time_str}`"
                )
                try:
                    await app.edit_message_text(
                        chat_id=w["dashboard_chat"],
                        message_id=w["dashboard_msg"],
                        text=text
                    )
                except Exception as e:
                    if "MESSAGE_NOT_MODIFIED" in str(e): pass 
        except Exception as e:
            logger.error(f"Dashboard updater error: {e}")

# ==============================================================================
# --- MAIN ENTRY POINT ---
# ==============================================================================

INSTANCE_ID = uuid.uuid4().hex[:8]

async def cleanup_startup():
    folder = Path(f"./downloads_{INSTANCE_ID}")
    try:
        if folder.exists():
            shutil.rmtree(folder)
            logger.info(f"🧹 Startup: Cleared temporary downloads folder for {INSTANCE_ID}.")
    finally:
        folder.mkdir(parents=True, exist_ok=True)
    
async def main():
    global USER_CLIENTS
    
    await cleanup_startup()
    asyncio.create_task(cleanup_watchdog())
    logger.info("🛡️ Auto-Cleanup Watchdog Started") 

    # Attach the listener to the main bot so it functions without a User Session!
    app.add_handler(MessageHandler(user_watcher_handler, filters.channel | filters.group | filters.private))

    await app.start()
    logger.info("🤖 Bot Started") 
    
    logger.info("📝 Updating Bot Commands...")
    try:
        public_commands = [
            BotCommand("start", "⚡ Check if bot is alive"),
            BotCommand("help", "📚 View the detailed usage guide"),
            BotCommand("chats", "💬 List your chat & channel IDs"),
            BotCommand("dl", "📥 Download or forward from a link"),
            BotCommand("watch", "👀 Setup a live auto-forwarder"),
            BotCommand("watchers", "📋 List your active watchers"),
            BotCommand("unwatch", "🗑 Stop watching a source"),
            BotCommand("cancel", "🚫 Cancel an ongoing task"),
            BotCommand("login", "🔑 Login to your Telegram session"),
            BotCommand("logout", "🚪 Logout from your session")
        ]

        admin_commands = public_commands + [
            BotCommand("broadcast", "🗞 Broadcast a message to users"),
            BotCommand("botstats", "📊 Check detailed user & task stats"),
            BotCommand("status", "🖥 Check system RAM/CPU/Uptime"),
            BotCommand("log", "📄 Fetch backend bot logs"),
            BotCommand("pixel", "✨ Bypass Pixeldrain links"),
            BotCommand("sos", "⚙️ Deep System Statistics"),
            BotCommand("mediainfo", "🔍 Technical File MetaData"),
            BotCommand("speedtest", "🚀 Test Server Speed")
        ]

        await app.set_bot_commands(public_commands, scope=BotCommandScopeDefault())

        all_admins = set(ADMINS + SUDOS)
        
        for admin_id in all_admins:
            try:
                await app.set_bot_commands(
                    admin_commands, 
                    scope=BotCommandScopeChat(chat_id=admin_id)
                )
            except Exception as e:
                logger.warning(f"⚠️ Could not set commands for Admin {admin_id}: {e}")
                
        logger.info("✅ Commands Updated: Public vs Admin scopes set!")
        
    except Exception as e:
        logger.error(f"⚠️ Failed to set commands: {e}", exc_info=True)
    
    logger.info("🔄 Loading Sessions for Active Watchers...")
    
    active_watcher_users = set()
    cursor = await db.get_all_watchers()
    async for w in cursor:
        active_watcher_users.add(w['user_id'])

    for user_id in active_watcher_users:
        user_session = await db.get_session(user_id)
        if not user_session:
            continue
            
        try:
            if user_id in USER_CLIENTS: continue

            logger.info(f"👤 Starting Watcher Session for: {user_id}")
            
            u_api = await db.get_api_id(user_id) or API_ID
            u_hash = await db.get_api_hash(user_id) or API_HASH
            
            user_client = Client(
                f"User_{user_id}", 
                session_string=user_session, 
                api_id=u_api, 
                api_hash=u_hash, 
                workers=4, 
                ipv6=False,
                no_updates=False 
            )
            
            user_client.add_handler(MessageHandler(user_watcher_handler, filters.channel | filters.group | filters.private))
            
            await user_client.start()
            USER_CLIENTS[user_id] = user_client
            logger.info(f"✅ Active: {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load {user_id}: {e}")

    logger.info(f"🔥 Total Live Listeners: {len(USER_CLIENTS)}")

    # Start both the Koyeb health check AND the Live Dashboard Updater
    asyncio.create_task(start_koyeb_health_check())
    asyncio.create_task(watcher_dashboard_updater())
    logger.info("📊 Live Watcher Dashboard Updater Started")
    
    # ==========================================
    # --- 🟢 WATCHER CATCH-UP ENGINE ---
    # ==========================================
    logger.info("🔄 Checking Watchers for missed messages (Catch-Up Engine)...")
    watcher_cursor = await db.get_all_watchers()
    async for w in watcher_cursor:
        wid = str(w["_id"])
        source_id = w["source_id"]
        last_processed = w.get("last_msg_id", 0)
        owner_id = w["user_id"]
        
        owner_client = USER_CLIENTS.get(owner_id)
        fetcher = owner_client if (owner_client and owner_client.is_connected) else app
        
        try:
            latest_msg_id = 0
            async for m in fetcher.get_chat_history(source_id, limit=1):
                latest_msg_id = m.id
                
            if latest_msg_id > last_processed and last_processed > 0:
                missed_count = latest_msg_id - last_processed
                logger.info(f"⚡ Watcher {wid} missed {missed_count} messages while offline. Queueing catch-up...")
                
                # Pre-fill the queue chronologically with missed messages
                for missing_id in range(last_processed + 1, latest_msg_id + 1):
                    await WATCHER_QUEUES[wid].put(missing_id)
                    
            # Ensure the worker is running to process the backlog AND future live messages
            await start_watcher_worker(wid)
            
        except Exception as e:
            logger.warning(f"Could not fetch history for Watcher Catch-up {wid}: {e}")
            await start_watcher_worker(wid) # Start it anyway for live messages

    # ==========================================
    # --- 🟢 BATCH AUTO-RESUME ENGINE ---
    # ==========================================
    logger.info("🔄 Checking database for interrupted batch tasks...")
    pending_tasks = await db.get_all_active_tasks()
    async for task in pending_tasks:
        t_user_id = task["user_id"]
        t_uuid = task["task_uuid"]
        
        log_msg = (
            f"♻️ **AUTO-RESUME ACTIVATED!**\n"
            f"🤖 **User ID:** `{t_user_id}`\n"
            f"📁 **Source:** `{task.get('source_title', 'Unknown')}`\n"
            f"🎯 **Destination:** `{task.get('dest_title', 'Unknown')}`\n"
            f"▶️ **Resuming From ID:** `{task['current_msg_id']}`"
        )
        
        # Send logs to Server and User!
        await send_log(log_msg)
        try:
            await app.send_message(t_user_id, log_msg)
        except Exception:
            pass
            
        # Spawn the task directly in the background
        asyncio.create_task(
            process_links_logic(
                client=app,
                message=None, # Headless execution!
                text=task["link"],
                dest_chat_id=task["dest_chat_id"],
                dest_thread_id=task["dest_thread_id"],
                dest_title=task["dest_title"],
                delay=task["delay"],
                acc_user_id=t_user_id,
                task_uuid=t_uuid,
                is_restricted=task["is_restricted"],
                allowed_types=task["allowed_types"],
                resume_from_id=task["current_msg_id"],
                saved_source_title=task.get("source_title")
            )
        )
        logger.info(f"▶️ Auto-Resumed task {t_uuid} for User {t_user_id}")

    await idle()
    
    await app.stop()
    for uid, client in USER_CLIENTS.items():
        try: await client.stop()
        except: pass
        
if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        pass
