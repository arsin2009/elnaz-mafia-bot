import asyncio
import html
import hashlib
import logging
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
    InputMediaPhoto, InputMediaAnimation,
)
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramAPIError

# ============================================================
# ARSIN AUTO REPLY v2 - SINGLE FILE MULTI-USER BUSINESS BOT
# Python 3.10+ | aiogram 3.x
# ============================================================
# Required environment variables:
#   BOT_TOKEN="..."
#   ADMIN_ID="numeric Telegram user ID"
# Install:
#   pip install -U aiogram
# Run:
#   python3 arsin_auto_reply_v2.py
#
# Notes:
# - Each customer must separately connect this bot in Telegram Business settings.
# - Bot /start does not grant access to a personal Telegram account.
# - Manual bank transfer is used; this bot does not verify bank payments automatically.
# - Timed announcement deletion is best-effort and Telegram limits apply.
# - Keep the database file and back it up before replacing an existing deployment.
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip()
ARSIN_OWNER_ID_RAW = os.getenv("ARSIN_OWNER_ID", "7311404671").strip()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "auto_reply.db")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است.")
if not ADMIN_ID_RAW:
    raise RuntimeError("ADMIN_ID تنظیم نشده است.")
try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError as exc:
    raise RuntimeError("ADMIN_ID باید شناسه عددی تلگرام باشد.") from exc
try:
    ARSIN_OWNER_ID = int(ARSIN_OWNER_ID_RAW)
except ValueError as exc:
    raise RuntimeError("ARSIN_OWNER_ID باید شناسه عددی تلگرام باشد.") from exc

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("arsin_auto_reply")
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
# user_id -> (state, optional object_id)
user_states: dict[int, tuple[str, object]] = {}
# Admin announcement media/text held until duration is selected.
pending_announcements: dict[int, dict] = {}


def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def dt_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_dt(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def db_init():
    with closing(db()) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            auto_enabled INTEGER NOT NULL DEFAULT 1,
            custom_reply TEXT NOT NULL DEFAULT '',
            custom_media_type TEXT NOT NULL DEFAULT '',
            custom_media_file_id TEXT NOT NULL DEFAULT '',
            custom_caption TEXT NOT NULL DEFAULT '',
            last_reminder_at TEXT NOT NULL DEFAULT '',
            cooldown_enabled INTEGER NOT NULL DEFAULT 0,
            cooldown_minutes INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS default_reply_cooldowns (
            owner_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            last_sent_at TEXT NOT NULL,
            PRIMARY KEY(owner_id, chat_id)
        );
        CREATE TABLE IF NOT EXISTS business_connections (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            user_chat_id INTEGER NOT NULL,
            is_enabled INTEGER NOT NULL DEFAULT 0,
            can_reply INTEGER NOT NULL DEFAULT 0,
            can_read_messages INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            word TEXT NOT NULL UNIQUE,
            response TEXT NOT NULL,
            private_enabled INTEGER NOT NULL DEFAULT 1,
            group_enabled INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS user_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            response TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            UNIQUE(user_id, word)
        );
        CREATE TABLE IF NOT EXISTS contact_replies (
            owner_id INTEGER NOT NULL,
            contact_id INTEGER NOT NULL,
            response TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(owner_id, contact_id)
        );
        CREATE TABLE IF NOT EXISTS contact_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            contact_id INTEGER NOT NULL,
            word TEXT NOT NULL,
            response TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            UNIQUE(owner_id, contact_id, word)
        );
        CREATE TABLE IF NOT EXISTS contact_book (
            owner_id INTEGER NOT NULL,
            contact_id INTEGER NOT NULL,
            username TEXT NOT NULL DEFAULT '',
            display_name TEXT NOT NULL DEFAULT '',
            added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(owner_id, contact_id)
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            starts_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'payment'
        );
        CREATE TABLE IF NOT EXISTS coupons (
            code TEXT PRIMARY KEY,
            discount_toman INTEGER NOT NULL,
            max_uses INTEGER NOT NULL DEFAULT 0,
            uses INTEGER NOT NULL DEFAULT 0,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS coupon_uses (
            code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(code, user_id)
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            gross_amount INTEGER NOT NULL,
            discount_amount INTEGER NOT NULL DEFAULT 0,
            amount_due INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting_proof',
            proof_type TEXT NOT NULL DEFAULT '',
            proof_file_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT NOT NULL DEFAULT '',
            reviewer_id INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            delete_at TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS announcement_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            announcement_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            deleted INTEGER NOT NULL DEFAULT 0,
            UNIQUE(announcement_id, chat_id, message_id)
        );
        CREATE TABLE IF NOT EXISTS announcement_payloads (
            announcement_id INTEGER PRIMARY KEY,
            payload_type TEXT NOT NULL,
            text_content TEXT NOT NULL DEFAULT '',
            file_id TEXT NOT NULL DEFAULT ''
        );
        """)
        # Preserve contacts configured by older versions in the new "special users" list.
        conn.execute("INSERT OR IGNORE INTO contact_book(owner_id,contact_id,username,display_name) SELECT owner_id,contact_id,'','' FROM contact_replies")
        conn.execute("INSERT OR IGNORE INTO contact_book(owner_id,contact_id,username,display_name) SELECT owner_id,contact_id,'','' FROM contact_keywords")
        defaults = {
            "enabled": "1",
            "general_reply": "سلام! در حال حاضر امکان پاسخ‌گویی ندارم. در اولین فرصت جواب می‌دم.",
            "welcome_text": "خوش اومدی! از منوی زیر می‌تونی پاسخ‌گوی خودکارت رو مدیریت کنی.",
            "join_links": "",
            "subscription_price": "150000",
            "card_number": "",
            "card_holder": "",
            "admin_auto_enabled": "1",
            "admin_reply": "سلام! پیام شما دریافت شد. در اولین فرصت پاسخ می‌دم.",
            "admin_media_type": "",
            "admin_media_file_id": "",
            "admin_caption": "",
            "admin_cooldown_enabled": "0",
            "admin_cooldown_minutes": "1",
        }
        for key, value in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
        conn.commit()
        # Migrations for databases created by the previous version.
        _ensure_column(conn, "business_connections", "can_read_messages", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "auto_enabled", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "users", "custom_reply", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "custom_media_type", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "custom_media_file_id", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "custom_caption", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "last_reminder_at", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "users", "cooldown_enabled", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "users", "cooldown_minutes", "INTEGER NOT NULL DEFAULT 1")
        conn.execute("UPDATE users SET cooldown_minutes=1 WHERE cooldown_minutes=10")
        conn.commit()


def _ensure_column(conn, table, column, definition):
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def get_setting(key: str, default: str = "") -> str:
    with closing(db()) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default


def set_setting(key: str, value: str):
    with closing(db()) as conn:
        conn.execute("""INSERT INTO settings(key,value) VALUES(?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, str(value)))
        conn.commit()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def is_arsin_owner(user_id: int) -> bool:
    """Recognize either configured Arsin owner ID or the bot admin ID."""
    return user_id in {ARSIN_OWNER_ID, ADMIN_ID}


def ensure_user(user_id: int, first_name: str = "", username: str = ""):
    with closing(db()) as conn:
        conn.execute("""INSERT INTO users(user_id,first_name,username)
            VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            first_name=excluded.first_name, username=excluded.username""",
            (user_id, first_name or "", username or ""))
        conn.commit()


def get_user(user_id: int):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def all_users():
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()


def normalize(value: str) -> str:
    replacements = {"ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "ؤ": "و", "إ": "ا", "أ": "ا", "ٱ": "ا", "\u200c": " ", "\u200f": "", "\u200e": ""}
    value = (value or "").strip().lower()
    for old, new in replacements.items():
        value = value.replace(old, new)
    return " ".join(value.split())


def get_global_keywords():
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM keywords ORDER BY id DESC").fetchall()


def get_user_keywords(user_id: int):
    with closing(db()) as conn:
        if is_arsin_owner(user_id):
            ids = sorted({ARSIN_OWNER_ID, ADMIN_ID})
            marks = ",".join("?" for _ in ids)
            return conn.execute(f"SELECT * FROM user_keywords WHERE user_id IN ({marks}) ORDER BY id DESC", ids).fetchall()
        return conn.execute("SELECT * FROM user_keywords WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()


def find_keyword(text: str, is_group: bool, owner_id: int):
    normalized = normalize(text)
    # User's own keywords are checked first; global/admin keywords follow.
    own = get_user_keywords(owner_id)
    for row in sorted(own, key=lambda r: len(normalize(r["word"])), reverse=True):
        word = normalize(row["word"])
        if row["enabled"] and word and word in normalized:
            return row["response"]
    for row in sorted(get_global_keywords(), key=lambda r: len(normalize(r["word"])), reverse=True):
        enabled = row["group_enabled"] if is_group else row["private_enabled"]
        word = normalize(row["word"])
        if enabled and word and word in normalized:
            return row["response"]
    return None


def owner_scope_ids(owner_id: int) -> list[int]:
    # Arsin's personal configuration is shared across the configured owner/admin IDs.
    if is_arsin_owner(owner_id):
        return sorted({ARSIN_OWNER_ID, ADMIN_ID})
    return [int(owner_id)]


def find_contact_keyword(text: str, owner_id: int, contact_id: int):
    normalized = normalize(text)
    ids = owner_scope_ids(owner_id)
    marks = ",".join("?" for _ in ids)
    with closing(db()) as conn:
        rows = conn.execute(
            f"SELECT * FROM contact_keywords WHERE owner_id IN ({marks}) AND contact_id=? AND enabled=1",
            [*ids, int(contact_id)],
        ).fetchall()
    for row in sorted(rows, key=lambda r: len(normalize(r["word"])), reverse=True):
        word = normalize(row["word"])
        if word and word in normalized:
            return row["response"]
    return None


def get_contact_reply(owner_id: int, contact_id: int) -> str:
    ids = owner_scope_ids(owner_id)
    marks = ",".join("?" for _ in ids)
    with closing(db()) as conn:
        row = conn.execute(
            f"SELECT response FROM contact_replies WHERE owner_id IN ({marks}) AND contact_id=? AND trim(response)<>'' ORDER BY updated_at DESC LIMIT 1",
            [*ids, int(contact_id)],
        ).fetchone()
    return str(row["response"]) if row else ""


def save_contact_reply(owner_id: int, contact_id: int, response: str):
    with closing(db()) as conn:
        for scoped_owner in owner_scope_ids(owner_id):
            conn.execute(
                "INSERT INTO contact_replies(owner_id,contact_id,response,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(owner_id,contact_id) DO UPDATE SET response=excluded.response,updated_at=CURRENT_TIMESTAMP",
                (scoped_owner, int(contact_id), response[:4096]),
            )
        conn.commit()


def save_contact_keyword(owner_id: int, contact_id: int, word: str, response: str):
    with closing(db()) as conn:
        for scoped_owner in owner_scope_ids(owner_id):
            existing = conn.execute(
                "SELECT id FROM contact_keywords WHERE owner_id=? AND contact_id=? AND lower(word)=lower(?) ORDER BY id DESC LIMIT 1",
                (scoped_owner, int(contact_id), word),
            ).fetchone()
            if existing:
                conn.execute("UPDATE contact_keywords SET word=?,response=?,enabled=1 WHERE id=?",
                             (word, response[:4096], existing["id"]))
            else:
                conn.execute("INSERT INTO contact_keywords(owner_id,contact_id,word,response,enabled) VALUES(?,?,?,?,1)",
                             (scoped_owner, int(contact_id), word, response[:4096]))
        conn.commit()


def save_contact_book(owner_id: int, contact_id: int, username: str = "", display_name: str = ""):
    with closing(db()) as conn:
        for scoped_owner in owner_scope_ids(owner_id):
            conn.execute(
                "INSERT INTO contact_book(owner_id,contact_id,username,display_name,added_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(owner_id,contact_id) DO UPDATE SET username=excluded.username,display_name=excluded.display_name,added_at=CURRENT_TIMESTAMP",
                (scoped_owner, int(contact_id), (username or "").lstrip("@")[:64], (display_name or "")[:128]),
            )
        conn.commit()


def get_contact_book(owner_id: int):
    ids = owner_scope_ids(owner_id)
    marks = ",".join("?" for _ in ids)
    with closing(db()) as conn:
        return conn.execute(
            f"SELECT contact_id, MAX(username) AS username, MAX(display_name) AS display_name "
            f"FROM contact_book WHERE owner_id IN ({marks}) GROUP BY contact_id ORDER BY MAX(added_at) DESC",
            ids,
        ).fetchall()


def get_contact_keywords(owner_id: int, contact_id: int):
    ids = owner_scope_ids(owner_id)
    marks = ",".join("?" for _ in ids)
    with closing(db()) as conn:
        return conn.execute(
            f"SELECT * FROM contact_keywords WHERE owner_id IN ({marks}) AND contact_id=? ORDER BY id DESC",
            [*ids, int(contact_id)],
        ).fetchall()


def delete_contact_reply(owner_id: int, contact_id: int):
    ids = owner_scope_ids(owner_id)
    marks = ",".join("?" for _ in ids)
    with closing(db()) as conn:
        conn.execute(f"DELETE FROM contact_replies WHERE owner_id IN ({marks}) AND contact_id=?", [*ids, int(contact_id)])
        conn.commit()


def delete_contact_keyword(owner_id: int, contact_id: int, keyword_id: int):
    ids = owner_scope_ids(owner_id)
    marks = ",".join("?" for _ in ids)
    with closing(db()) as conn:
        cur = conn.execute(
            f"DELETE FROM contact_keywords WHERE id=? AND owner_id IN ({marks}) AND contact_id=?",
            [int(keyword_id), *ids, int(contact_id)],
        )
        conn.commit()
        return cur.rowcount


def contact_display(owner_id: int, contact_id: int) -> str:
    for row in get_contact_book(owner_id):
        if int(row["contact_id"]) == int(contact_id):
            if row["username"]:
                return "@" + row["username"]
            if row["display_name"]:
                return str(row["display_name"])
    return str(contact_id)


def link_pending_contact(owner_id: int, sender_id: int, username: str, display_name: str = ""):
    """Bind a username-only saved contact to its real Telegram ID on first incoming message."""
    username = (username or "").lstrip("@").lower()
    if not username:
        return
    ids = owner_scope_ids(owner_id)
    marks = ",".join("?" for _ in ids)
    with closing(db()) as conn:
        pending = conn.execute(
            f"SELECT owner_id,contact_id,username FROM contact_book WHERE owner_id IN ({marks}) AND contact_id<0 AND lower(username)=?",
            [*ids, username],
        ).fetchall()
        if not pending:
            return
        for row in pending:
            scoped_owner, old_id = int(row["owner_id"]), int(row["contact_id"])
            reply = conn.execute("SELECT response FROM contact_replies WHERE owner_id=? AND contact_id=?", (scoped_owner, old_id)).fetchone()
            if reply:
                conn.execute(
                    "INSERT INTO contact_replies(owner_id,contact_id,response,updated_at) VALUES(?,?,?,CURRENT_TIMESTAMP) "
                    "ON CONFLICT(owner_id,contact_id) DO UPDATE SET response=excluded.response,updated_at=CURRENT_TIMESTAMP",
                    (scoped_owner, sender_id, reply["response"]),
                )
                conn.execute("DELETE FROM contact_replies WHERE owner_id=? AND contact_id=?", (scoped_owner, old_id))
            keywords = conn.execute("SELECT * FROM contact_keywords WHERE owner_id=? AND contact_id=?", (scoped_owner, old_id)).fetchall()
            for kw in keywords:
                conn.execute(
                    "INSERT INTO contact_keywords(owner_id,contact_id,word,response,enabled) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(owner_id,contact_id,word) DO UPDATE SET response=excluded.response,enabled=excluded.enabled",
                    (scoped_owner, sender_id, kw["word"], kw["response"], kw["enabled"]),
                )
            conn.execute("DELETE FROM contact_keywords WHERE owner_id=? AND contact_id=?", (scoped_owner, old_id))
            conn.execute(
                "INSERT INTO contact_book(owner_id,contact_id,username,display_name,added_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(owner_id,contact_id) DO UPDATE SET username=excluded.username,display_name=excluded.display_name,added_at=CURRENT_TIMESTAMP",
                (scoped_owner, sender_id, row["username"], display_name or ""),
            )
            conn.execute("DELETE FROM contact_book WHERE owner_id=? AND contact_id=?", (scoped_owner, old_id))
        conn.commit()


def price_toman() -> int:
    try:
        return max(0, int(get_setting("subscription_price", "150000")))
    except ValueError:
        return 150000


def toman(value: int) -> str:
    return f"{int(value):,}".replace(",", "٬") + " تومان"


def is_plus(user_id: int) -> bool:
    if user_id in (ADMIN_ID, ARSIN_OWNER_ID):
        return True
    with closing(db()) as conn:
        row = conn.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return False
    expires = parse_dt(row["expires_at"])
    return bool(expires and expires > now_utc())


def subscription_expiry(user_id: int) -> Optional[datetime]:
    if user_id in (ADMIN_ID, ARSIN_OWNER_ID):
        return None
    with closing(db()) as conn:
        row = conn.execute("SELECT expires_at FROM subscriptions WHERE user_id=?", (user_id,)).fetchone()
    return parse_dt(row["expires_at"]) if row else None


def activate_subscription(user_id: int, days: int = 30, source: str = "payment"):
    now = now_utc()
    current = subscription_expiry(user_id)
    start = current if current and current > now else now
    expiry = start + timedelta(days=days)
    with closing(db()) as conn:
        conn.execute("""INSERT INTO subscriptions(user_id,starts_at,expires_at,source)
            VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            starts_at=excluded.starts_at, expires_at=excluded.expires_at, source=excluded.source""",
            (user_id, dt_text(start), dt_text(expiry), source))
        conn.commit()
    return expiry


def forwarded_source_chat_id(message: Message) -> Optional[int]:
    """Extract the source chat ID from a Telegram-forwarded group/channel message."""
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        chat = getattr(origin, "chat", None)
        if chat is not None and getattr(chat, "id", None) is not None:
            return int(chat.id)
        sender_chat = getattr(origin, "sender_chat", None)
        if sender_chat is not None and getattr(sender_chat, "id", None) is not None:
            return int(sender_chat.id)
    # Some Telegram message variants expose the source as sender_chat.
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat is not None and getattr(sender_chat, "id", None) is not None:
        return int(sender_chat.id)
    return None


def join_link_rows():
    """Each configured line: chat_id_or_username | invite_or_public_URL."""
    result = []
    for line in get_setting("join_links", "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            chat_id, url = [x.strip() for x in line.split("|", 1)]
        else:
            url = line
            match = re.search(r"t\.me/([A-Za-z0-9_]+)", url)
            chat_id = "@" + match.group(1) if match else ""
        if chat_id and url:
            result.append((chat_id, url))
    return result


async def bot_is_admin(chat_id: int) -> bool:
    """The bot must be an administrator in every required group/channel."""
    try:
        me = await bot.get_me()
        target_chat = int(chat_id) if str(chat_id).lstrip("-").isdigit() else str(chat_id)
        member = await bot.get_chat_member(chat_id=target_chat, user_id=me.id)
        return member.status in ("creator", "administrator")
    except Exception as exc:
        logger.warning("Bot admin check failed for chat=%s: %s", chat_id, exc)
        return False


def member_is_joined(member) -> bool:
    status = getattr(member, "status", "")
    if status in ("creator", "administrator", "member"):
        return True
    if status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


async def check_membership(user_id: int) -> tuple[bool, list[str]]:
    missing = []
    for chat_id, url in join_link_rows():
        try:
            if not await bot_is_admin(int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id):
                logger.warning("Membership cannot be verified because bot is not admin: chat=%s", chat_id)
                missing.append(url)
                continue
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if not member_is_joined(member):
                missing.append(url)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            logger.warning("Membership check failed for %s: %s", chat_id, exc)
            missing.append(url)
        except Exception as exc:
            logger.exception("Unexpected membership check failure for %s: %s", chat_id, exc)
            missing.append(url)
    return not missing, missing


def join_keyboard(missing: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"عضویت در لینک {i}", url=url)] for i, url in enumerate(missing, 1)]
    rows.append([InlineKeyboardButton(text="✅ بررسی عضویت", callback_data="check_join")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_keyboard(user_id: int) -> InlineKeyboardMarkup:
    user = get_user(user_id)
    enabled = bool(user["auto_enabled"]) if user else True
    auto_text = "🟢 پاسخ خودکار: روشن" if enabled else "⚪ پاسخ خودکار: خاموش"
    rows = [[InlineKeyboardButton(text=auto_text, callback_data="user_toggle_auto")]]
    if is_plus(user_id):
        rows.append([InlineKeyboardButton(text="✏️ متن و رسانه پاسخ اختصاصی", callback_data="user_custom_reply")])
        rows.append([InlineKeyboardButton(text="🔑 کلمات کلیدی من", callback_data="user_keywords")])
        rows.append([InlineKeyboardButton(text="🎯 پاسخ دلخواه برای کاربر دلخواه", callback_data="contact_rules")])
        rows.append([InlineKeyboardButton(text="🤖 هوش مصنوعی", callback_data="plus_ai")])
        cooldown_on = bool(user["cooldown_enabled"]) if user else False
        cooldown_minutes = int(user["cooldown_minutes"]) if user else 1
        cooldown_text = "🟢 فیلتر تکرار پاسخ: روشن" if cooldown_on else "⚪ فیلتر تکرار پاسخ: خاموش"
        rows.append([InlineKeyboardButton(text=cooldown_text, callback_data="user_toggle_cooldown")])
        rows.append([InlineKeyboardButton(text=f"⏱ فاصله پاسخ عادی: {cooldown_minutes} دقیقه", callback_data="user_set_cooldown")])
    else:
        rows.append([InlineKeyboardButton(text="👑 اشتراک پلاس", callback_data="plus_info")])
    rows.extend([
        [InlineKeyboardButton(text="🔗 وضعیت اتصال حساب", callback_data="user_connection")],
        [InlineKeyboardButton(text="📘 راهنمای کامل", callback_data="user_help")],
    ])
    if is_admin(user_id):
        rows.append([InlineKeyboardButton(text="🎛 پنل مدیریت ارسین", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👥 کاربران ربات", callback_data="admin_users"), InlineKeyboardButton(text="⭐ کاربران پلاس", callback_data="admin_plus_users")],
        [InlineKeyboardButton(text="🧾 بررسی فیش‌ها", callback_data="admin_payments")],
        [InlineKeyboardButton(text="🎟 کدهای تخفیف", callback_data="admin_coupons"), InlineKeyboardButton(text="➕ اعطای پلاس", callback_data="admin_grant")],
        [InlineKeyboardButton(text="💰 قیمت اشتراک", callback_data="admin_price"), InlineKeyboardButton(text="💳 کارت و صاحب کارت", callback_data="admin_card")],
        [InlineKeyboardButton(text="✏️ پاسخ عمومی", callback_data="admin_general")],
        [InlineKeyboardButton(text="🔗 لینک‌های عضویت", callback_data="admin_links"), InlineKeyboardButton(text="👋 پیام بعد از عضویت", callback_data="admin_welcome")],
        [InlineKeyboardButton(text="📢 اطلاعیه همگانی", callback_data="admin_announce")],
        [InlineKeyboardButton(text="👤 تنظیم پاسخ خودکار ارسین", callback_data="admin_personal")],
        [InlineKeyboardButton(text="🔑 کلمات کلیدی عمومی", callback_data="admin_keywords")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard(back="user_menu"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ لغو", callback_data=f"cancel:{back}")]])


def plus_info_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 خرید اشتراک پلاس", callback_data="checkout")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="user_menu")],
    ])


def escape(value) -> str:
    return html.escape(str(value or ""))


def user_profile_link(user_id: int) -> str:
    return f"tg://user?id={user_id}"


def connection_for_user(user_id: int):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM business_connections WHERE user_id=? ORDER BY updated_at DESC LIMIT 1", (user_id,)).fetchone()


def save_business_connection(event):
    rights = getattr(event, "rights", None)
    can_read = bool(getattr(rights, "can_read_messages", False)) if rights else False
    can_reply = bool(getattr(rights, "can_reply", False)) if rights else False
    logger.info("Saving Business connection: user=%s user_chat_id=%s enabled=%s rights=%s can_reply=%s can_read=%s",
                getattr(getattr(event, "user", None), "id", None), getattr(event, "user_chat_id", None),
                getattr(event, "is_enabled", None), rights, can_reply, can_read)
    with closing(db()) as conn:
        conn.execute("""INSERT INTO business_connections(id,user_id,user_chat_id,is_enabled,can_reply,can_read_messages,updated_at)
            VALUES(?,?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET
            user_id=excluded.user_id,user_chat_id=excluded.user_chat_id,is_enabled=excluded.is_enabled,
            can_reply=excluded.can_reply,can_read_messages=excluded.can_read_messages,updated_at=CURRENT_TIMESTAMP""",
            (event.id, event.user.id, event.user_chat_id, int(event.is_enabled), int(can_reply), int(can_read)))
        conn.commit()
    ensure_user(event.user.id, event.user.first_name, event.user.username or "")


def connection_status_text(user_id: int) -> str:
    row = connection_for_user(user_id)
    if not row:
        return ("🔗 <b>اتصال حساب</b>\n\nهنوز اتصال Telegram Business دریافت نشده.\n"
                "ربات را از تنظیمات تلگرام در بخش Business Bots به حساب خود اضافه کنید و مجوز پاسخ‌گویی را بدهید.")
    return ("🔗 <b>وضعیت اتصال حساب</b>\n\n"
            f"وضعیت اتصال: {'✅ فعال' if row['is_enabled'] else '❌ غیرفعال'}\n"
            f"مجوز پاسخ‌گویی: {'✅ دارد' if row['can_reply'] else '❌ ندارد'}\n"
            f"مجوز خواندن پیام‌ها: {'✅ دارد' if row['can_read_messages'] else '❌ ندارد'}\n\n"
            "اگر مجوزها ناقص‌اند، اتصال را در تنظیمات Telegram Business ویرایش کنید.")


def get_pending_checkout(user_id: int):
    with closing(db()) as conn:
        return conn.execute("SELECT * FROM payments WHERE user_id=? AND status IN ('awaiting_proof','proof_received') ORDER BY id DESC LIMIT 1", (user_id,)).fetchone()


def new_checkout(user_id: int, discount: int = 0):
    gross = price_toman()
    discount = max(0, min(gross, int(discount)))
    due = gross - discount
    with closing(db()) as conn:
        conn.execute("UPDATE payments SET status='superseded' WHERE user_id=? AND status='awaiting_proof'", (user_id,))
        cur = conn.execute("INSERT INTO payments(user_id,gross_amount,discount_amount,amount_due,status) VALUES(?,?,?,?,?)", (user_id, gross, discount, due, "awaiting_proof"))
        conn.commit()
        return cur.lastrowid, due


def checkout_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧾 ثبت فیش پرداخت", callback_data="payment_proof")],
        [InlineKeyboardButton(text="🎟 کد تخفیف دارم", callback_data="coupon_enter")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="plus_info")],
    ])


def payment_text(amount_due: int, discount: int = 0) -> str:
    card = get_setting("card_number", "").strip()
    holder = get_setting("card_holder", "").strip()
    card_display = f"<code>{escape(card)}</code>" if card else "<i>هنوز شماره کارت از پنل ارسین ثبت نشده است.</i>"
    text = ("💳 <b>پرداخت اشتراک پلاس</b>\n\n"
            f"قیمت اشتراک: {toman(price_toman())}\n")
    if discount:
        text += f"تخفیف: {toman(discount)}\n"
    text += f"<b>مبلغ قابل پرداخت: {toman(amount_due)}</b>\n\n"
    text += f"نام صاحب کارت: <b>{escape(holder or 'ثبت نشده')}</b>\nشماره کارت (برای کپی روی آن بزنید):\n{card_display}\n\n"
    text += "پس از واریز، گزینه «ثبت فیش پرداخت» را بزنید و تصویر فیش را ارسال کنید."
    return text


def add_coupon(code: str, amount: int, max_uses: int):
    with closing(db()) as conn:
        conn.execute("INSERT INTO coupons(code,discount_toman,max_uses) VALUES(?,?,?)", (code.strip().upper(), amount, max_uses))
        conn.commit()


def coupon_apply(code: str, user_id: int) -> tuple[str, int]:
    code = code.strip().upper()
    gross = price_toman()
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM coupons WHERE code=? AND enabled=1", (code,)).fetchone()
        if not row:
            return "invalid", 0
        if row["max_uses"] > 0 and row["uses"] >= row["max_uses"]:
            return "exhausted", 0
        already = conn.execute("SELECT 1 FROM coupon_uses WHERE code=? AND user_id=?", (code, user_id)).fetchone()
        if already:
            return "used", 0
        discount = min(gross, int(row["discount_toman"]))
        conn.execute("INSERT INTO coupon_uses(code,user_id) VALUES(?,?)", (code, user_id))
        conn.execute("UPDATE coupons SET uses=uses+1 WHERE code=?", (code,))
        conn.commit()
    return ("full" if discount >= gross else "partial"), discount


async def send_custom_reply(connection_id: str, chat_id: int, owner_id: int, response: str):
    # A keyword response is plain text/HTML if the owner configured HTML tags.
    await bot.send_message(chat_id=chat_id, text=response[:4096], business_connection_id=connection_id, parse_mode="HTML")


async def send_owner_default(connection_id: str, chat_id: int, owner_id: int):
    if is_arsin_owner(owner_id):
        # Arsin has a dedicated personal response. It can be text, a photo, or a GIF.
        media_type = get_setting("admin_media_type", "").strip()
        file_id = get_setting("admin_media_file_id", "").strip()
        caption = get_setting("admin_caption", "") or get_setting("admin_reply", "")
        if media_type == "photo" and file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id,
                                 caption=(caption[:1024] if caption else None),
                                 business_connection_id=connection_id, parse_mode="HTML")
            return
        if media_type == "animation" and file_id:
            await bot.send_animation(chat_id=chat_id, animation=file_id,
                                     caption=(caption[:1024] if caption else None),
                                     business_connection_id=connection_id, parse_mode="HTML")
            return
        response = get_setting("admin_reply", "").strip()
        if response:
            await send_custom_reply(connection_id, chat_id, owner_id, response)
        return
    user = get_user(owner_id)
    if not user:
        return
    if is_plus(owner_id):
        media_type = user["custom_media_type"]
        file_id = user["custom_media_file_id"]
        caption = user["custom_caption"] or user["custom_reply"]
        if media_type == "photo" and file_id:
            await bot.send_photo(chat_id=chat_id, photo=file_id, caption=(caption[:1024] if caption else None), business_connection_id=connection_id, parse_mode="HTML")
            return
        if media_type == "animation" and file_id:
            await bot.send_animation(chat_id=chat_id, animation=file_id, caption=(caption[:1024] if caption else None), business_connection_id=connection_id, parse_mode="HTML")
            return
        if user["custom_reply"].strip():
            await send_custom_reply(connection_id, chat_id, owner_id, user["custom_reply"])
            return
    response = get_setting("general_reply", "").strip()
    if response:
        await send_custom_reply(connection_id, chat_id, owner_id, response)


# ============================================================
# START / USER MENU / MEMBERSHIP
# ============================================================

@dp.message(CommandStart())
async def start(message: Message):
    if not message.from_user:
        return
    u = message.from_user
    ensure_user(u.id, u.first_name, u.username or "")
    if is_admin(u.id):
        await message.answer("🎛 <b>پنل مدیریت ارسین</b>", reply_markup=admin_keyboard(), parse_mode="HTML")
        return
    ok, missing = await check_membership(u.id)
    if not ok:
        await message.answer(get_setting("join_prompt", "برای استفاده از ربات ابتدا در لینک‌های زیر عضو شو:") or "برای استفاده از ربات ابتدا در لینک‌های زیر عضو شو:", reply_markup=join_keyboard(missing), parse_mode="HTML")
        return
    await send_user_landing(message.chat.id, u.id)


async def send_user_landing(chat_id: int, user_id: int):
    welcome = get_setting("welcome_text", "").strip()
    if welcome:
        await bot.send_message(chat_id, welcome[:4096], parse_mode="HTML")
    await bot.send_message(chat_id, "👋 <b>منوی اختصاصی شما</b>", reply_markup=user_keyboard(user_id), parse_mode="HTML")


@dp.message(Command("panel"))
async def panel(message: Message):
    if not message.from_user:
        return
    if is_admin(message.from_user.id):
        await message.answer("🎛 <b>پنل مدیریت ارسین</b>", reply_markup=admin_keyboard(), parse_mode="HTML")
    else:
        ok, missing = await check_membership(message.from_user.id)
        if not ok:
            await message.answer("ابتدا عضویت در لینک‌ها را تکمیل کن.", reply_markup=join_keyboard(missing))
        else:
            await message.answer("منوی شما:", reply_markup=user_keyboard(message.from_user.id))


@dp.callback_query(F.data == "check_join")
async def cb_check_join(query: CallbackQuery):
    ok, missing = await check_membership(query.from_user.id)
    await query.answer("عضویت تأیید شد." if ok else "هنوز عضویت کامل نیست.", show_alert=not ok)
    if ok:
        ensure_user(query.from_user.id, query.from_user.first_name, query.from_user.username or "")
        await query.message.answer(get_setting("welcome_text", "")[:4096], parse_mode="HTML") if get_setting("welcome_text", "").strip() else None
        await query.message.answer("👋 <b>منوی اختصاصی شما</b>", reply_markup=user_keyboard(query.from_user.id), parse_mode="HTML")
    else:
        try:
            await query.message.edit_reply_markup(reply_markup=join_keyboard(missing))
        except TelegramBadRequest:
            pass


@dp.callback_query(F.data == "user_menu")
async def cb_user_menu(query: CallbackQuery):
    await query.answer()
    await query.message.answer("👋 <b>منوی شما</b>", reply_markup=user_keyboard(query.from_user.id), parse_mode="HTML")


@dp.callback_query(F.data == "user_toggle_auto")
async def cb_user_toggle_auto(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid):
        ok, _ = await check_membership(uid)
        if not ok:
            await query.answer("ابتدا عضویت اجباری را تکمیل کن.", show_alert=True)
            return
    ensure_user(uid, query.from_user.first_name, query.from_user.username or "")
    user = get_user(uid)
    new_value = 0 if user["auto_enabled"] else 1
    with closing(db()) as conn:
        conn.execute("UPDATE users SET auto_enabled=? WHERE user_id=?", (new_value, uid))
        conn.commit()
    await query.answer("پاسخ خودکار روشن شد." if new_value else "پاسخ خودکار خاموش شد.")
    await query.message.edit_reply_markup(reply_markup=user_keyboard(uid))


@dp.callback_query(F.data == "user_connection")
async def cb_user_connection(query: CallbackQuery):
    await query.answer()
    await query.message.answer(connection_status_text(query.from_user.id), parse_mode="HTML")


@dp.callback_query(F.data == "user_help")
async def cb_user_help(query: CallbackQuery):
    await query.answer()
    text = (
        "📘 <b>راهنمای کامل راه‌اندازی</b>\n\n"
        "<b>۱.</b> در تلگرام وارد Settings شوید و بخش Telegram Business را باز کنید.\n"
        "<b>۲.</b> بخش Chatbots / Business Bots را باز کنید و ربات را با نام کاربری‌اش اضافه کنید.\n"
        "<b>۳.</b> چت‌هایی را انتخاب کنید که ربات اجازه دارد در آن‌ها پاسخ بدهد.\n"
        "<b>۴.</b> مجوز پاسخ‌گویی را فعال کنید؛ برای دریافت و پردازش پیام‌ها، دسترسی‌های درخواستی تلگرام را بررسی کنید.\n"
        "<b>۵.</b> اتصال را ذخیره کنید و به این ربات برگردید؛ از «وضعیت اتصال حساب» مجوزها را بررسی کنید.\n"
        "<b>۶.</b> پاسخ خودکار را از منو روشن کنید. کاربران عادی از متن عمومی ارسین استفاده می‌کنند؛ کاربران پلاس می‌توانند متن و کلمات کلیدی اختصاصی بسازند.\n\n"
        "⚠️ استارت کردن این ربات به‌تنهایی حساب شخصی شما را متصل نمی‌کند. فقط چت‌ها و مجوزهایی که در Telegram Business انتخاب کرده‌اید قابل استفاده‌اند. در صورت غیرفعال بودن اتصال یا مجوز پاسخ‌گویی، ربات نمی‌تواند از طرف حساب شما پیام بفرستد.\n\n"
        "برای قالب‌بندی متن پلاس، می‌توانید HTML ساده مثل <code>&lt;b&gt;متن&lt;/b&gt;</code> و لینک مثل <code>&lt;a href=\"https://example.com\"&gt;لینک&lt;/a&gt;</code> وارد کنید."
    )
    await query.message.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ بازگشت", callback_data="user_menu")]]))


# ============================================================
# PLUS SUBSCRIPTION / CHECKOUT / COUPONS / PROOFS
# ============================================================

@dp.callback_query(F.data == "plus_info")
async def cb_plus_info(query: CallbackQuery):
    await query.answer()
    if is_plus(query.from_user.id):
        expiry = subscription_expiry(query.from_user.id)
        exp_text = "دائمی" if query.from_user.id == ADMIN_ID else (expiry.strftime("%Y-%m-%d %H:%M UTC") if expiry else "نامشخص")
        await query.message.answer(f"👑 <b>اشتراک پلاس شما فعال است.</b>\nانقضا: <code>{escape(exp_text)}</code>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="user_menu")]]), parse_mode="HTML")
        return
    text = (
        "👑 <b>اشتراک Arsin Plus</b>\n\n"
        "• متن پاسخ اختصاصی\n• کلمات کلیدی اختصاصی و پاسخ جداگانه\n"
        "• قالب‌بندی متن با HTML و لینک قابل کلیک\n• پاسخ همراه عکس یا GIF\n"
        "• کنترل مستقل تنظیمات پاسخ خودکار\n• تمدید و مدیریت تاریخ انقضا\n\n"
        f"قیمت اشتراک ۳۰ روزه: <b>{toman(price_toman())}</b>\n\n"
        "برای فعال‌سازی، پرداخت را انجام دهید یا کد تخفیف وارد کنید."
    )
    await query.message.answer(text, reply_markup=plus_info_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "checkout")
async def cb_checkout(query: CallbackQuery):
    await query.answer()
    uid = query.from_user.id
    if is_plus(uid):
        await query.message.answer("اشتراک پلاس شما فعال است. برای تمدید می‌توانید همین بخش را دوباره باز کنید.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 تمدید اشتراک", callback_data="renew")]]))
        return
    pid, due = new_checkout(uid, 0)
    await query.message.answer(payment_text(due), reply_markup=checkout_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "renew")
async def cb_renew(query: CallbackQuery):
    await query.answer()
    pid, due = new_checkout(query.from_user.id, 0)
    await query.message.answer(payment_text(due), reply_markup=checkout_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "coupon_enter")
async def cb_coupon_enter(query: CallbackQuery):
    user_states[query.from_user.id] = ("coupon", None)
    await query.answer()
    await query.message.answer("🎟 کد تخفیف خود را ارسال کنید:", reply_markup=cancel_keyboard("plus_info"))


@dp.callback_query(F.data == "payment_proof")
async def cb_payment_proof(query: CallbackQuery):
    pending = get_pending_checkout(query.from_user.id)
    if not pending:
        pid, due = new_checkout(query.from_user.id, 0)
        pending = get_pending_checkout(query.from_user.id)
    user_states[query.from_user.id] = ("proof", int(pending["id"]))
    await query.answer()
    await query.message.answer("🧾 لطفاً تصویر فیش پرداخت یا فایل رسید را ارسال کنید.", reply_markup=cancel_keyboard("plus_info"))


async def handle_contact_rule_input(message: Message, action: str, object_id):
    """Manage a Plus user's saved special contacts, replies and contact keywords."""
    uid = message.from_user.id
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    if not is_admin(uid) and not is_plus(uid):
        user_states.pop(uid, None)
        await message.answer("این قابلیت مخصوص اشتراک پلاس است.", reply_markup=user_keyboard(uid))
        return True

    if action == "contact_add_target":
        contact = None
        # Accept a forwarded message from the contact (only user-origin forwards reveal a user ID).
        origin = getattr(message, "forward_origin", None)
        forwarded_user = getattr(origin, "sender_user", None) if origin else None
        if forwarded_user is None:
            forwarded_user = getattr(message, "forward_from", None)
        if forwarded_user is not None:
            contact = forwarded_user
        else:
            raw = (message.text or "").strip()
            if raw.startswith("@"):
                raw = raw[1:]
            if raw and re.fullmatch(r"[A-Za-z0-9_]{5,32}", raw):
                # Bot API cannot resolve every arbitrary user's username. First check users already known to this bot.
                with closing(db()) as conn:
                    known = conn.execute("SELECT user_id,first_name,username FROM users WHERE lower(username)=lower(?) LIMIT 1", (raw,)).fetchone()
                if known:
                    class KnownContact:
                        id = int(known["user_id"])
                        username = known["username"] or ""
                        full_name = known["first_name"] or ""
                    contact = KnownContact()
                else:
                    try:
                        contact = await bot.get_chat("@" + raw)
                    except TelegramAPIError as exc:
                        # Bot API cannot resolve arbitrary user usernames. Save a stable temporary key;
                        # when that user next messages the connected Business account, bind their real ID.
                        logger.info("Username %s saved pending first contact because Bot API could not resolve it: %s", raw, exc)
                        placeholder_id = -(int(hashlib.sha256(raw.lower().encode("utf-8")).hexdigest()[:12], 16) + 1)
                        class PendingContact:
                            id = placeholder_id
                            username = raw
                            full_name = "@" + raw
                        contact = PendingContact()
            else:
                await message.answer("یوزرنیم عمومی مثل <code>@username</code> را بفرست یا یک پیام از خود آن کاربر فوروارد کن.", parse_mode="HTML")
                return True
        contact_id = int(contact.id)
        if contact_id == owner_id:
            await message.answer("نمی‌توانی حساب خودت را به فهرست کاربران ویژه اضافه کنی.")
            return True
        username = getattr(contact, "username", None) or ""
        display_name = getattr(contact, "full_name", None) or getattr(contact, "first_name", None) or ""
        save_contact_book(owner_id, contact_id, username, display_name)
        user_states.pop(uid, None)
        await message.answer(f"✅ کاربر ویژه اضافه شد: {escape('@'+username if username else display_name or str(contact_id))}\nشناسه: <code>{contact_id}</code>", parse_mode="HTML", reply_markup=contact_rules_keyboard(uid))
        return True

    if action in ("contact_reply_target", "contact_kw_target"):
        # Backward compatibility with a pending older numeric-ID flow.
        raw = (message.text or "").strip()
        try:
            contact_id = int(raw)
            if contact_id <= 0 or contact_id == owner_id:
                raise ValueError
        except ValueError:
            await message.answer("شناسه عددی معتبر بفرست یا از منوی کاربران ویژه، کاربر را با یوزرنیم/فوروارد اضافه کن.")
            return True
        save_contact_book(owner_id, contact_id)
        if action == "contact_reply_target":
            user_states[uid] = ("contact_reply_text", contact_id)
            await message.answer(f"✏️ متن دلخواه برای {contact_display(owner_id, contact_id)} را بفرست.", reply_markup=cancel_keyboard("contact_rules"))
        else:
            user_states[uid] = ("contact_kw_text", contact_id)
            await message.answer("کلمه و پاسخ را با قالب <code>کلمه | پاسخ</code> بفرست.", parse_mode="HTML", reply_markup=cancel_keyboard("contact_rules"))
        return True

    if action == "contact_reply_text":
        response = (message.text or "").strip()
        if not response:
            await message.answer("متن پاسخ نباید خالی باشد. یک متن بفرست.")
            return True
        save_contact_reply(owner_id, int(object_id), response)
        user_states.pop(uid, None)
        await message.answer("✅ پاسخ مخصوص کاربر ذخیره شد.", reply_markup=contact_user_keyboard(uid, int(object_id)))
        return True

    if action == "contact_kw_text":
        raw = (message.text or "").strip()
        if "|" not in raw:
            await message.answer("فرمت صحیح:\nکلمه | پاسخ\nمثال: قیمت | قیمت محصول ...")
            return True
        word, response = [part.strip() for part in raw.split("|", 1)]
        if not word or not response:
            await message.answer("کلمه و پاسخ نباید خالی باشند.")
            return True
        try:
            save_contact_keyword(owner_id, int(object_id), word, response)
        except sqlite3.Error as exc:
            logger.exception("Contact keyword save failed owner=%s contact=%s: %s", owner_id, object_id, exc)
            await message.answer("❌ ذخیره کلمه مخصوص این مخاطب ناموفق بود. خطا در لاگ ثبت شد.")
            return True
        user_states.pop(uid, None)
        await message.answer(f"✅ کلمه «{escape(word)}» برای {escape(contact_display(owner_id, int(object_id)))} ذخیره شد. هر بار تطبیق پیدا کند پاسخ می‌گیرد.", parse_mode="HTML", reply_markup=contact_user_keyboard(uid, int(object_id)))
        return True
    return False


@dp.message(F.chat.type == ChatType.PRIVATE)
async def private_user_inputs(message: Message):
    if not message.from_user:
        return
    uid = message.from_user.id
    state = user_states.get(uid)
    if not state:
        if not is_admin(uid):
            ok, missing = await check_membership(uid)
            if not ok:
                await message.answer("برای استفاده از ربات ابتدا در لینک‌های اجباری عضو شو.", reply_markup=join_keyboard(missing))
        return
    action, object_id = state
    if action in ("contact_add_target", "contact_reply_target", "contact_kw_target", "contact_reply_text", "contact_kw_text"):
        if await handle_contact_rule_input(message, action, object_id):
            return
    if is_admin(uid):
        await handle_admin_input(message, action, object_id)
        return
    if action == "coupon":
        if not message.text:
            await message.answer("لطفاً کد تخفیف را به‌صورت متن ارسال کنید.")
            return
        result, discount = coupon_apply(message.text, uid)
        user_states.pop(uid, None)
        if result in ("invalid", "exhausted", "used"):
            msg = {"invalid": "❌ کد تخفیف معتبر نیست.", "exhausted": "❌ ظرفیت استفاده از این کد تمام شده است.", "used": "❌ شما قبلاً از این کد استفاده کرده‌اید."}[result]
            await message.answer(msg, reply_markup=plus_info_keyboard())
            return
        if result == "full":
            expiry = activate_subscription(uid, 30, source="coupon")
            await message.answer("🎉 <b>اشتراک پلاس برای شما فعال شد!</b>\nتمام قابلیت‌های پلاس فعال هستند.\nانقضا: " + escape(expiry.strftime("%Y-%m-%d %H:%M UTC")), parse_mode="HTML", reply_markup=user_keyboard(uid))
            try:
                await bot.send_message(ADMIN_ID, f"🎟 اشتراک کاربر <a href=\"tg://user?id={uid}\">{uid}</a> با کد تخفیف {escape(message.text.strip().upper())} فعال شد.", parse_mode="HTML")
            except TelegramAPIError:
                pass
            return
        pid, due = new_checkout(uid, discount)
        await message.answer("✅ کد تخفیف اعمال شد.\n\n" + payment_text(due, discount), reply_markup=checkout_keyboard(), parse_mode="HTML")
        return
    if action == "proof":
        file_id = ""
        proof_type = ""
        if message.photo:
            file_id, proof_type = message.photo[-1].file_id, "photo"
        elif message.document:
            file_id, proof_type = message.document.file_id, "document"
        else:
            await message.answer("لطفاً تصویر فیش یا فایل رسید را ارسال کنید.")
            return
        payment_id = int(object_id or 0)
        with closing(db()) as conn:
            cur = conn.execute("UPDATE payments SET status='proof_received',proof_type=?,proof_file_id=? WHERE id=? AND user_id=? AND status='awaiting_proof'", (proof_type, file_id, payment_id, uid))
            conn.commit()
            changed = cur.rowcount
        user_states.pop(uid, None)
        if not changed:
            await message.answer("درخواست پرداخت فعالی پیدا نشد. لطفاً فرایند پرداخت را دوباره آغاز کنید.", reply_markup=plus_info_keyboard())
            return
        username = f"@{message.from_user.username}" if message.from_user.username else "ندارد"
        caption = (f"🧾 <b>فیش پرداخت جدید</b>\nشناسه پرداخت: <code>{payment_id}</code>\n"
                   f"کاربر: <a href=\"tg://user?id={uid}\">{escape(message.from_user.full_name)}</a>\n"
                   f"شناسه عددی: <code>{uid}</code>\nیوزرنیم: {escape(username)}\n"
                   f"مبلغ: <b>{toman(get_payment_amount(payment_id))}</b>")
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ تأیید پرداخت", callback_data=f"pay_approve:{payment_id}"), InlineKeyboardButton(text="❌ عدم تأیید", callback_data=f"pay_reject:{payment_id}")]])
        try:
            if proof_type == "photo":
                await bot.send_photo(ADMIN_ID, file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            else:
                await bot.send_document(ADMIN_ID, file_id, caption=caption, parse_mode="HTML", reply_markup=kb)
            await message.answer("✅ فیش شما برای ارسین ارسال شد. پس از بررسی، نتیجه به شما اطلاع داده می‌شود.")
        except TelegramAPIError as exc:
            logger.exception("Could not forward payment proof: %s", exc)
            await message.answer("ارسال فیش به مدیریت ناموفق بود. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    if action == "custom_reply":
        if not is_plus(uid):
            user_states.pop(uid, None)
            await message.answer("برای تنظیم پاسخ اختصاصی باید اشتراک پلاس فعال داشته باشید.", reply_markup=user_keyboard(uid))
            return
        if message.photo:
            file_id = message.photo[-1].file_id
            caption = message.caption or ""
            with closing(db()) as conn:
                conn.execute("UPDATE users SET custom_media_type='photo',custom_media_file_id=?,custom_caption=?,custom_reply=? WHERE user_id=?", (file_id, caption, caption, uid))
                conn.commit()
            user_states.pop(uid, None)
            await message.answer("✅ عکس و کپشن پاسخ اختصاصی ذخیره شد.", reply_markup=user_keyboard(uid))
            return
        if message.animation:
            file_id = message.animation.file_id
            caption = message.caption or ""
            with closing(db()) as conn:
                conn.execute("UPDATE users SET custom_media_type='animation',custom_media_file_id=?,custom_caption=?,custom_reply=? WHERE user_id=?", (file_id, caption, caption, uid))
                conn.commit()
            user_states.pop(uid, None)
            await message.answer("✅ GIF و کپشن پاسخ اختصاصی ذخیره شد.", reply_markup=user_keyboard(uid))
            return
        if not message.text:
            await message.answer("متن، عکس یا GIF بفرست. برای قالب‌بندی از HTML ساده استفاده کن.")
            return
        with closing(db()) as conn:
            conn.execute("UPDATE users SET custom_reply=?,custom_media_type='',custom_media_file_id='',custom_caption='' WHERE user_id=?", (message.text[:4096], uid))
            conn.commit()
        user_states.pop(uid, None)
        await message.answer("✅ پاسخ اختصاصی ذخیره شد.", reply_markup=user_keyboard(uid))
        return
    if action == "admin_cooldown_minutes":
        if not is_admin(uid):
            user_states.pop(uid, None)
            await message.answer("دسترسی ندارید.")
            return
        try:
            minutes = int((message.text or "").strip())
            if minutes < 1 or minutes > 10080:
                raise ValueError
        except ValueError:
            await message.answer("یک عدد صحیح از ۱ تا ۱۰۰۸۰ دقیقه وارد کن.")
            return
        set_setting("admin_cooldown_minutes", str(minutes))
        user_states.pop(uid, None)
        await message.answer(f"✅ فاصله پاسخ عادی ارسین روی {minutes} دقیقه تنظیم شد. کلمات کلیدی همچنان در هر بار پیام پاسخ می‌گیرند.", reply_markup=user_keyboard(uid))
        return
    if action == "cooldown_minutes":
        if not is_plus(uid):
            user_states.pop(uid, None)
            await message.answer("این قابلیت مخصوص اشتراک پلاس است.", reply_markup=user_keyboard(uid))
            return
        try:
            minutes = int((message.text or "").strip())
            if minutes < 1 or minutes > 10080:
                raise ValueError
        except ValueError:
            await message.answer("یک عدد صحیح از ۱ تا ۱۰۰۸۰ دقیقه وارد کن.")
            return
        ensure_user(uid, message.from_user.first_name, message.from_user.username or "")
        with closing(db()) as conn:
            conn.execute("UPDATE users SET cooldown_minutes=? WHERE user_id=?", (minutes, uid))
            conn.commit()
        user_states.pop(uid, None)
        await message.answer(f"✅ فاصله پاسخ عادی روی {minutes} دقیقه تنظیم شد. پاسخ کلمات کلیدی همچنان بدون محدودیت زمانی ارسال می‌شود.", reply_markup=user_keyboard(uid))
        return
    if action == "user_kw_add":
        if not is_plus(uid):
            user_states.pop(uid, None)
            await message.answer("این قابلیت مخصوص پلاس است.")
            return
        if not message.text or "|" not in message.text:
            await message.answer("فرمت صحیح:\nکلمه | پاسخ\nمثال: سلام | سلام، چطور می‌تونم کمک کنم؟")
            return
        word, response = [part.strip() for part in message.text.split("|", 1)]
        if not word or not response:
            await message.answer("کلمه و پاسخ نباید خالی باشند.")
            return
        try:
            with closing(db()) as conn:
                conn.execute("INSERT INTO user_keywords(user_id,word,response) VALUES(?,?,?) ON CONFLICT(user_id,word) DO UPDATE SET response=excluded.response,enabled=1", (uid, word, response))
                conn.commit()
        except sqlite3.IntegrityError:
            await message.answer("ثبت کلمه ناموفق بود.")
            return
        user_states.pop(uid, None)
        await message.answer("✅ کلمه کلیدی اختصاصی ذخیره شد.", reply_markup=user_keyboard(uid))


def get_payment_amount(payment_id: int) -> int:
    with closing(db()) as conn:
        row = conn.execute("SELECT amount_due FROM payments WHERE id=?", (payment_id,)).fetchone()
        return int(row["amount_due"]) if row else 0


@dp.callback_query(F.data.startswith("pay_approve:"))
async def cb_pay_approve(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    payment_id = int(query.data.split(":", 1)[1])
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not row or row["status"] != "proof_received":
            await query.answer("این پرداخت قبلاً بررسی شده یا وجود ندارد.", show_alert=True)
            return
        conn.execute("UPDATE payments SET status='approved',reviewed_at=?,reviewer_id=? WHERE id=?", (dt_text(now_utc()), query.from_user.id, payment_id))
        conn.commit()
    expiry = activate_subscription(row["user_id"], 30, source="payment")
    await query.answer("پرداخت تأیید شد؛ پلاس فعال شد.")
    try:
        await bot.send_message(row["user_id"], f"🎉 <b>پرداخت شما تأیید شد!</b>\nاشتراک پلاس ۳۰ روزه فعال شد.\nتاریخ انقضا: <code>{escape(expiry.strftime('%Y-%m-%d %H:%M UTC'))}</code>", parse_mode="HTML", reply_markup=user_keyboard(row["user_id"]))
    except TelegramAPIError:
        pass
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass


@dp.callback_query(F.data.startswith("pay_reject:"))
async def cb_pay_reject(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    payment_id = int(query.data.split(":", 1)[1])
    with closing(db()) as conn:
        row = conn.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
        if not row or row["status"] != "proof_received":
            await query.answer("این پرداخت قبلاً بررسی شده یا وجود ندارد.", show_alert=True)
            return
        conn.execute("UPDATE payments SET status='rejected',reviewed_at=?,reviewer_id=? WHERE id=?", (dt_text(now_utc()), query.from_user.id, payment_id))
        conn.commit()
    await query.answer("فیش رد شد.")
    try:
        await bot.send_message(row["user_id"], "❌ فیش پرداخت شما تأیید نشد. لطفاً اطلاعات پرداخت را بررسی و در صورت نیاز دوباره اقدام کنید.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 تلاش دوباره", callback_data="checkout")]]))
    except TelegramAPIError:
        pass
    try:
        await query.message.edit_reply_markup(reply_markup=None)
    except TelegramAPIError:
        pass


def contact_rules_keyboard(uid: int) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="➕ افزودن کاربر", callback_data="contact_add")]]
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    contacts = get_contact_book(owner_id)
    for row in contacts[:80]:
        cid = int(row["contact_id"])
        label = ("@" + row["username"]) if row["username"] else (row["display_name"] or str(cid))
        rows.append([InlineKeyboardButton(text=f"👤 {label[:45]}", callback_data=f"contact_user:{cid}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data="admin_personal" if is_admin(uid) else "user_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def contact_user_keyboard(uid: int, contact_id: int) -> InlineKeyboardMarkup:
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    current_reply = get_contact_reply(owner_id, contact_id)
    rows = [
        [InlineKeyboardButton(text="✉️ ثبت / مدیریت پاسخ مخصوص کاربر", callback_data=f"contact_reply_manage:{contact_id}")],
        [InlineKeyboardButton(text="🔑 ثبت کلمه کلیدی مخصوص کاربر", callback_data=f"contact_kw_add:{contact_id}")],
        [InlineKeyboardButton(text="📋 مشاهده کلمات کلیدی مخصوص کاربر", callback_data=f"contact_kw_list:{contact_id}")],
        [InlineKeyboardButton(text="⬅️ کاربران ویژه شما", callback_data="contact_rules")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def show_contact_user(query: CallbackQuery, contact_id: int):
    uid = query.from_user.id
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    name = contact_display(owner_id, contact_id)
    reply = get_contact_reply(owner_id, contact_id)
    current = escape(reply[:1200]) if reply else "<i>هنوز پاسخی ثبت نشده است.</i>"
    await query.answer()
    await query.message.answer(
        f"👤 <b>{escape(name)}</b>\nشناسه: <code>{contact_id}</code>\n\n"
        f"✉️ <b>پاسخ فعلی:</b>\n{current}\n\n"
        "کلمات کلیدی مخصوص این مخاطب مستقل از پاسخ عمومی هستند. پاسخ کلمات کلیدی در هر بار تطبیق ارسال می‌شود و فیلتر تکرار فقط پاسخ عادی را محدود می‌کند.",
        parse_mode="HTML", reply_markup=contact_user_keyboard(uid, contact_id))


@dp.callback_query(F.data == "contact_rules")
async def cb_contact_rules(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    await query.answer()
    await query.message.answer("👥 <b>کاربران ویژه شما</b>\n\nبرای افزودن، یوزرنیم عمومی کاربر را بفرست یا یک پیام از طرف او فوروارد کن. کاربران اضافه‌شده به‌صورت دکمه در این فهرست نمایش داده می‌شوند.", parse_mode="HTML", reply_markup=contact_rules_keyboard(uid))


@dp.callback_query(F.data == "contact_add")
async def cb_contact_add(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    user_states[uid] = ("contact_add_target", None)
    await query.answer()
    await query.message.answer("➕ یوزرنیم عمومی کاربر مثل <code>@username</code> را بفرست، یا یک پیام از طرف همان کاربر را فوروارد کن.", parse_mode="HTML", reply_markup=cancel_keyboard("contact_rules"))


@dp.callback_query(F.data.startswith("contact_user:"))
async def cb_contact_user(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    try:
        contact_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("شناسه کاربر نامعتبر است.", show_alert=True)
        return
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    if not any(int(r["contact_id"]) == contact_id for r in get_contact_book(owner_id)):
        await query.answer("این کاربر در فهرست شما نیست.", show_alert=True)
        return
    await show_contact_user(query, contact_id)


@dp.callback_query(F.data.startswith("contact_reply_manage:"))
async def cb_contact_reply_manage(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    contact_id = int(query.data.split(":", 1)[1])
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    current = get_contact_reply(owner_id, contact_id)
    name = contact_display(owner_id, contact_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ ویرایش / ثبت پاسخ", callback_data=f"contact_reply_edit:{contact_id}")],
        [InlineKeyboardButton(text="🗑 حذف پاسخ", callback_data=f"contact_reply_delete:{contact_id}")],
        [InlineKeyboardButton(text="⬅️ تنظیمات همین کاربر", callback_data=f"contact_user:{contact_id}")],
    ])
    await query.answer()
    await query.message.answer(
        f"✉️ <b>پاسخ مخصوص {escape(name)}</b>\n\nپاسخ فعلی:\n{escape(current) if current else '<i>هنوز پاسخی ثبت نشده است.</i>'}\n\n"
        "این پاسخ جای پاسخ عمومی را برای همین مخاطب می‌گیرد و فیلتر تکرار پاسخ عادی شامل آن می‌شود.",
        parse_mode="HTML", reply_markup=kb)


@dp.callback_query(F.data.startswith("contact_reply_edit:"))
async def cb_contact_reply_edit(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    contact_id = int(query.data.split(":", 1)[1])
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    user_states[uid] = ("contact_reply_text", contact_id)
    current = get_contact_reply(owner_id, contact_id)
    await query.answer()
    await query.message.answer("✏️ <b>پاسخ فعلی:</b>\n" + (escape(current) if current else "<i>ثبت نشده</i>") + "\n\nمتن جدید پاسخ مخصوص این کاربر را بفرست. این پاسخ جای پاسخ عمومی را می‌گیرد و فیلتر تکرار شاملش می‌شود.", parse_mode="HTML", reply_markup=cancel_keyboard(f"contact_user:{contact_id}"))


@dp.callback_query(F.data.startswith("contact_reply_delete:"))
async def cb_contact_reply_delete(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    contact_id = int(query.data.split(":", 1)[1])
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    delete_contact_reply(owner_id, contact_id)
    await show_contact_user(query, contact_id)


@dp.callback_query(F.data.startswith("contact_kw_add:"))
async def cb_contact_kw_add(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    contact_id = int(query.data.split(":", 1)[1])
    user_states[uid] = ("contact_kw_text", contact_id)
    await query.answer()
    await query.message.answer("🔑 کلمه و پاسخ مخصوص این کاربر را با قالب زیر بفرست:\n<code>کلمه | پاسخ</code>\nاگر کلمه تکراری باشد پاسخ آن به‌روزرسانی می‌شود. هر بار تطبیق پیدا کند پاسخ می‌گیرد و فیلتر تکرار شامل آن نیست.", parse_mode="HTML", reply_markup=cancel_keyboard(f"contact_user:{contact_id}"))


@dp.callback_query(F.data.startswith("contact_kw_list:"))
async def cb_contact_kw_list(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    contact_id = int(query.data.split(":", 1)[1])
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    rows = get_contact_keywords(owner_id, contact_id)
    lines = [f"📋 <b>کلمات کلیدی مخصوص {escape(contact_display(owner_id, contact_id))}</b>\n"]
    buttons = []
    for row in rows[:50]:
        lines.append(f"• <code>{escape(row['word'])}</code> → {escape(row['response'][:90])}")
        buttons.append([InlineKeyboardButton(text=f"🗑 حذف: {row['word'][:40]}", callback_data=f"contact_kw_del:{contact_id}:{row['id']}")])
    if not rows:
        lines.append("هنوز کلمه کلیدی مخصوصی ثبت نشده است.")
    buttons.append([InlineKeyboardButton(text="➕ افزودن کلمه کلیدی", callback_data=f"contact_kw_add:{contact_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ تنظیمات همین کاربر", callback_data=f"contact_user:{contact_id}")])
    await query.answer()
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@dp.callback_query(F.data.startswith("contact_kw_del:"))
async def cb_contact_kw_del(query: CallbackQuery):
    uid = query.from_user.id
    if not is_admin(uid) and not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    try:
        _, contact_id, keyword_id = query.data.split(":")
        contact_id, keyword_id = int(contact_id), int(keyword_id)
    except ValueError:
        await query.answer("شناسه کلمه نامعتبر است.", show_alert=True)
        return
    owner_id = ARSIN_OWNER_ID if is_admin(uid) else uid
    deleted = delete_contact_keyword(owner_id, contact_id, keyword_id)
    await query.answer("کلمه کلیدی حذف شد." if deleted else "کلمه پیدا نشد.")
    rows = get_contact_keywords(owner_id, contact_id)
    lines = [f"📋 <b>کلمات کلیدی مخصوص {escape(contact_display(owner_id, contact_id))}</b>\n"]
    buttons = []
    for row in rows[:50]:
        lines.append(f"• <code>{escape(row['word'])}</code> → {escape(row['response'][:90])}")
        buttons.append([InlineKeyboardButton(text=f"🗑 حذف: {row['word'][:40]}", callback_data=f"contact_kw_del:{contact_id}:{row['id']}")])
    if not rows:
        lines.append("هنوز کلمه کلیدی مخصوصی ثبت نشده است.")
    buttons.append([InlineKeyboardButton(text="➕ افزودن کلمه کلیدی", callback_data=f"contact_kw_add:{contact_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ تنظیمات همین کاربر", callback_data=f"contact_user:{contact_id}")])
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


# ============================================================
# PLUS KEYWORDS
# ============================================================

@dp.callback_query(F.data == "plus_ai")
async def cb_plus_ai(query: CallbackQuery):
    if not is_plus(query.from_user.id):
        await query.answer("این بخش مخصوص اشتراک پلاس است.", show_alert=True)
        return
    await query.answer()
    await query.message.answer("🤖 <b>هوش مصنوعی</b>\n\n🚧 این بخش در حال توسعه است. به‌محض آماده شدن، امکانات آن در همین بخش فعال می‌شود.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="user_menu")]]))


@dp.callback_query(F.data == "user_custom_reply")
async def cb_user_custom_reply(query: CallbackQuery):
    if not is_plus(query.from_user.id):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    user_states[query.from_user.id] = ("custom_reply", None)
    await query.answer()
    await query.message.answer("✏️ پاسخ اختصاصی را ارسال کنید.\nمی‌توانید متن HTML، عکس با کپشن یا GIF با کپشن بفرستید.\nبرای پاک کردن رسانه، یک متن ساده بفرستید.", reply_markup=cancel_keyboard("user_menu"))


@dp.callback_query(F.data == "user_keywords")
async def cb_user_keywords(query: CallbackQuery):
    if not is_plus(query.from_user.id):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    rows = get_user_keywords(query.from_user.id)
    keyboard_rows = [[InlineKeyboardButton(text="➕ افزودن / ویرایش کلمه", callback_data="user_kw_add")]]
    for row in rows[:40]:
        keyboard_rows.append([InlineKeyboardButton(text=f"🗑 {row['word']}"[:64], callback_data=f"user_kw_del:{row['id']}")])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ منوی اصلی", callback_data="user_menu")])
    await query.answer()
    await query.message.answer("🔑 <b>کلمات کلیدی اختصاصی شما</b>\nبرای افزودن یا ویرایش، کلمه و پاسخ را با | جدا کنید. برای حذف، روی کلمه بزنید.\n\n" + ("\n".join(f"• {escape(r['word'])} → {escape(r['response'][:50])}" for r in rows) or "هنوز کلمه‌ای ثبت نکرده‌اید."), reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows), parse_mode="HTML")


@dp.callback_query(F.data == "user_kw_add")
async def cb_user_kw_add(query: CallbackQuery):
    if not is_plus(query.from_user.id):
        await query.answer("این قابلیت مخصوص پلاس است.", show_alert=True)
        return
    user_states[query.from_user.id] = ("user_kw_add", None)
    await query.answer()
    await query.message.answer("فرمت را بفرست:\n<code>کلمه | پاسخ</code>", parse_mode="HTML", reply_markup=cancel_keyboard("user_keywords"))


@dp.callback_query(F.data.startswith("user_kw_del:"))
async def cb_user_kw_del(query: CallbackQuery):
    if not is_plus(query.from_user.id):
        await query.answer("این قابلیت مخصوص پلاس است.", show_alert=True)
        return
    keyword_id = int(query.data.split(":", 1)[1])
    with closing(db()) as conn:
        conn.execute("DELETE FROM user_keywords WHERE id=? AND user_id=?", (keyword_id, query.from_user.id))
        conn.commit()
    await cb_user_keywords(query)


# ============================================================
# ADMIN PANEL CALLBACKS
# ============================================================

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    await query.answer()
    await query.message.answer("🎛 <b>پنل مدیریت ارسین</b>", reply_markup=admin_keyboard(), parse_mode="HTML")


@dp.callback_query(F.data == "admin_users")
async def cb_admin_users(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    users = all_users()
    lines = [f"👥 <b>کاربران ثبت‌شده: {len(users)}</b>\n"]
    for u in users[:70]:
        name = escape(u["first_name"] or "بدون نام")
        username = "@" + escape(u["username"]) if u["username"] else "بدون یوزرنیم"
        lines.append(f"• <a href=\"tg://user?id={u['user_id']}\">{name}</a> | <code>{u['user_id']}</code> | {username} | {'⭐ پلاس' if is_plus(u['user_id']) else 'عادی'}")
    await query.answer()
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")]]))


@dp.callback_query(F.data == "admin_plus_users")
async def cb_admin_plus_users(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    with closing(db()) as conn:
        rows = conn.execute("SELECT s.user_id,s.expires_at,u.first_name,u.username FROM subscriptions s LEFT JOIN users u ON u.user_id=s.user_id ORDER BY s.expires_at DESC").fetchall()
    active = [r for r in rows if (parse_dt(r["expires_at"]) or now_utc()) > now_utc()]
    lines = [f"⭐ <b>اشتراک‌های فعال: {len(active)}</b>\n"]
    for r in active[:70]:
        name = escape(r["first_name"] or "بدون نام")
        username = "@" + escape(r["username"]) if r["username"] else "بدون یوزرنیم"
        lines.append(f"• <a href=\"tg://user?id={r['user_id']}\">{name}</a> | <code>{r['user_id']}</code> | {username}\nانقضا: <code>{escape(r['expires_at'])}</code>")
    await query.answer()
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")]]))


@dp.callback_query(F.data == "admin_price")
async def cb_admin_price(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("set_price", None)
    await query.answer()
    await query.message.answer(f"قیمت فعلی: {toman(price_toman())}\nقیمت جدید اشتراک ۳۰ روزه را فقط به تومان و به‌صورت عدد ارسال کنید.", reply_markup=cancel_keyboard("admin_panel"))


@dp.callback_query(F.data == "admin_card")
async def cb_admin_card(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("set_card", None)
    await query.answer()
    await query.message.answer("نام صاحب کارت و شماره کارت را در یک پیام با این قالب ارسال کنید:\n<code>نام صاحب کارت | شماره کارت</code>\nشماره کارت به کاربر در قالب قابل کپی نمایش داده می‌شود.", parse_mode="HTML", reply_markup=cancel_keyboard("admin_panel"))


@dp.callback_query(F.data == "admin_general")
async def cb_admin_general(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("set_general", None)
    await query.answer()
    await query.message.answer("متن پاسخ عمومی کاربران عادی را ارسال کنید. از HTML ساده برای قالب‌بندی استفاده کنید.", reply_markup=cancel_keyboard("admin_panel"))


@dp.callback_query(F.data == "admin_welcome")
async def cb_admin_welcome(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("set_welcome", None)
    await query.answer()
    await query.message.answer("پیامی را ارسال کنید که بعد از تکمیل عضویت اجباری به کاربر نمایش داده شود.", reply_markup=cancel_keyboard("admin_panel"))


@dp.callback_query(F.data == "admin_links")
async def cb_admin_links(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    await query.answer()
    raw = get_setting("join_links", "")
    links = [line.strip() for line in raw.splitlines() if line.strip()]
    lines = ["🔗 <b>مدیریت لینک‌های عضویت</b>", "برای افزودن لینک، ابتدا یک پیام را مستقیماً از گروه/کانال فوروارد کن؛ سپس لینک دعوت همان مقصد را بفرست.", "ربات باید در آن مقصد ادمین باشد تا بتواند عضویت را بررسی کند.", "", "<b>لینک‌های ثبت‌شده:</b>"]
    if links:
        for i, line in enumerate(links, 1):
            lines.append(f"{i}. <code>{escape(line[:220])}</code>")
    else:
        lines.append("هنوز لینکی ثبت نشده است.")
    keyboard_rows = []
    for i, line in enumerate(links, 1):
        keyboard_rows.append([InlineKeyboardButton(text=f"🗑 حذف لینک {i}", callback_data=f"admin_link_del:{i-1}")])
    keyboard_rows.append([InlineKeyboardButton(text="➕ ثبت/جایگزینی لینک‌ها", callback_data="admin_links_set")])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")])
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))


@dp.callback_query(F.data == "admin_links_set")
async def cb_admin_links_set(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("add_link_wait_forward", None)
    await query.answer()
    await query.message.answer(
        "🔗 <b>ثبت لینک عضویت — مرحله ۱ از ۲</b>\n\n"
        "ابتدا یک پیام را مستقیماً از همان گروه/کانال برای ربات <b>فوروارد</b> کن.\n"
        "ربات شناسه مقصد را تشخیص می‌دهد و بررسی می‌کند که خودش ادمین باشد.\n\n"
        "بعد از آن لینک دعوت یا لینک عمومی همان مقصد را می‌گیریم. لینک‌های قبلی حذف نمی‌شوند.",
        parse_mode="HTML", reply_markup=cancel_keyboard("admin_links"))


@dp.callback_query(F.data.startswith("admin_link_del:"))
async def cb_admin_link_delete(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    try:
        index = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("شناسه لینک نامعتبر است.", show_alert=True)
        return
    links = [line.strip() for line in get_setting("join_links", "").splitlines() if line.strip()]
    if index < 0 or index >= len(links):
        await query.answer("این لینک قبلاً حذف شده یا وجود ندارد.", show_alert=True)
        return
    removed = links.pop(index)
    set_setting("join_links", "\n".join(links))
    await query.message.answer(f"🗑 لینک حذف شد: <code>{escape(removed[:180])}</code>", parse_mode="HTML")
    await cb_admin_links(query)


@dp.callback_query(F.data == "admin_personal")
async def cb_admin_personal(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ متن پاسخ ارسین", callback_data="admin_personal_reply")],
        [InlineKeyboardButton(text="🔄 روشن/خاموش پاسخ شخصی", callback_data="admin_personal_toggle")],
        [InlineKeyboardButton(text="🔑 کلمات کلیدی اختصاصی ارسین", callback_data="admin_personal_keywords")],
        [InlineKeyboardButton(text="🎯 پاسخ دلخواه برای کاربر دلخواه", callback_data="contact_rules")],
        [InlineKeyboardButton(text=("🟢 فیلتر تکرار پاسخ ارسین: روشن" if get_setting("admin_cooldown_enabled", "0") == "1" else "⚪ فیلتر تکرار پاسخ ارسین: خاموش"), callback_data="admin_personal_cooldown_toggle")],
        [InlineKeyboardButton(text=f"⏱ فاصله پاسخ عادی ارسین: {get_setting('admin_cooldown_minutes', '1')} دقیقه", callback_data="admin_personal_cooldown_time")],
        [InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")],
    ])
    await query.answer()
    await query.message.answer("👤 <b>پنل شخصی ارسین</b>\nاشتراک پلاس ارسین دائمی است. این بخش پاسخ‌های اتصال Business حساب ارسین را مدیریت می‌کند.", reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data == "admin_personal_reply")
async def cb_admin_personal_reply(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("set_admin_reply", None)
    await query.answer()
    await query.message.answer("متن پاسخ خودکار شخصی ارسین را ارسال کنید. می‌توانید HTML ساده استفاده کنید.", reply_markup=cancel_keyboard("admin_personal"))


@dp.callback_query(F.data == "admin_personal_keywords")
async def cb_admin_personal_keywords(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    rows = get_user_keywords(ARSIN_OWNER_ID)
    lines = ["🔑 <b>کلمات کلیدی اختصاصی ارسین</b>\nفرمت افزودن یا ویرایش: <code>کلمه | پاسخ</code>\n"]
    for row in rows[:40]:
        lines.append(f"• <code>{escape(row['word'])}</code> → {escape(row['response'][:70])} ({'🟢 فعال' if row['enabled'] else '⚪ غیرفعال'})")
    keyboard_rows = []
    for row in rows[:40]:
        keyboard_rows.append([InlineKeyboardButton(text=f"🗑 حذف: {row['word'][:42]}", callback_data=f"admin_personal_kw_del:{row['id']}")])
    keyboard_rows.append([InlineKeyboardButton(text="➕ افزودن / ویرایش کلمه ارسین", callback_data="admin_personal_kw_add")])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ تنظیمات پاسخ ارسین", callback_data="admin_personal")])
    if not rows:
        lines.append("هنوز کلمه اختصاصی برای ارسین ثبت نشده است.")
    await query.answer()
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))


@dp.callback_query(F.data == "admin_personal_kw_add")
async def cb_admin_personal_kw_add(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("add_arsin_keyword", None)
    await query.answer()
    await query.message.answer("کلمه و پاسخ مخصوص ارسین را با این قالب بفرست:\n<code>کلمه | پاسخ</code>\nاگر همان کلمه از قبل وجود داشته باشد، پاسخ آن به‌روزرسانی می‌شود.", parse_mode="HTML", reply_markup=cancel_keyboard("admin_personal_keywords"))


@dp.callback_query(F.data.startswith("admin_personal_kw_del:"))
async def cb_admin_personal_kw_delete(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    try:
        keyword_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("شناسه کلمه نامعتبر است.", show_alert=True)
        return
    with closing(db()) as conn:
        owner_ids = sorted({ARSIN_OWNER_ID, ADMIN_ID})
        marks = ",".join("?" for _ in owner_ids)
        cur = conn.execute(f"DELETE FROM user_keywords WHERE id=? AND user_id IN ({marks})", [keyword_id, *owner_ids])
        conn.commit()
    await query.answer("کلمه حذف شد." if cur.rowcount else "این کلمه دیگر وجود ندارد.")
    rows = get_user_keywords(ARSIN_OWNER_ID)
    lines = ["🔑 <b>کلمات کلیدی اختصاصی ارسین</b>\nفرمت افزودن یا ویرایش: <code>کلمه | پاسخ</code>\n"]
    for row in rows[:40]:
        lines.append(f"• <code>{escape(row['word'])}</code> → {escape(row['response'][:70])} ({'🟢 فعال' if row['enabled'] else '⚪ غیرفعال'})")
    keyboard_rows = [[InlineKeyboardButton(text=f"🗑 حذف: {row['word'][:42]}", callback_data=f"admin_personal_kw_del:{row['id']}")] for row in rows[:40]]
    keyboard_rows.append([InlineKeyboardButton(text="➕ افزودن / ویرایش کلمه ارسین", callback_data="admin_personal_kw_add")])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ تنظیمات پاسخ ارسین", callback_data="admin_personal")])
    if not rows:
        lines.append("هنوز کلمه اختصاصی برای ارسین ثبت نشده است.")
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))


@dp.callback_query(F.data == "admin_personal_toggle")
async def cb_admin_personal_toggle(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    value = "0" if get_setting("admin_auto_enabled", "1") == "1" else "1"
    set_setting("admin_auto_enabled", value)
    await query.answer("پاسخ شخصی ارسین روشن شد." if value == "1" else "پاسخ شخصی ارسین خاموش شد.")


@dp.callback_query(F.data == "admin_personal_cooldown_toggle")
async def cb_admin_personal_cooldown_toggle(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    value = "0" if get_setting("admin_cooldown_enabled", "0") == "1" else "1"
    set_setting("admin_cooldown_enabled", value)
    await query.answer("فیلتر تکرار پاسخ ارسین روشن شد." if value == "1" else "فیلتر تکرار پاسخ ارسین خاموش شد.")
    await query.message.answer("👤 <b>پنل شخصی ارسین</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ متن پاسخ ارسین", callback_data="admin_personal_reply")],
        [InlineKeyboardButton(text=("🔄 خاموش کردن پاسخ شخصی" if get_setting("admin_auto_enabled", "1") == "1" else "🔄 روشن کردن پاسخ شخصی"), callback_data="admin_personal_toggle")],
        [InlineKeyboardButton(text="🔑 کلمات کلیدی اختصاصی ارسین", callback_data="admin_personal_keywords")],
        [InlineKeyboardButton(text=("🟢 فیلتر تکرار پاسخ ارسین: روشن" if value == "1" else "⚪ فیلتر تکرار پاسخ ارسین: خاموش"), callback_data="admin_personal_cooldown_toggle")],
        [InlineKeyboardButton(text=f"⏱ فاصله پاسخ عادی ارسین: {get_setting('admin_cooldown_minutes', '1')} دقیقه", callback_data="admin_personal_cooldown_time")],
        [InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")],
    ]), parse_mode="HTML")


@dp.callback_query(F.data == "admin_personal_cooldown_time")
async def cb_admin_personal_cooldown_time(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("admin_cooldown_minutes", None)
    await query.answer()
    await query.message.answer("⏱ فاصله پاسخ عادی ارسین را به دقیقه بفرست (از ۱ تا ۱۰۰۸۰). مقدار پیش‌فرض ۱ دقیقه است. کلمات کلیدی از این فیلتر مستثنا هستند.", reply_markup=cancel_keyboard("admin_personal"))


@dp.callback_query(F.data == "admin_grant")
async def cb_admin_grant(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("grant_plus", None)
    await query.answer()
    await query.message.answer("شناسه عددی کاربر را ارسال کن. اشتراک ۳۰ روزه فعال یا تمدید می‌شود.", reply_markup=cancel_keyboard("admin_panel"))


@dp.callback_query(F.data == "admin_coupons")
async def cb_admin_coupons(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM coupons ORDER BY created_at DESC LIMIT 30").fetchall()
    text = ["🎟 <b>کدهای تخفیف</b>\nفرمت ساخت: کد | مبلغ تخفیف به تومان | حداکثر تعداد استفاده (۰ = نامحدود)\n"]
    for r in rows:
        text.append(f"• <code>{escape(r['code'])}</code> — {toman(r['discount_toman'])} — استفاده: {r['uses']}/{r['max_uses'] or '∞'} — {'فعال' if r['enabled'] else 'غیرفعال'}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ساخت کد تخفیف", callback_data="admin_coupon_add")], [InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")]])
    await query.answer()
    await query.message.answer("\n".join(text), parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "admin_coupon_add")
async def cb_admin_coupon_add(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("add_coupon", None)
    await query.answer()
    await query.message.answer("فرمت:\n<code>CODE | تخفیف به تومان | حداکثر استفاده</code>\nمثال:\n<code>ARSIN20 | 20000 | 100</code>\nبرای استفاده نامحدود، عدد آخر را ۰ بگذار.", parse_mode="HTML", reply_markup=cancel_keyboard("admin_coupons"))


@dp.callback_query(F.data == "admin_keywords")
async def cb_admin_keywords(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    rows = get_global_keywords()
    lines = ["🔑 <b>کلمات کلیدی عمومی</b>\nفرمت افزودن: کلمه | پاسخ\n"]
    for row in rows[:40]:
        lines.append(f"• <code>{escape(row['word'])}</code> → {escape(row['response'][:60])} (پیوی {'🟢' if row['private_enabled'] else '⚪'} / گروه {'🟢' if row['group_enabled'] else '⚪'})")
    keyboard_rows = []
    for row in rows[:40]:
        keyboard_rows.append([InlineKeyboardButton(text=f"🗑 حذف: {row['word'][:45]}", callback_data=f"admin_keyword_del:{row['id']}")])
    keyboard_rows.append([InlineKeyboardButton(text="➕ افزودن کلمه عمومی", callback_data="admin_keyword_add")])
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")])
    if not rows:
        lines.append("هنوز کلمه‌ای ثبت نشده است.")
    await query.answer()
    await query.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))


@dp.callback_query(F.data.startswith("admin_keyword_del:"))
async def cb_admin_keyword_delete(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    try:
        keyword_id = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.answer("شناسه کلمه نامعتبر است.", show_alert=True)
        return
    with closing(db()) as conn:
        cur = conn.execute("DELETE FROM keywords WHERE id=?", (keyword_id,))
        conn.commit()
        deleted = cur.rowcount
    if not deleted:
        await query.answer("این کلمه دیگر وجود ندارد.", show_alert=True)
        return
    await query.message.answer("🗑 کلمه کلیدی عمومی حذف شد.")
    await cb_admin_keywords(query)


@dp.callback_query(F.data == "admin_keyword_add")
async def cb_admin_keyword_add(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("add_global_keyword", None)
    await query.answer()
    await query.message.answer("فرمت:\n<code>کلمه | پاسخ</code>", parse_mode="HTML", reply_markup=cancel_keyboard("admin_keywords"))


@dp.callback_query(F.data == "admin_payments")
async def cb_admin_payments(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM payments WHERE status='proof_received' ORDER BY id DESC LIMIT 20").fetchall()
    if not rows:
        text = "🧾 فیش پرداخت بررسی‌نشده‌ای وجود ندارد."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")]])
    else:
        text = "🧾 <b>فیش‌های در انتظار بررسی</b>\nبرای هر فیش، دکمه‌های تأیید/رد در پیامی که هنگام ارسال فیش دریافت کرده‌ای وجود دارد.\n\n"
        text += "\n".join(f"پرداخت <code>#{r['id']}</code> | کاربر <a href=\"tg://user?id={r['user_id']}\">{r['user_id']}</a> | {toman(r['amount_due'])}" for r in rows)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")]])
    await query.answer()
    await query.message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query(F.data == "admin_announce")
async def cb_admin_announce(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("announcement_content", None)
    await query.answer()
    await query.message.answer("📢 متن، عکس یا GIF اطلاعیه را در پیام بعدی ارسال کن. این اطلاعیه برای همه کسانی که ربات را استارت کرده‌اند فرستاده می‌شود؛ عضویت اجباری شرط نیست.", reply_markup=cancel_keyboard("admin_panel"))


@dp.callback_query(F.data == "announce_duration_infinite")
async def cb_announce_duration_infinite(query: CallbackQuery):
    if not is_admin(query.from_user.id) or query.from_user.id not in pending_announcements:
        await query.answer("اطلاعیه‌ای در انتظار نیست.", show_alert=True)
        return
    await query.answer("ارسال اطلاعیه آغاز شد.")
    payload = pending_announcements.pop(query.from_user.id)
    user_states.pop(query.from_user.id, None)
    await broadcast_announcement(payload, None)
    await query.message.answer("✅ ارسال اطلاعیه نامحدود انجام شد. ربات آن را به‌صورت زمان‌بندی‌شده حذف نمی‌کند.", reply_markup=admin_keyboard())


@dp.callback_query(F.data == "announce_duration_limited")
async def cb_announce_duration_limited(query: CallbackQuery):
    if not is_admin(query.from_user.id):
        await query.answer("دسترسی ندارید.", show_alert=True)
        return
    user_states[query.from_user.id] = ("announcement_minutes", None)
    await query.answer()
    await query.message.answer("مدت اطلاعیه را به دقیقه وارد کن. حداکثر ۲۸۷۹ دقیقه (کمتر از ۴۸ ساعت) قابل زمان‌بندی است.", reply_markup=cancel_keyboard("admin_panel"))


async def broadcast_announcement(payload: dict, minutes: Optional[int]):
    users = all_users()
    delete_at = dt_text(now_utc() + timedelta(minutes=minutes)) if minutes else ""
    with closing(db()) as conn:
        cur = conn.execute("INSERT INTO announcements(created_at,delete_at,mode) VALUES(?,?,?)", (dt_text(now_utc()), delete_at, "limited" if minutes else "infinite"))
        ann_id = cur.lastrowid
        conn.execute("INSERT INTO announcement_payloads(announcement_id,payload_type,text_content,file_id) VALUES(?,?,?,?)", (ann_id, payload["type"], payload.get("text", ""), payload.get("file_id", "")))
        conn.commit()
    sent = 0
    for user in users:
        chat_id = int(user["user_id"])
        try:
            msg = await send_announcement_to(chat_id, payload)
            with closing(db()) as conn:
                conn.execute("INSERT OR IGNORE INTO announcement_messages(announcement_id,chat_id,message_id) VALUES(?,?,?)", (ann_id, chat_id, msg.message_id))
                conn.commit()
            sent += 1
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            logger.info("Announcement skipped for %s: %s", chat_id, exc)
        except TelegramAPIError as exc:
            logger.warning("Announcement failed for %s: %s", chat_id, exc)
        await asyncio.sleep(0.04)
    logger.info("Announcement %s sent to %s users", ann_id, sent)


async def send_announcement_to(chat_id: int, payload: dict):
    kind = payload["type"]
    if kind == "photo":
        return await bot.send_photo(chat_id, payload["file_id"], caption=payload.get("text", "")[:1024] or None, parse_mode="HTML")
    if kind == "animation":
        return await bot.send_animation(chat_id, payload["file_id"], caption=payload.get("text", "")[:1024] or None, parse_mode="HTML")
    if kind == "document":
        return await bot.send_document(chat_id, payload["file_id"], caption=payload.get("text", "")[:1024] or None, parse_mode="HTML")
    return await bot.send_message(chat_id, payload.get("text", "")[:4096], parse_mode="HTML")


# ============================================================
# ADMIN INPUT HANDLER
# ============================================================

async def handle_admin_input(message: Message, action: str, object_id: Optional[int]):
    uid = message.from_user.id
    text = (message.text or "").strip()
    if action == "set_price":
        try:
            amount = int(text.replace(",", "").replace("٬", "").replace(" ", ""))
            if amount < 0:
                raise ValueError
        except ValueError:
            await message.answer("قیمت باید یک عدد صفر یا بزرگ‌تر به تومان باشد.")
            return
        set_setting("subscription_price", str(amount))
        user_states.pop(uid, None)
        await message.answer(f"✅ قیمت اشتراک ذخیره شد: {toman(amount)}", reply_markup=admin_keyboard())
    elif action == "set_card":
        if "|" not in text:
            await message.answer("فرمت صحیح: نام صاحب کارت | شماره کارت")
            return
        holder, card = [p.strip() for p in text.split("|", 1)]
        if not holder or not card:
            await message.answer("نام و شماره کارت هر دو لازم هستند.")
            return
        set_setting("card_holder", holder)
        set_setting("card_number", card)
        user_states.pop(uid, None)
        await message.answer("✅ اطلاعات کارت ذخیره شد.", reply_markup=admin_keyboard())
    elif action == "set_general":
        if not text:
            await message.answer("متن خالی است.")
            return
        set_setting("general_reply", text[:4096])
        user_states.pop(uid, None)
        await message.answer("✅ پاسخ عمومی ذخیره شد.", reply_markup=admin_keyboard())
    elif action == "set_welcome":
        if not text:
            await message.answer("متن خالی است.")
            return
        set_setting("welcome_text", text[:4096])
        user_states.pop(uid, None)
        await message.answer("✅ پیام بعد از عضویت ذخیره شد.", reply_markup=admin_keyboard())
    elif action == "add_link_wait_forward":
        chat_id = forwarded_source_chat_id(message)
        if not chat_id:
            await message.answer(
                "❌ شناسه مقصد از این پیام استخراج نشد. یک پیام را مستقیماً از همان گروه/کانال با گزینه Forward بفرست؛ کپی‌کردن متن کافی نیست.")
            return
        if not await bot_is_admin(chat_id):
            await message.answer(
                f"❌ ربات در مقصد <code>{chat_id}</code> ادمین نیست یا دسترسی لازم ندارد.\n"
                "ابتدا ربات را به همان گروه/کانال اضافه و ادمین کن، سپس دوباره پیام را فوروارد کن.", parse_mode="HTML")
            return
        user_states[uid] = ("add_link_wait_url", int(chat_id))
        await message.answer(
            f"✅ شناسه مقصد تشخیص داده شد: <code>{chat_id}</code>\n\n"
            "<b>مرحله ۲ از ۲:</b> حالا لینک دعوت یا لینک عمومی همین گروه/کانال را بفرست.\n"
            "مثال: <code>https://t.me/MyGroup</code> یا <code>https://t.me/+InviteCode</code>",
            parse_mode="HTML", reply_markup=cancel_keyboard("admin_links"))
    elif action == "add_link_wait_url":
        url = text.strip()
        if not url or not re.match(r"^https?://t\.me/", url, re.IGNORECASE):
            await message.answer("❌ لینک معتبر تلگرام بفرست؛ قالب باید با https://t.me/ شروع شود.")
            return
        chat_id = int(object_id) if object_id is not None else None
        if not chat_id:
            user_states.pop(uid, None)
            await message.answer("❌ شناسه مقصد از دست رفته است. ثبت لینک را دوباره شروع کن.")
            return
        if not await bot_is_admin(chat_id):
            await message.answer("❌ ربات دیگر در این مقصد ادمین نیست؛ ابتدا دسترسی را اصلاح کن.")
            return
        existing = [line.strip() for line in get_setting("join_links", "").splitlines() if line.strip()]
        existing = [line for line in existing if line.split("|", 1)[-1].strip() != url]
        existing.append(f"{chat_id} | {url}")
        set_setting("join_links", "\n".join(existing))
        user_states.pop(uid, None)
        await message.answer(
            f"✅ لینک عضویت ثبت شد.\nشناسه مقصد: <code>{chat_id}</code>\nلینک: <code>{escape(url)}</code>\n\n"
            "برای تست، از یک حساب معمولی /start بزن و بعد از عضویت روی «بررسی عضویت» بزن.",
            parse_mode="HTML", reply_markup=admin_keyboard())
    elif action == "set_links":
        # Backward-compatible path for older UI states.
        set_setting("join_links", text)
        user_states.pop(uid, None)
        await message.answer("✅ فهرست لینک‌ها ذخیره شد.", reply_markup=admin_keyboard())
    elif action == "set_admin_reply":
        # Photos and GIFs must be handled before checking message.text; Telegram media
        # captions are stored in message.caption, not message.text.
        if message.photo:
            file_id = message.photo[-1].file_id
            caption = (message.caption or "")[:1024]
            set_setting("admin_media_type", "photo")
            set_setting("admin_media_file_id", file_id)
            set_setting("admin_caption", caption)
            set_setting("admin_reply", caption)
            user_states.pop(uid, None)
            await message.answer("✅ عکس پاسخ شخصی ارسین ذخیره شد. این عکس همراه کپشن، پاسخ پیش‌فرض حساب Business ارسین خواهد بود.", reply_markup=admin_keyboard())
            return
        if message.animation:
            file_id = message.animation.file_id
            caption = (message.caption or "")[:1024]
            set_setting("admin_media_type", "animation")
            set_setting("admin_media_file_id", file_id)
            set_setting("admin_caption", caption)
            set_setting("admin_reply", caption)
            user_states.pop(uid, None)
            await message.answer("✅ GIF پاسخ شخصی ارسین ذخیره شد.", reply_markup=admin_keyboard())
            return
        if not text:
            await message.answer("لطفاً متن، عکس یا GIF بفرست. ارسال متن ساده، رسانه قبلی را پاک می‌کند.")
            return
        set_setting("admin_reply", text[:4096])
        set_setting("admin_media_type", "")
        set_setting("admin_media_file_id", "")
        set_setting("admin_caption", "")
        user_states.pop(uid, None)
        await message.answer("✅ متن پاسخ شخصی ارسین ذخیره شد. رسانه قبلی پاک شد.", reply_markup=admin_keyboard())
    elif action == "grant_plus":
        try:
            target = int(text)
            if target <= 0:
                raise ValueError
        except ValueError:
            await message.answer("شناسه عددی معتبر وارد کن.")
            return
        ensure_user(target)
        expiry = activate_subscription(target, 30, source="admin_grant")
        user_states.pop(uid, None)
        await message.answer(f"✅ اشتراک ۳۰ روزه برای کاربر <code>{target}</code> فعال شد.\nانقضا: <code>{escape(expiry.strftime('%Y-%m-%d %H:%M UTC'))}</code>", parse_mode="HTML", reply_markup=admin_keyboard())
        try:
            await bot.send_message(target, f"🎉 ارسین برای شما اشتراک پلاس فعال کرد!\nانقضا: <code>{escape(expiry.strftime('%Y-%m-%d %H:%M UTC'))}</code>", parse_mode="HTML", reply_markup=user_keyboard(target))
        except TelegramAPIError:
            pass
    elif action == "add_coupon":
        parts = [p.strip() for p in text.split("|")]
        if len(parts) != 3:
            await message.answer("فرمت: CODE | مبلغ تخفیف به تومان | حداکثر استفاده")
            return
        code = parts[0].upper()
        try:
            amount, max_uses = int(parts[1]), int(parts[2])
            if not code or amount <= 0 or max_uses < 0:
                raise ValueError
        except ValueError:
            await message.answer("مبلغ تخفیف باید مثبت و حداکثر استفاده صفر یا بزرگ‌تر باشد.")
            return
        try:
            add_coupon(code, amount, max_uses)
        except sqlite3.IntegrityError:
            await message.answer("این کد قبلاً ثبت شده است.")
            return
        user_states.pop(uid, None)
        await message.answer(f"✅ کد <code>{escape(code)}</code> با تخفیف {toman(amount)} ثبت شد.", parse_mode="HTML", reply_markup=admin_keyboard())
    elif action == "add_arsin_keyword":
        if not text or "|" not in text:
            await message.answer("فرمت صحیح: کلمه | پاسخ")
            return
        word, response = [p.strip() for p in text.split("|", 1)]
        if not word or not response:
            await message.answer("کلمه و پاسخ نباید خالی باشند.")
            return
        try:
            with closing(db()) as conn:
                owner_ids = sorted({ARSIN_OWNER_ID, ADMIN_ID})
                for owner_id in owner_ids:
                    existing = conn.execute("SELECT id FROM user_keywords WHERE user_id=? AND lower(word)=lower(?) ORDER BY id DESC LIMIT 1", (owner_id, word)).fetchone()
                    if existing:
                        conn.execute("UPDATE user_keywords SET word=?, response=?, enabled=1 WHERE id=?", (word, response, existing["id"]))
                    else:
                        conn.execute("INSERT INTO user_keywords(user_id,word,response,enabled) VALUES(?,?,?,1)", (owner_id, word, response))
                conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Arsin personal keyword error: %s", exc)
            await message.answer("ذخیره کلمه اختصاصی ارسین ناموفق بود؛ گزارش خطا در لاگ ثبت شد.")
            return
        user_states.pop(uid, None)
        await message.answer(f"✅ پاسخ کلمه «{escape(word)}» مخصوص ارسین ذخیره شد.", parse_mode="HTML", reply_markup=admin_keyboard())
    elif action == "add_global_keyword":
        if not text or "|" not in text:
            await message.answer("فرمت: کلمه | پاسخ")
            return
        word, response = [p.strip() for p in text.split("|", 1)]
        if not word or not response:
            await message.answer("کلمه و پاسخ نباید خالی باشند.")
            return
        try:
            with closing(db()) as conn:
                existing = conn.execute("SELECT id FROM keywords WHERE lower(word)=lower(?) ORDER BY id DESC LIMIT 1", (word,)).fetchone()
                if existing:
                    conn.execute("UPDATE keywords SET word=?, response=? WHERE id=?", (word, response, existing["id"]))
                else:
                    conn.execute("INSERT INTO keywords(word,response) VALUES(?,?)", (word, response))
                conn.commit()
        except sqlite3.Error as exc:
            logger.warning("Global keyword error: %s", exc)
            await message.answer("ذخیره کلمه ناموفق بود.")
            return
        user_states.pop(uid, None)
        await message.answer("✅ کلمه کلیدی عمومی ذخیره شد.", reply_markup=admin_keyboard())
    elif action == "announcement_content":
        payload = None
        if message.photo:
            payload = {"type": "photo", "file_id": message.photo[-1].file_id, "text": message.caption or ""}
        elif message.animation:
            payload = {"type": "animation", "file_id": message.animation.file_id, "text": message.caption or ""}
        elif message.document:
            payload = {"type": "document", "file_id": message.document.file_id, "text": message.caption or ""}
        elif message.text:
            payload = {"type": "text", "text": message.text}
        if not payload or (payload["type"] == "text" and not payload.get("text", "").strip()):
            await message.answer("لطفاً متن، عکس، GIF یا سند اطلاعیه را ارسال کن.")
            return
        pending_announcements[uid] = payload
        user_states[uid] = ("announcement_duration_choice", None)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="♾ نامحدود", callback_data="announce_duration_infinite")],
            [InlineKeyboardButton(text="⏱ محدود", callback_data="announce_duration_limited")],
        ])
        await message.answer("مدت اطلاعیه را انتخاب کن:", reply_markup=keyboard)
    elif action == "announcement_minutes":
        try:
            minutes = int(text)
            if minutes < 1 or minutes > 2879:
                raise ValueError
        except ValueError:
            await message.answer("عدد باید بین ۱ تا ۲۸۷۹ دقیقه باشد.")
            return
        payload = pending_announcements.pop(uid, None)
        user_states.pop(uid, None)
        if not payload:
            await message.answer("اطلاعیه‌ای در انتظار ارسال نیست.")
            return
        await message.answer("⏳ در حال ارسال اطلاعیه به کاربران...")
        await broadcast_announcement(payload, minutes)
        await message.answer(f"✅ اطلاعیه ارسال شد و برای حذف پس از {minutes} دقیقه زمان‌بندی شد.", reply_markup=admin_keyboard())


@dp.callback_query(F.data.startswith("cancel:"))
async def cb_cancel(query: CallbackQuery):
    user_states.pop(query.from_user.id, None)
    pending_announcements.pop(query.from_user.id, None)
    await query.answer("لغو شد.")
    target = query.data.split(":", 1)[1]
    if target == "admin_panel" and is_admin(query.from_user.id):
        await query.message.answer("🎛 پنل مدیریت ارسین", reply_markup=admin_keyboard())
    elif target == "admin_links" and is_admin(query.from_user.id):
        await cb_admin_links(query)
    elif target == "admin_keywords" and is_admin(query.from_user.id):
        await cb_admin_keywords(query)
    elif target == "admin_personal" and is_admin(query.from_user.id):
        await cb_admin_personal(query)
    elif target == "admin_personal_keywords" and is_admin(query.from_user.id):
        await cb_admin_personal_keywords(query)
    elif target == "admin_coupons" and is_admin(query.from_user.id):
        await query.message.answer("🎟 کدهای تخفیف", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ ساخت کد", callback_data="admin_coupon_add")], [InlineKeyboardButton(text="⬅️ پنل مدیریت", callback_data="admin_panel")]]))
    else:
        await query.message.answer("منو:", reply_markup=user_keyboard(query.from_user.id))


# ============================================================
# BUSINESS CONNECTION AND MESSAGE HANDLERS
# ============================================================

@dp.business_connection()
async def business_connection(event):
    save_business_connection(event)
    logger.info("Business connection update: user=%s enabled=%s rights=%s status=%s",
                event.user.id, event.is_enabled, getattr(event, "rights", None), connection_status_text(event.user.id))
    try:
        if event.user.id == ARSIN_OWNER_ID:
            await bot.send_message(ADMIN_ID, "🔗 اتصال Business حساب شخصی ارسین به‌روزرسانی شد.\n" + connection_status_text(ARSIN_OWNER_ID), parse_mode="HTML")
            if ARSIN_OWNER_ID != ADMIN_ID:
                await bot.send_message(ARSIN_OWNER_ID, "🔗 اتصال Telegram Business به‌روزرسانی شد.\n" + connection_status_text(ARSIN_OWNER_ID), parse_mode="HTML", reply_markup=user_keyboard(ARSIN_OWNER_ID))
        elif event.user.id == ADMIN_ID:
            await bot.send_message(ADMIN_ID, "🔗 اتصال Business به‌روزرسانی شد.\n" + connection_status_text(ADMIN_ID), parse_mode="HTML")
        else:
            await bot.send_message(event.user.id, "🔗 اتصال Telegram Business به‌روزرسانی شد.\n" + connection_status_text(event.user.id), parse_mode="HTML", reply_markup=user_keyboard(event.user.id))
    except TelegramAPIError:
        pass


def default_reply_cooldown_enabled(owner_id: int) -> bool:
    if is_arsin_owner(owner_id):
        return get_setting("admin_cooldown_enabled", "0") == "1"
    if not is_plus(owner_id):
        return False
    user = get_user(owner_id)
    return bool(user and int(user["cooldown_enabled"]))


def default_reply_cooldown_minutes(owner_id: int) -> int:
    if is_arsin_owner(owner_id):
        raw = get_setting("admin_cooldown_minutes", "1")
    else:
        user = get_user(owner_id)
        raw = user["cooldown_minutes"] if user else 1
    try:
        return max(1, min(10080, int(raw)))
    except (TypeError, ValueError):
        return 1


def default_reply_is_cooling_down(owner_id: int, chat_id: int) -> bool:
    """Throttle only ordinary/default replies for Plus customers and Arsin's personal account."""
    if not default_reply_cooldown_enabled(owner_id):
        return False
    minutes = default_reply_cooldown_minutes(owner_id)
    with closing(db()) as conn:
        row = conn.execute(
            "SELECT last_sent_at FROM default_reply_cooldowns WHERE owner_id=? AND chat_id=?",
            (owner_id, chat_id),
        ).fetchone()
    last_sent = parse_dt(row["last_sent_at"]) if row else None
    return bool(last_sent and now_utc() < last_sent + timedelta(minutes=minutes))


def mark_default_reply_sent(owner_id: int, chat_id: int):
    with closing(db()) as conn:
        conn.execute(
            "INSERT INTO default_reply_cooldowns(owner_id,chat_id,last_sent_at) VALUES(?,?,?) "
            "ON CONFLICT(owner_id,chat_id) DO UPDATE SET last_sent_at=excluded.last_sent_at",
            (owner_id, chat_id, dt_text(now_utc())),
        )
        conn.commit()


@dp.callback_query(F.data == "user_toggle_cooldown")
async def cb_user_toggle_cooldown(query: CallbackQuery):
    uid = query.from_user.id
    if not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    ensure_user(uid, query.from_user.first_name, query.from_user.username or "")
    user = get_user(uid)
    value = 0 if int(user["cooldown_enabled"]) else 1
    with closing(db()) as conn:
        conn.execute("UPDATE users SET cooldown_enabled=? WHERE user_id=?", (value, uid))
        conn.commit()
    await query.answer("فیلتر تکرار پاسخ روشن شد." if value else "فیلتر تکرار پاسخ خاموش شد.")
    await query.message.edit_reply_markup(reply_markup=user_keyboard(uid))
    if value:
        await query.message.answer("✅ فیلتر روشن است: پاسخ عادی هر مخاطب فقط یک بار در فاصله تعیین‌شده ارسال می‌شود. پاسخ کلمات کلیدی همیشه ارسال می‌شود.")


@dp.callback_query(F.data == "user_set_cooldown")
async def cb_user_set_cooldown(query: CallbackQuery):
    uid = query.from_user.id
    if not is_plus(uid):
        await query.answer("این قابلیت مخصوص اشتراک پلاس است.", show_alert=True)
        return
    user_states[uid] = ("cooldown_minutes", None)
    await query.answer()
    await query.message.answer("⏱ فاصله زمانی پاسخ عادی را به دقیقه بفرست (از ۱ تا ۱۰۰۸۰ دقیقه).\nمثلاً ۱ یعنی پس از پاسخ اول، تا یک دقیقه پاسخ عادی دیگری ارسال نمی‌شود. کلمات کلیدی از این محدودیت مستثنا هستند.", reply_markup=cancel_keyboard("user_menu"))


@dp.business_message()
async def business_message(message: Message):
    logger.info("Business message update received: from_user=%s chat_id=%s connection_id=%s text=%s",
                getattr(message.from_user, "id", None), message.chat.id,
                getattr(message, "business_connection_id", None), bool(message.text or message.caption))
    if not get_setting("enabled", "1") == "1":
        logger.warning("Business message ignored because global enabled setting is off")
        return
    connection_id = message.business_connection_id
    if not connection_id:
        return
    conn = None
    with closing(db()) as db_conn:
        conn = db_conn.execute("SELECT * FROM business_connections WHERE id=?", (connection_id,)).fetchone()
    if not conn:
        logger.warning("Business message ignored: no saved connection for connection_id=%s", connection_id)
        return
    if not conn["is_enabled"] or not conn["can_reply"]:
        logger.warning("Business message ignored: connection disabled or can_reply missing; owner=%s enabled=%s can_reply=%s can_read=%s",
                       conn["user_id"], conn["is_enabled"], conn["can_reply"], conn["can_read_messages"])
        return
    owner_id = int(conn["user_id"])
    logger.info("Business message received: owner_id=%s connection=%s chat_id=%s enabled=%s can_reply=%s",
                owner_id, connection_id, message.chat.id, conn["is_enabled"], conn["can_reply"])
    # Do not respond to messages sent by the account owner.
    if message.from_user and message.from_user.id == owner_id:
        return
    if is_arsin_owner(owner_id):
        if get_setting("admin_auto_enabled", "1") != "1":
            return
    else:
        user = get_user(owner_id)
        if not user or not user["auto_enabled"]:
            return
    text = message.text or message.caption or ""
    is_group = message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    sender_id = int(message.from_user.id) if message.from_user else int(message.chat.id)
    if message.from_user and message.from_user.username:
        link_pending_contact(owner_id, sender_id, message.from_user.username, message.from_user.full_name)
    # Most-specific contact keywords always win and always bypass cooldown.
    response = find_contact_keyword(text, owner_id, sender_id) if text else None
    if not response:
        response = find_keyword(text, is_group, owner_id) if text else None
    try:
        if response:
            await send_custom_reply(connection_id, message.chat.id, owner_id, response)
            return
        if message.chat.type != ChatType.PRIVATE:
            return
        # Contact-specific ordinary replies replace the generic default but remain throttled.
        contact_reply = get_contact_reply(owner_id, sender_id)
        # Cooldown affects only ordinary/default replies. All keyword replies above bypass it.
        if default_reply_is_cooling_down(owner_id, message.chat.id):
            logger.info("Default reply suppressed by Plus cooldown: owner=%s chat=%s", owner_id, message.chat.id)
            return
        if contact_reply:
            await send_custom_reply(connection_id, message.chat.id, owner_id, contact_reply)
        else:
            await send_owner_default(connection_id, message.chat.id, owner_id)
        if default_reply_cooldown_enabled(owner_id):
            mark_default_reply_sent(owner_id, message.chat.id)
    except (TelegramForbiddenError, TelegramBadRequest) as exc:
        logger.warning("Business reply failed for owner %s: %s", owner_id, exc)
    except TelegramAPIError as exc:
        logger.exception("Business API error while replying for owner %s, connection=%s, chat=%s: %s",
                         owner_id, connection_id, message.chat.id, exc)
    except Exception:
        logger.exception("Unexpected error in business auto-reply for owner %s", owner_id)


# ============================================================
# SUBSCRIPTION REMINDERS AND TIMED ANNOUNCEMENTS
# ============================================================

async def subscription_reminder_loop():
    while True:
        try:
            now = now_utc()
            soon = now + timedelta(days=3)
            with closing(db()) as conn:
                rows = conn.execute("SELECT s.user_id,s.expires_at,u.last_reminder_at FROM subscriptions s JOIN users u ON u.user_id=s.user_id").fetchall()
            for row in rows:
                uid = int(row["user_id"])
                expiry = parse_dt(row["expires_at"])
                if not expiry or expiry <= now or expiry > soon:
                    continue
                last = parse_dt(row["last_reminder_at"])
                # One reminder per subscription window; reset once subscription is extended beyond 3 days.
                if last and now - last < timedelta(days=1):
                    continue
                try:
                    await bot.send_message(uid, "⏰ <b>یادآوری اشتراک پلاس</b>\nفقط ۳ روز یا کمتر از اشتراک شما باقی مانده است. برای تمدید، روی دکمه زیر بزنید.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 تمدید اشتراک", callback_data="renew")]]))
                    with closing(db()) as conn:
                        conn.execute("UPDATE users SET last_reminder_at=? WHERE user_id=?", (dt_text(now), uid))
                        conn.commit()
                except TelegramAPIError as exc:
                    logger.info("Reminder failed for %s: %s", uid, exc)
                await asyncio.sleep(0.03)
        except Exception:
            logger.exception("Subscription reminder loop error")
        await asyncio.sleep(3600)


async def announcement_delete_loop():
    while True:
        try:
            now = dt_text(now_utc())
            with closing(db()) as conn:
                rows = conn.execute("SELECT id FROM announcements WHERE mode='limited' AND delete_at!='' AND delete_at<=?", (now,)).fetchall()
            for ann in rows:
                ann_id = int(ann["id"])
                with closing(db()) as conn:
                    msgs = conn.execute("SELECT id,chat_id,message_id FROM announcement_messages WHERE announcement_id=? AND deleted=0", (ann_id,)).fetchall()
                for item in msgs:
                    try:
                        await bot.delete_message(chat_id=item["chat_id"], message_id=item["message_id"])
                    except (TelegramBadRequest, TelegramForbiddenError) as exc:
                        logger.info("Timed announcement delete failed chat=%s message=%s: %s", item["chat_id"], item["message_id"], exc)
                    except TelegramAPIError as exc:
                        logger.warning("Timed announcement delete API error: %s", exc)
                    finally:
                        with closing(db()) as conn:
                            conn.execute("UPDATE announcement_messages SET deleted=1 WHERE id=?", (item["id"],))
                            conn.commit()
                    await asyncio.sleep(0.03)
                with closing(db()) as conn:
                    conn.execute("UPDATE announcements SET mode='completed' WHERE id=?", (ann_id,))
                    conn.commit()
        except Exception:
            logger.exception("Announcement deletion loop error")
        await asyncio.sleep(20)


# ============================================================
# FALLBACK / RUN
# ============================================================

@dp.message(F.chat.type == ChatType.PRIVATE, F.text)
async def fallback_private_text(message: Message):
    # Inputs are handled by private_user_inputs when a state exists.
    if not message.from_user:
        return
    if is_admin(message.from_user.id):
        return
    # Do not expose the private menu before membership check.
    ok, missing = await check_membership(message.from_user.id)
    if not ok:
        await message.answer("برای استفاده از ربات ابتدا در لینک‌های اجباری عضو شو.", reply_markup=join_keyboard(missing))


async def main():
    db_init()
    me = await bot.get_me()
    logger.info("========================================")
    logger.info("ARSIN AUTO REPLY v2 STARTED")
    logger.info("Bot: @%s | ID: %s", me.username, me.id)
    logger.info("Admin ID: %s", ADMIN_ID)
    logger.info("Arsin personal Business owner ID: %s", ARSIN_OWNER_ID)
    logger.info("Database: %s", DB_PATH)
    logger.info("========================================")
    tasks = [
        asyncio.create_task(subscription_reminder_loop()),
        asyncio.create_task(announcement_delete_loop()),
    ]
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query", "business_connection", "business_message"])
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped.")
