import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # --------------------------------------------------------------------------
    # 🔴 COMPULSORY (Core Bot Credentials & Database)
    # --------------------------------------------------------------------------
    # Get your API ID and HASH from my.telegram.org
    API_ID = int(os.environ.get("API_ID", 0) or 0)
    API_HASH = os.environ.get("API_HASH", "").strip()
    
    # Get your Bot Token from @BotFather
    BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
    
    # MongoDB Atlas Connection URI
    DB_URI = os.environ.get("DB_URI", "").strip()
    
    # MongoDB Database name (defaults to DestinyRestrict)
    DB_NAME = os.environ.get("DB_NAME", "").strip()

    # --------------------------------------------------------------------------
    # 🟡 OPTIONAL: LOG CHANNEL & TOPIC ROUTING
    # --------------------------------------------------------------------------
    # Examples:
    #   - Regular Channel or Group: "-1001234567890"
    #   - Specific Forum Topic: "-1001234567890/5" (ChatID/TopicID)
    _raw_log = os.environ.get("LOG_CHANNEL", "").strip()
    if "/" in _raw_log:
        _chat, _thread = _raw_log.split("/", 1)
        LOG_CHANNEL = int(_chat) if _chat.replace("-", "").isdigit() else 0
        LOG_THREAD_ID = int(_thread) if _thread.isdigit() else None
    else:
        LOG_CHANNEL = int(_raw_log) if _raw_log.replace("-", "").isdigit() else 0
        LOG_THREAD_ID = None
        
    # --------------------------------------------------------------------------
    # ⚙️ OPTIONAL: SETTINGS
    # --------------------------------------------------------------------------
    # Port for Hugging Face / Koyeb / Render health checks (defaults to 8080)
    PORT = int(os.environ.get("PORT", 8080))
    
    # Enable or disable user session login (/login command)
    LOGIN_SYSTEM = os.environ.get("LOGIN_SYSTEM", "True").strip().lower() == "true"
    
    # Send error notifications to user/log channel
    ERROR_MESSAGE = os.environ.get("ERROR_MESSAGE", "True").strip().lower() == "true"
    
    # Default delay between consecutive tasks (in seconds)
    WAITING_TIME = int(os.environ.get("WAITING_TIME", 3))

    # --------------------------------------------------------------------------
    # 👥 ACCESS CONTROL (Comma-Separated User IDs)
    # --------------------------------------------------------------------------
    # Format example: "123456789,987654321"
    ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split(",") if x.strip().isdigit()]
    SUDOS = [int(x) for x in os.environ.get("SUDOS", "").split(",") if x.strip().isdigit()]
