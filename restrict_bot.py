# -*- coding: utf-8 -*-
import os
import psutil
import time
import asyncio
import json
import uvloop

# --- 1. EVENT LOOP INITIALIZATION (FOR PYROFORK/WZGRAM) ---
uvloop.install()
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())
# ----------------------------------------------------------

# --- 2. BULLETPROOF KURIGRAM CRASH FIX ---
import pyrogram.enums
if not hasattr(pyrogram.enums, "ButtonStyle"):
    class DummyButtonStyle:
        DEFAULT = 0
    pyrogram.enums.ButtonStyle = DummyButtonStyle
# -----------------------------------------

import re
import shutil
import subprocess
import gc
import datetime
import uuid
from pathlib import Path
from collections import defaultdict, OrderedDict
import motor.motor_asyncio

from pyrogram import Client, filters, enums, idle
from pyrogram.raw.functions.messages import GetDialogs
from pyrogram.raw.types import InputPeerEmpty

# --- UNIVERSAL FORK & PYROMOD SUBSCRIPTABLE PATCH ---
# This bridges the gap between Pyromod's dictionary expectations 
# and modern Telegram forks' custom ListenerRegistry objects.
try:
    from pyrogram.dispatcher import ListenerRegistry
    
    if not hasattr(ListenerRegistry, "__getitem__"):
        def _reg_getitem(self, key):
            for attr in ["registry", "_registry", "data", "_data", "listeners"]:
                val = getattr(self, attr, None)
                if isinstance(val, dict):
                    return val[key]
            return getattr(self, key, {})
        ListenerRegistry.__getitem__ = _reg_getitem

    if not hasattr(ListenerRegistry, "__setitem__"):
        def _reg_setitem(self, key, value):
            for attr in ["registry", "_registry", "data", "_data", "listeners"]:
                val = getattr(self, attr, None)
                if isinstance(val, dict):
                    val[key] = value
                    return
            setattr(self, key, value)
        ListenerRegistry.__setitem__ = _reg_setitem

    if not hasattr(ListenerRegistry, "get"):
        def _reg_get(self, key, default=None):
            try:
                return self[key]
            except (KeyError, TypeError):
                return default
        ListenerRegistry.get = _reg_get
except ImportError:
    pass
# --------------------------------------------------

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
from urllib.parse import unquote, urlparse, quote
import platform
import socket
import logging                          
from telegraph import Telegraph
from bson.objectid import ObjectId      # <-- REQUIRED FOR UNIQUE ROUTING
import speedtest                        # <-- REQUIRED FOR SPEEDTEST
import numpy as np
from scipy.io import wavfile
from scipy.signal import welch, stft
from PIL import Image, ImageDraw, ImageFont
from mutagen import File as MutagenFile
import base64

try:
    import pyloudnorm as pyln
    HAS_PYLN = True
except ImportError:
    HAS_PYLN = False

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
        delay=3,
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

import inspect
import os

def get_transmission_kwargs(workers: int = 8) -> dict:
    """
    Dynamically detects fork support for concurrent transmissions.
    Uses MAX_CONCURRENT_TRANSMISSIONS from .env, or scales automatically via CPU cores.
    """
    sig = inspect.signature(Client.__init__)
    if "max_concurrent_transmissions" not in sig.parameters:
        return {}

    env_val = os.environ.get("MAX_CONCURRENT_TRANSMISSIONS", "").strip()
    if env_val.isdigit() and int(env_val) > 0:
        val = int(env_val)
    else:
        cpu_cores = os.cpu_count() or 2
        val = min(workers, max(2, cpu_cores * 2))

    return {"max_concurrent_transmissions": val}

bot_workers = min(32, (os.cpu_count() or 2) * 8)

app = Client(
    name="RestrictedBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=bot_workers,
    sleep_threshold=20,
    ipv6=False,
    **get_transmission_kwargs(workers=bot_workers)
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
    "log", "pixel", "sos", "mediainfo", "mi", "chats", "speedtest", "spectrogram", "spec"
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
WATCHER_DEDUPE_CACHE = defaultdict(OrderedDict)  # bounded per-watcher event dedupe
WATCHER_DEDUPE_LIMIT = 2000

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
    
    msg_range = None
    
    # 🟢 FIX: Handle both Comma-Separated Links AND Hyphen Ranges seamlessly
    if "," in raw:
        links = [l.strip() for l in raw.split(",")]
        raw = links[0] # Base the core logic off the first link
        last_link = links[-1]
        try:
            start_id = int(raw.rstrip("/").split("/")[-1].split("?")[0])
            end_id = int(last_link.rstrip("/").split("/")[-1].split("?")[0])
            if start_id <= end_id:
                msg_range = (start_id, end_id)
        except: pass
    else:
        m = re.search(r"/(\d+)\s*(?:-|to)\s*(\d+)$", raw, re.IGNORECASE)
        if m:
            try:
                start_id = int(m.group(1))
                end_id = int(m.group(2))
                if start_id <= end_id:
                    msg_range = (start_id, end_id)
                raw = raw[:m.start(0)] + "/" + m.group(1) # Clean tail so it parses as a normal link
            except: pass

    # Normal parsing for the base link
    if "t.me/" in raw:
        raw = raw.split("t.me/")[-1]
    elif "telegram.me/" in raw:
        raw = raw.split("telegram.me/")[-1]
        
    if raw.startswith("s/"):
        raw = raw[2:]
        
    raw = raw.split("?", 1)[0].strip("/")

    is_private_c = raw.startswith("c/")
    if is_private_c:
        clean = raw[2:]
        parts = clean.split("/")
        source_id = int("-100" + parts[0])
        topic_id = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else None
        
        msg_id = None
        last_segment = parts[-1].strip()
        if last_segment.isdigit():
            msg_id = int(last_segment)
            
        return {
            "kind": "private_c",
            "join_target": None,
            "chat_id": source_id,
            "topic_id": topic_id,
            "msg_id": msg_id,
            "msg_range": msg_range, # 🟢 Pass the clean range mapping
        }

    parts = raw.split("/")
    username = parts[0]
    topic_id = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else None
    
    msg_id = None
    last_segment = parts[-1].strip()
    if last_segment.isdigit():
        msg_id = int(last_segment)

    if username.startswith("+") or "joinchat" in username:
        return {
            "kind": "invite",
            "join_target": f"https://t.me/{raw}",
            "chat_id": None,
            "topic_id": topic_id,
            "msg_id": msg_id,
            "msg_range": msg_range,
        }

    return {
        "kind": "public",
        "join_target": username,
        "chat_id": username,
        "topic_id": topic_id,
        "msg_id": msg_id,
        "msg_range": msg_range,
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
    
    if "t.me/" in raw:
        raw = raw.split("t.me/")[-1]
    elif "telegram.me/" in raw:
        raw = raw.split("telegram.me/")[-1]
        
    if raw.startswith("s/"):
        raw = raw[2:]
        
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
        # 🟢 FIX: Ensure it is explicitly a Bot DM (len == 1), not a public channel ending in "bot"
        if "t.me/b/" in link_text or (str(parts[0]).lower().endswith("bot") and len(parts) == 1):
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
            msg = None
            bot_err_saved = None
            try:
                msg = await check_client.get_messages(chat_id, msg_id)
            except Exception as e:
                bot_err_saved = e

            if (bot_err_saved or not msg or msg.empty) and check_client == app and user_session:
                api_id = await db.get_api_id(user_id) or API_ID
                api_hash = await db.get_api_hash(user_id) or API_HASH
                check_client = Client(":memory:", session_string=user_session, api_id=api_id, api_hash=api_hash, no_updates=True, ipv6=False)
                await check_client.connect()
                is_temp_client = True
                try:
                    msg = await check_client.get_messages(chat_id, msg_id)
                    bot_err_saved = None
                except Exception as user_err:
                    bot_err_saved = user_err
                    
            if bot_err_saved:
                raise bot_err_saved

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

# ==============================================================================
# --- NEW: GOFILE UPLOADER & FFMPEG REMUX ENGINE ---
# ==============================================================================
import aiohttp
import os

async def upload_to_gofile(file_path: str):
    """Uploads a file to GoFile.io and returns the public download link."""
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.gofile.io/servers") as resp:
            data = await resp.json()
            if data.get("status") != "ok": raise Exception("Failed to get GoFile server")
            server = data["data"]["servers"][0]["name"]
            
        upload_url = f"https://{server}.gofile.io/contents/uploadfile"
        with open(file_path, 'rb') as f:
            form = aiohttp.FormData()
            form.add_field('file', f, filename=os.path.basename(file_path))
            async with session.post(upload_url, data=form) as resp:
                upload_data = await resp.json()
                if upload_data.get("status") == "ok":
                    return upload_data["data"]["downloadPage"]
                raise Exception(f"GoFile Error: {upload_data}")

async def process_remux(input_file, output_file, stream_config):
    """Instantly reshuffles, delays, and renames streams without re-encoding."""
    base_cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    inputs = ["-i", input_file]
    maps_and_meta = []
    
    input_count = 1
    out_idx = 0
    for track in stream_config:
        delay_ms = int(track.get("delay", 0))
        # If delay is applied, we must load the input file again with -itsoffset
        if delay_ms != 0:
            delay_sec = delay_ms / 1000.0
            inputs.extend(["-itsoffset", str(delay_sec), "-i", input_file])
            src_id = input_count
            input_count += 1
        else:
            src_id = 0
            
        idx = str(track['index']).replace('v:', '').replace('a:', '').replace('s:', '')
        maps_and_meta.extend(["-map", f"{src_id}:{idx}"])
        
        if track.get("title") and track.get("title").lower() != "skip":
            maps_and_meta.extend([f"-metadata:s:{out_idx}", f"title={track['title']}"])
            
        out_idx += 1
        
    final_cmd = base_cmd + inputs + maps_and_meta + ["-c", "copy", output_file]
    proc = await asyncio.create_subprocess_exec(*final_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    
    if proc.returncode != 0: 
        raise Exception(err.decode())
    return output_file
# ==============================================================================

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

CACHED_WEB_URL = None

@app.on_message(filters.command(["start"]) & (filters.private | filters.group))
async def send_start(client: Client, message: Message):
    global CACHED_WEB_URL
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
    
    # 🟢 UNIVERSAL URL AUTO-DETECTOR (HuggingFace, Render, Koyeb, Railway, Oracle/VPS, Custom)
    if not CACHED_WEB_URL:
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
                CACHED_WEB_URL = f"https://{raw_url}"
            else:
                CACHED_WEB_URL = raw_url
        else:
            # 🟢 ORACLE / VPS PUBLIC IP DETECTOR
            try:
                import urllib.request
                # Fetches the VPS Public IP and caches it forever so it's instantly ready
                public_ip = urllib.request.urlopen('https://api.ipify.org', timeout=3).read().decode('utf8')
                CACHED_WEB_URL = f"http://{public_ip}:{PORT}"
            except Exception as e:
                logger.warning(f"Could not detect public IP automatically: {e}")
                CACHED_WEB_URL = f"http://127.0.0.1:{PORT}"

    web_url = CACHED_WEB_URL

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
            # secure=True forces HTTPS to bypass datacenter port blocks
            st = speedtest.Speedtest(secure=True)
            st.get_best_server()
            st.download()
            st.upload()
            try:
                # Silently ignore image generation if Speedtest blocks the datacenter IP
                st.results.share() 
            except Exception:
                pass 
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

# --- UNIVERSAL LISTENER EXCEPTION MAPPING ---
try:
    from pyromod.exceptions import ListenerStopped
except ImportError:
    class ListenerStopped(Exception): pass

try:
    from pyrogram.errors import ListenerCanceled as NativeListenerStopped
except ImportError:
    class NativeListenerStopped(Exception): pass
# --------------------------------------------

@app.on_callback_query(filters.regex("^cancel_login$"))
async def cancel_login_cb(client, query):
    user_id = query.from_user.id
    
    # Attempt to kill the Pyromod or Native .ask() listener instantly
    try:
        if hasattr(client, "stop_listening"):
            await client.stop_listening(chat_id=user_id)
        elif hasattr(client, "cancel_listener"):
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
        try:
            me_auth = await client_auth.get_me()
            # 🟢 ENFORCE ID MATCH: Prevent cross-account chat leaks!
            if me_auth.id != user_id:
                await bot.send_message(user_id, f"⚠️ **Telegram ID Mismatch!**\n\nYou are chatting with me using ID `{user_id}`, but the phone number you entered belongs to ID `{me_auth.id}`.\n\nTo prevent cross-account chat mix-ups, you must log in using the exact same account you are chatting from!")
                await client_auth.disconnect()
                return
            is_prem = getattr(me_auth, "is_premium", False)
            first_name = me_auth.first_name or "User"
        except Exception:
            is_prem = False
            first_name = "User"

        string_session = await client_auth.export_session_string()
        await client_auth.disconnect()
        
        if len(string_session) < SESSION_STRING_SIZE:
            return await bot.send_message(user_id, '❌ **Fatal Error:** Invalid session string generated.')
            
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
    except (ListenerStopped, NativeListenerStopped, asyncio.CancelledError):
        # Silently caught when Cancel button is pressed or task is natively cancelled by the fork
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
    
    parsed = _parse_source_link(link_text)
    source_thread_id = parsed.get("topic_id")
    
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
    # 🟢 WZGRAM FALLBACK FIX: Prevent capturing unknown commands as links!
    text_content = message.text or message.caption or ""
    if text_content.startswith("/"):
        return
        
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
        [InlineKeyboardButton("🛠 Inspect & Edit Media", callback_data="dest_remux")],
        [InlineKeyboardButton("❌ Cancel Setup", callback_data="cancel_setup")]
    ]

@app.on_callback_query(filters.regex("^dest_remux$"))
async def remux_tg_callback(client: Client, query):
    user_id = query.from_user.id
    if user_id not in PENDING_TASKS: return await query.answer("Expired.", show_alert=True)
    link = PENDING_TASKS[user_id]["link"]
    
    await query.message.edit("🔎 **Probing Media Tracks...**")
    
    try:
        is_tg = _is_tg_link(link)
        if is_tg:
            parsed = _parse_source_link(link)
            probe_url = f"http://127.0.0.1:{PORT}/api/tg_stream?user_id={user_id}&chat_id={parsed['chat_id']}&msg_id={parsed['msg_id']}"
        else:
            from urllib.parse import quote
            probe_url = f"http://127.0.0.1:{PORT}/api/direct_stream?user_id={user_id}&url={quote(link, safe='')}"
            
        pdata = await _run_ffprobe_json(probe_url, fast=True)
        streams = pdata.get("streams", [])
        
        text = "🛠 **Media Inspector & Editor**\n\n**Available Tracks:**\n"
        for s in streams:
            idx = s.get("index")
            c_type = s.get("codec_type", "unknown").upper()
            c_name = s.get("codec_name", "")
            lang = s.get("tags", {}).get("language", "")
            title = s.get("tags", {}).get("title", "")
            text += f"• `{idx}` : **{c_type}** ({c_name}) {lang} *{title}*\n"
            
        text += "\n✏️ **Reply with your configuration.**\nFormat: `index: title=New Name, delay=500` separated by `|`.\n*Example:* `0 | 1: title=English Dub, delay=-200 | 2`\n\n*(Send /cancel to abort)*"
        
        config_msg = await app.ask(user_id, text, timeout=300)
        if config_msg.text.startswith('/'): return await config_msg.reply("Cancelled.")
        
        raw_config = config_msg.text.split('|')
        parsed_config = []
        for track in raw_config:
            parts = track.split(':')
            track_dict = {"index": parts[0].strip()}
            if len(parts) > 1:
                opts = parts[1].split(',')
                for opt in opts:
                    if '=' in opt:
                        k, v = opt.split('=', 1)
                        track_dict[k.strip().lower()] = v.strip()
            parsed_config.append(track_dict)
            
        name_msg = await app.ask(user_id, "✏️ **Send the NEW File Name (with extension like .mkv):**\n*(Or send `skip` to keep the original name)*", timeout=120)
        if name_msg.text.startswith('/'): return await name_msg.reply("Cancelled.")
        
        PENDING_TASKS[user_id]["remux_config"] = parsed_config
        PENDING_TASKS[user_id]["remux_name"] = name_msg.text.strip()
        
        up_btns = [
            [InlineKeyboardButton("📤 Send to Telegram DM", callback_data="up_tg_remux")],
            [InlineKeyboardButton("☁️ Upload to GoFile.io", callback_data="up_gf_remux")]
        ]
        await name_msg.reply("🚀 **Where do you want to upload the finished file?**", reply_markup=InlineKeyboardMarkup(up_btns))
        
    except Exception as e:
        await query.message.reply(f"❌ Error: {e}")

@app.on_callback_query(filters.regex(r"^up_(tg|gf)_remux$"))
async def execute_remux_callback(client: Client, query):
    user_id = query.from_user.id
    dest_type = query.data.split("_")[1]
    task_data = PENDING_TASKS.get(user_id)
    if not task_data: return await query.answer("Expired.", show_alert=True)
    
    status_msg = await query.message.edit("⚙️ **Processing Media...**\n1️⃣ Downloading...\n2️⃣ Remuxing...\n3️⃣ Uploading...")
    
    import time
    from pathlib import Path
    import shutil
    
    temp_dir = Path(f"./temp_remux_{user_id}_{int(time.time())}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    new_name = task_data["remux_name"] if task_data["remux_name"].lower() != "skip" else "Edited_Media.mkv"
    input_file = temp_dir / "input_media.dat"
    output_file = temp_dir / sanitize_filename(new_name)
    
    try:
        is_tg = _is_tg_link(task_data["link"])
        if is_tg:
            parsed = _parse_source_link(task_data["link"])
            uclient = USER_CLIENTS.get(user_id)
            if not uclient or not uclient.is_connected:
                session_str = await db.get_session(user_id)
                u_api = await db.get_api_id(user_id) or API_ID
                u_hash = await db.get_api_hash(user_id) or API_HASH
                uclient = Client(f"User_{user_id}", session_string=session_str, api_id=u_api, api_hash=u_hash, ipv6=False)
                await uclient.start()
                USER_CLIENTS[user_id] = uclient
            msg = await uclient.get_messages(parsed["chat_id"], parsed["msg_id"])
            await uclient.download_media(msg, file_name=str(input_file))
        else:
            await full_download_http(task_data["link"], str(input_file))
            
        await status_msg.edit("⚙️ **Remuxing Tracks (Instant Copy)...**")
        await process_remux(str(input_file), str(output_file), task_data["remux_config"])
        
        await status_msg.edit("☁️ **Uploading to Destination...**")
        if dest_type == "gf":
            url = await upload_to_gofile(str(output_file))
            await status_msg.edit(f"✅ **Success! Uploaded to GoFile.**\n\n🔗 **Link:** {url}", disable_web_page_preview=True)
        else:
            await app.send_document(chat_id=user_id, document=str(output_file), caption=f"✅ **Remuxed:** {new_name}")
            await status_msg.delete()
            
    except Exception as e:
        await status_msg.edit(f"❌ **Error:** {str(e)}")
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)
    
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
            uclient.add_handler(MessageHandler(user_watcher_handler, filters.all))
            await uclient.start()
            USER_CLIENTS[user_id] = uclient
            await status.edit("🔄 <b>Session Active! Fetching your dialogs...</b>", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            return await status.edit(f"❌ <b>Session Expired or Broken:</b> <code>{e}</code>\nPlease run <code>/logout</code> and <code>/login</code> again.")
    else:
        status = await message.reply("🔄 <b>Fetching your chats... Please wait</b>", parse_mode=enums.ParseMode.HTML)

    users, groups, channels, bots = [], [], [], []

    async def execute_raw_pagination(target_folder_id):
        import pyrogram.raw.types as raw_types
        from pyrogram.raw.functions.messages import GetDialogs
        
        offset_date = 0
        offset_id = 0
        offset_peer = raw_types.InputPeerEmpty()

        while True:
            try:
                response = await uclient.invoke(
                    GetDialogs(
                        offset_date=offset_date,
                        offset_id=offset_id,
                        offset_peer=offset_peer,
                        limit=100,
                        hash=0,
                        folder_id=target_folder_id
                    ),
                    sleep_threshold=60
                )
                
                if not getattr(response, "dialogs", None):
                    break

                resolved_users = {u.id: u for u in getattr(response, "users", [])}
                resolved_chats = {c.id: c for c in getattr(response, "chats", [])}

                for dialog in response.dialogs:
                    peer = dialog.peer
                    raw_chat_id = getattr(peer, "channel_id", getattr(peer, "chat_id", getattr(peer, "user_id", None)))
                    if not raw_chat_id: continue

                    if hasattr(peer, "channel_id"):
                        chat_id = int(f"-100{raw_chat_id}")
                    elif hasattr(peer, "chat_id"):
                        chat_id = int(f"-{raw_chat_id}")
                    else:
                        chat_id = raw_chat_id
                    
                    title = "Unknown Object"
                    category = ""
                    
                    if chat_id > 0:
                        u = resolved_users.get(chat_id)
                        if u:
                            title = getattr(u, "first_name", None)
                            if not title:
                                title = "Unknown User"
                            if getattr(u, "last_name", None):
                                title += f" {u.last_name}"
                            category = "bot" if getattr(u, "bot", False) else "private"
                    else:
                        c = resolved_chats.get(abs(chat_id)) or resolved_chats.get(getattr(peer, "channel_id", 0)) or resolved_chats.get(getattr(peer, "chat_id", 0))
                        if c:
                            title = getattr(c, "title", None)
                            if not title:
                                title = "Unknown Group"
                            category = "channel" if getattr(c, "broadcast", False) else "group"

                    line = f"• <b>{html.escape(title)}</b> │ <code>{chat_id}</code>"
                    
                    if "group" in category or "supergroup" in category: groups.append(line)
                    elif "channel" in category: channels.append(line)
                    elif "bot" in category: bots.append(line)
                    elif "private" in category: users.append(line)

                if len(response.dialogs) < 100:
                    break
                    
                last_dialog = response.dialogs[-1]
                offset_id = getattr(last_dialog, "top_message", 0)
                
                offset_date = 0
                for msg in response.messages:
                    if getattr(msg, "id", 0) == offset_id:
                        offset_date = getattr(msg, "date", 0)
                        break
                if offset_date == 0 and response.messages:
                    offset_date = getattr(response.messages[-1], "date", 0)

                last_peer = last_dialog.peer
                raw_last_id = getattr(last_peer, "channel_id", getattr(last_peer, "chat_id", getattr(last_peer, "user_id", 0)))
                
                if hasattr(last_peer, "channel_id"):
                    last_peer_id = int(f"-100{raw_last_id}")
                elif hasattr(last_peer, "chat_id"):
                    last_peer_id = int(f"-{raw_last_id}")
                else:
                    last_peer_id = raw_last_id

                try:
                    offset_peer = await uclient.resolve_peer(last_peer_id)
                except Exception:
                    if hasattr(last_peer, "channel_id"):
                        c = resolved_chats.get(raw_last_id)
                        offset_peer = raw_types.InputPeerChannel(channel_id=raw_last_id, access_hash=getattr(c, "access_hash", 0)) if c else raw_types.InputPeerEmpty()
                    elif hasattr(last_peer, "chat_id"):
                        offset_peer = raw_types.InputPeerChat(chat_id=raw_last_id)
                    else:
                        u = resolved_users.get(raw_last_id)
                        offset_peer = raw_types.InputPeerUser(user_id=raw_last_id, access_hash=getattr(u, "access_hash", 0)) if u else raw_types.InputPeerEmpty()

            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception as e:
                logger.warning(f"Raw dialog pagination error: {e}")
                break

    try:
        await execute_raw_pagination(0) # Standard Chats
        await execute_raw_pagination(1) # Archived Chats
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
        task_data["allowed_types"] = ALL_MSG_TYPES.copy()
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
        
    delay = max(3, min(int(task_data.get("delay", 3) or 3), 3600))
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

    if choice in ["speed_3", "speed_default"]:
        PENDING_TASKS[user_id]["delay"] = 3
        await show_filter_menu(query, user_id)
        return

async def process_speed_input(client: Client, message: Message):
    user_id = message.from_user.id
    text = message.text.strip()
    if not text.isdigit(): return await message.reply("❌ Numbers only.")
    
    delay = max(3, min(int(text), 3600)) 
    if user_id in PENDING_TASKS:
        PENDING_TASKS[user_id]["delay"] = delay
        await show_filter_menu(message, user_id)

async def finalize_watcher_setup(client, message, data, delay, user_id=None):
    delay = max(3, min(int(delay or 3), 3600))
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
            new_client.add_handler(MessageHandler(user_watcher_handler, filters.all))
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

async def handle_public_unrestricted(client: Client, acc, chatid: str, msgid: int, dest_chat_id, dest_thread_id, user_id, task_uuid, filter_thread_id, allowed_types, delay=3):
    """Fast-Path exclusively for Public Unrestricted links. Supports Albums."""
    
    msg = None
    fetcher = acc if acc else client
    try:
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
            if filter_thread_id != 1 and getattr(msg, "reply_to_top_message_id", None) != filter_thread_id and getattr(msg, "reply_to_message_id", None) != filter_thread_id and msg.id != filter_thread_id:
                return "SKIPPED"
        elif actual_thread != filter_thread_id:
            return "SKIPPED"

    # Strict Type Filtering
    msg_type = get_message_type(msg)
    if not msg_type or (allowed_types and msg_type not in allowed_types):
        return "SKIPPED"

    # 🟢 Shield live watchers from global batch cancellations
    is_w_task = False
    if user_id in ACTIVE_PROCESSES and task_uuid in ACTIVE_PROCESSES[user_id]:
        is_w_task = ACTIVE_PROCESSES[user_id][task_uuid].get("is_watcher", False)

    if (batch_temp.IS_BATCH.get(user_id) and not is_w_task) or (task_uuid and CANCEL_FLAGS.get(task_uuid)):
        return "FAILED"

    # 🟢 Mid-Batch Restriction Fallback Ejector
    is_content_protected = getattr(msg, "has_protected_content", False) or getattr(msg.chat, "has_protected_content", False)
    if is_content_protected:
        return "FALLBACK_RESTRICTED"

    # 🟢 Text Fast-Forward
    if msg_type == "Text":
        try:
            await client.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return "SUCCESS"
        except Exception as e:
            # 🟢 KICKS TO DOWNLOAD MODE IF FORWARDS ARE RESTRICTED
            if "CHAT_FORWARDS_RESTRICTED" in str(e) or "RESTRICTED" in str(e): return "FALLBACK_RESTRICTED"
            if acc:
                try:
                    await acc.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                    return "SUCCESS"
                except Exception as e2: 
                    if "CHAT_FORWARDS_RESTRICTED" in str(e2) or "RESTRICTED" in str(e2): return "FALLBACK_RESTRICTED"
                    return "FAILED"
            return "FAILED"

    try:
        await USER_FLOOD_LOCKS[user_id].wait_if_locked()
        
        # 🟢 ALBUM LOGIC RE-INTEGRATED
        if msg.media_group_id:
            try: m_group = await fetcher.get_media_group(chatid, msgid)
            except: m_group = [msg]
            
            group_size = len(m_group)
            if task_uuid:
                for m in m_group: batch_temp.SKIP_IDS[task_uuid].add(m.id)

            try:
                copy_res = await client.copy_media_group(chat_id=dest_chat_id, from_chat_id=chatid, message_id=msgid, message_thread_id=dest_thread_id)
            except Exception as e:
                if "CHAT_FORWARDS_RESTRICTED" in str(e) or "RESTRICTED" in str(e): return "FALLBACK_RESTRICTED"
                if acc:
                    try:
                        copy_res = await acc.copy_media_group(chat_id=dest_chat_id, from_chat_id=chatid, message_id=msgid, message_thread_id=dest_thread_id)
                    except Exception as e2:
                        if "CHAT_FORWARDS_RESTRICTED" in str(e2) or "RESTRICTED" in str(e2): return "FALLBACK_RESTRICTED"
                        copy_res = False
                else: copy_res = False
            
            if copy_res:
                if delay > 0 and group_size > 1: await asyncio.sleep(delay * (group_size - 1))
                return "SUCCESS"
            return "FAILED"

        # 🟢 Single Media Copy
        try:
            copy_res = await client.copy_message(chat_id=dest_chat_id, from_chat_id=chatid, message_id=msgid, message_thread_id=dest_thread_id)
            if not copy_res: raise ValueError("Bot copy failed")
            return "SUCCESS"
        except Exception as e:
            if "CHAT_FORWARDS_RESTRICTED" in str(e) or "RESTRICTED" in str(e):
                return "FALLBACK_RESTRICTED"
            if acc:
                try: 
                    copy_res = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=chatid, message_id=msgid, message_thread_id=dest_thread_id)
                    return "SUCCESS" if copy_res else "FAILED"
                except Exception as e2: 
                    if "CHAT_FORWARDS_RESTRICTED" in str(e2) or "RESTRICTED" in str(e2):
                        return "FALLBACK_RESTRICTED"
                    return "FAILED"
            return "FAILED"

    except FloodWait as e:
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
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
                
                user_workers = 8
                
                acc = Client(
                    name=f"temp_acc_{user_id}_{uuid.uuid4().hex}", 
                    in_memory=True,
                    session_string=user_data, 
                    api_hash=api_hash, 
                    api_id=api_id, 
                    no_updates=True,
                    workers=user_workers,
                    sleep_threshold=60,
                    ipv6=False,
                    **get_transmission_kwargs(workers=user_workers)
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
                    
                    # 🟢 FIX: Determine if link is a Public string username
                    is_pub = isinstance(parsed_source.get("chat_id"), str) and not str(parsed_source.get("chat_id")).lstrip('-').isdigit()

                    # 🟢 FIX: Strict Separation of Concerns! Fast path vs Heavy path.
                    if is_pub and not is_restricted:
                        task_result = await handle_public_unrestricted(
                            client, acc, chatid, msgid, dest_chat_id, dest_thread_id, 
                            user_id, task_uuid, filter_thread_id, allowed_types, delay
                        )
                        # 🟢 FIX: Catch mid-batch restricted files and dynamically route them to the heavy downloader!
                        if task_result == "FALLBACK_RESTRICTED":
                            task_result = await handle_private(
                                client, acc, message, chatid, msgid, index, total_count, 
                                status_message, dest_chat_id, dest_thread_id, delay, 
                                user_id, task_uuid, 
                                is_restricted=True, # FORCE HEAVY MODE FOR THIS MESSAGE
                                header_text=inner_header,
                                filter_thread_id=filter_thread_id, 
                                allowed_types=allowed_types 
                            )
                    else:
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
            # 🟢 FIX: If targeting General Topic (1), a missing thread ID is a valid match!
            if filter_thread_id != 1 and getattr(msg, "reply_to_top_message_id", None) != filter_thread_id and getattr(msg, "reply_to_message_id", None) != filter_thread_id and msg.id != filter_thread_id:
                return None, None
        elif actual_thread != filter_thread_id:
            return None, None

    msg_type = get_message_type(msg)
    if not msg_type: return None, None
    if allowed_types is not None and msg_type not in allowed_types: return None, None
    
    # 🟢 FIX: Shield Watchers from Global Cancels
    is_w_task = False
    if user_id in ACTIVE_PROCESSES and task_uuid in ACTIVE_PROCESSES[user_id]:
        is_w_task = ACTIVE_PROCESSES[user_id][task_uuid].get("is_watcher", False)
        
    if (batch_temp.IS_BATCH.get(user_id) and not is_w_task) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): 
        return None, None

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

    # 🟢 Define the watcher shield variable
    is_w_task = False
    if user_id in ACTIVE_PROCESSES and task_uuid in ACTIVE_PROCESSES[user_id]:
        is_w_task = ACTIVE_PROCESSES[user_id][task_uuid].get("is_watcher", False)

    try: 
        for attempt in range(3):
            if (batch_temp.IS_BATCH.get(user_id) and not is_w_task) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): return False
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
                                if (batch_temp.IS_BATCH.get(user_id) and not is_w_task) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): raise Exception("CANCELLED")
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
        if (batch_temp.IS_BATCH.get(user_id) and not is_w_task) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): return False

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
                    if (batch_temp.IS_BATCH.get(user_id) and not is_w_task) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): break
                    
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

                        sent = False
                        try:
                            if msg_type == "Document": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_document, document=file_path, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Video": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_video, video=file_path, duration=v_dur, width=v_w, height=v_h, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Audio": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_audio, audio=file_path, duration=a_dur, performer=a_perf, title=a_tit, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Photo": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_photo, photo=file_path, **kwargs)
                            elif msg_type == "Voice": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_voice, voice=file_path, progress=p_func, progress_args=p_args, **kwargs)
                            elif msg_type == "Animation": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_animation, animation=file_path, **kwargs)
                            elif msg_type == "Sticker": await safe_send(client, user_id, dest_chat_id, task_uuid, True, client.send_sticker, chat_id=dest_chat_id, sticker=file_path, message_thread_id=dest_thread_id)
                            else:
                                raise ValueError(f"Unsupported upload type: {msg_type}")
                            sent = True
                        except Exception:
                            if acc:
                                if msg_type == "Document": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_document, document=file_path, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Video": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_video, video=file_path, duration=v_dur, width=v_w, height=v_h, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Audio": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_audio, audio=file_path, duration=a_dur, performer=a_perf, title=a_tit, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Photo": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_photo, photo=file_path, **kwargs)
                                elif msg_type == "Voice": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_voice, voice=file_path, progress=p_func, progress_args=p_args, **kwargs)
                                elif msg_type == "Animation": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_animation, animation=file_path, **kwargs)
                                elif msg_type == "Sticker": await safe_send(acc, user_id, dest_chat_id, task_uuid, False, acc.send_sticker, chat_id=dest_chat_id, sticker=file_path, message_thread_id=dest_thread_id)
                                else:
                                    raise ValueError(f"Unsupported upload type: {msg_type}")
                                sent = True

                        if sent:
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="referrer" content="no-referrer"> <!-- Bypasses TMDB Hotlink Protection -->
    <title>Destiny TG Forwarder</title>
    
    <!-- Anime/Modern Aesthetics Font -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;800;900&display=swap" rel="stylesheet">

    <!-- 🟢 NEW: 3D Interactive WebGL Globe -->
    <script src="https://unpkg.com/globe.gl"></script>
    
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
            --liquid-width: 85%; /* Scaled up dynamically for TVs & Tablets */
            --bg: #0b0f19; --card: rgba(15, 23, 42, 0.6); --card-border: rgba(139, 92, 246, 0.3); 
            --text: #f8fafc; --subtext: #cbd5e1;
            --accent: #f472b6; 
            --glow: rgba(244, 114, 182, 0.5); --danger: #fb7185; --sidebar: rgba(11, 15, 25, 0.8);
            --anime-bg: url('https://images.unsplash.com/photo-1578632767115-351597cf2477?q=80&w=2560&auto=format&fit=crop'); /* Beautiful Anime/Starry scenery */
        }

        /* TV & iPad Pro Responsive Variable Overrides */
        @media (min-width: 1024px) { :root { --liquid-width: 75%; } }
        @media (min-width: 1920px) { :root { --liquid-width: 60%; font-size: 1.2rem; } }
        @media (min-width: 2560px) { :root { --liquid-width: 50%; font-size: 1.5rem; } }

        /* --- 🌑 DARK THEMES --- */
        [data-theme="amoled"] { --bg: #000000; --card: rgba(10,10,10,0.7); --card-border: #1f2937; --text: #f1f5f9; --subtext: #94a3b8; --accent: #38bdf8; --glow: rgba(56, 189, 248, 0.4); --sidebar: rgba(5,5,5,0.9); --anime-bg: none; }
        
        /* --- ⚔️ ANIME MEGA THEMES (THE ULTIMATE BYPASS: INTERNAL PROXY + GLOBAL CDN) --- */
        [data-theme="anime-magic"] { --bg: #1a0b2e; --card: rgba(26, 11, 46, 0.6); --card-border: rgba(217, 70, 239, 0.4); --text: #fdf4ff; --subtext: #f0abfc; --accent: #e879f9; --glow: rgba(232, 121, 249, 0.6); --sidebar: rgba(26, 11, 46, 0.85); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/7hMTEEqQvLntA220d9p6a92E31P.jpg'); }
        [data-theme="one-piece"] { --bg: #0c1524; --card: rgba(12, 21, 36, 0.75); --card-border: rgba(251, 191, 36, 0.5); --text: #ffffff; --subtext: #fde68a; --accent: #fbbf24; --glow: rgba(251, 191, 36, 0.7); --sidebar: rgba(12, 21, 36, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/4qCqZeJeqAMhQzEsx1zX4PUDQf0.jpg'); }
        [data-theme="jjk"] { --bg: #09090b; --card: rgba(9, 9, 11, 0.75); --card-border: rgba(139, 92, 246, 0.5); --text: #f8fafc; --subtext: #c4b5fd; --accent: #8b5cf6; --glow: rgba(139, 92, 246, 0.7); --sidebar: rgba(9, 9, 11, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/y4DhwEN8uXo8qMngF5y6y3rJ22C.jpg'); }
        [data-theme="demon-slayer"] { --bg: #0f172a; --card: rgba(15, 23, 42, 0.75); --card-border: rgba(16, 185, 129, 0.5); --text: #f8fafc; --subtext: #a7f3d0; --accent: #10b981; --glow: rgba(16, 185, 129, 0.7); --sidebar: rgba(15, 23, 42, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/xUfRZu2mi8jH6SzQEJST6mLiAJU.jpg'); }
        [data-theme="aot"] { --bg: #1c1917; --card: rgba(28, 25, 23, 0.75); --card-border: rgba(132, 204, 22, 0.4); --text: #fafaf9; --subtext: #d9f99d; --accent: #84cc16; --glow: rgba(132, 204, 22, 0.6); --sidebar: rgba(28, 25, 23, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/yVuTrc33ApeEhiL9GlaT5ZNbL51.jpg'); }
        [data-theme="naruto"] { --bg: #1e1b4b; --card: rgba(30, 27, 75, 0.75); --card-border: rgba(249, 115, 22, 0.5); --text: #fffedd; --subtext: #fdba74; --accent: #f97316; --glow: rgba(249, 115, 22, 0.7); --sidebar: rgba(30, 27, 75, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/v5zgEeeEiRiy2HndIinqBvHEDtG.jpg'); }
        [data-theme="fma"] { --bg: #1a0f0f; --card: rgba(26, 15, 15, 0.8); --card-border: rgba(220, 38, 38, 0.5); --text: #fef2f2; --subtext: #fca5a5; --accent: #dc2626; --glow: rgba(220, 38, 38, 0.7); --sidebar: rgba(26, 15, 15, 0.95); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/51xONKDBwT3eGZ5lG8xI04p80n8.jpg'); }
        [data-theme="geass"] { --bg: #150a1e; --card: rgba(21, 10, 30, 0.75); --card-border: rgba(225, 29, 72, 0.5); --text: #fff1f2; --subtext: #fecdd3; --accent: #e11d48; --glow: rgba(225, 29, 72, 0.7); --sidebar: rgba(21, 10, 30, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/22oEGtWjZk3T216bE6dMBfPqTjQ.jpg'); }
        [data-theme="solo"] { --bg: #020617; --card: rgba(2, 6, 23, 0.75); --card-border: rgba(56, 189, 248, 0.5); --text: #f0f9ff; --subtext: #bae6fd; --accent: #38bdf8; --glow: rgba(56, 189, 248, 0.7); --sidebar: rgba(2, 6, 23, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/v1YEXZ1lA2LpYhGz2Q0iS3k1vK0.jpg'); }
        [data-theme="hxh"] { --bg: #064e3b; --card: rgba(6, 78, 59, 0.75); --card-border: rgba(34, 197, 94, 0.5); --text: #f0fdf4; --subtext: #86efac; --accent: #22c55e; --glow: rgba(34, 197, 94, 0.7); --sidebar: rgba(6, 78, 59, 0.9); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/xT9UD1wH1TMWkK0VnFpMh0t0W8u.jpg'); }
        [data-theme="death-note"] { --bg: #000000; --card: rgba(10, 10, 10, 0.85); --card-border: rgba(153, 27, 27, 0.6); --text: #e5e5e5; --subtext: #a3a3a3; --accent: #dc2626; --glow: rgba(220, 38, 38, 0.8); --sidebar: rgba(5, 5, 5, 0.95); --anime-bg: url('/api/bg?url=https://image.tmdb.org/t/p/original/t3fRhG1kOioRNYj08tDqS8A690R.jpg'); }

        [data-theme="graphite"] { --bg: #141416; --card: #1c1c20; --card-border: #2e2e36; --text: #f3f4f6; --subtext: #9ca3af; --accent: #f59e0b; --glow: rgba(245, 158, 11, 0.4); --sidebar: #0e0e10; --anime-bg: none; }
        [data-theme="obsidian"] { --bg: #090e17; --card: #111827; --card-border: #1e293b; --text: #f1f5f9; --subtext: #94a3b8; --accent: #10b981; --glow: rgba(16, 185, 129, 0.4); --sidebar: #070a12; --anime-bg: none; }
        [data-theme="royal"] { --bg: #0b0914; --card: #151124; --card-border: #2d244a; --text: #f5f3ff; --subtext: #a78bfa; --accent: #8b5cf6; --glow: rgba(139, 92, 246, 0.4); --sidebar: #07050d; --anime-bg: none; }
        [data-theme="slate"] { --bg: #0f172a; --card: #1e293b; --card-border: #334155; --text: #f8fafc; --subtext: #94a3b8; --accent: #0ea5e9; --glow: rgba(14, 165, 233, 0.4); --sidebar: #090d16; --anime-bg: none; }
        [data-theme="charcoal"] { --bg: #12140e; --card: #1b1e15; --card-border: #2c3322; --text: #f7fee7; --subtext: #bef264; --accent: #a3e635; --glow: rgba(163, 230, 53, 0.4); --sidebar: #0c0e09; --anime-bg: none; }
        [data-theme="fresh-canopy"] { --bg: #0c1410; --card: #14201a; --card-border: #20352b; --text: #ecfdf5; --subtext: #6ee7b7; --accent: #bef264; --glow: rgba(190, 242, 100, 0.4); --sidebar: #080d0a; --anime-bg: none; }
        [data-theme="tiffany-noir"] { --bg: #071415; --card: #0f2022; --card-border: #19383b; --text: #f0fdfa; --subtext: #5eead4; --accent: #2dd4bf; --glow: rgba(45, 212, 191, 0.4); --sidebar: #040d0e; --anime-bg: none; }
        [data-theme="bridal-blush"] { --bg: #170d12; --card: #24141d; --card-border: #3d1e2e; --text: #fff1f2; --subtext: #fda4af; --accent: #fb7185; --glow: rgba(251, 113, 133, 0.4); --sidebar: #0f080c; --anime-bg: none; }

        /* --- ☀️ LIGHT / WHITE THEMES --- */
        [data-theme="rose-quartz"] { --bg: #fff1f3; --card: #ffffff; --card-border: #fecdd3; --text: #4c0519; --subtext: #9f1239; --accent: #f43f5e; --glow: rgba(244, 63, 94, 0.25); --sidebar: #ffe4e6; --anime-bg: none; }
        [data-theme="daylight-sky"] { --bg: #f0f7ff; --card: #ffffff; --card-border: #bfdbfe; --text: #0f172a; --subtext: #1e40af; --accent: #2563eb; --glow: rgba(37, 99, 235, 0.25); --sidebar: #e0f2fe; --anime-bg: none; }
        [data-theme="sage-linen"] { --bg: #f4f7f4; --card: #ffffff; --card-border: #ccfbf1; --text: #134e4a; --subtext: #0f766e; --accent: #0d9488; --glow: rgba(13, 148, 136, 0.25); --sidebar: #e6f4f1; --anime-bg: none; }
        [data-theme="golden-hour"] { --bg: #fffbeb; --card: #ffffff; --card-border: #fde68a; --text: #451a03; --subtext: #92400e; --accent: #d97706; --glow: rgba(217, 119, 6, 0.25); --sidebar: #fef3c7; --anime-bg: none; }

        * { box-sizing: border-box; }
        /* 🌊 Dynamic Glowing Orbs */
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

        body { 
            font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
            background-color: var(--bg); color: var(--text); margin: 0; overflow-x: hidden; 
            /* FIX 1: Only transition the color! Transitioning the whole background drops images in Chrome Android */
            transition: background-color 0.5s ease; 
            position: relative; z-index: 0; 
            
            /* FIX 2: Reduced dark tint opacity so the anime images are bright and visible */
            background-image: linear-gradient(rgba(0, 0, 0, 0.2), rgba(0, 0, 0, 0.5)), var(--anime-bg);
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }
        
        body::before, body::after { 
            content: ''; position: fixed; border-radius: 50%; 
            filter: blur(90px); -webkit-filter: blur(90px); z-index: -1; 
            opacity: calc(0.3 + var(--blob-opacity, 0)); 
            transition: opacity 0.8s ease; pointer-events: none; 
            will-change: transform; 
        }
        
        body::before { 
            width: 60vw; height: 60vh; 
            top: -10vh; left: -10vw; 
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            animation: flowPrimary 30s infinite alternate ease-in-out; 
        }
        body::after { 
            width: 65vw; height: 65vh; 
            bottom: -10vh; right: -10vw; 
            background: linear-gradient(135deg, #ec4899, var(--accent));
            animation: flowSecondary 35s infinite alternate ease-in-out; 
        }

        .view-section { display: none; padding-bottom: 40px; }
        .view-section.active { display: block; }

        #login-view { display: flex; align-items: center; justify-content: center; min-height: 100vh; padding: 20px; background: transparent; }
        .login-card { background: color-mix(in srgb, var(--card) var(--glass-bg, 100%), transparent); backdrop-filter: blur(var(--glass-blur, 0px)); -webkit-backdrop-filter: blur(var(--glass-blur, 0px)); border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); border-radius: 28px; width: 100%; max-width: 420px; padding: 36px 28px; box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 8px 32px rgba(0, 0, 0, var(--glass-shadow, 0)); text-align: center; transition: 0.3s; }
        .login-logo { width: 56px; height: 56px; background: var(--accent); border-radius: 50%; margin: 0 auto 20px auto; display: flex; align-items: center; justify-content: center; font-size: 24px; box-shadow: 0 0 25px var(--glow); color: #fff; }
        .login-title { font-size: 22px; font-weight: 800; color: #fff; margin-bottom: 6px; }
        .login-subtitle { font-size: 13px; color: #94a3b8; margin-bottom: 28px; }

        .navbar { display: flex; justify-content: space-between; align-items: center; padding: clamp(15px, 2vh, 25px) clamp(20px, 3vw, 40px); background: color-mix(in srgb, rgba(10, 10, 10, 0.6) var(--glass-bg, 100%), transparent); backdrop-filter: blur(calc(24px + var(--glass-blur, 0px))); -webkit-backdrop-filter: blur(calc(24px + var(--glass-blur, 0px))); border-bottom: 1px solid rgba(255,255,255,0.1); position: sticky; top: 0; z-index: 100; box-shadow: 0 4px 30px rgba(0,0,0,0.5); }
        .nav-brand { display: flex; align-items: center; gap: 16px; font-size: clamp(18px, 1.5vw, 24px); font-weight: 900; letter-spacing: 1px; text-transform: uppercase; text-shadow: 0 2px 10px rgba(0,0,0,0.5); }
        .nav-brand-icon { width: clamp(34px, 3vw, 48px); height: clamp(34px, 3vw, 48px); background: linear-gradient(135deg, var(--accent), #8b5cf6); border-radius: 12px; transform: rotate(10deg); display: flex; align-items: center; justify-content: center; box-shadow: 0 0 20px var(--glow); color: white; font-size: clamp(14px, 1.2vw, 20px); transition: transform 0.3s; }
        .nav-brand:hover .nav-brand-icon { transform: rotate(0deg) scale(1.1); }
        .nav-controls { display: flex; align-items: center; gap: clamp(12px, 1.5vw, 24px); }
        .icon-btn { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); color: #fff; width: clamp(40px, 3.5vw, 56px); height: clamp(40px, 3.5vw, 56px); border-radius: 14px; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); backdrop-filter: blur(10px); font-size: clamp(16px, 1.5vw, 24px); }
        .icon-btn:hover, .icon-btn:focus { border-color: var(--accent); background: rgba(255,255,255,0.15); transform: translateY(-3px); box-shadow: 0 5px 15px var(--glow); outline: none; }

        .sidebar-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); z-index: 200; opacity: 0; pointer-events: none; transition: 0.4s cubic-bezier(0.4, 0, 0.2, 1); }
        .sidebar { position: fixed; top: 0; left: -320px; width: clamp(280px, 25vw, 380px); height: 100%; background: color-mix(in srgb, var(--sidebar) var(--glass-bg, 80%), transparent); backdrop-filter: blur(calc(30px + var(--glass-blur, 0px))); -webkit-backdrop-filter: blur(calc(30px + var(--glass-blur, 0px))); z-index: 201; border-right: 1px solid rgba(255,255,255,0.1); box-shadow: 10px 0 50px rgba(0, 0, 0, 0.8); transition: left 0.4s cubic-bezier(0.4, 0, 0.2, 1), background 0.3s; padding: 30px 0; overflow-y: auto; }
        .sidebar.open { left: 0; }
        .sidebar-overlay.open { opacity: 1; pointer-events: auto; }
        .menu-item { padding: clamp(16px, 2vh, 24px) clamp(24px, 2vw, 32px); display: flex; align-items: center; gap: 20px; color: #cbd5e1; font-weight: 800; font-size: clamp(14px, 1.2vw, 18px); cursor: pointer; transition: all 0.25s; border-left: 0px solid transparent; }
        .menu-item:hover, .menu-item:focus, .menu-item.active { background: linear-gradient(90deg, rgba(255,255,255,0.1) 0%, transparent 100%); color: #fff; border-left: 6px solid var(--accent); padding-left: clamp(30px, 2.5vw, 38px); outline: none; }
        
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

        .container { 
            width: var(--liquid-width); 
            min-width: 320px; 
            max-width: 100%; 
            margin: 0 auto; 
            padding: env(safe-area-inset-top, 20px) env(safe-area-inset-right, 20px) env(safe-area-inset-bottom, 40px) env(safe-area-inset-left, 20px); 
            transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1); 
        }
        .section-title { font-size: clamp(1.25rem, 2vw + 1rem, 2.5rem); font-weight: 900; margin: 30px 0 20px 0; color: #fff; text-shadow: 0 0 15px var(--glow); display: flex; justify-content: space-between; align-items: center; text-transform: uppercase; letter-spacing: 1.5px; }
        
        /* Modernized Auto-Fit Grid with TV Support */
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(clamp(250px, 20vw, 400px), 1fr)); gap: clamp(16px, 2vw, 32px); margin-bottom: 20px; }
        
        /* Anime Glass Card */
        .card { 
            background: color-mix(in srgb, var(--card) var(--glass-bg, 80%), transparent); 
            backdrop-filter: blur(calc(16px + var(--glass-blur, 0px))); -webkit-backdrop-filter: blur(calc(16px + var(--glass-blur, 0px))); 
            border-radius: 24px; padding: clamp(20px, 3vw, 40px); 
            border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); 
            border-top: 1px solid rgba(255,255,255,0.2); border-left: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 10px 40px rgba(0, 0, 0, var(--glass-shadow, 0.3)), inset 0 0 20px rgba(255,255,255,0.02); 
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); 
        }
        .card:hover, .card:focus-within {
            transform: translateY(-5px) scale(1.01);
            box-shadow: 0 15px 50px rgba(0, 0, 0, 0.5), 0 0 20px var(--glow), inset 0 0 20px rgba(255,255,255,0.05);
            border-color: var(--accent);
        }
        
        /* D-Pad / TV Focus outlines */
        *:focus { outline: none; } /* 🟢 FIX: Removes the ugly blue tap box on mobile */
        .card-stat { font-size: clamp(24px, 2.5vw, 36px); font-weight: 900; color: var(--text); margin-top: 8px; }
        .card-label { font-size: clamp(11px, 1vw, 14px); color: var(--accent); text-transform: uppercase; font-weight: 800; letter-spacing: 1.5px; }

        .primary-btn { width: 100%; padding: clamp(15px, 2vh, 20px); background: linear-gradient(135deg, var(--accent), #8b5cf6); border: none; border-radius: 16px; color: #fff; font-size: clamp(14px, 1.2vw, 18px); font-weight: 900; cursor: pointer; transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1); box-shadow: 0 8px 25px var(--glow), inset 0 2px 5px rgba(255,255,255,0.2); text-transform: uppercase; letter-spacing: 1px; }
        .primary-btn:hover, .primary-btn:focus { transform: translateY(-4px) scale(1.02); box-shadow: 0 12px 35px var(--glow), inset 0 2px 5px rgba(255,255,255,0.3); outline: none; }
        .input-group { margin-bottom: clamp(18px, 2vh, 24px); text-align: left; }
        .input-group label { display: block; font-size: clamp(11px, 1vw, 14px); color: var(--subtext); margin-bottom: 8px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; }
        .input-group input, .input-group select { width: 100%; padding: clamp(14px, 2vh, 20px) 16px; border-radius: 16px; border: 2px solid var(--card-border); background: rgba(0,0,0,0.3); color: #fff; font-size: clamp(14px, 1.2vw, 18px); outline: none; transition: 0.3s; backdrop-filter: blur(10px); }
        .input-group input:focus, .input-group select:focus { border-color: var(--accent); box-shadow: 0 0 20px var(--glow), inset 0 0 10px var(--glow); background: rgba(0,0,0,0.5); }

        .task-row { background: linear-gradient(90deg, color-mix(in srgb, var(--card) var(--glass-bg, 60%), transparent), transparent); border: 1px solid rgba(255,255,255,0.1); border-left: 4px solid var(--accent); border-radius: 16px; padding: clamp(16px, 2vw, 24px); margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; gap: 15px; transition: 0.3s; backdrop-filter: blur(10px); }
        .task-row:hover { transform: translateX(5px); background: linear-gradient(90deg, color-mix(in srgb, var(--card) var(--glass-bg, 80%), transparent), rgba(255,255,255,0.05)); box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        .task-kill { background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), transparent); color: var(--danger); border: 1px solid rgba(239, 68, 68, 0.5); padding: 10px 20px; border-radius: 12px; font-size: clamp(12px, 1vw, 16px); font-weight: 800; cursor: pointer; transition: 0.3s; text-transform: uppercase; }
        .task-kill:hover, .task-kill:focus { background: var(--danger); color: #fff; box-shadow: 0 0 20px rgba(239, 68, 68, 0.6); transform: scale(1.05); }

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

        /* ==========================================================================
           CINEMA THEATER & 3D WEBGL ENGINE STYLES (NETFLIX / JIOHOTSTAR INSPIRED)
           ========================================================================== */
        .cinema-viewport {
            position: relative; width: 100%; aspect-ratio: 16/9; background: #000;
            border-radius: 24px; overflow: hidden; box-shadow: 0 30px 80px rgba(0,0,0,0.9), 0 0 50px var(--glow);
            border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent);
            display: flex; align-items: center; justify-content: center;
        }
        
        /* 📱 FULLSCREEN ADAPTIVE FIXES */
        .cinema-viewport:fullscreen, .cinema-viewport:-webkit-full-screen, .cinema-viewport.ios-fullscreen {
            border-radius: 0 !important; border: none !important; aspect-ratio: auto !important; 
            width: 100vw !important; height: 100vh !important;
            max-width: 100vw !important; max-height: 100vh !important;
            position: fixed !important; top: 0 !important; left: 0 !important; z-index: 9999 !important;
            padding: 0 !important; margin: 0 !important; background: #000 !important;
        }

        /* 📱 UNIVERSAL FULLSCREEN ROTATION (iOS, Android, HF iframes, PC, Mac) */
        #cinema-viewport.rotated-landscape,
        #cinema-viewport:fullscreen.rotated-landscape,
        #cinema-viewport:-webkit-full-screen.rotated-landscape,
        #cinema-viewport.ios-fullscreen.rotated-landscape {
            transform: translate(-50%, -50%) rotate(90deg) !important;
            width: 100vh !important;
            height: 100vw !important;
            max-width: 100vh !important;
            max-height: 100vw !important;
            position: fixed !important;
            top: 50% !important;
            left: 50% !important;
            margin: 0 !important;
            padding: 0 !important;
            border-radius: 0 !important;
            background: #000 !important;
        }
        .cinema-viewport:fullscreen .cinema-hud, .cinema-viewport:-webkit-full-screen .cinema-hud, .cinema-viewport.ios-fullscreen .cinema-hud {
            padding: 40px 30px; padding-bottom: max(40px, env(safe-area-inset-bottom));
        }
        .cinema-viewport:fullscreen .cinema-title-bar, .cinema-viewport:-webkit-full-screen .cinema-title-bar {
            padding: max(30px, env(safe-area-inset-top)) 30px; font-size: 18px;
        }
        .cinema-viewport:fullscreen .cinema-btn, .cinema-viewport:-webkit-full-screen .cinema-btn { font-size: 28px; }
        .cinema-viewport:fullscreen .time-badge, .cinema-viewport:-webkit-full-screen .time-badge { font-size: 16px; }

        /* WebGL canvas sits on top of the video feed */
        #webgl-canvas {
            position: absolute; left: 50%; top: 50%;
            width: 100%; height: 100%;
            display: block; z-index: 2;
            transform: translate(-50%, -50%);
            transform-origin: center center;
            object-fit: fill;
            will-change: width, height, transform;
        }

        /* 🟢 FIX 1: Make the feed 99% transparent so Apple WebKit still decodes it, 
           but it doesn't bleed out and stretch behind the WebGL canvas on mobile portrait! */
        .hidden-video-feed {
            position: absolute; inset: 0; width: 100%; height: 100%;
            object-fit: contain; opacity: 0.01; pointer-events: none; z-index: 1;
        }

        /* iPad / PWA CSS Fullscreen Fallback */
        .cinema-viewport:fullscreen, .cinema-viewport:-webkit-full-screen, .cinema-viewport.ios-fullscreen {
            border-radius: 0 !important; border: none !important; aspect-ratio: auto !important; 
            width: 100vw !important; height: 100vh !important;
            max-width: 100vw !important; max-height: 100vh !important;
            position: fixed !important; top: 0 !important; left: 0 !important; z-index: 99999 !important;
            padding: 0 !important; margin: 0 !important; background: #000 !important;
        }
        .cinema-viewport:fullscreen .cinema-hud, .cinema-viewport:-webkit-full-screen .cinema-hud, .cinema-viewport.ios-fullscreen .cinema-hud {
            padding: 40px 30px; padding-bottom: max(40px, env(safe-area-inset-bottom));
        }

        /* Custom subtitle layer: fully independent of the hidden <video>. */
        .subtitle-overlay {
            position: absolute; left: 1%; right: 1%; bottom: 10%; /* 🟢 FIX: Widened boundaries */
            display: flex; justify-content: center; align-items: flex-end;
            z-index: 28; pointer-events: none;
            text-align: center;
            padding: 0 10px;
            transition: opacity 0.25s ease, transform 0.25s ease;
        }
        .subtitle-text {
            max-width: 95%;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            line-height: 1.35;
            font-size: 20px;
            font-weight: 600;
            color: #ffffff;
            background: rgba(0, 0, 0, 0.70);
            border-radius: 7px;
            padding: 4px 10px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.95);
            text-align: center; /* 🟢 FIX: This ensures the text itself is perfectly centered when it breaks into 2 lines */
        }
        .cinema-viewport.fullscreen-subtitle .subtitle-overlay { bottom: 13%; }

        /* 🟢 NEW: Dedicated Audio Lyrics Scroller (Responsive Window/Fullscreen) */
        .lyrics-scroller {
            position: absolute; top: 55%; bottom: 15%; left: 5%; right: 5%;
            overflow: hidden; text-align: center; z-index: 10;
            display: none; scroll-behavior: smooth;
            -ms-overflow-style: none; scrollbar-width: none;
            mask-image: none; -webkit-mask-image: none;
            pointer-events: none;
        }
        .lyrics-scroller::-webkit-scrollbar { display: none; }
        
        .lrc-line {
            display: none; /* Hide inactive lines in windowed mode */
            font-size: clamp(14px, 2vw, 18px); font-weight: 600; color: rgba(255,255,255,0.3);
            margin: 12px 0; transition: all 0.3s ease; text-shadow: none;
        }
        .lrc-line.active {
            display: block; /* Show only the current active line */
            color: #ffffff; transform: scale(1.2); font-weight: 800; text-shadow: 0 0 15px rgba(255,255,255,0.8);
        }

        /* 🟢 FULLSCREEN OVERRIDES FOR LYRICS */
        .cinema-viewport:fullscreen .lyrics-scroller,
        .cinema-viewport:-webkit-full-screen .lyrics-scroller,
        .cinema-viewport.ios-fullscreen .lyrics-scroller {
            top: 68%; bottom: 12%;
            overflow-y: auto;
            mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%);
            -webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 20%, black 80%, transparent 100%);
        }
        .cinema-viewport:fullscreen .lrc-line,
        .cinema-viewport:-webkit-full-screen .lrc-line,
        .cinema-viewport.ios-fullscreen .lrc-line {
            display: block; /* Show all lines in fullscreen */
            transform: scale(1);
        }
        .cinema-viewport:fullscreen .lrc-line.active,
        .cinema-viewport:-webkit-full-screen .lrc-line.active,
        .cinema-viewport.ios-fullscreen .lrc-line.active {
            transform: scale(1.15);
        }

        /* 🟢 ALBUM COVER & TRACK INFO RESPONSIVE LAYOUT */
        #album-cover-art { display: none !important; } /* Hidden in windowed */
        
        .cinema-viewport:fullscreen #album-cover-art,
        .cinema-viewport:-webkit-full-screen #album-cover-art,
        .cinema-viewport.ios-fullscreen #album-cover-art {
            display: block !important; /* Visible in fullscreen */
        }

        #album-track-info {
            position: absolute;
            top: 40%; transform: translateY(-50%); /* Centered vertically in windowed mode */
            width: 100%; margin: 0; text-align: center;
        }
        
        .cinema-viewport:fullscreen #album-track-info,
        .cinema-viewport:-webkit-full-screen #album-track-info,
        .cinema-viewport.ios-fullscreen #album-track-info {
            top: auto; bottom: -2%; transform: none; /* Move back to the bottom under cover in fullscreen */
        }

        /* Center Skip Buttons (Liquid Glass UI) */
        .center-controls {
            position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: 5vw;
            z-index: 20; pointer-events: none; opacity: 1; transition: opacity 0.4s ease, transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }
        .center-btn {
            width: 70px; height: 70px; background: rgba(255, 255, 255, 0.08); border-radius: 50%; 
            border: 1px solid rgba(255, 255, 255, 0.15); color: #fff; display: flex; align-items: center; justify-content: center; 
            cursor: pointer; pointer-events: auto; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3), inset 0 0 15px rgba(255,255,255,0.05);
            transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        .center-btn:hover {
            background: rgba(255, 255, 255, 0.15); border-color: rgba(255, 255, 255, 0.3);
            transform: scale(1.1); box-shadow: 0 15px 40px rgba(0,0,0,0.4), inset 0 0 20px rgba(255,255,255,0.1);
        }
        .center-btn:active { transform: scale(0.95); background: rgba(255, 255, 255, 0.25); }
        #big-play-overlay {
            width: 90px; height: 90px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.4), inset 0 0 20px rgba(255,255,255,0.1), 0 0 30px var(--glow);
        }
        #big-play-overlay:hover { box-shadow: 0 15px 50px rgba(0,0,0,0.5), inset 0 0 30px rgba(255,255,255,0.2), 0 0 45px var(--glow); }

        /* Floating Netflix-Style OSD HUD */
        .cinema-hud {
            position: absolute; bottom: 0; left: 0; right: 0; padding: 20px 20px;
            background: linear-gradient(to top, rgba(0,0,0,0.95) 0%, rgba(0,0,0,0.7) 50%, transparent 100%);
            display: flex; flex-direction: column; gap: 16px; opacity: 1; transition: opacity 0.4s ease;
            z-index: 25; pointer-events: auto;
        }
        .cinema-title-bar {
            position: absolute; top: 0; left: 0; right: 0; padding: 20px;
            background: linear-gradient(to bottom, rgba(0,0,0,0.8) 0%, transparent 100%);
            color: #fff; font-weight: 700; font-size: 14px; opacity: 1; transition: opacity 0.4s ease;
            z-index: 25; pointer-events: none; text-shadow: 0 2px 4px rgba(0,0,0,0.8);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }

        /* Auto-Hide Logic */
        .cinema-viewport.idle-hide .cinema-hud, 
        .cinema-viewport.idle-hide .cinema-title-bar,
        .cinema-viewport.idle-hide .center-controls,
        .cinema-viewport.idle-hide #big-play-overlay,
        .cinema-viewport.idle-hide #hud-3d-btn {
            opacity: 0 !important;
            pointer-events: none !important;
            cursor: none !important;
        }
        .cinema-viewport.idle-hide .settings-popup {
            opacity: 0 !important;
            pointer-events: none !important;
            transform: translateY(8px);
        }
        .cinema-viewport.idle-hide .matrix-3d-menu:not(.open) {
            opacity: 0 !important;
            pointer-events: none !important;
        }

        /* 15s Seek Zones (Double Tap) */
        .seek-zone { 
            position: absolute; 
            top: 35%; bottom: 35%; /* Tightly restricts height to the exact center of the video */
            width: 25%; /* Keeps the touch zone away from the center play button */
            z-index: 10; 
            cursor: pointer; 
            display: flex; 
            align-items: center; 
            justify-content: center; 
            color: rgba(255,255,255,0); 
            font-size: 32px; 
            font-weight: bold; 
            transition: color 0.2s; 
            user-select: none; 
            -webkit-tap-highlight-color: rgba(0,0,0,0) !important; /* Completely kills the Android blue box */
            outline: none !important;
        }
        .seek-zone.left { left: 5%; }
        .seek-zone.right { right: 5%; }
        .seek-zone:active { 
            color: rgba(255,255,255,0.8); 
            background: radial-gradient(circle, rgba(255,255,255,0.15) 0%, transparent 65%); 
        }

        .cinema-scrubber-bar {
            position: relative; width: 100%; height: 6px; background: rgba(255,255,255,0.15);
            border-radius: 999px; cursor: pointer; transition: height 0.15s ease;
            /* Removed overflow:hidden so the glowing playback dot doesn't get clipped! */
        }
        .cinema-scrubber-bar:hover { height: 10px; }
        .scrubber-buffer {
            position: absolute; left: 0; top: 0; height: 100%; 
            background: rgba(255, 255, 255, 0.4); /* ⚪ Translucent white loaded buffer */
            border-radius: 999px; width: 0%; pointer-events: none; transition: width 0.2s linear; z-index: 1;
        }
        .scrubber-fill { height: 100%; background: #ffffff; border-radius: 999px; width: 0%; position: absolute; left: 0; top: 0; pointer-events: none; z-index: 2; }
        /* 🟢 FIX: Removed the ::after completely to kill the ball. Made the bar pure white! */

        .cinema-controls-row { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; }
        .ctrl-group { display: flex; align-items: center; gap: 12px; }
        .cinema-btn { background: none; border: none; color: #fff; cursor: pointer; font-size: 20px; display: flex; align-items: center; justify-content: center; transition: transform 0.2s, color 0.2s; padding: 0; }
        .cinema-btn:hover { color: var(--accent); transform: scale(1.2); }
        .time-badge { font-size: 11px; font-family: monospace; color: #cbd5e1; font-weight: 600; margin-left: 4px; white-space: nowrap; }

        /* Settings Floating Popups */
        .settings-popup {
            position: absolute; bottom: 85px; right: 30px; 
            background: color-mix(in srgb, var(--card) var(--glass-bg, 95%), transparent);
            backdrop-filter: blur(calc(20px + var(--glass-blur, 0px))); 
            -webkit-backdrop-filter: blur(calc(20px + var(--glass-blur, 0px))); 
            border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent);
            border-radius: 20px; padding: 20px; width: 320px; max-width: calc(100vw - 24px);
            max-height: min(78vh, 620px); overflow-y: auto; overflow-x: hidden;
            -webkit-overflow-scrolling: touch; overscroll-behavior: contain; touch-action: pan-y;
            display: none; z-index: 30; 
            box-shadow: 0 20px 50px rgba(0,0,0,0.8), 0 8px 32px rgba(0, 0, 0, var(--glass-shadow, 0));
            transition: opacity 0.25s ease, transform 0.25s ease;
            scrollbar-width: thin;
        }
        .settings-popup.open { display: block; }
        .cinema-viewport:fullscreen .settings-popup,
        .cinema-viewport:-webkit-full-screen .settings-popup {
            top: max(12px, env(safe-area-inset-top)); bottom: auto; right: 12px;
            max-height: calc(100dvh - 24px); overflow-y: auto;
        }
        @media (max-width: 700px) and (orientation: landscape) {
            .settings-popup {
                right: 8px; bottom: 58px; width: min(360px, calc(100vw - 16px));
                max-height: calc(100dvh - 70px);
            }
        }
        @media (max-width: 700px) and (orientation: portrait) {
            .settings-popup {
                right: 8px; bottom: 70px; width: min(360px, calc(100vw - 16px));
                max-height: 70dvh;
            }
        }
        .pop-title { font-size: 14px; font-weight: 800; margin-bottom: 12px; color: var(--accent); text-transform: uppercase; letter-spacing: 0.5px; }
        .pop-select { display: none; /* Hidden entirely to replace with Custom Glass Selects */ }
        
        /* 🟢 NEW: Custom Liquid Glass Dropdown Overrides for Mobile */
        .glass-select-container { position: relative; width: 100%; margin-bottom: 14px; user-select: none; }
        .glass-select-display {
            padding: 12px 14px;
            background: color-mix(in srgb, var(--bg) var(--glass-bg, 100%), transparent);
            border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent);
            border-radius: 12px; color: #fff; font-size: 12px; cursor: pointer; font-weight: 600;
            backdrop-filter: blur(calc(10px + var(--glass-blur, 0px))); -webkit-backdrop-filter: blur(calc(10px + var(--glass-blur, 0px)));
            display: flex; justify-content: space-between; align-items: center; transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: inset 0 0 10px rgba(255,255,255,0.02);
        }
        .glass-select-display::after { content: '▼'; font-size: 10px; color: var(--accent); transition: transform 0.3s; }
        .glass-select-display.active { border-color: var(--accent); box-shadow: 0 0 15px var(--glow), inset 0 0 10px rgba(255,255,255,0.05); }
        .glass-select-display.active::after { transform: rotate(180deg); }

        .glass-select-dropdown {
            position: absolute; top: calc(100% + 6px); left: 0; right: 0;
            background: color-mix(in srgb, #050505 var(--glass-bg, 95%), transparent);
            backdrop-filter: blur(calc(25px + var(--glass-blur, 0px))); -webkit-backdrop-filter: blur(calc(25px + var(--glass-blur, 0px)));
            border: 1px solid var(--accent);
            border-radius: 14px; max-height: 240px; overflow-y: auto; z-index: 9999;
            display: none; box-shadow: 0 20px 50px rgba(0,0,0,0.9), 0 0 30px var(--glow);
            scrollbar-width: thin; scrollbar-color: var(--accent) transparent;
        }
        .glass-select-dropdown.show { display: block; animation: glassDropFade 0.25s cubic-bezier(0.4, 0, 0.2, 1) forwards; }
        @keyframes glassDropFade { from { opacity: 0; transform: translateY(-10px) scale(0.98); } to { opacity: 1; transform: translateY(0) scale(1); } }

        .glass-select-item {
            padding: 14px 16px; font-size: 12px; color: #cbd5e1; border-bottom: 1px solid rgba(255,255,255,0.05); cursor: pointer; transition: all 0.2s;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .glass-select-item:last-child { border-bottom: none; }
        .glass-select-item:hover { background: rgba(56, 189, 248, 0.15); color: #fff; padding-left: 20px; }
        .glass-select-item.same-as-selected { background: rgba(56, 189, 248, 0.25); color: #fff; font-weight: 800; border-left: 4px solid var(--accent); }

        /* 3D Matrix Menu (Exact Layout from Image) */
        .matrix-3d-menu {
            position: absolute; top: 0; right: -360px; width: 340px; max-width: 94vw; height: 100%;
            background: color-mix(in srgb, #050505 var(--glass-bg, 92%), transparent); 
            backdrop-filter: blur(calc(25px + var(--glass-blur, 0px))); -webkit-backdrop-filter: blur(calc(25px + var(--glass-blur, 0px)));
            border-left: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); 
            transition: right 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s ease;
            padding: 24px; overflow-y: auto; z-index: 40;
            box-shadow: -10px 0 30px rgba(0, 0, 0, var(--glass-shadow, 0));
        }
        .matrix-3d-menu.open { right: 0; }
        .matrix-header { font-size: 18px; font-weight: 800; text-align: center; margin-bottom: 24px; color: #fff; }
        .matrix-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .matrix-column-title { font-size: 12px; color: var(--subtext); text-transform: uppercase; font-weight: 700; margin-bottom: 16px; letter-spacing: 0.5px; }
        .matrix-option { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; cursor: pointer; font-size: 13px; color: var(--text); }
        .matrix-radio { width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--subtext); display: flex; align-items: center; justify-content: center; transition: 0.2s; }
        .matrix-option.active .matrix-radio { border-color: #a3e635; }
        .matrix-option.active .matrix-radio::after { content: ''; width: 8px; height: 8px; background: #a3e635; border-radius: 50%; }

        /* =========================================================
           PERFORMANCE MODE (Kills all lag on Android TVs)
           ========================================================= */
        body.fast-mode::before, 
        body.fast-mode::after {
            display: none !important; /* Kills the animated blur blobs entirely */
        }

        body.fast-mode .card,
        body.fast-mode .navbar,
        body.fast-mode .sidebar,
        body.fast-mode .login-card,
        body.fast-mode .settings-popup,
        body.fast-mode .matrix-3d-menu,
        body.fast-mode .glass-select-dropdown,
        body.fast-mode .profile-menu {
            backdrop-filter: none !important;
            -webkit-backdrop-filter: none !important;
            background: var(--card) !important; /* Replaces glass with solid color */
            box-shadow: none !important; /* Kills heavy shadow painting */
            border: 1px solid var(--card-border) !important;
        }

        /* Fallback solid colors so menus don't become transparent without the blur */
        body.fast-mode .navbar { background: #0a0a0a !important; border-bottom: 1px solid #1f2937 !important; }
        body.fast-mode .sidebar { background: #050505 !important; }
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
            <div class="menu-item" onclick="switchView('globe', 'World Explorer')">🌎 World Explorer</div>
            <div class="menu-item" onclick="switchView('network', 'Live Network')">🌍 Live Network</div>
            <div class="menu-item" onclick="switchView('speedtest', 'Speedtest')">🚀 Speedtest</div>
            <div class="menu-item" onclick="switchView('sos', 'System SOS')">🖥 System SOS</div>
            <div class="menu-item" onclick="switchView('logs', 'Logs')">📋 System Logs</div>
            <div class="menu-item" onclick="switchView('mediainfo', 'Media Inspector')">🔍 Media Inspector</div>
            <div class="menu-item" onclick="switchView('spectrogram', 'Audio Spectrogram')">📉 Audio Spectrogram</div>
            <div class="menu-item" onclick="switchView('theater', 'Media Theater')">🍿 Media Theater</div>             
            <div class="menu-item" onclick="switchView('editor', 'Media Editor')">🛠️ Media Editor</div>
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
                <!-- ⚔️ ANIME MEGA THEMES -->
                <div class="theme-pill" style="background: linear-gradient(135deg, #0c1524, #1e3a8a); color: #fff; border-color: #fbbf24;" onclick="setTheme('one-piece', this)">
                    <div class="dots-group"><span class="dot" style="background:#fbbf24; color:#fbbf24;"></span><span class="dot" style="background:#ef4444; color:#ef4444;"></span></div>
                    <span class="pill-label">Grand Line</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #09090b, #3b0764); color: #fff; border-color: #8b5cf6;" onclick="setTheme('jjk', this)">
                    <div class="dots-group"><span class="dot" style="background:#8b5cf6; color:#8b5cf6;"></span><span class="dot" style="background:#0ea5e9; color:#0ea5e9;"></span></div>
                    <span class="pill-label">Domain Expansion</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #0f172a, #064e3b); color: #fff; border-color: #10b981;" onclick="setTheme('demon-slayer', this)">
                    <div class="dots-group"><span class="dot" style="background:#10b981; color:#10b981;"></span><span class="dot" style="background:#ef4444; color:#ef4444;"></span></div>
                    <span class="pill-label">Hinokami</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #1c1917, #451a03); color: #fff; border-color: #84cc16;" onclick="setTheme('aot', this)">
                    <div class="dots-group"><span class="dot" style="background:#84cc16; color:#84cc16;"></span><span class="dot" style="background:#b45309; color:#b45309;"></span></div>
                    <span class="pill-label">Survey Corps</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #1e1b4b, #7c2d12); color: #fff; border-color: #f97316;" onclick="setTheme('naruto', this)">
                    <div class="dots-group"><span class="dot" style="background:#f97316; color:#f97316;"></span><span class="dot" style="background:#3b82f6; color:#3b82f6;"></span></div>
                    <span class="pill-label">Nine Tails</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #1a0f0f, #7f1d1d); color: #fff; border-color: #dc2626;" onclick="setTheme('fma', this)">
                    <div class="dots-group"><span class="dot" style="background:#dc2626; color:#dc2626;"></span><span class="dot" style="background:#fbbf24; color:#fbbf24;"></span></div>
                    <span class="pill-label">Alchemy</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #150a1e, #4c0519); color: #fff; border-color: #e11d48;" onclick="setTheme('geass', this)">
                    <div class="dots-group"><span class="dot" style="background:#e11d48; color:#e11d48;"></span><span class="dot" style="background:#9333ea; color:#9333ea;"></span></div>
                    <span class="pill-label">Zero Requiem</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #020617, #172554); color: #fff; border-color: #38bdf8;" onclick="setTheme('solo', this)">
                    <div class="dots-group"><span class="dot" style="background:#38bdf8; color:#38bdf8;"></span><span class="dot" style="background:#8b5cf6; color:#8b5cf6;"></span></div>
                    <span class="pill-label">Arise</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #064e3b, #14532d); color: #fff; border-color: #22c55e;" onclick="setTheme('hxh', this)">
                    <div class="dots-group"><span class="dot" style="background:#22c55e; color:#22c55e;"></span><span class="dot" style="background:#0ea5e9; color:#0ea5e9;"></span></div>
                    <span class="pill-label">Nen Aura</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #000000, #450a0a); color: #fff; border-color: #dc2626;" onclick="setTheme('death-note', this)">
                    <div class="dots-group"><span class="dot" style="background:#dc2626; color:#dc2626;"></span><span class="dot" style="background:#f3f4f6; color:#f3f4f6;"></span></div>
                    <span class="pill-label">Shinigami</span>
                </div>
                <div class="theme-pill" style="background: linear-gradient(135deg, #1a0b2e, #2d1b4e); color: #fff; border-color: #e879f9;" onclick="setTheme('anime-magic', this)">
                    <div class="dots-group"><span class="dot" style="background:#e879f9; color:#e879f9;"></span><span class="dot" style="background:#c084fc; color:#c084fc;"></span></div>
                    <span class="pill-label">Anime Sky</span>
                </div>

                <!-- 🌑 STANDARD DARK THEMES -->
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
            <!-- DEBUG BUTTON ADDED HERE -->
            <button class="primary-btn" style="background: #eab308; color: #000; padding: 12px; margin-top: 15px;" onclick="runBackgroundDebug()">🛠️ Run Background Debug</button>
            
            <button class="primary-btn" style="background: rgba(239, 68, 68, 0.1); color: var(--danger); padding: 12px; margin-top: 8px;" onclick="logout()">Logout</button>
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

            <!-- ========================================== -->
            <!-- NETFLIX / HOTSTAR STYLE THEATER VIEW       -->
            <!-- ========================================== -->
            <div id="view-theater" class="view-section">
                <div class="section-title">
                    <span>Universal Media Theater</span>
                </div>

                <div class="cinema-viewport" id="cinema-viewport">
                    <canvas id="webgl-canvas"></canvas>
                    <video id="hidden-video" class="hidden-video-feed" playsinline webkit-playsinline preload="auto"></video>
                    <div id="subtitle-overlay" class="subtitle-overlay" aria-live="polite"></div>
                    <div id="lyrics-scroller" class="lyrics-scroller"></div> <!-- 🟢 NEW: Lyrics Layer -->

                    <!-- Video Title Bar -->
                    <div class="cinema-title-bar" id="cinema-title">No Media Loaded</div>

                    <!-- Center Visible Controls (Liquid Glass SVGs) -->
                    <div class="center-controls" id="center-controls">
                        <div class="center-btn" onclick="skipPlayback(-15)" title="Rewind 15s">
                            <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor"><path d="M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z"/></svg>
                        </div>
                        <div class="center-btn" id="big-play-overlay" onclick="togglePlayback()">
                            <svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                        </div>
                        <div class="center-btn" onclick="skipPlayback(15)" title="Forward 15s">
                            <svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor"><path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z"/></svg>
                        </div>
                    </div>

                    <!-- Double-Tap Seek Zones (Invisible Overlay for Mobile Swipes) -->
                    <div class="seek-zone left" onclick="handleZoneTap('left', -15, event)"></div>
                    <div class="seek-zone right" onclick="handleZoneTap('right', 15, event)"></div>

                    <!-- 3D Over-Under / SBS Matrix Menu -->
                    <div id="menu-3d" class="matrix-3d-menu">
                        <div class="matrix-header" style="display: flex; justify-content: space-between; align-items: center;">
                            <span>Anaglyph 3D</span>
                            <button onclick="document.getElementById('menu-3d').classList.remove('open')" style="background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 6px 12px; font-size: 11px; font-weight: bold; cursor: pointer;">Close ✕</button>
                        </div>
                        <div class="matrix-grid">
                            <div>
                                <div class="matrix-column-title">In Format</div>
                                <div class="matrix-option" onclick="setMatrix3DIn('lr', this)">Left/Right <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DIn('tb', this)">Top/Bottom <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DIn('ci', this)">Column Interleaved <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DIn('ri', this)">Row Interleaved <div class="matrix-radio"></div></div>
                                <div class="matrix-option active" onclick="setMatrix3DIn('none', this)">None <div class="matrix-radio"></div></div>
                            </div>
                            <div>
                                <div class="matrix-column-title">Out Format</div>
                                <div class="matrix-option" onclick="setMatrix3DOut('gm', this)">Green/Magenta <div class="matrix-radio"></div></div>
                                <div class="matrix-option active" onclick="setMatrix3DOut('rc', this)">Red/Cyan <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DOut('ba', this)">Blue/Amber <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DOut('lf', this)">Left Frame First <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DOut('rf', this)">Right Frame First <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DOut('vr', this)">VR <div class="matrix-radio"></div></div>
                                <div class="matrix-option" onclick="setMatrix3DOut('2d', this)">2D <div class="matrix-radio"></div></div>
                            </div>
                        </div>
                    </div>

                    <!-- Quick Settings Popup -->
                    <div id="media-settings-popup" class="settings-popup">
                        <div class="pop-title" style="display: flex; justify-content: space-between; align-items: center;">
                            <span>Stream Settings</span>
                            <button onclick="toggleSettingsPopup()" style="background: rgba(239,68,68,0.2); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 6px 12px; font-size: 11px; font-weight: bold; cursor: pointer;">Close ✕</button>
                        </div>
                        
                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">EXTERNAL PLAYERS</label>
                        <div style="display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap;">
                            <button class="primary-btn" style="padding: 8px 12px; font-size: 11px; background: #ea580c; width: auto;" onclick="openExternalPlayer('vlc')">VLC</button>
                            <button class="primary-btn" style="padding: 8px 12px; font-size: 11px; background: #2563eb; width: auto;" onclick="openExternalPlayer('mx')">MX Player</button>
                            <button class="primary-btn" style="padding: 8px 12px; font-size: 11px; background: #8b5cf6; width: auto;" onclick="openExternalPlayer('mpv')">MPV</button>
                            <button class="primary-btn" style="padding: 8px 12px; font-size: 11px; background: #f59e0b; width: auto;" onclick="openExternalPlayer('infuse')">Infuse</button>
                            <button class="primary-btn" style="padding: 8px 12px; font-size: 11px; background: #10b981; width: auto;" onclick="openExternalPlayer('outplayer')">Outplayer</button>
                        </div>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">VIDEO QUALITY</label>
                        <select id="pop-quality-select" class="pop-select" onchange="applyTrackSelection()"></select>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">AUDIO STREAM</label>
                        <select id="pop-audio-select" class="pop-select" onchange="applyTrackSelection()"></select>
                        
                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">PLAYBACK SPEED</label>
                        <select id="pop-speed-select" class="pop-select" onchange="applyPlaybackSpeed()">
                            <option value="0.25">0.25x</option>
                            <option value="0.5">0.5x</option>
                            <option value="0.75">0.75x</option>
                            <option value="1" selected>1.0x (Normal)</option>
                            <option value="1.25">1.25x</option>
                            <option value="1.5">1.5x</option>
                            <option value="1.75">1.75x</option>
                            <option value="2">2.0x</option>
                        </select>

                        <!-- NEW: Video Filter Sliders -->
                        <label style="font-size: 11px; color: var(--accent); font-weight: bold; margin-top: 10px;">VIDEO FILTERS & PRESETS</label>
                        <div style="display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap;">
                            <button class="theme-btn" onclick="setFilterPreset('none')">None</button>
                            <button class="theme-btn" onclick="setFilterPreset('vivid')">Vivid</button>
                            <button class="theme-btn" onclick="setFilterPreset('cinematic')">Cinematic</button>
                            <button class="theme-btn" onclick="setFilterPreset('soft')">Soft</button>
                            <button class="theme-btn" onclick="setFilterPreset('high_contrast')">Contrast+</button>
                            <button class="theme-btn" onclick="setFilterPreset('grayscale')">B & W</button>
                            <button class="theme-btn" onclick="setFilterPreset('cyberpunk')">Cyberpunk</button>
                            <button class="theme-btn" onclick="setFilterPreset('vintage')">Vintage</button>
                            <button class="theme-btn" onclick="setFilterPreset('warm')">Warm</button>
                            <button class="theme-btn" onclick="setFilterPreset('cool')">Cool</button>
                        </div>
                        
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px;">
                            <div>
                                <label style="font-size: 10px; color: var(--subtext);">Brightness: <span id="val-bright">100</span>%</label>
                                <input type="range" id="filter-bright" min="20" max="200" value="100" oninput="applyVideoFilters()" style="width: 100%; accent-color: var(--accent);">
                            </div>
                            <div>
                                <label style="font-size: 10px; color: var(--subtext);">Contrast: <span id="val-contrast">100</span>%</label>
                                <input type="range" id="filter-contrast" min="20" max="200" value="100" oninput="applyVideoFilters()" style="width: 100%; accent-color: var(--accent);">
                            </div>
                            <div>
                                <label style="font-size: 10px; color: var(--subtext);">Saturation: <span id="val-sat">100</span>%</label>
                                <input type="range" id="filter-sat" min="0" max="300" value="100" oninput="applyVideoFilters()" style="width: 100%; accent-color: var(--accent);">
                            </div>
                            <div>
                                <label style="font-size: 10px; color: var(--subtext);">Hue: <span id="val-hue">0</span>°</label>
                                <input type="range" id="filter-hue" min="-180" max="180" value="0" oninput="applyVideoFilters()" style="width: 100%; accent-color: var(--accent);">
                            </div>
                            <div>
                                <label style="font-size: 10px; color: var(--subtext);">Sepia: <span id="val-sepia">0</span>%</label>
                                <input type="range" id="filter-sepia" min="0" max="100" value="0" oninput="applyVideoFilters()" style="width: 100%; accent-color: var(--accent);">
                            </div>
                            <div>
                                <label style="font-size: 10px; color: var(--subtext);">Blur (Softness): <span id="val-blur">0</span>px</label>
                                <input type="range" id="filter-blur" min="0" max="10" value="0" step="0.5" oninput="applyVideoFilters()" style="width: 100%; accent-color: var(--accent);">
                            </div>
                        </div>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">SUBTITLES</label>
                        <select id="pop-sub-select" class="pop-select" onchange="applySubtitleSelection()"></select>
                        
                        <!-- NEW: Subtitle Fonts & Weights -->
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                            <div>
                                <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">FONT STYLE</label>
                                <select id="subtitle-font-select" class="pop-select" onchange="applySubtitleStyle()">
                                    <option value="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" selected>Standard (Sans)</option>
                                    <option value="Georgia, serif">Cinematic (Serif)</option>
                                    <option value="'Courier New', monospace">Typewriter</option>
                                    <option value="'Comic Sans MS', cursive">Casual (Comic)</option>
                                    <option value="Impact, fantasy">Bold Impact</option>
                                </select>
                            </div>
                            <div>
                                <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">FONT WEIGHT</label>
                                <select id="subtitle-weight-select" class="pop-select" onchange="applySubtitleStyle()">
                                    <option value="400">Normal</option>
                                    <option value="600" selected>Semi-Bold</option>
                                    <option value="800">Extra Bold</option>
                                    <option value="900">Heavy</option>
                                </select>
                            </div>
                        </div>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold; margin-top: 10px;">SUBTITLE SIZE</label>
                        <select id="subtitle-size-select" class="pop-select" onchange="applySubtitleStyle()">
                            <option value="10">10 px</option>
                            <option value="12">12 px</option>
                            <option value="14">14 px</option>
                            <option value="16">16 px</option>
                            <option value="18">18 px</option>
                            <option value="20" selected>20 px</option> <!-- 🟢 FIX: Moved 'selected' to 20px -->
                            <option value="22">22 px</option>
                            <option value="26">26 px</option>
                            <option value="30">30 px</option>
                            <option value="36">36 px</option>
                            <option value="42">42 px</option>
                        </select>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">SUBTITLE COLOR</label>
                        <input id="subtitle-color-input" type="color" value="#ffffff" onchange="applySubtitleStyle()" style="width: 100%; height: 40px; border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); border-radius: 10px; background: color-mix(in srgb, var(--bg) var(--glass-bg, 100%), transparent); margin-bottom: 14px; padding: 4px; backdrop-filter: blur(var(--glass-blur, 0px));">

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">SUBTITLE BACKGROUND</label>
                        <input id="subtitle-bg-input" type="color" value="#000000" onchange="applySubtitleStyle()" style="width: 100%; height: 40px; border: 1px solid color-mix(in srgb, var(--card-border) var(--glass-border, 100%), transparent); border-radius: 10px; background: color-mix(in srgb, var(--bg) var(--glass-bg, 100%), transparent); margin-bottom: 14px; padding: 4px; backdrop-filter: blur(var(--glass-blur, 0px));">

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">BACKGROUND OPACITY</label>
                        <input id="subtitle-bg-alpha" type="range" min="0" max="100" value="70" oninput="applySubtitleStyle()" style="width: 100%; margin-bottom: 14px;">

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">SUBTITLE SYNC DELAY (SECONDS)</label>
                        <div style="display: flex; gap: 8px; margin-bottom: 14px; align-items: center;">
                            <input id="subtitle-sync-slider" type="range" min="-10" max="10" step="0.25" value="0" oninput="updateSubtitleSync(this.value)" style="flex: 1; accent-color: var(--accent);">
                            <span id="subtitle-sync-val" style="color: var(--text); font-size: 12px; font-weight: bold; font-family: monospace; min-width: 50px; text-align: right;">0.00s</span>
                        </div>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold; margin-top: 10px;">SUBTITLE VERTICAL POSITION</label>
                        <div style="display: flex; gap: 8px; margin-bottom: 14px; align-items: center;">
                            <span style="color: var(--subtext); font-size: 10px; font-weight: bold;">TOP</span>
                            <input id="subtitle-pos-slider" type="range" min="2" max="95" value="88" oninput="applySubtitleStyle()" style="flex: 1; accent-color: var(--accent);">
                            <span style="color: var(--subtext); font-size: 10px; font-weight: bold;">BOT</span>
                        </div>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold; margin-top: 10px;">SUBTITLE WIDTH (STRETCH LINES)</label>
                        <div style="display: flex; gap: 8px; margin-bottom: 14px; align-items: center;">
                            <span style="color: var(--subtext); font-size: 10px; font-weight: bold;">NARROW</span>
                            <input id="subtitle-width-slider" type="range" min="30" max="100" value="95" oninput="applySubtitleStyle()" style="flex: 1; accent-color: var(--accent);"> <!-- 🟢 FIX: Changed default value to 95 -->
                            <span style="color: var(--subtext); font-size: 10px; font-weight: bold;">WIDE</span>
                        </div>

                        <label style="font-size: 11px; color: var(--subtext); font-weight: bold;">ASPECT RATIO</label>
                        <select id="pop-aspect-select" class="pop-select" onchange="applyAspectRatio(this.value)">
                            <option value="contain">Fit (Default)</option>
                            <option value="cover">Zoom / Fill Screen</option>
                            <option value="stretch">Stretch</option>
                            <option value="16-9">16:9 Standard</option>
                            <option value="21-9">21:9 Cinemascope</option>
                            <option value="4-3">4:3 Retro / IMAX</option>
                        </select>
                    </div>

                    <!-- HUD Overlay -->
                    <div class="cinema-hud" id="cinema-hud">
                        <div class="cinema-scrubber-bar" id="cinema-scrubber" onclick="seekPlayback(event)">
                            <div class="scrubber-buffer" id="scrubber-buffer"></div>
                            <div class="scrubber-fill" id="scrubber-fill"></div>
                        </div>
                        <div class="cinema-controls-row">
                            <div class="ctrl-group">
                                <button class="cinema-btn" id="hud-play-btn" onclick="togglePlayback()" title="Play/Pause">
                                    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                                </button>
                                <span class="time-badge" id="hud-time">00:00 / 00:00</span>
                            </div>
                            <div class="ctrl-group" style="gap: 16px;">
                                <!-- Mute / Sound -->
                                <button class="cinema-btn" id="hud-mute-btn" onclick="toggleMute()" title="Mute/Unmute">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
                                </button>
                                <!-- Picture-in-Picture -->
                                <button class="cinema-btn" id="hud-pip-btn" onclick="togglePiP()" title="Picture in Picture">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M19 7h-8v6h8V7zm2-4H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16.01H3V4.98h18v14.03z"/></svg>
                                </button>
                                <!-- Brightness Cycler -->
                                <button class="cinema-btn" id="hud-brightness-btn" onclick="cycleBrightness()" title="Brightness">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58c-.39-.39-1.03-.39-1.41 0-.39.39-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0 .39-.39.39-1.03 0-1.41L5.99 4.58zm12.37 12.37c-.39-.39-1.03-.39-1.41 0-.39.39-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0 .39-.39.39-1.03 0-1.41l-1.06-1.06zm1.06-10.96c.39-.39.39-1.03 0-1.41-.39-.39-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41.39.39 1.03.39 1.41 0l1.06-1.06zM7.05 18.36c.39-.39.39-1.03 0-1.41-.39-.39-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41.39.39 1.03.39 1.41 0l1.06-1.06z"/></svg>
                                </button>
                                <!-- Rotate -->
                                <button class="cinema-btn" id="hud-rotate-btn" onclick="toggleOrientation()" title="Rotate Screen">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M16.48 2.52c3.27 1.55 5.61 4.72 5.97 8.48h1.5C23.44 4.84 18.29 0 12 0l-.66.03 3.81 3.81 1.33-1.32zm-6.25-.77c-.59-.59-1.54-.59-2.12 0L1.75 8.11c-.59.59-.59 1.54 0 2.12l12.02 12.02c.59.59 1.54.59 2.12 0l6.36-6.36c.59-.59.59-1.54 0-2.12L10.23 1.75zm4.6 19.44L2.81 9.17l6.36-6.36 12.02 12.02-6.36 6.36zm-7.3-3.05v-1.42c-3.27-1.55-5.61-4.72-5.97-8.48h-1.5C.56 19.16 5.71 24 12 24l.66-.03-3.81-3.81-1.32 1.32z"/></svg>
                                </button>
                                <!-- 3D Matrix -->
                                <button class="cinema-btn" id="hud-3d-btn" onclick="toggleMatrixPopup()" title="3D Matrix">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h20"/><path d="M12 2v20"/><path d="M4.93 4.93l14.14 14.14"/><path d="M4.93 19.07L19.07 4.93"/></svg>
                                </button>
                                <!-- Settings & Tracks -->
                                <button class="cinema-btn" id="hud-settings-btn" onclick="toggleSettingsPopup()" title="Tracks & Settings">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M19.43 12.98c.04-.32.07-.64.07-.98s-.03-.66-.07-.98l2.11-1.65c.19-.15.24-.42.12-.64l-2-3.46c-.12-.22-.39-.3-.61-.22l-2.49 1c-.52-.4-1.08-.73-1.69-.98l-.38-2.65C14.46 2.18 14.25 2 14 2h-4c-.25 0-.46.18-.49.42l-.38 2.65c-.61.25-1.17.59-1.69.98l-2.49-1c-.23-.09-.49 0-.61.22l-2 3.46c-.13.22-.07.49.12.64l2.11 1.65c-.04.32-.07.65-.07.98s.03.66.07.98l-2.11 1.65c-.19.15-.24.42-.12.64l2 3.46c.12.22.39.3.61.22l2.49-1c.52.4 1.08.73 1.69.98l.38 2.65c.03.24.24.42.49.42h4c.25 0 .46-.18.49-.42l.38-2.65c.61-.25 1.17-.59 1.69-.98l2.49 1c.23.09.49 0 .61-.22l2-3.46c.12-.22.07-.49-.12-.64l-2.11-1.65zM12 15.5c-1.93 0-3.5-1.57-3.5-3.5s1.57-3.5 3.5-3.5 3.5 1.57 3.5 3.5-1.57 3.5-3.5 3.5z"/></svg>
                                </button>
                                <!-- Fullscreen -->
                                <button class="cinema-btn" id="hud-fullscreen-btn" onclick="toggleFullScreen()" title="Fullscreen">
                                    <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>
                                </button>
                            </div>
                        </div>
                    </div>
                </div> <!-- END OF CINEMA VIEWPORT -->

                <div class="card" style="margin-top: 20px;">
                    <div class="input-group">
                        <label>Load Stream (Telegram Post Link or Direct Video/Audio URL)</label>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" id="theater-stream-url" placeholder="https://t.me/c/123/456 or https://domain.com/movie.mkv" style="flex: 1;">
                            <button class="primary-btn" id="theater-load-btn" style="width: auto; padding: 0 24px;" onclick="loadTheaterMedia()">Load & Play</button>
                            <button class="primary-btn" style="width: auto; padding: 0 15px; background: #ef4444;" onclick="cancelTheaterStream()">Stop</button>
                        </div>
                    </div>
                    <!-- NEW: External Media Tracks (URL & Local File) -->
                    <div class="input-group" style="margin-top: 15px;">
                        <label>External Audio Track (URL or Local File)</label>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <input type="text" id="ext-audio-url" placeholder="Paste URL..." style="flex: 1;">
                            <button class="primary-btn" style="width: auto; padding: 0 15px; background: #8b5cf6;" onclick="loadExternalAudioUrl()">Load URL</button>
                            <label class="primary-btn" style="width: auto; padding: 12px 15px; background: #475569; cursor: pointer; margin: 0;">
                                📁 File <input type="file" accept="audio/*" style="display: none;" onchange="loadExternalAudioFile(event)">
                            </label>
                        </div>
                    </div>
                    <div class="input-group">
                        <label>External Subtitles (URL or .vtt Local File)</label>
                        <div style="display: flex; gap: 8px; align-items: center;">
                            <input type="text" id="ext-sub-url" placeholder="Paste URL..." style="flex: 1;">
                            <button class="primary-btn" style="width: auto; padding: 0 15px; background: #2dd4bf;" onclick="loadExternalSubtitlesUrl()">Load URL</button>
                            <label class="primary-btn" style="width: auto; padding: 12px 15px; background: #475569; cursor: pointer; margin: 0;">
                                📁 File <input type="file" accept=".vtt,.srt,.txt" style="display: none;" onchange="loadExternalSubtitlesFile(event)">
                            </label>
                        </div>
                    </div>
                    <!-- Hidden Audio Player for Sync -->
                    <audio id="ext-audio-player" style="display:none;" preload="auto"></audio>
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
                    <div style="display: flex; gap: 8px;">
                        <button id="refresh-chats-btn" class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px;" onclick="loadWebChats(true)">🔄 Refresh</button>
                        <button class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px; background: #10b981;" onclick="downloadChatsTxt()">📥 Download</button>
                    </div>
                </div>
                
                <div id="web-chats-warning" class="card" style="display:none; border-color: var(--danger); margin-bottom: 20px;">
                    <strong id="web-chats-warning-title" style="color: var(--danger);">⚠️ Telegram Session Not Connected</strong>
                    <p id="web-chats-warning-text" style="font-size: 12px; color: #94a3b8; margin: 6px 0 0 0;">Please connect your Telegram account in the <b>Settings</b> tab or run <code>/login</code> in the bot to view your dialog list.</p>
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

            <!-- 🟢 NEW: 3D WORLD GLOBE EXPLORER -->
            <div id="view-globe" class="view-section">
                <div class="section-title">
                    <span>Interactive World Explorer</span>
                </div>
                
                <div class="card" style="margin-bottom: 20px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                    <input type="text" id="globe-search" placeholder="🔍 Search any country (e.g. India, Japan, France)..." style="flex: 1; padding: 14px 20px; border-radius: 14px; border: 1px solid var(--card-border); background: color-mix(in srgb, var(--bg) 60%, transparent); color: #fff; font-size: 14px; outline: none; backdrop-filter: blur(10px);">
                    <button class="primary-btn" style="width: auto; padding: 0 25px;" onclick="searchGlobeCountry()">Search</button>
                </div>

                <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                    <!-- The 3D Canvas -->
                    <div class="card" style="flex: 1; min-width: 320px; padding: 0; overflow: hidden; height: 65vh; position: relative; border-radius: 20px; display: flex; align-items: center; justify-content: center; background: #000;">
                        <div id="globe-loading" style="position: absolute; z-index: 5; color: var(--accent); font-weight: bold; font-size: 16px; text-transform: uppercase; letter-spacing: 2px;">⏳ Booting Global Satellites...</div>
                        <div id="globe-viz" style="width: 100%; height: 100%;"></div>
                    </div>

                    <!-- The Information Panel -->
                    <div id="country-data-panel" class="card" style="flex: 1; min-width: 320px; max-height: 65vh; overflow-y: auto; display: none; padding: 30px;">
                        <div style="text-align: center; margin-bottom: 20px;">
                            <img id="c-flag" src="" style="width: 120px; border-radius: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); margin-bottom: 15px;">
                            <h2 id="c-name" style="margin: 0 0 5px 0; color: #fff; font-size: 28px; text-shadow: 0 0 15px var(--glow);">Country Name</h2>
                            <div id="c-time" style="color: var(--accent); font-weight: 900; font-size: 24px; font-family: monospace; letter-spacing: 1px; margin-top: 10px;">--:--:--</div>
                            <div style="font-size: 11px; color: var(--subtext); text-transform: uppercase; font-weight: bold; margin-top: 4px;">Live Local Time</div>
                        </div>

                        <div style="background: rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.05); border-radius: 16px; padding: 20px; margin-bottom: 20px;">
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                                <div><span style="color: var(--subtext); font-size: 11px; text-transform: uppercase;">Capital</span><div id="c-cap" style="color: #fff; font-size: 14px; font-weight: 700;">-</div></div>
                                <div><span style="color: var(--subtext); font-size: 11px; text-transform: uppercase;">Region</span><div id="c-reg" style="color: #fff; font-size: 14px; font-weight: 700;">-</div></div>
                                <div><span style="color: var(--subtext); font-size: 11px; text-transform: uppercase;">Population</span><div id="c-pop" style="color: #10b981; font-size: 14px; font-weight: 700;">-</div></div>
                                <div><span style="color: var(--subtext); font-size: 11px; text-transform: uppercase;">Currencies</span><div id="c-curr" style="color: #f59e0b; font-size: 14px; font-weight: 700;">-</div></div>
                            </div>
                            <div style="margin-top: 15px;"><span style="color: var(--subtext); font-size: 11px; text-transform: uppercase;">Languages</span><div id="c-lang" style="color: #fff; font-size: 14px; font-weight: 700;">-</div></div>
                        </div>

                        <h4 style="color: #fff; margin: 0 0 12px 0; font-size: 15px; border-bottom: 1px solid var(--card-border); padding-bottom: 8px;">📖 History & Current Details</h4>
                        <div id="c-wiki" style="font-size: 13px; color: #cbd5e1; line-height: 1.6; text-align: justify;">Select a country on the globe to analyze data.</div>
                    </div>
                </div>
            </div>

            <!-- SPEEDTEST VIEW -->
            <div id="view-network" class="view-section">
                <div class="section-title">
                    <span>Live Network & Activity</span>
                    <button class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px;" onclick="fetchNetworkStats()">🔄 Refresh</button>
                </div>
                
                <div class="card" style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <h3 style="margin: 0; font-size: 16px; color: #fff;">👥 User Activity</h3>
                        <span id="net-active-count" style="font-size: 12px; color: var(--accent); font-weight: 800;">0 ONLINE</span>
                    </div>
                    <div style="font-size: 12px; color: var(--subtext); margin-bottom: 15px;">Who's watching, where from, and on what</div>
                    <div id="network-active-list">
                        <div style="color: #64748b; font-size: 13px;">No active streams right now.</div>
                    </div>
                </div>

                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <h3 style="margin: 0; font-size: 16px; color: #fff;">🔴 Live Network Statistics</h3>
                    </div>
                    <div style="font-size: 12px; color: var(--subtext); margin-bottom: 15px;">Current & Recent Sessions</div>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
                        <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); padding: 15px; border-radius: 14px; text-align: center;">
                            <div style="font-size: 11px; color: var(--subtext); font-weight: 800; letter-spacing: 1px; text-transform: uppercase;">Live Now</div>
                            <div id="net-stat-live" style="font-size: 28px; font-weight: 900; color: #fff; margin-top: 5px;">0</div>
                        </div>
                        <div style="background: rgba(0,0,0,0.3); border: 1px solid var(--card-border); padding: 15px; border-radius: 14px; text-align: center;">
                            <div style="font-size: 11px; color: var(--subtext); font-weight: 800; letter-spacing: 1px; text-transform: uppercase;">Recent 24h</div>
                            <div id="net-stat-recent" style="font-size: 28px; font-weight: 900; color: #fff; margin-top: 5px;">0</div>
                        </div>
                    </div>
                    
                    <h3 style="margin: 0 0 10px 0; font-size: 14px; color: #fff;">Worker Bots Active</h3>
                    <div id="net-workers-count" style="font-size: 13px; color: #10b981; margin-bottom: 20px;">0 bots handling parallel chunks</div>

                    <h3 style="margin: 0 0 10px 0; font-size: 14px; color: #fff;">Recent Streams</h3>
                    <div id="network-recent-list" style="max-height: 300px; overflow-y: auto; padding-right: 5px; scrollbar-width: thin;">
                        <div style="color: #64748b; font-size: 13px;">No recent streams.</div>
                    </div>
                </div>
            </div>

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
                        <button class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px; background: #3b82f6;" onclick="copyLogs()">📋 Copy</button>
                        <a id="download-log-btn" href="#" onclick="downloadLogsAuth(event)" class="primary-btn" style="width: auto; padding: 8px 14px; font-size: 11px; text-decoration: none; text-align: center; background: #10b981;">📥 Download</a>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                    <input type="checkbox" id="live-logs-toggle" style="width: 16px; height: 16px; accent-color: var(--accent);" onchange="toggleLiveLogs(this.checked)">
                    <label for="live-logs-toggle" style="font-size: 12px; color: #94a3b8; font-weight: 700; cursor: pointer;">LIVE TAIL (Auto-refresh every 3s)</label>
                </div>
                <div style="background: #000; border: 1px solid var(--card-border); border-radius: 16px; padding: 16px; font-family: monospace; font-size: 11px; color: #38bdf8; height: 400px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;" id="log-terminal">Loading logs...</div>
            </div>

            <div id="view-mediainfo" class="view-section">
                <div class="section-title">MediaInfo Inspector</div>
                <div class="card" style="margin-bottom: 20px;">
                    <div class="input-group">
                        <label>Telegram File Link or Direct URL</label>
                        <input type="text" id="mi-link" placeholder="https://t.me/c/123/456 or http://...">
                    </div>
                    <button class="primary-btn" id="mi-btn" style="background: #8b5cf6;" onclick="runWebMediaInfo()">Analyze File</button>
                </div>
                <div class="card" id="mi-results-card" style="display: none;">
                    <div id="mi-results-content" style="font-family: monospace; font-size: 13px; color: var(--text); overflow-x: auto; white-space: pre-wrap; line-height: 1.5;"></div>
                </div>
            </div>

            <div id="view-spectrogram" class="view-section">
                <div class="section-title">Spectrogram & DSP Analyzer</div>
                <div class="card" style="margin-bottom: 20px;">
                    <p style="font-size: 12px; color: var(--subtext); margin-bottom: 15px;">Paste a direct Telegram link (`t.me/c/...`) or HTTP link to an audio file. The server will download a small chunk and render the frequencies.</p>
                    <div class="input-group">
                        <label>Audio Link</label>
                        <input type="text" id="spec-link" placeholder="https://t.me/c/123/456 or http://...">
                    </div>
                    <button class="primary-btn" id="spec-btn" style="background: #e11d48;" onclick="runWebSpectrogram()">Generate Spectrogram</button>
                </div>
                <div class="card" id="spec-results-card" style="display: none; text-align: center;">
                    <img id="spec-image" style="max-width: 100%; border-radius: 12px; margin-bottom: 15px; border: 1px solid var(--card-border);" />
                    <div id="spec-html" style="font-family: monospace; font-size: 13px; color: var(--text); overflow-x: auto; white-space: pre-wrap; line-height: 1.5; text-align: left;"></div>
                </div>
            </div>

            <!-- ========================================== -->
            <!-- NEW DEDICATED MEDIA EDITOR PAGE            -->
            <!-- ========================================== -->
            <div id="view-editor" class="view-section">
                <div class="section-title">Media Track Editor & Remuxer</div>
                
                <div class="card" style="margin-bottom: 20px;">
                    <div class="input-group">
                        <label>Target Media Link (Telegram or Direct URL)</label>
                        <div style="display: flex; gap: 8px;">
                            <input type="text" id="editor-stream-url" placeholder="https://t.me/c/123/456 or https://domain.com/movie.mkv" style="flex: 1;">
                            <button class="primary-btn" id="editor-load-btn" style="width: auto; padding: 0 24px; background: #8b5cf6;" onclick="loadEditorMedia()">Analyze Tracks</button>
                        </div>
                    </div>
                </div>
                
                <div class="card" id="editor-workspace" style="display: none; border-color: var(--accent);">
                    <h3 style="margin-top: 0; color: #fff; font-size: 16px; margin-bottom: 15px;">🛠 Inspect & Edit Tracks</h3>
                    
                    <div id="editor-tracks-container" style="max-height: 400px; overflow-y: auto; margin-bottom: 20px; display: flex; flex-direction: column; gap: 10px; padding-right: 5px;">
                        <!-- Dynamic Tracks Load Here -->
                    </div>

                    <div class="input-group" style="margin-top: 15px;">
                        <label>New File Name (e.g. Edited_Movie.mkv)</label>
                        <input type="text" id="editor-filename" placeholder="Output.mkv">
                    </div>

                    <div class="input-group">
                        <label>Upload Destination</label>
                        <select id="editor-dest" class="pop-select">
                            <option value="tg">Telegram (Saved Messages)</option>
                            <option value="gofile">GoFile.io (Public Link)</option>
                        </select>
                    </div>

                    <button class="primary-btn" id="editor-submit-btn" style="margin-top: 10px;" onclick="submitEditorTask()">🚀 Process & Upload</button>
                    <div id="editor-status" style="margin-top: 15px; font-size: 13px; font-weight: bold; color: var(--accent); text-align: center; display: none;"></div>
                </div>
            </div>
                        
            <div id="view-settings" class="view-section">
                
                <div class="section-title">Interface Settings</div>
                <div class="card" style="margin-bottom: 20px;">

                    <h3 style="margin-top: 0; font-size: 16px; color: #fff;">Performance Mode (Anti-Lag)</h3>
                    <p style="font-size: 12px; color: #94a3b8; margin-bottom: 15px;">Disables 3D background blobs, glassmorphism, and heavy shadows. Highly recommended for Android TVs.</p>
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 25px;">
                        <input type="checkbox" id="perf-mode-toggle" style="width: 18px; height: 18px; accent-color: var(--accent);" onchange="togglePerformanceMode(this.checked)">
                        <label for="perf-mode-toggle" style="font-size: 13px; color: #fff; font-weight: bold; cursor: pointer;">Enable Maximum Performance</label>
                    </div>

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

                <div class="section-title">Multi-Bot Worker Pool (Speed Multiplier)</div>
                <div class="card" style="margin-bottom: 20px;">
                    <h3 style="margin-top: 0; font-size: 16px; color: #fff;">Auxiliary Bot Tokens</h3>
                    <p style="font-size: 12px; color: #94a3b8; margin-bottom: 12px;">Add extra bot tokens (one per line or comma-separated) to enable parallel chunk downloads and eliminate 1080p/4K buffering.</p>
                    <div class="input-group">
                        <textarea id="worker-tokens-input" rows="3" placeholder="123456:ABC-DEF...&#10;789012:GHI-JKL..." style="width: 100%; padding: 12px; border-radius: 12px; border: 1px solid var(--card-border); background: var(--bg); color: var(--text); font-family: monospace; font-size: 12px; outline: none;"></textarea>
                    </div>
                    <button class="primary-btn" style="padding: 10px; width: auto;" onclick="saveWorkerTokens()">Save Worker Tokens</button>
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
                <div class="input-group">
                    <label>Destination Chat ID / Topic</label>
                    <div style="display: flex; gap: 8px;">
                        <input type="text" id="t-dest" placeholder="Enter ID or click Browse ->" style="flex: 1;" required>
                        <button type="button" class="primary-btn" style="width: auto; padding: 0 15px;" onclick="openChatSelector()">Browse</button>
                    </div>
                </div>

                <!-- Chat Selector Modal -->
                <div class="modal" id="chatSelectorModal" style="z-index: 310;">
                    <div class="modal-content" style="max-width: 400px; padding: 20px;">
                        <h3 style="margin-top: 0; color: #fff; font-size: 16px;">Select Destination</h3>
                        <input type="text" id="chat-search-input" placeholder="Search chats..." oninput="filterSelectorChats()" style="width: 100%; padding: 12px; margin-bottom: 12px; border-radius: 12px; border: 1px solid var(--card-border); background: var(--bg); color: var(--text); outline: none;">
                        <div id="chat-selector-list" style="max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;"></div>
                        <button type="button" class="btn-cancel" style="margin-top: 12px; width: 100%;" onclick="closeChatSelector()">Close</button>
                    </div>
                </div>

                <!-- Topic Selector Modal -->
                <div class="modal" id="topicSelectorModal" style="z-index: 320;">
                    <div class="modal-content" style="max-width: 400px; padding: 20px;">
                        <h3 style="margin-top: 0; color: #fff; font-size: 16px;">Select Topic</h3>
                        <div id="topic-selector-list" style="max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;">
                            <div style="color: var(--subtext);">Loading topics...</div>
                        </div>
                        <button type="button" class="btn-cancel" style="margin-top: 12px; width: 100%;" onclick="closeTopicSelector()">Cancel</button>
                    </div>
                </div>
                
                <!-- 🟢 NEW: Liquid Glass Chat Details Modal -->
                <div class="modal" id="chatDetailsModal" style="z-index: 330;">
                    <div class="modal-content" style="max-width: 480px; padding: 25px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                            <h3 style="margin: 0; color: #fff; font-size: 16px; text-transform: uppercase; letter-spacing: 1px;" id="cd-title">Chat Details</h3>
                            <button type="button" onclick="closeChatDetails()" style="background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; padding: 6px 12px; font-size: 11px; font-weight: bold; cursor: pointer; transition: 0.2s;">Close ✕</button>
                        </div>
                        <div id="cd-loading" style="color: var(--accent); font-weight: bold; text-align: center; padding: 20px;">⏳ Deep Scanning Telegram Servers...</div>
                        <div id="cd-content" style="display: none;">
                            <div style="background: rgba(0,0,0,0.3); border: 1px solid color-mix(in srgb, var(--card-border) 50%, transparent); border-radius: 16px; padding: 16px; margin-bottom: 15px; box-shadow: inset 0 0 15px rgba(0,0,0,0.5);">
                                <div style="font-size: 12px; color: var(--subtext); margin-bottom: 8px; display: flex; justify-content: space-between;"><span>ID:</span> <code id="cd-id" style="color: var(--accent); font-weight: 800;"></code></div>
                                <div style="font-size: 12px; color: var(--subtext); margin-bottom: 8px; display: flex; justify-content: space-between;"><span>Type:</span> <strong id="cd-type" style="color: #fff;"></strong></div>
                                <div style="font-size: 12px; color: var(--subtext); margin-bottom: 8px; display: flex; justify-content: space-between;"><span>Members:</span> <strong id="cd-members" style="color: #10b981;"></strong></div>
                                <div style="font-size: 12px; color: var(--subtext); display: flex; justify-content: space-between;"><span>Total Messages:</span> <strong id="cd-msgs" style="color: #38bdf8;"></strong></div>
                            </div>
                            <div id="cd-desc-container" style="background: rgba(0,0,0,0.3); border: 1px solid color-mix(in srgb, var(--card-border) 50%, transparent); border-radius: 14px; padding: 15px; margin-bottom: 15px; font-size: 12px; color: #cbd5e1; max-height: 100px; overflow-y: auto; white-space: pre-wrap; display: none;"></div>
                            
                            <div id="cd-topics-container" style="display: none; margin-top: 20px;">
                                <h4 style="margin: 0 0 12px 0; color: #fff; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--card-border); padding-bottom: 6px;">📂 Active Forum Topics</h4>
                                <div id="cd-topics-list" style="max-height: 220px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding-right: 5px;"></div>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- 🟢 END OF NEW MODAL -->

                <div class="input-group" id="delay-group">
                    <label>Forward Delay (Seconds)</label>
                    <input type="number" id="t-delay" value="3" min="3">
                </div>
                <div class="input-group">
                    <label>Media Filters (Allowed Types)</label>
                    <div class="filter-grid">
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Video" checked> Video</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Document" checked> Document</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Audio" checked> Audio</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Photo" checked> Photo</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Voice" checked> Voice</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Text" checked> Text</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Animation" checked> Animation</label>
                        <label class="filter-checkbox"><input type="checkbox" name="ftype" value="Sticker" checked> Sticker</label>
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

        // 🟢 NEW: Custom Liquid Glass Dropdown Engine
        function initCustomSelects() {
            document.querySelectorAll('.pop-select').forEach(select => {
                // Wipe any existing custom dropdowns if re-rendering (e.g. on new movie load)
                const existing = select.nextElementSibling;
                if (existing && existing.classList.contains('glass-select-container')) {
                    existing.remove();
                }

                // Create Wrapper
                const container = document.createElement('div');
                container.className = 'glass-select-container';

                // Create Display Box
                const display = document.createElement('div');
                display.className = 'glass-select-display';
                display.innerHTML = select.options[select.selectedIndex]?.text || 'Select...';

                // Create Options List
                const dropdown = document.createElement('div');
                dropdown.className = 'glass-select-dropdown';

                Array.from(select.options).forEach((opt, idx) => {
                    const item = document.createElement('div');
                    item.className = 'glass-select-item';
                    if (idx === select.selectedIndex) item.classList.add('same-as-selected');
                    item.innerHTML = opt.text;
                    item.addEventListener('click', (e) => {
                        e.stopPropagation();
                        select.selectedIndex = idx;
                        display.innerHTML = opt.text;
                        dropdown.querySelectorAll('.same-as-selected').forEach(el => el.classList.remove('same-as-selected'));
                        item.classList.add('same-as-selected');
                        dropdown.classList.remove('show');
                        display.classList.remove('active');
                        // Fire the native onchange event (applyTrackSelection, etc.)
                        select.dispatchEvent(new Event('change'));
                    });
                    dropdown.appendChild(item);
                });

                display.addEventListener('click', (e) => {
                    e.stopPropagation();
                    // Close other open dropdowns
                    document.querySelectorAll('.glass-select-dropdown.show').forEach(d => {
                        if (d !== dropdown) {
                            d.classList.remove('show');
                            d.previousElementSibling.classList.remove('active');
                        }
                    });
                    dropdown.classList.toggle('show');
                    display.classList.toggle('active');
                    // Auto-scroll to selected item
                    if (dropdown.classList.contains('show')) {
                        const activeItem = dropdown.querySelector('.same-as-selected');
                        if (activeItem) activeItem.scrollIntoView({block: 'nearest'});
                    }
                });

                container.appendChild(display);
                container.appendChild(dropdown);
                select.parentNode.insertBefore(container, select.nextSibling);
            });
        }

        // Global click listener to close custom dropdowns if clicking outside
        document.addEventListener('click', () => {
            document.querySelectorAll('.glass-select-dropdown.show').forEach(d => {
                d.classList.remove('show');
                d.previousElementSibling.classList.remove('active');
            });
        });

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

        function togglePerformanceMode(isFast) {
            const toggle = document.getElementById('perf-mode-toggle');
            if (toggle) toggle.checked = isFast;
            if (isFast) {
                document.body.classList.add('fast-mode');
                localStorage.setItem('fast_mode', 'true');
            } else {
                document.body.classList.remove('fast-mode');
                localStorage.setItem('fast_mode', 'false');
            }
        }

        // Initialize Performance Mode on Load
        setTimeout(() => {
            const savedFastMode = localStorage.getItem('fast_mode');
            if (savedFastMode === 'true') {
                togglePerformanceMode(true);
            } else if (savedFastMode === 'false') {
                togglePerformanceMode(false);
            } else {
                // First visit ever: Auto-Detect TVs and Firesticks!
                const isTV = /(tv|smarttv|bravia|chromecast|appletv|android tv|box)/i.test(navigator.userAgent);
                togglePerformanceMode(isTV); // Turns ON automatically if it's a TV
            }
        }, 100);

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
            
            // 🟢 Render initial static Glass Dropdowns (Aspect Ratio, Size, Speed)
            setTimeout(initCustomSelects, 200);
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
            if (viewId === 'network') fetchNetworkStats();
            if (viewId === 'sos') loadSosStats();
            if (viewId === 'settings') loadWorkerTokens();
            if (viewId === 'globe') setTimeout(initWorldGlobe, 300); // 🟢 Boot Globe when tab opens
        }
        
        async function fetchNetworkStats() {
            if (!currentUser) return;
            try {
                const res = await fetch(`/api/network?user_id=${currentUser}`);
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('net-active-count').innerText = `${data.active.length} ONLINE`;
                    document.getElementById('net-stat-live').innerText = data.active.length;
                    document.getElementById('net-stat-recent').innerText = data.recent.length;
                    document.getElementById('net-workers-count').innerText = `${data.worker_bots_count} worker bots handling parallel chunks`;
                    
                    const activeList = document.getElementById('network-active-list');
                    if (data.active.length === 0) {
                        activeList.innerHTML = '<div style="color: #64748b; font-size: 13px;">No active streams right now.</div>';
                    } else {
                        activeList.innerHTML = data.active.map(s => `
                            <div class="task-row" style="margin-bottom: 8px;">
                                <div style="flex:1;">
                                    <div style="display:flex; justify-content: space-between; align-items:center;">
                                        <div style="font-weight: 700; color: #fff; font-size: 13px; word-break: break-all;">${s.filename}</div>
                                        <div style="background: rgba(34, 197, 94, 0.2); color: #22c55e; padding: 2px 8px; border-radius: 6px; font-size: 10px; font-weight: 800;">ACTIVE</div>
                                    </div>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 6px; font-size: 11px; color: var(--subtext);">
                                        <div>⏱ Started: ${new Date(s.start_time * 1000).toLocaleTimeString()}</div>
                                        <div>📍 ${s.country} (${s.ip})</div>
                                        <div>🌐 ${s.device}</div>
                                        <div>👤 User: ${s.user_id}</div>
                                    </div>
                                </div>
                            </div>
                        `).join('');
                    }

                    const recentList = document.getElementById('network-recent-list');
                    if (data.recent.length === 0) {
                        recentList.innerHTML = '<div style="color: #64748b; font-size: 13px;">No recent streams.</div>';
                    } else {
                        recentList.innerHTML = data.recent.map(s => `
                            <div style="padding: 10px; border-bottom: 1px solid rgba(255,255,255,0.05);">
                                <div style="font-weight: 700; color: #cbd5e1; font-size: 12px; word-break: break-all;">${s.filename}</div>
                                <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 10px; color: #64748b;">
                                    <span>${s.device} • ${s.country}</span>
                                    <span>Ended: ${new Date(s.end_time * 1000).toLocaleTimeString()}</span>
                                </div>
                            </div>
                        `).join('');
                    }
                }
            } catch(e) {}
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
                    renderFilteredChats();
                } else {
                    warnBox.style.display = 'block';
                    document.getElementById('web-chats-warning-title').innerText = '⚠️ Telegram Dialog Fetch Error';
                    document.getElementById('web-chats-warning-text').innerText = data.message;
                    container.innerHTML = `<div style="color: var(--subtext); padding: 10px;">Please click refresh to try again. If the issue persists, your session might be expired.</div>`;
                }
            } catch(e) {
                warnBox.style.display = 'block';
                container.innerHTML = `<div style="color: var(--danger); padding: 10px;">Network Error: Could not connect to the bot server. Request timed out.</div>`;
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
                    <div class="task-row" style="margin-bottom: 8px; user-select: none; touch-action: manipulation;">
                        <div style="flex: 1; overflow: hidden;">
                            <div style="font-weight: 700; color: var(--text); font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${c.name}</div>
                            <div style="font-size: 11px; color: var(--accent); margin-top: 4px;">ID: <code>${c.id}</code></div>
                        </div>
                        <div style="display: flex; gap: 6px; flex-shrink: 0;">
                            <button class="task-kill" style="color: #38bdf8; border-color: rgba(56, 189, 248, 0.3); background: rgba(56, 189, 248, 0.1); padding: 8px 12px;" onclick="openChatDetails('${c.id}')">ℹ️ INFO</button>
                            <button class="task-kill" style="color: var(--accent); border-color: var(--card-border); background: var(--bg); padding: 8px 12px;" onclick="copyChatId('${c.id}')">📋 COPY</button>
                        </div>
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

        // 🟢 NEW: Chat Details Logic
        function closeChatDetails() { document.getElementById('chatDetailsModal').classList.remove('show'); }
        async function openChatDetails(chatId) {
            const modal = document.getElementById('chatDetailsModal');
            modal.classList.add('show');
            
            document.getElementById('cd-loading').style.display = 'block';
            document.getElementById('cd-loading').innerText = "⏳ Deep Scanning Telegram Servers...";
            document.getElementById('cd-content').style.display = 'none';
            document.getElementById('cd-desc-container').style.display = 'none';
            document.getElementById('cd-topics-container').style.display = 'none';
            document.getElementById('cd-title').innerText = "Analyzing Chat...";

            try {
                const res = await fetch(`/api/chat_details?user_id=${currentUser}&chat_id=${chatId}`);
                const textRaw = await res.text();
                
                let data;
                try {
                    data = JSON.parse(textRaw);
                } catch(e) {
                    throw new Error("Invalid Server Response: " + textRaw.substring(0, 80));
                }

                if (data.status === 'success') {
                    document.getElementById('cd-loading').style.display = 'none';
                    document.getElementById('cd-content').style.display = 'block';
                    
                    document.getElementById('cd-title').innerText = data.title || "Unknown";
                    document.getElementById('cd-id').innerText = data.id || "Unknown";
                    document.getElementById('cd-type').innerText = String(data.type || "").replace("ChatType.", "").toUpperCase();
                    document.getElementById('cd-members').innerText = (data.members && !isNaN(data.members)) ? Number(data.members).toLocaleString() : "N/A";
                    document.getElementById('cd-msgs').innerText = (data.total_messages && !isNaN(data.total_messages)) ? Number(data.total_messages).toLocaleString() : "Unknown";
                    
                    const descContainer = document.getElementById('cd-desc-container');
                    if (data.description) {
                        descContainer.innerText = data.description;
                        descContainer.style.display = 'block';
                    }

                    if (data.is_forum && data.topics && data.topics.length > 0) {
                        const topicsContainer = document.getElementById('cd-topics-container');
                        const topicsList = document.getElementById('cd-topics-list');
                        topicsContainer.style.display = 'block';
                        
                        topicsList.innerHTML = data.topics.map(t => `
                            <div style="background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.05); border-left: 3px solid var(--accent); padding: 10px 12px; border-radius: 10px; display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <div style="color: #fff; font-size: 12px; font-weight: 700;">${t.title}</div>
                                    <div style="color: var(--subtext); font-size: 10px; margin-top: 2px;">Topic ID: ${t.id}</div>
                                </div>
                                <div style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 4px 8px; border-radius: 6px; font-size: 10px; font-weight: 800;">
                                    ${t.top_msg !== "?" ? "Active" : "Idle"}
                                </div>
                            </div>
                        `).join('');
                    }
                } else {
                    document.getElementById('cd-loading').innerText = "❌ " + data.message;
                    alert("⚠️ Backend Error:\\n" + data.message);
                }
            } catch (err) {
                document.getElementById('cd-loading').innerText = "❌ Network Error or Invalid JSON.";
                alert("⚠️ Fetch Error:\\n" + err.message);
            }
        }
        async function fetchChatsList() {
            await loadWebChats();
        }

        function downloadChatsTxt() {
            if (!allLoadedChats || allLoadedChats.length === 0) {
                return alert("No chats to download! Please wait for them to load or click Refresh.");
            }
            let groups = [], channels = [], bots = [], users = [];
            
            // 🟢 FIX: Search for the category word anywhere inside the string to bypass the emojis!
            allLoadedChats.forEach(c => {
                let type = c.name.toLowerCase();
                if (type.includes('group')) groups.push(c);
                else if (type.includes('channel')) channels.push(c);
                else if (type.includes('bot')) bots.push(c);
                else if (type.includes('user')) users.push(c);
            });

            // 🟢 FIX: Added double backslashes so Python doesn't break the JS string!
            let txt = "DESTINY TG FORWARDER - CHATS & IDs EXPORT\\n";
            txt += "=========================================\\n\\n";

            const appendSection = (title, items) => {
                if (items.length === 0) return;
                txt += `--- ${title} (${items.length}) ---\\n`;
                items.forEach(i => txt += `${i.name.replace(/\\[.*?\\]\\s*/, '')} | ID: ${i.id}\\n`);
                txt += "\\n";
            };

            appendSection("GROUPS & SUPERGROUPS", groups);
            appendSection("CHANNELS", channels);
            appendSection("USERS", users);
            appendSection("BOTS", bots);

            const blob = new Blob([txt], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `tg_chats_${currentUser}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        async function loadWorkerTokens() {
            if (!currentUser) return;
            try {
                const res = await fetch(`/api/settings/tokens?user_id=${currentUser}`);
                const data = await res.json();
                if (data.status === 'success' && data.tokens) {
                    const el = document.getElementById('worker-tokens-input');
                    if (el) el.value = data.tokens.join('\\n');
                }
            } catch (_) {}
        }

        async function saveWorkerTokens() {
            const raw = document.getElementById('worker-tokens-input').value;
            const tokens = raw.split(/[\\n,]+/).map(t => t.trim()).filter(t => t.includes(':'));
            try {
                const res = await fetch('/api/settings/tokens', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: currentUser, tokens})
                });
                const data = await res.json();
                alert(data.message || "Tokens updated.");
            } catch (e) {
                alert("Failed to save tokens.");
            }
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
                    
                    // 🟢 FIX: Stop spamming get_dialogs on every heartbeat!
                    // ONLY fetch the chat list if the user is actually looking at the Chats tab!
                    if (!chatsLoaded && document.getElementById('view-chats').classList.contains('active')) {
                        fetchChatsList();
                        chatsLoaded = true;
                    }
                } else {
                    tgStatusEl.innerHTML = '<span style="color: #ef4444;">❌ Not Connected — Login First!</span>';
                    document.getElementById('tg-login-step1').style.display = 'block';
                    document.getElementById('tg-logout-btn').style.display = 'none';
                    chatsLoaded = false;
                }

                if (document.getElementById('view-logs').classList.contains('active')) fetchLogs();
                if (document.getElementById('view-network').classList.contains('active')) fetchNetworkStats();
                
                const dlList = document.getElementById('downloads-list');
                let newDlHtml = data.tasks.length ? '' : '<div style="color: #64748b;">No active downloads.</div>';
                data.tasks.forEach(t => {
                    newDlHtml += `
                        <div class="task-row">
                            <div>
                                <div style="font-weight: 700; color: #fff; font-size: 14px; word-break: break-all;">${t.name}</div>
                                <div style="font-size: 11px; color: var(--accent); margin-top: 4px;">Destination: ${t.dest} | Progress: ${t.current}/${t.total} (${t.percent}%)</div>
                            </div>
                            <button class="task-kill" onclick="cancelTask('${t.id}')">CANCEL</button>
                        </div>
                    `;
                });
                
                // 🟢 FIX: Only update DOM if HTML actually changed (Prevents TV lag spikes)
                if (dlList.innerHTML !== newDlHtml) {
                    dlList.innerHTML = newDlHtml;
                }

                const wList = document.getElementById('watchers-list');
                let newWListHtml = data.watchers.length ? '' : '<div style="color: #64748b;">No active watchers.</div>';
                data.watchers.forEach(w => {
                    newWListHtml += `
                        <div class="task-row">
                            <div>
                                <div style="font-weight: 700; color: #fff; font-size: 14px;">📡 ${w.source}</div>
                                <div style="font-size: 11px; color: #64748b; margin-top: 4px;">To: ${w.dest} | Detected: ${w.detected} | Success: ${w.success}</div>
                            </div>
                            <button class="task-kill" onclick="cancelWatcher('${w.id}')">REMOVE</button>
                        </div>
                    `;
                });
                
                if (wList.innerHTML !== newWListHtml) {
                    wList.innerHTML = newWListHtml;
                }
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
                const res = await fetch(`/api/logs?user_id=${currentUser}`);
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
        
        function downloadLogsAuth(e) {
            e.preventDefault();
            window.location.href = `/api/logs/download?user_id=${currentUser}`;
        }

        function copyLogs() {
            const term = document.getElementById('log-terminal');
            if (!term || !term.innerText) return alert("No logs to copy!");
            navigator.clipboard.writeText(term.innerText)
                .then(() => alert("Logs copied to clipboard!"))
                .catch(() => alert("Failed to copy logs. Your browser might block clipboard access."));
        }

        // --- CHAT & TOPIC SELECTOR MODAL LOGIC ---
        function openChatSelector() {
            document.getElementById('chatSelectorModal').classList.add('show');
            if(allLoadedChats.length === 0) loadWebChats();
            renderSelectorChats(allLoadedChats);
        }
        function closeChatSelector() { document.getElementById('chatSelectorModal').classList.remove('show'); }
        function closeTopicSelector() { document.getElementById('topicSelectorModal').classList.remove('show'); }

        function renderSelectorChats(chats) {
            const list = document.getElementById('chat-selector-list');
            list.innerHTML = chats.map(c => `
                <div style="padding: 12px; background: color-mix(in srgb, var(--card) 50%, transparent); border: 1px solid var(--card-border); border-radius: 12px; cursor: pointer; transition: 0.2s;" onclick="handleChatSelect('${c.id}', ${c.is_forum})">
                    <div style="font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 4px;">${c.name}</div>
                    <div style="font-size: 11px; color: var(--accent);">${c.id}</div>
                </div>
            `).join('');
        }

        function filterSelectorChats() {
            const q = document.getElementById('chat-search-input').value.toLowerCase();
            renderSelectorChats(allLoadedChats.filter(c => c.name.toLowerCase().includes(q) || c.id.includes(q)));
        }

        async function handleChatSelect(chatId, isForum) {
            closeChatSelector();
            if (isForum) {
                document.getElementById('topicSelectorModal').classList.add('show');
                const list = document.getElementById('topic-selector-list');
                list.innerHTML = '<div style="color: var(--accent); font-weight: bold;">⏳ Fetching topics from Telegram...</div>';
                try {
                    const res = await fetch(`/api/topics?user_id=${currentUser}&chat_id=${chatId}`);
                    const data = await res.json();
                    
                    // Added safe-check (data.topics && ...) to prevent JS crashes
                    if (data.status === 'success' && data.topics && data.topics.length > 0) {
                        let html = `<div style="padding: 12px; background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; cursor: pointer; margin-bottom: 4px;" onclick="confirmDestination('${chatId}')"><div style="font-size: 13px; font-weight: 700; color: #fff;">General (Root Group)</div></div>`;
                        html += data.topics.map(t => `
                            <div style="padding: 12px; background: var(--bg); border: 1px solid var(--card-border); border-radius: 12px; cursor: pointer;" onclick="confirmDestination('${chatId}/${t.id}')">
                                <div style="font-size: 13px; font-weight: 700; color: var(--text);">${t.title}</div>
                                <div style="font-size: 11px; color: var(--subtext); margin-top: 2px;">Topic ID: ${t.id}</div>
                            </div>
                        `).join('');
                        list.innerHTML = html;
                    } else {
                        // Fallback automatically to root chat ID if topics are empty or error occurs
                        confirmDestination(chatId);
                        closeTopicSelector();
                    }
                } catch(e) {
                    // Prevent indefinite hang if network drops
                    confirmDestination(chatId);
                    closeTopicSelector();
                }
            } else {
                confirmDestination(chatId);
            }
        }

        function confirmDestination(destStr) {
            document.getElementById('t-dest').value = destStr;
            closeTopicSelector();
        }

        // --- MEDIAINFO LOGIC ---
        async function runWebMediaInfo() {
            const link = document.getElementById('mi-link').value;
            if(!link) return alert("Please enter a link!");
            const btn = document.getElementById('mi-btn');
            btn.innerText = "⏳ Downloading & Analyzing (Please wait)...";
            btn.disabled = true;
            document.getElementById('mi-results-card').style.display = 'none';
            
            try {
                const res = await fetch('/api/mediainfo', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: currentUser, link: link})
                });
                const data = await res.json();
                if(data.status === 'success') {
                    document.getElementById('mi-results-card').style.display = 'block';
                    document.getElementById('mi-results-content').innerHTML = data.html;
                } else {
                    alert("Error: " + data.message);
                }
            } catch(e) {
                alert("Network error.");
            } finally {
                btn.innerText = "Analyze File";
                btn.disabled = false;
            }
        }

        // --- SPECTROGRAM LOGIC ---
        async function runWebSpectrogram() {
            const link = document.getElementById('spec-link').value;
            if(!link) return alert("Please enter a link!");
            const btn = document.getElementById('spec-btn');
            btn.innerText = "⏳ Running DSP & Rendering (Please wait)...";
            btn.disabled = true;
            document.getElementById('spec-results-card').style.display = 'none';
            
            try {
                const res = await fetch('/api/spectrogram', {
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: currentUser, link: link})
                });
                const data = await res.json();
                if(data.status === 'success') {
                    document.getElementById('spec-results-card').style.display = 'block';
                    document.getElementById('spec-image').src = "data:image/png;base64," + data.image;
                    document.getElementById('spec-html').innerHTML = data.html;
                } else {
                    alert("Error: " + data.message);
                }
            } catch(e) {
                alert("Network error.");
            } finally {
                btn.innerText = "Generate Spectrogram";
                btn.disabled = false;
            }
        }

        // ==========================================================================
        // --- Playback, OSD, tracks, subtitles & aspect-ratio engine ---
        let playerAspectMode = 'contain';
        let playerViewportRatio = 16 / 9;
        let playerRequiresTranscode = false;
        let playerDirectCompatible = true;
        let playerTimelineOffset = 0;
        let playerStreamGeneration = 0;
        let playerTotalDuration = 0;
        let activeSubtitleIndex = 'off';
        let isTranscodeSeeking = false;
        let subtitleCues = [];
        let subtitleAbortController = null;
        let hudTimeout;
        let subtitleSyncOffset = 0; // 🟢 NEW: Global Sync Offset Tracker
        
        function updateSubtitleSync(val) {
            subtitleSyncOffset = parseFloat(val);
            document.getElementById('subtitle-sync-val').innerText = (subtitleSyncOffset > 0 ? "+" : "") + subtitleSyncOffset.toFixed(2) + "s";
            renderCurrentSubtitle(); // Instantly update text on screen
        }

        // ======================================================================
        // WEBGL 3D ANAGLYPH SHADER PIPELINE
        // ======================================================================
        let matrix3DIn = 'none';
        let matrix3DOut = 'rc';
        let isRightFirst = false;
        let activeMediaLink = "";
        let playerSourceKind = 'tg'; // 'tg' or 'direct'
        let playerNativeUrl = '';
        let playerFallbackAttempted = false;
        let gl, glProgram, glTexture;

        const vsSource = `
            attribute vec2 a_position;
            varying vec2 v_uv;
            void main() {
                v_uv = (a_position + 1.0) * 0.5;
                v_uv.y = 1.0 - v_uv.y;
                gl_Position = vec4(a_position, 0.0, 1.0);
            }
        `;

        const fsSource = `
            precision mediump float;
            uniform sampler2D u_image;
            uniform int u_in_mode;
            uniform int u_out_mode;
            uniform bool u_swap;
            varying vec2 v_uv;

            void main() {
                vec2 uvL = v_uv;
                vec2 uvR = v_uv;

                if (u_in_mode == 1) {
                    uvL = vec2(v_uv.x * 0.5, v_uv.y);
                    uvR = vec2(0.5 + v_uv.x * 0.5, v_uv.y);
                } else if (u_in_mode == 2) {
                    uvL = vec2(v_uv.x, v_uv.y * 0.5);
                    uvR = vec2(v_uv.x, 0.5 + v_uv.y * 0.5);
                } else if (u_in_mode == 3) {
                    float col = mod(gl_FragCoord.x, 2.0);
                    if (col < 1.0) { uvR = uvL; } else { uvL = uvR; }
                } else if (u_in_mode == 4) {
                    float row = mod(gl_FragCoord.y, 2.0);
                    if (row < 1.0) { uvR = uvL; } else { uvL = uvR; }
                }

                if (u_swap) {
                    vec2 tmp = uvL; uvL = uvR; uvR = tmp;
                }

                vec4 cL = texture2D(u_image, uvL);
                vec4 cR = texture2D(u_image, uvR);

                if (u_in_mode == 0 || u_out_mode == 4) {
                    gl_FragColor = cL;
                } else if (u_out_mode == 0) {
                    gl_FragColor = vec4(cL.r, cR.g, cR.b, 1.0);
                } else if (u_out_mode == 1) {
                    gl_FragColor = vec4(cR.r, cL.g, cR.b, 1.0);
                } else if (u_out_mode == 2) {
                    gl_FragColor = vec4(cR.r, cR.g, cL.b, 1.0);
                } else if (u_out_mode == 3) {
                    if (v_uv.x < 0.5) gl_FragColor = texture2D(u_image, vec2(v_uv.x * 2.0, v_uv.y));
                    else gl_FragColor = texture2D(u_image, vec2((v_uv.x - 0.5) * 2.0, v_uv.y));
                }
            }
        `;

        function initWebGL() {
            const canvas = document.getElementById('webgl-canvas');
            if (!canvas) return;
            gl = canvas.getContext('webgl', { alpha: false, antialias: true, preserveDrawingBuffer: false });
            if (!gl) {
                console.warn('WebGL is unavailable; video surface cannot be rendered.');
                return;
            }

            function compileShader(type, src) {
                const s = gl.createShader(type);
                gl.shaderSource(s, src);
                gl.compileShader(s);
                if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
                    console.error('WebGL shader compile error:', gl.getShaderInfoLog(s));
                    gl.deleteShader(s);
                    return null;
                }
                return s;
            }

            const vs = compileShader(gl.VERTEX_SHADER, vsSource);
            const fs = compileShader(gl.FRAGMENT_SHADER, fsSource);
            if (!vs || !fs) return;

            glProgram = gl.createProgram();
            gl.attachShader(glProgram, vs);
            gl.attachShader(glProgram, fs);
            gl.linkProgram(glProgram);
            if (!gl.getProgramParameter(glProgram, gl.LINK_STATUS)) {
                console.error('WebGL program link error:', gl.getProgramInfoLog(glProgram));
                return;
            }
            gl.useProgram(glProgram);

            const buf = gl.createBuffer();
            gl.bindBuffer(gl.ARRAY_BUFFER, buf);
            gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
                -1, -1,  1, -1, -1,  1,
                -1,  1,  1, -1,  1,  1
            ]), gl.STATIC_DRAW);

            const pos = gl.getAttribLocation(glProgram, 'a_position');
            gl.enableVertexAttribArray(pos);
            gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);

            glTexture = gl.createTexture();
            gl.bindTexture(gl.TEXTURE_2D, glTexture);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
            gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);

            requestAnimationFrame(renderWebGLFrame);
        }

        function getEffectiveVideoSize() {
            const video = document.getElementById('hidden-video');
            let w = video?.videoWidth || 16;
            let h = video?.videoHeight || 9;
            if (matrix3DIn === 'lr' || matrix3DIn === 'ci') w = Math.round(w / 2);
            if (matrix3DIn === 'tb' || matrix3DIn === 'ri') h = Math.round(h / 2);
            return { w, h };
        }

        function resizePlayerSurface() {
            const vp = document.getElementById('cinema-viewport');
            const canvas = document.getElementById('webgl-canvas');
            if (!vp || !canvas) return;

            const vw = vp.clientWidth;
            const vh = vp.clientHeight;
            if (vw <= 0 || vh <= 0) return;

            const { w: sw, h: sh } = getEffectiveVideoSize();

            canvas.style.left = '50%';
            canvas.style.top = '50%';
            canvas.style.transform = 'translate(-50%, -50%)';

            if (playerAspectMode === 'stretch') {
                canvas.style.width = `${vw}px`;
                canvas.style.height = `${vh}px`;
                return;
            }

            const scale = playerAspectMode === 'cover'
                ? Math.max(vw / sw, vh / sh)
                : Math.min(vw / sw, vh / sh);
                
            const drawW = Math.max(1, Math.round(sw * scale));
            const drawH = Math.max(1, Math.round(sh * scale));

            canvas.style.width = `${drawW}px`;
            canvas.style.height = `${drawH}px`;
        }

        function renderWebGLFrame() {
            const video = document.getElementById('hidden-video');
            const canvas = document.getElementById('webgl-canvas');
            if (gl && glProgram && glTexture && video && video.readyState >= video.HAVE_CURRENT_DATA) {
                const { w: outW, h: outH } = getEffectiveVideoSize();

                // IMPORTANT: The WebGL buffer must match the 3D-adjusted output size, not the raw input size!
                // This prevents 3D SBS videos from being rendered squished.
                if (canvas.width !== outW || canvas.height !== outH) {
                    canvas.width = outW;
                    canvas.height = outH;
                    resizePlayerSurface();
                }

                gl.viewport(0, 0, canvas.width, canvas.height);
                gl.bindTexture(gl.TEXTURE_2D, glTexture);
                try {
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
                } catch (err) {
                    console.debug('WebGL video texture update failed:', err);
                }

                const inMap = { none: 0, lr: 1, tb: 2, ci: 3, ri: 4 };
                const outMap = { rc: 0, gm: 1, ba: 2, vr: 3, '2d': 4 };
                gl.uniform1i(gl.getUniformLocation(glProgram, 'u_in_mode'), inMap[matrix3DIn] ?? 0);
                gl.uniform1i(gl.getUniformLocation(glProgram, 'u_out_mode'), outMap[matrix3DOut] ?? 0);
                gl.uniform1i(gl.getUniformLocation(glProgram, 'u_swap'), isRightFirst ? 1 : 0);
                gl.drawArrays(gl.TRIANGLES, 0, 6);
            }
            requestAnimationFrame(renderWebGLFrame);
        }

        function setMatrix3DIn(val, el) {
            matrix3DIn = val;
            if (el?.parentElement) el.parentElement.querySelectorAll('.matrix-option').forEach(o => o.classList.remove('active'));
            el?.classList.add('active');
        }

        function setMatrix3DOut(val, el) {
            if (val === 'lf') isRightFirst = false;
            else if (val === 'rf') isRightFirst = true;
            else matrix3DOut = val;
            
            if (el?.parentElement) el.parentElement.querySelectorAll('.matrix-option').forEach(o => o.classList.remove('active'));
            el?.classList.add('active');
            
            renderCurrentSubtitle();
        }

        function toggleMatrixPopup() {
            const menu = document.getElementById('menu-3d');
            if (!menu) return;
            menu.classList.toggle('open');
            wakeHUD();
        }

        // ======================================================================
        // HUD / PLAYBACK CONTROLS
        // ======================================================================
        function wakeHUD() {
            const vp = document.getElementById('cinema-viewport');
            const video = document.getElementById('hidden-video');
            if (!vp) return;

            vp.classList.remove('idle-hide');
            clearTimeout(hudTimeout);

            if (video && !video.paused && !video.ended) {
                hudTimeout = setTimeout(() => {
                    // Do not hide an actively open settings/menu panel while the user is interacting with it.
                    const settingsOpen = document.getElementById('media-settings-popup')?.classList.contains('open');
                    const matrixOpen = document.getElementById('menu-3d')?.classList.contains('open');
                    if (settingsOpen || matrixOpen) return;
                    vp.classList.add('idle-hide');
                }, 5000);
            }
        }

        async function togglePlayback() {
            const video = document.getElementById('hidden-video');
            if (!video) return;
            wakeHUD();

            try {
                if (video.paused || video.ended) {
                    if (video.ended) {
                        try { video.currentTime = 0; } catch (_) {}
                    }
                    await video.play();
                } else {
                    video.pause();
                }
            } catch (err) {
                console.warn('Playback toggle failed:', err);
                wakeHUD();
            }
        }

        let tapTimerLeft = null;
        let tapTimerRight = null;
        
        function handleZoneTap(side, amount, event) {
            event.stopPropagation(); // Prevent background clicks from firing
            
            if (side === 'left') {
                if (tapTimerLeft) {
                    // It's a double tap! Clear timer and execute skip.
                    clearTimeout(tapTimerLeft);
                    tapTimerLeft = null;
                    skipPlayback(amount);
                } else {
                    // First tap: Wait 300ms. If no second tap, just wake the HUD.
                    tapTimerLeft = setTimeout(() => { 
                        tapTimerLeft = null; 
                        wakeHUD(); 
                    }, 300);
                }
            } else {
                if (tapTimerRight) {
                    clearTimeout(tapTimerRight);
                    tapTimerRight = null;
                    skipPlayback(amount);
                } else {
                    tapTimerRight = setTimeout(() => { 
                        tapTimerRight = null; 
                        wakeHUD(); 
                    }, 300);
                }
            }
        }

        function skipPlayback(sec) {
            const video = document.getElementById('hidden-video');
            if (!video) return;
            
            let current = video.currentTime || 0;
            let dur = video.duration || Infinity;
            
            if (playerRequiresTranscode && playerTotalDuration > 0) {
                current = playerTimelineOffset + current;
                dur = playerTotalDuration;
            } else if (playerTotalDuration > 0 && (!Number.isFinite(dur) || dur === 0 || dur === Infinity)) {
                dur = playerTotalDuration;
            }

            const target = Math.max(0, Math.min(dur, current + Number(sec || 0)));
            wakeHUD();

            const fill = document.getElementById('scrubber-fill');
            if (fill && dur > 0 && dur !== Infinity) {
                fill.style.width = `${(target / dur) * 100}%`;
            }

            if (playerRequiresTranscode) {
                isTranscodeSeeking = true;
                restartStreamAt(target);
                return;
            }
            try { video.currentTime = target; } catch (_) {}
            renderCurrentSubtitle(target);
        }

        // 🟢 FIX: Fully Draggable & Clickable Scrubber Logic
        let isDraggingScrubber = false;

        function getScrubberTime(e, bar) {
            const rect = bar.getBoundingClientRect();
            const clientX = e.clientX ?? (e.touches?.[0]?.clientX ?? rect.left);
            let pos = (clientX - rect.left) / rect.width;
            pos = Math.max(0, Math.min(1, pos));
            
            let dur = 0;
            if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                dur = window.totalAlbumDuration || 0;
            } else {
                const video = document.getElementById('hidden-video');
                dur = video?.duration || 0;
                if (typeof playerRequiresTranscode !== 'undefined' && playerRequiresTranscode && typeof playerTotalDuration !== 'undefined' && playerTotalDuration > 0) {
                    dur = playerTotalDuration;
                } else if (typeof playerTotalDuration !== 'undefined' && playerTotalDuration > 0 && (!Number.isFinite(dur) || dur <= 0 || dur === Infinity)) {
                    dur = playerTotalDuration;
                }
            }
            
            if (dur === 0 || dur === Infinity) return { pos: 0, target: 0, dur: 0 };
            return { pos, target: pos * dur, dur };
        }

        function seekPlayback(e) {
            // Disabled: Replaced by the smart pointer events below.
        }

        // Initialize smooth drag listeners safely
        setTimeout(() => {
            const scrubberBar = document.getElementById('cinema-scrubber');
            if (!scrubberBar) return;
            
            scrubberBar.removeAttribute('onclick'); // Remove old static click

            scrubberBar.addEventListener('pointerdown', (e) => {
                isDraggingScrubber = true;
                scrubberBar.setPointerCapture(e.pointerId);
                updateScrubberUI(e, scrubberBar);
            });

            scrubberBar.addEventListener('pointermove', (e) => {
                if (isDraggingScrubber) updateScrubberUI(e, scrubberBar);
            });

            scrubberBar.addEventListener('pointerup', (e) => {
                if (isDraggingScrubber) {
                    isDraggingScrubber = false;
                    scrubberBar.releasePointerCapture(e.pointerId);
                    commitSeek(e, scrubberBar);
                }
            });
        }, 1000);

        function updateScrubberUI(e, bar) {
            const { pos, target, dur } = getScrubberTime(e, bar);
            if (dur === 0) return;
            
            const fill = document.getElementById('scrubber-fill');
            if (fill) fill.style.width = `${pos * 100}%`;
            
            const fmt = (s) => {
                if (!Number.isFinite(s) || s < 0) return '00:00';
                const h = Math.floor(s / 3600);
                const m = Math.floor((s % 3600) / 60);
                const sec = Math.floor(s % 60);
                const hh = h > 0 ? `${String(h).padStart(2, '0')}:` : '';
                return `${hh}${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
            };
            
            const timeText = document.getElementById('hud-time');
            if (timeText) timeText.innerText = `${fmt(target)} / ${fmt(dur)}`;
            wakeHUD();
        }

        function commitSeek(e, bar) {
            const { target, dur } = getScrubberTime(e, bar);
            if (dur === 0) return;
            wakeHUD();
            
            // 🟢 ALBUM CROSS-TRACK SEEKING
            if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                let targetTrackIndex = 0;
                for (let i = 0; i < window.globalPlaylist.length; i++) {
                    const t = window.globalPlaylist[i];
                    if (target >= t.startTime && target <= t.startTime + t.duration) {
                        targetTrackIndex = i;
                        break;
                    }
                }
                
                const track = window.globalPlaylist[targetTrackIndex];
                const localTarget = target - track.startTime;
                
                if (targetTrackIndex !== window.currentPlayIndex) {
                    window.currentPlayIndex = targetTrackIndex;
                    if (window.updateAlbumText) window.updateAlbumText();
                    
                    playerTimelineOffset = localTarget;
                    isTranscodeSeeking = false;
                    
                    const nextUrl = playerDirectCompatible ? buildNativeUrl() : buildStreamUrl(localTarget);
                    setVideoSource(nextUrl, localTarget, true);
                    return;
                } else {
                    globalTargetTime = localTarget;
                    const video = document.getElementById('hidden-video');
                    if (playerRequiresTranscode) {
                        isTranscodeSeeking = true;
                        restartStreamAt(localTarget);
                    } else {
                        if (video) video.currentTime = localTarget;
                        renderCurrentSubtitle(localTarget);
                        if (!playerFallbackAttempted) armPlaybackWatchdog();
                    }
                    return;
                }
            }

            globalTargetTime = target; 
            const video = document.getElementById('hidden-video');
            if (playerRequiresTranscode) {
                isTranscodeSeeking = true;
                restartStreamAt(target);
            } else {
                if (video) video.currentTime = target;
                renderCurrentSubtitle(target);
                if (!playerFallbackAttempted) armPlaybackWatchdog(); 
            }
        }

        function toggleSettingsPopup() {
            const popup = document.getElementById('media-settings-popup');
            if (!popup) return;
            popup.classList.toggle('open');
            if (popup.classList.contains('open')) {
                document.getElementById('menu-3d')?.classList.remove('open');
            }
            wakeHUD();
        }

        function toggleFullScreen() {
            const vp = document.getElementById('cinema-viewport');
            if (!vp) return;
            
            // Detect iOS/iPadOS exclusively. 
            // Do NOT trap Android PWA (Standalone) devices here, as they support True Native Fullscreen.
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);

            // Apple completely blocks native fullscreen in PWAs. Use CSS-based faux-fullscreen for iOS only.
            if (isIOS) {
                vp.classList.toggle('ios-fullscreen');
                updateViewportBox();
                resizePlayerSurface();
                
                // Try to force landscape orientation if possible
                if (vp.classList.contains('ios-fullscreen') && screen.orientation && screen.orientation.lock) {
                    screen.orientation.lock('landscape').catch(() => {});
                } else if (screen.orientation && screen.orientation.unlock) {
                    screen.orientation.unlock();
                }
                return;
            }

            // Standard Native Fullscreen for Android, Windows, Mac
            if (!document.fullscreenElement && !document.webkitFullscreenElement) {
                if (vp.requestFullscreen) vp.requestFullscreen();
                else if (vp.webkitRequestFullscreen) vp.webkitRequestFullscreen();
            } else {
                if (document.exitFullscreen) document.exitFullscreen();
                else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
            }
        }

        let isForcedLandscape = false;

        async function toggleOrientation() {
            const vp = document.getElementById('cinema-viewport');
            const isNativeFullscreen = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
            const isIosFullscreen = vp && vp.classList.contains('ios-fullscreen');

            if (!isNativeFullscreen && !isIosFullscreen) {
                alert("Please enter Full Screen mode first (⛶) before rotating!");
                return;
            }

            isForcedLandscape = !isForcedLandscape;

            try {
                if (screen.orientation && screen.orientation.lock) {
                    await screen.orientation.lock(isForcedLandscape ? 'landscape' : 'portrait');
                } else if (screen.lockOrientation) {
                    screen.lockOrientation(isForcedLandscape ? 'landscape' : 'portrait');
                }
            } catch (err) {} // Silently ignore iframe blockages

            // Wait 250ms for native rotation. If screen is still portrait, force CSS rotation.
            setTimeout(() => {
                let actualLandscape = window.innerWidth > window.innerHeight;
                if (isForcedLandscape && !actualLandscape) {
                    vp.classList.add('rotated-landscape');
                } else {
                    vp.classList.remove('rotated-landscape');
                }
                updateViewportBox();
                resizePlayerSurface();
                wakeHUD();
            }, 250);
        }

        document.addEventListener('fullscreenchange', () => { 
            const vp = document.getElementById('cinema-viewport');
            if (!document.fullscreenElement) {
                if (vp) vp.classList.remove('rotated-landscape');
                isForcedLandscape = false;
                try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch(e){}
            }
            setTimeout(() => { updateViewportBox(); resizePlayerSurface(); }, 200);
        });
        
        document.addEventListener('webkitfullscreenchange', () => { 
            const vp = document.getElementById('cinema-viewport');
            if (!document.webkitFullscreenElement) {
                if (vp) vp.classList.remove('rotated-landscape');
                isForcedLandscape = false;
                try { if (screen.orientation && screen.orientation.unlock) screen.orientation.unlock(); } catch(e){}
            }
            setTimeout(() => { updateViewportBox(); resizePlayerSurface(); }, 200);
        });

        // ======================================================================
        // ROBUST ASPECT-RATIO / SURFACE SIZING
        // ======================================================================
        function getEffectiveVideoSize() {
            const video = document.getElementById('hidden-video');
            let w = video?.videoWidth || 16;
            let h = video?.videoHeight || 9;
            if (matrix3DIn === 'lr' || matrix3DIn === 'ci') w = Math.round(w / 2);
            if (matrix3DIn === 'tb' || matrix3DIn === 'ri') h = Math.round(h / 2);
            return { w, h };
        }

        function updateViewportBox() {
            resizePlayerSurface();
        }

        function resizePlayerSurface() {
            const vp = document.getElementById('cinema-viewport');
            const canvas = document.getElementById('webgl-canvas');
            const video = document.getElementById('hidden-video');
            if (!vp || !canvas || !video) return;

            // Skip WebGL sizing completely if it's an Audio-only file (FLAC, MP3)
            if (video.videoWidth === 0 || video.videoHeight === 0) {
                canvas.style.display = 'none';
                return;
            } else {
                canvas.style.display = 'block';
            }

            const vw = vp.clientWidth;
            const vh = vp.clientHeight;
            if (vw <= 0 || vh <= 0) return;

            let { w: sw, h: sh } = getEffectiveVideoSize();
            let drawW, drawH;

            if (playerAspectMode === 'stretch') {
                drawW = vw;
                drawH = vh;
            } else {
                // Determine the mathematical aspect ratio target
                let targetAspect = sw / sh;
                if (playerAspectMode === '16-9') targetAspect = 16 / 9;
                else if (playerAspectMode === '21-9') targetAspect = 21 / 9;
                else if (playerAspectMode === '4-3') targetAspect = 4 / 3;

                // Create a virtual box with the target aspect ratio
                let effW = 1000 * targetAspect;
                let effH = 1000;

                const scale = (playerAspectMode === 'cover') 
                    ? Math.max(vw / effW, vh / effH) 
                    : Math.min(vw / effW, vh / effH);

                drawW = Math.max(1, Math.round(effW * scale));
                drawH = Math.max(1, Math.round(effH * scale));
            }

            canvas.style.left = '50%';
            canvas.style.top = '50%';
            canvas.style.transform = 'translate(-50%, -50%)';
            canvas.style.width = `${drawW}px`;
            canvas.style.height = `${drawH}px`;
            
            // Re-sync subtitle position instantly when phone rotates or screen resizes
            if (typeof applySubtitleStyle === 'function') {
                applySubtitleStyle();
            }
        }

        function renderWebGLFrame() {
            const video = document.getElementById('hidden-video');
            const canvas = document.getElementById('webgl-canvas');
            
            // 🟢 FIX: Stop GPU loop if video is paused, ended, or buffering!
            if (gl && glProgram && glTexture && video && video.readyState >= video.HAVE_CURRENT_DATA && !video.paused && !video.ended) {
                
                // Do not crash WebGL on Audio-only files
                if (video.videoWidth === 0 || video.videoHeight === 0) {
                    requestAnimationFrame(renderWebGLFrame);
                    return;
                }

                const { w: outW, h: outH } = getEffectiveVideoSize();

                // IMPORTANT: The WebGL buffer must match the 3D-adjusted output size
                if (canvas.width !== outW || canvas.height !== outH) {
                    canvas.width = outW;
                    canvas.height = outH;
                    resizePlayerSurface();
                }

                gl.viewport(0, 0, canvas.width, canvas.height);
                gl.bindTexture(gl.TEXTURE_2D, glTexture);
                try {
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, video);
                    if (video.style.opacity !== '0.01') video.style.opacity = '0.01';
                    if (canvas.style.display === 'none') canvas.style.display = 'block';
                } catch (err) {
                    // 🟢 FIX: If direct CDN blocks CORS, fallback to showing the raw video element instantly!
                    video.style.opacity = '1';
                    canvas.style.display = 'none';
                    return;
                }

                const inMap = { none: 0, lr: 1, tb: 2, ci: 3, ri: 4 };
                const outMap = { rc: 0, gm: 1, ba: 2, vr: 3, '2d': 4 };
                gl.uniform1i(gl.getUniformLocation(glProgram, 'u_in_mode'), inMap[matrix3DIn] ?? 0);
                gl.uniform1i(gl.getUniformLocation(glProgram, 'u_out_mode'), outMap[matrix3DOut] ?? 0);
                gl.uniform1i(gl.getUniformLocation(glProgram, 'u_swap'), isRightFirst ? 1 : 0);
                gl.drawArrays(gl.TRIANGLES, 0, 6);
            }
            requestAnimationFrame(renderWebGLFrame);
        }

        function applyAspectRatio(mode) {
            const allowed = ['contain', 'cover', 'stretch', '16-9', '21-9', '4-3'];
            if (!allowed.includes(mode)) mode = 'contain';
            playerAspectMode = mode;
            resizePlayerSurface();
            localStorage.setItem('player_aspect_mode', mode);
            wakeHUD();
        }

        // ======================================================================
        // SUBTITLE ENGINE — custom WebVTT renderer with user-configurable style
        // ======================================================================
        function vttTimeToSeconds(ts) {
            const parts = String(ts).trim().replace(',', '.').split(':');
            if (parts.length === 3) return Number(parts[0]) * 3600 + Number(parts[1]) * 60 + Number(parts[2]);
            if (parts.length === 2) return Number(parts[0]) * 60 + Number(parts[1]);
            return Number(parts[0]) || 0;
        }

        function applyPlaybackSpeed() {
            const video = document.getElementById('hidden-video');
            const speed = document.getElementById('pop-speed-select')?.value || 1;
            if (video) video.playbackRate = parseFloat(speed);
        }

        function parseWebVTT(text) {
            if (!text) return [];
            const cues = [];
            const lines = String(text).replace(/\\r/g, '').split('\\n');
            let i = 0;
            
            while (i < lines.length) {
                if (lines[i].includes('-->')) {
                    const timeParts = lines[i].split('-->');
                    const start = vttTimeToSeconds(timeParts[0]);
                    
                    // 🟢 FIX: Parse end time AND extra VTT settings (like line:10%)
                    const endMatch = timeParts[1].trim().match(/^(\\S+)(.*)/);
                    const end = endMatch ? vttTimeToSeconds(endMatch[1]) : 0;
                    const settings = endMatch ? endMatch[2].trim() : '';
                    
                    let payload = [];
                    i++;
                    while (i < lines.length && lines[i].trim() !== '' && !lines[i].includes('-->')) {
                        payload.push(lines[i]);
                        i++;
                    }
                    
                    let rawText = payload.join('\\n');
                    
                    // 🟢 DETECT SDH INTENT: Top-Screen detection from ASS tags or VTT settings
                    let isTop = false;
                    if (rawText.includes('{\\an8}') || rawText.includes('{\\an7}') || rawText.includes('{\\an9}') || settings.includes('line:0') || settings.includes('line:10%')) {
                        isTop = true;
                    }
                    
                    // Strip complex ASS brackets but KEEP basic HTML formatting (colors, bold, italics)
                    let cleanText = rawText.replace(/\\{[^}]*\\}/g, '').trim();
                    
                    // Convert WebVTT color tags to HTML spans so the browser parses them correctly
                    cleanText = cleanText.replace(/<c\\.([^>]+)>([^<]+)<\\/c>/gi, '<span style="color:$1;">$2</span>');
                    
                    if (cleanText && Number.isFinite(start) && Number.isFinite(end)) {
                        cues.push({ start, end, text: cleanText, isTop: isTop });
                    }
                } else {
                    i++;
                }
            }
            return cues.sort((a, b) => a.start - b.start);
        }

        let lyricsAbortController = null;

        // 🟢 NEW: Dedicated Lyrics Fetcher & Parser
        async function fetchSmartLyrics(zipIdx = '') {
            const scroller = document.getElementById('lyrics-scroller');
            const overlay = document.getElementById('subtitle-overlay');
            if (scroller) { 
                scroller.innerHTML = ''; 
                scroller.style.display = 'none'; 
                scroller.dataset.rendered = ''; // 🟢 FIX: Force browser to rebuild DOM for new tracks
            }
            if (overlay) overlay.innerHTML = '';
            
            subtitleCues = [];
            activeSubtitleIndex = 'off';

            if (lyricsAbortController) {
                lyricsAbortController.abort();
                lyricsAbortController = null;
            }
            lyricsAbortController = new AbortController();
            
            try {
                let zipParam = (zipIdx !== '') ? `&zip_idx=${zipIdx}` : '';
                if (!zipParam && window.globalPlaylist && window.globalPlaylist.length > 0) {
                    const track = window.globalPlaylist[window.currentPlayIndex];
                    if (track) {
                        zipParam = `&zip_idx=${track.original_index}`;
                        zipIdx = track.original_index; // 🟢 Keep zipIdx synced for the unique ID
                    }
                }

                const url = `/api/subtitles?user_id=${encodeURIComponent(currentUser)}&link=${encodeURIComponent(activeMediaLink)}&sub_idx=metadata_lyrics${zipParam}`;
                const res = await fetch(url, { signal: lyricsAbortController.signal });
                if (!res.ok) return;
                
                const text = await res.text();
                if (!text || text.trim().length === 0) return;
                
                const lines = text.split('\\n');
                const lrcCues = [];
                const timeRegex = /\\[(\\d{2}):(\\d{2}\\.\\d{2,3})\\](.*)/;
                
                for (let line of lines) {
                    const match = line.match(timeRegex);
                    if (match) {
                        const min = parseInt(match[1], 10);
                        const sec = parseFloat(match[2]);
                        let textContent = match[3].replace(/<[^>]+>/g, '').replace(/\\[\\d{2}:\\d{2}\\.\\d{2,3}\\]/g, '').trim();
                        if (textContent) lrcCues.push({ start: min * 60 + sec, text: textContent, isLrc: true });
                    } else if (line.trim() !== '' && !line.startsWith('[')) {
                        let textContent = line.replace(/<[^>]+>/g, '').trim();
                        if (textContent) lrcCues.push({ start: -1, text: textContent, isLrc: true });
                    }
                }
                
                if (lrcCues.length > 0) {
                    for (let i = 0; i < lrcCues.length - 1; i++) lrcCues[i].end = lrcCues[i+1].start;
                    lrcCues[lrcCues.length - 1].end = 999999;
                    subtitleCues = lrcCues;
                    activeSubtitleIndex = `metadata_lyrics_${zipIdx}`; // 🟢 FIX: Unique ID per track (Prevents cache collision!)
                    renderCurrentSubtitle();
                }
            } catch(e) { 
                if (e.name !== 'AbortError') console.warn("Smart lyrics fetch failed:", e); 
            }
        }

        function renderCurrentSubtitle(forceTime = null) {
            const video = document.getElementById('hidden-video');
            const overlay = document.getElementById('subtitle-overlay');
            const scroller = document.getElementById('lyrics-scroller');
            
            if (!video || activeSubtitleIndex === 'off' || subtitleCues.length === 0) {
                if (overlay) overlay.innerHTML = '';
                if (scroller) scroller.style.display = 'none';
                return;
            }
            
            let t = 0;
            if (forceTime !== null) {
                t = forceTime;
            } else {
                let cur = video.currentTime || 0;
                t = playerRequiresTranscode ? (playerTimelineOffset + cur) : cur;
            }

            // 🟢 Apply the manual sync offset slider
            const adjustedTime = t - subtitleSyncOffset;

            // 🟢 STRICT SEPARATION: Use Scroller ONLY for explicitly parsed Lyrics (LRC)
            const useScroller = subtitleCues.length > 0 && subtitleCues[0].isLrc === true;

            if (useScroller) {
                if (overlay) overlay.style.display = 'none';
                if (scroller) {
                    scroller.style.display = 'block';
                    
                    if (scroller.dataset.rendered !== activeSubtitleIndex) {
                        scroller.innerHTML = subtitleCues.map((c, i) => `<div class="lrc-line" id="lrc-${i}">${c.text}</div>`).join('');
                        scroller.dataset.rendered = activeSubtitleIndex;
                    }
                    
                    let activeIdx = -1;
                    if (subtitleCues[0].start !== -1) { // Only scroll if synced
                        for (let i = 0; i < subtitleCues.length; i++) {
                            if (adjustedTime >= subtitleCues[i].start && adjustedTime < subtitleCues[i].end) {
                                activeIdx = i; break;
                            }
                        }
                        
                        if (activeIdx !== -1) {
                            const activeEl = document.getElementById(`lrc-${activeIdx}`);
                            if (activeEl && !activeEl.classList.contains('active')) {
                                document.querySelectorAll('.lrc-line.active').forEach(el => el.classList.remove('active'));
                                activeEl.classList.add('active');
                                scroller.scrollTo({
                                    top: activeEl.offsetTop - scroller.clientHeight / 2 + activeEl.clientHeight / 2,
                                    behavior: 'smooth'
                                });
                            }
                        } else if (adjustedTime < subtitleCues[0].start) {
                            document.querySelectorAll('.lrc-line.active').forEach(el => el.classList.remove('active'));
                            scroller.scrollTo({ top: 0, behavior: 'smooth' });
                        }
                    }
                }
                return;
            }

            // 🎥 Normal Video WebVTT Subtitles (or VTT on Audio)
            if (scroller) scroller.style.display = 'none';
            if (overlay) overlay.style.display = 'flex';

            const hits = subtitleCues.filter(c => adjustedTime >= c.start && adjustedTime <= c.end);
            
            if (!hits.length) {
                overlay.innerHTML = '';
                return;
            }
            
            let htmlContent = '';
            let hasTop = false;
            
            hits.forEach(c => {
                if (c.isTop) hasTop = true;
                htmlContent += `<div class="subtitle-text">${c.text}</div>`;
            });
            
            // 3D Split-Screen (VR/SBS) Subtitle Duplication
            if (matrix3DOut === 'vr') {
                overlay.style.left = '0';
                overlay.style.right = '0';
                overlay.innerHTML = `
                    <div style="display: flex; width: 100%; justify-content: space-around;">
                        <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;">${htmlContent}</div>
                        <div style="flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px;">${htmlContent}</div>
                    </div>
                `;
            } else {
                overlay.style.left = '1%'; /* 🟢 FIX: Allows the subtitle slider to stretch to 99% of screen width */
                overlay.style.right = '1%';
                overlay.innerHTML = `<div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">${htmlContent}</div>`;
            }
            
            // Flag the overlay so applySubtitleStyle knows where to put it
            overlay.dataset.isTop = hasTop ? 'true' : 'false';
            applySubtitleStyle();
        }
        
        async function applySubtitleSelection() {
            const subSelect = document.getElementById('pop-sub-select');
            const overlay = document.getElementById('subtitle-overlay');
            activeSubtitleIndex = subSelect?.value ?? 'off';
            subtitleCues = [];
            if (overlay) overlay.innerHTML = '';

            if (subtitleAbortController) {
                subtitleAbortController.abort();
                subtitleAbortController = null;
            }

            if (activeSubtitleIndex === 'off' || !activeMediaLink) {
                wakeHUD();
                return;
            }

            subtitleAbortController = new AbortController();
            try {
                let zipParam = '';
                if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                    const track = window.globalPlaylist[window.currentPlayIndex];
                    if (track) zipParam = `&zip_idx=${track.original_index}`;
                }
                
                const url = `/api/subtitles?user_id=${encodeURIComponent(currentUser)}&link=${encodeURIComponent(activeMediaLink)}&sub_idx=${encodeURIComponent(activeSubtitleIndex)}${zipParam}`;
                const response = await fetch(url, { signal: subtitleAbortController.signal, cache: 'force-cache' });
                if (!response.ok) throw new Error(`Subtitle server returned ${response.status}`);

                // The server caches extracted WebVTT.  Read it progressively so the
                // first cues can appear before the entire file has arrived.
                const reader = response.body?.getReader();
                if (!reader) {
                    subtitleCues = parseWebVTT(await response.text());
                    renderCurrentSubtitle();
                    return;
                }

                const decoder = new TextDecoder('utf-8');
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });

                    const blocks = buffer.split(/\\n\\s*\\n/);
                    buffer = blocks.pop() || '';
                    for (const block of blocks) {
                        const cues = parseWebVTT(block + '\\n\\n');
                        if (cues.length) subtitleCues.push(...cues);
                    }
                    subtitleCues.sort((a, b) => a.start - b.start);
                    renderCurrentSubtitle();
                }

                buffer += decoder.decode();
                if (buffer.trim()) {
                    const cues = parseWebVTT(buffer + '\\n\\n');
                    if (cues.length) subtitleCues.push(...cues);
                }
                subtitleCues.sort((a, b) => a.start - b.start);
                renderCurrentSubtitle();
            } catch (err) {
                if (err?.name !== 'AbortError') {
                    console.warn('Subtitle load failed:', err);
                    subtitleCues = [];
                }
            } finally {
                wakeHUD();
            }
        }

        function hexToRgba(hex, alpha) {
            const m = String(hex || '').replace('#', '');
            const n = parseInt(m.length === 3 ? m.split('').map(c => c + c).join('') : m, 16);
            if (!Number.isFinite(n)) return `rgba(0,0,0,${alpha})`;
            return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
        }

        function applySubtitleStyle() {
            const size = Number(document.getElementById('subtitle-size-select')?.value || 20); // 🟢 FIX: Fallback to 20px
            const fg = document.getElementById('subtitle-color-input')?.value || '#ffffff';
            const bg = document.getElementById('subtitle-bg-input')?.value || '#000000';
            const alpha = Math.max(0, Math.min(100, Number(document.getElementById('subtitle-bg-alpha')?.value || 70))) / 100;
            
            const font = document.getElementById('subtitle-font-select')?.value || 'sans-serif';
            const weight = document.getElementById('subtitle-weight-select')?.value || '600';
            
            const pos = document.getElementById('subtitle-pos-slider')?.value || 88;
            const stretch = document.getElementById('subtitle-width-slider')?.value || 95; // 🟢 FIX: Fallback to 95% width
            
            const overlay = document.getElementById('subtitle-overlay');
            const canvas = document.getElementById('webgl-canvas');
            
            if (overlay) {
                if (canvas && canvas.style.display !== 'none') {
                    // 🟢 FIX 2a: Lock subtitles dynamically to the mathematical BOTTOM edge of the video, NOT the viewport top!
                    const viewportHeight = overlay.parentElement.clientHeight;
                    const canvasHeight = parseFloat(canvas.style.height) || viewportHeight;
                    const topEdge = (viewportHeight - canvasHeight) / 2;
                    const bottomEdge = (viewportHeight - canvasHeight) / 2;
                    
                    if (overlay.dataset.isTop === 'true') {
                        overlay.style.top = `${Math.max(0, topEdge + (canvasHeight * 0.10))}px`;
                        overlay.style.bottom = 'auto';
                    } else {
                        overlay.style.top = 'auto';
                        overlay.style.bottom = `${Math.max(0, bottomEdge + (canvasHeight * ((100 - pos) / 100)))}px`; 
                    }
                } else {
                    if (overlay.dataset.isTop === 'true') {
                        overlay.style.top = '10%';
                        overlay.style.bottom = 'auto';
                    } else {
                        overlay.style.top = 'auto';
                        overlay.style.bottom = `${100 - pos}%`; 
                    }
                }
                overlay.style.alignItems = 'center'; 
            }

            // 🟢 FIX 2b: Dynamically shrink subtitle font size on narrow mobile portrait screens
            let responsiveSize = size;
            if (window.innerWidth < 600) {
                responsiveSize = Math.max(12, size * 0.65); // Scale down 35% on mobile phones
            }

            document.querySelectorAll('#subtitle-overlay .subtitle-text').forEach(text => {
                text.style.fontSize = `${responsiveSize}px`;
                text.style.color = fg;
                text.style.background = hexToRgba(bg, alpha);
                text.style.fontFamily = font;
                text.style.fontWeight = weight;
                text.style.maxWidth = `${stretch}%`;
            });
        }

        // ======================================================================
        // VIDEO FILTERS & EXTERNAL MEDIA ENGINE
        // ======================================================================
        function applyVideoFilters() {
            const b = document.getElementById('filter-bright').value;
            const c = document.getElementById('filter-contrast').value;
            const s = document.getElementById('filter-sat').value;
            const h = document.getElementById('filter-hue').value;
            const sep = document.getElementById('filter-sepia')?.value || 0;
            const blr = document.getElementById('filter-blur')?.value || 0;
            
            document.getElementById('val-bright').innerText = b;
            document.getElementById('val-contrast').innerText = c;
            document.getElementById('val-sat').innerText = s;
            document.getElementById('val-hue').innerText = h;
            if(document.getElementById('val-sepia')) document.getElementById('val-sepia').innerText = sep;
            if(document.getElementById('val-blur')) document.getElementById('val-blur').innerText = blr;
            
            const filterStr = `brightness(${b}%) contrast(${c}%) saturate(${s}%) hue-rotate(${h}deg) sepia(${sep}%) blur(${blr}px)`;
            
            const canvas = document.getElementById('webgl-canvas');
            const video = document.getElementById('hidden-video');
            if(canvas) canvas.style.filter = filterStr;
            if(video) video.style.filter = filterStr;
        }

        function setFilterPreset(preset) {
            const settings = {
                'none': {b: 100, c: 100, s: 100, h: 0, sep: 0, blr: 0},
                'vivid': {b: 105, c: 115, s: 130, h: 0, sep: 0, blr: 0},
                'cinematic': {b: 95, c: 120, s: 85, h: 0, sep: 0, blr: 0},
                'soft': {b: 110, c: 90, s: 110, h: -5, sep: 0, blr: 0.5},
                'high_contrast': {b: 100, c: 140, s: 110, h: 0, sep: 0, blr: 0},
                'grayscale': {b: 100, c: 110, s: 0, h: 0, sep: 0, blr: 0},
                'cyberpunk': {b: 90, c: 130, s: 150, h: 30, sep: 0, blr: 0},
                'vintage': {b: 110, c: 85, s: 70, h: 25, sep: 40, blr: 0.5},
                'warm': {b: 105, c: 105, s: 115, h: 10, sep: 10, blr: 0},
                'cool': {b: 95, c: 105, s: 110, h: -15, sep: 0, blr: 0}
            };
            const p = settings[preset] || settings['none'];
            document.getElementById('filter-bright').value = p.b;
            document.getElementById('filter-contrast').value = p.c;
            document.getElementById('filter-sat').value = p.s;
            document.getElementById('filter-hue').value = p.h;
            if(document.getElementById('filter-sepia')) document.getElementById('filter-sepia').value = p.sep;
            if(document.getElementById('filter-blur')) document.getElementById('filter-blur').value = p.blr;
            applyVideoFilters();
        }

        // Setup the audio player syncing
        function syncExternalAudio(urlOrBlob) {
            const extAudio = document.getElementById('ext-audio-player');
            const video = document.getElementById('hidden-video');
            extAudio.src = urlOrBlob;
            extAudio.load();
            video.muted = true; // Mute original video track
            
            extAudio.currentTime = video.currentTime;
            if(!video.paused) extAudio.play();
        }

        // --- Audio Loaders ---
        function loadExternalAudioUrl() {
            const url = document.getElementById('ext-audio-url').value.trim();
            if(!url) return alert("Please enter an external audio URL.");
            syncExternalAudio(url);
            alert("External Audio URL Loaded & Synced!");
        }

        function loadExternalAudioFile(event) {
            const file = event.target.files[0];
            if(!file) return;
            const blobUrl = URL.createObjectURL(file); // Create local memory URL
            syncExternalAudio(blobUrl);
            alert(`Local Audio File '${file.name}' Loaded & Synced!`);
        }

        // Setup the subtitle syncing
        function syncExternalSubtitles(text) {
            subtitleCues = parseWebVTT(text);
            activeSubtitleIndex = 'external';
            const subSelect = document.getElementById('pop-sub-select');
            if(subSelect) subSelect.value = 'off';
            renderCurrentSubtitle();
        }

        // --- Subtitle Loaders ---
        async function loadExternalSubtitlesUrl() {
            const url = document.getElementById('ext-sub-url').value.trim();
            if(!url) return alert("Please enter a .vtt subtitle URL.");
            try {
                const res = await fetch(url);
                if(!res.ok) throw new Error("HTTP " + res.status);
                const text = await res.text();
                syncExternalSubtitles(text);
                alert("External Subtitles URL Loaded!");
            } catch (err) {
                alert("Failed to load subtitles. (Check CORS or URL): " + err.message);
            }
        }

        function loadExternalSubtitlesFile(event) {
            const file = event.target.files[0];
            if(!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                syncExternalSubtitles(e.target.result);
                alert(`Local Subtitle File '${file.name}' Loaded!`);
            };
            reader.readAsText(file);
        }

        // ======================================================================
        // STREAM SELECTION — preserves playback position across changes
        // ======================================================================
        
        async function setVideoSource(streamUrl, preserveTime = 0, shouldPlay = true) {
            const video = document.getElementById('hidden-video');
            if (!video) return;
            const generation = ++playerStreamGeneration;

            video.pause();
            video.src = streamUrl;
            video.load();
            wakeHUD();

            const onMetadata = async () => {
                if (generation !== playerStreamGeneration) return;
                video.removeEventListener('loadedmetadata', onMetadata);
                isTranscodeSeeking = false; 
                updateViewportBox();
                resizePlayerSurface();
                
                // 🟢 FIX: Forcefully apply the target timestamp across both transcode and direct modes
                try {
                    const targetSeek = Number(preserveTime) || 0;
                    if (targetSeek > 0) {
                        video.currentTime = targetSeek;
                    }
                } catch (e) {
                    console.warn("Seek adjustment failed:", e);
                }

                if (shouldPlay) {
                    try { await video.play(); }
                    catch (err) { console.warn('Autoplay after track switch failed:', err); }
                }
                renderCurrentSubtitle();
            };
            video.addEventListener('loadedmetadata', onMetadata, { once: true });
        }

        function buildStreamUrl(startTime = null) {
            const quality = document.getElementById('pop-quality-select')?.value || 'Original';
            const audioSelect = document.getElementById('pop-audio-select');
            const audioIdx = audioSelect?.value || '';
            const option = audioSelect?.selectedOptions?.[0];
            const audioCodec = option?.dataset?.codec || '';
            const params = new URLSearchParams({
                user_id: String(currentUser || ''),
                link: activeMediaLink,
                quality,
                transcode: playerRequiresTranscode ? '1' : '0'
            });
            if (window.forceX264Flag) params.set('force_x264', '1'); 
            if (audioIdx !== '') params.set('audio_idx', audioIdx);
            if (audioCodec) params.set('audio_codec', audioCodec);
            if (Number.isFinite(startTime) && startTime > 0) params.set('start', String(startTime));
            
            // 🟢 INJECT TRACK INDEX FOR ZIP PLAYLISTS
            if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                const track = window.globalPlaylist[window.currentPlayIndex];
                if (track) params.set('zip_idx', String(track.original_index));
            }
            return `/api/stream?${params.toString()}`;
        }

        function buildNativeUrl() {
            // 🟢 FAST NATIVE DIRECT LINK SEEKING BYPASS
            if (playerSourceKind === 'direct' && window.currentProbeData && window.currentProbeData.resolved_url) {
                // We must proxy ZIPs to extract files, but normal direct links can stream straight from the CDN!
                if (!window.globalPlaylist || window.globalPlaylist.length === 0) {
                    return window.currentProbeData.resolved_url;
                }
            }
            
            let base = playerSourceKind === 'tg' 
                ? `/api/tg_stream?user_id=${encodeURIComponent(currentUser)}&link=${encodeURIComponent(activeMediaLink)}`
                : `/api/direct_stream?user_id=${encodeURIComponent(currentUser)}&url=${encodeURIComponent(activeMediaLink)}`;
                
            if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                const track = window.globalPlaylist[window.currentPlayIndex];
                if (track) base += `&zip_idx=${track.original_index}`;
            }
            return base;
        }

        function openExternalPlayer(appType) {
            if (!activeMediaLink) return alert("Please load a stream first!");
            
            let streamUrl = "";
            // 🟢 CRITICAL FIX: External players get raw CDN link for instant seeking!
            if (playerSourceKind === 'direct' && window.currentProbeData && window.currentProbeData.resolved_url) {
                streamUrl = window.currentProbeData.resolved_url;
            } else {
                streamUrl = window.location.origin + buildNativeUrl();
            }
            
            let title = document.getElementById('cinema-title')?.innerText || "Media Stream";
            let safeTitle = encodeURIComponent(title.replace(/[^a-zA-Z0-9.\-_ ()]/g, '_'));
            
            if (streamUrl.includes(window.location.origin) && !streamUrl.includes('&/')) {
                streamUrl += `&/${safeTitle}`;
            }

            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
            const isAndroid = /Android/.test(navigator.userAgent);

            if (appType === 'vlc') {
                if (isAndroid) window.location.href = `intent:${streamUrl}#Intent;package=org.videolan.vlc;type=video/*;S.title=${encodeURIComponent(title)};end`;
                else if (isIOS) window.location.href = `vlc-x-callback://x-callback-url/stream?url=${encodeURIComponent(streamUrl)}`;
                else window.location.href = `vlc://${streamUrl}`;
            } else if (appType === 'mx') {
                window.location.href = `intent:${streamUrl}#Intent;package=com.mxtech.videoplayer.ad;type=video/*;S.title=${encodeURIComponent(title)};end`;
            } else if (appType === 'mpv') {
                window.location.href = `intent:${streamUrl}#Intent;package=is.xyz.mpv;type=video/*;S.title=${encodeURIComponent(title)};end`;
            } else if (appType === 'infuse') {
                window.location.href = `infuse://x-callback-url/play?url=${encodeURIComponent(streamUrl)}`;
            } else if (appType === 'outplayer') {
                window.location.href = `outplayer://url/${streamUrl}`;
            }
        }

        async function applyTrackSelection() {
            if (!activeMediaLink) return;
            const video = document.getElementById('hidden-video');
            if (!video) return;

            const quality = document.getElementById('pop-quality-select')?.value || 'Original';
            const audioSelect = document.getElementById('pop-audio-select');
            const audioIdx = audioSelect?.value || '';
            const current = playerRequiresTranscode
                ? (playerTimelineOffset + (Number.isFinite(video.currentTime) ? video.currentTime : 0))
                : (Number.isFinite(video.currentTime) ? video.currentTime : 0);
            const wasPlaying = !video.paused && !video.ended;

            // Native/original path: do not spawn FFmpeg.
            const canStayNative = quality === 'Original' && audioIdx === '' && playerDirectCompatible;
            if (canStayNative) {
                playerRequiresTranscode = false;
                playerTimelineOffset = 0;
                isTranscodeSeeking = false;
                playerNativeUrl = buildNativeUrl();
                await setVideoSource(playerNativeUrl, current, wasPlaying || video.readyState < 2);
                wakeHUD();
                return;
            }

            // Explicit quality or alternate audio requires a server media pipeline.
            // The pipeline prefers remux/copy for the original video and compatible
            // selected audio, and encodes only when the requested output needs it.
            playerRequiresTranscode = true;
            const serverStart = current > 0 ? current : null;
            playerTimelineOffset = serverStart || 0;
            await setVideoSource(buildStreamUrl(serverStart), 0, wasPlaying || video.readyState < 2);
            wakeHUD();
        }

        function restartStreamAt(target) {
            const video = document.getElementById('hidden-video');
            if (!video || !activeMediaLink) return;
            const duration = playerTotalDuration > 0
                ? playerTotalDuration
                : (Number.isFinite(video.duration) && video.duration > 0 ? video.duration : Infinity);
            const safeTarget = Math.max(0, Math.min(duration, Number(target) || 0));
            playerTimelineOffset = safeTarget;
            isTranscodeSeeking = true;
            setVideoSource(buildStreamUrl(safeTarget), 0, true);
            renderCurrentSubtitle(safeTarget);
        }

        // ======================================================================
        // MEDIA PROBE + LOAD & HYBRID FALLBACK WATCHDOG
        // ======================================================================
        function canBrowserDirectPlay(mimeType, videoCodec, audioCodec, isAudioOnly = false) {
            const mime = String(mimeType || '').toLowerCase().split(';')[0];
            const v = String(videoCodec || '').toLowerCase();
            const a = String(audioCodec || '').toLowerCase();
            const definitelyUnsupportedAudio = new Set(['dts','truehd']);
            const browserAudio = new Set(['aac','mp3','flac','opus','vorbis','alac','pcm_s16le','pcm_s24le','pcm_s32le']);
            if (isAudioOnly) {
                if (definitelyUnsupportedAudio.has(a)) return false;
                return ['audio/mpeg','audio/mp4','audio/aac','audio/ogg','audio/webm','audio/wav','audio/flac','audio/opus'].includes(mime) || browserAudio.has(a);
            }
            if (!['video/mp4','video/webm','application/mp4'].includes(mime)) return false;
            if (definitelyUnsupportedAudio.has(a) || ['ac3','eac3'].includes(a)) return false;
            if (mime === 'video/webm') return ['vp8','vp9','av1'].includes(v || 'vp9');
            return ['h264','avc1','avc','vp9','av1','hevc','h265','hvc1'].includes(v || 'h264');
        }

        let playbackWatchdogTimer = null;
        let globalTargetTime = 0; // 🟢 NEW: Global tracker for exact playback position

        function armPlaybackWatchdog() {
            clearTimeout(playbackWatchdogTimer);
            playbackWatchdogTimer = setTimeout(async () => {
                const video = document.getElementById('hidden-video');
                if (!video || playerFallbackAttempted || playerRequiresTranscode) return;
                if (video.error || video.readyState < 2) {
                    playerFallbackAttempted = true;
                    playerRequiresTranscode = true;
                    playerTimelineOffset = globalTargetTime || 0; // 🟢 Use global tracker
                    await setVideoSource(buildStreamUrl(playerTimelineOffset), 0, true);
                }
            }, 6000); // 🟢 Increased to 6s to allow deep Telegram chunks time to load!
        }
        function disarmPlaybackWatchdog() { clearTimeout(playbackWatchdogTimer); }

        function addOption(select, value, label, dataset = null) {
            const option = document.createElement('option');
            option.value = String(value ?? '');
            option.textContent = label ?? String(value ?? '');
            if (dataset) Object.entries(dataset).forEach(([k, v]) => option.dataset[k] = String(v ?? ''));
            select.appendChild(option);
        }

        function cancelTheaterStream() {
            const video = document.getElementById('hidden-video');
            const extAudio = document.getElementById('ext-audio-player');
            const titleEl = document.getElementById('cinema-title');
            const btn = document.getElementById('theater-load-btn') || document.querySelector('button[onclick="loadTheaterMedia()"]');
            
            // 0. 🟢 SEND SIGNAL TO PYTHON BACKEND TO KILL INTERNAL PROCESSES FOR THIS USER ONLY
            try {
                fetch('/api/stream/kill', { 
                    method: 'POST', 
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_id: currentUser})
                });
            } catch(e) {}

            // 1. Force the browser to sever the HTTP socket connection immediately
            if (video) {
                video.pause();
                video.removeAttribute('src');
                video.load(); 
            }
            if (extAudio) {
                extAudio.pause();
                extAudio.removeAttribute('src');
                extAudio.load();
            }

            // 2. Clear subtitles & lyrics
            const subOverlay = document.getElementById('subtitle-overlay');
            if (subOverlay) subOverlay.innerHTML = '';
            
            const scroller = document.getElementById('lyrics-scroller');
            if (scroller) { 
                scroller.innerHTML = ''; 
                scroller.style.display = 'none'; 
                scroller.dataset.rendered = ''; 
            }
            
            if (typeof subtitleAbortController !== 'undefined' && subtitleAbortController) {
                subtitleAbortController.abort();
                subtitleAbortController = null;
            }
            if (typeof lyricsAbortController !== 'undefined' && lyricsAbortController) {
                lyricsAbortController.abort();
                lyricsAbortController = null;
            }
            
            // 3. Reset internal player state
            activeMediaLink = "";
            playerRequiresTranscode = false;
            playerTotalDuration = 0;
            globalTargetTime = 0;
            disarmPlaybackWatchdog();
            
            // 4. Reset UI visuals
            if (titleEl) titleEl.innerText = 'No Media Loaded';
            if (btn) { btn.innerText = 'Load & Play'; btn.disabled = false; }
            
            // 🟢 Clear Cover Art
            const vpNode = document.getElementById('cinema-viewport');
            if (vpNode) vpNode.style.backgroundImage = 'none';
            const coverImg = document.getElementById('album-cover-art');
            if (coverImg) coverImg.style.display = 'none';
            
            // Clear the 3D WebGL projection surface
            if (typeof gl !== 'undefined' && gl) {
                try {
                    gl.clearColor(0.0, 0.0, 0.0, 1.0);
                    gl.clear(gl.COLOR_BUFFER_BIT);
                } catch(e) {}
            }
            
            // Reset Dropdowns to default states
            const qSelect = document.getElementById('pop-quality-select');
            if(qSelect) qSelect.innerHTML = '<option value="Original">Original</option>';
            const aSelect = document.getElementById('pop-audio-select');
            if(aSelect) aSelect.innerHTML = '<option value="">Default Audio</option>';
            const sSelect = document.getElementById('pop-sub-select');
            if(sSelect) sSelect.innerHTML = '<option value="off">Off</option>';
            
            setTimeout(initCustomSelects, 50);
        }

        async function loadTheaterMedia() {
            window.forceX264Flag = false; 
            window.errorRetryCount = 0;   
            const input = document.getElementById('theater-stream-url');
            const link = input?.value.trim() || '';
            if (!link) return alert('Provide a valid Telegram or HTTP media link!');

            activeMediaLink = link;
            playerSourceKind = /(?:^|\/)t\.me\//i.test(link) || /telegram\.me\//i.test(link) ? 'tg' : 'direct';
            playerFallbackAttempted = false;
            const vp = document.getElementById('cinema-viewport');
            const titleEl = document.getElementById('cinema-title');
            const btn = document.querySelector('button[onclick="loadTheaterMedia()"]');
            const qSelect = document.getElementById('pop-quality-select');
            const aSelect = document.getElementById('pop-audio-select');
            const sSelect = document.getElementById('pop-sub-select');

            if (titleEl) titleEl.innerText = '⏳ Inspecting media...';
            if (vp) vp.classList.remove('idle-hide');
            if (btn) { btn.innerText = '⏳ Routing...'; btn.disabled = true; }

            qSelect.innerHTML = ''; addOption(qSelect, 'Original', 'Original');
            aSelect.innerHTML = ''; addOption(aSelect, '', 'Default Audio');
            sSelect.innerHTML = ''; addOption(sSelect, 'off', 'Off');

            try {
                // 🟢 FETCH PROBE & PLAYLIST SIMULTANEOUSLY
                const probePromise = fetch(`/api/media_probe?user_id=${encodeURIComponent(currentUser)}&link=${encodeURIComponent(link)}`, { cache: 'no-store' }).then(r => r.json());
                const playlistPromise = fetch(`/api/playlist?user_id=${encodeURIComponent(currentUser)}&link=${encodeURIComponent(link)}`, { cache: 'no-store' }).then(r => r.json()).catch(() => ({playlist:[]}));
                
                playerDirectCompatible = true;
                playerRequiresTranscode = false;
                globalTargetTime = 0; 
                
                const [pdata, plistData] = await Promise.all([probePromise, playlistPromise]);
                if (pdata.status !== 'success') throw new Error(pdata.message || 'Media probe failed');

                // 🟢 CRITICAL FIX: Save the probe data globally so the URL builder can bypass the proxy!
                window.currentProbeData = pdata; 

                playerDirectCompatible = Boolean(pdata.browser_compatible);
                playerTotalDuration = Number(pdata.duration) || 0;
                
                // 🟢 PLAYLIST INITIALIZATION & GLOBAL TIMELINE MATH
                window.globalPlaylist = plistData.playlist || [];
                window.currentPlayIndex = 0;
                
                if (window.globalPlaylist.length > 0 && playerTotalDuration > 0) {
                    const firstTrackSize = window.globalPlaylist[0].size || 1;
                    const bytesPerSecond = firstTrackSize / playerTotalDuration;
                    
                    let cumulativeTime = 0;
                    window.globalPlaylist.forEach((track) => {
                        let estDur = track.size / bytesPerSecond;
                        track.startTime = cumulativeTime;
                        track.duration = estDur;
                        cumulativeTime += estDur;
                    });
                    window.totalAlbumDuration = cumulativeTime;
                } else {
                    window.totalAlbumDuration = playerTotalDuration;
                }

                // 🟢 BUILD ALBUM ART & TRACK INFO GUI
                if (vp) {
                    let coverContainer = document.getElementById('album-cover-container');
                    if (!coverContainer) {
                        coverContainer = document.createElement('div');
                        coverContainer.id = 'album-cover-container';
                        coverContainer.style.position = 'absolute';
                        coverContainer.style.top = '5%';
                        coverContainer.style.left = '0';
                        coverContainer.style.width = '100%';
                        coverContainer.style.height = '60%'; 
                        coverContainer.style.transform = 'none';
                        coverContainer.style.display = 'flex';
                        coverContainer.style.flexDirection = 'column';
                        coverContainer.style.alignItems = 'center';
                        coverContainer.style.justifyContent = 'center';
                        coverContainer.style.zIndex = '1';
                        coverContainer.style.pointerEvents = 'none'; 
                        
                        const coverImg = document.createElement('img');
                        coverImg.id = 'album-cover-art';
                        coverImg.style.maxHeight = '80%'; 
                        coverImg.style.maxWidth = '80%';
                        coverImg.style.objectFit = 'contain';
                        coverImg.style.borderRadius = '20px';
                        coverImg.style.boxShadow = '0 30px 60px rgba(0,0,0,0.9)';
                        
                        const trackInfo = document.createElement('div');
                        trackInfo.id = 'album-track-info';
                        // 🟢 FIX: Cleaned up inline positioning. The responsive CSS block now handles 
                        // the exact placement of the text based on Full Screen vs Windowed Mode!
                        trackInfo.style.color = '#fff';
                        trackInfo.style.fontSize = '20px';
                        trackInfo.style.fontWeight = '800';
                        trackInfo.style.textShadow = '0 5px 15px rgba(0,0,0,0.9)';
                        
                        coverContainer.appendChild(coverImg);
                        coverContainer.appendChild(trackInfo);
                        vp.appendChild(coverContainer);
                    }
                    
                    const coverImg = document.getElementById('album-cover-art');
                    const trackInfo = document.getElementById('album-track-info');
                    
                    function updateAlbumText() {
                        let currentCoverUrl = 'https://cdn-icons-png.flaticon.com/512/2111/2111646.png';
                        let currentZipIdx = ''; 
                        let currentIsAudio = false;
                        let currentIsVideo = false;

                        if (pdata && pdata.mime_type) {
                            if (pdata.mime_type.startsWith('audio')) currentIsAudio = true;
                            if (pdata.mime_type.startsWith('video')) currentIsVideo = true;
                        }

                        if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                            const track = window.globalPlaylist[window.currentPlayIndex];
                            currentZipIdx = track.original_index;
                            
                            if (track.display_name) {
                                const ext = track.display_name.split('.').pop().toLowerCase();
                                if (['mp3', 'flac', 'm4a', 'wav', 'aac', 'ogg', 'alac', 'mka', 'opus'].includes(ext)) {
                                    currentIsAudio = true; currentIsVideo = false;
                                } else if (['mp4', 'mkv', 'webm', 'avi', 'm4v', 'ts'].includes(ext)) {
                                    currentIsAudio = false; currentIsVideo = true;
                                }
                            }

                            trackInfo.innerHTML = `<span style="color:var(--accent); font-size:12px; font-weight:900; letter-spacing:2px; text-transform:uppercase;">TRACK ${window.currentPlayIndex + 1} OF ${window.globalPlaylist.length}</span><br>${track.display_name}`;
                            if (titleEl) titleEl.innerText = `[${window.currentPlayIndex + 1}/${window.globalPlaylist.length}] ${track.display_name}`;
                            
                            const zipLink = (typeof activeMediaLink !== 'undefined' && activeMediaLink) ? activeMediaLink : link;
                            currentCoverUrl = `/api/cover?user_id=${encodeURIComponent(currentUser)}&link=${encodeURIComponent(zipLink)}&zip_idx=${track.original_index}`;
                        } else {
                            let singleName = pdata.file_name || 'Media Stream';
                            trackInfo.innerHTML = `<span style="color:var(--accent); font-size:12px; font-weight:900; letter-spacing:2px; text-transform:uppercase;">NOW PLAYING</span><br>${singleName}`;
                            if (titleEl) titleEl.innerText = singleName;
                            currentCoverUrl = `/api/cover?user_id=${encodeURIComponent(currentUser)}&link=${encodeURIComponent(link)}`;
                        }

                        // 🟢 Hide Cover Box for Videos so they aren't blocked!
                        if ((pdata.has_cover || currentIsAudio) && !currentIsVideo) {
                            coverContainer.style.display = 'flex';
                            coverContainer.style.zIndex = '50';
                            
                            if (coverImg) {
                                coverImg.style.display = 'block'; 
                                coverImg.style.minHeight = '220px';
                                coverImg.style.minWidth = '220px';
                                coverImg.style.opacity = '1'; 
                                
                                coverImg.onerror = function() {
                                    if (!this.src.includes('flaticon')) this.src = 'https://cdn-icons-png.flaticon.com/512/2111/2111646.png';
                                    vp.style.backgroundImage = 'none';
                                };
                                coverImg.onload = function() {
                                    if (!this.src.includes('flaticon')) {
                                        vp.style.backgroundImage = `linear-gradient(rgba(0,0,0,0.7), rgba(0,0,0,0.9)), url('${this.src}')`;
                                        vp.style.backgroundSize = 'cover';
                                        vp.style.backgroundPosition = 'center';
                                    } else {
                                        vp.style.backgroundImage = 'none';
                                    }
                                };
                                coverImg.src = currentCoverUrl;
                            }
                        } else {
                            if (coverContainer) coverContainer.style.display = 'none';
                            if (vp) vp.style.backgroundImage = 'none';
                        }
                        
                        // 🟢 ONLY fetch smart lyrics automatically if it's an Audio track!
                        if (currentIsAudio && typeof fetchSmartLyrics === 'function') {
                            // 🟢 FIX: Ensure we wait for the cover art DOM updates to finish,
                            // then forcefully trigger the lyrics fetch with the new zip index!
                            setTimeout(() => {
                                fetchSmartLyrics(currentZipIdx);
                            }, 50);
                        } else {
                            // Clear out old lyrics if we switch to a video track
                            const scroller = document.getElementById('lyrics-scroller');
                            if (scroller) { scroller.innerHTML = ''; scroller.style.display = 'none'; }
                        }
                    }
                    window.updateAlbumText = updateAlbumText;
                    updateAlbumText();
                }

                qSelect.innerHTML = '';
                (pdata.qualities?.length ? pdata.qualities : ['Original']).forEach(q => addOption(qSelect, q, q));

                aSelect.innerHTML = '';
                addOption(aSelect, '', 'Default Audio');
                (pdata.audio_tracks || []).forEach((a, i) => {
                    const lang = a.language ? ` · ${a.language}` : '';
                    const ch = a.channels ? ` · ${a.channels}ch` : '';
                    addOption(aSelect, a.index, `${a.label || `Track ${i + 1}`}${lang}${ch}`, { codec: a.codec_name || '' });
                });

                sSelect.innerHTML = '';
                addOption(sSelect, 'off', 'Off');
                (pdata.subtitles || []).forEach((s, i) => {
                    const lang = s.language ? ` · ${s.language}` : '';
                    addOption(sSelect, s.index, `${s.label || `Subtitle ${i + 1}`}${lang}`);
                });

                activeSubtitleIndex = 'off';
                subtitleCues = [];
                document.getElementById('subtitle-overlay').innerHTML = '';

                const savedAspect = localStorage.getItem('player_aspect_mode') || 'contain';
                const aspectSelect = document.getElementById('pop-aspect-select');
                if (aspectSelect) aspectSelect.value = savedAspect;
                applyAspectRatio(savedAspect);

                playerRequiresTranscode = !playerDirectCompatible;
                playerTimelineOffset = 0;

                const nativeUrl = buildNativeUrl();
                playerNativeUrl = nativeUrl;
                const ffmpegUrl = buildStreamUrl(0);

                if (playerDirectCompatible) {
                    disarmPlaybackWatchdog();
                    await setVideoSource(nativeUrl, 0, true);
                } else {
                    await setVideoSource(ffmpegUrl, 0, true);
                }

                if (!gl) initWebGL();
                wakeHUD();
                
                setTimeout(initCustomSelects, 50);
            } catch (err) {
                console.error('Media load failed:', err);
                if (titleEl) titleEl.innerText = `⚠️ ${err.message || 'Unable to load media'}`;
                alert(`Media load failed: ${err.message || 'Unable to load media'}`);
            } finally {
                if (btn) { btn.innerText = 'Load & Play'; btn.disabled = false; }
            }
        }

        // ======================================================================
        // EVENT WIRING
        // ======================================================================
        const vidElem = document.getElementById('hidden-video');
        const vpElement = document.getElementById('cinema-viewport');
        const centerCtrls = document.getElementById('center-controls');
        const bigPlay = document.getElementById('big-play-overlay');
        const hudPlay = document.getElementById('hud-play-btn');

        const playSvg = `<svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>`;
        const pauseSvg = `<svg width="40" height="40" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14h4v14h-4V5z"/></svg>`;
        const smallPlaySvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>`;
        const smallPauseSvg = `<svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>`;

        // 🟢 MOVED OUTSIDE THE IF-BLOCK SO HTML BUTTONS CAN FIND THEM
        function updateBufferBar() {
            const video = document.getElementById('hidden-video');
            const bufferBar = document.getElementById('scrubber-buffer');
            if (!video || !bufferBar) return;
            
            let dur = video.duration || 0;
            if (typeof playerRequiresTranscode !== 'undefined' && playerRequiresTranscode && typeof playerTotalDuration !== 'undefined' && playerTotalDuration > 0) dur = playerTotalDuration;
            else if (typeof playerTotalDuration !== 'undefined' && playerTotalDuration > 0 && (!Number.isFinite(dur) || dur <= 0 || dur === Infinity)) dur = playerTotalDuration;
            
            if (dur > 0 && video.buffered.length > 0) {
                let maxBuffered = 0;
                const curTime = video.currentTime;
                for (let i = 0; i < video.buffered.length; i++) {
                    if (video.buffered.start(i) <= curTime && video.buffered.end(i) >= curTime) {
                        maxBuffered = video.buffered.end(i);
                        break;
                    }
                }
                if (maxBuffered === 0) maxBuffered = video.buffered.end(video.buffered.length - 1);
                if (typeof playerRequiresTranscode !== 'undefined' && playerRequiresTranscode && typeof playerTimelineOffset !== 'undefined') {
                    maxBuffered += playerTimelineOffset;
                }
                
                // 🟢 GLOBAL TIMELINE SHIFT
                let displayMaxBuffered = maxBuffered;
                let displayDur = dur;
                if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                    const track = window.globalPlaylist[window.currentPlayIndex];
                    if (track) {
                        displayMaxBuffered = (track.startTime || 0) + maxBuffered;
                        displayDur = window.totalAlbumDuration || dur;
                    }
                }
                
                const pct = Math.min(100, (displayMaxBuffered / displayDur) * 100);
                bufferBar.style.width = `${pct}%`;
            }
        }

        function toggleMute() {
            const video = document.getElementById('hidden-video');
            const extAudio = document.getElementById('ext-audio-player');
            if (!video) return;
            
            video.muted = !video.muted;
            if (extAudio) extAudio.muted = video.muted;
            
            const muteBtn = document.getElementById('hud-mute-btn');
            if (muteBtn) {
                if (video.muted) {
                    muteBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>';
                } else {
                    muteBtn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>';
                }
            }
            wakeHUD();
        }

        let currentBrightLevel = 100;
        function cycleBrightness() {
            // 🟢 FIX: Added 150% and 200% brightness overdrive!
            const levels = [100, 150, 200, 75, 50, 25];
            let idx = levels.indexOf(currentBrightLevel);
            currentBrightLevel = levels[(idx + 1) % levels.length];
            
            const slider = document.getElementById('filter-bright');
            if (slider) slider.value = currentBrightLevel;
            applyVideoFilters();
            
            // 🟢 FIX: Dynamically update the SVG icon based on brightness level
            const btn = document.getElementById('hud-brightness-btn');
            if (btn) {
                if (currentBrightLevel >= 100) {
                    // Full Sun (All Rays)
                    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1zM5.99 4.58c-.39-.39-1.03-.39-1.41 0-.39.39-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0 .39-.39.39-1.03 0-1.41L5.99 4.58zm12.37 12.37c-.39-.39-1.03-.39-1.41 0-.39.39-.39 1.03 0 1.41l1.06 1.06c.39.39 1.03.39 1.41 0 .39-.39.39-1.03 0-1.41l-1.06-1.06zm1.06-10.96c.39-.39.39-1.03 0-1.41-.39-.39-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41.39.39 1.03.39 1.41 0l1.06-1.06zM7.05 18.36c.39-.39.39-1.03 0-1.41-.39-.39-1.03-.39-1.41 0l-1.06 1.06c-.39.39-.39 1.03 0 1.41.39.39 1.03.39 1.41 0l1.06-1.06z"/></svg>';
                } else if (currentBrightLevel === 75) {
                    // Medium Sun (Cross Rays only)
                    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7c-2.76 0-5 2.24-5 5s2.24 5 5 5 5-2.24 5-5-2.24-5-5-5zM2 13h2c.55 0 1-.45 1-1s-.45-1-1-1H2c-.55 0-1 .45-1 1s.45 1 1 1zm18 0h2c.55 0 1-.45 1-1s-.45-1-1-1h-2c-.55 0-1 .45-1 1s.45 1 1 1zM11 2v2c0 .55.45 1 1 1s1-.45 1-1V2c0-.55-.45-1-1-1s-1 .45-1 1zm0 18v2c0 .55.45 1 1 1s1-.45 1-1v-2c0-.55-.45-1-1-1s-1 .45-1 1z"/></svg>';
                } else if (currentBrightLevel === 50) {
                    // Low Sun (No Rays, Core Only)
                    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="5"/></svg>';
                } else {
                    // Lowest / Night (Moon Icon)
                    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M9.37 5.51A7.35 7.35 0 009.1 7.5c0 4.08 3.32 7.4 7.4 7.4.68 0 1.35-.09 1.99-.27A7.014 7.014 0 0112 19c-3.86 0-7-3.14-7-7 0-2.93 1.81-5.45 4.37-6.49z"/></svg>';
                }
            }
            wakeHUD();
        }

        async function togglePiP() {
            const video = document.getElementById('hidden-video');
            if (!video) return;
            try {
                // Standard API for Chrome, Edge, Firefox, Android
                if (document.pictureInPictureElement) {
                    await document.exitPictureInPicture();
                } else if (document.pictureInPictureEnabled) {
                    await video.requestPictureInPicture();
                } 
                // Apple iOS Safari proprietary API bypass
                else if (video.webkitSupportsPresentationMode && typeof video.webkitSetPresentationMode === "function") {
                    video.webkitSetPresentationMode(video.webkitPresentationMode === "picture-in-picture" ? "inline" : "picture-in-picture");
                } else {
                    alert("Picture-in-Picture is not supported by your device/browser.");
                }
            } catch (err) { console.error("PiP error:", err); }
            wakeHUD();
        }

        if (vidElem) {
            const extAudio = document.getElementById('ext-audio-player');

            // 🟢 FIX: Hide the main WebGL Canvas when PiP is active to prevent "Double Video"
            vidElem.addEventListener('enterpictureinpicture', () => {
                const canvas = document.getElementById('webgl-canvas');
                if (canvas) canvas.style.visibility = 'hidden'; 
            });
            vidElem.addEventListener('leavepictureinpicture', () => {
                const canvas = document.getElementById('webgl-canvas');
                if (canvas) canvas.style.visibility = 'visible'; 
            });
            vidElem.addEventListener('webkitpresentationmodechanged', () => {
                const canvas = document.getElementById('webgl-canvas');
                if (canvas) {
                    canvas.style.visibility = vidElem.webkitPresentationMode === "picture-in-picture" ? 'hidden' : 'visible';
                }
            });

            vidElem.addEventListener('play', () => {
                if (hudPlay) hudPlay.innerHTML = smallPauseSvg;
                if (bigPlay) bigPlay.innerHTML = pauseSvg;
                if (extAudio && extAudio.src) extAudio.play().catch(e => console.warn(e));
                wakeHUD();
            });
            vidElem.addEventListener('pause', () => {
                if (hudPlay) hudPlay.innerHTML = smallPlaySvg;
                if (bigPlay) bigPlay.innerHTML = playSvg;
                if (extAudio && extAudio.src) extAudio.pause();
                wakeHUD();
            });
            vidElem.addEventListener('ratechange', () => {
                if (extAudio && extAudio.src) extAudio.playbackRate = vidElem.playbackRate;
            });
            vidElem.addEventListener('seeking', () => {
                if (extAudio && extAudio.src) extAudio.currentTime = vidElem.currentTime;
            });
            // 🟢 STALL RECOVERY ENGINE
            let stallTimer = null;
            function triggerStallRecovery() {
                clearTimeout(stallTimer);
                stallTimer = setTimeout(async () => {
                    // Only reconnect if the player is actually trying to load/play data
                    if (playerRequiresTranscode && (!vidElem.paused || isTranscodeSeeking)) {
                        console.log("[DEBUG] Hard stall for 8s. Browser suspended stream. Forcing reconnect from:", globalTargetTime);
                        playerTimelineOffset = globalTargetTime || 0;
                        try { await setVideoSource(buildStreamUrl(playerTimelineOffset), 0, true); } catch(_) {}
                    }
                }, 30000); // Wait 30 seconds before determining the stream is dead
            }

            vidElem.addEventListener('ended', async () => {
                wakeHUD();
                
                // 🟢 PLAYLIST AUTO-NEXT LOGIC
                if (window.globalPlaylist && window.globalPlaylist.length > 0 && window.currentPlayIndex < window.globalPlaylist.length - 1) {
                    window.currentPlayIndex++;
                    if (window.updateAlbumText) window.updateAlbumText();
                    
                    console.log("[PLAYLIST] Playing Next Track...");
                    playerTimelineOffset = 0;
                    isTranscodeSeeking = false;
                    
                    // Re-calculate the URL for the next track index
                    const nextUrl = playerDirectCompatible ? buildNativeUrl() : buildStreamUrl(0);
                    try { await setVideoSource(nextUrl, 0, true); } catch (_) {}
                    return;
                }

                // Normal Stall/Reconnect Logic for single files
                if (playerRequiresTranscode && playerTotalDuration > 0 && globalTargetTime < playerTotalDuration - 5) {
                    console.log("[DEBUG] Stream ended prematurely. Reconnecting...");
                    
                    if (window.endedRetryCount > 3) {
                        const titleEl = document.getElementById('cinema-title');
                        if (titleEl) titleEl.innerText = '⚠️ Stream interrupted too many times.';
                        return;
                    }
                    window.endedRetryCount = (window.endedRetryCount || 0) + 1;

                    playerTimelineOffset = globalTargetTime || 0;
                    try { await setVideoSource(buildStreamUrl(playerTimelineOffset), 0, true); } catch (_) {}
                }
            });
            vidElem.addEventListener('waiting', () => { 
                if (bigPlay) bigPlay.innerHTML = '⏳'; 
                if (extAudio && extAudio.src) extAudio.pause(); 
                triggerStallRecovery(); 
            });
            vidElem.addEventListener('stalled', () => { 
                if (extAudio && extAudio.src) extAudio.pause(); // 🟢 FIX: Pause audio on stall
                triggerStallRecovery(); 
            });
            vidElem.addEventListener('playing', () => { 
                clearTimeout(stallTimer); 
                isTranscodeSeeking = false;
                window.errorRetryCount = 0; 
                window.endedRetryCount = 0; 
                if (bigPlay) bigPlay.innerHTML = pauseSvg; 

                // 🟢 FAST SYNC: Hard sync external audio when video resumes playing
                if (extAudio && extAudio.src) {
                    if (Math.abs(extAudio.currentTime - vidElem.currentTime) > 0.1) {
                        extAudio.currentTime = vidElem.currentTime;
                    }
                    extAudio.play().catch(e => console.warn(e));
                }
            });
            vidElem.addEventListener('loadedmetadata', () => { 
                clearTimeout(stallTimer);
                updateViewportBox(); resizePlayerSurface(); applyPlaybackSpeed(); 
            });
            vidElem.addEventListener('seeked', () => renderCurrentSubtitle());
            
            // 🟢 Attach buffer event
            vidElem.addEventListener('progress', updateBufferBar);

            vidElem.addEventListener('timeupdate', () => {
                clearTimeout(stallTimer); 
                updateBufferBar(); 

                // 🟢 FAST SYNC: Continuous drift correction for External Audio tracks
                if (extAudio && extAudio.src && !vidElem.paused && !vidElem.seeking) {
                    const drift = Math.abs(extAudio.currentTime - vidElem.currentTime);
                    if (drift > 0.15) { 
                        extAudio.currentTime = vidElem.currentTime;
                    }
                }
                
                let cur = vidElem.currentTime || 0;
                let dur = vidElem.duration || 0;

                if (playerRequiresTranscode) {
                    cur = playerTimelineOffset + cur;
                    if (playerTotalDuration > 0) dur = playerTotalDuration;
                } else if (playerTotalDuration > 0 && (!Number.isFinite(dur) || dur <= 0 || dur === Infinity)) {
                    dur = playerTotalDuration;
                }
                cur = Math.min(cur, dur);

                if (!isTranscodeSeeking && !vidElem.seeking && !isDraggingScrubber) {
                    globalTargetTime = cur; 
                }

                // 🟢 CONTINUOUS ALBUM TIMELINE LOGIC
                let displayCur = cur;
                let displayDur = dur;

                if (window.globalPlaylist && window.globalPlaylist.length > 0) {
                    const track = window.globalPlaylist[window.currentPlayIndex];
                    if (track) {
                        displayCur = (track.startTime || 0) + cur;
                        displayDur = window.totalAlbumDuration || dur;
                    }
                }
                
                displayCur = Math.min(displayCur, displayDur);

                const percent = displayDur ? Math.max(0, Math.min(100, displayCur / displayDur * 100)) : 0;
                const time = document.getElementById('hud-time');
                
                if (!isTranscodeSeeking && !vidElem.seeking && !isDraggingScrubber) {
                    const fill = document.getElementById('scrubber-fill');
                    if (fill) fill.style.width = `${percent}%`;
                    
                    const fmt = (s) => {
                        if (!Number.isFinite(s) || s < 0) return '00:00';
                        const h = Math.floor(s / 3600);
                        const m = Math.floor((s % 3600) / 60);
                        const sec = Math.floor(s % 60);
                        const hh = h > 0 ? `${String(h).padStart(2, '0')}:` : '';
                        return `${hh}${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
                    };
                    if (time) time.innerText = `${fmt(displayCur)} / ${fmt(displayDur)}`;
                }
                renderCurrentSubtitle(cur);
            });
            vidElem.addEventListener('error', async () => {
                const mediaError = vidElem.error;
                console.warn('Video element error:', mediaError);
                
                // 🟢 PREVENT ENDLESS LOOP: Stop trying if it fails twice
                if (window.errorRetryCount > 1) {
                    const titleEl = document.getElementById('cinema-title');
                    if (titleEl) titleEl.innerText = '⚠️ Playback Error: Browser Unsupported Format.';
                    return;
                }
                window.errorRetryCount = (window.errorRetryCount || 0) + 1;

                if (activeMediaLink) {
                    console.log("[DEBUG] Browser rejected codec (HEVC). Forcing H.264 Transcode...");
                    playerRequiresTranscode = true;
                    window.forceX264Flag = true; // 🟢 FIX: Switch from Copy to X264 Transcode
                    playerTimelineOffset = globalTargetTime || 0;
                    
                    setTimeout(async () => {
                        try { await setVideoSource(buildStreamUrl(playerTimelineOffset), 0, true); } catch (_) {}
                    }, 1500); 
                }
                wakeHUD();
            });
        }

        if (vpElement) {
            vpElement.addEventListener('pointermove', wakeHUD, { passive: true });
            vpElement.addEventListener('pointerdown', wakeHUD, { passive: true });
            vpElement.addEventListener('click', (e) => {
                // A tap/click wakes controls. Buttons keep their own click handlers.
                if (e.target.closest('button, .center-btn, .settings-popup, .matrix-3d-menu, .cinema-scrubber-bar')) return;
                wakeHUD();
            });
            vpElement.addEventListener('touchstart', wakeHUD, { passive: true });
            document.getElementById('media-settings-popup')?.addEventListener('pointerdown', wakeHUD, { passive: true });
            document.getElementById('menu-3d')?.addEventListener('pointerdown', wakeHUD, { passive: true });
        }

        const aspectSelect = document.getElementById('pop-aspect-select');
        if (aspectSelect) {
            const savedAspect = localStorage.getItem('player_aspect_mode') || 'contain';
            aspectSelect.value = savedAspect;
            applyAspectRatio(savedAspect);
        }

        const resizeObserver = typeof ResizeObserver !== 'undefined' && vpElement
            ? new ResizeObserver(() => { updateViewportBox(); resizePlayerSurface(); })
            : null;
        resizeObserver?.observe(vpElement);
        window.addEventListener('resize', () => { updateViewportBox(); resizePlayerSurface(); });
        
        document.addEventListener('fullscreenchange', () => { 
            updateViewportBox(); resizePlayerSurface(); 
            if (!document.fullscreenElement && screen.orientation && screen.orientation.unlock) {
                try { screen.orientation.unlock(); } catch(e){}
            }
        });
        
        document.addEventListener('webkitfullscreenchange', () => { 
            updateViewportBox(); resizePlayerSurface(); 
            if (!document.webkitFullscreenElement && screen.orientation && screen.orientation.unlock) {
                try { screen.orientation.unlock(); } catch(e){}
            }
        });

        // Initial state: hidden while idle, visible on first interaction/playback.
        if (vpElement) vpElement.classList.add('idle-hide');
        if (!gl) initWebGL();

        // ======================================================================
        // 🛠️ BACKGROUND DEBUGGER TOOL
        // ======================================================================
        function runBackgroundDebug() {
            try {
                const theme = document.documentElement.getAttribute('data-theme');
                const rootStyles = getComputedStyle(document.documentElement);
                const animeBg = String(rootStyles.getPropertyValue('--anime-bg')).trim();
                
                let debugLog = "🛠️ UI BACKGROUND DEBUGGER\\n";
                debugLog += "--------------------------------\\n";
                debugLog += "1️⃣ Active Theme: " + theme + "\\n";
                debugLog += "2️⃣ CSS Variable: " + (animeBg ? animeBg.substring(0, 30) + "..." : "Missing/None") + "\\n";
                
                // Extract URL (Double backslashes for Regex escape inside Python strings)
                const urlMatch = animeBg.match(/url\\(['"]?(.*?)['"]?\\)/);
                if (!urlMatch || !urlMatch[1]) {
                    debugLog += "\\n❌ ERROR: No valid URL found in CSS. Ensure theme CSS is formatted correctly.";
                    alert(debugLog);
                    return;
                }
                
                const targetUrl = urlMatch[1];
                debugLog += "3️⃣ Target URL: " + targetUrl.substring(0, 35) + "...\\n";
                debugLog += "\\n⏳ Testing Network Connection...\\n";
                
                // Attempt to load the image via JS to see if browser/HuggingFace blocks it
                const img = new Image();
                img.onload = function() {
                    debugLog += "✅ Network Test: SUCCESS!\\n";
                    debugLog += "The browser downloaded the image perfectly.\\n\\n";
                    debugLog += "👉 CONCLUSION: If you still can't see the image, the issue is the CSS gradient hiding it. Change the CSS 'background-image' linear-gradient opacity.";
                    alert(debugLog);
                };
                img.onerror = function() {
                    debugLog += "❌ Network Test: FAILED!\\n\\n";
                    debugLog += "👉 CONCLUSION: HuggingFace's Content Security Policy (CSP) or your mobile adblocker/browser is actively blocking the image URL from loading. Try opening the direct Space URL instead of the embedded iframe.";
                    alert(debugLog);
                };
                img.src = targetUrl;
                
            } catch (err) {
                alert("Debug Script Error: " + err.message);
            }
        }

        // ======================================================================
        // 🌍 3D WORLD GLOBE (HIGH-RES UPGRADE) & GEO API ENGINE
        // ======================================================================
        let myGlobe = null;
        let globalGeoData = [];
        let liveClockInterval = null;

        async function initWorldGlobe() {
            if (myGlobe) return; 
            const container = document.getElementById('globe-viz');
            
            // 🟢 UPGRADE 1: 50m High-Resolution Dataset!
            // This includes Mauritius, Andaman, Maldives, Seychelles, and tiny borders.
            const GEOJSON_URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson';

            try {
                const res = await fetch(GEOJSON_URL);
                const countries = await res.json();
                globalGeoData = countries.features;

                document.getElementById('globe-loading').style.display = 'none';

                myGlobe = Globe()
                    (container)
                    .width(container.clientWidth)
                    .height(container.clientHeight)
                    // 🟢 UPGRADE 2: High-Res Satellite Topography (Shows Mountains, Rivers, Oceans, Deserts)
                    .globeImageUrl('https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg')
                    .bumpImageUrl('https://unpkg.com/three-globe/example/img/earth-topology.png')
                    .backgroundImageUrl('https://unpkg.com/three-globe/example/img/night-sky.png')
                    .lineHoverPrecision(0)
                    .polygonsData(globalGeoData)
                    .polygonAltitude(0.01)
                    .polygonCapColor(() => 'rgba(56, 189, 248, 0.1)') // Made slightly more transparent so you can see the terrain underneath!
                    .polygonSideColor(() => 'rgba(0, 0, 0, 0.5)')
                    .polygonStrokeColor(() => '#38bdf8')
                    .polygonLabel(({ properties: d }) => `
                        <div style="background: rgba(0,0,0,0.85); padding: 8px 12px; border-radius: 8px; border: 1px solid var(--accent); color: white; font-family: 'Nunito', sans-serif; box-shadow: 0 5px 15px rgba(0,0,0,0.5);">
                            <b style="font-size:14px; text-transform:uppercase; letter-spacing:1px;">${d.ADMIN}</b>
                            <div style="font-size:10px; color:#94a3b8; margin-top:3px;">Click to Analyze</div>
                        </div>
                    `)
                    .onPolygonHover(hoverD => myGlobe
                        .polygonAltitude(d => d === hoverD ? 0.06 : 0.01)
                        .polygonCapColor(d => d === hoverD ? 'rgba(244, 114, 182, 0.6)' : 'rgba(56, 189, 248, 0.1)')
                    )
                    .onPolygonClick(({ properties: d }) => {
                        fetchCountryAnalytics(d.ISO_A2, d.ADMIN);
                    });

                // Auto-Rotate
                myGlobe.controls().autoRotate = true;
                myGlobe.controls().autoRotateSpeed = 0.5;

                // Responsive
                window.addEventListener('resize', () => {
                    if (myGlobe) myGlobe.width(container.clientWidth).height(container.clientHeight);
                });

            } catch (err) {
                console.error("Globe Boot Error:", err);
                document.getElementById('globe-loading').innerText = "⚠️ Server connection to satellites failed.";
            }
        }

        async function fetchCountryAnalytics(isoCode, countryName) {
            document.getElementById('country-data-panel').style.display = 'block';
            document.getElementById('c-name').innerText = "Scanning Data...";
            document.getElementById('c-wiki').innerHTML = '<span style="color:var(--accent);">Fetching geopolitical records via Secure Backend Proxy...</span>';
            
            if (myGlobe) myGlobe.controls().autoRotate = false;

            let countryData = null;

            // 🟢 BLOCK 1: Fetch Core Demographic & Time Data via Backend Proxy
            try {
                const proxyUrl = '/api/proxy/country?iso=' + (isoCode || '') + '&name=' + encodeURIComponent(countryName);
                const res = await fetch(proxyUrl);
                
                const rawText = await res.text();
                let rawJson;
                try {
                    rawJson = JSON.parse(rawText);
                } catch (e) {
                    throw new Error("Invalid JSON from server: " + rawText.substring(0, 40) + "...");
                }

                if (!res.ok) {
                    throw new Error(rawJson.error || "HTTP " + res.status);
                }
                
                // 🟢 BULLETPROOF FIX: Safely handle both Array [ {data} ] and Object {data} responses
                let data = null;
                if (Array.isArray(rawJson) && rawJson.length > 0) {
                    data = rawJson[0];
                } else if (typeof rawJson === 'object' && rawJson !== null && !Array.isArray(rawJson)) {
                    data = rawJson;
                }
                
                if (!data || !data.flags) {
                    throw new Error("API returned an unrecognizable structure.");
                }
                
                countryData = data; 
                
                document.getElementById('c-flag').src = (data.flags && (data.flags.svg || data.flags.png)) || '';
                document.getElementById('c-name').innerText = (data.name && data.name.common) || countryName;
                document.getElementById('c-cap').innerText = data.capital ? data.capital[0] : 'N/A';
                document.getElementById('c-reg').innerText = ((data.region || '') + ' (' + (data.subregion || '') + ')').replace(' ()', '');
                document.getElementById('c-pop').innerText = data.population ? data.population.toLocaleString() : 'N/A';
                document.getElementById('c-lang').innerText = data.languages ? Object.values(data.languages).join(', ') : 'Unknown';
                document.getElementById('c-curr').innerText = data.currencies ? Object.values(data.currencies).map(c => c.name + ' (' + c.symbol + ')').join(', ') : 'Unknown';

                clearInterval(liveClockInterval);
                if (data.timezones && data.timezones.length > 0) {
                    const primaryTz = data.timezones[0];
                    updateLiveCountryTime(primaryTz);
                    liveClockInterval = setInterval(() => updateLiveCountryTime(primaryTz), 1000);
                } else {
                    document.getElementById('c-time').innerText = "Time Unknown";
                }

            } catch (err) {
                console.error("Proxy API failed:", err);
                document.getElementById('c-name').innerText = countryName;
                document.getElementById('c-cap').innerText = "Error";
                document.getElementById('c-pop').innerText = "Error";
                document.getElementById('c-wiki').innerHTML = '<span style="color:#ef4444;">Network Error: Backend Proxy failed. ' + err.message + '</span>';
                return; 
            }

            // 🟢 BLOCK 2: Fetch Wikipedia via Backend Proxy
            try {
                const wikiQuery = countryData ? (countryData.name && countryData.name.common) || countryName : countryName;
                const wikiRes = await fetch('/api/proxy/wiki?q=' + encodeURIComponent(wikiQuery));
                
                if (wikiRes.ok) {
                    const wikiData = await wikiRes.json();
                    if (wikiData.type !== "disambiguation" && wikiData.extract) {
                        const pageUrl = (wikiData.content_urls && wikiData.content_urls.desktop) ? wikiData.content_urls.desktop.page : 'https://en.wikipedia.org/wiki/' + encodeURIComponent(wikiQuery);
                        document.getElementById('c-wiki').innerHTML = '<p>' + wikiData.extract + '</p><a href="' + pageUrl + '" target="_blank" style="color: var(--accent); text-decoration: none; font-weight: bold; font-size: 11px; text-transform: uppercase; border: 1px solid var(--accent); padding: 5px 10px; border-radius: 6px; display: inline-block; margin-top: 10px;">Read Full Wikipedia Article</a>';
                    } else {
                        document.getElementById('c-wiki').innerText = "Wikipedia summary requires disambiguation.";
                    }
                } else {
                    document.getElementById('c-wiki').innerText = "Detailed Wikipedia historical records currently unavailable.";
                }
            } catch (err) {
                document.getElementById('c-wiki').innerText = "Detailed Wikipedia historical records currently unavailable.";
            }
        }

        // ======================================================================
        // DEDICATED MEDIA EDITOR TAB (Python-Safe Strings)
        // ======================================================================
        async function loadEditorMedia() {
            const link = document.getElementById('editor-stream-url').value.trim();
            if (!link) return alert('Provide a valid media link!');
            
            const btn = document.getElementById('editor-load-btn');
            const workspace = document.getElementById('editor-workspace');
            const container = document.getElementById('editor-tracks-container');
            const statusBox = document.getElementById('editor-status');
            
            btn.innerText = '⏳ Probing...';
            btn.disabled = true;
            workspace.style.display = 'none';
            statusBox.style.display = 'none';
            
            try {
                const res = await fetch('/api/media_probe?user_id=' + encodeURIComponent(currentUser) + '&link=' + encodeURIComponent(link));
                const data = await res.json();
                
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Probe failed');
                }
                
                window.editorProbeData = data;
                window.editorMediaLink = link;
                container.innerHTML = '';
                
                data.streams.forEach(function(s) {
                    const type = s.codec_type || 'unknown';
                    const codec = s.codec_name || '';
                    const idx = s.index;
                    const lang = (s.tags && (s.tags.language || s.tags.LANGUAGE)) || '';
                    const title = (s.tags && (s.tags.title || s.tags.TITLE)) || '';
                    
                    let color = '#f59e0b';
                    if (type === 'video') color = '#38bdf8';
                    if (type === 'audio') color = '#10b981';
                    
                    let langText = lang ? '(' + lang + ')' : '';
                    
                    let htmlStr = '<div style="padding: 12px; margin: 0; background: rgba(0,0,0,0.4); border: 1px solid var(--card-border); border-left: 4px solid ' + color + '; display: flex; flex-direction: column; gap: 8px; border-radius: 12px;">';
                    htmlStr += '<div style="display: flex; justify-content: space-between; align-items: center;">';
                    htmlStr += '<label style="color: #fff; font-weight: bold; font-size: 13px; display: flex; align-items: center; gap: 8px;">';
                    htmlStr += '<input type="checkbox" id="edit-keep-' + idx + '" checked style="width: 16px; height: 16px; accent-color: var(--accent);"> ';
                    htmlStr += 'Track ' + idx + ' [' + type.toUpperCase() + ']';
                    htmlStr += '</label>';
                    htmlStr += '<span style="color: var(--subtext); font-size: 11px;">' + codec + ' ' + langText + '</span>';
                    htmlStr += '</div>';
                    htmlStr += '<div style="display: flex; gap: 10px;">';
                    htmlStr += '<input type="text" id="edit-title-' + idx + '" placeholder="New Title..." value="' + title + '" style="flex: 2; padding: 8px; border-radius: 8px; border: 1px solid var(--card-border); background: var(--bg); color: #fff; font-size: 12px;">';
                    htmlStr += '<input type="number" id="edit-delay-' + idx + '" placeholder="Delay (ms)" value="0" style="flex: 1; padding: 8px; border-radius: 8px; border: 1px solid var(--card-border); background: var(--bg); color: #fff; font-size: 12px;">';
                    htmlStr += '</div></div>';
                    
                    container.innerHTML += htmlStr;
                });
                
                document.getElementById('editor-filename').value = data.file_name || 'output.mkv';
                workspace.style.display = 'block';
                
                // Re-initialize custom glass dropdowns for the destination selector
                initCustomSelects();
                
            } catch (err) {
                alert("Analysis failed: " + err.message);
            } finally {
                btn.innerText = 'Analyze Tracks';
                btn.disabled = false;
            }
        }

        async function submitEditorTask() {
            const btn = document.getElementById('editor-submit-btn');
            const status = document.getElementById('editor-status');
            const dest = document.getElementById('editor-dest').value;
            const newName = document.getElementById('editor-filename').value;
            
            let config = [];
            window.editorProbeData.streams.forEach(function(s) {
                const idx = s.index;
                const cb = document.getElementById('edit-keep-' + idx);
                if (cb && cb.checked) {
                    config.push({
                        index: idx,
                        title: document.getElementById('edit-title-' + idx).value,
                        delay: document.getElementById('edit-delay-' + idx).value || 0
                    });
                }
            });
            
            if (config.length === 0) return alert("You must keep at least one track!");
            
            btn.disabled = true;
            btn.innerText = "⏳ Processing...";
            status.style.display = 'block';
            status.innerText = "Downloading, Remuxing & Uploading... This may take a few minutes depending on file size.";
            
            try {
                const res = await fetch('/api/edit_media', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_id: currentUser,
                        link: window.editorMediaLink,
                        config: config,
                        new_name: newName,
                        dest: dest
                    })
                });
                const data = await res.json();
                
                if (data.status === 'success') {
                    status.innerHTML = '✅ <b>Success!</b><br><a href="' + data.url + '" target="_blank" style="color: #10b981; text-decoration: underline;">Click here to view/download</a>';
                } else {
                    status.innerHTML = '❌ <b>Error:</b> ' + data.message;
                }
            } catch (e) {
                status.innerHTML = '❌ <b>Network Error:</b> ' + e.message;
            } finally {
                btn.disabled = false;
                btn.innerText = "🚀 Process & Upload";
            }
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
        delay = max(3, min(int(data.get("delay", 3)), 3600))
        allowed_types = data.get("filters", ["Video", "Document"])
        if not isinstance(allowed_types, list):
            allowed_types = ["Video", "Document"]
        allowed_types = [t for t in allowed_types if t in ALL_MSG_TYPES]

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

        if not await check_disk_space():
            return web.json_response({"status": "error", "message": "Server disk is almost full (<500MB). Please wait."})

        if user_id not in ADMINS and batch_temp.ACTIVE_TASKS[user_id] >= MAX_CONCURRENT_TASKS_PER_USER:
            return web.json_response({"status": "error", "message": f"Task limit reached ({MAX_CONCURRENT_TASKS_PER_USER} max). Wait for existing tasks to finish."})

        is_restricted, _ = await check_link_restriction(user_id, link)
        if is_restricted is None: is_restricted = False

        task_uuid = uuid.uuid4().hex
        batch_temp.ACTIVE_TASKS[user_id] += 1
        batch_temp.IS_BATCH[user_id] = False

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
        delay = max(3, min(int(data.get("delay", 3)), 3600))
        allowed_types = data.get("filters", ["Video", "Document"])
        if not isinstance(allowed_types, list):
            allowed_types = ["Video", "Document"]
        allowed_types = [t for t in allowed_types if t in ALL_MSG_TYPES]

        dest_chat_id = user_id
        dest_thread_id = None
        if dest_str:
            dest_chat_id, dest_thread_id = _parse_chat_target(dest_str)

        is_restricted, _ = await check_link_restriction(user_id, link)
        if is_restricted is None: is_restricted = False

        parsed = _parse_source_link(link)

        source_thread = parsed.get("topic_id")
        
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
                new_client.add_handler(MessageHandler(user_watcher_handler, filters.all))
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
            source_thread=source_thread,
            dest_thread=dest_thread_id,
            delay=delay,
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
        uid = int(request.query.get("user_id", 0))
    except:
        uid = 0
        
    if uid not in ADMINS and uid not in SUDOS:
        return web.json_response({"logs": "⚠️ ACCESS DENIED: You must be a Bot Admin to view server logs."})
        
    try:
        logs = await asyncio.to_thread(_read_logs_sync)
        return web.json_response({"logs": logs})
    except Exception as e:
        return web.json_response({"logs": f"Error reading logs: {e}"})

async def _api_download_log_handler(request):
    try:
        uid = int(request.query.get("user_id", 0))
    except:
        uid = 0
        
    if uid not in ADMINS and uid not in SUDOS:
        return web.Response(text="ACCESS DENIED: Admins Only", status=403)
        
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
    
    client = Client(f"web_auth_{uid}_{uuid.uuid4().hex}", in_memory=True, api_id=API_ID, api_hash=API_HASH)
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
        
        # 🟢 ENFORCE ID MATCH: Prevent cross-account chat leaks!
        me = await client.get_me()
        if me.id != uid:
            await client.disconnect()
            del WEB_AUTH_CACHE[uid]
            return web.json_response({"status": "error", "message": f"⚠️ ID Mismatch! You logged into the Web UI as {uid}, but this phone number belongs to {me.id}. Please use your own Telegram account."})
            
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
        
        # 🟢 ENFORCE ID MATCH: Prevent cross-account chat leaks!
        me = await client.get_me()
        if me.id != uid:
            await client.disconnect()
            del WEB_AUTH_CACHE[uid]
            return web.json_response({"status": "error", "message": f"⚠️ ID Mismatch! You logged into the Web UI as {uid}, but this phone number belongs to {me.id}. Please use your own Telegram account."})
            
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
    session_str = await db.get_session(uid)
    
    if not session_str:
        return web.json_response({"status": "error", "message": "Not connected to Telegram. Please login."})

    uclient = USER_CLIENTS.get(uid)
    
    # 🟢 DYNAMIC WAKE-UP: Keep the main user session alive so we don't lose Access Hashes!
    if not uclient or not uclient.is_connected:
        try:
            api_id = await db.get_api_id(uid) or API_ID
            api_hash = await db.get_api_hash(uid) or API_HASH
            uclient = Client(f"User_{uid}", session_string=session_str, api_id=api_id, api_hash=api_hash, workers=4, ipv6=False)
            uclient.add_handler(MessageHandler(user_watcher_handler, filters.all))
            await uclient.start()
            USER_CLIENTS[uid] = uclient
        except Exception as e:
            return web.json_response({"status": "error", "message": f"Session invalid: {e}"})

    dialog_collection = []

    try:
        async def execute_raw_pagination(target_folder_id):
            import pyrogram.raw.types as raw_types
            from pyrogram.raw.functions.messages import GetDialogs
            
            offset_date = 0
            offset_id = 0
            offset_peer = raw_types.InputPeerEmpty()

            while True:
                try:
                    response = await uclient.invoke(
                        GetDialogs(
                            offset_date=offset_date,
                            offset_id=offset_id,
                            offset_peer=offset_peer,
                            limit=100,
                            hash=0,
                            folder_id=target_folder_id
                        ),
                        sleep_threshold=60
                    )
                    
                    if not getattr(response, "dialogs", None):
                        break

                    resolved_users = {u.id: u for u in getattr(response, "users", [])}
                    resolved_chats = {c.id: c for c in getattr(response, "chats", [])}

                    for dialog in response.dialogs:
                        peer = dialog.peer
                        raw_chat_id = getattr(peer, "channel_id", getattr(peer, "chat_id", getattr(peer, "user_id", None)))
                        if not raw_chat_id: continue

                        if hasattr(peer, "channel_id"):
                            chat_id = int(f"-100{raw_chat_id}")
                        elif hasattr(peer, "chat_id"):
                            chat_id = int(f"-{raw_chat_id}")
                        else:
                            chat_id = raw_chat_id
                        
                        title = "Unknown Object"
                        category_label = "Unknown"
                        is_forum = False
                        
                        if chat_id > 0:
                            u = resolved_users.get(chat_id)
                            if u:
                                title = getattr(u, "first_name", None)
                                if not title:
                                    title = "Unknown User"
                                if getattr(u, "last_name", None):
                                    title += f" {u.last_name}"
                                category_label = "🤖 Bot" if getattr(u, "bot", False) else "👤 User"
                        else:
                            c = resolved_chats.get(abs(chat_id)) or resolved_chats.get(getattr(peer, "channel_id", 0)) or resolved_chats.get(getattr(peer, "chat_id", 0))
                            if c:
                                title = getattr(c, "title", None)
                                if not title:
                                    title = "Unknown Group"
                                category_label = "📢 Channel" if getattr(c, "broadcast", False) else "👥 Group"
                                is_forum = getattr(c, "forum", False)

                        dialog_collection.append({
                            "id": str(chat_id), 
                            "name": f"[{category_label}] {title}", 
                            "is_forum": is_forum
                        })

                    if len(response.dialogs) < 100:
                        break
                        
                    last_dialog = response.dialogs[-1]
                    offset_id = getattr(last_dialog, "top_message", 0)
                    
                    offset_date = 0
                    for msg in response.messages:
                        if getattr(msg, "id", 0) == offset_id:
                            offset_date = getattr(msg, "date", 0)
                            break
                    if offset_date == 0 and response.messages:
                        offset_date = getattr(response.messages[-1], "date", 0)

                    last_peer = last_dialog.peer
                    raw_last_id = getattr(last_peer, "channel_id", getattr(last_peer, "chat_id", getattr(last_peer, "user_id", 0)))
                    
                    if hasattr(last_peer, "channel_id"):
                        last_peer_id = int(f"-100{raw_last_id}")
                    elif hasattr(last_peer, "chat_id"):
                        last_peer_id = int(f"-{raw_last_id}")
                    else:
                        last_peer_id = raw_last_id

                    try:
                        offset_peer = await uclient.resolve_peer(last_peer_id)
                    except Exception:
                        if hasattr(last_peer, "channel_id"):
                            c = resolved_chats.get(raw_last_id)
                            offset_peer = raw_types.InputPeerChannel(channel_id=raw_last_id, access_hash=getattr(c, "access_hash", 0)) if c else raw_types.InputPeerEmpty()
                        elif hasattr(last_peer, "chat_id"):
                            offset_peer = raw_types.InputPeerChat(chat_id=raw_last_id)
                        else:
                            u = resolved_users.get(raw_last_id)
                            offset_peer = raw_types.InputPeerUser(user_id=raw_last_id, access_hash=getattr(u, "access_hash", 0)) if u else raw_types.InputPeerEmpty()

                except FloodWait as e:
                    await asyncio.sleep(e.value + 1)
                except Exception as e:
                    logger.warning(f"Raw dialog pagination error: {e}")
                    break

        async def populate_web_dialogs():
            await execute_raw_pagination(0) # Standard Chats
            await execute_raw_pagination(1) # Archived Chats

        try:
            await asyncio.wait_for(populate_web_dialogs(), timeout=300.0)
        except asyncio.TimeoutError:
            logger.warning("Web dialog fetch reached the 300s timeout ceiling. Returning the partial payload.")
            
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

    # Deduplicate arrays safely before returning to web UI
    sanitized_collection = {c['id']: c for c in dialog_collection}.values()
    return web.json_response({"status": "success", "chats": list(sanitized_collection)})

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
            st = speedtest.Speedtest(secure=True)
            st.get_best_server()
            st.download()
            st.upload()
            try:
                st.results.share()
            except Exception:
                pass
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

async def _api_topics_handler(request):
    uid = int(request.query.get("user_id", 0))
    chat_id = request.query.get("chat_id", "")
    try: chat_id = int(chat_id)
    except: pass
    
    session_str = await db.get_session(uid)
    if not session_str:
        return web.json_response({"status": "error", "message": "Not connected to Telegram."})

    uclient = USER_CLIENTS.get(uid)

    # 🟢 DYNAMIC WAKE-UP
    if not uclient or not uclient.is_connected:
        try:
            api_id = await db.get_api_id(uid) or API_ID
            api_hash = await db.get_api_hash(uid) or API_HASH
            uclient = Client(f"User_{uid}", session_string=session_str, api_id=api_id, api_hash=api_hash, workers=4, ipv6=False)
            uclient.add_handler(MessageHandler(user_watcher_handler, filters.all))
            await uclient.start()
            USER_CLIENTS[uid] = uclient
        except Exception as e:
            return web.json_response({"status": "error", "message": f"Session invalid: {e}"})
    
    topics = []
    try:
        async def fetch_tg_topics():
            try:
                async for topic in uclient.get_forum_topics(chat_id, limit=300):
                    topics.append({"id": topic.id, "title": topic.title})
            except Exception as e:
                # Graceful handling of Pyrogram pagination bug
                if "'NoneType'" not in str(e):
                    logger.warning(f"Topic pagination interrupted: {e}")
            
        try:
            await asyncio.wait_for(fetch_tg_topics(), timeout=25.0)
        except asyncio.TimeoutError:
            logger.warning(f"Topics endpoint timed out. Returning {len(topics)} topics found so far.")
        except Exception as e:
            logger.warning(f"Topics endpoint exception: {repr(e)}")
                
    except Exception as e:
        logger.warning(f"Topics endpoint error: {repr(e)}")

    return web.json_response({"status": "success", "topics": topics})

# 🟢 NEW: Deep Chat Details & MetaData Fetcher
import traceback

async def _api_chat_details_handler(request):
    uid = int(request.query.get("user_id", 0))
    raw_chat_string = request.query.get("chat_id", "").strip()
    
    if not raw_chat_string:
        return web.json_response({"status": "error", "message": "Missing required chat_id parameter."})
        
    try: 
        chat_id = int(raw_chat_string)
    except ValueError: 
        chat_id = raw_chat_string if raw_chat_string.startswith("@") else f"@{raw_chat_string}"

    session_str = await db.get_session(uid)
    if not session_str:
        return web.json_response({"status": "error", "message": "Not logged in."})

    uclient = USER_CLIENTS.get(uid)
    
    # Wake up routine to prevent locks
    if not uclient or not uclient.is_connected:
        try:
            api_id = await db.get_api_id(uid) or API_ID
            api_hash = await db.get_api_hash(uid) or API_HASH
            uclient = Client(f"User_{uid}", session_string=session_str, api_id=api_id, api_hash=api_hash, workers=4, ipv6=False)
            uclient.add_handler(MessageHandler(user_watcher_handler, filters.all))
            await uclient.start()
            USER_CLIENTS[uid] = uclient
        except Exception as e:
            logger.error(f"[CHAT DETAILS] Client connection failed: {e}")
            return web.json_response({"status": "error", "message": f"Session invalid: {e}"})

    try:
        # 🟢 FIX 1: Safely resolve ALL chat types (Users, Bots, Channels, Groups)
        try:
            chat = await asyncio.wait_for(uclient.get_chat(chat_id), timeout=12.0)
        except PeerIdInvalid:
            try:
                resolved_peer = await asyncio.wait_for(uclient.resolve_peer(chat_id), timeout=8.0)
                chat = await asyncio.wait_for(uclient.get_chat(resolved_peer), timeout=12.0)
            except Exception as inner_e:
                raise Exception(f"Fatal resolution failure. ({inner_e})")
        
        # Safely fetch total message count (Only works on Groups/Channels/PMs)
        try:
            total_msgs = await asyncio.wait_for(uclient.get_chat_history_count(chat_id), timeout=6.0)
        except Exception:
            total_msgs = "Unknown"

        topics = []
        is_forum = getattr(chat, "is_forum", False)
        
        # 🟢 FIX 2: Only fetch topics if it's explicitly a SUPERGROUP and a FORUM!
        # Prevents crashing on normal Groups, Channels, Bots, or Users.
        if is_forum and getattr(chat, "type", None) == enums.ChatType.SUPERGROUP:
            async def fetch_forum_topology():
                try:
                    # 🟢 FIX 3: HARD LIMIT to 250 topics so it finishes in 1-2 seconds and never times out!
                    async for t in uclient.get_forum_topics(chat_id, limit=250):
                        top_msg_data = getattr(t, "top_message", "?")
                        if hasattr(top_msg_data, "id"):
                            top_msg_val = str(top_msg_data.id)
                        else:
                            top_msg_val = str(top_msg_data)
                        topics.append({
                            "id": t.id,
                            "title": t.title,
                            "top_msg": top_msg_val
                        })
                except Exception as inner_e:
                    if "'NoneType'" not in str(inner_e):
                        logger.warning(f"[CHAT DETAILS] Topic pagination interrupted: {inner_e}")
                        
            try:
                # Give it 8 seconds to fetch the 250 topics
                await asyncio.wait_for(fetch_forum_topology(), timeout=8.0)
            except asyncio.TimeoutError:
                logger.warning(f"[CHAT DETAILS] Topic fetch timed out. Returning {len(topics)} topics found so far.")
            except Exception as e:
                logger.warning(f"[CHAT DETAILS] Could not fetch topics: {repr(e)}")

        return web.json_response({
            "status": "success",
            "id": str(chat.id),
            "title": chat.title or getattr(chat, "first_name", "Unknown"),
            "type": str(getattr(chat, "type", "Unknown")).replace("ChatType.", "").upper(),
            "members": getattr(chat, "members_count", 0),
            "total_messages": total_msgs,
            "description": getattr(chat, "description", getattr(chat, "bio", "")),
            "is_forum": is_forum,
            "topics": topics
        })
    except Exception as e:
        import traceback
        err_trace = traceback.format_exc()
        logger.error(f"[CHAT DETAILS ERROR] Traceback:\n{err_trace}")
        return web.json_response({"status": "error", "message": f"API Error: {str(e)}"})

async def _api_mediainfo_web_handler(request):
    data = await request.json()
    uid = int(data.get("user_id", 0))
    url = data.get("link", "")
    if not url: return web.json_response({"status": "error", "message": "No link provided"})
    
    file_path = Path(os.getcwd()) / f"web_mi_{uid}_{int(time.time())}.dat"
    file_name_display = "Unknown_File"
    file_size_display = 0
    
    try:
        # 🟢 FIX: Prioritize Telegram links FIRST so they don't get trapped by the HTTP downloader
        if "t.me" in url or "telegram.me" in url:
            parsed = _parse_source_link(url)
            chat_id = parsed.get("chat_id")
            msg_id = parsed.get("msg_id")
            
            # 🟢 DYNAMIC WAKE-UP: Automatically reconnect session if it fell asleep
            uclient = USER_CLIENTS.get(uid)
            if not uclient or not uclient.is_connected:
                session_str = await db.get_session(uid)
                if not session_str:
                    return web.json_response({"status": "error", "message": "Telegram session not active. Connect in Settings."})
                try:
                    api_id = await db.get_api_id(uid) or API_ID
                    api_hash = await db.get_api_hash(uid) or API_HASH
                    uclient = Client(f"User_{uid}", session_string=session_str, api_id=api_id, api_hash=api_hash, workers=4, ipv6=False)
                    uclient.add_handler(MessageHandler(user_watcher_handler, filters.all))
                    await uclient.start()
                    USER_CLIENTS[uid] = uclient
                except Exception as e:
                    return web.json_response({"status": "error", "message": f"Session invalid: {e}"})
                
            try:
                msg = await uclient.get_messages(chat_id, msg_id)
            except Exception as e:
                return web.json_response({"status": "error", "message": f"Failed to fetch message: {e}"})
                
            if not msg or msg.empty: return web.json_response({"status": "error", "message": "Message not found or inaccessible"})
            
            media_obj = msg.document or msg.video or msg.audio or msg.photo
            if not media_obj: return web.json_response({"status": "error", "message": "No media found in the provided link"})
            
            file_name_display = getattr(media_obj, 'file_name', 'Telegram_Media')
            file_size_display = getattr(media_obj, 'file_size', 0)
            
            await partial_download_tg(uclient, msg, file_path, limit_mb=15)

        elif url.startswith("http"):
            file_size_display, detected_name = await partial_download_http(url, file_path, limit_mb=15)
            file_name_display = detected_name
        else:
            return web.json_response({"status": "error", "message": "Invalid link format"})
            
        real_ext = Path(file_name_display).suffix
        if real_ext:
            new_path = file_path.with_suffix(real_ext)
            file_path.rename(new_path)
            file_path = new_path
            
        cmd = ["mediainfo", str(file_path)]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await process.communicate()
        raw_output = stdout.decode('utf-8', errors='ignore').strip()
        
        if not raw_output:
            return web.json_response({"status": "error", "message": "Could not read media metadata. File might be empty or invalid."})
            
        raw_output = raw_output.replace(str(file_path), file_name_display).replace(str(file_path.absolute()), file_name_display)
        html_formatted = f"<div style='color:var(--accent); font-weight:bold; font-size:15px;'>📌 {html.escape(file_name_display)}</div><br>" + parseinfo(raw_output, file_size_display)
        
        return web.json_response({"status": "success", "html": html_formatted})
        
    except Exception as e:
        # 🟢 FIX: Force empty string errors to print their raw representation so the popup is never blank
        err_msg = str(e) if str(e).strip() else repr(e)
        return web.json_response({"status": "error", "message": f"Processing error: {err_msg}"})
    finally:
        if 'file_path' in locals() and file_path.exists():
            try: os.remove(file_path)
            except: pass

async def _api_spectrogram_web_handler(request):
    data = await request.json()
    uid = int(data.get("user_id", 0))
    url = data.get("link", "")
    if not url: return web.json_response({"status": "error", "message": "No link provided"})
    
    temp_dir = Path(f"./temp_sox_web_{uid}_{int(time.time())}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    original_file = temp_dir / "audio_input.dat"
    wav_file = temp_dir / "converted.wav"
    output_img = temp_dir / "spectrogram.png"
    
    try:
        # 1. DOWNLOAD FULL FILE
        if "t.me" in url or "telegram.me" in url:
            parsed = _parse_source_link(url)
            chat_id = parsed.get("chat_id")
            msg_id = parsed.get("msg_id")
            
            uclient = USER_CLIENTS.get(uid)
            if not uclient or not uclient.is_connected:
                return web.json_response({"status": "error", "message": "Telegram session not active. Connect in Settings."})
                
            msg = await uclient.get_messages(chat_id, msg_id)
            if msg.empty: return web.json_response({"status": "error", "message": "Message not found or inaccessible"})
            await uclient.download_media(msg, file_name=str(original_file))
        elif url.startswith("http"):
            await full_download_http(url, original_file)
        else:
            return web.json_response({"status": "error", "message": "Invalid link format"})

        # 2. FFMPEG
        ffmpeg_cmd = ["ffmpeg", "-i", str(original_file), "-vn", "-ac", "2", "-c:a", "pcm_f32le", str(wav_file), "-y"]
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        await process.wait()
        
        if not wav_file.exists(): return web.json_response({"status": "error", "message": "Audio Extraction Failed."})

        # 3. DSP & SOX
        stats = generate_audio_stats_dsp(str(wav_file), str(original_file), "Web Audio")
        if not stats: return web.json_response({"status": "error", "message": "DSP Processing Failed."})

        sox_cmd = ["sox", str(wav_file), "-n", "spectrogram", "-o", str(output_img), "-x", "1000", "-Y", "800", "-c", "Audio", "-t", " "]
        process_sox = await asyncio.create_subprocess_exec(*sox_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process_sox.communicate()

        if not output_img.exists(): return web.json_response({"status": "error", "message": "SoX Generation Failed."})

        # 4. CONVERT TO BASE64 & HTML
        with open(output_img, "rb") as img_f:
            img_b64 = base64.b64encode(img_f.read()).decode('utf-8')

        m = stats['mastering']
        mastering_html = ""
        if m:
            mastering_html = (
                f"<br><span style='color:var(--accent);'><b>— MASTERING ANALYSIS —</b></span><br>"
                f"🎚 <b>Dynamic Range:</b> DR {m['dr']}<br>"
                f"🔊 <b>Loudness:</b> {m['lufs']:.1f} LUFS<br>"
                f"📈 <b>Peak / RMS:</b> {m['peak']:.2f} dBFS / {m['rms']:.2f} dB<br>"
                f"🏷 <b>Score:</b> {m['grade']}"
            )

        html_stats = (
            f"<span style='color:#10b981;'><b>{stats['auth_badge']}</b></span><br>"
            f"<i>{stats['auth_desc']}</i><br><br>"
            f"📀 <b>Format:</b> {stats['format']} • {stats['channel_str']} • {stats['bit_depth']}-bit • {stats['sample_rate']/1000} kHz<br>"
            f"📈 <b>Cutoff:</b> {stats['cutoff']} kHz<br>"
            f"🧱 <b>Cliff Drop:</b> {stats['cliff_drop']:.1f} dB"
            f"{mastering_html}"
        )

        return web.json_response({"status": "success", "image": img_b64, "html": html_stats})

    except Exception as e:
        return web.json_response({"status": "error", "message": f"Processing error: {e}"})
    finally:
        import shutil
        try: shutil.rmtree(str(temp_dir), ignore_errors=True)
        except: pass

# ==============================================================================
# --- HIGH-PERFORMANCE STREAMING, TRANSCODING & PROBE ENGINE ---
# ==============================================================================

def _is_tg_link(link):
    """Strictly separate Telegram Links from Direct Links to prevent intermixing."""
    if not link: return False
    return bool(re.search(r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)\/", str(link).strip().lower()))

DIRECT_URL_CACHE = {}
DIRECT_URL_CACHE_TTL = 900
DIRECT_RESOLVE_LOCKS = defaultdict(asyncio.Lock)
DIRECT_HEADER_CACHE = {}
DIRECT_HTTP_SESSION = None
DIRECT_HTTP_SESSION_LOCK = asyncio.Lock()

async def _get_direct_http_session():
    """Shared HTTP client with keep-alive/DNS reuse for direct media hosts."""
    global DIRECT_HTTP_SESSION
    if DIRECT_HTTP_SESSION is not None and not DIRECT_HTTP_SESSION.closed:
        return DIRECT_HTTP_SESSION
    async with DIRECT_HTTP_SESSION_LOCK:
        if DIRECT_HTTP_SESSION is None or DIRECT_HTTP_SESSION.closed:
            connector = aiohttp.TCPConnector(
                limit=0,          
                limit_per_host=0, 
                ttl_dns_cache=300,
                keepalive_timeout=60,
                enable_cleanup_closed=True,
            )
            timeout = aiohttp.ClientTimeout(
                total=None,
                connect=15,
                sock_connect=15,
                sock_read=None,   
            )
            DIRECT_HTTP_SESSION = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                },
            )
    return DIRECT_HTTP_SESSION

async def _close_direct_http_session():
    global DIRECT_HTTP_SESSION
    session = DIRECT_HTTP_SESSION
    DIRECT_HTTP_SESSION = None
    if session is not None and not session.closed:
        try:
            await session.close()
        except Exception:
            pass


async def resolve_direct_link(url):
    """Resolve common file-host pages to a stream URL, with coalesced/cached resolution."""
    original = str(url or '').strip()
    if not original:
        return original

    now = time.time()
    cached = DIRECT_URL_CACHE.get(original)
    if cached and cached[1] > now:
        return cached[0]

    lock = DIRECT_RESOLVE_LOCKS[original]
    async with lock:
        now = time.time()
        cached = DIRECT_URL_CACHE.get(original)
        if cached and cached[1] > now:
            return cached[0]

        import re
        result = original
        session = await _get_direct_http_session()

        # 1. Pixeldrain Auto-Bypass
        pixel_match = re.search(r"pixeldrain\.com/u/([a-zA-Z0-9_-]+)", original)
        if pixel_match:
            result = f"https://cdn.pixeldrain.eu.cc/{pixel_match.group(1)}"

        # 2. Dropbox Auto-Bypass (Forces direct download)
        if "dropbox.com" in original:
            result = original.replace("?dl=0", "?dl=1").replace("&dl=0", "&dl=1")
            if "?dl=1" not in result and "&dl=1" not in result:
                result += "?dl=1"

        # 3. OneDrive / SharePoint Auto-Bypass
        if result == original and ("onedrive.live.com" in original or "sharepoint.com" in original):
            result += "&download=1" if "?" in original else "?download=1"

        # 4. HuggingFace Auto-Bypass
        if result == original and "huggingface.co" in original and "/blob/" in original:
            result = original.replace("/blob/", "/resolve/")

        # 5. MediaFire Auto-Bypass
        if result == original and "mediafire.com/file/" in original:
            try:
                async with session.get(original, allow_redirects=True) as r:
                    html_text = await r.text(errors='ignore')
                    m = re.search(r'href="(https?://download[^"]+)"\s+id="downloadButton"', html_text, re.I)
                    if m:
                        result = m.group(1)
            except Exception as exc:
                logger.warning(f"Mediafire resolve failed: {exc}")

        # 6. Google Drive Auto-Bypass (Native Virus-Scan Bypasser)
        if result == original:
            gdrive_match = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?id=)([a-zA-Z0-9_-]+)", original)
            if gdrive_match:
                file_id = gdrive_match.group(1)
                scan_url = f"https://drive.google.com/uc?id={file_id}&export=download"
                try:
                    # Natively fetch the Google Drive confirm token to bypass the Large File warning
                    async with session.get(scan_url, allow_redirects=True) as r:
                        text = await r.text(errors='ignore')
                        confirm_match = re.search(r"confirm=([a-zA-Z0-9_-]+)", text)
                        if confirm_match:
                            result = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={confirm_match.group(1)}"
                        elif "download_warning" in str(r.url):
                            # 🟢 FIX: GDrive changed warning page URL structure!
                            m = re.search(r"confirm=([a-zA-Z0-9_-]+)", str(r.url))
                            if m:
                                result = f"https://drive.google.com/uc?id={file_id}&export=download&confirm={m.group(1)}"
                            else:
                                result = f"https://drive.google.com/uc?id={file_id}&export=download&confirm=t"
                        else:
                            result = str(r.url)
                except Exception as exc:
                    logger.warning(f"GDrive native bypass failed: {exc}")
                    result = original # 🟢 FIX: Never fallback to dead workers

        # 7. GoFile API
        if result == original:
            gofile_match = re.search(r"gofile\.io/d/([a-zA-Z0-9]+)", original)
            if gofile_match:
                try:
                    # 🟢 FIX: GoFile blocks generic clients. Use Real Chrome UA!
                    g_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
                    async with session.post("https://api.gofile.io/accounts", headers=g_headers) as r:
                        token_data = await r.json(content_type=None)
                    token = ((token_data.get('data') or {}).get('token') or '').strip()
                    if token:
                        g_headers["Authorization"] = f"Bearer {token}"
                        async with session.get(
                            f"https://api.gofile.io/contents/{gofile_match.group(1)}?wt=4fd6sg89d7s6",
                            headers=g_headers,
                        ) as r:
                            data = await r.json(content_type=None)
                        for item in ((data.get('data') or {}).get('children') or {}).values():
                            if item.get('type') == 'file' and item.get('link'):
                                result = item['link']
                                break
                except Exception as exc:
                    logger.warning(f"GoFile resolve failed: {exc}")

        # 8. Buzzheavier API
        if result == original:
            buzz_match = re.search(r"buzzheavier\.com/([a-zA-Z0-9]+)", original)
            if buzz_match:
                try:
                    async with session.get(
                        original,
                        headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                        allow_redirects=True,
                    ) as r:
                        html_text = await r.text(errors='ignore')
                    patterns = [
                        r'href=["\'](https://[^"\']+\.(?:mp4|mkv|webm|m4v|mp3|m4a|flac|opus)(?:\?[^"\']*)?)["\']',
                        r'(https://[^"\']+buzzheavier[^"\']+)',
                    ]
                    for pat in patterns:
                        m = re.search(pat, html_text, re.I)
                        if m:
                            result = m.group(1).replace('&amp;', '&')
                            break
                except Exception as exc:
                    logger.warning(f"Buzzheavier resolve failed: {exc}")

        # 9. 🟢 UNIVERSAL HTML MEDIA SCRAPER (Catches VikingFile, Extralink, and hundreds of custom hosts!)
        if result == original:
            try:
                u_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"}
                async with session.get(original, headers=u_headers, allow_redirects=True) as r:
                    content_type = r.headers.get("Content-Type", "").lower()
                    if "text/html" in content_type:
                        html_text = await r.text(errors='ignore')
                        # Match 1: HTML5 Video/Source Tags
                        m = re.search(r'(?:<source[^>]+src=["\']|<video[^>]+src=["\'])(https?://[^"\']+\.(?:mp4|mkv|webm|m4v|mp3|m4a|flac|opus)(?:\?[^"\']*)?)["\']', html_text, re.I)
                        if m:
                            result = m.group(1).replace('&amp;', '&')
                        else:
                            # Match 2: Direct media links floating in hrefs
                            m = re.search(r'href=["\'](https?://[^"\']+\.(?:mp4|mkv|webm|m4v|mp3|m4a|flac|opus)(?:\?[^"\']*)?)["\']', html_text, re.I)
                            if m:
                                result = m.group(1).replace('&amp;', '&')
                    else:
                        result = str(r.url) # If it auto-redirected directly to the raw file!
            except Exception:
                pass

        # 10. Last resort: a single ranged GET resolves redirects and captures useful headers
        if result == original:
            try:
                async with session.get(
                    original,
                    headers={"Range": "bytes=0-0", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                    allow_redirects=True,
                ) as r:
                    result = str(r.url)
                    DIRECT_HEADER_CACHE[original] = {
                        "content_type": r.headers.get("Content-Type", "").split(';')[0],
                        "content_length": r.headers.get("Content-Length"),
                        "content_range": r.headers.get("Content-Range"),
                        "accept_ranges": r.headers.get("Accept-Ranges"),
                        "content_disposition": r.headers.get("Content-Disposition", ""),
                    }
            except Exception:
                result = original

        DIRECT_URL_CACHE[original] = (result, now + DIRECT_URL_CACHE_TTL)
        if len(DIRECT_URL_CACHE) > 512:
            oldest = min(DIRECT_URL_CACHE.items(), key=lambda kv: kv[1][1])[0]
            DIRECT_URL_CACHE.pop(oldest, None)
        if len(DIRECT_HEADER_CACHE) > 512:
            oldest = next(iter(DIRECT_HEADER_CACHE))
            DIRECT_HEADER_CACHE.pop(oldest, None)
        return result

async def _direct_upstream_request(url, request):
    """Open a direct HTTP source through the shared keep-alive session."""
    resolved = await resolve_direct_link(url)
    session = await _get_direct_http_session()
    
    from urllib.parse import urlparse
    
    # 🟢 FIX: Mimic a real browser precisely to bypass Cloudflare Worker 502/403s!
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.5",
        "Sec-Fetch-Dest": "video",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }
    
    for header in (
        "Range", "If-Range", "If-Modified-Since", "If-None-Match", "Cookie"
    ):
        value = request.headers.get(header)
        if value:
            req_headers[header] = value

    # Smart Referer & Origin Injection for Worker Bypasses
    client_referer = request.headers.get("Referer")
    if client_referer:
        req_headers["Referer"] = client_referer
    else:
        parsed_res = urlparse(resolved)
        req_headers["Referer"] = f"{parsed_res.scheme}://{parsed_res.netloc}/"
        req_headers["Origin"] = f"{parsed_res.scheme}://{parsed_res.netloc}"

    resp = await session.request(
        method=request.method,
        url=resolved,
        headers=req_headers,
        allow_redirects=True,
    )
    
    # Log upstream worker errors for debugging
    if resp.status in (502, 503, 403):
        logger.warning(f"⚠️ Upstream {resp.status} Error from {resolved[:80]}")
        
    return session, resp, resolved

# --- GLOBAL NETWORK TRACKER ---
GLOBAL_NETWORK_STATS = {"active": {}, "recent": []}

def _track_stream(req, fname, uid):
    sid = uuid.uuid4().hex
    ip = req.headers.get("X-Forwarded-For", req.remote).split(",")[0].strip()
    ua = req.headers.get("User-Agent", "")
    br = "App"
    if "VLC" in ua: br = "VLC"
    elif "mpv" in ua: br = "MPV"
    elif "Chrome" in ua: br = "Chrome"
    elif "Safari" in ua and "Chrome" not in ua: br = "Safari"
    elif "Firefox" in ua: br = "Firefox"
    osn = "Device"
    if "Windows" in ua: osn = "Windows"
    elif "Mac OS" in ua: osn = "macOS"
    elif "Android" in ua: osn = "Android"
    elif "iPhone" in ua or "iPad" in ua: osn = "iOS"
    elif "Linux" in ua: osn = "Linux"
    GLOBAL_NETWORK_STATS["active"][sid] = {
        "ip": ip, "country": req.headers.get("CF-IPCountry", "Unknown"), 
        "device": f"{br} • {osn}", "filename": fname, 
        "start_time": time.time(), "user_id": uid
    }
    return sid

def _untrack_stream(sid):
    if sid in GLOBAL_NETWORK_STATS["active"]:
        entry = GLOBAL_NETWORK_STATS["active"].pop(sid)
        entry["end_time"] = time.time()
        GLOBAL_NETWORK_STATS["recent"].insert(0, entry)
        if len(GLOBAL_NETWORK_STATS["recent"]) > 50: 
            GLOBAL_NETWORK_STATS["recent"].pop()

async def _api_direct_stream_handler(request):
    """Native direct-link proxy with full HTTP Range support, keep-alive reuse, and STORED ZIP resolution."""
    url = request.query.get("url", "").strip()
    logger.info(f"🌐 [DIRECT STREAM] Proxying {request.method} request for: {url[:100]}...")
    if not url or not url.lower().startswith(("http://", "https://")):
        return web.Response(status=400, text="Invalid direct media URL")

    resolved = await resolve_direct_link(url)
    filename = _guess_filename_from_url(resolved, "direct_media").lower()
    is_zip = filename.endswith(".zip") or ".zip." in filename
    
    session = await _get_direct_http_session()
    virtual_size = -1
    virtual_data_offset = 0
    mime_type = None

    # [STORED ZIP RESOLUTION] - Maps HTTP bytes to absolute payload boundaries
    zip_idx = request.query.get("zip_idx", "")
    if is_zip:
        try:
            async with session.head(resolved, allow_redirects=True) as h_resp:
                raw_size = int(h_resp.headers.get("Content-Length", 0))
            
            if raw_size > 0:
                async def zip_read_http(off, length):
                    headers = {"Range": f"bytes={off}-{off+length-1}", "User-Agent": "Mozilla/5.0"}
                    async with session.get(resolved, headers=headers) as r:
                        return await r.read()
                        
                playlist = await get_zip_playlist(zip_read_http, raw_size)
                if playlist:
                    target_entry = playlist[0]
                    if zip_idx.isdigit():
                        for track in playlist:
                            if track["original_index"] == int(zip_idx):
                                target_entry = track
                                break
                    entry = await resolve_specific_zip_entry(zip_read_http, target_entry)
                    if entry:
                        virtual_size = entry["size"]
                        virtual_data_offset = entry["data_offset"]
                        mime_type = mimetypes.guess_type(entry["name"])[0] or "video/x-matroska"
        except Exception as e:
            logger.warning(f"Direct ZIP resolution failed: {e}")

    # Construct payload-aligned Range Headers
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "video/webm,video/ogg,video/*;q=0.9,application/ogg;q=0.7,audio/*;q=0.6,*/*;q=0.5",
    }
    
    client_range = request.headers.get("Range", "")
    start_byte = 0
    end_byte = None
    
    if client_range:
        match = re.match(r"bytes=(\d*)-(\d*)", client_range)
        if match:
            if match.group(1): start_byte = int(match.group(1))
            if match.group(2): end_byte = int(match.group(2))
    
    if virtual_size > 0:
        if end_byte is None or end_byte >= virtual_size:
            end_byte = virtual_size - 1
        real_start = start_byte + virtual_data_offset
        real_end = end_byte + virtual_data_offset
        req_headers["Range"] = f"bytes={real_start}-{real_end}"
    else:
        if client_range:
            req_headers["Range"] = client_range

    # Propagate necessary headers
    for header in ("If-Range", "If-Modified-Since", "If-None-Match", "Cookie", "Referer"):
        val = request.headers.get(header)
        if val: req_headers[header] = val

    try:
        remote = await session.request(
            method=request.method,
            url=resolved,
            headers=req_headers,
            allow_redirects=True,
        )
    except Exception as exc:
        return web.Response(status=502, text=f"Direct source connection failed: {exc}")

    # Stream Headers Formulation
    out_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Content-Disposition, ETag, Last-Modified, Cache-Control",
        "Cache-Control": "public, max-age=300",
        "Accept-Ranges": "bytes"
    }
    
    if virtual_size > 0:
        out_headers["Content-Type"] = mime_type
        chunk_len = end_byte - start_byte + 1
        out_headers["Content-Length"] = str(chunk_len)
        out_headers["Content-Range"] = f"bytes {start_byte}-{end_byte}/{virtual_size}"
        out_status = 206 if client_range else 200
    else:
        copy_headers = ("Content-Type", "Content-Length", "Content-Range", "Content-Disposition", "ETag", "Last-Modified")
        for k in copy_headers:
            if remote.headers.get(k) is not None:
                out_headers[k] = remote.headers[k]
        out_headers.setdefault("Content-Type", "application/octet-stream")
        out_status = remote.status

    if request.method == "HEAD":
        remote.release()
        return web.Response(status=out_status, headers=out_headers)

    response = web.StreamResponse(status=out_status, headers=out_headers)
    sid = _track_stream(request, filename, "Direct")
    try:
        await response.prepare(request)
        async for chunk in remote.content.iter_chunked(524288):
            if chunk:
                await response.write(chunk)
        await response.write_eof()
        return response
    except (ConnectionResetError, asyncio.CancelledError, aiohttp.ClientConnectionError, aiohttp.client_exceptions.ClientConnectionResetError, BrokenPipeError, ConnectionAbortedError):
        return response
    except Exception as exc:
        if "Connection closed" not in str(exc):
            logger.debug(f"Direct stream disconnect/error: {exc}")
        return response
    finally:
        _untrack_stream(sid)
        try:
            remote.release()
        except Exception:
            try: remote.close()
            except: pass

MEDIA_META_CACHE = {}
MEDIA_META_TTL = 600
MEDIA_META_LOCKS = defaultdict(asyncio.Lock)


def _media_cache_key(user_id, link):
    return f"{user_id}:{link.strip()}"


def _guess_filename_from_url(url, fallback="Direct_Stream_Media"):
    from urllib.parse import urlparse, parse_qsl, unquote
    import os
    try:
        parsed = urlparse(url)
        # 1. Check query params for explicit file names (Fixes "?path=" or "?filename=")
        qs = dict(parse_qsl(parsed.query))
        for k in ['filename', 'name', 'file', 'title', 'path']:
            if k in qs:
                val = unquote(qs[k])
                name = os.path.basename(val)
                if name and "." in name:
                    return name
                elif val and "/" not in val:
                    return val
        
        # 2. Fallback to standard URL path
        name = os.path.basename(parsed.path)
        name = unquote(name) if name else fallback
        
        # 3. Ignore extremely generic fallback names and force FFprobe to do the work later
        if name.lower() in ["download", "video", "media", "stream", "file", "play", fallback.lower()]:
            return fallback
            
        return name
    except Exception:
        return fallback

def _guess_browser_compatibility(mime_type, filename, streams):
    """Conservative browser-compatibility check used by the native player path."""
    mime = (mime_type or "").lower().split(";", 1)[0]
    ext = Path(str(filename or "")).suffix.lower()
    # 🟢 FIX: Ignore cover art so audio files aren't mistakenly treated as videos
    videos = [s for s in (streams or []) if s.get("codec_type") == "video" and s.get("codec_name") not in {"mjpeg", "png", "bmp", "webp"}]
    audios = [s for s in (streams or []) if s.get("codec_type") == "audio"]
    vc = str(videos[0].get("codec_name") if videos else "").lower()
    ac = str(audios[0].get("codec_name") if audios else "").lower()

    # These audio codecs are deliberately kept off the native browser path.
    # They need the compatibility/FFmpeg route for reliable playback.
    bad_audio = {"dts", "truehd", "ac3", "eac3"}

    # Standalone audio: preserve the original stream whenever its codec/MIME
    # is something the browser can consume.
    if not videos:
        if mime in {
            "audio/mpeg", "audio/mp4", "audio/m4a", "audio/aac", "audio/ogg",
            "audio/webm", "audio/wav", "audio/flac", "audio/opus", "audio/x-m4a"
        } or ext in {".m4a", ".mp3", ".aac", ".ogg", ".wav", ".flac", ".opus", ".mka", ".alac"}:
            return ac not in {"dts", "truehd", "ac3", "eac3"}
        return ac in {
            "mp3", "aac", "flac", "opus", "vorbis",
            "pcm_s16le", "pcm_s24le", "pcm_s32le",
            "pcm_s16be", "pcm_s24be", "pcm_s32be",
            "alac", "wavpack"
        }

    # WebM native route.
    if mime == "video/webm" or ext == ".webm":
        return vc in {"vp8", "vp9", "av1"} and ac not in bad_audio

    # MP4/M4V native route. H.264/VP9/AV1 are allowed here; the
    # browser-side player separately remains conservative about audio.
    if ext in {".mp4", ".m4v"} or mime in {"video/mp4", "application/mp4"}:
        # 🟢 FIX 1: Removed 'hevc', 'h265', 'hvc1'. Chrome/Firefox/Android CANNOT play HEVC natively!
        return vc in {
            "h264", "avc", "avc1", "vp9", "av1"
        } and ac not in bad_audio

    return False

async def _run_ffprobe_json(input_url, fast=True):
    """Fast probe first; retry with a larger probe only when the small probe fails."""
    probe_pairs = ((10 * 1024 * 1024, 5 * 1024 * 1024), (50 * 1024 * 1024, 25 * 1024 * 1024)) if fast else ((50 * 1024 * 1024, 25 * 1024 * 1024),)
    last_error = None
    for probesize, analyzeduration in probe_pairs:
        cmd = [
            "ffprobe", "-v", "error", "-hide_banner",
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", # 🟢 FIX: Real User-Agent
            "-rw_timeout", "120000000", # 🟢 FIX: 120s timeout for slow Cloudflare Workers
            "-probesize", str(probesize),
            "-analyzeduration", str(analyzeduration),
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,channels,channel_layout:"
            "stream_tags=language,title,handler_name:stream_disposition=default,forced",
            "-of", "json", input_url,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                cmd[0], *cmd[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return json.loads(stdout.decode('utf-8', errors='ignore') or '{}')
            last_error = stderr.decode('utf-8', errors='ignore').strip() or 'ffprobe failed'
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or 'ffprobe failed')

# ------------------------------------------------------------------------------
# Telegram access/pool cache. This avoids probing every bot for every Range
# request while still allowing automatic fallback to the logged-in user session.
# ------------------------------------------------------------------------------
TG_ACCESS_CACHE = {}
TG_ACCESS_CACHE_TTL = 120
TG_ACCESS_LOCKS = defaultdict(asyncio.Lock)


def _tg_client_cache_name(client):
    return str(getattr(client, "name", None) or id(client))


async def _get_user_stream_client(user_id):
    """Return the single persistent user session used as Telegram streaming fallback."""
    uclient = USER_CLIENTS.get(user_id)
    if uclient and getattr(uclient, "is_connected", False):
        return uclient, False

    session_str = await db.get_session(user_id)
    if not session_str:
        return None, False
    api_id = await db.get_api_id(user_id) or API_ID
    api_hash = await db.get_api_hash(user_id) or API_HASH
    try:
        uclient = Client(
            f"User_{user_id}",
            session_string=session_str,
            api_id=api_id,
            api_hash=api_hash,
            workers=4,
            no_updates=True,
            ipv6=False,
        )
        await uclient.start()
        USER_CLIENTS[user_id] = uclient
        return uclient, False
    except Exception as exc:
        logger.warning(f"User streaming session start failed: {exc}")
        return None, False


async def _probe_tg_client(client, chat_id, msg_id):
    try:
        await get_client_msg(client, chat_id, msg_id)
        return client
    except Exception as e:
        err_str = str(e).lower()
        
        # 🟢 FIX: Removed the bot_token restriction! Now, if there are no worker bots, 
        # the User Session is also allowed to do a quick 5-chat scan to find newly forwarded channels.
        if any(err in err_str for err in ["peer_id_invalid", "channel_invalid", "channel_private", "keyerror"]):
            try:
                logger.debug(f"Client {getattr(client, 'name', 'session')} missing peer {chat_id}. Forcing quick dialog scan...")
                # Scan only the absolute most recent dialogs (Safe for User Sessions too)
                async for _ in client.get_dialogs(limit=5):
                    pass
                # Retry fetching the message
                await get_client_msg(client, chat_id, msg_id)
                logger.info(f"✅ Client {getattr(client, 'name', 'session')} successfully resolved {chat_id} after scan.")
                return client
            except Exception as inner_e:
                logger.debug(f"Client {getattr(client, 'name', 'session')} still failed after scan: {inner_e}")
                pass
        return None

async def _get_working_tg_pool(user_id, chat_id, msg_id, fallback_client=None):
    """Return accessible bot clients first, then one user-session fallback. Strictly scoped to user_id."""
    key = (user_id, chat_id, int(msg_id))
    cached = TG_ACCESS_CACHE.get(key)
    now = time.time()
    if cached and cached[1] > now:
        pool = [c for c in cached[0] if getattr(c, "is_connected", True)]
        if pool:
            return pool, False

    lock = TG_ACCESS_LOCKS[key]
    async with lock:
        cached = TG_ACCESS_CACHE.get(key)
        if cached and cached[1] > time.time():
            pool = [c for c in cached[0] if getattr(c, "is_connected", True)]
            if pool:
                return pool, False

        candidates = []
        seen = set()
        
        # Use ONLY this specific user's worker bots! Ignored main app bot for privacy.
        user_worker_bots = list(USER_WORKER_BOTS.get(user_id, []))
        
        for client in user_worker_bots:
            if client is None:
                continue
                
            # 🟢 FIX: Properly refresh bot connections if they disconnected to check access correctly!
            if not getattr(client, "is_connected", False):
                try:
                    await client.connect()
                except Exception as e:
                    logger.debug(f"Worker bot refresh failed: {e}")
                    continue
                    
            marker = _tg_client_cache_name(client)
            if marker in seen:
                continue
            seen.add(marker)
            candidates.append(client)

        pool = []
        if candidates:
            results = await asyncio.gather(
                # 🟢 FIX: Increased timeout to 20s. If a bot needs to fetch dialogs, 
                # it needs enough time to finish before being marked as 'failed'.
                *[asyncio.wait_for(_probe_tg_client(c, chat_id, msg_id), timeout=20.0) for c in candidates],
                return_exceptions=True,
            )
            for result in results:
                if result is not None and not isinstance(result, Exception):
                    pool.append(result)

        if pool:
            TG_ACCESS_CACHE[key] = (pool, time.time() + TG_ACCESS_CACHE_TTL)
            return pool, False

        # 🟢 FIX: If the user has worker bots configured, DO NOT fallback to the user session for streaming!
        # The user session should ONLY be used if the user hasn't provided any bot tokens.
        if user_worker_bots:
             logger.warning(f"All worker bots failed to access {chat_id}. Blocking fallback to prevent User Session FloodWaits.")
             return [], False

        if fallback_client is not None and getattr(fallback_client, "is_connected", False):
            user_client = fallback_client
        else:
            user_client, _ = await _get_user_stream_client(user_id)

        if user_client is not None:
            if await _probe_tg_client(user_client, chat_id, msg_id):
                TG_ACCESS_CACHE[key] = ([user_client], time.time() + 30)
                return [user_client], True

        return [], False

async def _invalidate_tg_access(user_id, chat_id, msg_id, client=None):
    key = (user_id, chat_id, int(msg_id))
    cached = TG_ACCESS_CACHE.get(key)
    if not cached:
        return
    if client is None:
        TG_ACCESS_CACHE.pop(key, None)
        return
    pool = [c for c in cached[0] if c is not client]
    if pool:
        TG_ACCESS_CACHE[key] = (pool, time.time() + min(TG_ACCESS_CACHE_TTL, 30))
    else:
        TG_ACCESS_CACHE.pop(key, None)


async def _api_media_probe_handler(request):
    """Metadata probe with caching and fast native-path friendly fallbacks."""
    try:
        user_id = int(request.query.get("user_id", 0))
    except Exception:
        user_id = 0
    link = request.query.get("link", "").strip()
    if not link:
        return web.json_response({"status": "error", "message": "Link required"}, status=400)

    cache_key = _media_cache_key(user_id, link)
    cached = MEDIA_META_CACHE.get(cache_key)
    if cached and cached[1] > time.time():
        return web.json_response(cached[0])

    lock = MEDIA_META_LOCKS[cache_key]
    async with lock:
        cached = MEDIA_META_CACHE.get(cache_key)
        if cached and cached[1] > time.time():
            return web.json_response(cached[0])

        is_tg = _is_tg_link(link)
        logger.info(f"🔎 [PROBE] Starting probe | User: {user_id} | Is TG: {is_tg} | Link: {link[:100]}...")
        
        actual_url = link
        real_file_name = "Unknown_Media"
        mime_type = "video/mp4"
        streams = []
        duration_val = 0.0

        try:
            if is_tg:
                parsed = _parse_source_link(link)
                chat_id = parsed.get("chat_id")
                msg_id = parsed.get("msg_id")
                msg_range = parsed.get("msg_range") # 🟢 Extract range
                if chat_id is None or msg_id is None:
                    return web.json_response({"status": "error", "message": "Invalid Telegram link"}, status=400)
                pool, user_fallback = await _get_working_tg_pool(user_id, chat_id, msg_id)
                if not pool:
                    return web.json_response({"status": "error", "message": "Telegram file is not accessible"}, status=403)
                msg = await get_client_msg(pool[0], chat_id, msg_id)
                media = msg.document or msg.video or msg.audio
                if not media:
                    return web.json_response({"status": "error", "message": "No media found"}, status=404)
                real_file_name = getattr(media, "file_name", None) or getattr(media, "title", None) or f"Telegram_Media_{msg_id}"
                mime_type = getattr(media, "mime_type", None) or "video/mp4"
                actual_url = f"http://127.0.0.1:{PORT}/api/tg_stream?user_id={user_id}&chat_id={chat_id}&msg_id={msg_id}"
                if msg_range:
                    actual_url += f"&range={msg_range[0]}-{msg_range[1]}" # 🟢 Send to stream backend
            else:
                actual_url = await resolve_direct_link(link)
                real_file_name = _guess_filename_from_url(actual_url, _guess_filename_from_url(link, "Direct_Stream_Media"))
                cached_headers = DIRECT_HEADER_CACHE.get(link) or DIRECT_HEADER_CACHE.get(actual_url)
                if cached_headers:
                    mime_type = cached_headers.get("content_type") or mime_type
                    cd = cached_headers.get("content_disposition", "")
                    if cd:
                        m = re.search(r"filename\*=UTF-8''([^;]+)", cd, re.I) # 🟢 FIX: Better Regex for RFC 5987
                        if m:
                            real_file_name = unquote(m.group(1).strip().strip('"'))
                        else:
                            m = re.search(r'filename=["\']?([^"\';]+)', cd, re.I) # 🟢 FIX: Catches all standard filename headers
                            if m:
                                real_file_name = unquote(m.group(1).strip())

            probe_input = actual_url
            if not is_tg:
                # 🟢 Restoring Loopback for Direct Links to prevent strict 5XX server blocks
                probe_input = f"http://127.0.0.1:{PORT}/api/direct_stream?user_id={user_id}&url={quote(actual_url, safe='')}"
                logger.debug(f"🔎 [PROBE] Feeding Loopback Proxy to FFprobe: {probe_input[:100]}...")

            tg_duration = 0.0
            if is_tg and 'media' in locals() and media:
                tg_duration = float(getattr(media, "duration", 0) or 0)
                if tg_duration > 0:
                    duration_val = tg_duration
                    logger.info(f"🔎 [PROBE TG] Found Telegram native duration: {duration_val}s")

            try:
                pdata = await _run_ffprobe_json(probe_input, fast=True)
                streams = pdata.get("streams", []) or []
                if duration_val <= 0:
                    try:
                        duration_val = float((pdata.get("format") or {}).get("duration", 0) or 0)
                    except Exception:
                        duration_val = 0.0
                        
                # 🟢 NEW FIX: Attempt to extract real title from ffprobe metadata if filename is generic
                if not is_tg and real_file_name in ("Direct_Stream_Media", "download", "video", "media", "file"):
                    format_tags = pdata.get("format", {}).get("tags", {})
                    title_tag = format_tags.get("title") or format_tags.get("TITLE")
                    if title_tag:
                        ext = ""
                        if "video" in mime_type: ext = ".mp4"
                        elif "audio" in mime_type: ext = ".mp3"
                        real_file_name = title_tag if "." in title_tag else title_tag + ext

                logger.info(f"🔎 [PROBE HTTP] Success! Streams found: {len(streams)}, Duration: {duration_val}s")
            except Exception as probe_exc:
                logger.warning(f"🔎 [PROBE HTTP] Loopback HTTP probe failed: {probe_exc}")
                streams = []

            # 🟢 MKV SPARSE PROBE FALLBACK: If HTTP probe returned no streams for a Telegram file,
            # sample the head & tail directly into a small temp file (just like /mediainfo)
            if not streams and is_tg and 'pool' in locals() and pool and 'msg' in locals() and msg:
                logger.info("🔎 [PROBE TG] Falling back to fast local sparse-file probe for MKV/Telegram...")
                temp_probe = Path(f"./probe_{user_id}_{int(time.time())}.dat")
                temp_named = None
                try:
                    await partial_download_tg(pool[0], msg, temp_probe, limit_mb=8)
                    real_ext = Path(real_file_name).suffix or ".mkv"
                    temp_named = temp_probe.with_suffix(real_ext)
                    temp_probe.rename(temp_named)
                    pdata = await _run_ffprobe_json(str(temp_named), fast=False)
                    streams = pdata.get("streams", []) or []
                    if duration_val <= 0:
                        duration_val = float((pdata.get("format") or {}).get("duration", 0) or 0)
                    logger.info(f"🔎 [PROBE TG] Local sparse probe succeeded: {len(streams)} streams found, Duration: {duration_val}s")
                except Exception as sparse_err:
                    logger.error(f"🔎 [PROBE TG] Local sparse probe failed: {sparse_err}", exc_info=True)
                finally:
                    for p in [temp_probe, temp_named]:
                        if p and p.exists():
                            try: os.remove(p)
                            except Exception: pass

            # 🟢 Extract duration from stream DURATION tags if still not detected
            if duration_val <= 0:
                for s in streams:
                    tags = s.get("tags", {}) or {}
                    tag_dur = tags.get("DURATION") or tags.get("duration")
                    if tag_dur:
                        try:
                            parts = str(tag_dur).split(':')
                            if len(parts) >= 3:
                                h, m, sec = float(parts[0]), float(parts[1]), float(parts[2])
                                duration_val = (h * 3600) + (m * 60) + sec
                                if duration_val > 0:
                                    logger.info(f"🔎 [PROBE] Extracted duration from stream tag: {duration_val}s")
                                    break
                        except Exception: pass

            if duration_val <= 0 and tg_duration > 0:
                duration_val = tg_duration

            # 🟢 FIX: Separate Video streams from Cover Art streams!
            videos = [s for s in streams if s.get("codec_type") == "video" and s.get("codec_name") not in {"mjpeg", "png", "bmp", "webp"}]
            covers = [s for s in streams if s.get("codec_type") == "video" and s.get("codec_name") in {"mjpeg", "png", "bmp", "webp"}]
            audios = [s for s in streams if s.get("codec_type") == "audio"]
            
            # 🟢 CRITICAL FIX: Filter out image-based subtitles (PGS, VobSub) because FFmpeg cannot convert them!
            valid_sub_codecs = {"subrip", "ass", "ssa", "webvtt", "mov_text"}
            subs = [s for s in streams if s.get("codec_type") == "subtitle" and s.get("codec_name") in valid_sub_codecs]
            filename_lower = str(real_file_name).lower()
            is_audio = bool(audios and not videos) or filename_lower.endswith((
                ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac", ".opus"
            ))

            qualities = ["Original"]
            if not is_audio:
                height = int((videos[0].get("height") or 0)) if videos else 0
                width = int((videos[0].get("width") or 0)) if videos else 0
                if height >= 2160 or width >= 3840:
                    qualities.extend(["4K", "1080p", "720p", "480p", "360p"])
                elif height >= 1080 or width >= 1920:
                    qualities.extend(["1080p", "720p", "480p", "360p"])
                elif height >= 720:
                    qualities.extend(["720p", "480p", "360p"])
                elif height >= 480:
                    qualities.extend(["480p", "360p"])
                else:
                    qualities.append("360p")

            audio_tracks = []
            for i, st in enumerate(audios):
                tags = st.get("tags", {}) or {}
                lang = tags.get("language") or tags.get("LANGUAGE")
                # Removed 'handler_name' fallback so it doesn't show 'SoundHandler'
                title = tags.get("title") or tags.get("TITLE")
                audio_tracks.append({
                    "index": st.get("index"),
                    "label": title or lang or f"Track {i+1}",
                    "language": lang or "",
                    "channels": st.get("channels") or 0,
                    "codec_name": st.get("codec_name") or "",
                })

            subtitles = []
            for i, st in enumerate(subs):
                tags = st.get("tags", {}) or {}
                lang = tags.get("language") or tags.get("LANGUAGE")
                # Removed 'handler_name' fallback so it doesn't show 'SubtitleHandler'
                title = tags.get("title") or tags.get("TITLE")
                subtitles.append({
                    "index": st.get("index"),
                    "label": title or lang or f"Subtitle {i+1}",
                    "language": lang or "",
                })

            video_codec = (videos[0].get("codec_name") if videos else "").lower()
            audio_codec = (audios[0].get("codec_name") if audios else "").lower()
            browser_compatible = _guess_browser_compatibility(mime_type, real_file_name, streams)
            if not streams:
                ext = Path(filename_lower).suffix
                mime_guess = mime_type.lower().split(';')[0]
                browser_compatible = (
                    ext in {".mp4", ".m4v", ".webm", ".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac", ".opus"}
                    or mime_guess in {
                        "video/mp4", "video/webm", "application/mp4", "audio/mpeg", "audio/mp4",
                        "audio/aac", "audio/ogg", "audio/webm", "audio/wav", "audio/flac", "audio/opus"
                    }
                )

            result = {
                "status": "success",
                "file_name": real_file_name,
                "mime_type": mime_type,
                "requires_transcode": not browser_compatible,
                "browser_compatible": browser_compatible,
                "has_cover": len(covers) > 0, # 🟢 NEW: Send flag to Javascript player
                "video_codec": video_codec,
                "audio_codec": audio_codec,
                "video_width": int(videos[0].get("width") or 0) if videos else 0,
                "video_height": int(videos[0].get("height") or 0) if videos else 0,
                "duration": duration_val,
                "qualities": list(OrderedDict.fromkeys(qualities)),
                "audio_tracks": audio_tracks,
                "subtitles": subtitles,
                "resolved_url": actual_url if not is_tg else "",
                "streams": streams,
            }
            MEDIA_META_CACHE[cache_key] = (result, time.time() + MEDIA_META_TTL)
            if len(MEDIA_META_CACHE) > 512:
                oldest = min(MEDIA_META_CACHE.items(), key=lambda kv: kv[1][1])[0]
                MEDIA_META_CACHE.pop(oldest, None)
            return web.json_response(result)
        except Exception as exc:
            logger.exception("Media probe failed")
            return web.json_response({"status": "error", "message": str(exc)}, status=502)

async def _api_cover_handler(request):
    """Extracts embedded Album Art/Cover Art from audio files on the fly."""
    try:
        user_id = int(request.query.get("user_id", 0))
    except:
        user_id = 0
    link = request.query.get("link", "").strip()
    if not link:
        return web.Response(status=400, text="No link provided")

    is_tg = _is_tg_link(link)
    actual_url = link

    try:
        if is_tg:
            parsed = _parse_source_link(link)
            chat_id = parsed.get("chat_id")
            msg_id = parsed.get("msg_id")
            actual_url = f"http://127.0.0.1:{PORT}/api/tg_stream?user_id={user_id}&chat_id={chat_id}&msg_id={msg_id}"
        else:
            actual_url = await resolve_direct_link(link)

        # Grabs the exact cover frame directly from the media container
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", actual_url,
            "-map", "0:v:0",
            "-vframes", "1", "-c:v", "mjpeg", "-f", "image2", "pipe:1"
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode == 0 and stdout:
            return web.Response(body=stdout, content_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
        else:
            return web.Response(status=404, text="No cover found")
    except Exception as e:
        return web.Response(status=500, text=str(e))

async def _api_stream_handler(request):
    """Adaptive stream pipeline: native redirect first, minimal FFmpeg fallback."""
    try:
        user_id = int(request.query.get("user_id", 0))
    except Exception:
        user_id = 0
    link = request.query.get("link", "")
    quality = request.query.get("quality", "Original")
    audio_idx = request.query.get("audio_idx", None)
    audio_codec = request.query.get("audio_codec", "").lower().strip()
    start_time = request.query.get("start", None)
    force_transcode = request.query.get("transcode", "") in ("1", "true")
    force_x264 = request.query.get("force_x264", "") == "1" # 🟢 NEW FLAG
    if not link:
        return web.Response(status=400, text="No link provided")

    is_tg = _is_tg_link(link)
    logger.info(f"🎬 [TRANSCODE] Request | User: {user_id} | Is TG: {is_tg} | Link: {link[:100]}...")
    
    actual_url = link
    mime_type = "video/mp4"
    filename = "media"
    is_audio = False

    try:
        if is_tg:
            parsed = _parse_source_link(link)
            chat_id = parsed.get("chat_id")
            msg_id = parsed.get("msg_id")
            msg_range = parsed.get("msg_range") # 🟢 Extract range
            if chat_id is None or msg_id is None:
                return web.Response(status=400, text="Invalid Telegram link")
            pool, _ = await _get_working_tg_pool(user_id, chat_id, msg_id)
            if not pool:
                return web.Response(status=403, text="Telegram source is not accessible")
            msg = await get_client_msg(pool[0], chat_id, msg_id)
            media = msg.document or msg.video or msg.audio
            if not media:
                return web.Response(status=404, text="Media not found")
            filename = str(getattr(media, 'file_name', '') or '').lower()
            mime_type = getattr(media, 'mime_type', 'video/mp4') or 'video/mp4'
            actual_url = f"http://127.0.0.1:{PORT}/api/tg_stream?user_id={user_id}&chat_id={chat_id}&msg_id={msg_id}"
            if msg_range:
                actual_url += f"&range={msg_range[0]}-{msg_range[1]}" # 🟢 Send to stream backend
            is_audio = filename.endswith((".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".wma", ".opus", ".dsf", ".ape", ".mka", ".alac")) or "audio" in mime_type
        else:
            actual_url = await resolve_direct_link(link)
            filename = _guess_filename_from_url(actual_url, "direct_media").lower()
            lower = actual_url.lower().split('?', 1)[0]
            is_audio = bool(re.search(r"\.(flac|mp3|m4a|ogg|wav|aac|wma|opus|dsf|ape|mka|alac)$", lower))
            mime_type = "audio/mpeg" if filename.endswith('.mp3') else (
                "audio/mp4" if filename.endswith(('.m4a','.aac')) else (
                    "audio/ogg" if filename.endswith('.ogg') else (
                        "audio/wav" if filename.endswith('.wav') else (
                            "audio/flac" if filename.endswith('.flac') else (
                                "audio/opus" if filename.endswith('.opus') else (
                                    "video/webm" if filename.endswith('.webm') else "video/mp4"
                                )
                            )
                        )
                    )
                )
            )
            # 🟢 CRITICAL FIX: Restore Loopback Proxy for FFmpeg!
            # FFmpeg's native HTTP client gets stuck when seeking direct links. Route through Python proxy!
            from urllib.parse import quote
            actual_url = f"http://127.0.0.1:{PORT}/api/direct_stream?user_id={user_id}&url={quote(link, safe='')}"
            logger.debug(f"🎬 [TRANSCODE] Using Local Proxy for FFmpeg: {actual_url[:100]}...")
    except Exception as exc:
        return web.Response(status=502, text=f"Source resolution failed: {exc}")

    # Always keep the browser on the byte-range path for the original/default
    # stream. FFmpeg is reserved for explicit track/quality selection or codecs
    # which the browser cannot decode directly.
    if quality == "Original" and (audio_idx is None or str(audio_idx).strip() == "") and not force_transcode:
        if is_tg:
            raise web.HTTPFound(f"/api/tg_stream?user_id={user_id}&chat_id={quote(str(chat_id), safe='')}&msg_id={msg_id}")
        raise web.HTTPFound(f"/api/direct_stream?user_id={user_id}&url={quote(link, safe='')}")

    # 🟢 DYNAMIC CODEC RETRIEVAL: Pull cached metadata to ensure we don't blind-copy incompatible streams
    cache_key = _media_cache_key(user_id, link)
    cached_meta = MEDIA_META_CACHE.get(cache_key)
    video_codec = ""
    if cached_meta:
        meta = cached_meta[0]
        if not audio_codec:
            audio_codec = meta.get("audio_codec", "").lower()
        video_codec = meta.get("video_codec", "").lower()
        
        # 🟢 FIX: Use the fully resolved filename, avoiding generics!
        if meta.get("file_name") and meta.get("file_name").lower() not in ("unknown_media", "direct_stream_media", "download", "file", "media"):
            filename = meta.get("file_name").lower()

    # 🟢 SMART COPY LOGIC: Never copy E-AC3/AC3/DTS/TrueHD into MP4 for browsers
    unsupported_web_codecs = {"hevc", "h265", "hvc1", "x265"}
    needs_video_transcode = video_codec in unsupported_web_codecs or force_x264 or quality != "Original"

    bad_audio = {"dts", "truehd", "ac3", "eac3"}
    # 🟢 FIX: If we are transcoding the video for web compatibility, we MUST also force the audio to transcode!
    # Browsers instantly crash or loop endlessly when fed 5.1/6-channel audio inside a fragmented MP4!
    if audio_codec in bad_audio or needs_video_transcode:
        copy_audio = False
    else:
        copy_audio = audio_codec in {'aac', 'mp3', 'opus', 'flac'} or (audio_idx is None and not force_transcode)
        
    if video_codec in unsupported_web_codecs:
        copy_video = False
    else:
        copy_video = quality == "Original" and not force_x264 
        
    res_scale_map = {"4K":"3840:-2", "1080p":"1920:-2", "720p":"1280:-2", "480p":"854:-2", "360p":"640:-2"}
    scale_filter = res_scale_map.get(quality)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", 
        "-rw_timeout", "120000000", 
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
        "-reconnect_at_eof", "1", "-reconnect_on_network_error", "1", 
        "-seekable", "1", 
        "-probesize", "5M", "-analyzeduration", "5M", 
        "-fflags", "+nobuffer+flush_packets+genpts" # 🟢 FIX: +genpts ensures synced timestamps, removed deprecated -async 1
    ]

    if start_time is not None:
        try:
            start_float = max(0.0, float(start_time))
            if start_float > 0:
                cmd += ["-ss", f"{start_float:.3f}"]
        except Exception:
            pass

    cmd += ["-i", actual_url]

    if is_audio:
        if audio_idx is not None and str(audio_idx).strip():
            cmd += ["-map", f"0:{audio_idx}"]
        else:
            cmd += ["-map", "0:a:0?"]
        cmd += ["-vn", "-sn"]
        
        # 🟢 FIX: Never use MP4 container for audio-only streams. Browsers wait for video frames and hang.
        # Also, explicitly map compatible codecs to their native containers to prevent FFmpeg crashes.
        if copy_audio and audio_codec == "mp3":
            cmd += ["-c:a", "copy", "-f", "mp3", "pipe:1"]
            mime_type = "audio/mpeg"
        elif copy_audio and audio_codec in {"opus", "vorbis", "ogg"}:
            cmd += ["-c:a", "copy", "-f", "ogg", "pipe:1"]
            mime_type = "audio/ogg"
        elif copy_audio and audio_codec == "flac":
            cmd += ["-c:a", "copy", "-f", "flac", "pipe:1"]
            mime_type = "audio/flac"
        elif copy_audio and audio_codec == "aac":
            cmd += ["-c:a", "copy", "-f", "adts", "pipe:1"]
            mime_type = "audio/aac"
        else:
            # 🟢 ULTIMATE FALLBACK: Transcode EVERYTHING else (ALAC, WAV, DTS, Atmos, DSF, MKA, etc.) to AAC!
            cmd += ["-c:a", "aac", "-b:a", "256k", "-ac", "2", "-f", "adts", "pipe:1"]
            mime_type = "audio/aac"
    else:
        cmd += ["-map", "0:v:0?"]
        if audio_idx is not None and str(audio_idx).strip():
            cmd += ["-map", f"0:{audio_idx}"]
        else:
            cmd += ["-map", "0:a:0?"]
        cmd += ["-sn"]

        if copy_video and not scale_filter:
            cmd += ["-c:v", "copy"]
            if video_codec in {"hevc", "h265", "hvc1"}:
                cmd += ["-tag:v", "hvc1"]
            elif video_codec in {"vp9", "vp8", "av1"}:
                cmd += ["-strict", "experimental"]
        else:
            cmd += [
                "-vf", f"scale={scale_filter or 'trunc(iw/2)*2:trunc(ih/2)*2'}",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-pix_fmt", "yuv420p", "-threads", "0",
            ]

        if copy_audio:
            cmd += ["-c:a", "copy"]
        else:
            cmd += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"] # 🟢 Downmix to Stereo for Web

        cmd += ["-avoid_negative_ts", "make_non_negative", "-max_muxing_queue_size", "9999", "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]

    logger.info(f"🎬 [STREAMING] User: {user_id} | File: {filename} | Quality: {quality} | AudioIdx: {audio_idx} | StartTime: {start_time}")
    logger.info(f"🎬 [FFMPEG CMD] {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, # 🟢 FIX: Prevents OS pipe buffer deadlock
    )
    import aiohttp
    
    # 🟢 FIX: Separate HTTP Header logic strictly for iOS/Apple devices!
    user_agent = request.headers.get("User-Agent", "").lower()
    is_apple = ("safari" in user_agent and "chrome" not in user_agent and "android" not in user_agent) or "applecoremedia" in user_agent or "macintosh" in user_agent or "iphone" in user_agent or "ipad" in user_agent

    stream_headers = {
        "Content-Type": mime_type if is_audio else "video/mp4",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-store",
    }

    apple_target_length = None
    if is_apple:
        stream_headers["Accept-Ranges"] = "bytes"
        client_range = request.headers.get("Range", "")
        if client_range:
            start_byte = 0
            end_byte = 2147483647 # Fake 2GB Maximum
            
            match = re.match(r"bytes=(\d*)-(\d*)", client_range.strip())
            if match:
                if match.group(1): start_byte = int(match.group(1))
                if match.group(2): end_byte = int(match.group(2))
                
            fake_total = 2147483648
            end_byte = min(end_byte, fake_total - 1)
            
            # Mathematical compliance for Safari's strict AVPlayer parser
            stream_headers["Content-Range"] = f"bytes {start_byte}-{end_byte}/{fake_total}"
            
            apple_target_length = end_byte - start_byte + 1
            stream_headers["Content-Length"] = str(apple_target_length)
            status_code = 206
        else:
            stream_headers["Content-Length"] = "2147483648"
            status_code = 200
    else:
        # ULTRA-STABLE 200 OK RESPONSE FOR CHROME, ANDROID, WINDOWS
        stream_headers["Accept-Ranges"] = "none"
        status_code = 200

    response = web.StreamResponse(status=status_code, headers=stream_headers)
    sid = _track_stream(request, filename, user_id)
    try:
        await response.prepare(request)
        bytes_sent = 0
        while True:
            buf = await proc.stdout.read(262144) 
            if not buf:
                break
                
            # 🟢 FIX: If Safari only asked for a specific chunk size (e.g., 2 bytes for a probe),
            # we MUST forcefully truncate the data and close the stream. 
            # If we send more data than we promised in the Content-Length, Safari instantly kills playback!
            if is_apple and apple_target_length is not None:
                if bytes_sent + len(buf) >= apple_target_length:
                    buf = buf[:apple_target_length - bytes_sent]
                    await response.write(buf)
                    break
                    
            await response.write(buf)
            bytes_sent += len(buf)
            
        await response.write_eof()
    except (ConnectionResetError, asyncio.CancelledError, aiohttp.client_exceptions.ClientConnectionResetError):
        pass
    except Exception:
        pass
    finally:
        _untrack_stream(sid)
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass
    return response

CLIENT_MSG_CACHE = {}
CLIENT_MSG_CACHE_MAX = 2048
CLIENT_MSG_LOCKS = defaultdict(asyncio.Lock)


async def get_client_msg(client, chat_id, msg_id):
    """Cache Telegram messages and coalesce simultaneous metadata requests."""
    key = (id(client), chat_id, int(msg_id))
    cached = CLIENT_MSG_CACHE.get(key)
    if cached is not None:
        return cached
    lock = CLIENT_MSG_LOCKS[key]
    async with lock:
        cached = CLIENT_MSG_CACHE.get(key)
        if cached is not None:
            return cached
        msg = await client.get_messages(chat_id, msg_id)
        if getattr(msg, "empty", True) or not (msg.document or msg.video or msg.audio):
            raise ValueError(f"Empty Message for client {getattr(client, 'name', 'Unknown')}")
        CLIENT_MSG_CACHE[key] = msg
        if len(CLIENT_MSG_CACHE) > CLIENT_MSG_CACHE_MAX:
            try:
                CLIENT_MSG_CACHE.pop(next(iter(CLIENT_MSG_CACHE)))
            except Exception:
                pass
        return msg


async def fetch_single_chunk(client, chat_id, msg_id, offset, limit):
    """Fetches a chunk strictly. Retries on transient errors with clean byte skipping."""
    # 🟢 FIX: Universal 1MB Alignment - Rock solid for Telegram MTProto
    ALIGNMENT = 1048576
    aligned_offset = (offset // ALIGNMENT) * ALIGNMENT
    target_bytes = limit
    
    for attempt in range(6): # 🟢 INCREASED RETRIES FOR STABILITY
        # 🟢 CRITICAL FIX: Instantly revive dead worker bots if Telegram severed the socket
        if not getattr(client, "is_connected", False):
            try:
                await client.connect()
            except Exception:
                pass

        # MUST reset skip_bytes on every retry loop to prevent data corruption
        skip_bytes = offset - aligned_offset
        fetch_limit = target_bytes + skip_bytes
        try:
            msg = await get_client_msg(client, chat_id, msg_id)
            data = bytearray()
            
            # 🟢 FIX: Pass fetch_limit to let Pyrogram safely close the connection automatically
            async for chunk in client.stream_media(msg, offset=aligned_offset, limit=fetch_limit):
                if skip_bytes > 0:
                    if len(chunk) <= skip_bytes:
                        skip_bytes -= len(chunk)
                        continue
                else:
                        chunk = chunk[skip_bytes:]
                        skip_bytes = 0
                        
                data.extend(chunk)
                # Removed manual 'break' to stop severing sockets mid-stream
                    
            if not data: 
                raise ValueError("EOF Reached or Empty Chunk")
                
            return bytes(data[:target_bytes])
            
        except FloodWait as e:
            logger.warning(f"[{getattr(client, 'name', 'Client')}] Rate-limited for {e.value}s. Sleeping...")
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            logger.debug(f"Chunk fetch error on {getattr(client, 'name', 'Client')} (attempt {attempt+1}/6): {e}")
            if attempt == 5:
                raise e
            await asyncio.sleep(1.5 + attempt) # 🟢 EXPONENTIAL BACKOFF FOR TG DROPS
            
    raise TimeoutError("Exceeded max retries for chunk")

async def parallel_stream_generator(fallback_client, chat_id, msg_parts, start_byte, total_length, chunk_size=2 * 1024 * 1024, concurrency=6):
    """Fast Telegram range generator with cached client selection and split-safe work units."""
    if total_length <= 0:
        return

    user_id = 0
    # The fallback client is already scoped to the current user session when one
    # exists. Pool discovery uses app + worker bots first and falls back to that
    # user session only when no bot can read the file.
    if fallback_client in USER_CLIENTS.values():
        for uid, candidate in USER_CLIENTS.items():
            if candidate is fallback_client:
                user_id = uid
                break

    try:
        pool, is_user_session = await _get_working_tg_pool(user_id, chat_id, msg_parts[0]["msg_id"], fallback_client=fallback_client)
    except Exception:
        pool, is_user_session = ([fallback_client] if fallback_client else [app]), bool(fallback_client and fallback_client is not app)

    if not pool:
        pool = [fallback_client or app]
        is_user_session = bool(fallback_client and fallback_client is not app)

    if is_user_session:
        safe_concurrency = 1
    else:
        requested = max(1, int(os.environ.get("TG_STREAM_CONCURRENCY", str(concurrency))))
        safe_concurrency = min(requested, len(pool))

    # Build precise units that never cross split-file boundaries.
    range_start = int(start_byte)
    range_end = range_start + int(total_length)
    units = []
    for part in msg_parts:
        p_start = int(part["start"])
        p_end = int(part["end"])
        if p_end <= range_start or p_start >= range_end:
            continue
        cursor = max(range_start, p_start)
        limit_end = min(range_end, p_end)
        while cursor < limit_end:
            take = min(int(chunk_size), limit_end - cursor)
            units.append((part, cursor - p_start, take))
            cursor += take

    if not units:
        return

    if safe_concurrency == 1:
        client = pool[0]
        for part, internal_offset, internal_limit in units:
            try:
                yield await fetch_single_chunk(client, chat_id, part["msg_id"], internal_offset, internal_limit)
            except Exception:
                await _invalidate_tg_access(chat_id, part["msg_id"], client)
                raise
        return

    # Multi-bot path. Each batch is fetched in parallel but yielded in source
    # order so the HTTP byte stream remains perfectly ordered.
    cursor = 0
    while cursor < len(units):
        batch = units[cursor:cursor + safe_concurrency]

        async def _fetch_with_failover(unit_idx, unit):
            part, internal_offset, internal_limit = unit
            preferred = pool[unit_idx % len(pool)]
            candidates = [preferred] + [c for c in pool if c is not preferred]
            last_exc = None
            for client in candidates:
                try:
                    return await fetch_single_chunk(client, chat_id, part["msg_id"], internal_offset, internal_limit)
                except Exception as exc:
                    last_exc = exc
                    await _invalidate_tg_access(chat_id, part["msg_id"], client)
            raise last_exc or RuntimeError("Telegram chunk fetch failed")

        results = await asyncio.gather(
            *[_fetch_with_failover(i, unit) for i, unit in enumerate(batch)],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                raise result
            if result:
                yield result
        cursor += len(batch)

async def _api_tg_stream_handler(request):
    """High-speed Telegram Range proxy with multi-bot routing, user fallback, split files and ZIP extraction."""
    try:
        user_id = int(request.query.get("user_id", 0))
    except Exception:
        user_id = 0

    link = request.query.get("link")
    logger.info(f"🌐 [TG STREAM] Native Byte-Range Request | User: {user_id} | Link: {str(link)[:60]}...")
    msg_range = None
    if link:
        parsed = _parse_source_link(link)
        chat_id = parsed.get("chat_id")
        msg_id = parsed.get("msg_id")
        msg_range = parsed.get("msg_range")
    else:
        chat_id = request.query.get("chat_id")
        msg_id = request.query.get("msg_id")
        range_spec = request.query.get("range", "")
        if range_spec:
            rm = re.match(r"^(\d+)-(\d+)$", range_spec)
            if rm: msg_range = (int(rm.group(1)), int(rm.group(2)))

    if chat_id is None or msg_id is None:
        return web.Response(status=400, text="Missing chat_id/msg_id or link")

    msg_id = int(msg_id)
    chat_id = int(chat_id) if str(chat_id).lstrip('-').isdigit() else chat_id

    response = None
    temp_client = None
    try:
        working_pool, using_user_session = await _get_working_tg_pool(user_id, chat_id, msg_id)
        if not working_pool:
            return web.Response(status=403, text="Telegram file is not accessible")
        primary_client = working_pool[0]

        msg = await get_client_msg(primary_client, chat_id, msg_id)
        media = msg.document or msg.video or msg.audio
        if not media:
            return web.Response(status=404)

        filename = str(getattr(media, "file_name", "") or "").lower()
        mime_type = getattr(media, "mime_type", "application/octet-stream") or "application/octet-stream"

        parts_map = []
        global_offset = 0

        # 🟢 FIX: Directly utilize the perfectly parsed msg_range for seamless multi-part chunking!
        if msg_range:
            start_id, end_id = msg_range[0], msg_range[1]
            for mid in range(start_id, end_id + 1):
                try:
                    m = await get_client_msg(primary_client, chat_id, mid)
                    doc = m.document or m.video or m.audio
                    if doc:
                        psz = int(doc.file_size or 0)
                        if psz > 0:
                            parts_map.append({"msg_id": m.id, "start": global_offset, "end": global_offset + psz, "size": psz})
                            global_offset += psz
                except Exception:
                    continue
        else:
            match = re.search(r'\.(\d{2,3})$', filename)
            if match and int(match.group(1)) == 1:
                current_id = msg_id
                while True:
                    try:
                        m = await get_client_msg(primary_client, chat_id, current_id)
                        doc = m.document or m.video
                        if not doc:
                            break
                        psz = int(doc.file_size or 0)
                        parts_map.append({"msg_id": m.id, "start": global_offset, "end": global_offset + psz, "size": psz})
                        global_offset += psz
                        current_id += 1
                        next_m = await get_client_msg(primary_client, chat_id, current_id)
                        next_doc = next_m.document or next_m.video
                        if not next_doc or not re.search(r'\.\d{2,3}$', next_doc.file_name or ""):
                            break
                    except Exception:
                        break
            else:
                part_size = int(getattr(media, "file_size", 0) or 0)
                if part_size <= 0:
                    return web.Response(status=502, text="Telegram media has no usable file size")
                parts_map.append({"msg_id": msg_id, "start": 0, "end": part_size, "size": part_size})
                global_offset = part_size

        if not parts_map:
            return web.Response(status=404, text="No readable media parts")

        virtual_size = global_offset
        virtual_data_offset = 0
        zip_idx = request.query.get("zip_idx", "")
        is_zip = filename.endswith(".zip") or ".zip." in filename
        if is_zip:
            async def zip_read(off, length):
                buf = bytearray()
                async for chunk in parallel_stream_generator(primary_client, chat_id, parts_map, off, length, concurrency=6):
                    buf.extend(chunk)
                    if len(buf) >= length:
                        break
                return bytes(buf[:length])

            playlist = await get_zip_playlist(zip_read, virtual_size)
            if playlist:
                target_entry = playlist[0]
                if zip_idx.isdigit():
                    for track in playlist:
                        if track["original_index"] == int(zip_idx):
                            target_entry = track
                            break
                entry = await resolve_specific_zip_entry(zip_read, target_entry)
                if entry:
                    virtual_size = entry["size"]
                    virtual_data_offset = entry["data_offset"]
                    mime_type = mimetypes.guess_type(entry["name"])[0] or "video/x-matroska"
                    filename = entry["name"]

        if virtual_size <= 0:
            return web.Response(status=502, text="Invalid virtual media size")

        range_header = request.headers.get("Range", "")
        start_byte = 0
        end_byte = virtual_size - 1
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if match:
                first, last = match.group(1), match.group(2)
                if first:
                    start_byte = int(first)
                    if last:
                        end_byte = min(int(last), virtual_size - 1)
                elif last:
                    suffix_len = int(last)
                    if suffix_len > 0:
                        start_byte = max(0, virtual_size - suffix_len)
                        end_byte = virtual_size - 1

        if start_byte < 0 or start_byte >= virtual_size or end_byte < start_byte:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{virtual_size}"})

        chunk_len = end_byte - start_byte + 1
        
        if "GLOBAL_STREAM_TASKS" not in globals():
            global GLOBAL_STREAM_TASKS
            GLOBAL_STREAM_TASKS = {}
            
        # 🟢 FIX: Make the lock key unique with a UUID so simultaneous parallel requests 
        # from VLC or FFmpeg don't aggressively cancel each other out, 
        # while still allowing the Web UI "Stop" button to kill them cleanly!
        import uuid
        client_ip = request.remote or "unknown_ip"
        lock_key = f"{user_id}_{chat_id}_{msg_id}_{client_ip}_{uuid.uuid4().hex}"
        
        GLOBAL_STREAM_TASKS[lock_key] = asyncio.current_task()

        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_len),
            "Content-Type": mime_type,
            "Content-Range": f"bytes {start_byte}-{end_byte}/{virtual_size}",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Content-Type",
            "Cache-Control": "no-store",
        }

        if request.method == "HEAD":
            return web.Response(status=206 if range_header else 200, headers=headers)

        import aiohttp
        response = web.StreamResponse(status=206 if range_header else 200, headers=headers)
        
        adjusted_start = start_byte + virtual_data_offset
        gen = parallel_stream_generator(primary_client, chat_id, parts_map, adjusted_start, chunk_len, concurrency=6)
        
        sid = _track_stream(request, filename, user_id)
        try:
            await response.prepare(request)
            async for chunk in gen:
                await response.write(chunk)
            await response.write_eof()
        except (ConnectionResetError, asyncio.CancelledError, aiohttp.client_exceptions.ClientConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass # Normal browser disconnects ignored
        except Exception as exc:
            if "Connection closed" not in str(exc) and "BrokenPipeError" not in str(exc):
                logger.debug(f"Telegram stream disconnect/error: {exc}")
        finally:
            _untrack_stream(sid)
            if hasattr(gen, 'aclose'):
                try: 
                    await asyncio.wait_for(gen.aclose(), timeout=1.0)
                except Exception:
                    pass
            
        if not response.prepared:
            return web.Response(status=499, text="Client Closed Request")
        return response

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception(f"Telegram stream failed: {exc}")
        if response is None or not getattr(response, 'prepared', False):
            return web.Response(status=502, text="Telegram stream failed")
        return response
    finally:
        if temp_client is not None:
            try:
                await temp_client.disconnect()
            except Exception:
                pass

SUBTITLE_CACHE = {}
SUBTITLE_CACHE_TTL = 3600
SUBTITLE_LOCKS = defaultdict(asyncio.Lock)

async def _api_subtitles_handler(request):
    """Extract embedded subtitle once, cache the WebVTT, and serve it fast thereafter."""
    try:
        user_id = int(request.query.get("user_id", 0))
    except Exception:
        user_id = 0
    link = request.query.get("link", "").strip()
    sub_idx = request.query.get("sub_idx", "0").strip()
    zip_idx = request.query.get("zip_idx", "").strip() # 🟢 FIX: Fixes NameError crash
    if not link:
        return web.Response(status=400, text="Invalid Link")

    is_tg = _is_tg_link(link)
    logger.info(f"📝 [SUBTITLES] Extract Request | User: {user_id} | Is TG: {is_tg} | Sub_Idx: {sub_idx} | Link: {link[:60]}...")

    # 🟢 FIX: Include zip_idx in the cache key so different tracks in an album don't overwrite each other!
    cache_key = f"{user_id}:{link}:{sub_idx}:{zip_idx}"
    now = time.time()
    cached = SUBTITLE_CACHE.get(cache_key)
    if cached and cached[1] > now:
        body = cached[0]
        return web.Response(body=body, status=200, headers={
            "Content-Type": "text/vtt; charset=utf-8",
            "Content-Length": str(len(body)),
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        })

    actual_url = link
    if is_tg:
        parsed = _parse_source_link(link)
        chat_id = parsed.get("chat_id")
        msg_id = parsed.get("msg_id")
        msg_range = parsed.get("msg_range") # 🟢 Extract range
        if chat_id is None or msg_id is None:
            return web.Response(status=400, text="Invalid Telegram link")
        actual_url = f"http://127.0.0.1:{PORT}/api/tg_stream?user_id={user_id}&chat_id={chat_id}&msg_id={msg_id}"
        if msg_range:
            actual_url += f"&range={msg_range[0]}-{msg_range[1]}" 
        if zip_idx:
            actual_url += f"&zip_idx={zip_idx}" 
    else:
        # 🟢 CRITICAL FIX: Route FFmpeg through internal proxy so subtitle extraction doesn't stall on CDNs
        from urllib.parse import quote
        if zip_idx:
            actual_url = f"http://127.0.0.1:{PORT}/api/direct_stream?user_id={user_id}&url={quote(link, safe='')}&zip_idx={zip_idx}"
        else:
            actual_url = f"http://127.0.0.1:{PORT}/api/direct_stream?user_id={user_id}&url={quote(link, safe='')}"

    # 🟢 FIX: Extract Embedded Metadata Lyrics directly!
    if sub_idx == "metadata_lyrics":
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format_tags=lyrics,LYRICS,Lyrics,UNSYNCEDLYRICS,SYLT",
            "-of", "default=noprint_wrappers=1:nokey=1",
            actual_url
        ]
            
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            # 🟢 FIX: Decode and unescape literal FFprobe string newlines
            raw_text = stdout.decode('utf-8', errors='ignore')
            raw_text = raw_text.replace('\\r\\n', '\n').replace('\\n', '\n')
            body = raw_text.encode('utf-8')
            
            if not body.strip():
                return web.Response(status=404, text="No lyrics found")
                
            SUBTITLE_CACHE[cache_key] = (bytes(body), time.time() + SUBTITLE_CACHE_TTL)
            return web.Response(body=body, status=200, headers={
                "Content-Type": "text/vtt; charset=utf-8",
                "Content-Length": str(len(body)),
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "public, max-age=3600",
            })
        except Exception as exc:
            return web.Response(status=502, text=str(exc))

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", 
        "-rw_timeout", "120000000", 
        "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2",
        "-seekable", "1", "-multiple_requests", "1"
        # 🟢 CRITICAL FIX: Removed probesize limit so MKV subs are found!
    ]
    
    cmd += [
        "-i", actual_url,
        "-map", f"0:{sub_idx}",
        "-vn", "-an", "-c:s", "webvtt", "-f", "webvtt", "pipe:1"
    ]

    import aiohttp
    response = web.StreamResponse(status=200, headers={
        "Content-Type": "text/vtt; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": "no-cache",
    })
    
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        await response.prepare(request)
        
        body_buffer = bytearray()
        while True:
            chunk = await proc.stdout.read(8192)
            if not chunk:
                break
            body_buffer.extend(chunk)
            await response.write(chunk)
            
        await response.write_eof()
        await proc.wait()
        
        if proc.returncode == 0 and body_buffer:
            SUBTITLE_CACHE[cache_key] = (bytes(body_buffer), time.time() + SUBTITLE_CACHE_TTL)
            if len(SUBTITLE_CACHE) > 128:
                oldest = min(SUBTITLE_CACHE.items(), key=lambda kv: kv[1][1])[0]
                SUBTITLE_CACHE.pop(oldest, None)
        return response
    except (ConnectionResetError, asyncio.CancelledError, aiohttp.client_exceptions.ClientConnectionResetError):
        return response
    except Exception as exc:
        try: proc.kill()
        except: pass
        if not response.prepared:
            return web.Response(status=502, text=str(exc))
        return response
            
import mimetypes
import math
import re
import asyncio

def _u16(b, o): return int.from_bytes(b[o:o + 2], "little")
def _u32(b, o): return int.from_bytes(b[o:o + 4], "little")
def _u64(b, o): return int.from_bytes(b[o:o + 8], "little")

def _zip64_sizes(extra, uncomp, comp, need_offset=False, offset=0):
    i = 0
    while i + 4 <= len(extra):
        hid, hsz = _u16(extra, i), _u16(extra, i + 2)
        body = extra[i + 4:i + 4 + hsz]
        if hid == 0x0001:
            vals = [_u64(body, j) for j in range(0, (len(body) // 8) * 8, 8)]
            k = 0
            if uncomp == 0xFFFFFFFF and k < len(vals): uncomp = vals[k]; k += 1
            if comp == 0xFFFFFFFF and k < len(vals): comp = vals[k]; k += 1
            if need_offset and offset == 0xFFFFFFFF and k < len(vals): offset = vals[k]; k += 1
            break
        i += 4 + hsz
    return uncomp, comp, offset

def parse_local_header(buf):
    if len(buf) < 30 or buf[0:4] != b"PK\x03\x04": return None
    flag, method = _u16(buf, 6), _u16(buf, 8)
    comp, uncomp = _u32(buf, 18), _u32(buf, 22)
    name_len, extra_len = _u16(buf, 26), _u16(buf, 28)
    name = buf[30:30 + name_len].decode("utf-8", "ignore")
    extra = buf[30 + name_len:30 + name_len + extra_len]
    if uncomp == 0xFFFFFFFF or comp == 0xFFFFFFFF: uncomp, comp, _ = _zip64_sizes(extra, uncomp, comp)
    return {"method": method, "name": name, "data_offset": 30 + name_len + extra_len, "size": uncomp, "comp_size": comp, "has_descriptor": bool(flag & 0x08)}

def _parse_central_directory_full(tail, tail_base, zip_size):
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0: return []
    cd_offset = _u32(tail, eocd + 16)
    cd_records = _u16(tail, eocd + 10)
    z64loc = tail.rfind(b"PK\x06\x07")
    if cd_offset == 0xFFFFFFFF and z64loc >= 0:
        rel = _u64(tail, z64loc + 8) - tail_base
        if 0 <= rel < len(tail) and tail[rel:rel + 4] == b"PK\x06\x06": 
            cd_offset = _u64(tail, rel + 48)
            cd_records = _u64(tail, rel + 32)
    rel_cd = cd_offset - tail_base
    if rel_cd < 0 or rel_cd >= len(tail): return []
    
    entries = []
    o = rel_cd
    for _ in range(cd_records):
        if o + 46 > len(tail) or tail[o:o+4] != b"PK\x01\x02": break
        method, comp, uncomp = _u16(tail, o + 10), _u32(tail, o + 20), _u32(tail, o + 24)
        name_len, extra_len, comment_len = _u16(tail, o + 28), _u16(tail, o + 30), _u16(tail, o + 32)
        local_offset = _u32(tail, o + 42)
        name = tail[o + 46:o + 46 + name_len].decode("utf-8", "ignore")
        extra = tail[o + 46 + name_len:o + 46 + name_len + extra_len]
        if uncomp == 0xFFFFFFFF or comp == 0xFFFFFFFF or local_offset == 0xFFFFFFFF: 
            uncomp, comp, local_offset = _zip64_sizes(extra, uncomp, comp, need_offset=True, offset=local_offset)
        
        entries.append({"method": method, "name": name, "size": uncomp, "comp_size": comp, "local_offset": local_offset})
        o += 46 + name_len + extra_len + comment_len
    return entries

async def get_zip_playlist(read_fn, zip_size):
    try:
        tail_len = min(262144, zip_size)
        tail = await read_fn(zip_size - tail_len, tail_len)
        entries = _parse_central_directory_full(tail, zip_size - tail_len, zip_size)
        valid_exts = (".flac", ".mp3", ".m4a", ".ogg", ".wav", ".aac", ".wma", ".opus", ".dsf", ".ape", ".mka", ".alac", ".mp4", ".mkv", ".webm")
        playlist = []
        for idx, e in enumerate(entries):
            if e["name"].lower().endswith(valid_exts) and e["method"] == 0:
                e["original_index"] = idx
                e["display_name"] = e["name"].split("/")[-1].split("\\")[-1]
                playlist.append(e)
        return playlist
    except Exception: return []

async def resolve_specific_zip_entry(read_fn, entry):
    try:
        lh_buf = await read_fn(entry["local_offset"], min(4096, entry["size"] + 4096))
        lh = parse_local_header(lh_buf)
        if not lh: return None
        data_offset = entry["local_offset"] + lh["data_offset"]
        return {"method": 0, "name": entry["name"], "data_offset": data_offset, "size": entry["size"], "comp_size": entry["comp_size"]}
    except Exception: return None

CLIENT_MSG_CACHE = {}

async def get_client_msg(client, chat_id, msg_id):
    """Caches Telegram messages per-client. Propagates errors instead of permanently caching None."""
    key = (id(client), chat_id, msg_id)
    if key not in CLIENT_MSG_CACHE:
        msg = await client.get_messages(chat_id, msg_id)
        if getattr(msg, "empty", True) or not (msg.document or msg.video or msg.audio):
            raise ValueError(f"Empty Message for client {getattr(client, 'name', 'Unknown')}")
        CLIENT_MSG_CACHE[key] = msg
    return CLIENT_MSG_CACHE[key]

# 🟢 NEW: Global Smart RAM Cache for FFmpeg Micro-Requests
TG_CHUNK_CACHE = {}
TG_CHUNK_CACHE_MAX_SIZE = 128
TG_CHUNK_LOCKS = defaultdict(asyncio.Lock)

async def _get_cached_tg_chunk_pool(user_id, working_pool, chat_id, msg_id, chunk_index):
    cache_key = (user_id, chat_id, msg_id, chunk_index)
    async with TG_CHUNK_LOCKS[cache_key]:
        if cache_key in TG_CHUNK_CACHE:
            return TG_CHUNK_CACHE[cache_key]
            
        data = bytearray()
        import random
        import asyncio
        # Randomize start bot to spread FFprobe metadata load evenly
        start_bot_idx = random.randint(0, max(0, len(working_pool) - 1))
        
        # Try every bot in the pool up to 2 times
        for attempt in range(len(working_pool) * 2):
            client = working_pool[(start_bot_idx + attempt) % len(working_pool)]
            try:
                if not getattr(client, "is_connected", False):
                    await client.connect()
                    
                msg = await get_client_msg(client, chat_id, msg_id)
                data.clear()
                
                async def fetch_1mb():
                    async for chunk in client.stream_media(msg, offset=chunk_index, limit=1):
                        data.extend(chunk)
                        
                # 🟢 THE KILL SWITCH: If Pyrogram's socket freezes, forcefully kill it after 8 seconds 
                # and immediately switch to the next bot! No more 30-second frozen players!
                await asyncio.wait_for(fetch_1mb(), timeout=8.0)
                
                if data:
                    break # Success!
            except asyncio.TimeoutError:
                logger.debug(f"Bot {getattr(client, 'name', 'Client')} timed out. Rotating...")
                continue
            except Exception as e:
                logger.debug(f"Bot {getattr(client, 'name', 'Client')} failed: {e}. Rotating...")
                continue
                
        if not data:
            raise ValueError(f"Failed to fetch chunk {chunk_index} across all bots.")
            
        chunk_bytes = bytes(data)
        TG_CHUNK_CACHE[cache_key] = chunk_bytes
        
        if len(TG_CHUNK_CACHE) > TG_CHUNK_CACHE_MAX_SIZE:
            TG_CHUNK_CACHE.pop(next(iter(TG_CHUNK_CACHE)))
            
        await asyncio.sleep(0.01) # Prevent event loop starvation
        return chunk_bytes

async def fetch_single_chunk(client, chat_id, msg_id, offset, limit):
    """Legacy strict fetcher for Downloads. Wrapped with timeout to prevent hangs."""
    ALIGNMENT = 1048576
    aligned_offset = (offset // ALIGNMENT) * ALIGNMENT
    target_bytes = limit
    
    for attempt in range(6): 
        if not getattr(client, "is_connected", False):
            try: await client.connect()
            except Exception: pass

        skip_bytes = offset - aligned_offset
        fetch_limit = target_bytes + skip_bytes
        try:
            msg = await get_client_msg(client, chat_id, msg_id)
            data = bytearray()
            
            async def fetch_legacy():
                nonlocal skip_bytes
                async for chunk in client.stream_media(msg, offset=aligned_offset, limit=fetch_limit):
                    if skip_bytes > 0:
                        if len(chunk) <= skip_bytes:
                            skip_bytes -= len(chunk)
                            continue
                        else:
                            chunk = chunk[skip_bytes:]
                            skip_bytes = 0
                    data.extend(chunk)
                    
            import asyncio
            # Force Pyrogram to give up if socket is dead
            await asyncio.wait_for(fetch_legacy(), timeout=12.0)
                    
            if not data: 
                raise ValueError("EOF Reached or Empty Chunk")
            return bytes(data[:target_bytes])
            
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
        except Exception as e:
            if attempt == 5: raise e
            await asyncio.sleep(1.5 + attempt) 
            
    raise TimeoutError("Exceeded max retries for chunk")

async def parallel_stream_generator(fallback_client, chat_id, msg_parts, start_byte, total_length, chunk_size=1048576, concurrency=4):
    """Ultra-Stable Continuous Stream Generator with Auto-Recovery and Bot Rotation."""
    if total_length <= 0: return

    working_pool = []
    user_id = 0
    if fallback_client in USER_CLIENTS.values():
        for uid, candidate in USER_CLIENTS.items():
            if candidate is fallback_client:
                user_id = uid; break

    user_worker_bots = list(USER_WORKER_BOTS.get(user_id, []))
    for c in user_worker_bots:
        try:
            if getattr(c, "is_connected", False): working_pool.append(c)
        except Exception: pass
            
    if fallback_client:
        try:
            if getattr(fallback_client, "is_connected", False): working_pool.append(fallback_client)
        except Exception: pass

    if not working_pool:
        working_pool = [app]

    bytes_needed = total_length
    current_offset = start_byte

    for part in msg_parts:
        if bytes_needed <= 0: break
        if part["start"] <= current_offset < part["end"]:
            internal_offset = current_offset - part["start"]
            internal_limit = min(bytes_needed, part["size"] - internal_offset)
            bytes_yielded_this_part = 0
            
            while bytes_yielded_this_part < internal_limit:
                current_byte_offset = internal_offset + bytes_yielded_this_part
                CHUNK_SIZE = 1048576
                chunk_index = current_byte_offset // CHUNK_SIZE
                skip_bytes = current_byte_offset % CHUNK_SIZE
                remaining_bytes = internal_limit - bytes_yielded_this_part
                
                import asyncio
                # 🟢 Pass the ENTIRE pool into the smart cache so it can rotate bots instantly!
                chunk_task = asyncio.create_task(_get_cached_tg_chunk_pool(user_id, working_pool, chat_id, part["msg_id"], chunk_index))
                chunk_data = await asyncio.shield(chunk_task)
                
                if skip_bytes > 0:
                    chunk_data = chunk_data[skip_bytes:]
                    
                chunk_to_yield = chunk_data[:remaining_bytes]
                if chunk_to_yield:
                    yield chunk_to_yield
                    bytes_yielded_this_part += len(chunk_to_yield)
                    
                await asyncio.sleep(0.001) 
                        
            current_offset += internal_limit
            bytes_needed -= internal_limit
            
USER_WORKER_BOTS = defaultdict(list)

async def init_worker_bots(user_id=None):
    """Initializes extra bot clients from MongoDB for parallel downloads per user."""
    user_ids_to_init = [user_id] if user_id else []
    if not user_id:
        # Find all users with tokens
        cursor = db.col.find({"bot_tokens": {"$exists": True, "$ne": []}})
        async for u in cursor:
            user_ids_to_init.append(u["id"])
            
    for uid in user_ids_to_init:
        # Stop existing bots for this user
        for c in USER_WORKER_BOTS.get(uid, []):
            try: await c.stop()
            except Exception: pass
        USER_WORKER_BOTS[uid].clear()
        
        # Fetch tokens uniquely for this user
        user_doc = await db.col.find_one({"id": uid})
        tokens = user_doc.get("bot_tokens", []) if user_doc else []
        
        for idx, token in enumerate(tokens, start=1):
            try:
                bot_client = Client(
                    f"worker_bot_{uid}_{idx}",
                    api_id=API_ID,
                    api_hash=API_HASH,
                    bot_token=token.strip(),
                    workers=4,
                    no_updates=True, # 🟢 REVERT: Must be True to save RAM and prevent background update floods.
                    ipv6=False
                )
                await bot_client.start()
                USER_WORKER_BOTS[uid].append(bot_client)
                logger.info(f"🚀 Worker Bot {idx} active for user {uid} parallel streaming.")
            except Exception as e:
                logger.warning(f"Could not load worker token {idx} for user {uid}: {e}")

async def _api_get_worker_tokens(request):
    uid = int(request.query.get("user_id", 0))
    doc = await db.col.find_one({"id": uid})
    return web.json_response({"status": "success", "tokens": doc.get("bot_tokens", []) if doc else []})

async def _api_save_worker_tokens(request):
    data = await request.json()
    uid = int(data.get("user_id", 0))
    tokens = [t.strip() for t in data.get("tokens", []) if ":" in t]
    
    # Save directly to the User's Database Object
    await db.col.update_one({"id": uid}, {"$set": {"bot_tokens": tokens}}, upsert=True)
    asyncio.create_task(init_worker_bots(uid))
    
    # Clear access cache so the new bots are used immediately
    TG_ACCESS_CACHE.clear()
    
    return web.json_response({"status": "success", "message": f"Saved {len(tokens)} worker token(s) for your account. Pool reloading."})

async def _api_network_stats(request):
    try: uid = int(request.query.get("user_id", 0))
    except: uid = 0
    return web.json_response({
        "status": "success",
        "active": list(GLOBAL_NETWORK_STATS["active"].values()),
        "recent": GLOBAL_NETWORK_STATS["recent"],
        "worker_bots_count": len(USER_WORKER_BOTS.get(uid, []))
    })

# --- NEW: NATIVE IMAGE PROXY TO BYPASS HUGGINGFACE CSP ---
async def _api_bg_proxy(request):
    url = request.query.get("url", "")
    if not url: return web.Response(status=400)
    import aiohttp
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                body = await resp.read()
                return web.Response(body=body, headers={"Content-Type": "image/jpeg", "Cache-Control": "public, max-age=8640000"})
    except Exception:
        return web.Response(status=500)

async def _api_playlist_handler(request):
    """Extracts playlist array from ZIPs and Split ZIPs for continuous album playback."""
    try: user_id = int(request.query.get("user_id", 0))
    except: user_id = 0
    link = request.query.get("link", "").strip()
    if not link: return web.json_response({"status": "error"})
    
    is_tg = _is_tg_link(link)
    playlist = []
    try:
        if is_tg:
            parsed = _parse_source_link(link)
            chat_id = parsed.get("chat_id")
            msg_id = parsed.get("msg_id")
            pool, _ = await _get_working_tg_pool(user_id, chat_id, msg_id)
            primary_client = pool[0]
            
            msg = await get_client_msg(primary_client, chat_id, msg_id)
            media = msg.document or msg.video or msg.audio
            filename = str(getattr(media, "file_name", "")).lower()
            
            is_zip = filename.endswith(".zip") or ".zip." in filename
            if not is_zip: return web.json_response({"status": "success", "playlist": []})
            
            parts_map = []
            global_offset = 0
            match = re.search(r'\.(\d{2,3})$', filename)
            if match and int(match.group(1)) == 1:
                current_id = msg_id
                while True:
                    try:
                        m = await get_client_msg(primary_client, chat_id, current_id)
                        doc = m.document or m.video or m.audio
                        if not doc: break
                        psz = int(doc.file_size or 0)
                        parts_map.append({"msg_id": m.id, "start": global_offset, "end": global_offset + psz, "size": psz})
                        global_offset += psz
                        current_id += 1
                        next_m = await get_client_msg(primary_client, chat_id, current_id)
                        next_doc = next_m.document or next_m.video or next_m.audio
                        if not next_doc or not re.search(r'\.\d{2,3}$', next_doc.file_name or ""): break
                    except Exception: break
            else:
                part_size = int(getattr(media, "file_size", 0) or 0)
                parts_map.append({"msg_id": msg_id, "start": 0, "end": part_size, "size": part_size})
                global_offset = part_size
                
            async def zip_read_tg(off, length):
                buf = bytearray()
                async for chunk in parallel_stream_generator(primary_client, chat_id, parts_map, off, length, concurrency=6):
                    buf.extend(chunk)
                    if len(buf) >= length: break
                return bytes(buf[:length])
                
            playlist = await get_zip_playlist(zip_read_tg, global_offset)
        else:
            actual_url = await resolve_direct_link(link)
            filename = _guess_filename_from_url(actual_url).lower()
            is_zip = filename.endswith(".zip") or ".zip." in filename
            if not is_zip: return web.json_response({"status": "success", "playlist": []})
            
            session = await _get_direct_http_session()
            async with session.head(actual_url, allow_redirects=True) as h_resp:
                raw_size = int(h_resp.headers.get("Content-Length", 0))
                
            async def zip_read_http(off, length):
                headers = {"Range": f"bytes={off}-{off+length-1}", "User-Agent": "Mozilla/5.0"}
                async with session.get(actual_url, headers=headers) as r:
                    return await r.read()
                    
            playlist = await get_zip_playlist(zip_read_http, raw_size)
            
        return web.json_response({"status": "success", "playlist": playlist})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})

# ==============================================================================
# --- NEW: WORLD EXPLORER PROXY ENDPOINTS ---
# ==============================================================================
async def _api_proxy_country(request):
    iso = request.query.get("iso", "").strip()
    name = request.query.get("name", "").strip()
    import aiohttp
    import json
    from urllib.parse import quote

    async def fetch_api(url):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        # Ensure we actually got data, not an empty list [] or error dict
                        if isinstance(data, list) and len(data) > 0: return data
                        if isinstance(data, dict) and "flags" in data: return data
                    except Exception:
                        pass
                return None

    try:
        data = None
        # Attempt 1: Try ISO Code
        if iso and iso != "-99":
            data = await fetch_api(f"https://restcountries.com/v3.1/alpha/{iso}")
        
        # Attempt 2: Fallback to Exact Name Search
        if not data and name:
            data = await fetch_api(f"https://restcountries.com/v3.1/name/{quote(name)}?fullText=true")
            
        # Attempt 3: Fallback to Partial Name Search
        if not data and name:
            data = await fetch_api(f"https://restcountries.com/v3.1/name/{quote(name)}")

        # Return Success or clear 404 Error
        if data:
            return web.json_response(data)
        else:
            return web.Response(status=404, text=json.dumps({"error": "Country data not found or API rate limited."}), content_type="application/json")
            
    except Exception as e:
        return web.Response(status=500, text=json.dumps({"error": str(e)}), content_type="application/json")

async def _api_proxy_wiki(request):
    q = request.query.get("q", "").strip()
    import aiohttp
    from urllib.parse import quote
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with aiohttp.ClientSession() as session:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(q)}"
            async with session.get(url, headers=headers) as resp:
                text = await resp.text()
                return web.Response(status=resp.status, text=text, content_type="application/json")
    except Exception as e:
        return web.Response(status=500, text=str(e))

async def _api_edit_media_handler(request):
    data = await request.json()
    uid = int(data.get("user_id", 0))
    link = data.get("link", "")
    config = data.get("config", [])
    new_name = data.get("new_name", "output.mkv")
    dest = data.get("dest", "tg")
    
    if not link or not config:
        return web.json_response({"status": "error", "message": "Missing link or config"})
        
    import time
    from pathlib import Path
    import shutil
    
    temp_dir = Path(f"./temp_remux_{uid}_{int(time.time())}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    input_file = temp_dir / "input_media.dat"
    output_file = temp_dir / sanitize_filename(new_name)
    
    try:
        is_tg = _is_tg_link(link)
        if is_tg:
            parsed = _parse_source_link(link)
            uclient = USER_CLIENTS.get(uid)
            if not uclient or not uclient.is_connected:
                session_str = await db.get_session(uid)
                u_api = await db.get_api_id(uid) or API_ID
                u_hash = await db.get_api_hash(uid) or API_HASH
                uclient = Client(f"User_{uid}", session_string=session_str, api_id=u_api, api_hash=u_hash, ipv6=False)
                await uclient.start()
                USER_CLIENTS[uid] = uclient
            msg = await uclient.get_messages(parsed["chat_id"], parsed["msg_id"])
            await uclient.download_media(msg, file_name=str(input_file))
        else:
            await full_download_http(link, str(input_file))
            
        await process_remux(str(input_file), str(output_file), config)
        
        url = ""
        if dest == "gofile":
            url = await upload_to_gofile(str(output_file))
        else:
            sent_msg = await app.send_document(chat_id=uid, document=str(output_file), caption=f"✅ Remuxed: {new_name}")
            url = f"https://t.me/c/{str(uid).replace('-100', '')}/{sent_msg.id}"
            
        return web.json_response({"status": "success", "url": url})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)})
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)

async def start_koyeb_health_check(host: str = "0.0.0.0"):
    if web is None: return
    global PORT
    app_web = web.Application()
    app_web.router.add_get("/api/network", _api_network_stats)
    app_web.router.add_get("/api/bg", _api_bg_proxy)
    app_web.router.add_get("/api/chat_details", _api_chat_details_handler) # 🟢 NEW: Chat Details Endpoint
    app_web.router.add_get("/manifest.json", _manifest_handler)
    app_web.router.add_get("/sw.js", _sw_handler)
    app_web.router.add_get("/", _dashboard_ui_handler)
    app_web.router.add_get("/health", _dashboard_ui_handler)
    app_web.router.add_get("/api/stats", _api_stats_handler)
    app_web.router.add_get("/api/logs", _api_logs_handler)
    app_web.router.add_get("/api/chats", _api_chats_handler)
    app_web.router.add_get("/api/topics", _api_topics_handler)
    app_web.router.add_post("/api/mediainfo", _api_mediainfo_web_handler)
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
    app_web.router.add_post("/api/spectrogram", _api_spectrogram_web_handler)
    app_web.router.add_get("/api/media_probe", _api_media_probe_handler)
    app_web.router.add_get("/api/cover", _api_cover_handler) # 🟢 NEW: Cover Art API
    app_web.router.add_get("/api/stream", _api_stream_handler)
    app_web.router.add_get("/api/direct_stream", _api_direct_stream_handler)
    app_web.router.add_get("/api/subtitles", _api_subtitles_handler)
    app_web.router.add_get("/api/topics", _api_topics_handler)
    app_web.router.add_get("/api/tg_stream", _api_tg_stream_handler) # <-- ADD THIS LINE
    app_web.router.add_post("/api/mediainfo", _api_mediainfo_web_handler)
    app_web.router.add_get("/api/settings/tokens", _api_get_worker_tokens)
    app_web.router.add_post("/api/settings/tokens", _api_save_worker_tokens)
    app_web.router.add_get("/api/playlist", _api_playlist_handler) # 🟢 ADD THIS LINE
    app_web.router.add_get("/api/stream", _api_stream_handler)      
    # 🟢 ADD THESE TWO NEW LINES HERE:
    app_web.router.add_get("/api/proxy/country", _api_proxy_country)
    app_web.router.add_get("/api/proxy/wiki", _api_proxy_wiki)  
    app_web.router.add_post("/api/edit_media", _api_edit_media_handler) # 🟢 ADD THIS LINE!
    
    # 🟢 ADD THIS NEW ROUTE FOR THE STOP BUTTON
    async def _api_kill_stream(request):
        try:
            data = await request.json()
            uid = str(data.get("user_id", ""))
            
            if "GLOBAL_STREAM_TASKS" in globals() and uid:
                keys_to_delete = []
                # Safely find and cancel ONLY the streams belonging to this user
                for key, task in list(GLOBAL_STREAM_TASKS.items()):
                    if key.startswith(f"{uid}_"):
                        if not task.done():
                            task.cancel()
                        keys_to_delete.append(key)
                
                # Remove them from the global dictionary
                for k in keys_to_delete:
                    GLOBAL_STREAM_TASKS.pop(k, None)
                    
            return web.json_response({"status": "success", "message": "User streams killed cleanly."})
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)})

    app_web.router.add_post("/api/stream/kill", _api_kill_stream)
        
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
    limit_bytes = max(1, int(limit_mb * 1024 * 1024))

    if file_size <= limit_bytes:
        await client.download_media(message, file_name=str(file_path))
        return

    # Preserve the original sparse-file strategy, but actually honor limit_mb.
    chunk_size = 1048576
    total_chunks = math.ceil(file_size / chunk_size)
    edge_chunks = max(1, math.ceil((limit_bytes / 2) / chunk_size))
    edge_chunks = min(edge_chunks, total_chunks // 2)

    with open(file_path, "wb") as f:
        # Start of file: container headers + stream declarations.
        async for chunk in client.stream_media(message, limit=edge_chunks):
            f.write(chunk)

        if total_chunks > edge_chunks:
            offset = max(edge_chunks, total_chunks - edge_chunks)
            tail_limit = total_chunks - offset
            if tail_limit > 0:
                f.seek(offset * chunk_size)
                async for chunk in client.stream_media(message, offset=offset, limit=tail_limit):
                    f.write(chunk)

async def partial_download_http(url, file_path, limit_mb=15):
    """Robust bounded HTTP sampler used by MediaInfo/probing.

    Important properties:
      * Never assumes the remote Content-Length equals the number of bytes that
        will actually arrive. Some CDNs/proxies close a response early.
      * Uses byte ranges for large files when supported.
      * Never calls response.read() without a size cap on a supposedly ranged
        response.
      * Rejects HTML pages early because a movie-page URL is not a media URL.
      * Returns gracefully with the bytes that were actually received when the
        remote server truncates a probe response.
    """
    limit_bytes = max(1, int(limit_mb * 1024 * 1024))
    ua = (
        "Mozilla/5.0 (Linux; Android 10; Mobile) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Mobile Safari/537.36"
    )
    headers = {
        "User-Agent": ua,
        "Accept": "video/*,audio/*,application/octet-stream,application/vnd.apple.mpegurl,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    timeout = aiohttp.ClientTimeout(total=None, connect=20, sock_connect=20, sock_read=25)

    def filename_from_headers(resp):
        detected = "Stream_File.dat"
        cd = resp.headers.get("Content-Disposition", "")
        if cd:
            # RFC 5987 filename*=UTF-8''... first, then normal filename=.
            m = re.search(r"filename\\*=(?:UTF-8''|utf-8'')([^;]+)", cd, re.I)
            if m:
                detected = unquote(m.group(1).strip().strip('"'))
            else:
                m = re.search(r'filename="?([^";]+)"?', cd, re.I)
                if m:
                    detected = m.group(1).strip()
        if detected == "Stream_File.dat":
            path_name = os.path.basename(urlparse(url).path)
            if path_name:
                detected = unquote(path_name)
        return detected or "Stream_File.dat"

    async def consume_limited(resp, out_f, max_bytes):
        """Write at most max_bytes and tolerate premature upstream EOF."""
        written = 0
        try:
            async for chunk in resp.content.iter_chunked(256 * 1024):
                if not chunk:
                    continue
                remaining = max_bytes - written
                if remaining <= 0:
                    break
                if len(chunk) > remaining:
                    chunk = chunk[:remaining]
                out_f.write(chunk)
                written += len(chunk)
                if written >= max_bytes:
                    break
        except (aiohttp.ClientPayloadError,
                aiohttp.ServerDisconnectedError,
                asyncio.TimeoutError,
                ConnectionError,
                OSError) as exc:
            # A truncated probe is still useful to ffprobe if it contains enough
            # container headers/stream descriptors. Do not turn this into a fatal
            # ContentLengthError for the web player.
            logger.warning(f"[HTTP probe] Remote body ended early: {exc}")
        return written

    async with aiohttp.ClientSession(timeout=timeout, raise_for_status=False) as session:
        # First request: headers + content-type + filename. Do not consume its body.
        try:
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                if resp.status >= 400:
                    body = await resp.text(errors="ignore")
                    raise RuntimeError(f"HTTP {resp.status}: {body[:180]}")

                content_type = (resp.headers.get("Content-Type") or "").lower()
                detected_name = filename_from_headers(resp)
                declared_size = int(resp.headers.get("Content-Length", "0") or 0)
                final_url = str(resp.url)

                # A webpage is not a playable media stream. Give the UI a useful
                # message instead of feeding HTML to ffprobe/HTMLMediaElement.
                if "text/html" in content_type or content_type.startswith("text/plain") and not re.search(r"\.(?:m3u8|mpd)(?:$|\?)", final_url, re.I):
                    raise ValueError(
                        "This URL returned a webpage/text page, not a direct video/audio stream. "
                        "Use the direct .mp4/.webm/.mkv/.m3u8 media URL."
                    )
        except ValueError:
            raise

        # Small/unknown-size resource: read only the probe budget. Even if the
        # server advertises a larger Content-Length, we never require all bytes.
        if declared_size == 0 or declared_size <= limit_bytes:
            with open(file_path, "wb") as f:
                try:
                    async with session.get(url, headers=headers, allow_redirects=True) as resp:
                        if resp.status >= 400:
                            raise RuntimeError(f"HTTP {resp.status} while reading media")
                        await consume_limited(resp, f, limit_bytes)
                except (aiohttp.ClientPayloadError,
                        aiohttp.ServerDisconnectedError,
                        asyncio.TimeoutError,
                        ConnectionError,
                        OSError) as exc:
                    logger.warning(f"[HTTP probe] Body truncated after partial read: {exc}")
            return declared_size, detected_name

        # Large resource: make a sparse probe file from head + tail ranges.
        edge_bytes = max(1_000_000, limit_bytes // 2)
        edge_bytes = min(edge_bytes, max(1, declared_size // 2))
        head_expected = edge_bytes
        tail_start = max(0, declared_size - edge_bytes)

        with open(file_path, "wb") as f:
            # HEAD sample.
            head_headers = headers.copy()
            head_headers["Range"] = f"bytes=0-{head_expected - 1}"
            try:
                async with session.get(url, headers=head_headers, allow_redirects=True) as resp:
                    if resp.status >= 400:
                        raise RuntimeError(f"HTTP {resp.status} for initial probe range")
                    await consume_limited(resp, f, head_expected)
                    head_is_partial = resp.status == 206 or bool(resp.headers.get("Content-Range"))
            except (aiohttp.ClientPayloadError,
                    aiohttp.ServerDisconnectedError,
                    asyncio.TimeoutError,
                    ConnectionError,
                    OSError) as exc:
                logger.warning(f"[HTTP probe] Head range ended early: {exc}")
                head_is_partial = False

            # Tail sample only when the server really honors Range. If it ignores
            # the Range header and returns 200/full-body, do not corrupt the sparse
            # file by writing the beginning of the file at the tail offset.
            tail_headers = headers.copy()
            tail_headers["Range"] = f"bytes={tail_start}-{declared_size - 1}"
            try:
                async with session.get(url, headers=tail_headers, allow_redirects=True) as resp:
                    if resp.status == 206 or resp.headers.get("Content-Range"):
                        f.seek(tail_start)
                        await consume_limited(resp, f, edge_bytes)
                    else:
                        logger.info("[HTTP probe] Remote server ignored tail Range; using head sample only.")
            except (aiohttp.ClientPayloadError,
                    aiohttp.ServerDisconnectedError,
                    asyncio.TimeoutError,
                    ConnectionError,
                    OSError) as exc:
                logger.warning(f"[HTTP probe] Tail range ended early: {exc}")

        return declared_size, detected_name

async def download_audio_snippet_tg(client_to_use, message, file_path, limit_mb=15):
    """Continuous download of the first X MB so SoX/FFmpeg reads it as a valid truncated file."""
    with open(file_path, "wb") as f:
        current_bytes = 0
        async for chunk in client_to_use.stream_media(message):
            f.write(chunk)
            current_bytes += len(chunk)
            if current_bytes >= limit_mb * 1024 * 1024:
                break

async def download_audio_snippet_http(url, file_path, limit_mb=15):
    """Continuous HTTP download of the first X MB."""
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                current_bytes = 0
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    f.write(chunk)
                    current_bytes += len(chunk)
                    if current_bytes >= limit_mb * 1024 * 1024:
                        break

async def full_download_http(url, file_path):
    """Full HTTP download for Spectrogram analysis."""
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            with open(file_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    f.write(chunk)
                    
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
                await client.download_media(media_msg, file_name=str(file_path))

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
# --- THE ULTIMATE FORENSIC & MASTERING AUDIO ANALYZER ---
# ==============================================================================

def get_channel_info_dsp(file_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels,channel_layout,codec_name", "-of", "json", str(file_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        info = json.loads(result.stdout)['streams'][0]
        
        channels = info.get('channels', 2)
        layout = info.get('channel_layout', 'unknown').lower()
        codec = info.get('codec_name', '').lower()

        codec_map = {'alac': 'ALAC', 'aac': 'AAC', 'flac': 'FLAC', 'mp3': 'MP3', 'eac3': 'E-AC-3', 'ac4': 'AC-4', 'truehd': 'TrueHD', 'opus': 'OPUS', 'vorbis': 'OGG', 'pcm_s16le': 'WAV'}
        detected_format = codec_map.get(codec, codec.upper() if codec else "AUDIO")

        is_spatial = False
        if codec in ['eac3', 'ac4', 'truehd']:
            is_spatial = True
            channel_str = f"{channels} Ch (Binaural Downmix)" if 'binaural' in layout else f"{channels} Ch (Spatial / Atmos)"
        elif layout != 'unknown':
            channel_str = f"{channels} Ch ({layout.title()})"
        else:
            channel_str = f"{channels} Ch"

        return detected_format, channel_str, is_spatial
    except Exception: return "AUDIO", "2.0 Ch (Stereo)", False

def analyze_mastering(data, sr):
    try:
        if data.ndim == 1: data = np.expand_dims(data, axis=1)
        samples, channels = data.shape

        dc_offset_db = 20 * np.log10(np.abs(np.mean(data, axis=0)) + 1e-12)
        worst_dc = np.max(dc_offset_db)

        peak_db = 20 * np.log10(np.max(np.abs(data), axis=0) + 1e-12)
        max_peak = np.max(peak_db)
        rms_db = 20 * np.log10(np.sqrt(np.mean(data**2, axis=0)) + 1e-12)
        avg_rms = np.mean(rms_db)

        clip_events = 0
        for ch in range(channels):
            is_clip = (np.abs(data[:, ch]) >= 0.997).astype(int)
            if len(is_clip) >= 3:
                seq = np.convolve(is_clip, np.ones(3), mode='valid')
                clip_events += np.sum(seq == 3)

        correlation = 1.0
        if channels >= 2:
            c1, c2 = data[:, 0] - np.mean(data[:, 0]), data[:, 1] - np.mean(data[:, 1])
            den = np.sqrt(np.sum(c1**2) * np.sum(c2**2))
            if den > 0: correlation = np.sum(c1 * c2) / den

        lufs = -70.0
        if HAS_PYLN:
            meter = pyln.Meter(sr)
            lufs = meter.integrated_loudness(data)

        dr_channels = []
        for ch in range(channels):
            ch_data = data[:, ch]
            block_samples = 3 * sr
            num_blocks = len(ch_data) // block_samples
            if num_blocks > 1:
                rms_blocks = [np.sqrt(2 * np.mean(ch_data[i*block_samples:(i+1)*block_samples]**2) + 1e-12) for i in range(num_blocks)]
                peak_blocks = [np.max(np.abs(ch_data[i*block_samples:(i+1)*block_samples])) for i in range(num_blocks)]
                top_indices = np.argsort(rms_blocks)[::-1][:max(1, int(num_blocks * 0.2))]
                avg_top_rms = np.mean([rms_blocks[i] for i in top_indices])
                top_peaks = sorted([peak_blocks[i] for i in top_indices], reverse=True)
                if avg_top_rms > 0:
                    dr_channels.append(20 * np.log10((top_peaks[1] if len(top_peaks) > 1 else top_peaks[0]) / avg_top_rms))
        dr_val = max(1, int(round(np.mean(dr_channels)))) if dr_channels else 0

        grade = "🟢 Excellent" if (dr_val >= 11 and clip_events == 0) else ("🟡 Good / Moderate" if dr_val >= 8 and clip_events <= 50 else "🔴 Poor (Hot Master / Clipped)")
        return {"dc_offset": round(worst_dc, 1), "peak": round(max_peak, 2), "rms": round(avg_rms, 2), "clipping": clip_events, "correlation": round(correlation, 2), "lufs": round(lufs, 1), "dr": dr_val, "grade": grade}
    except Exception: return None

def detect_fake_24bit(data_raw, sr):
    try:
        mono = data_raw.mean(axis=1) if data_raw.ndim > 1 else data_raw
        frame_len = sr
        n_frames = len(mono) // frame_len
        if n_frames < 3: return "n/a", 0.0, "Track too short."
        frame_rms = np.array([np.sqrt(np.mean(mono[i*frame_len:(i+1)*frame_len] ** 2) + 1e-18) for i in range(n_frames)])
        loud_sample = np.concatenate([mono[i*frame_len:(i+1)*frame_len] for i in np.argsort(frame_rms)[::-1][:max(1, n_frames // 4)]])
        scaled = loud_sample * 32768.0
        on_grid_ratio = float(np.mean(np.abs(scaled - np.round(scaled)) < 1e-3))
        noise_floor_db = 20 * np.log10(np.std(np.concatenate([mono[i*frame_len:(i+1)*frame_len] for i in np.argsort(frame_rms)[:max(1, n_frames // 10)]])) + 1e-12)

        if on_grid_ratio > 0.98: return "padded", 0.95, f"{on_grid_ratio*100:.1f}% samples on 16-bit grid (Padded upscale)."
        if noise_floor_db >= -60.0: return "genuine", 0.50, f"No silent sections found (quietest is {noise_floor_db:.1f} dB). Assumed genuine."
        if noise_floor_db > -98.0: return "dithered_upscale", round(min(0.9, max(0.5, (noise_floor_db + 110) / 20)), 2), f"Noise floor {noise_floor_db:.1f} dB matches 16-bit dither."
        return "genuine", 0.85, f"Noise floor {noise_floor_db:.1f} dB matches 24-bit."
    except Exception: return "n/a", 0.0, "Analysis failed."

def generate_audio_stats_dsp(wav_path, original_file_path, original_name):
    try:
        audio = MutagenFile(original_file_path, easy=True)
        full = MutagenFile(original_file_path)
        title = audio.get('title', [original_name])[0] if audio else original_name
        artist = audio.get('artist', ['Unknown Artist'])[0] if audio else "Unknown Artist"
        bit_depth = getattr(full.info, "bits_per_sample", 16) if hasattr(full, 'info') else 16
        sample_rate_meta = getattr(full.info, "sample_rate", 44100) if hasattr(full, 'info') else 44100
    except Exception: title, artist, bit_depth, sample_rate_meta = original_name, "Unknown Artist", 16, 44100

    format_name, channel_str, is_spatial = get_channel_info_dsp(original_file_path)

    try:
        sr, data_raw = wavfile.read(wav_path)
        bit_verdict, bit_confidence, bit_detail = ("n/a", 0.0, "") if bit_depth != 24 else detect_fake_24bit(data_raw, sr)
        mastering = analyze_mastering(data_raw, sr)

        if data_raw.ndim > 1:
            f, t, Zxx_L = stft(data_raw[:, 0], fs=sr, nperseg=8192)
            f, t, Zxx_R = stft(data_raw[:, 1], fs=sr, nperseg=8192)
            max_mag = np.maximum(np.max(np.abs(Zxx_L), axis=1), np.max(np.abs(Zxx_R), axis=1))
            stft_2d = np.maximum(np.abs(Zxx_L), np.abs(Zxx_R))
        else:
            f, t, Zxx = stft(data_raw, fs=sr, nperseg=8192)
            max_mag, stft_2d = np.max(np.abs(Zxx), axis=1), np.abs(Zxx)

        psd_db = 20 * np.log10(max_mag + 1e-12)
        nyquist_hz = sr / 2.0
        passband_mask = (f >= 1000) & (f <= 8000)
        rel_psd_db = psd_db - (np.mean(psd_db[passband_mask]) if np.any(passband_mask) else np.max(psd_db))

        search_mask = f >= 10000
        search_freqs, search_db = f[search_mask], rel_psd_db[search_mask]
        noise_eval_mask = search_freqs >= (nyquist_hz * 0.85)
        dynamic_threshold = max(-60.0, min(-35.0, (np.median(search_db[noise_eval_mask]) if np.any(noise_eval_mask) else -55.0) + 12.0))

        cutoff_hz, consecutive_bins, required_bins = nyquist_hz, 0, max(1, int(150 / (sr / 8192)))
        for i in range(len(search_db) - 1, -1, -1):
            if search_db[i] > dynamic_threshold:
                consecutive_bins += 1
                if consecutive_bins >= required_bins: cutoff_hz = search_freqs[i + consecutive_bins - 1]; break
            else: consecutive_bins = 0

        pre_mask = (f >= max(0, cutoff_hz - 1500)) & (f <= cutoff_hz)
        post_mask = (f > cutoff_hz) & (f <= min(nyquist_hz, cutoff_hz + 1500))
        cliff_drop = float(np.median(rel_psd_db[pre_mask]) - np.median(rel_psd_db[post_mask])) if np.any(pre_mask) and np.any(post_mask) else 0.0

        hole_ratio = 0.0
        high_band_mask = (f >= 12000) & (f <= min(20000, nyquist_hz - 500))
        if np.any(high_band_mask):
            peak_val = np.max(stft_2d[high_band_mask, :])
            if peak_val > 0: hole_ratio = float(np.mean(stft_2d[high_band_mask, :] < (peak_val * 1e-4)))

        lossless_formats = ['FLAC', 'ALAC', 'WAV', 'PCM', 'DSF', 'DSD', 'AIFF']
        if is_spatial or format_name in ['E-AC-3', 'AC-4', 'TRUEHD']: auth_badge, auth_desc = "🟢 Dolby Atmos / Spatial", "Genuine spatial audio stream."
        elif format_name in lossless_formats:
            if bit_verdict == "padded": auth_badge, auth_desc = f"🔴 Fake 24-Bit / Padded ({bit_confidence*100:.0f}%)", bit_detail
            elif bit_verdict == "dithered_upscale": auth_badge, auth_desc = f"🟡 Possible Dithered Upscale ({bit_confidence*100:.0f}%)", bit_detail
            elif sample_rate_meta >= 88200 and (cutoff_hz/1000.0) >= 24.0: auth_badge, auth_desc = "🟢 Hi-Res Lossless", f"Genuine extension to {cutoff_hz/1000.0} kHz."
            elif hole_ratio > 0.15 and cliff_drop < 15.0 and (cutoff_hz/1000.0) >= 19.0: auth_badge, auth_desc = "🔴 Fake Lossless (Lossy)", f"Spectral hole {hole_ratio*100:.1f}%. Typical AAC/Opus transcode."
            elif cliff_drop >= 18.0 and (cutoff_hz/1000.0) <= 20.5 and mastering and mastering['clipping'] > 50: auth_badge, auth_desc = "🟢 Lossless · CD Quality (Hot Master)", "Clipping generated harmonics."
            elif cliff_drop >= 18.0 and (cutoff_hz/1000.0) <= 20.5: auth_badge, auth_desc = "🔴 Fake Lossless / Upscale", "Hard brick-wall cliff detected."
            elif (cutoff_hz/1000.0) > 20.0 or cliff_drop < 16.0: auth_badge, auth_desc = f"🟢 Lossless · {'Studio Master (24-bit)' if bit_depth == 24 else 'CD Quality'}", "Clean high-frequency response."
            else: auth_badge, auth_desc = "🟡 Inconclusive / Filtered", "Unusual slope detected."
        else:
            auth_badge, auth_desc = ("🟢 Standard Lossy", "Normal brick-wall detected.") if cliff_drop >= 18.0 else ("🟢 High-Bitrate Lossy", "Gradual roll-off. Excellent quality.")

        return {"title": title, "artist": artist, "format": format_name, "bit_depth": bit_depth, "sample_rate": sample_rate_meta, "channel_str": channel_str, "cutoff": round(cutoff_hz/1000.0, 1), "cliff_drop": round(cliff_drop, 1), "auth_badge": auth_badge, "auth_desc": auth_desc, "mastering": mastering}
    except Exception as e: return None

@app.on_message(filters.command(["spectrogram", "spec"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def tg_spectrogram_cmd(client: Client, message: Message):
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
        elif replied.document or replied.video or replied.audio or replied.voice:
            media_msg = replied

    if not url and not media_msg:
        return await message.reply("❌ Usage: `/spec <link>` or reply to a file/link.")

    status_msg = await message.reply("📉 <b>Downloading & Analyzing Audio...</b>", parse_mode=enums.ParseMode.HTML)
    
    temp_dir = Path(f"./temp_sox_{message.from_user.id}_{int(time.time())}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    original_file = temp_dir / "audio_input.dat"
    wav_file = temp_dir / "converted.wav"
    output_img = temp_dir / "spectrogram.png"

    try:
        # 1. DOWNLOAD LOGIC (FULL FILE)
        if url:
            if "t.me" in url or "telegram.me" in url:
                parsed = _parse_source_link(url)
                chat_id = parsed.get("chat_id")
                msg_id = parsed.get("msg_id")
                
                uclient = USER_CLIENTS.get(message.from_user.id)
                if not uclient or not uclient.is_connected:
                    return await status_msg.edit_text("❌ Telegram session not active. Please /login.")
                    
                msg = await uclient.get_messages(chat_id, msg_id)
                if msg.empty: return await status_msg.edit_text("❌ Message not found or inaccessible.")
                await uclient.download_media(msg, file_name=str(original_file))
            else:
                await full_download_http(url, original_file)
        else:
            await client.download_media(media_msg, file_name=str(original_file))

        # 2. CONVERSION
        await status_msg.edit_text("📉 <b>Running DSP Mathematics...</b>", parse_mode=enums.ParseMode.HTML)
        ffmpeg_cmd = ["ffmpeg", "-i", str(original_file), "-vn", "-ac", "2", "-c:a", "pcm_f32le", str(wav_file), "-y"]
        process = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        await process.wait()
        
        if not wav_file.exists(): return await status_msg.edit_text("❌ Audio Extraction Failed.")

        # 3. STATS & SOX
        stats = generate_audio_stats_dsp(str(wav_file), str(original_file), "Audio Analysis")
        if not stats: return await status_msg.edit_text("❌ DSP Processing Failed.")

        sox_cmd = ["sox", str(wav_file), "-n", "spectrogram", "-o", str(output_img), "-x", "1000", "-Y", "800", "-c", "Audio", "-t", " "]
        process_sox = await asyncio.create_subprocess_exec(*sox_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await process_sox.communicate()

        if not output_img.exists(): return await status_msg.edit_text("❌ SoX Image Generation Failed.")

        # 4. CAPTION BUILDING
        m = stats['mastering']
        mastering_text = ""
        if m:
            phase_warn = "⚠️ Mono risk" if m['correlation'] < -0.2 else "Phase OK"
            dc_warn = "⚠️ Defect" if m['dc_offset'] > -60.0 else "Clean"
            mastering_text = (
                f"\n<b>— MASTERING ANALYSIS —</b>\n"
                f"🎚 <b>Dynamic Range:</b> <code>DR {m['dr']}</code>\n"
                f"🔊 <b>Loudness (LUFS):</b> <code>{m['lufs']:.1f} LUFS</code>\n"
                f"📈 <b>Peak / RMS:</b> <code>{m['peak']:.2f} dBFS</code> / <code>{m['rms']:.2f} dB</code>\n"
                f"💥 <b>Clipping Events:</b> <code>{m['clipping']}</code>\n"
                f"⚖️ <b>Stereo Correl:</b> <code>{m['correlation']:.2f} ({phase_warn})</code>\n"
                f"🔌 <b>DC Offset:</b> <code>{m['dc_offset']:.1f} dBFS ({dc_warn})</code>\n"
                f"🏷 <b>Score:</b> {m['grade']}\n"
            )

        caption = (
            f"📊 <b>Audio Analysis: Fidelity & Mastering</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<blockquote expandable>"
            f"<b>— FIDELITY & AUTHENTICITY —</b>\n"
            f"📀 <b>Container:</b> <code>{stats['format']} • {stats['channel_str']} • {stats['bit_depth']}-bit • {stats['sample_rate']/1000} kHz</code>\n"
            f"📈 <b>Bandwidth Cutoff:</b> <code>{stats['cutoff']} kHz</code>\n"
            f"🧱 <b>Cliff Drop:</b> <code>{stats['cliff_drop']:.1f} dB</code>\n"
            f"🔍 <b>Authenticity:</b> {stats['auth_badge']}\n"
            f"<i>{stats['auth_desc']}</i>\n"
            f"{mastering_text}"
            f"</blockquote>\n"
            f"⚡ <b>RESULT:</b> {stats['auth_badge']}"
        )

        await message.reply_photo(photo=str(output_img), caption=caption, parse_mode=enums.ParseMode.HTML)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
    finally:
        import shutil
        try: shutil.rmtree(str(temp_dir), ignore_errors=True)
        except: pass
            
# ==============================================================================
# --- LIVE WATCHER ENGINE (WITH UNIVERSAL QUEUE & CATCH-UP) ---
# ==============================================================================

from pyrogram.handlers import MessageHandler

WATCHER_QUEUES = defaultdict(asyncio.Queue)
WATCHER_WORKERS = {}

async def start_watcher_worker(wid_str):
    """Ensure exactly one live worker task exists for this watcher."""
    task = WATCHER_WORKERS.get(wid_str)
    if task is None or task.done() or task.cancelled():
        WATCHER_WORKERS[wid_str] = asyncio.create_task(watcher_worker_loop(wid_str))

async def watcher_worker_loop(wid_str):
    """Process one watcher's queue serially and keep its checkpoint consistent."""
    queue = WATCHER_QUEUES[wid_str]
    while True:
        msg_id = await queue.get()
        try:
            watcher = await db.db.watchers.find_one({"_id": ObjectId(wid_str)})
            if not watcher:
                continue

            owner_id = watcher["user_id"]
            watcher_db_id = watcher["_id"]
            source_id = watcher["source_id"]
            source_thread = watcher.get("source_thread")
            dest_id = watcher["dest_id"]
            dest_thread = watcher.get("dest_thread")
            delay = max(3, min(int(watcher.get("delay", 3)), 3600))
            is_restricted = watcher.get("is_restricted", False)
            allowed_types = watcher.get("allowed_types", ["Video", "Document"])

            # Prefer the owner's connected user session for sources it can access;
            # otherwise use the bot. This is only an access-selection fallback.
            owner_client = USER_CLIENTS.get(owner_id)
            fetcher = owner_client if (owner_client and owner_client.is_connected) else app

            try:
                msg = await fetcher.get_messages(source_id, msg_id)
            except Exception as fetch_err:
                logger.warning(f"Watcher {wid_str}: could not fetch {source_id}/{msg_id}: {fetch_err}")
                msg = None

            # Never advance the checkpoint merely because an ID was dequeued.
            # Missing/deleted/inaccessible IDs can safely be considered skipped.
            if not msg or msg.empty:
                await db.db.watchers.update_one(
                    {"_id": watcher_db_id},
                    {"$max": {"last_msg_id": int(msg_id)}, "$inc": {"stats.skipped": 1}}
                )
                continue

            msg_type = get_message_type(msg)
            if not msg_type:
                await db.db.watchers.update_one(
                    {"_id": watcher_db_id},
                    {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.skipped": 1}}
                )
                continue

            is_content_protected = (
                getattr(msg, "has_protected_content", False)
                or getattr(msg.chat, "has_protected_content", False)
            )

            await db.db.watchers.update_one(
                {"_id": watcher_db_id}, {"$inc": {"stats.detected": 1}}
            )

            if msg_type not in allowed_types:
                await db.db.watchers.update_one(
                    {"_id": watcher_db_id},
                    {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.skipped": 1}}
                )
                continue

            # Canonical source-topic check. Telegram forum messages expose the
            # thread through message_thread_id; reply fields are only fallbacks
            # for clients/older message objects.
            if source_thread is not None:
                actual_thread = getattr(msg, "message_thread_id", None)
                if actual_thread is None:
                    actual_thread = getattr(msg, "reply_to_top_message_id", None)
                if actual_thread is None:
                    actual_thread = getattr(msg, "reply_to_message_id", None)

                # A topic service message can itself have the topic root ID.
                if actual_thread is None and getattr(msg, "id", None) == int(source_thread):
                    actual_thread = int(source_thread)

                if actual_thread != int(source_thread):
                    await db.db.watchers.update_one(
                        {"_id": watcher_db_id},
                        {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.skipped": 1}}
                    )
                    continue

            if delay > 0:
                await asyncio.sleep(delay)

            processed_successfully = False

            # Fast copy is used only for content the current Telegram API/client
            # permits to copy. Protected-content handling is left to the existing
            # permission-aware path below; this patch does not add any bypass.
            if not is_restricted and not is_content_protected:
                if getattr(msg, "media_group_id", None):
                    group_cache_key = f"{owner_id}_{source_id}_{msg.media_group_id}_{dest_id}_{dest_thread}"
                    if WATCHER_MEDIA_GROUPS.get(group_cache_key):
                        await db.db.watchers.update_one(
                            {"_id": watcher_db_id},
                            {"$max": {"last_msg_id": int(msg.id)}}
                        )
                        continue
                    WATCHER_MEDIA_GROUPS[group_cache_key] = True

                try:
                    await USER_FLOOD_LOCKS[owner_id].wait_if_locked()

                    if getattr(msg, "media_group_id", None):
                        try:
                            m_group = await fetcher.get_media_group(source_id, msg.id)
                        except Exception:
                            m_group = [msg]
                        group_size = len(m_group)

                        try:
                            copy_res = await safe_send(
                                app, owner_id, dest_id, None, True,
                                app.copy_media_group,
                                chat_id=dest_id,
                                from_chat_id=source_id,
                                message_id=msg.id,
                                message_thread_id=dest_thread
                            )
                        except Exception:
                            if owner_client and owner_client.is_connected:
                                copy_res = await safe_send(
                                    owner_client, owner_id, dest_id, None, False,
                                    owner_client.copy_media_group,
                                    chat_id=dest_id,
                                    from_chat_id=source_id,
                                    message_id=msg.id,
                                    message_thread_id=dest_thread
                                )
                            else:
                                copy_res = False

                        if copy_res:
                            processed_successfully = True
                            if delay > 0 and group_size > 1:
                                await asyncio.sleep(delay * (group_size - 1))
                    else:
                        try:
                            copy_res = await safe_send(
                                app, owner_id, dest_id, None, True,
                                app.copy_message,
                                chat_id=dest_id,
                                from_chat_id=source_id,
                                message_id=msg.id,
                                message_thread_id=dest_thread
                            )
                        except Exception:
                            if owner_client and owner_client.is_connected:
                                copy_res = await safe_send(
                                    owner_client, owner_id, dest_id, None, False,
                                    owner_client.copy_message,
                                    chat_id=dest_id,
                                    from_chat_id=source_id,
                                    message_id=msg.id,
                                    message_thread_id=dest_thread
                                )
                            else:
                                copy_res = False
                        if copy_res:
                            processed_successfully = True

                except FloodWait as e:
                    USER_FLOOD_LOCKS[owner_id].set_lock(e.value + 5)
                    await asyncio.sleep(e.value + 5)
                    try:
                        if owner_client and owner_client.is_connected:
                            if getattr(msg, "media_group_id", None):
                                copy_res = await safe_send(
                                    owner_client, owner_id, dest_id, None, False,
                                    owner_client.copy_media_group,
                                    chat_id=dest_id, from_chat_id=source_id,
                                    message_id=msg.id, message_thread_id=dest_thread
                                )
                            else:
                                copy_res = await safe_send(
                                    owner_client, owner_id, dest_id, None, False,
                                    owner_client.copy_message,
                                    chat_id=dest_id, from_chat_id=source_id,
                                    message_id=msg.id, message_thread_id=dest_thread
                                )
                            processed_successfully = bool(copy_res)
                    except Exception as retry_err:
                        logger.warning(f"Watcher {wid_str}: copy retry failed: {retry_err}")
                except Exception as e:
                    logger.warning(f"Watcher {wid_str}: fast copy failed: {e}. Falling back to existing processing path.")

            if processed_successfully:
                await db.db.watchers.update_one(
                    {"_id": watcher_db_id},
                    {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.success": 1}}
                )
                continue

            # Existing heavy-processing path. No new protected-content bypass is
            # introduced here; it uses the file's existing implementation.
            try:
                log_chat_id, log_topic_id = await get_fallback_log_chat(app, "BOT")
                kwargs_status = {
                    "chat_id": log_chat_id,
                    "text": f"⬇️ **Watcher:** Processing ID `{msg.id}`..."
                }
                if log_topic_id:
                    kwargs_status["message_thread_id"] = log_topic_id
                dummy_status = await app.send_message(**kwargs_status)

                task_uuid = uuid.uuid4().hex
                if owner_id not in ACTIVE_PROCESSES:
                    ACTIVE_PROCESSES[owner_id] = {}
                ACTIVE_PROCESSES[owner_id][task_uuid] = {
                    "user": "Watcher",
                    "dest_title_name": watcher.get("dest_title", "Destination"),
                    "source_title": watcher.get("source_title", "Source"),
                    "item": f"Live Watcher ID: {msg.id}",
                    "started": time.time(),
                    "is_watcher": True,
                    "source_id": source_id
                }

                try:
                    result = await handle_private(
                        client=app,
                        acc=owner_client,
                        message=msg,
                        chatid=source_id,
                        msgid=msg.id,
                        index=1,
                        total_count=1,
                        status_message=dummy_status,
                        dest_chat_id=dest_id,
                        dest_thread_id=dest_thread,
                        delay=0,
                        user_id=owner_id,
                        task_uuid=task_uuid,
                        is_restricted=True,
                        allowed_types=allowed_types
                    )
                finally:
                    cleanup_task_memory(owner_id, task_uuid)
                    try:
                        await dummy_status.delete()
                    except Exception:
                        pass

                if result == "SUCCESS" or result is True:
                    await db.db.watchers.update_one(
                        {"_id": watcher_db_id},
                        {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.success": 1}}
                    )
                elif result == "SKIPPED":
                    await db.db.watchers.update_one(
                        {"_id": watcher_db_id},
                        {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.skipped": 1}}
                    )
                else:
                    await db.db.watchers.update_one(
                        {"_id": watcher_db_id},
                        {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.failed": 1}}
                    )
            except Exception as e:
                logger.error(f"Watcher {wid_str} failed for user {owner_id}, message {msg.id}: {e}", exc_info=True)
                await db.db.watchers.update_one(
                    {"_id": watcher_db_id},
                    {"$max": {"last_msg_id": int(msg.id)}, "$inc": {"stats.failed": 1}}
                )

        except Exception as outer_e:
            logger.error(f"Fatal error in watcher worker {wid_str}: {outer_e}", exc_info=True)
        finally:
            queue.task_done()


async def process_watcher_message(client, message):
    chat_id = message.chat.id
    topic_id = getattr(message, "message_thread_id", None)
    if topic_id is None:
        topic_id = getattr(message, "reply_to_top_message_id", None)
    if topic_id is None:
        topic_id = getattr(message, "reply_to_message_id", None)

    cursor = await db.get_watchers_for_source(chat_id, topic_id)
    watchers = await cursor.to_list(length=100)

    # 🟢 FIX: Always merge global chat watchers (source_thread = None)
    # This prevents the bot from ignoring messages inside topics when the whole group is watched.
    if topic_id is not None:
        cursor_global = await db.get_watchers_for_source(chat_id, None)
        watchers.extend(await cursor_global.to_list(length=100))

    # 🟢 Live Listener ONLY pushes IDs to the queue now!
    # Use a bounded recent-event cache rather than remembering only the last
    # event. Bot/user updates can arrive interleaved, so a one-entry cache can
    # still enqueue the same message twice.
    for w in watchers:
        wid = str(w["_id"])

        dedupe_key = (message.chat.id, topic_id, message.id)

        cache = WATCHER_DEDUPE_CACHE[wid]
        if dedupe_key in cache:
            cache.move_to_end(dedupe_key)
            continue
        cache[dedupe_key] = time.time()
        while len(cache) > WATCHER_DEDUPE_LIMIT:
            cache.popitem(last=False)

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
    app.add_handler(MessageHandler(user_watcher_handler, filters.all))

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
            BotCommand("speedtest", "🚀 Test Server Speed"),
            BotCommand("spectrogram", "📉 Audio Spectrogram")
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
            
            user_client.add_handler(MessageHandler(user_watcher_handler, filters.all))
            
            await user_client.start()
            USER_CLIENTS[user_id] = user_client
            logger.info(f"✅ Active: {user_id}")
            
        except Exception as e:
            logger.error(f"❌ Failed to load {user_id}: {e}")

    logger.info(f"🔥 Total Live Listeners: {len(USER_CLIENTS)}")

    # Initialize per-user worker bots on startup
    await init_worker_bots()

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
        source_thread = w.get("source_thread")
        last_processed = int(w.get("last_msg_id", 0) or 0)
        owner_id = w["user_id"]

        owner_client = USER_CLIENTS.get(owner_id)
        fetcher = owner_client if (owner_client and owner_client.is_connected) else app

        # Always start the worker, even when history is temporarily unavailable.
        await start_watcher_worker(wid)

        if last_processed <= 0:
            continue

        try:
            # IMPORTANT: do not manufacture every integer message ID. Telegram
            # message IDs can have gaps (deleted messages, service messages, etc.).
            # Queue actual messages returned by history, oldest first.
            missed = []
            async for m in fetcher.get_chat_history(source_id):
                if not m or m.empty:
                    continue
                if m.id <= last_processed:
                    break
                missed.append(m.id)

            if missed:
                missed.reverse()
                logger.info(
                    f"⚡ Watcher {wid} found {len(missed)} actual missed messages "
                    f"after ID {last_processed}. Queueing chronologically..."
                )
                for missing_id in missed:
                    await WATCHER_QUEUES[wid].put(int(missing_id))

        except Exception as e:
            logger.warning(f"Could not fetch history for Watcher Catch-up {wid}: {e}")

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
        
