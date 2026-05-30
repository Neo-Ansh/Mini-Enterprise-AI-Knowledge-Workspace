# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# ── AI ────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ── Database ──────────────────────────────────────────────────────────
MONGO_CONNECTION_STR = os.getenv("MONGO_CONNECTION_STR")

# ── Auth ──────────────────────────────────────────────────────────────
JWT_SECRET = os.getenv("JWT_SECRET", "change_this_secret_in_production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))  # 8 hours

# ── Startup validation ────────────────────────────────────────────────
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY in .env")

if not MONGO_CONNECTION_STR:
    raise RuntimeError("Missing MONGO_CONNECTION_STR in .env")