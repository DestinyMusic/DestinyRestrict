# -*- coding: utf-8 -*-
import os
import psutil
import time
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
LOG_CHANNEL = int(_raw_log) if _raw_log.replace("-", "").isdigit() else 0

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

HELP_TXT = """<b>📚 BOT'S USAGE GUIDE</b>

▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬✘▬
<blockquote expandable>
<b>🟢 1. SINGLE & BATCH DOWNLOADS</b>
• Send a single link to process one post.
• Send links in a "From - To" format to process multiple files at once.
• Works for both Public and Private links.
• <b>Examples:</b>
  ├ <code>https://t.me/xxxx/1001</code>
  └ <code>https://t.me/c/xxxx/101 - 120</code>

<b>👀 2. LIVE WATCHERS (AUTO-FORWARDING)</b>
• Automatically monitor a source and forward new messages to targets.
• Supports routing to <b>Multiple Targets</b> simultaneously!
• Features built-in <b>Content Filtering</b> (e.g., Only Videos & Docs).
• <b>Setup:</b> Send <code>/watch https://t.me/channel/123</code>
• <b>Manage:</b> Use <code>/watchers</code> to view and delete mappings.

<b>🤖 3. BOT CHATS & RESTRICTED CONTENT</b>
• Send the standard bot/user link and message ID.
• <b>Formats:</b> 
  ├ <code>https://t.me/botusername/4321</code>
  └ <code>https://t.me/123456789/4321</code> (User/Bot ID)
• Bypasses "Saving Restricted Content" limits automatically!

<b>🛠 4. USEFUL COMMANDS</b>
• <code>/dl</code> - Reply to a link to process it.
• <code>/watch</code> - Setup a new live auto-forwarder.
• <code>/watchers</code> - View active watchers & filters.
• <code>/unwatch</code> - Stop watching a source.
• <code>/cancel</code> - Cancel ongoing tasks.
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
        dashboard_msg=None
    ):
        if allowed_types is None:
            allowed_types = ["Video", "Document"]

        query = {
            "user_id": int(user_id),
            "source_id": int(source_id),
            "source_thread": int(source_thread) if source_thread is not None else None
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
                "$setOnInsert": {"stats": {"detected": 0, "success": 0, "skipped": 0, "failed": 0}}
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

db = Database(DB_URI, DB_NAME)

# ==============================================================================
# --- CLIENT & GLOBAL STATE ---
# ==============================================================================

app = Client(
    "RestrictedBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=min(16, (os.cpu_count() or 2) * 4),                 
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
    "log", "pixel", "sos", "mediainfo", "mi"
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

SERVER_UPLOAD_LIMIT = asyncio.Semaphore(int(os.environ.get("SERVER_UPLOAD_LIMIT", 30))) 
USER_SEMAPHORE_LIMIT = 3 
USER_SEMAPHORES = defaultdict(lambda: asyncio.Semaphore(USER_SEMAPHORE_LIMIT))

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

PENDING_TASKS = {}
PROGRESS = {}
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
        if "t.me/b/" in link_text or re.search(r"t\.me/[a-zA-Z0-9_]+bot/", link_text, re.IGNORECASE):
            is_private = True
            if "t.me/b/" in link_text:
                chat_id = parts[1] if len(parts) > 1 else parts[0]
            else:
                chat_id = parts[0]
            
            if len(parts) > 1 and parts[-1].isdigit():
                msg_id = int(parts[-1])
            return False, "🤖 **Bot/User DM Link:** Will route through User Session."
            
        elif "t.me/c/" in link_text:
            is_private = True
            chat_id = int("-100" + parts[0])
            if len(parts) > 1 and parts[-1].isdigit():
                msg_id = int(parts[-1])
        else:
            chat_id = parts[0]
            if len(parts) > 1 and parts[-1].isdigit():
                msg_id = int(parts[-1])
                
            if str(chat_id).isdigit() or str(chat_id).lower().endswith("bot"):
                is_private = True
                if str(chat_id).isdigit():
                    chat_id = int(chat_id)
            
    except Exception as e:
        return None, f"⚠️ **Could not analyze link.** Error: {e}"

    is_temp_client = False
    check_client = app 
    
    if is_private:
        existing_client = USER_CLIENTS.get(user_id)
        if existing_client and existing_client.is_connected:
            check_client = existing_client
            is_temp_client = False
        else:
            user_session = await db.get_session(user_id)
            if not user_session:
                return None, "🔒 **Private Link:** Please /login to verify restrictions."
            
            api_id = await db.get_api_id(user_id)
            api_hash = await db.get_api_hash(user_id)
            check_client = Client(":memory:", session_string=user_session, api_id=api_id, api_hash=api_hash, no_updates=True, ipv6=False)
            is_temp_client = True

    is_restricted = False
    status_msg = ""
    
    try:
        if is_temp_client:
            await check_client.connect()
            
        if msg_id:
            msg = await check_client.get_messages(chat_id, msg_id)
            if getattr(msg.chat, "has_protected_content", False) or getattr(msg, "has_protected_content", False):
                is_restricted = True
                status_msg = "🔒 **Source is RESTRICTED** (Will use Download Mode)"
            else:
                is_restricted = False
                status_msg = "🔓 **Source is PUBLIC/UNRESTRICTED** (Will use Fast Forward)"
        else:
            chat = await check_client.get_chat(chat_id)
            if getattr(chat, "has_protected_content", False):
                is_restricted = True
                status_msg = "🔒 **Channel is RESTRICTED** (Will use Download Mode)"
            else:
                is_restricted = False
                status_msg = "🔓 **Channel is PUBLIC/UNRESTRICTED**"
            
    except Exception as e:
        if "CHANNEL_PRIVATE" in str(e) or "USER_NOT_PARTICIPANT" in str(e):
            status_msg = "⚠️ **Private Chat:** I can't check yet (You need to join first)."
        else:
            status_msg = f"⚠️ **Check Failed:** `{str(e)[:30]}...`"
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
            except Exception as e:
                logger.debug(f"Progress bar edit skipped: {e}")
        
        total_size = rec.get("total", 0)
        if total_size > 0 and total_size < 50 * 1024 * 1024:
            await asyncio.sleep(9) 
        else:
            await asyncio.sleep(20)
            
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
            except Exception as e:
                logger.debug(f"Progress bar edit skipped: {e}")
        
        total_size = rec.get("total", 0)
        if total_size > 0 and total_size < 50 * 1024 * 1024:
            await asyncio.sleep(9) 
        else:
            await asyncio.sleep(20)
            
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
    
    try:
        if not await db.is_user_exist(user_id):
            await db.add_user(user_id, user_name)
            logger.info(f"New user {user_id} saved to database.") 
    except Exception as e:
        logger.error(f"Failed to save user {user_id}: {e}", exc_info=True)

    welcome_video_url = "https://files.catbox.moe/o9azww.mp4"
    welcome_text = (
        f"<b>👋 Hi {message.from_user.mention}, I am the Restricted Content Bot.</b>\n\n"
        "<blockquote expandable>"
        "<b>🛡 Features:</b>\n"
        "• Download Restricted Content\n"
        "• Setup Live Auto-Forwarders (Watchers)\n"
        "• Fast, Multi-Threaded Processing\n\n"
        "<b>🔑 Note:</b> For downloading private restricted content, you need to <code>/login</code> first.\n\n"
        "<b>📚 Know how to use the bot by sending /help</b>\n"
        "</blockquote>"
    )
    
    buttons = [
        [InlineKeyboardButton("❣️ Developer", url = "https://t.me/thanuj66")],
        [InlineKeyboardButton('🔍 sᴜᴘᴘᴏʀᴛ ɢʀᴏᴜᴘ', url='https://t.me/telegram'), InlineKeyboardButton('🤖 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ', url='https://t.me/telegram')]
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
    except Exception as e:
        await client.send_message(
            chat_id=message.chat.id,
            text=welcome_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            reply_to_message_id=message.id,
            parse_mode=enums.ParseMode.HTML
        )

@app.on_message(filters.command(["help"]) & (filters.private | filters.group))
async def send_help(client: Client, message: Message):
    await client.send_message(
        message.chat.id, 
        text=HELP_TXT,
        parse_mode=enums.ParseMode.HTML,
        disable_web_page_preview=True
    )

@app.on_message(filters.command(["cancel"]) & (filters.private | filters.group))
async def send_cancel(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id in PENDING_TASKS:
        del PENDING_TASKS[user_id]
        await message.reply("✅ **Setup process cancelled.** You can send a new link now.")
        return

    user_tasks = ACTIVE_PROCESSES.get(user_id, {})
    if not user_tasks:
        await message.reply("✅ **No active tasks to cancel.**")
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
    
@app.on_callback_query(filters.regex(r"^cancel_") | filters.regex(r"^cancel_task:"))
async def cancel_callback(client: Client, query):
    user_id = query.from_user.id
    data = query.data

    if data == "cancel_setup":
        if user_id in PENDING_TASKS:
            del PENDING_TASKS[user_id]
        await query.message.edit("❌ **Task Setup Cancelled.**")
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
        await query.message.edit("**🛑 Cancelling ALL your tasks...**\n(This may take a moment to stop current downloads)")
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
        await query.message.edit(f"🛑 **Task cancelled:** `{user_tasks[task_uuid].get('item','Task')}`\nIt will stop shortly.")
        return
        
@app.on_callback_query(filters.regex("^close_menu"))
async def close_menu(client, query):
    try:
        await query.message.delete()
    except Exception as e:
        logger.debug(f"Failed to delete close_menu message: {e}")
        await query.answer("Menu closed.")

@app.on_message(filters.command(["log"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def send_log_handler(client: Client, message: Message):
    if os.path.exists("bot.log"):
        await message.reply_document("bot.log", caption="📄 **Bot Logs**\n(Updates automatically)")
    else:
        await message.reply("⚠️ Log file not found yet.")

@app.on_message(filters.command(["pixel"]) & (filters.user(ADMINS) | filters.user(SUDOS)))
async def pixel_bypass_handler(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply(
            "**Usage:**\n`/pixel https://pixeldrain.com/u/xxxx`\n\n"
            "Or multiple comma-separated links:\n"
            "`/pixel link1,link2,link3`"
        )

    input_text = message.text.split(None, 1)[1]
    matches = re.findall(r"pixeldrain\.com/u/([a-zA-Z0-9_-]+)", input_text)
    
    if not matches:
        return await message.reply(
            "❌ **No valid Pixeldrain links found.**\n"
            "Please ensure the links follow the format: `https://pixeldrain.com/u/XXXX`"
        )

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
    await message.reply(reply_text, disable_web_page_preview=True)

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
    await message.reply(msg, quote=True, parse_mode=enums.ParseMode.HTML)
    
@app.on_message(filters.command(["botstats"]) & filters.user(ADMINS))
async def bot_stats_handler(client: Client, message: Message):
    wait = await message.reply("<b>📊 Generating detailed stats...</b>", parse_mode=enums.ParseMode.HTML)
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
    await wait.edit(stats_msg, parse_mode=enums.ParseMode.HTML)

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
    status_msg = await message.reply("<i>Fetching System Stats...</i>", parse_mode=enums.ParseMode.HTML)
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
    except Exception as e:
        await status_msg.edit_text(f"❌ Error fetching system stats: {e}")

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
    await query.message.edit("✅ **Logout cancelled.** Your session is still active and safe!")
    await query.answer()

@app.on_callback_query(filters.regex("^confirm_logout$"))
async def confirm_logout_cb(client, query):
    user_id = query.from_user.id
    
    await query.message.edit("📡 **Connecting to Telegram to terminate session...**")

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
                await query.message.edit("✅ **Session successfully removed from Telegram Devices.**")
            except Exception as e:
                if "terminated" in str(e) or "Connection" in str(e):
                    await query.message.edit("✅ **Session terminated successfully.**")
                else:
                    raise e
            
        except AuthKeyUnregistered:
            await query.message.edit("⚠️ **Session was already invalid.** Cleaning local database...")
        except Exception as e:
            logger.warning(f"Remote logout warning for {user_id}: {e}")
            await query.message.edit("✅ **Local session cleared.** (Remote session might already be gone)")
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

    # Clear the database
    await db.set_session(user_id, session=None)
    await db.set_api_id(user_id, api_id=None)
    await db.set_api_hash(user_id, api_hash=None)
    
    await query.message.reply("**Logout Complete** ♦\n(You are now disconnected)")
    await query.answer()

from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove

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
        
    await query.message.edit("<b>❌ Login Process Cancelled!</b>\n\n*(If the bot still seems stuck waiting for input, simply send /cancel to clear it)*")
    await query.answer("Cancelled", show_alert=False)
    
@app.on_message(filters.private & ~filters.forwarded & filters.command(["login"]))
async def login_handler(bot: Client, message: Message):
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        
    user_data = await db.get_session(message.from_user.id)
    if user_data is not None:
        await message.reply("**You Are Already Logged In. First /logout Your Old Session. Then Do Login.**")
        return  
        
    user_id = int(message.from_user.id)
    
    # 🎛 CREATE THE INLINE CANCEL BUTTON
    cancel_kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_login")]])

    if API_ID != 0 and API_HASH:
        await message.reply("**🔑 Specific API ID and HASH found in variables. Using them automatically...**")
        api_id = API_ID
        api_hash = API_HASH
    else:
        api_id_msg = await bot.ask(user_id, "<b>Send Your API ID.</b>", filters=filters.text, reply_markup=cancel_kb)
        if not api_id_msg or not api_id_msg.text: return
        
        if api_id_msg.text.startswith('/'):
            return await api_id_msg.reply('<b>Process cancelled!</b>')
            
        try:
            api_id = int(api_id_msg.text)
            if api_id < 1000000 or api_id > 99999999:
                 await api_id_msg.reply("**❌ Invalid API ID**\n\nPlease start again with /login.", quote=True)
                 return
        except ValueError:
            await api_id_msg.reply("**API ID must be an integer, start your process again by /login**", quote=True)
            return
        
        api_hash_msg = await bot.ask(user_id, "**Now Send Me Your API HASH**", filters=filters.text, reply_markup=cancel_kb)
        if not api_hash_msg or not api_hash_msg.text: return
        
        if api_hash_msg.text.startswith('/'):
            return await api_hash_msg.reply('<b>Process cancelled!</b>')
            
        api_hash = api_hash_msg.text.strip()

        if not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
             await api_hash_msg.reply("**❌ Invalid API HASH (Must be 32 Hex Characters)**\n\nPlease start again with /login.", quote=True)
             return

    login_text = (
        "🔐 **Login Process Initiated**\n\n"
        "Please send your **Phone Number** in international format.\n"
        "Example: `+1234567890`\n\n"
        "🛡️ *Your session is stored securely locally.*"
    )

    phone_number_msg = await bot.ask(chat_id=user_id, text=login_text, filters=filters.text, reply_markup=cancel_kb)
    if not phone_number_msg or not phone_number_msg.text: return
    
    # 🔥 COMMAND ESCAPE: Catches /sos, /cancel
    if phone_number_msg.text.startswith('/'):
        return await phone_number_msg.reply('<b>Process cancelled!</b>')
        
    phone_number = phone_number_msg.text.strip()
    if not re.fullmatch(r"\+\d{8,15}", phone_number):
         await phone_number_msg.reply('❌ **Invalid phone number format.** Use international format (e.g., +1234567890).')
         return
    
    client_auth = Client(":memory:", api_id=api_id, api_hash=api_hash)
    await client_auth.connect()
    
    await phone_number_msg.reply("Sending OTP...")
    
    try:
        code = await client_auth.send_code(phone_number)
        phone_code_msg = await bot.ask(user_id, "Please check for an OTP in your official Telegram account. If you got it, send OTP here after reading the below format. \n\nIf OTP is `12345`, **please send it as** `1 2 3 4 5`.", filters=filters.text, timeout=600, reply_markup=cancel_kb)
    except PhoneNumberInvalid:
        await phone_number_msg.reply('`PHONE_NUMBER` **is invalid.**')
        await client_auth.disconnect()
        return
        
    if not phone_code_msg or not phone_code_msg.text:
        await client_auth.disconnect()
        return
        
    if phone_code_msg.text.startswith('/'):
        await client_auth.disconnect()
        return await phone_code_msg.reply('<b>Process cancelled!</b>')
        
    try:
        phone_code = phone_code_msg.text.replace(" ", "")
        await client_auth.sign_in(phone_number, code.phone_code_hash, phone_code)
    except PhoneCodeInvalid:
        await phone_code_msg.reply('**OTP is invalid.**')
        await client_auth.disconnect()
        return
    except PhoneCodeExpired:
        await phone_code_msg.reply('**OTP is expired.**')
        await client_auth.disconnect()
        return
    except SessionPasswordNeeded:
        two_step_msg = await bot.ask(user_id, '**Your account has enabled two-step verification. Please provide the password.**', filters=filters.text, timeout=300, reply_markup=cancel_kb)
        
        if not two_step_msg or not two_step_msg.text:
            await client_auth.disconnect()
            return
            
        if two_step_msg.text.startswith('/'):
            await client_auth.disconnect()
            return await two_step_msg.reply('<b>Process cancelled!</b>')
            
        try:
            password = two_step_msg.text
            await client_auth.check_password(password=password)
        except PasswordHashInvalid:
            await two_step_msg.reply('**Invalid Password Provided**')
            await client_auth.disconnect()
            return
            
    string_session = await client_auth.export_session_string()
    await client_auth.disconnect()
    
    if len(string_session) < SESSION_STRING_SIZE:
        return await message.reply('<b>Invalid session string</b>')
        
    is_prem = False
    first_name = ""
    try:
        uclient = Client(":memory:", session_string=string_session, api_id=api_id, api_hash=api_hash)
        await uclient.connect()
        me = await uclient.get_me()
        is_prem = getattr(me, "is_premium", False)
        first_name = me.first_name or "User"
        
        await db.set_session(message.from_user.id, session=string_session)
        await db.set_api_id(message.from_user.id, api_id=api_id)
        await db.set_api_hash(message.from_user.id, api_hash=api_hash)
        
        try:
            await uclient.disconnect()
        except Exception:
            pass
    except Exception as e:
        return await message.reply_text(f"<b>ERROR IN LOGIN:</b> `{e}`")
        
    prem_text = "⭐ <b>Telegram Premium:</b> <code>Active (4GB Uploads Enabled)</code>" if is_prem else "🔹 <b>Account Type:</b> <code>Standard (2GB Upload Limit)</code>"

    success_msg = (
        f"✅ <b>Account Login Successful!</b>\n\n"
        f"👤 <b>Logged in as:</b> <code>{first_name}</code>\n"
        f"{prem_text}\n\n"
        f"<i>If you encounter any AUTH KEY errors later, run /logout and /login again.</i>"
    )
    await bot.send_message(message.from_user.id, success_msg)

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
        return await message.reply_text("**Reply This Command To Your Broadcast Message**")
    sts = await message.reply_text(text='Broadcasting your messages...')
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
        return await message.reply("**Usage:**\n`/watch https://t.me/channel/123`\n(Supports Topics too!)")
    
    link_text = message.command[1]
    wait_msg = await message.reply("🔎 **Analyzing Source...**", quote=True)
    is_restricted, status_text = await check_link_restriction(user_id, link_text)
    
    source_thread_id = None
    clean_text = link_text.replace("https://", "").replace("http://", "").replace("t.me/", "").replace("c/", "").split("?")[0]
    parts = clean_text.strip("/").split("/")
    if len(parts) >= 3 and parts[1].isdigit():
         source_thread_id = int(parts[1])
    
    await wait_msg.delete()
    
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
        return await message.reply("**Usage:** `/unwatch -100xxxx` or `/unwatch -100xxxx 5`")
    try:
        source_id = int(message.command[1])
        source_thread = int(message.command[2]) if len(message.command) == 3 else None
        user_id = message.from_user.id

        if await db.remove_watcher(user_id, source_id, source_thread):
            
            # Intercept and Cancel Active Downloads
            cancelled_tasks = 0
            if user_id in ACTIVE_PROCESSES:
                for tid, info in list(ACTIVE_PROCESSES[user_id].items()):
                    if info.get("is_watcher") and info.get("source_id") == source_id:
                        CANCEL_FLAGS[tid] = True
                        cancelled_tasks += 1

            msg = "✅ **Watcher Removed.**"
            if cancelled_tasks > 0:
                msg += f"\n🛑 Also cancelled `{cancelled_tasks}` ongoing downloads from this watcher."
            await message.reply(msg)
            
        else:
            await message.reply("⚠️ Watcher not found.")
    except Exception as e:
        logger.error(f"Unwatch failed with input {message.command}: {e}", exc_info=True)
        await message.reply("❌ Invalid ID or Database Error.")

@app.on_message(filters.command(["watchers"]) & filters.private)
async def list_watchers(client, message):
    user_id = message.from_user.id
    
    if user_id in ADMINS:
        cursor = await db.get_all_watchers()
    else:
        cursor = await db.get_user_watchers(user_id)
        
    user_watchers = await cursor.to_list(length=100)
    if not user_watchers:
        return await message.reply("💤 **No active watchers found.**")
    
    text = "**👀 Active Watchers Manager**\n\nSelect a watcher to remove:"
    buttons = []
    
    for w in user_watchers:
        src_id = w['source_id']
        src_display = w.get('source_title') or str(src_id)
        dst_display = w.get('dest_title') or str(w['dest_id'])
        
        if len(src_display) > 15: src_display = src_display[:12] + "..."
        if len(dst_display) > 15: dst_display = dst_display[:12] + "..."
        
        label = f"{src_display} ➔ {dst_display}"
        topic = w.get("source_thread") or 0
        callback = f"unwatch_{w['user_id']}_{src_id}_{topic}"
        
        buttons.append([InlineKeyboardButton(f"🗑 {label}", callback_data=callback)])
    
    buttons.append([InlineKeyboardButton("🧨 Cancel All Watchers", callback_data="unwatch_all")])
    buttons.append([InlineKeyboardButton("❌ Close", callback_data="close_menu")])
    
    await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))
    
@app.on_callback_query(filters.regex("^unwatch_"))
async def unwatch_callback(client, query):
    if query.data == "unwatch_all":
        user_id = query.from_user.id
        result = await db.db.watchers.delete_many({'user_id': int(user_id)})
        
        # Intercept and Cancel ALL Active Watcher Downloads
        cancelled_tasks = 0
        if user_id in ACTIVE_PROCESSES:
            for tid, info in list(ACTIVE_PROCESSES[user_id].items()):
                if info.get("is_watcher"):
                    CANCEL_FLAGS[tid] = True
                    cancelled_tasks += 1
                    
        msg = f"✅ **Success!**\n\n🗑 Removed `{result.deleted_count}` active watchers."
        if cancelled_tasks > 0:
            msg += f"\n🛑 Intercepted and Cancelled `{cancelled_tasks}` active watcher downloads."
        await query.message.edit(msg)
        return

    data = query.data.split("_")
    owner_id = int(data[1])
    source_id = int(data[2])
    topic_id = int(data[3])

    query_db = {"user_id": owner_id, "source_id": source_id}
    if topic_id == 0:
        query_db["$or"] = [
            {"user_id": owner_id, "source_id": source_id, "source_thread": None},
            {"user_id": owner_id, "source_id": source_id, "source_thread": {"$exists": False}},
        ]
    else:
        query_db["source_thread"] = topic_id

    watcher = await db.db.watchers.find_one(query_db)
    
    src_name = str(source_id)
    dest_name = "Unknown"
    
    if watcher:
        src_name = watcher.get('source_title') or str(source_id)
        dest_name = watcher.get('dest_title') or str(watcher.get('dest_id'))

    if topic_id == 0:
        await db.db.watchers.delete_many({
            "user_id": owner_id,
            "source_id": source_id,
            "$or": [
                {"source_thread": None},
                {"source_thread": {"$exists": False}},
            ]
        })
    else:
        await db.db.watchers.delete_many({
            "user_id": owner_id,
            "source_id": source_id,
            "source_thread": topic_id
        })

    # Intercept and Cancel SPECIFIC Watcher Downloads
    cancelled_tasks = 0
    if owner_id in ACTIVE_PROCESSES:
        for tid, info in list(ACTIVE_PROCESSES[owner_id].items()):
            if info.get("is_watcher") and info.get("source_id") == source_id:
                CANCEL_FLAGS[tid] = True
                cancelled_tasks += 1

    msg = (
        f"🗑 **Active Watcher Task Removed**\n\n"
        f"From: **{src_name}**\n"
        f"To: **{dest_name}**"
    )
    if cancelled_tasks > 0:
        msg += f"\n\n🛑 **Cancelled `{cancelled_tasks}` active ongoing downloads** originating from this watcher."
        
    await query.message.edit(msg)

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

    wait_msg = await message.reply("🔎 **Analyzing Link...**", quote=True)
    is_restricted, status_text = await check_link_restriction(user_id, link_text)
    await wait_msg.delete()

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
        await message.reply_text(
            "**Usage:**\n"
            "• Reply to a link with `/dl`\n"
            "• Or send `/dl https://t.me/...`"
        )
        return

    wait_msg = await message.reply("🔎 **Analyzing Link...**", quote=True)
    is_restricted, status_text = await check_link_restriction(user_id, link_text)
    await wait_msg.delete()

    if message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        PENDING_TASKS[user_id] = {
            "link": link_text,
            "dest_chat_id": message.chat.id,
            "dest_thread_id": message.message_thread_id,
            "dest_title": message.chat.title or "This Group",
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
        return await query.answer("❌ Task expired. Send link again.", show_alert=True)
    choice = query.data
    
    if choice == "dest_dm":
        PENDING_TASKS[user_id]["dest_chat_id"] = user_id
        PENDING_TASKS[user_id]["dest_thread_id"] = None
        PENDING_TASKS[user_id]["status"] = "waiting_speed_choice" # <<< FIX
        await ask_for_speed(query)
    elif choice == "dest_custom":
        PENDING_TASKS[user_id]["status"] = "waiting_id"
        buttons = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel_setup")]]
        await query.message.edit_text(
            "📝 **Send the Target Chat ID**\n\n"
            "Examples:\n"
            "• Channel/Group: `-100123456789`\n"
            "• Specific Topic: `-100123456789/5`\n\n"
            "⚠️ __Make sure I am an admin in that chat!__",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

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
        await query.answer("❌ Task expired.", show_alert=True)
        return
    
    choice = query.data
    task_data = PENDING_TASKS[user_id]
    
    if choice == "speed_manual":
        PENDING_TASKS[user_id]["status"] = "waiting_speed_input"
        await query.message.edit(
            "⏱ **Enter Delay (Seconds)**\n\n"
            "Every time a new message arrives, I will wait this long before forwarding it.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_setup")]])
        )
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

    if not user_session:
        error_msg = (
            "❌ **You are not logged in.**\n\n"
            "Watcher mode requires your account to 'listen' for new messages.\n"
            "Please use the /login command first before setting this up."
        )
        if hasattr(message, "edit_text"):
            return await message.edit_text(error_msg)
        else:
            return await message.reply(error_msg)

    if user_id not in USER_CLIENTS:
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

    user_client = USER_CLIENTS[user_id]
    try:
        parsed = _parse_source_link(src_link)
        source_id = parsed["chat_id"]
        source_title = "Unknown Source"

        if parsed["kind"] == "invite":
            try:
                await user_client.join_chat(parsed["join_target"])
            except Exception:
                pass
            chat = await user_client.get_chat(parsed["join_target"])
            source_id = chat.id
            source_title = chat.title or str(source_id)

        elif parsed["kind"] == "public":
            chat = await user_client.get_chat(parsed["join_target"])
            source_id = chat.id
            source_title = chat.title or str(source_id)
            try:
                await user_client.join_chat(parsed["join_target"])
            except Exception:
                pass

        else:
            chat = await user_client.get_chat(source_id)
            source_title = chat.title or str(source_id)

    except Exception as e:
        return await message.reply(
            "❌ **Could not access Source.**\n"
            "Make sure your User Account is a member of that channel/group.\n"
            f"Error: `{e}`"
        )

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
        dashboard_msg=message.id
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
                {"user_id": user_id, "source_id": source_id, "source_thread": data.get("source_thread_id")},
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
        await app.send_message(chat_id, text, message_thread_id=topic_id)
    except Exception as e:
        print(f"❌ Failed to send log: {e}")

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
    
    await send_log(f"▶️ **Task Started**\nUser: `{user_id}`\nLink: `{task_data['link'][:40]}...`")

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
    
    # 1. Force resolve the string username to a strict Integer ID first!
    actual_chat_id = await resolve_to_id(acc, chatid)

    try:
        msg = await acc.get_messages(actual_chat_id, msgid)
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
            # Bot copies using resolved Integer ID
            copy_res = await client.copy_message(chat_id=dest_chat_id, from_chat_id=actual_chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            if not copy_res: # FIX: Force Exception if Pyrogram returns None
                raise ValueError("Bot copy returned None (Bot lacks direct access)")
            return "SUCCESS"
        except Exception as e1:
            logger.warning(f"Bot copy failed for {msgid}: {e1}. Falling back to User Session...")
            # Fallback to User Session copying
            try:
                owner_copy = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=actual_chat_id, message_id=msgid, message_thread_id=dest_thread_id)
                return "SUCCESS" if owner_copy else "FAILED"
            except Exception as e2:
                logger.error(f"User Session copy also failed for {msgid}: {e2}")
                return "FAILED"
    except FloodWait as e:
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
        try:
            owner_copy = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=actual_chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            return "SUCCESS" if owner_copy else "FAILED"
        except Exception as e3:
            logger.error(f"FloodWait recovery copy failed for {msgid}: {e3}")
            return "FAILED"
    except Exception as e:
        logger.error(f"Total copy failure for {msgid}: {e}")
        return "FAILED"

async def process_links_logic(client: Client, message: Message, text: str, dest_chat_id=None, dest_thread_id=None, dest_title="Direct Message", delay=3, acc_user_id=None, task_uuid=None, is_restricted=False, allowed_types=None):
    user_id = acc_user_id or (message.from_user.id if message.from_user else 0)
    user_mention = message.from_user.mention if message.from_user else f"User({user_id})"
    
    if user_id not in ACTIVE_PROCESSES: ACTIVE_PROCESSES[user_id] = {}
    if not task_uuid: task_uuid = uuid.uuid4().hex
    
    ACTIVE_PROCESSES[user_id][task_uuid] = {
        "user": user_mention, 
        "dest_title_name": dest_title,
        "item": text[:50]+"...", 
        "started": time.time()
    }

    if dest_chat_id is None: dest_chat_id = message.chat.id
    if dest_thread_id is None: dest_thread_id = message.message_thread_id

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
                return await message.reply("❌ Invalid link format. Send a valid Telegram post link with a message ID.")

            total_count = max(1, toID - fromID + 1)

            user_data = await db.get_session(user_id)
            if not user_data:
                await message.reply("**/login First.**")
                return
                
            is_temp_acc = False
            acc = USER_CLIENTS.get(user_id)
            
            if not acc or not acc.is_connected:
                api_id = await db.get_api_id(user_id)
                api_hash = await db.get_api_hash(user_id)
                
                acc = Client(
                    f"User_{user_id}", 
                    session_string=user_data, 
                    api_hash=api_hash, 
                    api_id=api_id, 
                    no_updates=False, # Must be False for watchers
                    workers=4,
                    sleep_threshold=60,
                    ipv6=False
                )
                # Attach watcher handler to the temporary client too
                acc.add_handler(MessageHandler(user_watcher_handler, filters.channel | filters.group | filters.private))
                await acc.start()
                USER_CLIENTS[user_id] = acc
                is_temp_acc = True
            
            try:
                source_ref = parsed_source.get("chat_id")
                if source_ref is None:
                    return await message.reply("❌ Could not resolve source chat.")

                source_chat = await acc.get_chat(source_ref)
                source_title = source_chat.title or source_chat.first_name or "Source Chat"
                
                # --- NEW CRITICAL FIX: CACHE INTEGER ID & TYPE ---
                ACTUAL_CHAT_ID = source_chat.id
                IS_PUBLIC_LINK = isinstance(source_ref, str) and not str(source_ref).lstrip('-').isdigit()
                # -------------------------------------------------
                
            except Exception as e: 
                logger.warning(f"Could not fetch chat title for {source_ref}: {e}")
                ACTUAL_CHAT_ID = source_ref # Fallback
                IS_PUBLIC_LINK = isinstance(source_ref, str) and not str(source_ref).lstrip('-').isdigit()

            ACTIVE_PROCESSES[user_id][task_uuid].update({"source_title": source_title, "total": total_count, "current": 0})
            status_text_header = f"**Batch Task Started!** 🚀\n"
            if filter_thread_id:
                status_text_header += f"**Filter:** `Topic {filter_thread_id} Only` 🎯\n"

            if is_restricted:
                status_message = await client.send_message(
                    message.chat.id,
                    f"⚡ **Initializing Task...**\n{status_text_header}\nSource: {source_title}\nTotal Files: {total_count}",
                    reply_to_message_id=message.id,
                    message_thread_id=message.message_thread_id
                )
            else:
                status_message = await client.send_message(
                    message.chat.id,
                    f"{status_text_header}\n\n{generate_bar(0)}\n\n"
                    f"**Source:** {source_title}\n**Destination :** {dest_title}\n"
                    f"**Total:** {total_count}\n**Processed:** 0\n**Success:** 0 | **Skipped:** 0\n**Failed:** 0\n**ETA:** ...",
                    reply_to_message_id=message.id
                )

            last_update_time = time.time()
            inner_header = f"Filter: Topic {filter_thread_id} Only 🎯" if filter_thread_id else ""

            for index, msgid in enumerate(range(fromID, toID+1), start=1):
                loop_start_time = time.time()

                if task_uuid in ACTIVE_PROCESSES.get(user_id, {}):
                    ACTIVE_PROCESSES[user_id][task_uuid]["current"] = index

                if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)):
                    was_cancelled = True; break

                is_success = False
                try:
                    # USE THE CACHED INTEGER ID INSTEAD OF RESOLVING EVERY LOOP
                    chatid = ACTUAL_CHAT_ID
                    
                    if IS_PUBLIC_LINK and not is_restricted:
                        task_result = await handle_public_unrestricted(
                            client, acc, chatid, msgid, dest_chat_id, dest_thread_id, 
                            user_id, task_uuid, filter_thread_id, allowed_types
                        )
                    else:
                        # Unchanged fallback for all Private/Restricted files
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
                        await status_message.edit_text(f"❌ **Task Cancelled automatically**\nReason: FloodWait too long ({e.value}s).")
                        was_cancelled = True
                        break

                    wait_msg = f"⏳ **Rate Limiting Detected**\nSleeping for {e.value} seconds..."
                    try: 
                        if not is_restricted: await status_message.edit_text(wait_msg)
                    except: pass
                    
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
                        except Exception as e: 
                            logger.debug(f"Failed to edit master dashboard: {e}")
                    
        except Exception as e:
            await send_log(f"❌ **Task Crashed**\nUser: `{user_id}`\nError: `{e}`")

        finally:
            cleanup_task_memory(user_id, task_uuid)
            
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
                if batch_temp.ACTIVE_TASKS.get(user_id, 0) <= 0:
                    # ONLY stop if they also have ZERO active watchers in the database
                    w_count = await db.db.watchers.count_documents({"user_id": user_id})
                    if w_count == 0:
                        try: await acc.stop()
                        except: pass
                        USER_CLIENTS.pop(user_id, None)

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
            
            try: await client.send_message(message.chat.id, final_text, reply_to_message_id=message.id)
            except: pass
            try: await status_message.delete()
            except: pass

# ==============================================================================
# --- 1. UTILITY: ID RESOLVER ---
# ==============================================================================
async def resolve_to_id(client, chat_ref):
    """
    Resolves public string usernames (e.g., 'MundoLossless') to strict integer 
    IDs so Pyrogram can access them flawlessly like private channels.
    """
    try:
        if isinstance(chat_ref, str) and not chat_ref.lstrip('-').isdigit():
            chat = await client.get_chat(chat_ref)
            return chat.id
        return int(chat_ref)
    except Exception as e:
        logger.error(f"Failed to resolve {chat_ref}: {e}")
        return chat_ref

# ==============================================================================
# --- 2. MESSAGE FETCHER & VALIDATOR ---
# ==============================================================================
async def _fetch_and_validate_msg(acc, chatid, msgid, user_id, filter_thread_id, allowed_types, task_uuid):
    try:
        msg = await acc.get_messages(chatid, msgid)
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
    
    # 1. Force resolve public links to internal IDs (Fixes the MundoLossless bug)
    actual_chat_id = await resolve_to_id(acc, chatid)

    # 2. Determine link type
    is_public = isinstance(chatid, str) and not chatid.lstrip('-').isdigit()
    is_live_watch = (delay == 0 and status_message and "Watcher" in getattr(status_message, "text", ""))

    # 3. Pre-fetch and validate message
    msg, msg_type = await _fetch_and_validate_msg(acc, actual_chat_id, msgid, user_id, filter_thread_id, allowed_types, task_uuid)
    if not msg:
        return "SKIPPED" # <--- Tell the main loop to mark it as Skipped!

    kwargs = {
        "msg": msg, "msg_type": msg_type, "index": index, "total_count": total_count, 
        "status_message": status_message, "dest_chat_id": dest_chat_id, "dest_thread_id": dest_thread_id,
        "delay": delay, "user_id": user_id, "task_uuid": task_uuid, "header_text": header_text
    }

    # 4. Route the task
    is_content_protected = is_restricted or getattr(msg, "has_protected_content", False) or getattr(msg.chat, "has_protected_content", False)
    
    if not is_content_protected:
        if is_live_watch:
            return await handle_unrestricted_live(client, acc, actual_chat_id, msgid, **kwargs)
        elif is_public:
            return await handle_unrestricted_public(client, acc, actual_chat_id, msgid, **kwargs)
        else:
            return await handle_unrestricted_private(client, acc, actual_chat_id, msgid, **kwargs)
    else:
        if is_live_watch:
            return await handle_restricted_live(client, acc, actual_chat_id, msgid, **kwargs)
        elif is_public:
            return await handle_restricted_public(client, acc, actual_chat_id, msgid, **kwargs)
        else:
            return await handle_restricted_private(client, acc, actual_chat_id, msgid, **kwargs)

# ==============================================================================
# --- 🟢 UNRESTRICTED ROUTES ---
# ==============================================================================

async def _execute_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, user_id):
    """Core copy logic for Unrestricted Private types."""
    if msg_type == "Text":
        try:
            await client.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return True
        except Exception:
            try:
                await acc.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                return True
            except:
                return False
            
    try:
        await USER_FLOOD_LOCKS[user_id].wait_if_locked()
        try:
            await client.copy_message(chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            return True
        except Exception:
            owner_copy = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            return bool(owner_copy)
    except FloodWait as e:
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
        try:
            await acc.copy_message(chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            return True
        except Exception:
            return False
    except Exception:
        return False

async def _execute_public_live_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, user_id):
    """Fixed copy logic specifically for Public links and Live Watchers."""
    if msg_type == "Text":
        try:
            await client.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return True
        except Exception:
            try:
                await acc.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                return True
            except:
                return False
            
    try:
        await USER_FLOOD_LOCKS[user_id].wait_if_locked()
        try:
            copy_res = await client.copy_message(chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            if not copy_res: # FIX: Force fallback if Pyrogram returns None
                raise ValueError("Bot copy returned None")
            return True
        except Exception:
            owner_copy = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            return bool(owner_copy)
    except FloodWait as e:
        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5)
        await asyncio.sleep(e.value + 5)
        try:
            owner_copy = await acc.copy_message(chat_id=dest_chat_id, from_chat_id=chat_id, message_id=msgid, message_thread_id=dest_thread_id)
            return bool(owner_copy)
        except Exception:
            return False
    except Exception:
        return False

# 1 Public Link
async def handle_unrestricted_public(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, **kwargs):
    user_id = kwargs.get("user_id")
    return await _execute_public_live_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, user_id)

# 2 Pvt link
async def handle_unrestricted_private(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, **kwargs):
    user_id = kwargs.get("user_id")
    return await _execute_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, user_id)

# 3 Live watch
async def handle_unrestricted_live(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, **kwargs):
    user_id = kwargs.get("user_id")
    return await _execute_public_live_unrestricted_copy(client, acc, chat_id, msgid, dest_chat_id, dest_thread_id, msg, msg_type, user_id)

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


# ==============================================================================
# --- CORE RESTRICTED DOWNLOAD / UPLOAD ENGINE ---
# ==============================================================================
async def _execute_restricted_download_upload(client, acc, chatid, msgid, dest_chat_id, dest_thread_id, msg, msg_type, index, total_count, status_message, delay, user_id, task_uuid, header_text):
    """Contains all original 300+ lines of fallback downloading and splitting code."""
    
    # --- FIX: Preserve pure text messages with clickable links instantly ---
    if msg_type == "Text":
        try:
            await client.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
            return True
        except Exception:
            try:
                await acc.send_message(dest_chat_id, msg.text, entities=msg.entities, message_thread_id=dest_thread_id)
                return True
            except: return False

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

    down_task = None
    if status_message:
        down_task = asyncio.create_task(downstatus(client, status_message, status_message.chat.id, index, total_count, header_text))
        
    file_path = None
    ph_path = None
    download_success = False

    split_limit = 2000 * 1024 * 1024 
    is_premium = False
    try:
        me = acc.me if acc.me else await acc.get_me()
        if me.is_premium: is_premium = True
    except Exception: 
        pass

    try: 
        for attempt in range(3):
            if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): return False
            try:
                msg_fresh = await acc.get_messages(chatid, msgid)
                if msg_fresh.empty: return False
                
                file_size = 0
                if msg_fresh.document: file_size = msg_fresh.document.file_size
                elif msg_fresh.video: file_size = msg_fresh.video.file_size
                elif msg_fresh.audio: file_size = msg_fresh.audio.file_size

                if file_size > split_limit:
                    if is_premium and LOG_CHANNEL:
                        if status_message: await status_message.edit_text(f"🚀 **Large File Detected ({_pretty_bytes(file_size)})**\nDownloading for Premium Bypass...")
                        file_path = await acc.download_media(msg_fresh, file_name=str(file_path_to_save), progress=progress, progress_args=[status_message, "down", task_uuid])
                        if down_task and not down_task.done(): down_task.cancel()
                        
                        if status_message: await status_message.edit_text(f"☁️ **Uploading to Log Server (Premium Bypass)...**")
                        log_chat_id = int(str(LOG_CHANNEL).split("/")[0]) if "/" in str(LOG_CHANNEL) else int(LOG_CHANNEL)
                        
                        up_task = asyncio.create_task(upstatus(client, status_message, status_message.chat.id, index, total_count, header_text)) if status_message else None
                        caption = msg.caption if msg.caption else ""
                        caption_entities = msg.caption_entities if getattr(msg, "caption_entities", None) else None
                        sent_msg = None
                        
                        try:
                            kwargs = {"chat_id": log_chat_id, "caption": caption}
                            if caption_entities: kwargs["caption_entities"] = caption_entities
                            p_args = [status_message, "up", task_uuid]
                            
                            if "Document" == msg_type: sent_msg = await acc.send_document(document=file_path, progress=progress, progress_args=p_args, **kwargs)
                            elif "Video" == msg_type: sent_msg = await acc.send_video(video=file_path, duration=msg.video.duration, width=msg.video.width, height=msg.video.height, progress=progress, progress_args=p_args, **kwargs)
                            elif "Audio" == msg_type: sent_msg = await acc.send_audio(audio=file_path, progress=progress, progress_args=p_args, **kwargs)
                            else: sent_msg = await acc.send_document(document=file_path, progress=progress, progress_args=p_args, **kwargs)
                            
                            if sent_msg:
                                await client.copy_message(chat_id=dest_chat_id, from_chat_id=log_chat_id, message_id=sent_msg.id, message_thread_id=dest_thread_id)
                        except Exception as up_err:
                            raise up_err
                        finally:
                            if up_task and not up_task.done(): up_task.cancel()
                            try:
                                if file_path and os.path.exists(file_path): os.remove(file_path)
                            except Exception: pass
                        return True
                    else:
                        file_path = await acc.download_media(msg_fresh, file_name=str(file_path_to_save), progress=progress, progress_args=[status_message, "down", task_uuid])
                        if down_task and not down_task.done(): down_task.cancel()
                        
                        if status_message: await status_message.edit_text(f"✂️ **Splitting large file ({_pretty_bytes(file_size)})...**")
                        parts = await split_file_python(file_path, chunk_size=1900*1024*1024)
                        
                        if status_message and f"{status_message.id}:up" in PROGRESS: del PROGRESS[f"{status_message.id}:up"]

                        up_task = asyncio.create_task(upstatus(client, status_message, status_message.chat.id, index, total_count, header_text)) if status_message else None
                        caption = msg.caption if msg.caption else ""
                        caption_entities = msg.caption_entities if getattr(msg, "caption_entities", None) else None
                    
                    async with USER_SEMAPHORES[user_id]:
                        async with SERVER_UPLOAD_LIMIT:
                            for part in parts:
                                if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): raise Exception("CANCELLED")
                                while True:
                                    await USER_FLOOD_LOCKS[user_id].wait_if_locked() 
                                    try:
                                        await client.send_document(dest_chat_id, str(part), caption=caption, caption_entities=caption_entities, message_thread_id=dest_thread_id)
                                        break
                                    except FloodWait as e: 
                                        if e.value > 300: raise e
                                        USER_FLOOD_LOCKS[user_id].set_lock(e.value + 5) 
                                        await asyncio.sleep(e.value + 5)
                                    except Exception:
                                        break
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
                        file_path = await asyncio.wait_for(
                            acc.download_media(msg_fresh, file_name=str(file_path_to_save), progress=progress, progress_args=[status_message, "down", task_uuid]),
                            timeout=1200
                        )
                    except asyncio.TimeoutError:
                        return False
                
                try:
                    thumb = None
                    if msg_fresh.document and msg_fresh.document.thumbs: thumb = msg_fresh.document.thumbs[0]
                    elif msg_fresh.video and msg_fresh.video.thumbs: thumb = msg_fresh.video.thumbs[0]
                    elif msg_fresh.audio and msg_fresh.audio.thumbs: thumb = msg_fresh.audio.thumbs[0]
                    if thumb: ph_path = await acc.download_media(thumb.file_id, file_name=str(task_folder_path / "thumb.jpg"))
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

        # Clean up BOTH memory leaks
        if status_message:
            PROGRESS.pop(f"{status_message.id}:up", None)
            PROGRESS.pop(f"{status_message.id}:down", None)
        up_task = asyncio.create_task(upstatus(client, status_message, status_message.chat.id, index, total_count, header_text)) if status_message else None
        
        caption = msg.caption if msg.caption else None
        caption_entities = msg.caption_entities if getattr(msg, "caption_entities", None) else None
        uploader = client 
        upload_success = False
        
        async with SERVER_UPLOAD_LIMIT:
            async with USER_SEMAPHORES[user_id]:
                while True:
                    if batch_temp.IS_BATCH.get(user_id) or (task_uuid and CANCEL_FLAGS.get(task_uuid)): break
                    
                    await USER_FLOOD_LOCKS[user_id].wait_if_locked() 
                    try:
                        # --- FIX: Dynamically apply caption and hidden links ---
                        kwargs = {"chat_id": dest_chat_id, "message_thread_id": dest_thread_id, "caption": caption}
                        if caption_entities:
                            kwargs["caption_entities"] = caption_entities
                        if ph_path and os.path.exists(ph_path):
                            kwargs["thumb"] = ph_path
                            
                        p_args = [status_message, "up", task_uuid] if status_message else None
                        p_func = progress if status_message else None

                        if msg_type == "Document": await uploader.send_document(document=file_path, progress=p_func, progress_args=p_args, **kwargs)
                        elif msg_type == "Video": await uploader.send_video(video=file_path, duration=getattr(msg.video, 'duration', 0) or 0, width=getattr(msg.video, 'width', 0) or 0, height=getattr(msg.video, 'height', 0) or 0, progress=p_func, progress_args=p_args, **kwargs)
                        elif msg_type == "Audio": await uploader.send_audio(audio=file_path, progress=p_func, progress_args=p_args, **kwargs)
                        elif msg_type == "Photo": await uploader.send_photo(photo=file_path, **kwargs)
                        elif msg_type == "Voice": await uploader.send_voice(voice=file_path, progress=p_func, progress_args=p_args, **kwargs)
                        elif msg_type == "Animation": await uploader.send_animation(animation=file_path, **kwargs)
                        elif msg_type == "Sticker": await uploader.send_sticker(chat_id=dest_chat_id, sticker=file_path, message_thread_id=dest_thread_id)
                        
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
# --- Koyeb health check (optional) ---
# ==============================================================================
try:
    from aiohttp import web
except ImportError:
    web = None

async def _koyeb_health_handler(request):
    return web.Response(text="OK", status=200)

async def start_koyeb_health_check(host: str = "0.0.0.0"):
    if web is None:
        logger.info("aiohttp not installed; Koyeb health check not started.")
        return
    
    # Uses the global PORT variable defined at the top of your script
    global PORT 
    
    app_web = web.Application()
    app_web.router.add_get("/", _koyeb_health_handler)
    app_web.router.add_get("/health", _koyeb_health_handler)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, host, PORT)
    await site.start()
    logger.info(f"Starting Koyeb health check server on port {PORT}...")

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
        return await message.reply("❌ Usage: `/mediainfo <link>` or reply to a file/link.")

    status_msg = await message.reply(f"<i>Generating MediaInfo...</i>", parse_mode=enums.ParseMode.HTML)
    
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
# --- LIVE WATCHER ENGINE ---
# ==============================================================================

from pyrogram.handlers import MessageHandler

async def process_watcher_message(client, message):
    chat_id = message.chat.id
    topic_id = getattr(message, "message_thread_id", None)

    cursor = await db.get_watchers_for_source(chat_id, topic_id)
    watchers = await cursor.to_list(length=100)

    if not watchers and topic_id is not None:
        cursor = await db.get_watchers_for_source(chat_id, None)
        watchers = await cursor.to_list(length=100)

    if not watchers:
        return

    msg_type = get_message_type(message)
    if not msg_type:
        return

    is_content_protected = getattr(message, "has_protected_content", False) or getattr(message.chat, "has_protected_content", False)

    for watcher in watchers:
        owner_id = watcher["user_id"]
        w_topic = watcher.get("source_thread")
        
        # 1. Increment Detected
        await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.detected": 1}})

        allowed_types = watcher.get("allowed_types", ["Video", "Document"])
        if msg_type not in allowed_types:
            # 2. Increment Skipped (Filtered out)
            await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.skipped": 1}})
            continue

        delay = watcher.get("delay", 0)
        is_restricted = watcher.get("is_restricted", False)
        dest_id = watcher["dest_id"]
        dest_thread = watcher.get("dest_thread")

        if delay > 0:
            watcher_key = f"{owner_id}_{chat_id}_{dest_id}"
            now = time.time()
            
            # If it's the first message in a while, just wait the standard delay
            if WATCHER_LAST_RUN.get(watcher_key, 0) < now:
                WATCHER_LAST_RUN[watcher_key] = now + delay
                await asyncio.sleep(delay)
            else:
                # Burst detected! Get in line and calculate exactly how long to wait
                wait_time = WATCHER_LAST_RUN[watcher_key] - now + delay
                WATCHER_LAST_RUN[watcher_key] += delay
                
                # NO CAP: The bot will dutifully queue every single file infinitely!
                await asyncio.sleep(wait_time)
            
        processed_successfully = False

        if not is_restricted and not is_content_protected:
            try:
                await USER_FLOOD_LOCKS[owner_id].wait_if_locked()
                try:
                    copy_res = await app.copy_message(chat_id=dest_id, from_chat_id=chat_id, message_id=message.id, message_thread_id=dest_thread)
                    if copy_res: processed_successfully = True
                except FloodWait as e:
                    raise e 
                except Exception:
                    owner_client = USER_CLIENTS.get(owner_id)
                    if owner_client:
                        try:
                            owner_copy = await owner_client.copy_message(chat_id=dest_id, from_chat_id=chat_id, message_id=message.id, message_thread_id=dest_thread)
                            if owner_copy: processed_successfully = True
                        except FloodWait as e:
                            raise e
            except FloodWait as e:
                USER_FLOOD_LOCKS[owner_id].set_lock(e.value + 5)
                await asyncio.sleep(e.value + 5)
                owner_client = USER_CLIENTS.get(owner_id)
                if owner_client:
                    try:
                        owner_copy = await owner_client.copy_message(chat_id=dest_id, from_chat_id=chat_id, message_id=message.id, message_thread_id=dest_thread)
                        if owner_copy: processed_successfully = True
                    except Exception as err:
                        logger.warning(f"Watcher fast copy retry failed: {err}")
            except Exception as e:
                logger.warning(f"Watcher fast copy failed: {e}. Falling back to download.")

        if processed_successfully:
            # 3. Increment Success (Fast Forward)
            await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.success": 1}})
            continue
            
        # Fallback to Download Mode
        owner_client = USER_CLIENTS.get(owner_id)
        if not owner_client:
            await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.failed": 1}})
            continue

        try:
            log_chat_id, log_topic_id = parse_chat_topic(LOG_CHANNEL) if LOG_CHANNEL else (owner_id, None)
            dummy_status = await app.send_message(
                log_chat_id,
                f"⬇️ **Watcher:** Processing ID `{message.id}`...",
                message_thread_id=log_topic_id
            )

            # --- REGISTRATION START ---
            task_uuid = uuid.uuid4().hex
            if owner_id not in ACTIVE_PROCESSES: 
                ACTIVE_PROCESSES[owner_id] = {}
                
            ACTIVE_PROCESSES[owner_id][task_uuid] = {
                "user": "Watcher", 
                "dest_title_name": watcher.get("dest_title", "Destination"),
                "source_title": watcher.get("source_title", "Source"),
                "item": f"Live Watcher ID: {message.id}", 
                "started": time.time(),
                "is_watcher": True,
                "source_id": chat_id
            }
            # --- REGISTRATION END ---

            result = await handle_private(
                client=app,
                acc=owner_client,
                message=message,
                chatid=chat_id,
                msgid=message.id,
                index=1,
                total_count=1,
                status_message=dummy_status,
                dest_chat_id=dest_id,
                dest_thread_id=dest_thread,
                delay=0,
                user_id=owner_id,
                task_uuid=task_uuid, # <-- NOW USES REGISTERED UUID
                is_restricted=True,
                allowed_types=allowed_types
            )
            
            # Map handle_private results directly to DB Stats
            if result == "SUCCESS" or result is True:
                await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.success": 1}})
            elif result == "SKIPPED":
                await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.skipped": 1}})
            else:
                await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.failed": 1}})

            cleanup_task_memory(owner_id, task_uuid) # Clean up so RAM stays clean!

            try:
                await dummy_status.delete()
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Watcher Fail for {owner_id}: {e}")
            await db.db.watchers.update_one({"user_id": owner_id, "source_id": chat_id, "source_thread": w_topic}, {"$inc": {"stats.failed": 1}})
        
async def user_watcher_handler(client, message):
    await process_watcher_message(client, message)

# ==============================================================================
# --- DASHBOARD UPDATER ---
# ==============================================================================
WATCHER_RENDER_CACHE = {}

async def watcher_dashboard_updater():
    while True:
        await asyncio.sleep(30)
        try:
            # Find all watchers that have a linked dashboard message
            cursor = db.db.watchers.find({"dashboard_chat": {"$ne": None}, "dashboard_msg": {"$ne": None}})
            async for w in cursor:
                wid = str(w["_id"])
                current_stats = w.get("stats", {})
                
                # Compare to memory cache, only edit message if numbers actually changed
                cached = WATCHER_RENDER_CACHE.get(wid)
                if cached == current_stats:
                    continue 

                WATCHER_RENDER_CACHE[wid] = dict(current_stats)

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
                    f"*(Updates dynamically every 30s)*"
                )
                try:
                    await app.edit_message_text(
                        chat_id=w["dashboard_chat"],
                        message_id=w["dashboard_msg"],
                        text=text
                    )
                except Exception as e:
                    if "MESSAGE_NOT_MODIFIED" in str(e): pass 
                    # If message was manually deleted by user, we just ignore it
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

    await app.start()
    logger.info("🤖 Bot Started") 
    
    logger.info("📝 Updating Bot Commands...")
    try:
        public_commands = [
            BotCommand("start", "⚡ Check if bot is alive"),
            BotCommand("help", "📚 View the detailed usage guide"),
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
            BotCommand("mediainfo", "🔍 Technical File MetaData")
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

    asyncio.create_task(start_koyeb_health_check())
    await idle()
    
    await app.stop()
    for uid, client in USER_CLIENTS.items():
        try: await client.stop()
        except: pass
        
if __name__ == "__main__":
    app.run(main())
