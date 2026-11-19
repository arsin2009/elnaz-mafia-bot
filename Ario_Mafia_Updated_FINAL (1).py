import os
import asyncio
import random
import re
import json
import html
import sqlite3
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
    ChatMemberUpdated,
)

# ================================================================
# CONFIG
# ================================================================
# V20 — black market combat expansion + concurrency hardening
TOKEN = "659564757:AAHJUliFimNsIHB-JBG0OJmloD8VlsFZkR4"
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

ARSIN_USERNAME = "arsin_mo"
DB = os.getenv("DB_PATH", "elnaz_bot_data.sqlite3")
MIN_PLAYERS = 5
MAX_PLAYERS = 18
SETUP_REPEAT_SECONDS = 20
COIN_BASE_REWARD = 20
COIN_COOLDOWN = 300
AUNT_GAME_COOLDOWN = 1500  # 25 minutes
MENU_INACTIVITY_TIMEOUT = 240  # 4 minutes

# ================================================================
# ⚽ FOOTBALL TEAM / CLUB SYSTEM
# ================================================================
FOOTBALL_TEAM_CREATION_COST = 20_000_000
FOOTBALL_MAX_PLAYERS = 22
FOOTBALL_MIN_STAKE = 1
FOOTBALL_DAILY_INCOME_DEFAULT_PER_POWER = 1_000_000
FOOTBALL_GAME_COOLDOWN = 3600
FOOTBALL_CONTRACT_NOTICE_DAYS = 10
FOOTBALL_LINEUP_LIMITS = {"دروازه بان": 1, "حمله": 3, "هافبک": 4, "دفاع": 4}
FOOTBALL_CONTRACT_MONTH_DAYS = 30
FOOTBALL_CONTRACT_YEAR_DAYS = 365
FOOTBALL_CONTRACT_3YEAR_DAYS = 1095
FOOTBALL_CONTRACT_OPTIONS = (("1 ماهه", 1, 30), ("1 ساله", 12, 365), ("3 ساله", 36, 1095))
FOOTBALL_POSITIONS = ("دفاع", "هافبک", "حمله", "دروازه بان")

FOOTBALL_FAMOUS_PLAYERS = {
    "دفاع": [("ویرژیل فن دایک", 94), ("سرخیو راموس", 91), ("روبن دیاز", 90), ("ویلیام سالیبا", 89), ("آنتونیو رودیگر", 89), ("ترنت الکساندر آرنولد", 88), ("اشرف حکیمی", 90), ("آلفونسو دیویس", 88), ("مارکینیوس", 90), ("جان استونز", 87), ("کیم مین جائه", 87), ("ژول کونده", 87), ("اندرو رابرتسون", 86), ("کایل واکر", 86), ("ماتیس دی‌لیخت", 86)],
    "هافبک": [("لوکا مودریچ", 93), ("کوین دی‌بروینه", 94), ("جود بلینگام", 95), ("رودری", 95), ("تونی کروس", 92), ("فدریکو والورده", 91), ("برونو فرناندز", 91), ("پدری", 89), ("فرنکی دی‌یونگ", 89), ("برناردو سیلوا", 92), ("نگولو کانته", 88), ("مارتین اودگارد", 90), ("دکلان رایس", 89), ("جمال موسیالا", 91), ("فلوریان ویرتز", 91)],
    "حمله": [("کریستیانو رونالدو", 96), ("لیونل مسی", 97), ("کیلیان امباپه", 96), ("ارلینگ هالند", 96), ("وینیسیوس جونیور", 95), ("نیمار", 92), ("محمد صلاح", 93), ("هری کین", 94), ("رابرت لواندوفسکی", 94), ("سون هیونگ مین", 92), ("لامین یامال", 91), ("عثمان دمبله", 90), ("رودریگو", 90), ("جولیان آلوارز", 90), ("خویچا کواراتسخلیا", 89)],
    "دروازه بان": [("تیبو کورتوا", 95), ("آلیسون بکر", 94), ("مانوئل نویر", 92), ("جان‌لوئیجی دوناروما", 93), ("امیلیانو مارتینز", 91), ("ادرسون", 91), ("یان سومر", 88), ("مایک مانیان", 92), ("مارک آندره تراشتگن", 91), ("کاسپر اشمایکل", 87), ("دیوگو کوستا", 88), ("اونانا", 86), ("بونو", 88), ("کیم سئونگ گیو", 84), ("جوردن پیکفورد", 87)],
}

def _football_generated_names(position):
    prefixes = {
        "دفاع": "مدافع", "هافبک": "هافبک", "حمله": "مهاجم", "دروازه بان": "دروازه‌بان"
    }
    return [(f"{prefixes[position]} شماره {i}", 65 + ((i * 7) % 25)) for i in range(1, 36)]

FOOTBALL_COACH_FAMOUS = [
    ("پپ گواردیولا", 98), ("کارلو آنچلوتی", 97), ("یورگن کلوپ", 96), ("ژوزه مورینیو", 94),
    ("زین‌الدین زیدان", 95), ("سیمئونه", 93), ("آرسن ونگر", 92), ("الکس فرگوسن", 99),
    ("ژابی آلونسو", 92), ("لوئیس انریکه", 94), ("توماس توخل", 93), ("آنتونیو کونته", 94),
    ("میکل آرتتا", 91), ("روبرتو دی‌زربی", 89), ("ماسیمیلیانو آلگری", 91), ("اونای امری", 90),
    ("تن هاخ", 88), ("فابیو کاپلو", 94), ("مارچلو لیپی", 95), ("ویسنته دل‌بوسکه", 95),
]

def football_seed_data(c):
    if int(c.execute("SELECT COUNT(*) FROM football_coaches").fetchone()[0]) == 0:
        coaches = list(FOOTBALL_COACH_FAMOUS)
        coaches += [(f"مربی شماره {i}", 70 + ((i * 11) % 26)) for i in range(1, 101 - len(coaches) + 1)]
        for name,power in coaches[:100]:
            monthly = max(5_000_000, 5_000_000 + max(0, power-70)*500_000)
            c.execute("INSERT INTO football_coaches(name,power,monthly_price) VALUES(?,?,?)", (name,power,monthly))
    if int(c.execute("SELECT COUNT(*) FROM football_players").fetchone()[0]) == 0:
        for position in FOOTBALL_POSITIONS:
            players = list(FOOTBALL_FAMOUS_PLAYERS[position]) + _football_generated_names(position)
            for name,power in players[:50]:
                monthly = max(5_000_000, 5_000_000 + max(0, power-65)*300_000)
                c.execute("INSERT INTO football_players(name,position,power,monthly_price) VALUES(?,?,?,?)", (name,position,power,monthly))


# ================================================================
# PROPERTY / REAL ESTATE SYSTEM
# ================================================================
PROPERTY_REGIONS = [
    (1, "نیاوران", 200000),
    (2, "سعادت آباد", 190000),
    (3, "زعفرانیه", 180000),
    (4, "الهیه", 160000),
    (5, "فرمانیه", 140000),
    (6, "پاسداران", 110000),
    (7, "ونک", 80000),
    (8, "جردن", 60000),
    (9, "تهرانپارس", 30000),
    (10, "چیتگر", 10000),
]
PROPERTY_SIZES = [50, 100, 150, 200]
MALL_STORE_SIZES = [1, 10, 30, 50, 60, 100, 150, 200, 300, 600]
MALL_STORE_PRICE_PER_METER = 300000
BUSINESS_ITEM_CODES = {
    "🎮 کنسول PS4": "K01",
    "🎮 کنسول PS5": "K02",
    "🎮 کنسول Xbox Series S": "K03",
    "🎮 کنسول Xbox Series X": "K04",
    "🖥️ مانیتور 24 اینچ سونی": "K05",
    "🛋️ مبل تک نفره": "K06",
    "🪛 پایه دیواری مانیتور 24 سونی": "K07",
    "🖥️ کامپیوتر PC نسل 9 گیمینگ": "K08",
    "⌨️🖱️ پک کیبورد و موس ریزر گیمینگ": "K09",
}
BUSINESS_ITEM_DEFAULTS = {
    "🎮 کنسول PS4": (100000, "کنسول برای پک گیمینگ"),
    "🎮 کنسول PS5": (200000, "کنسول برای پک گیمینگ"),
    "🎮 کنسول Xbox Series S": (90000, "کنسول برای پک گیمینگ"),
    "🎮 کنسول Xbox Series X": (225000, "کنسول برای پک گیمینگ"),
    "🖥️ مانیتور 24 اینچ سونی": (50000, "مانیتور موردنیاز هر پک"),
    "🛋️ مبل تک نفره": (15000, "مبل موردنیاز هر پک"),
    "🪛 پایه دیواری مانیتور 24 سونی": (5000, "پایه موردنیاز هر پک"),
    "🖥️ کامپیوتر PC نسل 9 گیمینگ": (300000, "کامپیوتر برای پک کامپیوتری"),
    "⌨️🖱️ پک کیبورد و موس ریزر گیمینگ": (10000, "کیبورد و موس موردنیاز پک کامپیوتری"),
}

# Each material is calculated from a base requirement for a 100m² house.
# package_size/package_price allows exact formulas such as 1,000 bricks = 30,000 Arior.
BUILDING_MATERIALS = [
    ("آجر", "عدد", 100000, 1000, 30000, "🧱"),
    ("آهن", "تن", 10, 1, 500000, "🔩"),
    ("سیمان", "تن", 20, 1, 120000, "🧱"),
    ("گچ", "تن", 5, 1, 90000, "⚪"),
    ("ماسه", "تن", 30, 1, 45000, "🏖️"),
    ("شن", "تن", 15, 1, 50000, "🪨"),
    ("بلوک", "عدد", 3000, 1000, 25000, "🧱"),
    ("کاشی و سرامیک", "مترمربع", 100, 1, 25000, "◻️"),
    ("لوله‌کشی آب و فاضلاب", "متر", 250, 1, 6000, "🚰"),
    ("سیم و کابل برق", "متر", 800, 1, 4500, "⚡"),
    ("رنگ", "لیتر", 180, 1, 7000, "🎨"),
    ("عایق", "مترمربع", 100, 1, 8000, "🛡️"),
    ("چوب و درب", "مترمربع", 35, 1, 35000, "🚪"),
    ("شیشه و پنجره", "مترمربع", 30, 1, 50000, "🪟"),
]

# Decoration items. Prices are defaults only; every price is editable from Arsin panel.
DECORATION_ITEMS = [
    ("یخچال", 70000, "آشپزخانه"),
    ("ماکروفر", 25000, "آشپزخانه"),
    ("گاز رومیزی", 30000, "آشپزخانه"),
    ("چای‌ساز", 12000, "آشپزخانه"),
    ("آرام‌پز", 10000, "آشپزخانه"),
    ("قهوه‌ساز اسپرسو + وسایل", 65000, "آشپزخانه"),
    ("قهوه‌ساز کپسولی + وسایل", 45000, "آشپزخانه"),
    ("قهوه‌ساز فرنچ‌پرس + وسایل", 15000, "آشپزخانه"),
    ("آسیاب‌کن قهوه + وسایل", 22000, "آشپزخانه"),
    ("همزن برقی", 18000, "آشپزخانه"),
    ("ادویه‌جات کامل", 9000, "آشپزخانه"),
    ("لیوان و فنجان سرویس 100تایی", 30000, "آشپزخانه"),
    ("دکوری و مجسمه 5 عدد", 20000, "آشپزخانه"),
    ("سینک ظرفشویی مدرن", 50000, "آشپزخانه"),
    ("سرویس ظروف غذاخوری کامل", 40000, "آشپزخانه"),
    ("سینی چند عدد", 12000, "آشپزخانه"),
    ("سرویس چینی قدیمی و عتیقه", 100000, "آشپزخانه"),
    ("دستمال آشپزخانه", 5000, "آشپزخانه"),
    ("دستمال تمیزکاری", 4000, "آشپزخانه"),
    ("دستکش ظرفشویی", 3000, "آشپزخانه"),
    ("دستمال زیر قابلمه‌ای", 3000, "آشپزخانه"),
    ("سماور", 35000, "آشپزخانه"),
    ("ماشین ظرفشویی", 85000, "آشپزخانه"),
    ("ماشین لباسشویی", 80000, "آشپزخانه"),
    ("کابینت", 90000, "آشپزخانه"),
    ("هود", 35000, "آشپزخانه"),
    ("چاقو سرویس کامل", 18000, "آشپزخانه"),
    ("تلویزیون و میز", 90000, "پذیرایی"),
    ("مبل", 100000, "پذیرایی"),
    ("فرش", 80000, "پذیرایی"),
    ("دکور", 25000, "پذیرایی"),
    ("میز غذاخوری", 55000, "پذیرایی"),
    ("جاکفشی", 12000, "پذیرایی"),
    ("اتاق پرو", 45000, "اتاق"),
    ("تخت خواب", 60000, "اتاق"),
    ("میز تحریر", 30000, "اتاق"),
    ("میز آرایش", 35000, "اتاق"),
    ("کمد", 50000, "اتاق"),
    ("مخلوط‌کن", 18000, "آشپزخانه"),
    ("آبمیوه‌گیر", 20000, "آشپزخانه"),
    ("خردکن", 14000, "آشپزخانه"),
    ("لوازم آرایش", 40000, "اتاق"),
    ("میز عسلی", 15000, "پذیرایی"),
    ("صندلی", 10000, "پذیرایی"),
    ("میز مطالعه", 28000, "اتاق"),
    ("چراغ مطالعه", 8000, "اتاق"),
    ("کتابخانه", 45000, "پذیرایی"),
    ("گرامافون", 75000, "پذیرایی"),
    ("صفحه گرامافون", 12000, "پذیرایی"),
    ("لوازم موسیقی", 60000, "پذیرایی"),
]
SHOSHOL_COOLDOWN = 420  # 7 minutes
HACK_COOLDOWN = 420  # 7 minutes
LEVEL_UP_BASE_COST = 10000
UPGRADE_STAT_BASE_COST = 10000
LEVEL_AH_COUNT = 10
LEVEL_UP_REWARD = 1000
MAX_STAT_LEVEL = 10
COIN_PHRASE = "آریو"
ROLE_DM_SECONDS = 120
SPEAK_SECONDS = 100
CHALLENGE_SECONDS = 30
VOTE_SECONDS = 10
NIGHT_SECONDS = 120
DEFENSE_SECONDS = 100

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def send_bot_message(chat_id, text, **kwargs):
    msg = await bot.send_message(chat_id, text, **kwargs)
    game = games.get(chat_id)
    if game:
        game.setdefault("message_ids", set()).add(msg.message_id)
    return msg

# ================================================================
# ARIO PERSONALITY
# ================================================================
ARIO_SYSTEM_PROMPT = """
تو «آریو» هستی؛ ربات اصلی آرسین.
- خیلی وفادار و کمی حسود هستی.
- اگر کسی اسم «آرسین» را آورد، با لحن ربات آریو پاسخ بده.
- اگر آرسین (@arsin_mo) با تو حرف زد، با لحن صمیمی و محترمانه پاسخ بده.
- در بقیه موارد، دوستانه و شیک صحبت می‌کنی.
"""

# ================================================================
# ROLE DEFINITIONS
# 5 separate buttons exist for شهروند ساده and 5 separate buttons for مافیای ساده.
# رئیس مافیا + دکتر لکتر CAN BOTH be in the same game.
# ================================================================
ROLE_BUTTONS = [
    ("دکتر", "دکتر", 1),
    ("کاراگاه", "کاراگاه", 1),
    ("تک تیر انداز", "تک تیر انداز", 1),
    ("جان سخت", "جان سخت", 1),
    ("روان پزشک", "روان پزشک", 1),
    ("فروشنده", "فروشنده", 1),
    ("شهروند ساده", "شهروند", 1),
    ("شهروند ساده", "شهروند", 1),
    ("شهروند ساده", "شهروند", 1),
    ("شهروند ساده", "شهروند", 1),
    ("شهروند ساده", "شهروند", 1),
    ("رییس مافیا", "رییس مافیا", 1),
    ("دکتر لکتر", "دکتر لکتر", 1),
    ("مافیای ساده", "مافیا ساده", 1),
    ("مافیای ساده", "مافیا ساده", 1),
    ("مافیای ساده", "مافیا ساده", 1),
    ("مافیای ساده", "مافیا ساده", 1),
    ("مافیای ساده", "مافیا ساده", 1),
]
MAFIA_ROLES = {"رییس مافیا", "دکتر لکتر", "مافیا ساده"}

# ================================================================
# RUNTIME STATE
# ================================================================
games = {}
pending_link = {}
pending_admin = {}
LOTTERY_PENDING = {}
LOTTERY_LOOP_STARTED = False
football_name_pending = {}
transfer_pending = {}
market_pending = {}
wager_games = {}
wager_counter = 0
WAGER_WAIT_SECONDS = 60
combat_timeout_tokens = {}
combat_action_locks = {}
DB_HEAVY_OP_SEMAPHORE = asyncio.Semaphore(64)
# حافظه سریع وضعیت دوئل؛ دیتابیس همچنان برای ماندگاری استفاده می‌شود.
# این کش فقط وضعیت فعال مبارزه را نگه می‌دارد تا هر کلیک چندین بار SQLite را نخواند.
combat_states = {}

# ================================================================
# 🃏 7 KHABIS GAME
# ================================================================
SEVEN_GAMES = {}
SEVEN_LOCKS = {}
SEVEN_TASKS = {}
SEVEN_COUNTDOWN_TASKS = {}
SEVEN_WAIT_SECONDS = 300
SEVEN_TURN_SECONDS = 10
SEVEN_MIN_PLAYERS = 2
SEVEN_MAX_PLAYERS = 4

SEVEN_SUITS = ["♥️", "♦️", "♣️", "♠️"]
SEVEN_RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

# The requested dealing totals require 60 cards. We use a 52-card deck
# plus 8 wild Joker cards. Jokers have no special effect and may be played
# on any active card.
SEVEN_JOKER_COUNT = 0


# ================================================================
# DATABASE
# ================================================================
def db():
    # Fast short-lived SQLite connections. WAL is enabled once during init_db;
    # every connection gets a generous busy timeout so concurrent callbacks
    # wait for a short write instead of failing with "database is locked".
    c = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA busy_timeout=30000")
    c.execute("PRAGMA temp_store=MEMORY")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init_db():
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute(
            "CREATE TABLE IF NOT EXISTS users(" 
            "id INTEGER PRIMARY KEY, username TEXT, started INTEGER DEFAULT 1)"
        )
        c.execute("CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS coins(user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, last_ah INTEGER DEFAULT 0, ah_count INTEGER DEFAULT 0, level INTEGER DEFAULT 0, luck_level INTEGER DEFAULT 0, exp_level INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS shoshol_cooldowns(user_id INTEGER PRIMARY KEY, last_used INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS hack_cooldowns(user_id INTEGER PRIMARY KEY, last_used INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS bot_bans(user_id INTEGER PRIMARY KEY, wallet_balance INTEGER DEFAULT 0, bank_balance INTEGER DEFAULT 0, username TEXT DEFAULT '', full_name TEXT DEFAULT '', banned_at INTEGER DEFAULT 0, banned_by INTEGER DEFAULT 0, group_notice_sent INTEGER DEFAULT 0)")
        ban_cols = {row[1] for row in c.execute("PRAGMA table_info(bot_bans)").fetchall()}
        if "group_notice_sent" not in ban_cols:
            c.execute("ALTER TABLE bot_bans ADD COLUMN group_notice_sent INTEGER DEFAULT 0")
        c.execute("CREATE TABLE IF NOT EXISTS admin_users(user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', full_name TEXT DEFAULT '', added_at INTEGER DEFAULT 0, added_by INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS admin_permissions(user_id INTEGER NOT NULL, section TEXT NOT NULL, enabled INTEGER DEFAULT 1, PRIMARY KEY(user_id,section))")
        c.execute("CREATE TABLE IF NOT EXISTS known_chats(chat_id INTEGER PRIMARY KEY, chat_type TEXT NOT NULL, title TEXT DEFAULT '', username TEXT DEFAULT '', active INTEGER DEFAULT 1, updated_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS auto_replies(id INTEGER PRIMARY KEY AUTOINCREMENT, keyword TEXT UNIQUE NOT NULL, response TEXT NOT NULL, active INTEGER DEFAULT 1, created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS lotteries(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, chat_id INTEGER NOT NULL, message_id INTEGER DEFAULT 0, creator_id INTEGER NOT NULL, prize INTEGER NOT NULL, draw_at INTEGER NOT NULL, min_players INTEGER DEFAULT 0, max_players INTEGER DEFAULT 0, status TEXT DEFAULT 'active', created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS lottery_players(lottery_id INTEGER NOT NULL, user_id INTEGER NOT NULL, joined_at INTEGER DEFAULT 0, PRIMARY KEY(lottery_id,user_id))")
        c.execute("CREATE TABLE IF NOT EXISTS lottery_messages(lottery_id INTEGER NOT NULL, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, PRIMARY KEY(lottery_id,chat_id))")
        c.execute("CREATE TABLE IF NOT EXISTS scheduled_announcements(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, delete_at INTEGER NOT NULL)")
        user_cols = {row[1] for row in c.execute("PRAGMA table_info(users)").fetchall()}
        if "full_name" not in user_cols:
            c.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
        cols = {row[1] for row in c.execute("PRAGMA table_info(coins)").fetchall()}
        for name in ("ah_count", "level", "luck_level", "exp_level"):
            if name not in cols:
                c.execute(f"ALTER TABLE coins ADD COLUMN {name} INTEGER DEFAULT 0")
        c.execute("CREATE TABLE IF NOT EXISTS gift_codes(code TEXT PRIMARY KEY, amount INTEGER NOT NULL, active INTEGER DEFAULT 1, created_at INTEGER DEFAULT 0, mode TEXT DEFAULT 'multi', max_uses INTEGER DEFAULT 0)")
        gift_cols = {row[1] for row in c.execute("PRAGMA table_info(gift_codes)").fetchall()}
        if "mode" not in gift_cols:
            c.execute("ALTER TABLE gift_codes ADD COLUMN mode TEXT DEFAULT 'multi'")
        if "max_uses" not in gift_cols:
            c.execute("ALTER TABLE gift_codes ADD COLUMN max_uses INTEGER DEFAULT 0")
        c.execute("CREATE TABLE IF NOT EXISTS gift_redemptions(code TEXT NOT NULL, user_id INTEGER NOT NULL, redeemed_at INTEGER NOT NULL, PRIMARY KEY(code,user_id))")
        c.execute("CREATE TABLE IF NOT EXISTS daily_state(user_id INTEGER PRIMARY KEY, last_box INTEGER DEFAULT 0, streak INTEGER DEFAULT 0, last_streak_day TEXT DEFAULT '')")
        c.execute("CREATE TABLE IF NOT EXISTS missions(user_id INTEGER NOT NULL, day TEXT NOT NULL, mtype TEXT NOT NULL, target INTEGER NOT NULL, progress INTEGER DEFAULT 0, reward INTEGER NOT NULL, claimed INTEGER DEFAULT 0, PRIMARY KEY(user_id,day,mtype))")
        c.execute("CREATE TABLE IF NOT EXISTS bank(user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS bank_hack_blocks(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, unlock_at INTEGER NOT NULL, created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS market(listing_id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL, amount INTEGER NOT NULL, price INTEGER NOT NULL, active INTEGER DEFAULT 1, created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS wager_games(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL DEFAULT 0, game_type TEXT NOT NULL, creator_id INTEGER NOT NULL, stake INTEGER NOT NULL, opponent_id INTEGER DEFAULT 0, status TEXT NOT NULL, created_at INTEGER DEFAULT 0, expires_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS player_stats(user_id INTEGER PRIMARY KEY, games INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, draws INTEGER DEFAULT 0, points INTEGER DEFAULT 0, xp INTEGER DEFAULT 0, best_win INTEGER DEFAULT 0, win_streak INTEGER DEFAULT 0, best_streak INTEGER DEFAULT 0, updated_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS achievements(user_id INTEGER NOT NULL, code TEXT NOT NULL, unlocked_at INTEGER DEFAULT 0, PRIMARY KEY(user_id,code))")
        c.execute("CREATE TABLE IF NOT EXISTS inventory(user_id INTEGER NOT NULL, item TEXT NOT NULL, quantity INTEGER DEFAULT 0, PRIMARY KEY(user_id,item))")
        c.execute("CREATE TABLE IF NOT EXISTS item_market(listing_id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL, item TEXT NOT NULL, quantity INTEGER NOT NULL, price INTEGER NOT NULL, active INTEGER DEFAULT 1, created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS tournaments(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER DEFAULT 0, creator_id INTEGER NOT NULL, stake INTEGER NOT NULL, prize INTEGER DEFAULT 0, status TEXT NOT NULL, created_at INTEGER DEFAULT 0, expires_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS tournament_players(tournament_id INTEGER NOT NULL, user_id INTEGER NOT NULL, joined_at INTEGER DEFAULT 0, active INTEGER DEFAULT 1, PRIMARY KEY(tournament_id,user_id))")
        tp_cols={row[1] for row in c.execute("PRAGMA table_info(tournament_players)").fetchall()}
        if "active" not in tp_cols:
            c.execute("ALTER TABLE tournament_players ADD COLUMN active INTEGER DEFAULT 1")
        c.execute("CREATE TABLE IF NOT EXISTS tournament_rounds(tournament_id INTEGER NOT NULL, round_no INTEGER NOT NULL, player_a INTEGER NOT NULL, player_b INTEGER NOT NULL, winner_id INTEGER DEFAULT 0, PRIMARY KEY(tournament_id,round_no,player_a,player_b))")
        c.execute("CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL, amount INTEGER NOT NULL, balance_after INTEGER NOT NULL, note TEXT DEFAULT '', created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS combat_battles(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER DEFAULT 0, creator_id INTEGER NOT NULL, opponent_id INTEGER DEFAULT 0, stake INTEGER NOT NULL, status TEXT NOT NULL, creator_power INTEGER DEFAULT 0, opponent_power INTEGER DEFAULT 0, winner_id INTEGER DEFAULT 0, created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS champions(user_id INTEGER PRIMARY KEY, titles INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, best_power INTEGER DEFAULT 0, updated_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS combat_duels(id INTEGER PRIMARY KEY AUTOINCREMENT, battle_id INTEGER UNIQUE NOT NULL, turn_user INTEGER NOT NULL, hp_a INTEGER DEFAULT 100, hp_b INTEGER DEFAULT 100, defending_user INTEGER DEFAULT 0, special_a INTEGER DEFAULT 1, special_b INTEGER DEFAULT 1, turn_no INTEGER DEFAULT 1, updated_at INTEGER DEFAULT 0)")
        duel_cols={row[1] for row in c.execute("PRAGMA table_info(combat_duels)").fetchall()}
        if "potion_state" not in duel_cols:
            c.execute("ALTER TABLE combat_duels ADD COLUMN potion_state TEXT DEFAULT ''")
        c.execute("CREATE TABLE IF NOT EXISTS item_auctions(auction_id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id INTEGER NOT NULL, item TEXT NOT NULL, quantity INTEGER NOT NULL, start_price INTEGER NOT NULL, current_bid INTEGER DEFAULT 0, current_bidder INTEGER DEFAULT 0, min_increment INTEGER NOT NULL, status TEXT NOT NULL, created_at INTEGER DEFAULT 0, end_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS user_pets(user_id INTEGER PRIMARY KEY, active_pet TEXT DEFAULT '')")
        c.execute("CREATE TABLE IF NOT EXISTS aunt_game_stats(user_id INTEGER PRIMARY KEY, aunt_id INTEGER DEFAULT 0, games_count INTEGER DEFAULT 0, updated_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS properties(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, region_id INTEGER NOT NULL, region_name TEXT NOT NULL, area INTEGER NOT NULL, land_price INTEGER NOT NULL, status TEXT DEFAULT 'land', purchased_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS mall_stores(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, area INTEGER NOT NULL, purchase_price INTEGER NOT NULL, purchased_at INTEGER DEFAULT 0, last_income_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS business_items(store_id INTEGER NOT NULL, item TEXT NOT NULL, quantity INTEGER DEFAULT 0, total_spent INTEGER DEFAULT 0, PRIMARY KEY(store_id,item))")
        c.execute("CREATE TABLE IF NOT EXISTS property_materials(property_id INTEGER NOT NULL, material TEXT NOT NULL, purchased INTEGER DEFAULT 0, purchased_at INTEGER DEFAULT 0, PRIMARY KEY(property_id,material))")
        c.execute("CREATE TABLE IF NOT EXISTS property_decor(property_id INTEGER NOT NULL, item TEXT NOT NULL, quantity INTEGER DEFAULT 0, purchased_at INTEGER DEFAULT 0, PRIMARY KEY(property_id,item))")
        c.execute("CREATE TABLE IF NOT EXISTS football_teams(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE NOT NULL, club_name TEXT NOT NULL, club_name_norm TEXT UNIQUE NOT NULL, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, draws INTEGER DEFAULT 0, games INTEGER DEFAULT 0, experience INTEGER DEFAULT 0, last_game_at INTEGER DEFAULT 0, created_at INTEGER DEFAULT 0, last_income_at INTEGER DEFAULT 0)")
        football_team_cols = {row[1] for row in c.execute("PRAGMA table_info(football_teams)").fetchall()}
        if "last_income_at" not in football_team_cols:
            c.execute("ALTER TABLE football_teams ADD COLUMN last_income_at INTEGER DEFAULT 0")
        c.execute("CREATE TABLE IF NOT EXISTS leaderboard_reward_runs(period_type TEXT NOT NULL, period_key TEXT NOT NULL, board TEXT NOT NULL, paid_at INTEGER DEFAULT 0, PRIMARY KEY(period_type,period_key,board))")
        c.execute("CREATE TABLE IF NOT EXISTS football_coaches(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, power INTEGER NOT NULL, monthly_price INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS football_players(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, position TEXT NOT NULL, power INTEGER NOT NULL, monthly_price INTEGER NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS football_team_coaches(team_id INTEGER PRIMARY KEY, coach_id INTEGER NOT NULL, contract_days INTEGER NOT NULL, contract_started_at INTEGER DEFAULT 0, contract_notice_sent INTEGER DEFAULT 0, contract_paid INTEGER NOT NULL DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS football_team_players(id INTEGER PRIMARY KEY AUTOINCREMENT, team_id INTEGER NOT NULL, player_id INTEGER NOT NULL, position TEXT NOT NULL, power INTEGER NOT NULL, monthly_price INTEGER NOT NULL, contract_days INTEGER NOT NULL, contract_started_at INTEGER DEFAULT 0, games_played INTEGER DEFAULT 0, in_lineup INTEGER DEFAULT 0, contract_notice_sent INTEGER DEFAULT 0, contract_paid INTEGER NOT NULL DEFAULT 0)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_football_team_player_unique ON football_team_players(team_id,player_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_football_team_players_team_pos ON football_team_players(team_id,position,in_lineup)")
        c.execute("CREATE TABLE IF NOT EXISTS football_matches(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER DEFAULT 0, creator_team_id INTEGER NOT NULL, opponent_team_id INTEGER NOT NULL, creator_user_id INTEGER NOT NULL, opponent_user_id INTEGER NOT NULL, stake INTEGER NOT NULL, status TEXT NOT NULL, winner_user_id INTEGER DEFAULT 0, created_at INTEGER DEFAULT 0, accepted_at INTEGER DEFAULT 0, finished_at INTEGER DEFAULT 0)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_football_matches_status ON football_matches(status,created_at)")
        football_seed_data(c)
        c.execute("CREATE INDEX IF NOT EXISTS idx_inventory_user_qty ON inventory(user_id,quantity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_bank_blocks_user_unlock ON bank_hack_blocks(user_id,unlock_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_business_items_store_qty ON business_items(store_id,quantity)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_mall_stores_user ON mall_stores(user_id,id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_time ON transactions(user_id,created_at)")
        aunt_cols = {row[1] for row in c.execute("PRAGMA table_info(aunt_game_stats)").fetchall()}
        if "last_game_at" not in aunt_cols:
            c.execute("ALTER TABLE aunt_game_stats ADD COLUMN last_game_at INTEGER DEFAULT 0")
        # V17 one-time migration: clear all existing aunt relationships so the new
        # mutual/one-to-one system starts clean. Game counters are preserved.
        reset_marker = c.execute("SELECT v FROM settings WHERE k='aunt_relationship_reset_v17'").fetchone()
        if not reset_marker:
            c.execute("UPDATE aunt_game_stats SET aunt_id=0,updated_at=?", (int(time.time()),))
            c.execute("INSERT INTO settings(k,v) VALUES('aunt_relationship_reset_v17','1')")
        c.execute("CREATE TABLE IF NOT EXISTS seven_games(id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, message_id INTEGER DEFAULT 0, creator_id INTEGER NOT NULL, stake INTEGER NOT NULL, max_players INTEGER NOT NULL, status TEXT NOT NULL, state_json TEXT DEFAULT '', created_at INTEGER DEFAULT 0, expires_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS seven_players(game_id INTEGER NOT NULL, user_id INTEGER NOT NULL, joined_at INTEGER DEFAULT 0, paid INTEGER DEFAULT 1, PRIMARY KEY(game_id,user_id))")
        c.commit()


def remember(user):
    with db() as c:
        c.execute(
            "INSERT INTO users(id,username,full_name,started) VALUES(?,?,?,1) "
            "ON CONFLICT(id) DO UPDATE SET username=excluded.username,full_name=excluded.full_name,started=1",
            (user.id, user.username or "", user.full_name or ""),
        )
        if user.username and user.username.lower() == ARSIN_USERNAME.lower():
            c.execute(
                "INSERT INTO settings(k,v) VALUES('arsin_user_id',?) "
                "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                (str(user.id),),
            )
        c.commit()


def get_setting(key):
    with db() as c:
        row = c.execute("SELECT v FROM settings WHERE k=?", (key,)).fetchone()
        return row[0] if row else None


def set_setting(key, value):
    with db() as c:
        c.execute(
            "INSERT INTO settings(k,v) VALUES(?,?) "
            "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (key, value),
        )
        c.commit()


def format_coins(amount):
    return f"{int(amount):,}"


def get_link_chat_id(slot):
    value = get_setting("link" + slot + "_chat_id")
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value

def configured_link_slots():
    """Return all configured membership-link slots in numeric order.

    link1/link2 are kept for backward compatibility; additional links are
    stored as link3, link4, ... without a fixed upper limit.
    """
    with db() as c:
        rows = c.execute("SELECT k FROM settings WHERE k LIKE 'link%' AND k NOT LIKE '%_chat_id'").fetchall()
    slots = []
    for (key,) in rows:
        m = re.fullmatch(r"link(\d+)", str(key))
        if not m:
            continue
        value = get_setting(key)
        if value:
            slots.append(int(m.group(1)))
    return sorted(set(slots))

def next_link_slot():
    slots = configured_link_slots()
    return (max(slots) + 1) if slots else 1

def link_display_url(link):
    if not link:
        return None
    return link if link.startswith(("http://", "https://")) else "https://t.me/" + link.lstrip("@")


# ================================================================
# COINS / GIFT CODES
# ================================================================
def get_coin_row(user_id):
    with db() as c:
        row=c.execute("SELECT balance,last_ah,ah_count,level,luck_level,exp_level FROM coins WHERE user_id=?",(user_id,)).fetchone()
    if not row:
        return {"balance":0,"last_ah":0,"ah_count":0,"level":0,"luck_level":0,"exp_level":0}
    return {"balance":int(row[0] or 0),"last_ah":int(row[1] or 0),"ah_count":int(row[2] or 0),"level":int(row[3] or 0),"luck_level":int(row[4] or 0),"exp_level":int(row[5] or 0)}

def get_balance(user_id): return get_coin_row(user_id)["balance"]

def add_coins(user_id,amount):
    with db() as c:
        c.execute("INSERT INTO coins(user_id,balance,last_ah,ah_count,level,luck_level,exp_level) VALUES(?,?,0,0,0,0,0) ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance",(user_id,int(amount)))
        c.commit()
    return get_balance(user_id)

def coin_cooldown(user_id): return get_coin_row(user_id)["last_ah"]

def set_coin_time(user_id,ts):
    with db() as c:
        c.execute("INSERT INTO coins(user_id,balance,last_ah,ah_count,level,luck_level,exp_level) VALUES(?,?,?,0,0,0,0) ON CONFLICT(user_id) DO UPDATE SET last_ah=excluded.last_ah",(user_id,0,int(ts)))
        c.commit()

def process_ah(user_id):
    r=get_coin_row(user_id); count=r["ah_count"]+1; level=r["level"]
    leveled=False; level_reward=0
    if count % LEVEL_AH_COUNT == 0:
        level+=1; leveled=True; level_reward=LEVEL_UP_REWARD
    reward=COIN_BASE_REWARD+level*100
    with db() as c:
        c.execute("INSERT INTO coins(user_id,balance,last_ah,ah_count,level,luck_level,exp_level) VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance,last_ah=excluded.last_ah,ah_count=excluded.ah_count,level=excluded.level",(user_id,reward+level_reward,int(time.time()),count,level,r["luck_level"],r["exp_level"]))
        c.commit()
    log_tx(user_id,"ah",reward+level_reward,"آریو")
    bump_mission(user_id,"ah")
    return {**get_coin_row(user_id),"reward":reward,"level_reward":level_reward,"leveled_up":leveled}

def get_price(key, default):
    value = get_setting("price:" + str(key))
    try:
        return max(0, int(value)) if value is not None else int(default)
    except (TypeError, ValueError):
        return int(default)


def set_price(key, value):
    set_setting("price:" + str(key), str(max(0, int(value))))


def price_key_for(category, name):
    return f"{category}:{name}"


def upgrade_level(user_id):
    r=get_coin_row(user_id); cost=get_price("upgrade:level", LEVEL_UP_BASE_COST)
    if r["balance"]<cost: return False,r,cost
    with db() as c:
        c.execute("UPDATE coins SET balance=balance-?,level=level+1 WHERE user_id=?",(cost,user_id)); c.commit()
    return True,get_coin_row(user_id),cost

def upgrade_stat(user_id,stat):
    r=get_coin_row(user_id); cur=r[stat]
    if cur>=MAX_STAT_LEVEL: return False,r,0,"max"
    stat_key = "luck" if stat == "luck_level" else "exp"
    cost=(cur+1)*get_price("upgrade:"+stat_key, UPGRADE_STAT_BASE_COST)
    if r["balance"]<cost: return False,r,cost,"funds"
    with db() as c:
        c.execute(f"UPDATE coins SET balance=balance-?,{stat}={stat}+1 WHERE user_id=?",(cost,user_id)); c.commit()
    return True,get_coin_row(user_id),cost,"ok"

TRADE_BASE_CHANCE = 20
TRADE_LUCK_MAX_BONUS = 10
TRADE_EXP_MAX_BONUS = 10
TRADE_FOX_BONUS = 5
TRADE_POTION_BONUS = 5
TRADE_MIN_NET_DIVISOR = 3
TRADE_POTION_ITEM = "🧪 معجون افزایش شانس ترید"
TRADE_POTION_DEFAULT_PRICE = 250000

def trade_chance(user_id, include_potion=True):
    r=get_coin_row(user_id)
    luck_bonus=min(TRADE_LUCK_MAX_BONUS,int(r["luck_level"]))
    exp_bonus=min(TRADE_EXP_MAX_BONUS,int(r["exp_level"]))
    fox_bonus=TRADE_FOX_BONUS if active_pet(user_id)=="🦊 روباه" else 0
    potion_bonus=TRADE_POTION_BONUS if include_potion and inventory_qty(user_id,TRADE_POTION_ITEM)>0 else 0
    return min(50, TRADE_BASE_CHANCE+luck_bonus+exp_bonus+fox_bonus+potion_bonus)

def do_trade(user_id,amount):
    r=get_coin_row(user_id)
    if amount < 2: return None,r,"minimum"
    if r["balance"]<amount: return None,r,"funds"
    # One trade potion is automatically consumed on a trade when available.
    potion_available=inventory_qty(user_id,TRADE_POTION_ITEM)>0
    win=min(50,int(trade_chance(user_id, include_potion=potion_available)))
    min_net=max(1,(amount + TRADE_MIN_NET_DIVISOR - 1)//TRADE_MIN_NET_DIVISOR)
    max_net=amount-1
    if min_net>max_net:
        return None,r,"minimum"
    if potion_available:
        remove_item(user_id,TRADE_POTION_ITEM,1)
    if random.random()<win/100:
        net=random.randint(min_net,max_net)
    else:
        net=-random.randint(min_net,max_net)
    payout=amount+net
    with db() as c:
        c.execute("UPDATE coins SET balance=balance-?+? WHERE user_id=?",(amount,payout,user_id)); c.commit()
    if potion_available:
        log_tx(user_id,"trade_potion_use",0,TRADE_POTION_ITEM)
    return net,get_coin_row(user_id),"ok"

# ================================================================
# ARIOOR EXTENDED ECONOMY
# ================================================================

def log_tx(user_id, kind, amount, note=""):
    with db() as c:
        bal = c.execute("SELECT balance FROM coins WHERE user_id=?", (user_id,)).fetchone()
        balance = int(bal[0]) if bal else 0
        c.execute("INSERT INTO transactions(user_id,kind,amount,balance_after,note,created_at) VALUES(?,?,?,?,?,?)",
                  (user_id, kind, int(amount), balance, note, int(time.time())))
        c.commit()


def today_key():
    return time.strftime("%Y-%m-%d", time.localtime())


def yesterday_key():
    return time.strftime("%Y-%m-%d", time.localtime(time.time()-86400))


def get_daily_state(user_id):
    with db() as c:
        row=c.execute("SELECT last_box,streak,last_streak_day FROM daily_state WHERE user_id=?",(user_id,)).fetchone()
    if not row:
        return {"last_box":0,"streak":0,"last_streak_day":""}
    return {"last_box":int(row[0] or 0),"streak":int(row[1] or 0),"last_streak_day":row[2] or ""}


def claim_daily_box(user_id):
    st=get_daily_state(user_id); now_ts=int(time.time()); remain=86400-(now_ts-st["last_box"])
    if st["last_box"] and remain>0:
        return False, st, remain, 0
    today=today_key()
    if st["last_streak_day"]==yesterday_key(): streak=st["streak"]+1
    elif st["last_streak_day"]==today: streak=max(1,st["streak"])
    else: streak=1
    reward=min(5000,500+max(0,streak-1)*250)
    add_coins(user_id,reward)
    with db() as c:
        c.execute("INSERT INTO daily_state(user_id,last_box,streak,last_streak_day) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET last_box=excluded.last_box,streak=excluded.streak,last_streak_day=excluded.last_streak_day",(user_id,now_ts,streak,today))
        c.commit()
    log_tx(user_id,"daily_box",reward,f"streak={streak}")
    return True,{"last_box":now_ts,"streak":streak,"last_streak_day":today},0,reward


def ensure_missions(user_id):
    day=today_key()
    mission_defs=[("ah",3,600),("trade",2,900),("transfer",1,700)]
    with db() as c:
        for typ,target,reward in mission_defs:
            c.execute("INSERT OR IGNORE INTO missions(user_id,day,mtype,target,progress,reward,claimed) VALUES(?,?,?,?,0,?,0)",(user_id,day,typ,target,reward))
        c.commit()


def mission_rows(user_id):
    ensure_missions(user_id)
    with db() as c:
        return c.execute("SELECT mtype,target,progress,reward,claimed FROM missions WHERE user_id=? AND day=? ORDER BY mtype",(user_id,today_key())).fetchall()


def mission_label(typ):
    return {"ah":"⛏️ ۳ بار آریو استخراج کن","trade":"۲ ترید انجام بده","transfer":"۱ انتقال آریور انجام بده"}.get(typ,typ)


def bump_mission(user_id, typ, amount=1):
    ensure_missions(user_id)
    with db() as c:
        c.execute("UPDATE missions SET progress=MIN(target,progress+?) WHERE user_id=? AND day=? AND mtype=? AND claimed=0",(amount,user_id,today_key(),typ))
        c.commit()


def claim_mission(user_id, typ):
    ensure_missions(user_id)
    with db() as c:
        row=c.execute("SELECT target,progress,reward,claimed FROM missions WHERE user_id=? AND day=? AND mtype=?",(user_id,today_key(),typ)).fetchone()
        if not row: return False,"missing",0
        target,progress,reward,claimed=map(int,row)
        if claimed: return False,"claimed",reward
        if progress<target: return False,"incomplete",reward
        c.execute("UPDATE missions SET claimed=1 WHERE user_id=? AND day=? AND mtype=?",(user_id,today_key(),typ)); c.commit()
    add_coins(user_id,reward); log_tx(user_id,"mission",reward,typ)
    return True,"ok",reward


def release_due_bank_hacks(user_id=None):
    now=int(time.time())
    with db() as c:
        if user_id is None:
            rows=c.execute("SELECT id,user_id,amount FROM bank_hack_blocks WHERE unlock_at<=?",(now,)).fetchall()
        else:
            rows=c.execute("SELECT id,user_id,amount FROM bank_hack_blocks WHERE user_id=? AND unlock_at<=?",(user_id,now)).fetchall()
        for block_id,uid,amount in rows:
            penalty=int(amount)//10
            returned=max(0,int(amount)-penalty)
            if returned:
                c.execute("INSERT INTO bank(user_id,balance) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance",(uid,returned))
            c.execute("DELETE FROM bank_hack_blocks WHERE id=?",(block_id,))
            c.execute("INSERT INTO transactions(user_id,kind,amount,balance_after,note,created_at) VALUES(?,?,?,?,?,?)",(uid,"hack_block_release",returned,0,f"blocked={amount};penalty={penalty}",now))
        c.commit()

def bank_raw_balance(user_id):
    with db() as c:
        row=c.execute("SELECT balance FROM bank WHERE user_id=?",(user_id,)).fetchone()
    return int(row[0]) if row else 0

def bank_blocked_amount(user_id):
    release_due_bank_hacks(user_id)
    now=int(time.time())
    with db() as c:
        row=c.execute("SELECT COALESCE(SUM(amount),0) FROM bank_hack_blocks WHERE user_id=? AND unlock_at>?",(user_id,now)).fetchone()
    return int(row[0] or 0)

def bank_balance(user_id):
    release_due_bank_hacks(user_id)
    raw=bank_raw_balance(user_id)
    blocked=bank_blocked_amount(user_id)
    return max(0,raw-blocked)

def bank_deposit(user_id,amount):
    if amount<=0 or get_balance(user_id)<amount: return False,bank_balance(user_id)
    add_coins(user_id,-amount)
    with db() as c:
        c.execute("INSERT INTO bank(user_id,balance) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance",(user_id,amount)); c.commit()
    log_tx(user_id,"bank_deposit",-amount,f"deposit={amount}")
    return True,bank_balance(user_id)

def bank_withdraw(user_id,amount):
    available=bank_balance(user_id)
    if amount<=0 or available<amount: return False,available
    with db() as c:
        c.execute("UPDATE bank SET balance=balance-? WHERE user_id=?",(amount,user_id)); c.commit()
    add_coins(user_id,amount); log_tx(user_id,"bank_withdraw",amount,f"withdraw={amount}")
    return True,bank_balance(user_id)

def total_wealth(user_id):
    release_due_bank_hacks(user_id)
    return get_balance(user_id) + bank_raw_balance(user_id)


def is_banned(user_id):
    with db() as c:
        return c.execute("SELECT 1 FROM bot_bans WHERE user_id=?", (user_id,)).fetchone() is not None


def banned_rows():
    with db() as c:
        return c.execute("SELECT user_id,username,full_name,wallet_balance,bank_balance,banned_at FROM bot_bans ORDER BY banned_at DESC").fetchall()


def consume_group_ban_notice(user_id):
    with db() as c:
        row = c.execute("SELECT group_notice_sent FROM bot_bans WHERE user_id=?", (int(user_id),)).fetchone()
        if not row or int(row[0] or 0):
            return False
        c.execute("UPDATE bot_bans SET group_notice_sent=1 WHERE user_id=?", (int(user_id),))
        c.commit()
        return True


def ban_user(user_id, banned_by=0):
    if is_banned(user_id):
        return False, None
    release_due_bank_hacks(user_id)
    wallet=get_balance(user_id)
    bank=bank_raw_balance(user_id)
    row=get_user_record(user_id)
    username=row[1] if row else ""
    full_name=row[2] if row else ""
    with db() as c:
        c.execute("INSERT INTO bot_bans(user_id,wallet_balance,bank_balance,username,full_name,banned_at,banned_by,group_notice_sent) VALUES(?,?,?,?,?,?,?,0)",(user_id,wallet,bank,username or "",full_name or "",int(time.time()),int(banned_by or 0)))
        c.execute("UPDATE coins SET balance=0 WHERE user_id=?",(user_id,))
        c.execute("UPDATE bank SET balance=0 WHERE user_id=?",(user_id,))
        c.execute("DELETE FROM bank_hack_blocks WHERE user_id=?",(user_id,))
        c.commit()
    return True, wallet+bank


def unban_user(user_id):
    with db() as c:
        row=c.execute("SELECT wallet_balance,bank_balance FROM bot_bans WHERE user_id=?",(user_id,)).fetchone()
        if not row:
            return False,0
        wallet,bank=map(int,row)
        c.execute("INSERT INTO coins(user_id,balance,last_ah,ah_count,level,luck_level,exp_level) VALUES(?,?,0,0,0,0,0) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance",(user_id,wallet))
        c.execute("INSERT INTO bank(user_id,balance) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET balance=excluded.balance",(user_id,bank))
        c.execute("DELETE FROM bot_bans WHERE user_id=?",(user_id,))
        c.commit()
    return True,wallet+bank


def forwarded_user_id(message):
    """Return the sender user ID when this message was forwarded from a user."""
    origin=getattr(message, "forward_origin", None)
    sender=getattr(origin, "sender_user", None) if origin is not None else None
    if sender is not None and getattr(sender, "id", None):
        try:
            remember(sender)
        except Exception:
            pass
        return int(sender.id)
    # Compatibility with older aiogram/Telegram fields.
    legacy=getattr(message, "forward_from", None)
    if legacy is not None and getattr(legacy, "id", None):
        try:
            remember(legacy)
        except Exception:
            pass
        return int(legacy.id)
    return None


def resolve_user_id(value):
    value=(value or "").strip()
    if value.isdigit():
        uid=int(value)
        with db() as c:
            row=c.execute("SELECT id FROM users WHERE id=?",(uid,)).fetchone()
        return uid if row else None
    username=value[1:] if value.startswith("@") else value
    if not username:
        return None
    with db() as c:
        row=c.execute("SELECT id FROM users WHERE lower(username)=?",(username.lower(),)).fetchone()
    return int(row[0]) if row else None


def change_total_balance(user_id, delta):
    release_due_bank_hacks(user_id)
    delta=int(delta)
    wallet=get_balance(user_id)
    bank=bank_balance(user_id)
    total=wallet+bank
    if delta<0 and total < abs(delta):
        return False,total,wallet,bank
    if delta>=0:
        add_coins(user_id,delta)
    else:
        take=-delta
        from_wallet=min(wallet,take)
        if from_wallet:
            add_coins(user_id,-from_wallet)
            take-=from_wallet
        if take:
            with db() as c:
                c.execute("UPDATE bank SET balance=MAX(0,balance-?) WHERE user_id=?",(take,user_id)); c.commit()
    return True,total+delta,get_balance(user_id),bank_balance(user_id)


def remember_chat(chat):
    if not chat or getattr(chat,"type",None) not in ("group","supergroup","channel"):
        return
    title=getattr(chat,"title",None) or ""
    username=getattr(chat,"username",None) or ""
    with db() as c:
        c.execute("INSERT INTO known_chats(chat_id,chat_type,title,username,active,updated_at) VALUES(?,?,?,?,1,?) ON CONFLICT(chat_id) DO UPDATE SET chat_type=excluded.chat_type,title=excluded.title,username=excluded.username,active=1,updated_at=excluded.updated_at",(chat.id,chat.type,title,username,int(time.time())))
        c.commit()


def leaderboard_wealth(limit=5):
    with db() as c:
        return c.execute("SELECT u.id,u.username,u.full_name,COALESCE(c.balance,0)+COALESCE(b.balance,0) AS wealth FROM users u LEFT JOIN coins c ON c.user_id=u.id LEFT JOIN bank b ON b.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) AND lower(COALESCE(u.username,'')) != lower(?) ORDER BY wealth DESC,u.id ASC LIMIT ?",(ARSIN_USERNAME,limit)).fetchall()


def leaderboard(limit=10):
    with db() as c:
        return c.execute("SELECT u.id,u.username,c.balance,c.level,c.luck_level,c.exp_level FROM users u JOIN coins c ON c.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) AND lower(COALESCE(u.username,'')) != lower(?) ORDER BY c.balance DESC LIMIT ?",(ARSIN_USERNAME,limit)).fetchall()


def recent_transactions(user_id,limit=10):
    with db() as c:
        return c.execute("SELECT kind,amount,balance_after,note,created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT ?",(user_id,limit)).fetchall()


def create_market_listing(seller_id,amount,price):
    if amount<=0 or price<=0 or get_balance(seller_id)<amount: return False
    add_coins(seller_id,-amount)
    with db() as c:
        c.execute("INSERT INTO market(seller_id,amount,price,active,created_at) VALUES(?,?,?,1,?)",(seller_id,amount,price,int(time.time()))); c.commit()
    log_tx(seller_id,"market_lock",-amount,f"listing price={price}")
    return True


def active_market(limit=10):
    with db() as c:
        return c.execute("SELECT listing_id,seller_id,amount,price,created_at FROM market WHERE active=1 ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()


def buy_market_listing(buyer_id,listing_id):
    with db() as c:
        row=c.execute("SELECT seller_id,amount,price,active FROM market WHERE listing_id=?",(listing_id,)).fetchone()
        if not row: return False,"missing",0,0
        seller,amount,price,active=row
        if not active: return False,"inactive",0,0
        if seller==buyer_id: return False,"self",0,0
        if get_balance(buyer_id)<price: return False,"funds",price,amount
        c.execute("UPDATE market SET active=0 WHERE listing_id=? AND active=1",(listing_id,)); c.commit()
    add_coins(buyer_id,amount); add_coins(seller,price)
    log_tx(buyer_id,"market_buy",amount,f"paid={price}")
    log_tx(seller,"market_sell",price,f"sold={amount}")
    return True,"ok",price,amount


# ================================================================
# STAGES 1-5: GAME PROGRESSION / STATS / RANKS / ITEMS / TOURNAMENTS
# ================================================================
ACHIEVEMENT_DEFS = {
    "first_game": ("🎮 اولین بازی", "اولین بازی شرطی خودت را تمام کن", 1),
    "first_win": ("🏆 اولین برد", "اولین بردت را ثبت کن", 1),
    "wins_10": ("🔥 ۱۰ برد", "۱۰ بازی را ببر", 10),
    "wins_50": ("💎 ۵۰ برد", "۵۰ بازی را ببر", 50),
    "games_100": ("🎮 ۱۰۰ بازی", "۱۰۰ بازی را کامل کن", 100),
    "streak_5": ("🔥 استریک ۵", "۵ برد پیاپی بگیر", 5),
    "streak_10": ("👑 استریک ۱۰", "۱۰ برد پیاپی بگیر", 10),
    "rich_100k": ("💰 ثروتمند", "موجودی کیف پول به ۱۰۰,۰۰۰ برسد", 100000),
}

RANKS = [
    (0, "🥉 برنز"),
    (100, "🥈 نقره"),
    (300, "🥇 طلا"),
    (700, "💎 الماس"),
    (1500, "👑 مستر"),
]

SHOP_ITEMS_V2 = {
    "🛡️ سپر انرژی": (2500, "تجهیز دفاعی؛ +8 قدرت مبارزه"),
    "🛡️ نگهبان": (1000000, "محافظ شوشول بری؛ 10٪ از شانس نهایی شوشول بری مهاجم کم می‌کند"),
    "🛡️ نگهبان بانک": (1000000, "محافظ بانک؛ 10٪ از شانس نهایی هک مهاجم کم می‌کند"),
    "🍀 شانس ویژه": (3000, "یک بار +10٪ شانس مبارزه و سپس مصرف می‌شود"),
    "🎟️ بلیت بازی": (1500, "یک آیتم قابل معامله برای اقتصاد بازی"),
    "⚡ Boost XP": (4000, "۵۰۰ XP فوری"),
    "🔫 بلستر پلاسما": (4500, "تجهیز هجومی؛ +10 قدرت مبارزه"),
    "💣 بمب انرژی": (5500, "تجهیز هجومی؛ +12 قدرت مبارزه"),
    "⚔️ شمشیر انرژی": (6000, "تجهیز هجومی؛ +13 قدرت مبارزه"),
    "🦾 زره نانو": (7000, "تجهیز دفاعی؛ +14 قدرت مبارزه"),
    "🐺 گرگ نگهبان": (9000, "همراه مبارز؛ +16 قدرت مبارزه"),
    "🦅 پهپاد همراه": (11000, "همراه هوشمند؛ +18 قدرت مبارزه"),
    "🤖 ربات مبارز": (18000, "همراه ویژه؛ +28 قدرت مبارزه"),
    "🕸️ قهرمان تارزن": (20000, "شخصیت قهرمانی خیالی؛ +30 قدرت مبارزه"),
    "🧙 جادوگر سایه": (25000, "شخصیت قهرمانی خیالی؛ +35 قدرت مبارزه"),
    "🎮 کنسول PS4": (100000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "🎮 کنسول PS5": (200000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "🎮 کنسول Xbox Series S": (90000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "🎮 کنسول Xbox Series X": (225000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "🖥️ مانیتور 24 اینچ سونی": (50000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "🛋️ مبل تک نفره": (15000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "🪛 پایه دیواری مانیتور 24 سونی": (5000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "🖥️ کامپیوتر PC نسل 9 گیمینگ": (300000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
    "⌨️🖱️ پک کیبورد و موس ریزر گیمینگ": (10000, "لوازم کسب‌وکار؛ فقط برای مغازه پاساژ"),
}

COMBAT_POWER = {
    "🛡️ سپر انرژی": 8,
    "🛡️ نگهبان": 0,
    "🛡️ نگهبان بانک": 0,
    "🍀 شانس ویژه": 0,
    "🎟️ بلیت بازی": 0,
    "⚡ Boost XP": 0,
    "🔫 بلستر پلاسما": 10,
    "💣 بمب انرژی": 12,
    "⚔️ شمشیر انرژی": 13,
    "🦾 زره نانو": 14,
    "🐺 گرگ نگهبان": 16,
    "🦅 پهپاد همراه": 18,
    "🤖 ربات مبارز": 28,
    "🕸️ قهرمان تارزن": 30,
    "🧙 جادوگر سایه": 35,
    "⚔️ تیغه نهایی": 25,
    "🔫 تفنگ پلاسما X": 30,
    "🛡️ زره تیتانیومی": 20,
    "🤖 ربات تهاجمی X": 35,
    "🔋 هسته انرژی": 40,
    # تجهیزات شوشول بری قدرت مبارزه ندارند؛ اثرشان روی شانس شوشول بری است.
    "🔪 چاقوی دول‌بری": 0,
    "✂️ قیچی": 0,
    "🪚 اره‌برقی": 0,
    "🔪 دول‌بُر": 0,
    "🛡️ شوشول طلایی": 0,
    "💘 معشوق شوشول": 0,
}

# ================================================================
# V20 — BLACK MARKET POTIONS / PERMANENT COMBAT EQUIPMENT
# ================================================================
# One-use combat potions. Each potion changes one distinct combat aspect.
COMBAT_POTIONS = {
    "🧪 معجون خشم": (150000, "۳۰٪ قدرت آسیب حمله بعدی این نبرد را افزایش می‌دهد", "rage"),
    "🧪 معجون دقت": (120000, "۱۵٪ شانس خطای حمله را کم می‌کند؛ برای این نبرد", "accuracy"),
    "🧪 معجون ضربه بحرانی": (180000, "۲۵٪ شانس حمله بحرانی با آسیب دوبرابر", "critical"),
    "🧪 معجون درمان": (140000, "پس از حمله ۲۵ جان بازیابی می‌کند", "heal"),
    "🧪 معجون زره": (160000, "۳۰٪ از آسیب حمله بعدی را کم می‌کند", "armor"),
    "🧪 معجون ضدحمله": (190000, "۲۵٪ آسیب دریافتی را به مهاجم برمی‌گرداند", "counter"),
    "🧪 معجون سرعت": (170000, "۲۰٪ شانس جاخالی دادن از حمله بعدی", "dodge"),
    "🧪 معجون تمرکز": (110000, "۵ واحد به حداقل آسیب حمله اضافه می‌کند", "focus"),
    "🧪 معجون شکننده": (175000, "اثربخشی دفاع حریف را ۳۰٪ کم می‌کند", "shatter"),
    "🧪 معجون یخ": (155000, "آسیب حمله بعدی حریف را ۳۰٪ کم می‌کند", "freeze"),
}

# Five permanent combat items. They are never consumed by combat.
PERMANENT_COMBAT_ITEMS = {
    "⚔️ تیغه نهایی": (1200000, 25, "تجهیز دائمی؛ +25 قدرت مبارزه"),
    "🔫 تفنگ پلاسما X": (1500000, 30, "تجهیز دائمی؛ +30 قدرت مبارزه"),
    "🛡️ زره تیتانیومی": (1300000, 20, "تجهیز دائمی؛ +20 قدرت مبارزه"),
    "🤖 ربات تهاجمی X": (2200000, 35, "تجهیز دائمی؛ +35 قدرت مبارزه"),
    "🔋 هسته انرژی": (2800000, 40, "تجهیز دائمی؛ +40 قدرت مبارزه"),
}

# Ten one-use defensive potions. They are consumed when activated in a combat.
COMBAT_DEFENSE_POTIONS = {
    "🧴 معجون دفاع فولادی": (90000, 15, "۱۵٪ از آسیب حمله بعدی را کم می‌کند"),
    "🧴 معجون دفاع آهنی": (120000, 20, "۲۰٪ از آسیب حمله بعدی را کم می‌کند"),
    "🧴 معجون دفاع الماسی": (180000, 30, "۳۰٪ از آسیب حمله بعدی را کم می‌کند"),
    "🧴 معجون سپر انرژی": (240000, 40, "۴۰٪ از آسیب حمله بعدی را کم می‌کند"),
    "🧴 معجون زره نانو": (300000, 50, "۵۰٪ از آسیب حمله بعدی را کم می‌کند"),
    "🧴 معجون بازتاب": (210000, 20, "۲۰٪ آسیب حمله بعدی را به مهاجم بازمی‌گرداند"),
    "🧴 معجون جاخالی": (160000, 25, "۲۵٪ شانس جاخالی از حمله بعدی"),
    "🧴 معجون ترمیم": (150000, 20, "۲۰ جان بعد از دریافت حمله بازیابی می‌کند"),
    "🧴 معجون ضدبحرانی": (200000, 35, "۳۵٪ احتمال حمله بحرانی حریف را خنثی می‌کند"),
    "🧴 معجون سنگین": (175000, 25, "۲۵٪ قدرت آسیب حمله بعدی حریف را کم می‌کند"),
}

# Shoshol rain items: one-use attack items.
SHOSHOL_RAIN_ITEMS = {
    "🌧️ بارش شوشول": (5000000, 30, 10, "کاهش ۱۰٪ از کل دارایی هدف"),
    "🌧️ بارش شوشول نانو": (8000000, 50, 30, "کاهش ۳۰٪ از کل دارایی هدف"),
    "🌧️ بارش شوشول طلایی": (11000000, 70, 50, "کاهش ۵۰٪ از کل دارایی هدف"),
}
SHOSHOL_RAIN_DEFENSES = {
    "🛡️ پدافند بارش شوشول": (600000, "🌧️ بارش شوشول", 20, "۲۰ واحد درصد از شانس بارش شوشول کم می‌کند"),
    "🛡️ پدافند بارش شوشول نانو": (800000, "🌧️ بارش شوشول نانو", 40, "۴۰ واحد درصد از شانس بارش شوشول نانو کم می‌کند"),
    "🛡️ پدافند بارش شوشول طلایی": (1000000, "🌧️ بارش شوشول طلایی", 60, "۶۰ واحد درصد از شانس بارش شوشول طلایی کم می‌کند"),
}

# ================================================================
# 🐾 PET SYSTEM
# ================================================================
# هر حیوان یک آیتم واقعی در کوله‌پشتی است و می‌تواند فعال شود.
PETS = {
    "🐺 گرگ": (25000, "⚔️ +20 قدرت مبارزه؛ همراه مبارز"),
    "🦊 روباه": (22000, "🍀 +5٪ شانس برد در ترید و مبارزه"),
    "🐯 ببر": (40000, "⚔️ +30 قدرت مبارزه؛ مهاجم قدرتمند"),
    "🦅 عقاب": (35000, "🧠 +25٪ XP دریافتی از بردها"),
    "🐉 اژدها": (150000, "🔥 +40 قدرت مبارزه و +50٪ XP؛ حیوان بسیار کمیاب"),
}

PET_COMBAT_POWER = {
    "🐺 گرگ": 20,
    "🦊 روباه": 0,
    "🐯 ببر": 30,
    "🦅 عقاب": 0,
    "🐉 اژدها": 40,
}

def pet_owned(uid, pet):
    return inventory_qty(uid, pet) > 0

def active_pet(uid):
    with db() as c:
        r=c.execute("SELECT active_pet FROM user_pets WHERE user_id=?",(uid,)).fetchone()
    return (r[0] or "") if r else ""

def set_active_pet(uid, pet):
    if pet and pet not in PETS: return False
    if pet and not pet_owned(uid,pet): return False
    with db() as c:
        c.execute("INSERT INTO user_pets(user_id,active_pet) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET active_pet=excluded.active_pet",(uid,pet or "")); c.commit()
    return True

def pet_shop_text(uid):
    active=active_pet(uid)
    lines=["🐾 فروشگاه حیوانات / Pet Shop\n"]
    for i,(pet,(cost,desc)) in enumerate(PETS.items(),1):
        owned=inventory_qty(uid,pet)
        mark="✅ فعال" if active==pet else ("🎒 داری" if owned else "🛒 خرید")
        current_cost=get_price(price_key_for("pets", pet), cost)
        lines.append(f"{i}. {pet} — 💎 {format_coins(current_cost)} آریور\n   {desc} | {mark}")
    return "\n".join(lines)

def pet_shop_keyboard(uid):
    rows=[]
    for i,pet in enumerate(PETS,1):
        if active_pet(uid)==pet:
            rows.append([button(f"❌ غیرفعال کردن {pet}",f"pet:off:{i}")])
        elif inventory_qty(uid,pet)>0:
            rows.append([button(f"🐾 فعال کردن {pet}",f"pet:on:{i}")])
        else:
            rows.append([button(f"🛒 خرید {pet}",f"pet:buy:{i}")])
    rows.append([button("🔙 برگشت به منو","user:menu")])
    rows.append([button("❌ بستن منو","menu:close")])
    return keyboard(rows)

def pet_effect_description(pet):
    return PETS.get(pet,(0,"🎒 حیوان همراه"))[1]

def pet_chance_bonus(uid):
    return 5 if active_pet(uid)=="🦊 روباه" else 0

def pet_xp_multiplier(uid):
    return 1.5 if active_pet(uid)=="🦅 عقاب" else (1.5 if active_pet(uid)=="🐉 اژدها" else 1.0)

def pet_power(uid):
    pet=active_pet(uid)
    return PET_COMBAT_POWER.get(pet,0)

BLACK_SHOP_ITEMS = {
    k: (v[0] * 10, v[1])
    for k, v in SHOP_ITEMS_V2.items()
    if k in COMBAT_POWER and COMBAT_POWER[k] > 0
}

# 🧪 One-use trade potion. One unit is consumed automatically on the next trade.
BLACK_SHOP_ITEMS[TRADE_POTION_ITEM] = (TRADE_POTION_DEFAULT_PRICE, "+5٪ شانس برد ترید؛ با هر ترید یک عدد مصرف می‌شود")

# 🕶️ تجهیزات اختصاصی «شوشول بری»
# مجموع ابزارهای هجومی دقیقاً +30٪ به شانس پایه 50٪ اضافه می‌کنند؛ سقف موفقیت 80٪ است.
SHOSHUL_TOOLS = {
    "🔪 چاقوی دول‌بری": (12000, 8, "ابزار شوشول بری؛ +8٪ شانس موفقیت"),
    "✂️ قیچی": (14000, 8, "ابزار شوشول بری؛ +8٪ شانس موفقیت"),
    "🪚 اره‌برقی": (18000, 7, "ابزار شوشول بری؛ +7٪ شانس موفقیت"),
    "🔪 دول‌بُر": (22000, 7, "ابزار شوشول بری؛ +7٪ شانس موفقیت"),
}

# 🛡️ ضد شوشول بر: روی شانس نهایی مهاجم اثر منفی می‌گذارند.
SHOSHUL_DEFENSES = {
    "🛡️ شوشول طلایی": (30000, 15, "ضد شوشول بر؛ 15٪ از شانس برد مهاجم کم می‌کند"),
    "💘 معشوق شوشول": (22000, 10, "ضد شوشول بر؛ 10٪ از شانس برد مهاجم کم می‌کند"),
}

for _name, (_base_cost, _bonus, _desc) in {**SHOSHUL_TOOLS, **SHOSHUL_DEFENSES}.items():
    BLACK_SHOP_ITEMS[_name] = (_base_cost * 10, _desc)

# 💻 سیستم هک بانک
HACKER_ITEM = "💻 هکر"
ANTI_HACK_ITEM = "🛡️ ضد هک"
HACKER_MAX_LEVEL = 5
ANTI_HACK_MAX_LEVEL = 3
HACKER_BASE_COST = 500000
ANTI_HACK_BASE_COST = 750000
HACKER_BASE_CHANCE = 30
HACKER_LEVEL_STEP = 10
ANTI_HACK_LEVEL_STEP = 10
HACK_CATCH_CHANCE = 80

BLACK_SHOP_ITEMS[HACKER_ITEM] = (HACKER_BASE_COST, "سطح ۱ هکر؛ امکان هک موجودی بانک کاربران با ریپلای و دستور «هک»")
BLACK_SHOP_ITEMS[ANTI_HACK_ITEM] = (ANTI_HACK_BASE_COST, "سطح ۱ ضد هک؛ هر سطح ۱۰٪ از شانس هکر کم می‌کند")

def hack_level(uid):
    return min(inventory_qty(uid,HACKER_ITEM), HACKER_MAX_LEVEL)

def anti_hack_level(uid):
    return min(inventory_qty(uid,ANTI_HACK_ITEM), ANTI_HACK_MAX_LEVEL)

def hack_next_cost(uid,item):
    if item==HACKER_ITEM:
        lvl=hack_level(uid)
        base=get_price("black:"+HACKER_ITEM, HACKER_BASE_COST)
        return base*(2**lvl) if lvl<HACKER_MAX_LEVEL else 0
    if item==ANTI_HACK_ITEM:
        lvl=anti_hack_level(uid)
        base=get_price("black:"+ANTI_HACK_ITEM, ANTI_HACK_BASE_COST)
        return base*(2**lvl) if lvl<ANTI_HACK_MAX_LEVEL else 0
    return get_price(price_key_for("black", item), BLACK_SHOP_ITEMS.get(item,(0,""))[0])

def bank_guardian_level(uid):
    return 1 if inventory_qty(uid, "🛡️ نگهبان بانک") > 0 else 0

def shoshol_guardian_level(uid):
    return 1 if inventory_qty(uid, "🛡️ نگهبان") > 0 else 0

def hack_success_chance(attacker_id,target_id):
    lvl=hack_level(attacker_id)
    defense=anti_hack_level(target_id)
    # Level 1=30%; each upgrade +10%. To honor the requested level-5 cap of 80%,
    # the fifth level is treated as the final mastery level and grants the extra +20%.
    if lvl<=0: return 0,0,0
    chance=HACKER_BASE_CHANCE + (lvl-1)*HACKER_LEVEL_STEP
    if lvl==HACKER_MAX_LEVEL: chance=80
    reduction=defense*ANTI_HACK_LEVEL_STEP
    guardian_reduction=10 if bank_guardian_level(target_id) else 0
    total_reduction=reduction + guardian_reduction
    return max(0,chance-total_reduction),chance,total_reduction


def black_shop_buy(uid, item):
    if item not in BLACK_SHOP_ITEMS:
        return False, "missing", 0
    if item in (HACKER_ITEM, ANTI_HACK_ITEM):
        current = hack_level(uid) if item==HACKER_ITEM else anti_hack_level(uid)
        maximum = HACKER_MAX_LEVEL if item==HACKER_ITEM else ANTI_HACK_MAX_LEVEL
        cost = hack_next_cost(uid,item)
        if current >= maximum:
            return False, "max", 0
    else:
        repeatable = item in COMBAT_POTIONS or item in COMBAT_DEFENSE_POTIONS or item in SHOSHOL_RAIN_ITEMS or item in SHOSHOL_RAIN_DEFENSES or item == TRADE_POTION_ITEM
        if not repeatable and inventory_qty(uid, item) > 0:
            return False, "owned", BLACK_SHOP_ITEMS[item][0]
        cost = get_price(price_key_for("black", item), BLACK_SHOP_ITEMS[item][0])
    if get_balance(uid) < cost:
        return False, "funds", cost
    add_coins(uid, -cost)
    add_item(uid, item, 1)
    log_tx(uid, "black_shop_item", -cost, f"{item};level={current+1 if item in (HACKER_ITEM,ANTI_HACK_ITEM) else 1}")
    return True, "ok", cost

def combat_power(uid):
    with db() as c:
        rows=c.execute("SELECT item,quantity FROM inventory WHERE user_id=? AND quantity>0",(uid,)).fetchall()
    total=0
    for item,qty in rows:
        power=COMBAT_POWER.get(item,0)
        if power:
            total += power * min(int(qty), 10)
    total += pet_power(uid)
    return total

def combat_equipment_text(uid):
    with db() as c:
        rows=c.execute("SELECT item,quantity FROM inventory WHERE user_id=? AND quantity>0 ORDER BY item",(uid,)).fetchall()
    lines=[]
    for item,qty in rows:
        power=COMBAT_POWER.get(item,0)
        if power:
            lines.append(f"{item} × {qty} — ⚔️ +{power*min(int(qty),10)}")
        else:
            lines.append(f"{item} × {qty} — 🎒 کاربردی")
    total=combat_power(uid)
    return "🎒 تجهیزات مبارزه\n\n" + ("\n".join(lines) if lines else "هنوز تجهیزاتی نداری.") + f"\n\n⚔️ قدرت کل تجهیزات: {total}"


def ensure_player_stats(uid):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO player_stats(user_id) VALUES(?)", (uid,))
        c.commit()

def player_stats(uid):
    ensure_player_stats(uid)
    with db() as c:
        r=c.execute("SELECT games,wins,losses,draws,points,xp,best_win,win_streak,best_streak FROM player_stats WHERE user_id=?",(uid,)).fetchone()
    return {"games":r[0],"wins":r[1],"losses":r[2],"draws":r[3],"points":r[4],"xp":r[5],"best_win":r[6],"win_streak":r[7],"best_streak":r[8]}

def player_rank(uid):
    st=player_stats(uid); points=st["points"]
    rank=RANKS[0][1]
    for threshold,name in RANKS:
        if points>=threshold: rank=name
    return rank,points

def record_game(uid, result, reward=0, game_type="game"):
    ensure_player_stats(uid)
    with db() as c:
        row=c.execute("SELECT games,wins,losses,draws,points,xp,best_win,win_streak,best_streak FROM player_stats WHERE user_id=?",(uid,)).fetchone()
        games,wins,losses,draws,points,xp,best,streak,best_streak=row
        games += 1
        if result=="win":
            wins+=1; streak+=1; points+=25; xp+=int(50*pet_xp_multiplier(uid)); best=max(best,int(reward)); best_streak=max(best_streak,streak)
        elif result=="loss":
            losses+=1; streak=0; points=max(0,points-10); xp+=10
        else:
            draws+=1; streak=0; points+=5; xp+=20
        c.execute("UPDATE player_stats SET games=?,wins=?,losses=?,draws=?,points=?,xp=?,best_win=?,win_streak=?,best_streak=?,updated_at=? WHERE user_id=?",(games,wins,losses,draws,points,xp,best,streak,best_streak,int(time.time()),uid)); c.commit()
    check_achievements(uid)

def achievements_list(uid):
    with db() as c:
        return [r[0] for r in c.execute("SELECT code FROM achievements WHERE user_id=? ORDER BY unlocked_at",(uid,)).fetchall()]

def unlock_achievement(uid, code):
    with db() as c:
        cur=c.execute("INSERT OR IGNORE INTO achievements(user_id,code,unlocked_at) VALUES(?,?,?)",(uid,code,int(time.time())))
        changed=cur.rowcount>0; c.commit()
    return changed

def check_achievements(uid):
    st=player_stats(uid); checks=[]
    if st["games"]>=1: checks.append("first_game")
    if st["wins"]>=1: checks.append("first_win")
    if st["wins"]>=10: checks.append("wins_10")
    if st["wins"]>=50: checks.append("wins_50")
    if st["games"]>=100: checks.append("games_100")
    if st["best_streak"]>=5: checks.append("streak_5")
    if st["best_streak"]>=10: checks.append("streak_10")
    if get_balance(uid)>=100000: checks.append("rich_100k")
    for code in checks: unlock_achievement(uid,code)

def inventory_qty(uid,item):
    with db() as c:
        r=c.execute("SELECT quantity FROM inventory WHERE user_id=? AND item=?",(uid,item)).fetchone()
    return int(r[0]) if r else 0

def add_item(uid,item,qty=1):
    if qty<=0: return
    with db() as c:
        c.execute("INSERT INTO inventory(user_id,item,quantity) VALUES(?,?,?) ON CONFLICT(user_id,item) DO UPDATE SET quantity=quantity+excluded.quantity",(uid,item,qty)); c.commit()

def remove_item(uid,item,qty=1):
    if inventory_qty(uid,item)<qty: return False
    with db() as c:
        c.execute("UPDATE inventory SET quantity=quantity-? WHERE user_id=? AND item=?",(qty,uid,item)); c.execute("DELETE FROM inventory WHERE user_id=? AND item=? AND quantity<=0",(uid,item)); c.commit()
    return True

def consume_combat_item(uid, item):
    """Atomic one-unit inventory consumption; safe against concurrent clicks."""
    with db() as c:
        cur=c.execute("UPDATE inventory SET quantity=quantity-1 WHERE user_id=? AND item=? AND quantity>0",(uid,item))
        if cur.rowcount<=0:
            return False
        c.execute("DELETE FROM inventory WHERE user_id=? AND item=? AND quantity<=0",(uid,item))
        c.commit()
    return True

def _effect_list(state, uid):
    effects=state.setdefault("potion_effects",{})
    key=str(uid)
    value=effects.get(key, effects.get(uid, []))
    if isinstance(value,str): value=[value] if value else []
    effects[key]=list(value)
    if uid in effects and uid != key: effects.pop(uid,None)
    return effects[key]

def _take_effect(state, uid, effect):
    effects=_effect_list(state,uid)
    if effect in effects:
        effects.remove(effect)
        return True
    return False

def add_combat_potion_effect(state, uid, item):
    if item not in COMBAT_POTIONS and item not in COMBAT_DEFENSE_POTIONS:
        return False, "آیتم مبارزه‌ای نامعتبر است."
    if inventory_qty(uid,item)<=0:
        return False, "این آیتم را نداری."
    if not consume_combat_item(uid,item):
        return False, "این آیتم دیگر موجود نیست."
    if item in COMBAT_POTIONS:
        effect=COMBAT_POTIONS[item][2]
        effects=_effect_list(state,uid)
        if effect=="freeze":
            # Freeze targets the opponent's next attack.
            effects=_effect_list(state,uid)
            effects.append("freeze_target")
        else:
            effects.append(effect)
        return True, COMBAT_POTIONS[item][1]
    pct=COMBAT_DEFENSE_POTIONS[item][1]
    state.setdefault("defense_potion",{})[str(uid)]={"item":item,"pct":pct}
    return True, COMBAT_DEFENSE_POTIONS[item][2]


def combat_potion_keyboard(bid, uid):
    state=combat_states.get(bid) or duel_get(bid)
    rows=[]
    if not state: return keyboard([[button("🔙 برگشت","combat:potionback:%s"%bid)]])
    items=[]
    for item in list(COMBAT_POTIONS)+list(COMBAT_DEFENSE_POTIONS):
        q=inventory_qty(uid,item)
        if q>0:
            items.append((item,q))
    if not items:
        rows.append([button("❌ معجون قابل استفاده نداری","combat:potionback:%s"%bid)])
    else:
        for item,q in items:
            rows.append([button(f"🧪 {item} × {q}",f"combat:potion:{bid}:{list(COMBAT_POTIONS).index(item) if item in COMBAT_POTIONS else 100+list(COMBAT_DEFENSE_POTIONS).index(item)}")])
    rows.append([button("🔙 برگشت","combat:potionback:%s"%bid)])
    return keyboard(rows)

def item_effect_description(item, qty=1, uid_for_effect=None):
    if item in SHOSHUL_TOOLS:
        _cost, bonus, desc = SHOSHUL_TOOLS[item]
        return f"🎯 {desc}"
    if item in SHOSHUL_DEFENSES:
        _cost, reduction, desc = SHOSHUL_DEFENSES[item]
        return f"🛡️ {desc}"
    if item == HACKER_ITEM: return f"💻 هکر سطح {hack_level(uid_for_effect) if uid_for_effect is not None else qty}/{HACKER_MAX_LEVEL} | با ریپلای روی کاربر و نوشتن «هک» تلاش می‌کنی؛ شانس فعلی تا ۸۰٪"
    if item == ANTI_HACK_ITEM: return f"🛡️ ضد هک سطح {anti_hack_level(uid_for_effect) if uid_for_effect is not None else qty}/{ANTI_HACK_MAX_LEVEL} | هر سطح ۱۰٪ از شانس هکر کم می‌کند"
    if item == "⚡ Boost XP": return "🧠 با خرید/استفاده، ۵۰۰ XP اضافه می‌کند"
    if item == "🍀 شانس ویژه": return "🍀 در مبارزه یک‌بار +10٪ شانس می‌دهد و سپس مصرف می‌شود"
    if item == "🛡️ سپر انرژی": return "🛡️ یک شکست در مبارزه را خنثی می‌کند و سپس مصرف می‌شود"
    if item == "🛡️ نگهبان": return "🛡️ دفاع دائمی؛ 10٪ از شانس نهایی شوشول بری مهاجم کم می‌کند"
    if item == "🛡️ نگهبان بانک": return "🏦 دفاع دائمی؛ 10٪ از شانس نهایی هک مهاجم کم می‌کند"
    if item == "🎟️ بلیت بازی": return "🎮 آیتم اقتصادی و قابل معامله در بازار"
    if item in PETS:
        return "🐾 " + pet_effect_description(item) + (" | ✅ فعال" if uid_for_effect is not None and active_pet(uid_for_effect) == item else " | برای استفاده فعالش کن")
    if item in COMBAT_POTIONS:
        return "🧪 مصرف یک‌باره در یک نبرد: " + COMBAT_POTIONS[item][1]
    if item in COMBAT_DEFENSE_POTIONS:
        return "🧴 مصرف یک‌باره در یک نبرد: " + COMBAT_DEFENSE_POTIONS[item][2]
    if item in SHOSHOL_RAIN_ITEMS:
        _cost,_chance,_loss,_desc=SHOSHOL_RAIN_ITEMS[item]
        return f"🌧️ یک‌بارمصرف؛ {_chance}٪ شانس؛ {_desc}"
    if item in SHOSHOL_RAIN_DEFENSES:
        return "🛡️ " + SHOSHOL_RAIN_DEFENSES[item][3]
    if item in PERMANENT_COMBAT_ITEMS:
        return "♾️ دائمی؛ " + PERMANENT_COMBAT_ITEMS[item][2]
    if item in COMBAT_POWER and COMBAT_POWER[item] > 0:
        return f"⚔️ +{COMBAT_POWER[item]} قدرت مبارزه برای هر عدد"
    return "🎒 آیتم کاربردی"

def inventory_text(uid):
    with db() as c: rows=c.execute("SELECT item,quantity FROM inventory WHERE user_id=? AND quantity>0 ORDER BY item",(uid,)).fetchall()
    if not rows: return "🎒 کوله‌پشتی شما خالی است.\n\n🛍️ از فروشگاه آیتم یا فروشگاه سیاه خرید کن."
    lines=[]
    for item,qty in rows:
        power=COMBAT_POWER.get(item,0)
        power_suffix=f" | ⚔️ قدرت کل: +{power*min(int(qty),10)}" if power else ""
        lines.append(f"{item} × {qty}{power_suffix}\n   ↳ {item_effect_description(item, qty, uid)}")
    return "🎒 کوله‌پشتی و تجهیزات شما\n\n"+"\n".join(lines)+f"\n\n⚔️ قدرت کل مبارزه: {combat_power(uid)}"

def shop_v2_buy(uid,item):
    if item not in SHOP_ITEMS_V2: return False,"missing",0
    cost=get_price(price_key_for("shop", item), SHOP_ITEMS_V2[item][0])
    if get_balance(uid)<cost: return False,"funds",cost
    add_coins(uid,-cost); add_item(uid,item,1); log_tx(uid,"shop_item",-cost,item)
    if item=="⚡ Boost XP":
        with db() as c: c.execute("UPDATE player_stats SET xp=xp+500 WHERE user_id=?",(uid,)); c.commit()
    return True,"ok",cost

def create_item_listing(seller,item,qty,price):
    if not item or qty<=0 or price<=0 or inventory_qty(seller,item)<qty: return False
    if not remove_item(seller,item,qty): return False
    with db() as c: c.execute("INSERT INTO item_market(seller_id,item,quantity,price,active,created_at) VALUES(?,?,?, ?,1,?)",(seller,item,qty,price,int(time.time()))); c.commit()
    log_tx(seller,"item_market_lock",0,f"{item} x{qty} price={price}")
    return True

def active_item_market(limit=10):
    with db() as c: return c.execute("SELECT listing_id,seller_id,item,quantity,price,created_at FROM item_market WHERE active=1 ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()

def buy_item_listing(buyer,lid):
    with db() as c:
        row=c.execute("SELECT seller_id,item,quantity,price,active FROM item_market WHERE listing_id=?",(lid,)).fetchone()
        if not row: return False,"missing",0
        seller,item,qty,price,active=row
        if not active: return False,"inactive",price
        if seller==buyer: return False,"self",price
        if get_balance(buyer)<price: return False,"funds",price
        c.execute("UPDATE item_market SET active=0 WHERE listing_id=? AND active=1",(lid,)); c.commit()
    add_coins(buyer,-price); add_coins(seller,price); add_item(buyer,item,qty)
    log_tx(buyer,"item_market_buy",-price,f"listing={lid}"); log_tx(seller,"item_market_sell",price,f"listing={lid}")
    return True,"ok",price

# ================================================================
# REAL ITEM AUCTION MARKET
# ================================================================
def create_auction(seller,item,qty,start_price,minutes):
    if not item or qty<=0 or start_price<=0 or minutes<=0 or inventory_qty(seller,item)<qty:
        return None,"invalid"
    if not remove_item(seller,item,qty): return None,"invalid"
    increment=max(1,start_price//10)
    now=int(time.time()); end=now+min(minutes,1440)*60
    with db() as c:
        cur=c.execute("INSERT INTO item_auctions(seller_id,item,quantity,start_price,current_bid,current_bidder,min_increment,status,created_at,end_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(seller,item,qty,start_price,0,0,increment,"active",now,end))
        aid=cur.lastrowid; c.commit()
    log_tx(seller,"auction_lock",0,f"auction={aid} {item} x{qty}")
    return aid,"ok"

def auction_get(aid):
    with db() as c:
        r=c.execute("SELECT auction_id,seller_id,item,quantity,start_price,current_bid,current_bidder,min_increment,status,created_at,end_at FROM item_auctions WHERE auction_id=?",(aid,)).fetchone()
    if not r:return None
    return dict(id=r[0],seller_id=r[1],item=r[2],quantity=r[3],start_price=r[4],current_bid=r[5],current_bidder=r[6],min_increment=r[7],status=r[8],created_at=r[9],end_at=r[10])

def active_auctions(limit=12):
    now=int(time.time())
    with db() as c:
        return c.execute("SELECT auction_id,seller_id,item,quantity,start_price,current_bid,current_bidder,min_increment,end_at FROM item_auctions WHERE status='active' AND end_at>? ORDER BY end_at LIMIT ?",(now,limit)).fetchall()

def place_auction_bid(aid,bidder,amount):
    a=auction_get(aid)
    if not a or a['status']!='active': return False,'closed',0
    now=int(time.time())
    if now>=a['end_at']: return False,'expired',a['current_bid']
    if bidder==a['seller_id']: return False,'seller',a['current_bid']
    minimum=a['start_price'] if a['current_bid']<=0 else a['current_bid']+a['min_increment']
    if amount<minimum:return False,'minimum',minimum
    if get_balance(bidder)<amount:return False,'funds',amount
    # Lock the new bid and refund the previous bidder.
    add_coins(bidder,-amount); log_tx(bidder,'auction_bid_lock',-amount,f'auction={aid}')
    if a['current_bidder'] and a['current_bidder']!=bidder and a['current_bid']>0:
        add_coins(a['current_bidder'],a['current_bid']); log_tx(a['current_bidder'],'auction_outbid_refund',a['current_bid'],f'auction={aid}')
    with db() as c:
        c.execute("UPDATE item_auctions SET current_bid=?,current_bidder=? WHERE auction_id=? AND status='active'",(amount,bidder,aid)); c.commit()
    return True,'ok',amount

def finish_auction(aid):
    a=auction_get(aid)
    if not a or a['status']!='active' or int(time.time())<a['end_at']:return None
    if a['current_bidder']:
        add_coins(a['seller_id'],a['current_bid']); add_item(a['current_bidder'],a['item'],a['quantity'])
        log_tx(a['seller_id'],'auction_sale',a['current_bid'],f'auction={aid}')
        log_tx(a['current_bidder'],'auction_win',0,f'auction={aid} {a["item"]}')
        result=('sold',a['current_bidder'],a['current_bid'])
    else:
        add_item(a['seller_id'],a['item'],a['quantity']); log_tx(a['seller_id'],'auction_return',0,f'auction={aid}')
        result=('returned',a['seller_id'],0)
    with db() as c:c.execute("UPDATE item_auctions SET status='finished' WHERE auction_id=? AND status='active'",(aid,)); c.commit()
    return result

async def auction_expiry_task(aid):
    a=auction_get(aid)
    if not a:return
    await asyncio.sleep(max(1,a['end_at']-int(time.time())))
    finish_auction(aid)


def streak_text(uid):
    st=player_stats(uid); daily=get_daily_state(uid)
    return f"🔥 استریک برد: {st['win_streak']}\n🏆 بهترین استریک: {st['best_streak']}\n📅 استریک روزانه: {daily['streak']} روز"

def leaderboard_points(limit=10):
    with db() as c:
        return c.execute("SELECT u.id,u.username,s.points,s.wins,s.games,s.best_streak FROM users u JOIN player_stats s ON s.user_id=u.id ORDER BY s.points DESC,s.wins DESC LIMIT ?",(limit,)).fetchall()

def leaderboard_wins(limit=10):
    with db() as c:
        return c.execute("SELECT u.id,u.username,s.wins,s.games,s.points FROM users u JOIN player_stats s ON s.user_id=u.id ORDER BY s.wins DESC,s.points DESC LIMIT ?",(limit,)).fetchall()

def leaderboard_balance(limit=10):
    return leaderboard(limit)

def tournament_create(chat_id,creator_id,stake):
    if stake<=0 or get_balance(creator_id)<stake: return None,"funds"
    add_coins(creator_id,-stake); log_tx(creator_id,"tournament_lock",-stake,"tournament")
    with db() as c:
        cur=c.execute("INSERT INTO tournaments(chat_id,creator_id,stake,prize,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",(chat_id,creator_id,stake,stake,"waiting",int(time.time()),int(time.time())+TOURNAMENT_WAIT_SECONDS)); tid=cur.lastrowid
        c.execute("INSERT INTO tournament_players(tournament_id,user_id,joined_at,active) VALUES(?,?,?,1)",(tid,creator_id,int(time.time()))); c.commit()
    return tid,"ok"

def tournament_get(tid):
    with db() as c:
        r=c.execute("SELECT id,chat_id,message_id,creator_id,stake,prize,status,created_at,expires_at FROM tournaments WHERE id=?",(tid,)).fetchone()
    if not r:return None
    return {"id":r[0],"chat_id":r[1],"message_id":r[2],"creator_id":r[3],"stake":r[4],"prize":r[5],"status":r[6],"created_at":r[7],"expires_at":r[8]}

def tournament_players(tid,active_only=False):
    with db() as c:
        q="SELECT user_id FROM tournament_players WHERE tournament_id=?"
        if active_only:q+=" AND active=1"
        q+=" ORDER BY joined_at"
        return [r[0] for r in c.execute(q,(tid,)).fetchall()]

def tournament_join(tid,uid):
    t=tournament_get(tid)
    if not t:return None,"closed"
    if t["status"]!="waiting":return t,"closed"
    if int(time.time())>=t["expires_at"]:return t,"expired"
    ps=tournament_players(tid)
    if uid in ps:return t,"self"
    if len(ps)>=8:return t,"full"
    if get_balance(uid)<t["stake"]:return t,"funds"
    add_coins(uid,-t["stake"]); log_tx(uid,"tournament_lock",-t["stake"],f"tid={tid}")
    with db() as c:
        c.execute("INSERT INTO tournament_players(tournament_id,user_id,joined_at,active) VALUES(?,?,?,1)",(tid,uid,int(time.time())))
        c.execute("UPDATE tournaments SET prize=prize+? WHERE id=?",(t["stake"],tid)); c.commit()
    return tournament_get(tid),"ok"

def champion_record(uid):
    with db() as c:
        r=c.execute("SELECT titles,wins,best_power FROM champions WHERE user_id=?",(uid,)).fetchone()
    return {"titles":int(r[0]),"wins":int(r[1]),"best_power":int(r[2])} if r else {"titles":0,"wins":0,"best_power":0}

def award_champion(uid,power):
    with db() as c:
        c.execute("INSERT INTO champions(user_id,titles,wins,best_power,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET titles=titles+1,wins=wins+1,best_power=MAX(best_power,excluded.best_power),updated_at=excluded.updated_at",(uid,1,1,power,int(time.time()))); c.commit()

def tournament_match_winner(a,b):
    pa,pb=combat_power(a),combat_power(b)
    diff=pa-pb
    chance=max(15,min(85,50+diff*2))
    return (a if random.random()<chance/100 else b),pa,pb,chance

def tournament_round(tid):
    t=tournament_get(tid)
    if not t:return None
    ps=tournament_players(tid,active_only=True)
    if len(ps)==1:
        winner=ps[0]
        if t["status"]!="finished":
            with db() as c:c.execute("UPDATE tournaments SET status='finished' WHERE id=?",(tid,)); c.commit()
            add_coins(winner,t["prize"]); log_tx(winner,"tournament_win",t["prize"],f"tid={tid}")
            award_champion(winner,combat_power(winner)); record_game(winner,"win",t["prize"],"tournament")
            for u in tournament_players(tid):
                if u!=winner: record_game(u,"loss",0,"tournament")
        return ("final",winner,t["prize"],[])
    with db() as c:
        r=c.execute("SELECT COALESCE(MAX(round_no),0) FROM tournament_rounds WHERE tournament_id=?",(tid,)).fetchone(); rnd=int(r[0])+1
    results=[]; winners=[]
    for i in range(0,len(ps)-1,2):
        a,b=ps[i],ps[i+1]
        w,pa,pb,chance=tournament_match_winner(a,b); l=b if w==a else a
        winners.append(w); results.append((a,b,w,l,pa,pb,chance))
        with db() as c:
            c.execute("INSERT INTO tournament_rounds(tournament_id,round_no,player_a,player_b,winner_id) VALUES(?,?,?,?,?)",(tid,rnd,a,b,w))
            c.execute("UPDATE tournament_players SET active=0 WHERE tournament_id=? AND user_id=?",(tid,l)); c.commit()
    if len(ps)%2==1:
        bye=ps[-1]; winners.append(bye); results.append((bye,None,bye,None,combat_power(bye),0,100))
    return ("round",rnd,winners,results)

TOURNAMENT_WAIT_SECONDS=120

# ================================================================
# PLAYER-vs-PLAYER WAGER GAMES
# ================================================================
WAGER_GAME_NAMES = {
    "dooz": "دوز",
    "rps": "سنگ کاغذ قیچی",
    "cards": "جنگ کارت",
    "evenodd": "زوج یا فرد",
    "guess": "حدس عدد",
    "higher": "بالاتر",
    "dice": "تاس جنگ",
    "blackjack": "بلک‌جک ساده",
    "quickmath": "مسابقه سرعت",
    "seven": "هفت خبیث",
}

def create_wager(chat_id, creator_id, game_type, stake):
    global wager_counter
    if stake <= 0 or get_balance(creator_id) < stake:
        return None, "funds"
    add_coins(creator_id, -stake)
    with db() as c:
        cur = c.execute(
            "INSERT INTO wager_games(chat_id,message_id,game_type,creator_id,stake,status,created_at,expires_at) VALUES(?,?,?,?,?,'waiting',?,?)",
            (chat_id, 0, game_type, creator_id, stake, int(time.time()), int(time.time()) + WAGER_WAIT_SECONDS)
        )
        wid = cur.lastrowid
        c.commit()
    wager_counter += 1
    wager_games[wid] = {
        "id": wid, "chat_id": chat_id, "message_id": 0, "game_type": game_type,
        "creator_id": creator_id, "stake": stake, "opponent_id": None,
        "status": "waiting", "created_at": time.time(), "expires_at": time.time() + WAGER_WAIT_SECONDS,
        "timeout_token": 0, "timeout_tasks": set()
    }
    log_tx(creator_id, "wager_lock", -stake, WAGER_GAME_NAMES.get(game_type, game_type))
    return wid, "ok"


# ================================================================
# COMBAT V4: WEAPONS + DEFENSE EQUIPMENT
# ================================================================
COMBAT_WEAPONS = {
    "🔫 بلستر پلاسما": 10, "💣 بمب انرژی": 12, "⚔️ شمشیر انرژی": 13,
    "🤖 ربات مبارز": 18, "🕸️ قهرمان تارزن": 20, "🧙 جادوگر سایه": 22,
    "⚔️ تیغه نهایی": 25, "🔫 تفنگ پلاسما X": 30, "🛡️ زره تیتانیومی": 20,
    "🤖 ربات تهاجمی X": 35, "🔋 هسته انرژی": 40,
}
COMBAT_DEFENSE_ITEMS = {
    "🦺 جلیقه ضد گلوله": (250000, 10, "۱۰٪ از آسیب حمله بعدی را خنثی می‌کند"),
    "🪖 کلاه ایمنی": (350000, 15, "۱۵٪ از آسیب حمله بعدی را خنثی می‌کند"),
    "🛡️ سپر فولادی": (500000, 20, "۲۰٪ از آسیب حمله بعدی را خنثی می‌کند"),
    "🥋 زره طلایی": (750000, 30, "۳۰٪ از آسیب حمله بعدی را خنثی می‌کند"),
    "💎 سپر الماسی": (1000000, 40, "۴۰٪ از آسیب حمله بعدی را خنثی می‌کند"),
    "👑 زره افسانه‌ای": (1500000, 50, "۵۰٪ از آسیب حمله بعدی را خنثی می‌کند"),
}
for _name, (_cost, _pct, _desc) in COMBAT_DEFENSE_ITEMS.items():
    BLACK_SHOP_ITEMS[_name] = (_cost, _desc)

for _name, (_cost, _power, _desc) in PERMANENT_COMBAT_ITEMS.items():
    BLACK_SHOP_ITEMS[_name] = (_cost, _desc)

for _name, (_cost, _desc, _effect) in COMBAT_POTIONS.items():
    BLACK_SHOP_ITEMS[_name] = (_cost, _desc)

for _name, (_cost, _pct, _desc) in COMBAT_DEFENSE_POTIONS.items():
    BLACK_SHOP_ITEMS[_name] = (_cost, _desc)

for _name, (_cost, _chance, _loss_pct, _desc) in SHOSHOL_RAIN_ITEMS.items():
    BLACK_SHOP_ITEMS[_name] = (_cost, f"{_chance}٪ شانس؛ {_desc}")

for _name, (_cost, _target_item, _reduction, _desc) in SHOSHOL_RAIN_DEFENSES.items():
    BLACK_SHOP_ITEMS[_name] = (_cost, _desc)

def combat_attack_power(uid):
    with db() as c:
        rows=c.execute("SELECT item,quantity FROM inventory WHERE user_id=? AND quantity>0",(uid,)).fetchall()
    return sum(COMBAT_WEAPONS.get(item,0)*min(int(qty),3) for item,qty in rows)

def combat_defense_percent(uid):
    with db() as c:
        rows=c.execute("SELECT item,quantity FROM inventory WHERE user_id=? AND quantity>0",(uid,)).fetchall()
    best=0; best_item=""
    for item,qty in rows:
        if int(qty)>0 and item in COMBAT_DEFENSE_ITEMS:
            pct=COMBAT_DEFENSE_ITEMS[item][1]
            if pct>best: best,best_item=pct,item
    return min(50,best),best_item

def combat_attack_damage(uid):
    return max(5,min(45,random.randint(7,12)+combat_attack_power(uid)//2))

def set_wager_message(wid, message_id):
    if wid in wager_games:
        wager_games[wid]["message_id"] = message_id
    with db() as c:
        c.execute("UPDATE wager_games SET message_id=? WHERE id=? AND status='waiting'", (message_id, wid))
        c.commit()

def get_wager(wid):
    if wid in wager_games:
        return wager_games[wid]
    with db() as c:
        row = c.execute(
            "SELECT id,chat_id,message_id,game_type,creator_id,stake,opponent_id,status,created_at,expires_at FROM wager_games WHERE id=?",
            (wid,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": row[0], "chat_id": row[1], "message_id": row[2], "game_type": row[3],
        "creator_id": row[4], "stake": row[5], "opponent_id": row[6] or None,
        "status": row[7], "created_at": row[8], "expires_at": row[9]
    }

def refund_wager(wid):
    w = get_wager(wid)
    if not w or w["status"] != "waiting":
        return False, w
    add_coins(w["creator_id"], w["stake"])
    log_tx(w["creator_id"], "wager_refund", w["stake"], WAGER_GAME_NAMES.get(w["game_type"], w["game_type"]))
    with db() as c:
        c.execute("UPDATE wager_games SET status='refunded' WHERE id=? AND status='waiting'", (wid,))
        c.commit()
    wager_games.pop(wid, None)
    return True, w

def join_wager(wid, opponent_id):
    w = get_wager(wid)
    if not w:
        return None, "missing"
    if w["status"] != "waiting":
        return w, "closed"
    if int(time.time()) >= int(w["expires_at"]):
        return w, "expired"
    if opponent_id == w["creator_id"]:
        return w, "self"
    if get_balance(opponent_id) < w["stake"]:
        return w, "funds"
    add_coins(opponent_id, -w["stake"])
    with db() as c:
        c.execute(
            "UPDATE wager_games SET opponent_id=?,status='active' WHERE id=? AND status='waiting'",
            (opponent_id, wid)
        )
        c.commit()
    w["opponent_id"] = opponent_id
    w["status"] = "active"
    wager_games[wid] = w
    log_tx(opponent_id, "wager_lock", -w["stake"], WAGER_GAME_NAMES.get(w["game_type"], w["game_type"]))
    return w, "ok"

def finish_wager(wid, winner_id=None, draw=False):
    w = get_wager(wid)
    if not w or w["status"] != "active":
        return None, "closed"
    pot = w["stake"] * 2
    game_name = WAGER_GAME_NAMES.get(w["game_type"], w["game_type"])
    if draw:
        add_coins(w["creator_id"], w["stake"]); add_coins(w["opponent_id"], w["stake"])
        log_tx(w["creator_id"], "wager_draw_refund", w["stake"], game_name)
        log_tx(w["opponent_id"], "wager_draw_refund", w["stake"], game_name)
        record_game(w["creator_id"], "draw", w["stake"], w["game_type"])
        record_game(w["opponent_id"], "draw", w["stake"], w["game_type"])
    else:
        add_coins(winner_id, pot); log_tx(winner_id, "wager_win", pot, game_name)
        loser = w["opponent_id"] if winner_id == w["creator_id"] else w["creator_id"]
        record_game(winner_id, "win", pot, w["game_type"]); record_game(loser, "loss", 0, w["game_type"])
    with db() as c:
        c.execute("UPDATE wager_games SET status=? WHERE id=?", ("draw" if draw else "finished", wid)); c.commit()
    wager_games.pop(wid, None)
    check_achievements(w["creator_id"]); check_achievements(w["opponent_id"])
    return w, "ok"

def wager_invite_keyboard(wid):
    return keyboard([[button("🎮 شرکت کردن", f"wager:join:{wid}")]])

def wager_game_players(w):
    return (w["creator_id"], w["opponent_id"])

def wager_display_name(user):
    return f"@{user.username}" if user and user.username else (user.full_name if user else "بازیکن")

def wager_ids_text(w):
    return (f"👤 بازیکن اول: {mention_by_id(w['creator_id'])}\n"
            f"👤 بازیکن دوم: {mention_by_id(w['opponent_id'])}")


def wager_expected_player(w):
    typ=w.get("game_type")
    if typ=="dooz": return w.get("turn")
    if typ=="blackjack": return w.get("bj_turn")
    if typ=="guess": return w["creator_id"] if w.get("target") is None else w["opponent_id"]
    if typ in ("rps","evenodd","cards","dice","higher"):
        choices=w.get("choices") if typ in ("rps","evenodd") else w.get("rolls")
        choices=choices or {}
        missing=[uid for uid in (w["creator_id"],w["opponent_id"]) if uid not in choices]
        if len(missing)==1: return missing[0]
        if len(missing)==2: return w["creator_id"]
    return None


def refresh_wager_timeout(wid):
    w=wager_games.get(wid)
    if not w or w.get("status")!="active": return
    w["timeout_token"]=int(w.get("timeout_token",0))+1
    token=w["timeout_token"]
    task=asyncio.create_task(wager_inactivity_timeout(wid,token))
    w.setdefault("timeout_tasks",set()).add(task)
    task.add_done_callback(lambda t: w.get("timeout_tasks",set()).discard(t))


async def wager_inactivity_timeout(wid, token):
    await asyncio.sleep(WAGER_WAIT_SECONDS)
    w=wager_games.get(wid)
    if not w or w.get("status")!="active" or int(w.get("timeout_token",0))!=token:
        return
    expected=wager_expected_player(w)
    if expected is None:
        finish_wager(wid,draw=True)
        try:
            await bot.send_message(w["chat_id"],
                f"⏰ یک دقیقه گذشت و هیچ پاسخ معتبری ثبت نشد.\n"
                f"🎮 بازی: {WAGER_GAME_NAMES.get(w['game_type'],w['game_type'])}\n"
                f"🤝 بازی مساوی شد و ورودی هر دو نفر برگشت.\n\n{wager_ids_text(w)}")
        except Exception: pass
        return
    winner=w["opponent_id"] if expected==w["creator_id"] else w["creator_id"]
    finish_wager(wid,winner)
    try:
        await bot.send_message(w["chat_id"],
            f"⏰ یک دقیقه فرصت {display_name_by_id(expected)} تمام شد.\n"
            f"🚫 به دلیل عدم انجام حرکت، حریف برنده اعلام شد.\n"
            f"🏆 برنده: {mention_by_id(winner)}\n"
            f"💎 جایزه: {format_coins(w['stake']*2)} آریور\n\n{wager_ids_text(w)}", parse_mode="HTML")
    except Exception: pass


async def wager_expiry_task(wid):
    await asyncio.sleep(WAGER_WAIT_SECONDS)
    w = get_wager(wid)
    if not w or w["status"] != "waiting":
        return
    ok, w = refund_wager(wid)
    if not ok:
        return
    try:
        await bot.edit_message_text(
            chat_id=w["chat_id"],
            message_id=w["message_id"],
            text=f"⏰ زمان «{WAGER_GAME_NAMES.get(w['game_type'], w['game_type'])}» تمام شد.\n\n"
                 f"👤 کسی شرکت نکرد.\n💎 مبلغ {format_coins(w['stake'])} آریور به حساب سازنده برگشت خورد. ↩️"
        )
    except Exception:
        pass

async def start_wager_game(w):
    gid=w["id"]; chat_id=w["chat_id"]; creator=w["creator_id"]; opponent=w["opponent_id"]; stake=w["stake"]
    name=WAGER_GAME_NAMES.get(w["game_type"],w["game_type"])
    w.setdefault("timeout_token",0); w.setdefault("timeout_tasks",set())
    if w["game_type"]=="dooz":
        wager_games[gid]["board"]=[""]*9; wager_games[gid]["turn"]=creator
        await send_bot_message(chat_id,f"🟢🔴 دوز شروع شد!\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n\n{wager_ids_text(w)}\n\nنوبت {mention_by_id(creator)} است.",reply_markup=dooz_keyboard(gid),parse_mode="HTML")
    elif w["game_type"]=="rps":
        wager_games[gid]["choices"]={}
        await send_bot_message(chat_id,f"✊✋✌️ {name} شروع شد!\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n👥 {display_name_by_id(creator)} × {display_name_by_id(opponent)}\n{wager_ids_text(w)}\n\nهر دو بازیکن انتخاب خود را بزنند.",reply_markup=keyboard([[button("✊ سنگ",f"wager:rps:{gid}:rock"),button("📄 کاغذ",f"wager:rps:{gid}:paper"),button("✂️ قیچی",f"wager:rps:{gid}:scissors")]]))
    elif w["game_type"]=="evenodd":
        wager_games[gid]["choices"]={}
        await send_bot_message(chat_id,f"🎯 زوج یا فرد شروع شد!\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n\n👤 بازیکن اول: {display_name_by_id(creator)}\n👤 بازیکن دوم: {display_name_by_id(opponent)}\n{wager_ids_text(w)}\n\nهر بازیکن انتخاب خودش را بزند.",reply_markup=keyboard([[button("🔵 زوج",f"wager:evenodd:{gid}:even"),button("🟣 فرد",f"wager:evenodd:{gid}:odd")]]))
    elif w["game_type"]=="guess":
        wager_games[gid]["target"]=None
        await send_bot_message(chat_id,f"🔢 حدس عدد شروع شد!\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n\n👤 بازیکن اول: {display_name_by_id(creator)}\n👤 بازیکن دوم: {display_name_by_id(opponent)}\n{wager_ids_text(w)}\n\n🎯 اول {display_name_by_id(creator)} یک عدد مخفی بین ۱ تا ۱۰ انتخاب کند.",reply_markup=keyboard([[button(str(i),f"wager:guess:{gid}:secret:{i}") for i in range(1,6)],[button(str(i),f"wager:guess:{gid}:secret:{i}") for i in range(6,11)]]))
    elif w["game_type"] in ("cards","dice","higher"):
        w["rolls"]={}; action={"cards":"🃏 کارت بکش","dice":"🎲 تاس بنداز","higher":"📈 عدد بگیر"}[w["game_type"]]
        await send_bot_message(chat_id,f"{action} — {name} شروع شد!\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n\n👤 بازیکن اول: {display_name_by_id(creator)}\n👤 بازیکن دوم: {display_name_by_id(opponent)}\n{wager_ids_text(w)}\n\nهر دو بازیکن روی دکمه بزنند.",reply_markup=keyboard([[button(action,f"wager:draw:{gid}")]]))
    elif w["game_type"]=="blackjack":
        deck=[1,2,3,4,5,6,7,8,9,10,10,10,10]*4; random.shuffle(deck)
        w["deck"]=deck; w["hands"]={creator:[deck.pop(),deck.pop()],opponent:[deck.pop(),deck.pop()]}; w["stood"]={creator:False,opponent:False}; w["bj_turn"]=creator
        await send_bot_message(chat_id,f"🃏 بلک‌جک شروع شد!\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n\n👤 بازیکن اول: {display_name_by_id(creator)}\n👤 بازیکن دوم: {display_name_by_id(opponent)}\n{wager_ids_text(w)}\n\nنوبت {mention_by_id(creator)} است.\nدست شما: {sum(w['hands'][creator])}",reply_markup=keyboard([[button("🃏 کارت بگیر",f"wager:blackjack:{gid}:hit"),button("✋ ایست",f"wager:blackjack:{gid}:stand")]]))
    elif w["game_type"]=="quickmath":
        a=random.randint(2,20); b=random.randint(2,20); op=random.choice(["+","-","×"]); ans=a+b if op=="+" else a-b if op=="-" else a*b
        choices={ans,ans+random.choice([-3,-2,-1,1,2,3]),ans+random.choice([-5,-4,4,5]),ans+random.choice([-7,-6,6,7])}
        while len(choices)<4: choices.add(ans+random.randint(-10,10))
        choices=list(choices); random.shuffle(choices); w["math_answer"]=ans; w["math_started"]=time.time()
        await send_bot_message(chat_id,f"⚡ مسابقه سرعت شروع شد!\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n\n👤 بازیکن اول: {display_name_by_id(creator)}\n👤 بازیکن دوم: {display_name_by_id(opponent)}\n{wager_ids_text(w)}\n\n🧠 سریع‌ترین جواب درست برنده است:\n\n{a} {op} {b} = ؟",reply_markup=keyboard([[button(str(x),f"wager:quickmath:{gid}:{x}") for x in choices[:2]],[button(str(x),f"wager:quickmath:{gid}:{x}") for x in choices[2:]]]))
        refresh_wager_timeout(gid)

    if w.get("game_type") != "quickmath":
        refresh_wager_timeout(gid)

async def quickmath_timeout(gid):
    await asyncio.sleep(60)
    w=wager_games.get(gid)
    if not w or w.get("status")!="active" or "math_answer" not in w:return
    finish_wager(gid,draw=True)
    try: await bot.send_message(w["chat_id"],f"⏰ زمان مسابقه سرعت تمام شد؛ هیچ پاسخ درستی ثبت نشد.\n🤝 ورودی هر دو نفر برگشت.\n\n{wager_ids_text(w)}")
    except Exception:pass

# ================================================================
# 🃏 7 KHABIS — MULTIPLAYER WAGER GAME
# ================================================================
def seven_make_deck():
    # Standard 52-card deck: 4 suits × 13 ranks.
    deck=[f"{rank}|{suit}" for suit in SEVEN_SUITS for rank in SEVEN_RANKS]
    random.shuffle(deck)
    return deck


def seven_card_text(card):
    rank,suit=card.split("|",1)
    if rank=="JOKER":
        return "🃏 جوکر"
    return f"{rank}{suit}"


def seven_card_rank(card):
    return card.split("|",1)[0]


def seven_card_suit(card):
    return card.split("|",1)[1]


def seven_is_joker(card):
    return seven_card_rank(card)=="JOKER"


def seven_deal_count(n):
    # Total deck = 52 cards. The center count includes the active card.
    return {2:11,3:7,4:5}[n]


def seven_playable(card, active_card):
    # Jack can always be played, regardless of the active card suit/rank.
    if seven_is_joker(card):
        return True
    if seven_card_rank(card)=="J":
        return True
    if seven_is_joker(active_card):
        return True
    return seven_card_rank(card)==seven_card_rank(active_card) or seven_card_suit(card)==seven_card_suit(active_card)


def seven_has_playable(hand, active_card):
    return any(seven_playable(c,active_card) for c in hand)


def seven_has_special(hand, rank):
    return any(seven_card_rank(c)==rank for c in hand)


def seven_player_ids(g):
    return g["players"]


def seven_player_name(uid):
    return mention_by_id(uid)


def seven_state_text(g, notice=""):
    turn_uid=g["players"][g["turn_index"]]
    turn_name=seven_player_name(turn_uid)
    penalty=g.get("penalty",0)
    direction="➡️ ساعتگرد" if g.get("direction",1)==1 else "⬅️ پادساعتگرد"
    lines=["🃏 هفت خبیث",f"💎 شرط هر نفر: {format_coins(g['stake'])} آریور",f"👥 بازیکنان: {len(g['players'])}/{g['max_players']}"]
    lines.append(f"🎴 کارت زمینه: {seven_card_text(g['active_card'])}")
    lines.append(f"🔄 جهت بازی: {direction}")
    if penalty:
        lines.append(f"🔥 جریمه ۷: {penalty} کارت")
    lines.append(f"⏱️ نوبت: {turn_name}")
    if notice:
        lines.append("")
        lines.append(notice)
    lines.append("")
    lines.append("🔒 کارت‌های هر بازیکن فقط در پیوی خودش نمایش داده می‌شود.")
    return "\n".join(lines)


def seven_public_keyboard(g):
    left=max(0,int(g.get("deadline",time.time())-time.time()))
    return keyboard([[timer_button(left,"زمان نوبت")],[button("🎯 نوبت","seven:turn" )]])


def seven_private_keyboard(g, uid):
    hand=g["hands"].get(str(uid),[])
    rows=[]
    card_buttons=[]
    for i,card in enumerate(hand):
        card_buttons.append(button(f"🎴 {seven_card_text(card)}",f"seven:play:{g['id']}:{i}"))
    for i in range(0,len(card_buttons),5):
        rows.append(card_buttons[i:i+5])
    left=max(0,int(g.get("deadline",time.time())-time.time()))
    rows.append([timer_button(left,"زمان")])
    turn_uid=g["players"][g["turn_index"]]
    if turn_uid==uid:
        rows.append([button("🟢 نوبت توعه","seven:turn")])
    else:
        rows.append([button(f"🎯 نوبت {display_name_by_id(turn_uid)}","seven:turn")])
    active=g["active_card"]
    can_play=any(seven_playable_with_override(c,g) for c in hand)
    if g.get("penalty",0)>0 and g.get("turn_uid")==uid:
        draw_color="🔴"
    else:
        draw_color="🔴" if can_play or seven_has_special(hand,"J") else "🟢"
    rows.append([button(f"{draw_color} 🎴 کشیدن",f"seven:draw:{g['id']}")])
    rows.append([button("🏳️ تسلیم شدن",f"seven:surrender:{g['id']}")])
    return keyboard(rows)


async def seven_send_private(g, uid, notice=""):
    hand=g["hands"].get(str(uid),[])
    text=(f"🃏 هفت خبیث\n\n🎴 کارت زمینه: {seven_card_text(g['active_card'])}\n"
          f"🎒 کارت‌های تو: {len(hand)}\n")
    if g.get("penalty",0):
        text+=f"🔥 جریمه فعال: {g['penalty']} کارت\n"
    if notice:
        text+=f"\n{notice}\n"
    try:
        mid=g.setdefault("private_messages",{}).get(str(uid))
        markup=seven_private_keyboard(g,uid)
        if mid:
            await bot.edit_message_text(chat_id=uid,message_id=mid,text=text,reply_markup=markup)
        else:
            sent=await bot.send_message(uid,text,reply_markup=markup)
            g["private_messages"][str(uid)]=sent.message_id
    except Exception:
        pass


async def seven_refresh_private(g, notice=""):
    for uid in list(g["players"]):
        await seven_send_private(g,uid,notice)


def seven_persist(g):
    state={k:v for k,v in g.items() if k not in {"lock","task"}}
    state["private_messages"] = g.get("private_messages",{})
    state["extra_private_messages"] = g.get("extra_private_messages",{})
    with db() as c:
        c.execute("UPDATE seven_games SET message_id=?,state_json=? WHERE id=?",(g.get("message_id",0),json.dumps(state,ensure_ascii=False),g["id"]))
        c.commit()


def seven_lobby_text(g, intro=""):
    lines=["🃏 لابی هفت خبیث", "", f"🔑 کد لابی: #{g['id']}", f"💎 شرط هر نفر: {format_coins(g['stake'])} آریور", f"👥 ظرفیت: {len(g['players'])}/{g['max_players']}", f"⏳ فرصت تکمیل: {SEVEN_WAIT_SECONDS//60} دقیقه", "", "👤 شرکت‌کنندگان:"]
    for i,uid in enumerate(g.get("players",[]),1):
        lines.append(f"{i}. {seven_player_name(uid)}")
    if intro:
        lines.extend(["", intro])
    return "\n".join(lines)


def seven_lobby_keyboard(g):
    rows=[[button("🎮 شرکت در بازی",f"seven:lobby:{g['id']}:join")]]
    rows.append([button("2 نفر",f"seven:lobby:{g['id']}:2"),button("3 نفر",f"seven:lobby:{g['id']}:3"),button("4 نفر",f"seven:lobby:{g['id']}:4")])
    rows.append([button("🔒 بستن لابی",f"seven:lobby:{g['id']}:close")])
    return keyboard(rows)


async def seven_close_lobby(g, reason="بسته شدن لابی"):
    if not g or g.get("status")!="waiting":
        return False
    participants=list(g.get("players",[]))
    stake=int(g.get("stake",0))
    gid=int(g.get("id",0))
    for uid in participants:
        add_coins(uid,stake)
        log_tx(uid,"seven_refund",stake,reason)
    g["status"]="refunded"
    with db() as c:
        c.execute("UPDATE seven_games SET status='refunded',state_json=? WHERE id=?",(json.dumps(g,ensure_ascii=False),gid))
        c.commit()
    t=SEVEN_TASKS.pop(gid,None)
    if t: t.cancel()
    t=SEVEN_COUNTDOWN_TASKS.pop(gid,None)
    if t: t.cancel()

    # Delete the group lobby message.
    try:
        if g.get("message_id"):
            await bot.delete_message(g["chat_id"],g["message_id"])
    except Exception:
        pass

    # Notify every participant privately after refund.
    text=f"🔒 لابی #{gid} بسته شد.\n\n❌ دلیل: لابی به ظرفیت تعیین‌شده نرسید و بسته شد.\n💎 هزینه ورودی ({format_coins(stake)} آریور) به کیف پول شما برگشت داده شد."
    for uid in participants:
        try:
            await bot.send_message(uid,text)
        except Exception:
            pass
    SEVEN_GAMES.pop(gid,None)
    return True


def seven_create(chat_id,creator_id,stake,max_players):
    if max_players not in (2,3,4) or stake<=0 or get_balance(creator_id)<stake:
        return None,"funds"
    add_coins(creator_id,-stake); log_tx(creator_id,"seven_lock",-stake,"هفت خبیث")
    now_ts=int(time.time())
    with db() as c:
        cur=c.execute("INSERT INTO seven_games(chat_id,creator_id,stake,max_players,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?)",(chat_id,creator_id,stake,max_players,"waiting",now_ts,now_ts+SEVEN_WAIT_SECONDS))
        gid=cur.lastrowid
        c.execute("INSERT INTO seven_players(game_id,user_id,joined_at,paid) VALUES(?,?,?,1)",(gid,creator_id,now_ts)); c.commit()
    g={"id":gid,"chat_id":chat_id,"message_id":0,"creator_id":creator_id,"stake":stake,"max_players":max_players,"status":"waiting","players":[creator_id],"hands":{},"center":[],"active_card":"","turn_index":0,"direction":1,"penalty":0,"pending_bonus":False,"deadline":0,"private_messages":{},"extra_private_messages":{},"missed_turns":{},"created_at":time.time(),"expires_at":time.time()+SEVEN_WAIT_SECONDS,"last_notice":""}
    SEVEN_GAMES[gid]=g
    return gid,"ok"


def seven_join(gid,uid):
    g=seven_get_game(gid)
    if not g or g.get("status")!="waiting": return None,"closed"
    if uid in g["players"]: return g,"self"
    if len(g["players"])>=g["max_players"]: return g,"full"
    if not get_balance(uid)>=g["stake"]: return g,"funds"
    add_coins(uid,-g["stake"]); log_tx(uid,"seven_lock",-g["stake"],"هفت خبیث")
    g["players"].append(uid)
    with db() as c:
        c.execute("INSERT INTO seven_players(game_id,user_id,joined_at,paid) VALUES(?,?,?,1)",(gid,uid,int(time.time())))
        c.commit()
    return g,"ok"


async def seven_finish_refund(g, reason="لغو بازی"):
    return await seven_close_lobby(g, reason)


def seven_start(g):
    n=len(g["players"]); each=seven_deal_count(n)
    deck=seven_make_deck()
    g["hands"]={str(uid):[] for uid in g["players"]}
    for _ in range(each):
        for uid in g["players"]:
            g["hands"][str(uid)].append(deck.pop())
    # Remaining stack is the center. One random center card becomes the initial active card.
    random_index=random.randrange(len(deck))
    g["active_card"]=deck.pop(random_index)
    g["center"]=deck
    g["turn_index"]=0
    g["direction"]=1
    g["penalty"]=0
    g["pending_bonus"]=False
    g["missed_turns"]={str(uid):0 for uid in g["players"]}
    g["paid_player_count"]=len(g["players"])
    g["all_players"]=list(g["players"])
    g["status"]="active"
    g["deadline"]=time.time()+SEVEN_TURN_SECONDS
    g["turn_uid"]=g["players"][0]
    seven_persist(g)


def seven_next_index(g,steps=1):
    n=len(g["players"])
    return (g["turn_index"] + g["direction"]*steps) % n


async def seven_cleanup_finished_game(g, winner_uid, reason="پایان بازی"):
    """Delete all bot messages belonging to the finished 7 Khabis game, then announce the winner in PV to every original participant."""
    if not g:
        return

    participants=list(g.get("all_players") or g.get("players") or [])

    # Stop timer/countdown tasks first.
    t=SEVEN_TASKS.pop(g.get("id"),None)
    if t:
        t.cancel()
    t=SEVEN_COUNTDOWN_TASKS.pop(g.get("id"),None)
    if t:
        t.cancel()

    # Delete the public group game message.
    try:
        if g.get("message_id"):
            await bot.delete_message(g["chat_id"], g["message_id"])
    except Exception:
        pass

    # Delete each participant's private game message.
    for uid in participants:
        mid=g.get("private_messages",{}).get(str(uid))
        if mid:
            try:
                await bot.delete_message(uid, mid)
            except Exception:
                pass
        for extra_mid in list(g.get("extra_private_messages",{}).get(str(uid),[]) or []):
            try:
                await bot.delete_message(uid, extra_mid)
            except Exception:
                pass

    # The winner announcement is the only remaining game-related PV message.
    winner_name=seven_player_name(winner_uid)
    text=f"🏆 بازی هفت خبیث تمام شد!\n\n🥇 برنده: {winner_name}\n🎉 تبریک! جایزه بازی به برنده پرداخت شد."
    for uid in participants:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
        except Exception:
            pass


async def seven_cleanup_game_messages(g):
    """Delete game messages when a game is cancelled/refunded."""
    if not g:
        return
    participants=list(g.get("all_players") or g.get("players") or [])
    try:
        if g.get("message_id"):
            await bot.delete_message(g["chat_id"], g["message_id"])
    except Exception:
        pass
    for uid in participants:
        mid=g.get("private_messages",{}).get(str(uid))
        if mid:
            try:
                await bot.delete_message(uid, mid)
            except Exception:
                pass
        for extra_mid in list(g.get("extra_private_messages",{}).get(str(uid),[]) or []):
            try:
                await bot.delete_message(uid, extra_mid)
            except Exception:
                pass


async def seven_finish_if_empty(g,uid):
    if g["hands"].get(str(uid),[]):
        return False
    pot=g["stake"]*int(g.get("paid_player_count",len(g["players"])))
    add_coins(uid,pot); log_tx(uid,"seven_win",pot,"هفت خبیث")
    for other in list(g.get("all_players") or g["players"]):
        record_game(other,"win" if other==uid else "loss",pot if other==uid else 0,"seven")
    g["status"]="finished"; g["winner_id"]=uid
    with db() as c:
        c.execute("UPDATE seven_games SET status='finished',state_json=? WHERE id=?",(json.dumps(g,ensure_ascii=False),g["id"])); c.commit()
    await seven_cleanup_finished_game(g,uid)
    SEVEN_GAMES.pop(g["id"],None)
    return True


def seven_active_player_count(g):
    return len(g.get("players",[]))


def seven_remove_player(g, uid, reason="حضور نداشتن"):
    players=g.get("players") or []
    if uid not in players:
        return False, None
    old_index=players.index(uid)
    was_turn=(uid==g.get("turn_uid"))
    players.pop(old_index)
    g.setdefault("hands",{}).pop(str(uid),None)
    g.setdefault("missed_turns",{}).pop(str(uid),None)
    if g.get("pending_jack_uid")==uid:
        g["pending_jack_uid"]=None
        g["pending_suit"]=None
        g["active_suit_override"]=None
    if g.get("pending_bonus"):
        g["pending_bonus"]=False
    if not players:
        g["status"]="finished"
        g["turn_uid"]=None
        g["turn_index"]=0
        g["deadline"]=0
        t=SEVEN_TASKS.pop(g.get("id"),None)
        if t and t is not asyncio.current_task(): t.cancel()
        t=SEVEN_COUNTDOWN_TASKS.pop(g.get("id"),None)
        if t and t is not asyncio.current_task(): t.cancel()
        return True, None
    turn_index=int(g.get("turn_index",0))
    if old_index < turn_index:
        turn_index-=1
    elif old_index == turn_index and was_turn:
        turn_index=turn_index % len(players)
    elif turn_index >= len(players):
        turn_index=0
    g["turn_index"]=turn_index
    g["turn_uid"]=players[turn_index]
    g["deadline"]=time.time()+SEVEN_TURN_SECONDS
    return True, g["turn_uid"]


async def seven_try_finish_after_elimination(g):
    if g.get("status")!="active":
        return None
    if len(g.get("players",[]))==1:
        winner=g["players"][0]
        pot=g["stake"]*len(g.get("players_before_finish",g["players"]))
        # The original number of paid players is stored separately when available.
        pot=g["stake"]*int(g.get("paid_player_count",len(g["players"])))
        add_coins(winner,pot); log_tx(winner,"seven_win",pot,"هفت خبیث")
        record_game(winner,"win",pot,"seven")
        g["status"]="finished"; g["winner_id"]=winner
        t=SEVEN_TASKS.pop(g["id"],None)
        if t: t.cancel()
        t=SEVEN_COUNTDOWN_TASKS.pop(g["id"],None)
        if t: t.cancel()
        with db() as c:
            c.execute("UPDATE seven_games SET status='finished',state_json=? WHERE id=?",(json.dumps(g,ensure_ascii=False),g["id"])); c.commit()
        # Message cleanup + PV-only winner announcement to all original participants.
        await seven_cleanup_finished_game(g,winner)
        SEVEN_GAMES.pop(g["id"],None)
        return winner
    return None


def seven_move_to_next(g,steps=1):
    players=g.get("players") or []
    if not players:
        g["turn_index"]=0
        g["turn_uid"]=None
        g["deadline"]=0
        return
    n=len(players)
    idx=int(g.get("turn_index",0))
    direction=int(g.get("direction",1) or 1)
    g["turn_index"]=(idx + direction*int(steps)) % n
    g["turn_uid"]=players[g["turn_index"]]
    g["deadline"]=time.time()+SEVEN_TURN_SECONDS


def seven_draw_one(g,uid,count=1):
    cards=[]
    for _ in range(count):
        if not g["center"]:
            # Rebuild from played cards is not needed: played cards are already the top of
            # the same center stack, so with the requested mechanics the center stays stocked.
            break
        card=g["center"].pop(0)
        g["hands"][str(uid)].append(card); cards.append(card)
    return cards


def seven_play_card(g,uid,index):
    if g.get("turn_uid")!=uid: return False,"turn",None
    hand=g["hands"].get(str(uid),[])
    if index<0 or index>=len(hand): return False,"card",None
    card=hand[index]
    active=g["active_card"]
    penalty=g.get("penalty",0)
    # During a 7 chain, another 7 can continue it even when suit/number does not match.
    if penalty>0:
        if seven_card_rank(card)!="7": return False,"penalty",None
    elif not seven_playable(card,active):
        return False,"notplayable",None
    hand.pop(index)
    g["center"].append(card)
    g["active_card"]=card
    rank=seven_card_rank(card)
    notice=f"🎴 {seven_card_text(card)} بازی شد."

    if rank=="8":
        g["pending_bonus"]=True
        # The 8 itself must be followed by a matching bonus card. Stay on same turn.
        valid_bonus=[c for c in hand if (seven_card_suit(c)==seven_card_suit(card) or seven_card_rank(c)==seven_card_rank(card))]
        if not valid_bonus:
            drawn=seven_draw_one(g,uid,1)
            g["pending_bonus"]=False
            seven_move_to_next(g)
            notice+=f"\n⚠️ کارت جایزه نداشتی؛ {len(drawn)} کارت کشیدی و نوبت رد شد."
        else:
            g["deadline"]=time.time()+SEVEN_TURN_SECONDS
            notice+="\n🎁 حالا باید یک کارت جایزه هم‌خال یا هم‌شماره بازی کنی."
        return True,"ok",notice

    if g.get("pending_bonus"):
        # A non-8 bonus completes the 8 chain.
        g["pending_bonus"]=False

    if rank=="A":
        seven_move_to_next(g,2)
        notice+="\n⏭️ آس: نوبت بازیکن بعدی رد شد."
    elif rank=="2":
        next_uid=g["players"][seven_next_index(g)]
        if hand:
            moved=hand.pop(random.randrange(len(hand)))
            g["hands"][str(next_uid)].append(moved)
            notice+=f"\n🎁 یک کارت تصادفی از دست زننده ۲ به {seven_player_name(next_uid)} داده شد."
        seven_move_to_next(g)
    elif rank=="7":
        g["penalty"] = penalty + 2
        seven_move_to_next(g)
        notice+=f"\n🔥 جریمه ۷ به {g['penalty']} کارت رسید؛ نفر بعد می‌تواند ۷ بازی کند یا با کشیدن، جریمه را بگیرد."
    elif rank=="10":
        g["direction"]*=-1
        seven_move_to_next(g)
        notice+=f"\n🔄 جهت بازی عوض شد."
    elif rank=="J":
        # Suit selection is handled by the separate callback; keep the turn on this player temporarily.
        g["pending_suit"] = None
        g["pending_jack_uid"] = uid
        g["deadline"]=time.time()+SEVEN_TURN_SECONDS
        notice+="\n🃏 جک بازی شد؛ خال جدید را انتخاب کن."
    else:
        seven_move_to_next(g)
    return True,"ok",notice


def seven_jack_choose(g,uid,suit):
    if g.get("pending_jack_uid")!=uid or suit not in SEVEN_SUITS: return False
    g["pending_jack_uid"]=None; g["pending_suit"]=suit
    # Store the chosen suit as a synthetic active card. It is not a physical card.
    g["active_suit_override"]=suit
    seven_move_to_next(g)
    return True


def seven_playable_with_override(card,g):
    override=g.get("active_suit_override")
    if override and not seven_is_joker(card):
        return seven_card_suit(card)==override or seven_card_rank(card)==seven_card_rank(g["active_card"])
    return seven_playable(card,g["active_card"])


async def seven_public_update(g,notice=""):
    if g.get("status") not in ("active","waiting"): return
    text=seven_state_text(g,notice)
    try:
        await bot.edit_message_text(chat_id=g["chat_id"],message_id=g["message_id"],text=text,reply_markup=seven_public_keyboard(g),parse_mode="HTML")
    except Exception:
        pass


def seven_load_game_from_db(gid):
    with db() as c:
        row=c.execute("SELECT id,chat_id,message_id,creator_id,stake,max_players,status,state_json,created_at,expires_at FROM seven_games WHERE id=?",(gid,)).fetchone()
    if not row or row[6] not in ("active","waiting"):
        return None
    try:
        state=json.loads(row[7] or "{}")
    except Exception:
        return None
    if not state:
        return None
    state["id"]=int(row[0]); state["chat_id"]=int(row[1]); state["message_id"]=int(row[2] or 0)
    state["creator_id"]=int(row[3]); state["stake"]=int(row[4]); state["max_players"]=int(row[5]); state["status"]=row[6]
    state["created_at"]=row[8]; state["expires_at"]=row[9]
    state.setdefault("private_messages",{}); state.setdefault("extra_private_messages",{}); state.setdefault("missed_turns",{}); state.setdefault("turn_token",0)
    SEVEN_GAMES[gid]=state
    return state


def seven_get_game(gid):
    return SEVEN_GAMES.get(gid) or seven_load_game_from_db(gid)


async def seven_turn_timer(gid,token):
    await asyncio.sleep(SEVEN_TURN_SECONDS)
    g=seven_get_game(gid)
    if not g or g.get("status")!="active" or int(g.get("turn_token",0))!=int(token): return
    lock=SEVEN_LOCKS.setdefault(gid,asyncio.Lock())
    async with lock:
        g=seven_get_game(gid)
        if not g or g.get("status")!="active" or int(g.get("turn_token",0))!=int(token): return
        if time.time() < float(g.get("deadline",0)):
            return
        uid=g["turn_uid"]
        missed=int(g.setdefault("missed_turns",{}).get(str(uid),0))+1
        g["missed_turns"][str(uid)]=missed

        if missed>=2:
            removed, next_uid=seven_remove_player(g,uid,"عدم حضور در دو نوبت")
            if not removed:
                return
            notice=f"🚫 {seven_player_name(uid)} به دلیل نزدن هیچ دکمه‌ای در دو نوبت پیاپی از بازی حذف شد."
            winner=await seven_try_finish_after_elimination(g)
            if winner:
                return
            if next_uid:
                notice+=f"\n➡️ نوبت {seven_player_name(next_uid)} شد."
            seven_persist(g)
            # Remove the eliminated player's stale private game message so old buttons cannot be used.
            try:
                mid=g.get("private_messages",{}).get(str(uid))
                if mid:
                    await bot.delete_message(uid,mid)
                g.get("private_messages",{}).pop(str(uid),None)
            except Exception:
                pass
            await seven_public_update(g,notice)
            await seven_refresh_private(g,notice)
            seven_schedule_timer(g)
            return

        # First timeout: automatic draw/penalty, then pass the turn.
        if g.get("pending_jack_uid")==uid:
            g["pending_jack_uid"]=None
            seven_draw_one(g,uid,1); seven_move_to_next(g)
            notice=f"⏰ {seven_player_name(uid)} در نوبت اول هیچ دکمه‌ای نزد؛ یک کارت کشید و نوبتش رد شد.\n➡️ نوبت {seven_player_name(g['turn_uid'])} شد.\n⚠️ یک عدم‌حضور ثبت شد؛ یک نوبت دیگر بدون اقدام باعث حذف می‌شود."
        elif g.get("pending_bonus"):
            g["pending_bonus"]=False; seven_draw_one(g,uid,1); seven_move_to_next(g)
            notice=f"⏰ {seven_player_name(uid)} در نوبت اول هیچ دکمه‌ای نزد؛ کارت جایزه نگرفت، یک کارت کشید و نوبتش رد شد.\n➡️ نوبت {seven_player_name(g['turn_uid'])} شد.\n⚠️ یک عدم‌حضور ثبت شد؛ یک نوبت دیگر بدون اقدام باعث حذف می‌شود."
        elif g.get("penalty",0)>0:
            count=g["penalty"]; drawn=seven_draw_one(g,uid,count); g["penalty"]=0; seven_move_to_next(g)
            notice=f"⏰ {seven_player_name(uid)} در نوبت اول هیچ دکمه‌ای نزد؛ جریمه {len(drawn)} کارت را گرفت و نوبتش رد شد.\n➡️ نوبت {seven_player_name(g['turn_uid'])} شد.\n⚠️ یک عدم‌حضور ثبت شد؛ یک نوبت دیگر بدون اقدام باعث حذف می‌شود."
        else:
            drawn=seven_draw_one(g,uid,1); seven_move_to_next(g)
            notice=f"⏰ {seven_player_name(uid)} در نوبت اول هیچ دکمه‌ای نزد؛ {len(drawn)} کارت خودکار کشید و نوبتش رد شد.\n➡️ نوبت {seven_player_name(g['turn_uid'])} شد.\n⚠️ یک عدم‌حضور ثبت شد؛ یک نوبت دیگر بدون اقدام باعث حذف می‌شود."
        seven_persist(g)
        if await seven_finish_if_empty(g,uid):
            return
        await seven_public_update(g,notice); await seven_refresh_private(g,notice)
        seven_schedule_timer(g)


async def seven_live_countdown(gid, token):
    """Update the visible 7 Khabis countdown every second without waiting for a button press."""
    last_left = None
    while True:
        g = SEVEN_GAMES.get(gid)
        if not g or g.get("status") != "active" or int(g.get("turn_token", 0)) != int(token):
            return

        left = max(0, int(g.get("deadline", time.time()) - time.time()))
        if left != last_left:
            # Public game message: update only its keyboard so the game log/text remains intact.
            try:
                await bot.edit_message_reply_markup(
                    chat_id=g["chat_id"],
                    message_id=g["message_id"],
                    reply_markup=seven_public_keyboard(g),
                )
            except Exception:
                pass

            # Every active player's existing private game message gets the same live timer.
            for uid in list(g.get("players", [])):
                try:
                    mid = g.get("private_messages", {}).get(str(uid))
                    if mid:
                        await bot.edit_message_reply_markup(
                            chat_id=uid,
                            message_id=mid,
                            reply_markup=seven_private_keyboard(g, uid),
                        )
                except Exception:
                    pass

            last_left = left

        if left <= 0:
            return
        await asyncio.sleep(1)


def seven_schedule_timer(g):
    g["turn_token"]=int(g.get("turn_token",0))+1
    token=g["turn_token"]

    old=SEVEN_TASKS.get(g["id"])
    if old and old is not asyncio.current_task() and not old.done():
        old.cancel()
    task=asyncio.create_task(seven_turn_timer(g["id"],token))
    SEVEN_TASKS[g["id"]]=task

    old_countdown=SEVEN_COUNTDOWN_TASKS.get(g["id"])
    if old_countdown:
        old_countdown.cancel()
    countdown_task=asyncio.create_task(seven_live_countdown(g["id"],token))
    SEVEN_COUNTDOWN_TASKS[g["id"]]=countdown_task


async def seven_start_after_lobby(g):
    participants=list(g.get("players",[]))
    mentions=" ".join(seven_player_name(uid) for uid in participants)
    seven_start(g)
    await seven_public_update(g,f"🚀 بازی شروع شد؛ نوبت بازیکن اول است.\n\n👥 شرکت‌کنندگان:\n{mentions}")
    await seven_refresh_private(g)
    seven_schedule_timer(g)


async def seven_lobby_expiry(gid):
    await asyncio.sleep(SEVEN_WAIT_SECONDS)
    g=SEVEN_GAMES.get(gid)
    if not g or g.get("status")!="waiting": return
    if len(g["players"])<g["max_players"]:
        await seven_finish_refund(g,"عدم تکمیل لابی هفت خبیث")

def display_name_by_id(user_id):
    try:
        row=get_user_record(user_id)
        if row:
            if row[1]: return "@"+row[1]
            if row[2]: return row[2]
    except Exception:
        pass
    return "بازیکن"

def mention_by_id(user_id):
    """منشن واقعی تلگرام بر اساس ID؛ بدون نیاز به username."""
    import html
    try:
        row=get_user_record(user_id)
        name=(row[2] if row and row[2] else None) or (row[1] if row and row[1] else None) or "بازیکن"
    except Exception:
        name="بازیکن"
    return f'<a href="tg://user?id={int(user_id)}">{html.escape(str(name))}</a>'

def get_user_record(user_id):
    with db() as c:
        return c.execute("SELECT id,username,full_name FROM users WHERE id=?", (user_id,)).fetchone()

def active_gifts():
    with db() as c:
        return c.execute("SELECT g.code,g.amount,g.mode,g.max_uses,COUNT(r.user_id) FROM gift_codes g LEFT JOIN gift_redemptions r ON r.code=g.code WHERE g.active=1 GROUP BY g.code,g.amount,g.mode,g.max_uses ORDER BY g.created_at DESC").fetchall()


def create_gift(code, amount, mode="multi", max_uses=0):
    mode = "single" if mode == "single" else "multi"
    max_uses = max(1, int(max_uses))
    with db() as c:
        try:
            c.execute("INSERT INTO gift_codes(code,amount,active,created_at,mode,max_uses) VALUES(?,?,1,?,?,?)", (code, amount, int(time.time()), mode, max_uses))
            c.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def expire_gift(code):
    with db() as c:
        cur = c.execute("UPDATE gift_codes SET active=0 WHERE code=? AND active=1", (code.strip(),))
        changed = cur.rowcount > 0
        c.commit()
        return changed


def redeem_gift(code, user_id):
    with db() as c:
        row = c.execute("SELECT amount,mode FROM gift_codes WHERE code=? AND active=1", (code.strip(),)).fetchone()
        if not row:
            return None, "invalid"
        amount = int(row[0])
        mode = row[1] or "multi"
        limit_row = c.execute("SELECT max_uses FROM gift_codes WHERE code=?", (code.strip(),)).fetchone()
        max_uses = int(limit_row[0] or 0) if limit_row else (1 if mode == "single" else 0)

        if c.execute("SELECT 1 FROM gift_redemptions WHERE code=? AND user_id=?", (code.strip(), user_id)).fetchone():
            return amount, "used"

        used_count = int(c.execute("SELECT COUNT(*) FROM gift_redemptions WHERE code=?", (code.strip(),)).fetchone()[0])
        if max_uses > 0 and used_count >= max_uses:
            c.execute("UPDATE gift_codes SET active=0 WHERE code=?", (code.strip(),))
            c.commit()
            return amount, "expired"

        c.execute("INSERT INTO coins(user_id,balance,last_ah) VALUES(?,?,0) ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance", (user_id, amount))
        c.execute("INSERT INTO gift_redemptions(code,user_id,redeemed_at) VALUES(?,?,?)", (code.strip(), user_id, int(time.time())))
        if max_uses > 0 and used_count + 1 >= max_uses:
            c.execute("UPDATE gift_codes SET active=0 WHERE code=?", (code.strip(),))
        c.commit()
        return amount, "ok"


def is_arsin_user(user):
    return bool(user and user.username and user.username.lower() == ARSIN_USERNAME.lower())


def arsin_user_id():
    value = get_setting("arsin_user_id")
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def is_arsin_id(user_id):
    aid = arsin_user_id()
    return bool(aid and int(user_id) == aid)


def is_arsin_target(user):
    return bool(user and (is_arsin_user(user) or is_arsin_id(user.id)))


def is_admin_user_id(user_id):
    if is_arsin_id(user_id):
        return True
    with db() as c:
        return c.execute("SELECT 1 FROM admin_users WHERE user_id=?", (int(user_id),)).fetchone() is not None


def is_admin_user(user):
    return bool(user and is_admin_user_id(user.id))


def add_admin_user(user, added_by=0):
    if not user or is_arsin_user(user):
        return False
    remember(user)
    with db() as c:
        c.execute("INSERT OR REPLACE INTO admin_users(user_id,username,full_name,added_at,added_by) VALUES(?,?,?,?,?)", (int(user.id), user.username or "", user.full_name or "", int(time.time()), int(added_by or 0)))
        c.commit()
    return True


ADMIN_SECTIONS = {
    "addcoins": "💎 افزایش موجودی",
    "removebalance": "➖ کسر موجودی",
    "prices": "🏷️ قیمت‌ها",
    "banned": "🚫 کاربران بن‌شده",
    "announce": "📢 اطلاعیه",
    "gift": "🎁 کد هدیه",
    "gifts": "📋 لیست کد هدیه",
    "links": "🔗 لینک‌های عضویت",
    "football": "⚽ مدیریت فوتبال",
    "help": "📚 راهنمای آرسین",
    "autoreply": "💬 پاسخ خودکار",
    "welcome": "👋 ولکام بات",
    "moderation": "🛡️ دستورات اخراج",
}

def admin_has_permission(user_id, section):
    if is_arsin_id(user_id):
        return True
    with db() as c:
        row = c.execute("SELECT enabled FROM admin_permissions WHERE user_id=? AND section=?", (int(user_id), section)).fetchone()
    return bool(row and int(row[0]) == 1)

def set_admin_permission(user_id, section, enabled):
    if is_arsin_id(user_id):
        return
    with db() as c:
        c.execute("INSERT INTO admin_permissions(user_id,section,enabled) VALUES(?,?,?) ON CONFLICT(user_id,section) DO UPDATE SET enabled=excluded.enabled", (int(user_id), section, 1 if enabled else 0))
        c.commit()

def remove_admin_user(user_id):
    if is_arsin_id(user_id):
        return False
    with db() as c:
        cur=c.execute("DELETE FROM admin_users WHERE user_id=?", (int(user_id),))
        c.execute("DELETE FROM admin_permissions WHERE user_id=?", (int(user_id),))
        c.commit()
    return cur.rowcount > 0

def admin_rows():
    with db() as c:
        return c.execute("SELECT user_id,username,full_name,added_at FROM admin_users ORDER BY added_at DESC").fetchall()

def admin_permission_text(uid):
    rows=[]
    for key,label in ADMIN_SECTIONS.items():
        rows.append(f"{'✅' if admin_has_permission(uid,key) else '❌'} {label}")
    return "🔐 دسترسی‌های این مدیر\n\n" + "\n".join(rows)

def admin_permission_keyboard(uid):
    rows=[]
    for key,label in ADMIN_SECTIONS.items():
        enabled=admin_has_permission(uid,key)
        rows.append([button(f"{'✅' if enabled else '❌'} {label}", f"adminperm:{uid}:{key}:{0 if enabled else 1}")])
    rows.append([button("🔙 لیست ادمین‌ها", "admin:admins")])
    rows.append([button("❌ بستن پنل", "menu:close")])
    return keyboard(rows)

def admin_list_keyboard():
    rows=[]
    for uid,username,full_name,added_at in admin_rows():
        label = f"@{username}" if username else (full_name or str(uid))
        rows.append([button(f"👑 {label}"[:60], f"admin:admin:{uid}")])
    rows.append([button("🔙 پنل مدیریت", "admin:panel")])
    rows.append([button("❌ بستن پنل", "menu:close")])
    return keyboard(rows)


# ================================================================
# GENERAL HELPERS
# ================================================================
# ----------------------------------------------------------------
# Menu navigation helpers
# ----------------------------------------------------------------
# The bot edits one Telegram message through the different menu stages.
# We therefore keep a small in-memory history per menu message so
# «🔙 برگشت» can restore the exact previous stage instead of always
# jumping to the main menu.
_MENU_HISTORY = {}

def _is_user_menu_back_button(btn):
    try:
        text = str(btn.text or "")
        data = str(btn.callback_data or "")
    except Exception:
        return False
    if not text.startswith("🔙"):
        return False
    # Do not touch admin/panel/game controls that have their own navigation.
    blocked = ("admin:", "ftadmin:", "lbr:")
    if data.startswith(blocked):
        return False
    return data.startswith(("user:", "property:", "football:", "combat:", "help:", "trade:", "menu:"))

def keyboard(rows):
    # Normalize user-facing menu navigation to the standard three controls:
    # row 1: 🔙 برگشت + 🏠 برگشت به منو
    # row 2: ❌ بستن منو
    # The share-location page is intentionally excluded: it only gets close.
    normalized = [list(r) for r in rows]
    had_close = any(str(getattr(b, "callback_data", "")) == "menu:close" for r in normalized for b in r)
    for r in normalized:
        r[:] = [b for b in r if str(getattr(b, "callback_data", "")) != "menu:close"]
    has_user_back = any(_is_user_menu_back_button(b) for r in normalized for b in r)
    has_share_page = any(str(getattr(b, "callback_data", "")) in ("menu:group", "menu:private") for r in normalized for b in r)
    if has_user_back and not has_share_page:
        cleaned = []
        for r in normalized:
            rr = [b for b in r if not _is_user_menu_back_button(b)]
            if rr:
                cleaned.append(rr)
        cleaned.append([button("🔙 برگشت", "menu:back"), button("🏠 برگشت به منو", "menu:home")])
        cleaned.append([button("❌ بستن منو", "menu:close")])
        normalized = cleaned
    elif had_close:
        normalized.append([button("❌ بستن منو", "menu:close")])
    return InlineKeyboardMarkup(inline_keyboard=normalized)


def button(text, data, style=None):
    kwargs = {"text": text, "callback_data": data}
    if style:
        kwargs["style"] = style
    return InlineKeyboardButton(**kwargs)


def alive(game):
    return [p for p in game["players"] if p["alive"]]


def get_player(game, user_id):
    return next((p for p in game["players"] if p["id"] == user_id), None)


def mafia_count(game):
    return sum(1 for p in alive(game) if p["role"] in MAFIA_ROLES)


def citizen_count(game):
    return sum(1 for p in alive(game) if p["role"] not in MAFIA_ROLES)


def side(role):
    return "mafia" if role in MAFIA_ROLES else "citizen"


def now():
    return time.time()


async def safe_delete(message):
    try:
        await message.delete()
    except Exception:
        pass


async def delete_message_id(chat_id, message_id):
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:
        pass


async def restrict_user(chat_id, user_id, can_speak=False):
    try:
        if can_speak:
            permissions = ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
        else:
            permissions = ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False,
            )
        await bot.restrict_chat_member(chat_id, user_id, permissions=permissions)
    except Exception:
        pass


async def allow_only_speaker(chat_id, game, user_id):
    for p in alive(game):
        await restrict_user(chat_id, p["id"], p["id"] == user_id)


async def allow_all_alive(chat_id, game):
    for p in alive(game):
        await restrict_user(chat_id, p["id"], True)


async def mute_all_alive(chat_id, game):
    for p in alive(game):
        await restrict_user(chat_id, p["id"], False)


def label_player(player):
    if player.get("username"):
        return f'@{player["username"]}'
    return ("@"+player["username"]) if player.get("username") else (player.get("full_name") or "بازیکن")

def display_user(game,user_id):
    p=get_player(game,user_id)
    return label_player(p) if p else 'بازیکن'


def check_win(game):
    m = mafia_count(game)
    c = citizen_count(game)
    if m == 0:
        game["winner"] = "شهروند"
        return True
    if m >= c:
        game["winner"] = "مافیا"
        return True
    return False


# ================================================================
# LINK / START REQUIREMENT
# ================================================================
def target_from_link(value):
    if not value:
        return None
    value = value.strip()
    if value.startswith("@"):
        return value
    match = re.match(r"https?://t\.me/([A-Za-z0-9_]+)(?:/.*)?$", value)
    if match:
        return "@" + match.group(1)
    return None


async def bot_is_admin(chat_id):
    """Return True only when this bot is an administrator/owner in the target chat."""
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id, me.id)
        return member.status in ("creator", "administrator")
    except Exception as exc:
        print(f"Bot admin check failed for chat {chat_id}: {exc}")
        return False


def member_is_joined(member):
    """Telegram membership states that count as being inside the chat."""
    status = getattr(member, "status", "")
    if status in ("creator", "administrator", "member"):
        return True
    # In a supergroup/channel a restricted member is still a member when
    # ChatMemberRestricted.is_member is True.
    if status == "restricted" and getattr(member, "is_member", False):
        return True
    return False


async def check_memberships(user_id):
    """Check both configured chats directly by Chat ID using Telegram Bot API.

    The bot must be an administrator in both chats. This avoids relying on
    private invite-link parsing, which Telegram does not expose to bots.
    """
    slots = configured_link_slots()
    if not slots:
        return True
    for slot in slots:
        key = "link" + str(slot)
        link = get_setting(key)
        chat_id = get_link_chat_id(str(slot))
        target = chat_id if chat_id is not None else target_from_link(link)
        if target is None:
            print(f"Membership check: {key} has no usable Chat ID")
            return False

        try:
            if not await bot_is_admin(target):
                print(f"Membership check: bot is NOT admin in {key} ({target})")
                return False

            member = await bot.get_chat_member(target, user_id)
            if member_is_joined(member):
                continue

            print(f"Membership check: user {user_id} is not a member of {key}; status={getattr(member, 'status', None)}")
            return False
        except Exception as exc:
            print(f"Membership check failed for {key} / {target}: {exc}")
            return False
    return True


async def membership_keyboard():
    rows = []
    for slot in configured_link_slots():
        key = "link" + str(slot)
        link = get_setting(key)
        if link:
            url = link_display_url(link)
            rows.append([InlineKeyboardButton(text=f"🔗 لینک عضویت {slot}", url=url)])
    rows.append([button("✅ عضو شدم", "check_membership")])
    return keyboard(rows)


async def send_join_buttons(chat_id, include_start=True):
    rows = []
    for slot in configured_link_slots():
        key = "link" + str(slot)
        link = get_setting(key)
        if link:
            url = link_display_url(link)
            rows.append([InlineKeyboardButton(text=f"🔗 عضویت در لینک {slot}", url=url)])
    if include_start:
        me = await bot.get_me()
        rows.append([InlineKeyboardButton(text="🤖 ورود به ربات / استارت", url=f"https://t.me/{me.username}?start=join_game")])
    rows.append([button("✅ عضو شدم", "check_membership")])
    await bot.send_message(chat_id, "🔒 ابتدا ربات را استارت کن و در هر دو لینک عضو شو.\n\n👇 سپس «عضو شدم» را بزن تا بررسی کنم.", reply_markup=keyboard(rows))


async def eligible_for_game(user_id):
    with db() as c:
        row = c.execute("SELECT started FROM users WHERE id=?", (user_id,)).fetchone()
    if not row or not row[0]:
        return False
    return await check_memberships(user_id)


# ================================================================
# ORIGINAL AI HANDLER
# ================================================================
async def get_ai_response(user_text, is_arsin):
    # OpenAI is disabled. Keep the bot fully functional without an API key.
    if "مافیا" in user_text:
        return "برای شروع بازی مافیا، داخل گروه «بازی مافیا» رو بفرست."
    if "سلام" in user_text:
        return "سلام! قابلیت هوش مصنوعی فعلاً غیرفعاله، ولی بخش بازی مافیا فعاله."
    return "فعلاً قابلیت گفت‌وگوی هوش مصنوعی غیرفعاله. برای اجرای بازی، «بازی مافیا» رو در گروه بفرست."


# ================================================================
# GAME STATE
# ================================================================
def new_game(message):
    return {
        "chat": message.chat.id,
        "creator": message.from_user.id,
        "phase": "waiting_start",
        "n": 5,
        "selected_roles": {},
        "players": [],
        "round": 0,
        "speaker_order": [],
        "speaker_index": 0,
        "speaker": None,
        "speaker_deadline": 0,
        "speaker_message": None,
        "challenge_message": None,
        "challenge_target": None,
        "challenge_from": None,
        "votes": {},
        "vote_target": None,
        "vote_message": None,
        "night_actions": {},
        "doctor_save": None,
        "lecter_save": None,
        "mafia_target": None,
        "kill_selector": None,
        "night_deaths": [],
        "night_log": [],
        "night_message": None,
        "silent_next_day": set(),
        "hard_used": {},
        "hard_immune": set(),
        "psy_used": {},
        "seller_used": set(),
        "eliminated_history": [],
        "winner": None,
        "setup_message_ids": set(),
        "message_ids": set(),
        "tasks": set(),
        "turn_token": 0,
    }


def selected_role_total(game):
    return sum(game["selected_roles"].values())


def selected_role_list(game):
    roles = []
    for label, role, amount in ROLE_BUTTONS:
        count = game["selected_roles"].get(role, 0)
        if amount == 5:
            if count:
                roles.extend([role] * count)
        else:
            roles.extend([role] * count)
    return roles


def role_selection_keyboard(game):
    rows = []
    # Every simple-citizen / simple-mafia slot is a separate button.
    # The first N slots of the same role are shown selected (green).
    seen_slots = {}
    for idx, (label, role, amount) in enumerate(ROLE_BUTTONS):
        slot_no = seen_slots.get(role, 0)
        seen_slots[role] = slot_no + 1
        selected_count = game["selected_roles"].get(role, 0)
        selected = slot_no < selected_count
        shown = ("🟢 " if selected else "") + label
        rows.append([button(shown, f"role:{idx}", "success" if selected else None)])
    rows.append([button("مرحله بعد", "role:next")])
    return keyboard(rows)


def setup_keyboard(game):
    return keyboard(
        [
            [
                button("➖", "setup:-"),
                button(f'تعداد پلیر: {game["n"]}', "setup:count"),
                button("➕", "setup:+"),
            ],
            [button("مرحله بعد", "setup:next")],
        ]
    )


def join_keyboard(game):
    return keyboard(
        [[button("پایه‌ام", "join:me"), button(f'تعداد: {len(game["players"])}/{game["n"]}', "join:count")]]
    )


def participant_text(game):
    role_lines = []
    for label, role, amount in ROLE_BUTTONS:
        count = game["selected_roles"].get(role, 0)
        if count:
            role_lines.append(f"{label} = {count}")

    participant_lines = [
        f'{i + 1}. {label_player(p)}' for i, p in enumerate(game["players"])
    ]
    if not participant_lines:
        participant_lines = ["هنوز کسی پایه نشده."]

    return (
        "کاربرانی که قصد بازی دارند روی «پایه‌ام» کلیک کنند.\n\n"
        f'تعداد پلیر: {game["n"]}\n\n'
        "نقش‌ها:\n"
        + "\n".join(role_lines)
        + "\n\nشرکت‌کننده‌ها:\n"
        + "\n".join(participant_lines)
    )


def validate_roles(game):
    total = selected_role_total(game)
    if total != game["n"]:
        return False, "تعداد نقش‌ها باید دقیقاً برابر تعداد پلیرها باشد."

    mafia = sum(
        count for role, count in game["selected_roles"].items() if role in MAFIA_ROLES
    )
    if mafia < 1:
        return False, "حداقل یک مافیا انتخاب کن. 🕵️‍♂️"

    # Both special mafia roles are allowed together.
    if game["selected_roles"].get("رییس مافیا", 0) > 1:
        return False, "رییس مافیا فقط یک بار قابل انتخاب است."
    if game["selected_roles"].get("دکتر لکتر", 0) > 1:
        return False, "دکتر لکتر فقط یک بار قابل انتخاب است."
    if game["selected_roles"].get("مافیا ساده", 0) > 5:
        return False, "حداکثر ۵ مافیا ساده قابل انتخاب است."
    if game["selected_roles"].get("شهروند", 0) > 5:
        return False, "حداکثر ۵ شهروند ساده قابل انتخاب است."

    return True, ""


# ================================================================
# SETUP
# ================================================================
async def start_game_setup(message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("بازی مافیا فقط داخل گروه قابل اجراست.")
        return

    if message.chat.id in games:
        await message.answer("یک بازی در این گروه در حال اجراست.")
        return

    game = new_game(message)
    games[message.chat.id] = game
    bump_mission(message.from_user.id,"trade",0)

    sent = await message.answer(
        "🎭 بدون آرسین می‌خواین بازی کنین؟ باشه، ولی دفعه آخرتون باشه 😤😂",
        reply_markup=keyboard(
            [[button("شروع بازی", "game:start"), button("لغو بازی", "game:cancel")]]
        ),
    )
    game["setup_message_ids"].add(sent.message_id)
    game["message_ids"].add(sent.message_id)
    asyncio.create_task(repeat_setup_message(message.chat.id))


async def repeat_setup_message(chat_id):
    while True:
        await asyncio.sleep(SETUP_REPEAT_SECONDS)
        game = games.get(chat_id)
        if not game or game["phase"] != "waiting_start":
            return
        try:
            sent = await send_bot_message(
                chat_id,
                "🎭 بدون آرسین می‌خواین بازی کنین؟ باشه، ولی دفعه آخرتون باشه 😤😂",
                reply_markup=keyboard(
                    [[button("شروع بازی", "game:start"), button("لغو بازی", "game:cancel")]]
                ),
            )
            game["setup_message_ids"].add(sent.message_id)
            game["message_ids"].add(sent.message_id)
        except Exception:
            return


async def cancel_game(chat_id):
    game = games.pop(chat_id, None)
    if not game:
        return
    for message_id in list(game["setup_message_ids"] | game.get("message_ids", set())):
        await delete_message_id(chat_id, message_id)
    for task in list(game["tasks"]):
        task.cancel()


async def creator_only(query, game):
    if query.from_user.id != game["creator"]:
        await query.answer("فقط سازنده بازی می‌تواند این بخش را کنترل کند.", show_alert=True)
        return False
    return True


@dp.callback_query(F.data == "game:cancel")
async def callback_cancel(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if game and not await creator_only(query, game):
        return
    await cancel_game(query.message.chat.id)
    await query.answer()


@dp.callback_query(F.data == "game:start")
async def callback_start(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game:
        return
    if not await creator_only(query, game):
        return
    game["phase"] = "setup"
    await query.message.edit_text("👥 تعداد پلیرها را انتخاب کنید:", reply_markup=setup_keyboard(game))
    await query.answer()


@dp.callback_query(F.data.startswith("setup:"))
async def callback_setup(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game["phase"] != "setup":
        return
    if not await creator_only(query, game):
        return

    action = query.data.split(":", 1)[1]
    if action == "+":
        game["n"] = min(MAX_PLAYERS, game["n"] + 1)
    elif action == "-":
        game["n"] = max(MIN_PLAYERS, game["n"] - 1)
    elif action == "next":
        game["selected_roles"] = {}
        game["phase"] = "roles"
        await query.message.edit_text("🎭 نقش‌های بازی را انتخاب کنید", reply_markup=role_selection_keyboard(game))
        await query.answer()
        return

    await query.message.edit_reply_markup(reply_markup=setup_keyboard(game))
    await query.answer()


@dp.callback_query(F.data.startswith("role:"))
async def callback_role(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game["phase"] != "roles":
        return
    if not await creator_only(query, game):
        return

    value = query.data.split(":", 1)[1]
    if value == "next":
        ok, error = validate_roles(game)
        if not ok:
            await query.answer(error, show_alert=True)
            return
        game["selected"] = selected_role_list(game)
        game["players"] = []
        game["phase"] = "join"
        await query.message.edit_text(participant_text(game), reply_markup=join_keyboard(game))
        await query.answer()
        return

    index = int(value)
    _, role, _ = ROLE_BUTTONS[index]

    # Each button represents exactly one slot. For the five simple-citizen
    # and five simple-mafia buttons, pressing a slot toggles one player.
    # This means there are literally 5 separate buttons for each role.
    seen_slots = {}
    slot_no = 0
    for i, (_, r, _) in enumerate(ROLE_BUTTONS):
        if i == index:
            slot_no = seen_slots.get(r, 0)
            break
        seen_slots[r] = seen_slots.get(r, 0) + 1

    current = game["selected_roles"].get(role, 0)
    selected = slot_no < current

    if selected:
        # Remove this slot and shift later selected slots left.
        game["selected_roles"][role] = current - 1
        if game["selected_roles"][role] <= 0:
            game["selected_roles"].pop(role, None)
    else:
        if selected_role_total(game) + 1 > game["n"]:
            await query.answer("تعداد نقش‌ها کامل شده.", show_alert=True)
            return
        max_slots = sum(1 for _, r, _ in ROLE_BUTTONS if r == role)
        if current >= max_slots:
            await query.answer("ظرفیت این نقش کامل شده.", show_alert=True)
            return
        game["selected_roles"][role] = current + 1

    await query.message.edit_reply_markup(reply_markup=role_selection_keyboard(game))
    await query.answer()


@dp.callback_query(F.data == "join:count")
async def callback_join_count(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if game:
        await query.answer(f'{len(game["players"])}/{game["n"]}', show_alert=True)


@dp.callback_query(F.data == "join:me")
async def callback_join(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game["phase"] != "join":
        return

    if any(p["id"] == query.from_user.id for p in game["players"]):
        await query.answer("قبلاً پایه شدی.", show_alert=True)
        return
    if len(game["players"]) >= game["n"]:
        await query.answer("ظرفیت کامل است.", show_alert=True)
        return

    if not await eligible_for_game(query.from_user.id):
        await query.answer("❌ ابتدا ربات را استارت کن و داخل هر دو لینک عضو شو.", show_alert=True)
        await send_join_buttons(query.message.chat.id, include_start=True)
        return

    game["players"].append(
        {
            "id": query.from_user.id,
            "username": query.from_user.username or "",
            "role": None,
            "alive": True,
            "reason": "",
        }
    )

    await query.message.edit_text(participant_text(game), reply_markup=join_keyboard(game))
    await query.answer("پایه شدی")

    if len(game["players"]) == game["n"]:
        await distribute_roles(query.message.chat.id)


# ================================================================
# ROLE DELIVERY
# ================================================================
async def distribute_roles(chat_id):
    game = games.get(chat_id)
    if not game or game.get("phase") != "join":
        return

    game["phase"] = "rolesent"
    roles = game["selected"][:]
    random.shuffle(roles)

    for player in game["players"]:
        role = roles.pop()
        player["role"] = role
        try:
            await send_bot_message(
                player["id"],
                f"🎭 نقش شما:\n{role}\n\nنقشت را برای کسی نفرست.",
            )
        except Exception:
            # If a user cannot receive the role DM, remove them from the game.
            player["alive"] = False
            player["reason"] = "نتوانست نقش را در پیوی دریافت کند"

    sent=await send_bot_message(chat_id,"🎭 نقش‌ها به پیوی ارسال شد. ⏳ تا ۲ دقیقه دیگر بازی شروع می‌شود. 🌙",reply_markup=keyboard([[timer_button(ROLE_DM_SECONDS,"زمان شروع")]]))
    t=asyncio.create_task(countdown_task(chat_id,sent.message_id,now()+ROLE_DM_SECONDS,"rolesent","زمان شروع")); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
    await asyncio.sleep(ROLE_DM_SECONDS)

    if chat_id in games:
        await start_day(chat_id)


# ================================================================
# LIVE COUNTDOWN
# ================================================================
def timer_button(seconds,label="زمان"):
    return button(f"⏳ {label}: {max(0,int(seconds))} ثانیه باقی‌مانده", "timer:noop")

async def countdown_task(chat_id,message_id,deadline,phase,label,base_rows=None):
    last=-1
    while True:
        game=games.get(chat_id)
        if not game or game.get("phase")!=phase: return
        left=max(0,int(deadline-now()))
        if left!=last:
            try:
                rows=list(base_rows or [])
                rows.append([timer_button(left,label)])
                await bot.edit_message_reply_markup(chat_id,message_id,reply_markup=keyboard(rows))
            except Exception: pass
            last=left
        if left<=0:return
        await asyncio.sleep(1)

@dp.callback_query(F.data=="timer:noop")
async def timer_noop(query:CallbackQuery): await query.answer("⏳ شمارش زمان زنده است.")

# ================================================================
# DAY / SPEAKING
# ================================================================
async def start_day(chat_id):
    game = games.get(chat_id)
    if not game:
        return
    if game.get("phase") == "day" and game.get("speaker") is not None:
        return
    if check_win(game):
        await finish_game(chat_id)
        return

    game["phase"] = "day"
    game["round"] += 1
    game["speaker_order"] = [p["id"] for p in alive(game)]
    random.shuffle(game["speaker_order"])
    game["speaker_index"] = 0
    await next_speaker(chat_id)


async def next_speaker(chat_id):
    game = games.get(chat_id)
    if not game:
        return
    if check_win(game):
        await finish_game(chat_id)
        return

    await delete_message_id(chat_id, game.get("speaker_message"))
    game["speaker_message"] = None

    game["turn_token"] += 1
    turn_token = game["turn_token"]
    while game["speaker_index"] < len(game["speaker_order"]):
        user_id = game["speaker_order"][game["speaker_index"]]
        game["speaker_index"] += 1
        player = get_player(game, user_id)
        if not player or not player["alive"]:
            continue
        if user_id in game["silent_next_day"]:
            continue

        game["speaker"] = user_id
        game["speaker_deadline"] = now() + SPEAK_SECONDS
        await allow_only_speaker(chat_id, game, user_id)
        sent = await send_bot_message(
            chat_id,
            f"🎤 نوبت صحبت {display_user(game,user_id)} است! 🗣️\n⏱️ {SPEAK_SECONDS} ثانیه فرصت داری.",
            reply_markup=keyboard([[button("⚔️ چالش", f"challenge:{user_id}"),button("⏭️ رد صحبت", f"skip:{user_id}")],[timer_button(SPEAK_SECONDS,"زمان صحبت")]]),
        )
        game["speaker_message"] = sent.message_id
        t=asyncio.create_task(speaker_timer(chat_id,user_id,SPEAK_SECONDS,turn_token)); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
        t=asyncio.create_task(countdown_task(chat_id,sent.message_id,game["speaker_deadline"],"day","زمان صحبت",[[button("⚔️ چالش",f"challenge:{user_id}"),button("⏭️ رد صحبت",f"skip:{user_id}")]])); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
        return

    await vote_round(chat_id)


async def speaker_timer(chat_id, user_id, seconds, turn_token):
    await asyncio.sleep(seconds)
    game = games.get(chat_id)
    if game and game.get("phase") == "day" and game.get("speaker") == user_id and game.get("turn_token") == turn_token:
        game["speaker"] = None
        await delete_message_id(chat_id, game.get("speaker_message"))
        game["speaker_message"] = None
        await next_speaker(chat_id)


@dp.callback_query(F.data.startswith("challenge:"))
async def callback_challenge(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game["phase"] != "day":
        return

    target = int(query.data.split(":", 1)[1])
    challenger = query.from_user.id
    if game.get("speaker") != target:
        await query.answer("⏰ این نوبت تمام شده است.", show_alert=True)
        return
    if not get_player(game, challenger) or not get_player(game, challenger)["alive"]:
        await query.answer("💀 شما زنده نیستید.", show_alert=True)
        return
    if challenger == target:
        await query.answer("خودت نمی‌تونی خودت رو چالش کنی.", show_alert=True)
        return

    sent = await send_bot_message(
        query.message.chat.id,
        f"{display_name_by_id(challenger)} چالش می‌خواد؛ قبول می‌کنی؟",
        reply_markup=keyboard(
            [
                [
                    button("اره", f"challenge_yes:{challenger}:{target}"),
                    button("نه", f"challenge_no:{challenger}:{target}"),
                ]
            ]
        ),
    )
    game["challenge_message"] = sent.message_id
    game["challenge_from"] = challenger
    game["challenge_target"] = target
    await query.answer()


@dp.callback_query(F.data.startswith("challenge_yes:"))
async def callback_challenge_yes(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game["phase"] != "day":
        return

    _, challenger, target = query.data.split(":")
    challenger = int(challenger)
    target = int(target)
    # IMPORTANT: the challenger does NOT accept the challenge.
    # Only the player whose turn it currently is (the challenged speaker)
    # can press "اره" or "نه".
    if query.from_user.id != target or game.get("speaker") != target:
        await query.answer("فقط بازیکنی که الان نوبت صحبتش است می‌تواند چالش را قبول یا رد کند.", show_alert=True)
        return

    await delete_message_id(query.message.chat.id, game.get("challenge_message"))
    game["challenge_message"] = None
    game["speaker"] = target
    game["turn_token"] += 1
    challenge_token = game["turn_token"]
    game["speaker_deadline"] = now() + CHALLENGE_SECONDS
    await allow_only_speaker(query.message.chat.id, game, target)
    sent=await send_bot_message(query.message.chat.id,f"⚔️ نوبت چالش {display_user(game,target)} است! 🗣️\n⏱️ {CHALLENGE_SECONDS} ثانیه فرصت داری.",reply_markup=keyboard([[timer_button(CHALLENGE_SECONDS,"زمان چالش")]]))
    game["speaker_message"]=sent.message_id
    t=asyncio.create_task(speaker_timer(query.message.chat.id,target,CHALLENGE_SECONDS,challenge_token)); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
    t=asyncio.create_task(countdown_task(query.message.chat.id,sent.message_id,game["speaker_deadline"],"day","زمان چالش")); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
    await query.answer()


@dp.callback_query(F.data.startswith("challenge_no:"))
async def callback_challenge_no(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game:
        return

    _, challenger, target = query.data.split(":")
    if query.from_user.id != int(target) or game.get("speaker") != int(target):
        await query.answer("فقط بازیکنی که الان نوبت صحبتش است می‌تواند چالش را قبول یا رد کند.", show_alert=True)
        return

    await delete_message_id(query.message.chat.id, game.get("challenge_message"))
    game["challenge_message"] = None
    await query.answer("❌ چالش رد شد.")


@dp.callback_query(F.data.startswith("skip:"))
async def callback_skip(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game.get("speaker") != int(query.data.split(":", 1)[1]):
        return
    await query.answer("⏭️ صحبت رد شد.")
    await delete_message_id(query.message.chat.id, game.get("speaker_message"))
    game["speaker_message"] = None
    game["speaker"] = None
    await next_speaker(query.message.chat.id)


# ================================================================
# VOTING
# ================================================================
def vote_threshold(game):
    return max(1, (len(alive(game)) + 1) // 2)


async def vote_round(chat_id):
    game = games.get(chat_id)
    if not game:
        return

    await allow_all_alive(chat_id, game)
    game["phase"] = "vote"

    for target_player in list(alive(game)):
        if not target_player["alive"]:
            continue

        game["vote_target"] = target_player["id"]
        game["votes"] = {}
        threshold = vote_threshold(game)
        sent = await send_bot_message(
            chat_id,
            f'🗳️ رای‌گیری برای {display_user(game,target_player["id"])}\n🎯 حد نصاب: {threshold}',
            reply_markup=keyboard(
                [
                    [button("🗳️ رای", f"vote:{target_player['id']}")],
                    [timer_button(VOTE_SECONDS,"زمان رای")]
                ]
            ),
        )
        game["vote_message"] = sent.message_id
        t=asyncio.create_task(countdown_task(chat_id,sent.message_id,now()+VOTE_SECONDS,"vote","زمان رای",[[button("🗳️ رای",f"vote:{target_player['id']}")]])); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
        await asyncio.sleep(VOTE_SECONDS)
        await safe_delete(sent)

        if sum(1 for value in game["votes"].values() if value == target_player["id"]) >= threshold:
            await defense_phase(chat_id, target_player["id"])
            return

    await night_phase(chat_id)


@dp.callback_query(F.data.startswith("vote:"))
async def callback_vote(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game["phase"] != "vote":
        return

    voter = get_player(game, query.from_user.id)
    if not voter or not voter["alive"]:
        await query.answer("💀 شما زنده نیستید.", show_alert=True)
        return

    target = int(query.data.split(":", 1)[1])
    if target != game.get("vote_target"):
        await query.answer("این رأی مربوط به مرحله فعلی نیست.", show_alert=True)
        return

    game["votes"][query.from_user.id] = target
    count = sum(1 for value in game["votes"].values() if value == target)
    try:
        await query.message.edit_reply_markup(
            reply_markup=keyboard(
                [
                    [
                        button("رای", f"vote:{target}"),
                        button(f"تعداد رای: {count}", f"vote_count:{target}"),
                    ]
                ]
            )
        )
    except Exception:
        pass
    await query.answer("🗳️ رای ثبت شد")


@dp.callback_query(F.data.startswith("vote_count:"))
async def callback_vote_count(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if game:
        target = int(query.data.split(":", 1)[1])
        count = sum(1 for value in game["votes"].values() if value == target)
        await query.answer(f"تعداد رای: {count}", show_alert=True)


async def defense_phase(chat_id, user_id):
    game = games.get(chat_id)
    if not game:
        return
    target = get_player(game, user_id)
    if not target or not target["alive"]:
        await night_phase(chat_id)
        return

    game["phase"] = "defense"
    game["speaker"] = user_id
    game["speaker_deadline"] = now()+DEFENSE_SECONDS
    await allow_only_speaker(chat_id, game, user_id)
    sent=await send_bot_message(chat_id,f"🛡️ {display_user(game,user_id)} به دفاع رفت! 🎤\n⏱️ {DEFENSE_SECONDS} ثانیه فرصت داری.",reply_markup=keyboard([[button("⏭️ رد دفاع",f"defense_skip:{user_id}")],[timer_button(DEFENSE_SECONDS,"زمان دفاع")]]))
    game["defense_message"]=sent.message_id
    t=asyncio.create_task(defense_timer(chat_id,user_id)); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
    t=asyncio.create_task(countdown_task(chat_id,sent.message_id,game["speaker_deadline"],"defense","زمان دفاع",[[button("⏭️ رد دفاع",f"defense_skip:{user_id}")]])); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)

async def defense_timer(chat_id,user_id):
    await asyncio.sleep(DEFENSE_SECONDS)
    game=games.get(chat_id)
    if game and game.get("phase")=="defense" and game.get("speaker")==user_id:
        await delete_message_id(chat_id,game.get("defense_message")); game["defense_message"]=None
        await final_vote(chat_id,user_id)

@dp.callback_query(F.data.startswith("defense_skip:"))
async def defense_skip(query:CallbackQuery):
    game=games.get(query.message.chat.id)
    if not game or game.get("phase")!="defense": return
    uid=int(query.data.split(":",1)[1])
    if query.from_user.id!=uid:
        await query.answer("❌ فقط خود فردِ در دفاع می‌تواند دفاعش را رد کند.",show_alert=True); return
    await query.answer("⏭️ دفاع رد شد.")
    await delete_message_id(query.message.chat.id,game.get("defense_message")); game["defense_message"]=None
    await final_vote(query.message.chat.id,uid)


async def final_vote(chat_id, user_id):
    game = games.get(chat_id)
    if not game:
        return

    game["phase"] = "final_vote"
    game["vote_target"] = user_id
    game["votes"] = {}
    await allow_all_alive(chat_id, game)

    threshold = vote_threshold(game)
    sent = await send_bot_message(
        chat_id,
        f"🗳️ رای نهایی برای {display_user(game,user_id)}\n🎯 حد نصاب: {threshold}",
        reply_markup=keyboard(
            [
                [
                    button("🗳️ رای", f"final_vote:{user_id}"),
                    button("🔢 تعداد رای: 0", f"final_vote_count:{user_id}"),
                ]
            ]
        ),
    )
    game["vote_message"] = sent.message_id
    t=asyncio.create_task(countdown_task(chat_id,sent.message_id,now()+VOTE_SECONDS,"final_vote","زمان رای نهایی",[[button("🗳️ رای",f"final_vote:{user_id}")]])); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
    await asyncio.sleep(VOTE_SECONDS)
    await safe_delete(sent)

    count = sum(1 for value in game["votes"].values() if value == user_id)
    if count >= threshold:
        await eliminate_player(chat_id, user_id, "اخراج با رای")

    await night_phase(chat_id)


@dp.callback_query(F.data.startswith("final_vote:"))
async def callback_final_vote(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if not game or game["phase"] != "final_vote":
        return

    voter = get_player(game, query.from_user.id)
    if not voter or not voter["alive"]:
        await query.answer("💀 شما زنده نیستید.", show_alert=True)
        return

    target = int(query.data.split(":", 1)[1])
    if target != game.get("vote_target"):
        await query.answer("این رأی مربوط به مرحله فعلی نیست.", show_alert=True)
        return

    game["votes"][query.from_user.id] = target
    count = sum(1 for value in game["votes"].values() if value == target)
    try:
        await query.message.edit_reply_markup(
            reply_markup=keyboard(
                [
                    [
                        button("رای", f"final_vote:{target}"),
                        button(f"تعداد رای: {count}", f"final_vote_count:{target}"),
                    ]
                ]
            )
        )
    except Exception:
        pass
    await query.answer("🗳️ رای ثبت شد")


@dp.callback_query(F.data.startswith("final_vote_count:"))
async def callback_final_vote_count(query: CallbackQuery):
    game = games.get(query.message.chat.id)
    if game:
        target = int(query.data.split(":", 1)[1])
        count = sum(1 for value in game["votes"].values() if value == target)
        await query.answer(f"تعداد رای: {count}", show_alert=True)


# ================================================================
# NIGHT TARGET KEYBOARDS
# ================================================================
def target_keyboard(game, action, *, mafia_only=False, allow_none=False, exclude_self=None):
    rows = []
    for p in alive(game):
        if exclude_self is not None and p["id"] == exclude_self:
            continue
        if is_arsin_id(p["id"]):
            continue
        if mafia_only and p["role"] not in MAFIA_ROLES:
            continue
        rows.append([button(f"👤 {label_player(p)}", f"night:{action}:{p['id']}")])
    if allow_none:
        rows.append([button("⏭️ انتخاب نمی‌کنم", f"night:{action}:none")])
    return keyboard(rows)


async def night_phase(chat_id):
    game = games.get(chat_id)
    if not game:
        return
    if game.get("phase") == "night":
        return
    if check_win(game):
        await finish_game(chat_id)
        return

    game["phase"] = "night"
    game["night_actions"] = {}
    game["doctor_save"] = None
    game["lecter_save"] = None
    game["mafia_target"] = None
    game["kill_selector"] = None
    game["night_deaths"] = []
    game["night_log"] = []

    await mute_all_alive(chat_id, game)
    night_message = await send_bot_message(chat_id,"🌙 شب شد! بازیکنان نقش‌دار به پیوی ربات بیان. 🤖\n🚫 شهروندهای ساده نیاز به اقدام ندارند.",reply_markup=keyboard([[timer_button(NIGHT_SECONDS,"زمان شب")]]))
    game["night_message"] = night_message.message_id
    t=asyncio.create_task(countdown_task(chat_id,night_message.message_id,now()+NIGHT_SECONDS,"night","زمان شب")); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)

    # Choose the current mafia kill selector.
    boss = next((p for p in alive(game) if p["role"] == "رییس مافیا"), None)
    if boss:
        game["kill_selector"] = boss["id"]
    else:
        lecter = next((p for p in alive(game) if p["role"] == "دکتر لکتر"), None)
        if lecter:
            game["kill_selector"] = lecter["id"]
        else:
            simple_mafia = next((p for p in alive(game) if p["role"] == "مافیا ساده"), None)
            if simple_mafia:
                game["kill_selector"] = simple_mafia["id"]

    for p in alive(game):
        role = p["role"]
        try:
            if role == "دکتر":
                await send_bot_message(
                    p["id"],
                    "💉 لطفاً یک پلیر را برای سیو شب انتخاب کنید. 🛡️",
                    reply_markup=target_keyboard(game, "doctor", exclude_self=p["id"]),
                )
            elif role == "کاراگاه":
                await send_bot_message(
                    p["id"],
                    "🔎 یک کاربر را برای استعلام شب انتخاب کنید. 🕵️",
                    reply_markup=target_keyboard(game, "detective", exclude_self=p["id"]),
                )
            elif role == "تک تیر انداز":
                await send_bot_message(
                    p["id"],
                    "🎯 یک کاربر را برای شلیک انتخاب کنید؛ اگر شهروند باشد خودتان از بازی خارج می‌شوید. ⚠️",
                    reply_markup=target_keyboard(game, "sniper", allow_none=True, exclude_self=p["id"]),
                )
            elif role == "جان سخت":
                used = game["hard_used"].get(p["id"], 0)
                await send_bot_message(
                    p["id"],
                    f"🧠 آیا استعلام میگیری؟ (حداکثر ۲ بار)\nاستفاده شده: {used}/2",
                    reply_markup=keyboard(
                        [
                            [
                                button("استعلام میگیرم", "night:hard:yes"),
                                button("استعلام نمیگیرم", "night:hard:no"),
                            ]
                        ]
                    ),
                )
            elif role == "روان پزشک":
                used = game["psy_used"].get(p["id"], 0)
                await send_bot_message(
                    p["id"],
                    f"یک کاربر را برای سکوت انتخاب کنید (تنها ۲ بار)\nاستفاده شده: {used}/2",
                    reply_markup=target_keyboard(game, "psycho", allow_none=True, exclude_self=p["id"]),
                )
            elif role == "فروشنده":
                if p["id"] in game["seller_used"]:
                    await send_bot_message(p["id"], "🛒 فروشنده قبلاً از قابلیت خود استفاده کرده است. ⛔")
                else:
                    await send_bot_message(
                        p["id"],
                        "🛒 یک کاربر را برای فروش نقش انتخاب کنید (تنها یک بار). 🎭",
                        reply_markup=target_keyboard(game, "seller", allow_none=True, exclude_self=p["id"]),
                    )
            elif role == "رییس مافیا":
                await send_bot_message(
                    p["id"],
                    "🔪 یک کاربر را برای کشته شب انتخاب کنید. 🌙",
                    reply_markup=target_keyboard(game, "boss", exclude_self=p["id"]),
                )
            elif role == "دکتر لکتر":
                await send_bot_message(
                    p["id"],
                    "🛡️ یکی از مافیاها را برای سیو انتخاب کنید. 🩺",
                    reply_markup=target_keyboard(game, "lector_save", mafia_only=True, exclude_self=p["id"]),
                )
                # If the boss is dead, Lecter is also the kill selector.
                if game["kill_selector"] == p["id"]:
                    await send_bot_message(
                        p["id"],
                        "👑 رییس مافیا داخل بازی نیست؛ شما مسئول انتخاب کشته شب هستید. 🔪",
                        reply_markup=target_keyboard(game, "kill", exclude_self=p["id"]),
                    )
            elif role == "مافیا ساده":
                if game["kill_selector"] == p["id"]:
                    await send_bot_message(
                        p["id"],
                        "👑 رییس مافیا و دکتر لکتر داخل بازی نیستند؛ شما مسئول انتخاب کشته شب هستید. 🔪",
                        reply_markup=target_keyboard(game, "kill", exclude_self=p["id"]),
                    )
                else:
                    await send_bot_message(
                        p["id"],
                        "💬 یک کاربر را برای مشورت به مسئول کشته شب پیشنهاد بده. 🔪",
                        reply_markup=target_keyboard(game, "mafia_suggest", exclude_self=p["id"]),
                    )
        except Exception:
            pass

    await asyncio.sleep(NIGHT_SECONDS)
    game = games.get(chat_id)
    if game and game["phase"] == "night":
        await resolve_night(chat_id)


@dp.callback_query(F.data.startswith("night:"))
async def callback_night(query: CallbackQuery):
    game = next(
        (
            g
            for g in games.values()
            if g["phase"] == "night"
            and get_player(g, query.from_user.id)
            and get_player(g, query.from_user.id)["alive"]
        ),
        None,
    )
    if not game:
        await query.answer("بازی شب فعالی نیست.", show_alert=True)
        return

    player = get_player(game, query.from_user.id)
    parts = query.data.split(":")
    action = parts[1]
    raw_target = parts[2]
    target_id = None if raw_target == "none" else (None if raw_target in ("yes", "no") else int(raw_target))

    # Doctor
    if action == "doctor":
        game["doctor_save"] = target_id
        game["night_actions"][player["id"]] = {"action": "doctor", "target": target_id}
        await query.message.edit_text(f"🛡️ شما {display_user(game,target_id)} را برای سیو انتخاب کردید. ✅")
        await query.answer()
        return

    # Detective
    if action == "detective":
        target = get_player(game, target_id)
        if not target:
            await query.answer("❌ کاربر نامعتبر است. 👤", show_alert=True)
            return
        result = "شهروند" if target["role"] == "رییس مافیا" or side(target["role"]) == "citizen" else "مافیا"
        game["night_actions"][player["id"]] = {"action": "detective", "target": target_id}
        await query.message.edit_text(f"🔎 نتیجه استعلام: {display_user(game,target_id)} = {result} 🕵️")
        await query.answer()
        return

    # Sniper
    if action == "sniper":
        game["night_actions"][player["id"]] = {"action": "sniper", "target": target_id}
        await query.message.edit_text("✅ انتخاب شما ثبت شد. 🎯")
        await query.answer()
        return

    # Tough
    if action == "hard":
        used = game["hard_used"].get(player["id"], 0)
        if raw_target == "yes":
            if used >= 2:
                await query.answer("استعلام شما تمام شده.", show_alert=True)
                return
            game["hard_used"][player["id"]] = used + 1
            game["night_actions"][player["id"]] = {"action": "hard", "used": used + 1}
            report = "\n".join(
                f'{label_player(p)}: {p["role"]} 🎭' for p in game["players"] if not p["alive"]
            ) or "هنوز بازیکن حذف‌شده‌ای وجود ندارد."
            await query.message.edit_text("📋 گزارش بازیکن‌های حذف‌شده:\n" + report)
        else:
            game["night_actions"][player["id"]] = {"action": "hard_no"}
            await query.message.edit_text("⏭️ استعلام این شب انجام نشد. 🌙")
        await query.answer()
        return

    # Psychiatrist
    if action == "psycho":
        used = game["psy_used"].get(player["id"], 0)
        if target_id is None:
            game["night_actions"][player["id"]] = {"action": "psycho", "target": None}
            await query.message.edit_text("🤫 این شب کسی را ساکت نکردید. 🔇")
            await query.answer()
            return
        if used >= 2:
            await query.answer("استفاده‌های روان پزشک تمام شده.", show_alert=True)
            return
        game["psy_used"][player["id"]] = used + 1
        game["night_actions"][player["id"]] = {"action": "psycho", "target": target_id}
        await query.message.edit_text(f"🤫 {display_user(game,target_id)} برای روز بعد ساکت شد. 🔇")
        await query.answer()
        return

    # Seller
    if action == "seller":
        if player["id"] in game["seller_used"]:
            await query.answer("فروشنده قبلاً استفاده شده.", show_alert=True)
            return
        game["seller_used"].add(player["id"])
        game["night_actions"][player["id"]] = {"action": "seller", "target": target_id}
        await query.message.edit_text("✅ انتخاب شما ثبت شد. 🎯")
        await query.answer()
        return

    # Boss kill
    if action == "boss":
        if game.get("kill_selector") != player["id"]:
            await query.answer("در این شب شما مسئول انتخاب کشته نیستید.", show_alert=True)
            return
        game["mafia_target"] = target_id
        game["night_actions"][player["id"]] = {"action": "kill", "target": target_id}
        await query.message.edit_text("🔪 انتخاب کشته شب ثبت شد. 🌙")
        await query.answer()
        return

    # Lecter save
    if action == "lector_save":
        if player["role"] != "دکتر لکتر":
            return
        if target_id is not None:
            target = get_player(game, target_id)
            if not target or target["role"] not in MAFIA_ROLES:
                await query.answer("فقط مافیا را می‌توانی سیو کنی.", show_alert=True)
                return
        game["lecter_save"] = target_id
        game["night_actions"][player["id"]] = {"action": "lector_save", "target": target_id}
        await query.message.edit_text("🛡️ سیو دکتر لکتر ثبت شد. ✅")
        await query.answer()
        return

    # Fallback kill by Lecter/simple mafia
    if action == "kill":
        if game.get("kill_selector") != player["id"]:
            await query.answer("در این شب شما مسئول انتخاب کشته نیستید.", show_alert=True)
            return
        game["mafia_target"] = target_id
        game["night_actions"][player["id"]] = {"action": "kill", "target": target_id}
        await query.message.edit_text("🔪 انتخاب کشته شب ثبت شد. 🌙")
        await query.answer()
        return

    # Simple mafia suggestion
    if action == "mafia_suggest":
        game["night_actions"][player["id"]] = {"action": "mafia_suggest", "target": target_id}
        selector = get_player(game, game.get("kill_selector")) if game.get("kill_selector") else None
        if selector:
            await send_bot_message(
                selector["id"],
                f'💬 {display_user(game,player["id"])} پیشنهاد داد {display_user(game,target_id)} کشته شود. 🔪',
            )
        await query.message.edit_text("💬 پیشنهاد شما برای مسئول کشته ارسال شد. 🔪")
        await query.answer()
        return

    await query.answer()


# ================================================================
# NIGHT RESOLUTION
# ================================================================
async def eliminate_player(chat_id, user_id, reason):
    game = games.get(chat_id)
    if not game:
        return
    player = get_player(game, user_id)
    if not player or not player["alive"]:
        return

    player["alive"] = False
    player["reason"] = reason
    game["eliminated_history"].append(
        {"id": player["id"], "role": player["role"], "reason": reason}
    )
    await restrict_user(chat_id, user_id, False)

    if "شب" in reason:
        game["night_deaths"].append((player["id"], player["role"], reason))


async def resolve_night(chat_id):
    game = games.get(chat_id)
    if not game:
        return

    # Inactivity: every living active role must respond during the night.
    # Simple citizens are exempt. If a role has no action, they are removed.
    for p in list(alive(game)):
        if p["role"] == "شهروند":
            continue
        if p["id"] not in game["night_actions"]:
            # Boss / Lecter / simple mafia are also expected to act.
            await eliminate_player(chat_id, p["id"], "به دلیل نبودن داخل بازی اخراج شد")

    # Seller: permanently convert the selected player's role to citizen.
    seller = next((p for p in alive(game) if p["role"] == "فروشنده"), None)
    if seller and seller["id"] in game["night_actions"]:
        action = game["night_actions"][seller["id"]]
        target = get_player(game, action.get("target"))
        if target and target["alive"] and action.get("target") is not None:
            target["role"] = "شهروند"
            await send_bot_message(target["id"], "نقش شما فروخته شد و اکنون شهروند هستید.")

    # Psychiatrist: target skips the next day's speaking turn.
    psy = next((p for p in alive(game) if p["role"] == "روان پزشک"), None)
    if psy and psy["id"] in game["night_actions"]:
        action = game["night_actions"][psy["id"]]
        target = get_player(game, action.get("target"))
        if target and target["alive"]:
            game["silent_next_day"].add(target["id"])
            game["night_log"].append(f'🤫 {display_user(game,target["id"])} برای روز بعد ساکت شد. 🔇')

    # Sniper.
    sniper = next((p for p in alive(game) if p["role"] == "تک تیر انداز"), None)
    if sniper:
        action = game["night_actions"].get(sniper["id"])
        target = get_player(game, action.get("target")) if action else None
        if target:
            if target["role"] == "رییس مافیا":
                pass  # Boss is immune to sniper.
            elif target["role"] in MAFIA_ROLES:
                if game.get("lecter_save") != target["id"]:
                    await eliminate_player(chat_id, target["id"], "کشته شب توسط تک تیر انداز")
            else:
                await eliminate_player(chat_id, sniper["id"], "کشته شب به علت شلیک به شهروند")

    # Mafia kill.
    target = get_player(game, game.get("mafia_target")) if game.get("mafia_target") else None
    if target and target["alive"] and game.get("doctor_save") != target["id"]:
        if target["role"] == "جان سخت" and target["id"] not in game["hard_immune"]:
            game["hard_immune"].add(target["id"])
            game["night_log"].append(f'🛡️ {display_user(game,target["id"])} (جان سخت) برای اولین شلیک مافیا زنده ماند.')
        else:
            await eliminate_player(chat_id, target["id"], "کشته شب")

    # Remove the night message after the night ends.
    await delete_message_id(chat_id, game.get("night_message"))

    lines = ["🌅 گزارش شب"]
    if game["night_log"]:
        lines.append("\n".join(game["night_log"]))
    else:
        lines.append("روان پزشک کسی را ساکت نکرد و جان سخت گزارش ویژه‌ای ندارد.")

    if game["night_deaths"]:
        lines.append(
            "☠️ کشته‌های شب: "
            + ", ".join(display_user(game,item[0]) for item in game["night_deaths"])
        )
    else:
        lines.append("کسی در شب کشته نشد.")

    expelled = [
        p for p in game["players"]
        if (not p["alive"] and "نبودن داخل بازی" in p.get("reason", ""))
    ]
    if expelled:
        lines.append("🚫 اخراج به دلیل نبودن: " + ", ".join(label_player(p) for p in expelled))

    await send_bot_message(chat_id, "\n".join(lines))

    game["silent_next_day"] = {
        user_id
        for user_id in game["silent_next_day"]
        if (get_player(game, user_id) and get_player(game, user_id)["alive"])
    }

    if check_win(game):
        await finish_game(chat_id)
    else:
        await start_day(chat_id)


# ================================================================
# FINISH
# ================================================================
async def finish_game(chat_id):
    game = games.pop(chat_id, None)
    if not game:
        return

    await allow_all_alive(chat_id, game)
    winner = game["winner"]
    winning_side = "mafia" if winner == "مافیا" else "citizen"
    winners = [
        label_player(p)
        for p in game["players"]
        if p["alive"] and side(p["role"]) == winning_side
    ]

    await send_bot_message(
        chat_id,
        f"🏆 {winner} برنده شد! 🎉\n\n👑 بازیکنان برنده:\n"
        + ("\n".join(winners) or "ندارد"),
    )



def dooz_keyboard(gid):
    board=wager_games.get(gid,{}).get("board",[""]*9)
    rows=[]
    for r in range(3):
        row=[]
        for c in range(3):
            idx=r*3+c
            row.append(button(board[idx] or "⬜", f"wager:dooz:{gid}:{idx}"))
        rows.append(row)
    return keyboard(rows)

def dooz_winner(board):
    wins=((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
    for a,b,c in wins:
        if board[a] and board[a]==board[b]==board[c]:
            return board[a]
    if all(board): return "draw"
    return None

# ================================================================
# USER MENU / ECONOMY
# ================================================================
def displayed_username(uid):
    # منو باید برای همه کاربران مشخص کند متعلق به چه کسی است.
    # در صورت داشتن username، همان @username نمایش داده می‌شود؛
    # اگر username وجود نداشته باشد، نام نمایشی کاربر نشان داده می‌شود.
    row = get_user_record(uid)
    if row:
        username = (row[1] or "").strip()
        full_name = (row[2] or "").strip()
        if username:
            return "@" + username.lstrip("@")
        if full_name:
            return full_name
    return "بازیکن"

def total_balance(uid):
    return get_balance(uid) + bank_balance(uid)

def balance_display(uid):
    if is_arsin_id(uid):
        return ("💰 موجودی کل: & آریور\n"
                "👛 کیف پول: & آریور\n"
                "🏦 بانک: & آریور\n"
                "🔒 بلوکه‌شده: & آریور")
    blocked = bank_blocked_amount(uid)
    return (f"💰 موجودی کل: {format_coins(total_balance(uid))} آریور\n"
            f"👛 کیف پول: {format_coins(get_balance(uid))} آریور\n"
            f"🏦 بانک: {format_coins(bank_balance(uid))} آریور\n"
            f"🔒 بلوکه‌شده: {format_coins(blocked)} آریور")

def aunt_record(uid):
    with db() as c:
        row=c.execute("SELECT aunt_id,games_count,last_game_at FROM aunt_game_stats WHERE user_id=?",(uid,)).fetchone()
    if not row: return {"aunt_id":0,"games_count":0,"last_game_at":0}
    return {"aunt_id":int(row[0] or 0),"games_count":int(row[1] or 0),"last_game_at":int(row[2] or 0)}

def aunt_selected_by_other(aunt_id, excluded_user_id=0):
    """Return the current owner of an aunt relationship, excluding one user."""
    with db() as c:
        row=c.execute("SELECT user_id FROM aunt_game_stats WHERE aunt_id=? AND user_id<>? LIMIT 1",(int(aunt_id),int(excluded_user_id))).fetchone()
    return int(row[0]) if row else 0

def aunt_pair_for(uid):
    """Return the user's reciprocal aunt partner, or 0 when no valid pair exists."""
    rec=aunt_record(uid)
    aunt_id=int(rec.get("aunt_id",0) or 0)
    if not aunt_id or aunt_id==int(uid):
        return 0
    other=aunt_record(aunt_id)
    if int(other.get("aunt_id",0) or 0) != int(uid):
        return 0
    return aunt_id

def set_aunt_pair(uid, aunt_id):
    """Create a mutual one-to-one aunt relationship: A.aunt=B and B.aunt=A."""
    uid=int(uid); aunt_id=int(aunt_id); now=int(time.time())
    with db() as c:
        c.execute("INSERT INTO aunt_game_stats(user_id,aunt_id,games_count,updated_at,last_game_at) VALUES(?,?,0,?,0) ON CONFLICT(user_id) DO UPDATE SET aunt_id=excluded.aunt_id,updated_at=excluded.updated_at",(uid,aunt_id,now))
        c.execute("INSERT INTO aunt_game_stats(user_id,aunt_id,games_count,updated_at,last_game_at) VALUES(?,?,0,?,0) ON CONFLICT(user_id) DO UPDATE SET aunt_id=excluded.aunt_id,updated_at=excluded.updated_at",(aunt_id,uid,now))
        c.commit()

def clear_aunt_pair(uid):
    """Break the whole pair, leaving both people without an aunt."""
    uid=int(uid); now=int(time.time())
    with db() as c:
        row=c.execute("SELECT aunt_id FROM aunt_game_stats WHERE user_id=?",(uid,)).fetchone()
        partner=int(row[0] or 0) if row else 0
        c.execute("UPDATE aunt_game_stats SET aunt_id=0,updated_at=? WHERE user_id=?",(now,uid))
        if partner and partner != uid:
            c.execute("UPDATE aunt_game_stats SET aunt_id=0,updated_at=? WHERE user_id=? AND aunt_id=?",(now,partner,uid))
        c.commit()
    return partner

def clear_aunt(uid):
    clear_aunt_pair(uid)

def increment_aunt_games(uid, set_cooldown=True):
    now=int(time.time())
    with db() as c:
        c.execute("INSERT INTO aunt_game_stats(user_id,aunt_id,games_count,updated_at,last_game_at) VALUES(?,0,1,?,?) ON CONFLICT(user_id) DO UPDATE SET games_count=games_count+1,updated_at=excluded.updated_at,last_game_at=excluded.last_game_at",(uid,now,now if set_cooldown else 0))
        c.commit()
    return aunt_record(uid)["games_count"]

def aunt_game_remaining(uid):
    last=aunt_record(uid)["last_game_at"]
    return max(0, AUNT_GAME_COOLDOWN - int(time.time()-last))

def aunt_cooldown_text(uid):
    remaining=aunt_game_remaining(uid)
    if remaining<=0:
        return ""
    mins,secs=divmod(remaining,60)
    return f"⏳ خاله‌بازی هنوز آماده نیست! 👑\n🕐 {mins} دقیقه و {secs} ثانیه مونده.\n💧 هر ۲۵ دقیقه یک بار می‌تونی خاله‌بازی کنی."


def reset_user_data(uid):
    uid=int(uid)
    with db() as c:
        # Clear all personal progression and owned items.
        c.execute("DELETE FROM bank_hack_blocks WHERE user_id=?",(uid,))
        c.execute("DELETE FROM bank WHERE user_id=?",(uid,))
        c.execute("DELETE FROM inventory WHERE user_id=?",(uid,))
        c.execute("DELETE FROM user_pets WHERE user_id=?",(uid,))
        c.execute("DELETE FROM player_stats WHERE user_id=?",(uid,))
        c.execute("DELETE FROM achievements WHERE user_id=?",(uid,))
        c.execute("DELETE FROM daily_state WHERE user_id=?",(uid,))
        c.execute("DELETE FROM missions WHERE user_id=?",(uid,))
        c.execute("DELETE FROM transactions WHERE user_id=?",(uid,))
        c.execute("DELETE FROM gift_redemptions WHERE user_id=?",(uid,))
        c.execute("DELETE FROM shoshol_cooldowns WHERE user_id=?",(uid,))
        c.execute("DELETE FROM hack_cooldowns WHERE user_id=?",(uid,))
        c.execute("DELETE FROM champions WHERE user_id=?",(uid,))
        c.execute("DELETE FROM aunt_game_stats WHERE user_id=?",(uid,))
        c.execute("UPDATE aunt_game_stats SET aunt_id=0,updated_at=? WHERE aunt_id=?",(int(time.time()),uid))
        c.execute("DELETE FROM property_materials WHERE property_id IN (SELECT id FROM properties WHERE user_id=?)",(uid,))
        c.execute("DELETE FROM property_decor WHERE property_id IN (SELECT id FROM properties WHERE user_id=?)",(uid,))
        c.execute("DELETE FROM properties WHERE user_id=?",(uid,))
        c.execute("DELETE FROM football_team_players WHERE team_id IN (SELECT id FROM football_teams WHERE user_id=?)",(uid,))
        c.execute("DELETE FROM football_team_coaches WHERE team_id IN (SELECT id FROM football_teams WHERE user_id=?)",(uid,))
        c.execute("DELETE FROM football_matches WHERE creator_user_id=? OR opponent_user_id=?",(uid,uid))
        c.execute("DELETE FROM football_teams WHERE user_id=?",(uid,))
        c.execute("DELETE FROM business_items WHERE store_id IN (SELECT id FROM mall_stores WHERE user_id=?)",(uid,))
        c.execute("DELETE FROM mall_stores WHERE user_id=?",(uid,))
        c.execute("UPDATE market SET active=0 WHERE seller_id=? AND active=1",(uid,))
        c.execute("UPDATE item_market SET active=0 WHERE seller_id=? AND active=1",(uid,))
        c.execute("UPDATE item_auctions SET status='cancelled' WHERE seller_id=? AND status='active'",(uid,))
        c.execute("UPDATE item_auctions SET current_bid=0,current_bidder=0 WHERE current_bidder=? AND status='active'",(uid,))
        c.execute("INSERT INTO coins(user_id,balance,last_ah,ah_count,level,luck_level,exp_level) VALUES(?,?,0,0,0,0,0) ON CONFLICT(user_id) DO UPDATE SET balance=0,last_ah=0,ah_count=0,level=0,luck_level=0,exp_level=0",(uid,0))
        c.commit()
    transfer_pending.pop(uid,None); pending_link.pop(uid,None); pending_admin.pop(uid,None)


def profile_text(uid):
    r=get_coin_row(uid); win=min(50,int(TRADE_BASE_CHANCE+min(TRADE_LUCK_MAX_BONUS,int(r["luck_level"]))+min(TRADE_EXP_MAX_BONUS,int(r["exp_level"]))+(TRADE_FOX_BONUS if active_pet(uid)=="🦊 روباه" else 0)))
    st=get_daily_state(uid)
    display=displayed_username(uid)
    rank,rank_points=player_rank(uid)
    pet=active_pet(uid) or "هیچ‌کدام"
    team=football_team(uid)
    if team:
        team_power=football_team_power(team['id'])
        team_income=football_daily_income_amount(team['id'])
        team_info=f"⚽ تیم فوتبال: ✅ دارد\n🏷️ نام تیم: {team['club_name']}\n💪 قدرت تیم: {team_power}\n💰 درآمد روزانه فوتبال: {format_coins(team_income)} آریور"
    else:
        team_info="⚽ تیم فوتبال: ❌ ندارد\n💰 درآمد روزانه فوتبال: 0 آریور"
    return (f"👤 منوی کاربر آریو ✨\n\n🪪 این منو متعلق به کاربر: {display}\n\n{balance_display(uid)}\n{team_info}\n🏆 رنک: {rank} ({rank_points} امتیاز)\n🐾 حیوان فعال: {pet}\n👑 تعداد خاله‌بازی: {aunt_record(uid)['games_count']}\n⭐ لول کاربر: {r['level']}\n🍀 لول شانس: {r['luck_level']}/10 (+{min(10,int(r['luck_level']))}% شانس ترید)\n🧠 لول تجربه: {r['exp_level']}/10 (+{min(10,int(r['exp_level']))}% شانس ترید)\n🎯 شانس برد ترید: {win}%\n🧪 معجون شانس ترید: {inventory_qty(uid,TRADE_POTION_ITEM)} عدد (+5%؛ در ترید بعدی یک عدد مصرف می‌شود)\n⛏️ تعداد آریو: {r['ah_count']}\n🔥 استریک روزانه: {st['streak']}\n⚔️ قدرت تجهیزات: {combat_power(uid)}")

def user_menu_keyboard(uid=None):
    uid=int(uid or 0)
    team_label = "⚽ مدیریت تیم" if uid and football_team(uid) else "⚽ ساخت تیم"
    return keyboard([
        [button("🎁 جایزه روزانه","user:daily"),button("🎯 ماموریت‌ها","user:missions")],
        [button("⬆️ ارتقا","user:upgrade_menu"),button("📈 ترید","user:trade")],
        [button("🏦 بانک آریور","user:bank"),button("🎮 بازی‌ها","user:games")],
        [button("🏬 پاساژ","user:passage"),button("💼 دارایی ها","user:assets_menu")],
        [button("🏢 کسب و کار","user:business"),button(team_label,"user:football")],
        [button("🏆 لیدر بورد","user:leaderboard_menu"),button("🥇 رنک و لیگ","user:rank")],
        [button("🥊 مبارزه","user:combat"),button("🏆 تورنمنت","user:tournament")],
        [button("💸 انتقال آریور","user:transfer"),button("📚 راهنما","user:help")],
        [button("🎟️ قرعه‌کشی","user:lotteries")],
        [button("❌ بستن منو","menu:close")]
    ])

def upgrade_menu_keyboard():
    return keyboard([
        [button("⬆️ ارتقای لول","user:level")],
        [button("🍀 ارتقای شانس","user:luck")],
        [button("🧠 ارتقای تجربه","user:exp")],
        [button("🔙 برگشت به منو","user:menu")],
        [button("❌ بستن منو","menu:close")]
    ])

def passage_keyboard():
    return keyboard([
        [button("🕶️ فروشگاه سیاه","user:blackshop"),button("🛍️ فروشگاه","user:shop")],
        [button("🧱 مصالح","user:materials"),button("🛋️ دکوراسیون","user:decor")],
        [button("🏠 املاک","user:property"),button("🐾 پت شاپ","user:petshop")],
        [button("🔙 برگشت به منو","user:menu")],
        [button("❌ بستن منو","menu:close")]
    ])

def assets_menu_keyboard():
    return keyboard([
        [button("🎒 کوله پشتی","user:inventory"),button("🏅 دستاورد ها","user:achievements")],
        [button("👑 قهرمان","user:champion"),button("📜 تاریخچه","user:history")],
        [button("🏠 املاک","user:assets")],
        [button("🧰 لوازم کسب و کار","user:business_items")],
        [button("🐾 پت های من","user:pets"),button("📊 امار من","user:stats")],
        [button("🔙 برگشت به منو","user:menu")],
        [button("❌ بستن منو","menu:close")]
    ])

def leaderboard_menu_keyboard():
    return keyboard([
        [button("💰 پولدار ها","user:wealth")],
        [button("⭐ بهترین ها","user:best_leaderboard")],
        [button("📊 فعالیت ها","user:activity_leaderboard")],
        [button("⚽ بهترین تیم های فوتبال","user:football_leaderboard")],
        [button("🔙 برگشت به منو","user:menu")],
        [button("❌ بستن منو","menu:close")]
    ])

def trade_keyboard(): return keyboard([[button("🎲 ترید 100 آریور","trade:100")],[button("🎲 ترید 1,000 آریور","trade:1000")],[button("🎲 ترید 10,000 آریور","trade:10000")],[button("🔙 برگشت به منو","user:menu")],[button("❌ بستن منو","menu:close")]])

def help_categories_keyboard():
    return keyboard([
        [button("💰 آریور و پروفایل", "help:cat:money"), button("🏦 بانک", "help:cat:bank")],
        [button("🎁 روزانه و ماموریت", "help:cat:daily"), button("📊 آمار و رنک", "help:cat:stats")],
        [button("🛍️ فروشگاه و آیتم‌ها", "help:cat:shop"), button("🥊 مبارزه و تجهیزات", "help:cat:combat")],
        [button("🏠 ملک و ساخت", "help:cat:property"), button("🛋️ دکوراسیون", "help:cat:decor")],
        [button("🐾 حیوانات / Pet", "help:cat:pets"), button("🏆 رنک و لیگ", "help:cat:rank")],
        [button("✂️ شوشول بری", "help:cat:shoshol"), button("💻 هک و امنیت", "help:cat:hacking")],
        [button("🎮 بازی‌های شرطی", "help:cat:games")],
        [button("🃏 هفت خبیث", "help:cat:seven")],
        [button("🏆 تورنمنت و قهرمان", "help:cat:tournament"), button("🎭 مافیا", "help:cat:mafia")],
        [button("🏢 کسب و کار و مغازه", "help:cat:business")],
        [button("⚽ تیم و باشگاه فوتبال", "help:cat:football")],
        [button("👑 خاله‌بازی", "help:cat:aunt")],
        [button("🎁 کد هدیه و عضویت", "help:cat:general")],
        [button("🔙 برگشت به منو", "user:menu")],
        [button("❌ بستن منو", "menu:close")],
    ])

HELP_CATEGORY_TEXTS = {
    "money": (
        "💰 راهنمای آریور و پروفایل\n\n"
        "• «آریو» → استخراج آریو و تبدیل خودکار به آریور؛ هر ۵ دقیقه یک‌بار ⛏️\n"
        "• «موجودی» → نمایش موجودی کیف پول 💎\n"
        "• «منو» → پروفایل شخصی و امکانات 👤\n"
        "• 🏠 خرید ملک / 🧱 مصالح / 🛋️ دکوراسیون / 💼 دارایی‌ها → سیستم کامل ملک و خانه.\n"
        "• «ترید مقدار» → ترید با مبلغ حداقل 2 آریور؛ سود/ضرر هر ترید حداقل یک‌سوم مبلغ است؛ مثال: «ترید 2500» 🎲\n"
        "• «ارتقای لول» → 10,000 آریور برای +۱ لول اصلی ⭐\n"
        "• «ارتقای لول شانس» → هر لول +۲.۹٪ شانس؛ حداکثر ۱۰ (۲۹٪) 🍀\n"
        "• «ارتقای لول تجربه» → هر لول +۲.۹٪ شانس؛ حداکثر ۱۰ (۲۹٪) 🧠\n"
        "• شانس ترید: ۲۰٪ پایه + حداکثر ۱۰٪ لول شانس + حداکثر ۱۰٪ لول تجربه + ۵٪ روباه + ۵٪ معجون؛ سقف ۵۰٪ است. 🧪\n"
        "• «انتقال مقدار» با ریپلای به کاربر → انتقال آریور 💸"
    ),
    "bank": (
        "🏦 راهنمای بانک آریور\n\n"
        "• «بانک» → نمایش موجودی بانک 💳\n"
        "• «واریز مقدار» → مثال: «واریز 5000»\n"
        "• «برداشت مقدار» → مثال: «برداشت 2000»\n"
        "• بانک برای نگهداری جداگانه آریور استفاده می‌شود. 💎\n"
        "• اگر به‌خاطر لو رفتن هک پولی بلوکه شود، مقدار بلوکه‌شده در موجودی قابل برداشت حساب نمی‌شود. 🔒"
    ),
    "daily": (
        "🎁 راهنمای روزانه و ماموریت‌ها\n\n"
        "• «جایزه روزانه» → دریافت جعبه روزانه 🎁\n"
        "• «استریک» → نمایش استریک روزانه 🔥\n"
        "• «ماموریت‌ها» → ماموریت‌های روزانه و میزان پیشرفت 🎯\n"
        "• بعد از تکمیل مأموریت، دکمه دریافت جایزه ظاهر می‌شود.\n"
    ),
    "stats": (
        "📊 راهنمای آمار، دستاورد و رنک\n\n"
        "• «آمار» → بازی، برد، باخت، مساوی، درصد برد و XP 📈\n"
        "• «دستاوردها» → دستاوردهای باز و قفل‌شده 🏅\n"
        "• «رنک» → لیگ و امتیاز فعلی 🥇\n"
        "• «رتبه‌بندی» → رتبه‌بندی بازیکنان 🏆\n"
        "• «لیدربورد برد» و «لیدربورد امتیاز» → رتبه‌بندی تخصصی 🔥⭐\n"
        "• «پولدارا» → ۵ بازیکن ثروتمندتر بر اساس کیف پول + بانک 💰\n"
        "• برد +۲۵، مساوی +۵ و باخت −۱۰ امتیاز دارد.\n"
    ),
    "shop": (
        "🛍️ راهنمای فروشگاه و آیتم‌ها\n\n"
        "• «فروشگاه» → آیتم‌های عادی و لوازم کسب‌وکار را نشان می‌دهد. 🛍️\n"
        "• لوازم کسب‌وکار: PS4، PS5، Xbox Series S، Xbox Series X، مانیتور ۲۴ اینچ سونی، مبل تک‌نفره، پایه دیواری مانیتور، PC نسل ۹ گیمینگ و پک کیبورد و موس ریزر.\n"
        "• لوازم کسب‌وکار فقط با داشتن حداقل یک مغازه پاساژ قابل خرید هستند.\n"
        "• «آیتم‌ها» → تمام آیتم‌های شما، تعداد و قدرت تجهیزات 🎒\n"
        "• داخل کوله‌پشتی کارایی هر آیتم هم دقیقاً نوشته می‌شود. ℹ️\n"
        "• ابزارهای شوشول بری و آیتم‌های ضدشوشول در فروشگاه سیاه هستند. 🕶️\n"
        "• V20: ۱۰ معجون مبارزه‌ای یک‌بارمصرف، ۵ تجهیزات دائمی مبارزه و ۱۰ معجون دفاعی یک‌بارمصرف در فروشگاه سیاه اضافه شده‌اند. 🧪\n"
        "• معجون‌های مبارزه در نوبت خودت از دکمه «🧪 معجون‌ها» داخل مبارزه استفاده می‌شوند و پس از مصرف از کوله‌پشتی کم می‌شوند.\n"
        "• ۵ تجهیزات دائمی مبارزه مصرف نمی‌شوند و قدرتشان همیشه در مبارزه محاسبه می‌شود.\n"
        "• بارش شوشول، نانو و طلایی یک‌بارمصرف‌اند؛ برای استفاده روی پیام هدف ریپلای کن و دستور همان آیتم را بفرست.\n"
        "• پدافند بارش شوشول، شانس نهایی همان نوع بارش را به‌صورت واحد درصد کم می‌کند و پس از خرید در برابر حمله‌های مربوط فعال است.\n"        "• «💻 هکر» و «🛡️ ضد هک» هم در فروشگاه سیاه هستند؛ سطح آن‌ها با خریدهای بعدی ارتقا پیدا می‌کند.\n"
    ),
    "combat": (
        "🥊 راهنمای مبارزه و تجهیزات\n\n"
        "• «فروشگاه سیاه» → تجهیزات مبارزه و شخصیت‌های خیالی ⚔️\n"
        "• قیمت‌های فروشگاه سیاه ۱۰ برابر قیمت آیتم‌های عادی است. 🕶️💎\n"
        "• «مبارزه مقدار» در گروه → مثال: «مبارزه 1000»\n"
        "• نفر دوم با دکمه «شرکت کردن» وارد می‌شود.\n"
        "• بعد از ورود نفر دوم، مبارزه واقعاً نوبتی می‌شود. ⚔️\n"
        "• ❤️ هر بازیکن 100 جان دارد.\n"
        "• ⚔️ حمله: آسیب تصادفی بر اساس قدرت تجهیزات.\n"
        "• 🛡️ دفاع: ضربه بعدی را نصف می‌کند.\n"

        "• 🏆 با صفر شدن جان، حریف برنده کل دو ورودی می‌شود.\n"
        "• 🛡️ سپر انرژی در سیستم قبلیِ دفاعی قابل مصرف است و در نسخه دوئل برای تعادل، نتیجه را مستقیماً عوض نمی‌کند.\n"
        "• اگر تا 60 ثانیه کسی وارد نشود، مبلغ سازنده برمی‌گردد. ⏳\n"
        "\n✂️ شوشول بری\n"
        "• «شوشول بری» را با ریپلای روی کاربر اجرا کن. 😈\n"
        "• هدف باید حداقل 500 آریور در کیف پول عادی داشته باشد؛ بانک قابل دزدی نیست. 🏦🚫\n"
        "• شانس پایه 50٪ است و ابزارها حداکثر +30٪ می‌دهند؛ سقف موفقیت 80٪ است. 🎯\n"
        "• چاقوی دول‌بری +8٪، قیچی +8٪، اره‌برقی +7٪ و دول‌بُر +7٪ می‌دهند. 🧰\n"
        "• شوشول طلایی 15٪ و معشوق شوشول 10٪ از شانس مهاجم کم می‌کنند. 🛡️\n"
        "• سود یا جریمه تصادفی بین 0 تا یک‌سی‌ام موجودی کیف پول هدف است. 💎\n"
        "• اگر جریمه از کیف پول مهاجم بیشتر باشد، فقط کل موجودی کیف پول او کسر می‌شود.\n"
    ),
    "hacking": (
        "💻 راهنمای هک و امنیت بانک 🛡️\n\n"
        "• برای هک باید آیتم «💻 هکر» را از فروشگاه سیاه داشته باشی.\n"
        "• روی پیام کاربر موردنظر ریپلای کن و فقط بنویس «هک».\n"
        "• هک برای هر کاربر فقط هر ۷ دقیقه یک‌بار قابل انجام است. ⏳\n"
        "• هکر ۵ سطح دارد. سطح ۱ شانس پایه ۳۰٪ دارد.\n"
        "• سطح‌های بعدی شانس را بالا می‌برند و سطح ۵ حداکثر شانس پایه ۸۰٪ دارد.\n"
        "• «🛡️ ضد هک» ۳ سطح دارد و هر سطح ۱۰٪ از شانس هکر کم می‌کند.\n"
        "• بنابراین هکر سطح ۵ مقابل ضد هک سطح ۳، شانس نهایی ۵۰٪ دارد. 🎯\n"
        "• در صورت موفقیت، بین یک‌دهم تا سه‌دهم موجودی قابل استفاده بانک هدف دزدیده می‌شود.\n"
        "• هر عملیات همچنین ۸۰٪ احتمال لو رفتن دارد. در صورت لو رفتن، نصف موجودی فعلی بانک هکر ۲۴ ساعت بلوکه می‌شود.\n"
        "• بعد از ۲۴ ساعت، ۹۰٪ مبلغ بلوکه‌شده برمی‌گردد و ۱۰٪ آن جریمه می‌شود.\n"
        "• هک فقط روی بانک انجام می‌شود و بدون داشتن آیتم هکر امکان اجرای «هک» وجود ندارد.\n"
        "• قیمت شروع هکر: ۵۰۰,۰۰۰ آریور؛ هزینه هر ارتقا دو برابر می‌شود: ۱M، ۲M، ۴M، ۸M.\n"
        "• قیمت شروع ضد هک: ۷۵۰,۰۰۰ آریور؛ ارتقاها: ۱.۵M و ۳M.\n"
    ),
    "shoshol": (
        "✂️ راهنمای کامل شوشول بری 😈\n\n"
        "📌 دستور: روی پیام کاربر موردنظر ریپلای کن و بنویس «شوشول بری».\n\n"
        "💰 شرط هدف: کاربر باید حداقل 500 آریور در کیف پول عادی داشته باشد.\n"
        "🏦 موجودی بانک هدف قابل دزدی نیست و هیچ اثری در شوشول بری ندارد.\n"
        "🎯 شانس پایه موفقیت: 50٪\n"
        "🔪 چاقوی دول‌بری: +8٪\n"
        "✂️ قیچی: +8٪\n"
        "🪚 اره‌برقی: +7٪\n"
        "🔪 دول‌بُر: +7٪\n"
        "📈 مجموع ابزارهای هجومی حداکثر +30٪ و سقف شانس نهایی 80٪ است.\n"
        "⏳ هر کاربر هر 7 دقیقه یک بار می‌تواند شوشول بری انجام دهد.\n\n"
        "🛡️ شوشول طلایی: 15٪ از شانس مهاجم کم می‌کند.\n"
        "💘 معشوق شوشول: 10٪ از شانس مهاجم کم می‌کند.\n"
        "🛡️ مجموع کاهش دفاعی حداکثر 25٪ است.\n\n"
        "💎 در صورت موفقیت، مقدار تصادفی از 0 تا یک‌سی‌ام موجودی کیف پول هدف منتقل می‌شود.\n"
        "🚨 در صورت شکست، مقدار تصادفی به‌عنوان جریمه از کیف پول مهاجم کم می‌شود.\n"
        "⚠️ اگر جریمه بیشتر از موجودی کیف پول مهاجم باشد، فقط کل کیف پول او کسر می‌شود.\n"
        "🔒 بانک هیچ‌کدام از طرفین در این عملیات دست‌کاری نمی‌شود.\n\n"
        "🎒 برای دیدن تعداد و اثر ابزارها: «آیتم‌ها» را بزن.\n"
        "🕶️ خرید ابزارها: «فروشگاه سیاه»\n"
    ),
    "games": (
        "🎮 راهنمای بازی‌های شرطی دو نفره\n\n"
        "• «دوز 100» → دوز ⭕️❌\n"
        "• «سنگ کاغذ قیچی 100» → ✊📄✂️\n"
        "• «جنگ کارت 100» → کارت بالاتر برنده 🃏\n"
        "• «زوج یا فرد 100» → انتخاب زوج/فرد 🎯\n"
        "• «حدس عدد 100» → عدد مخفی ۱ تا ۱۰ و حدس نفر دوم 🔢\n"
        "• «بالاتر 100» → عدد بالاتر برنده 📈\n"
        "• «تاس جنگ 100» → تاس بالاتر برنده 🎲\n"
        "• «بلک‌جک ساده 100» → بازی نوبتی؛ کارت یا ایست 🃏\n"
        "• «مسابقه سرعت 100» → اولین پاسخ درست برنده است ⚡\n"
        "• ورودی دو نفر برابر است؛ برنده کل مبلغ را می‌گیرد.\n"
        "• مساوی = برگشت ورودی‌ها؛ عدم ورود نفر دوم تا ۶۰ ثانیه = برگشت پول. ⏳"
    ),
    "seven": (
        "🃏 راهنمای هفت خبیث\n\n"
        "• «بازی 7 خبیث مقدار» یا «بازی هفت خبیث مقدار» → ساخت بازی شرطی.\n"
        "• لابی ۲ تا ۴ نفره است؛ سازنده تعداد نفرات را انتخاب می‌کند.\n"
        "• ۲ نفر: هر نفر ۱۱ کارت؛ ۳۰ کارت در وسط.\n"
        "• ۳ نفر: هر نفر ۷ کارت؛ ۳۱ کارت در وسط.\n"
        "• ۴ نفر: هر نفر ۵ کارت؛ ۳۲ کارت در وسط.\n"
        "• دسته بازی دقیقاً ۵۲ کارت استاندارد دارد؛ کارت جوکر وجود ندارد. 🃏🚫\n"
        "• کارت‌های هر بازیکن برای حفظ حریم خصوصی در پیوی خودش نمایش داده می‌شود؛ پیام گروه وضعیت عمومی بازی را نشان می‌دهد.\n"
        "• هر نوبت ۱۰ ثانیه است؛ در پایان زمان، یک کارت خودکار کشیده می‌شود و نوبت رد می‌شود. ⏱️\n"
        "• فقط کارت هم‌خال یا هم‌شماره قابل بازی است.\n"
        "• آس → نوبت نفر بعد را رد می‌کند.\n"
        "• ۲ → یک کارت تصادفی از دست زننده ۲ به نفر بعد می‌دهد.\n"
        "• ۷ → جریمه ۲ کارت برای نفر بعد؛ با ۷ می‌تواند جریمه را زنجیره‌ای کند. با «کشیدن» جریمه کامل گرفته می‌شود.\n"
        "• ۸ → بعد از آن باید یک کارت جایزه هم‌خال یا هم‌شماره بازی شود؛ اگر نداشتی یک کارت می‌کشی و نوبتت رد می‌شود.\n"
        "• ۱۰ → جهت بازی را برعکس می‌کند.\n"
        "• J → می‌توانی خال فعال را انتخاب کنی و سپس نوبتت تمام می‌شود.\n"
        "• دکمه «🎴 کشیدن»: سبز یعنی کارت قابل بازی نداری؛ قرمز یعنی کارت قابل بازی یا جک داری. رنگ فقط اطلاع‌رسانی است و دکمه قرمز هم قابل کلیک است.\n"
        "• دکمه «🎯 نوبت» نوبت فعلی را نشان می‌دهد و در نوبت خودت سبز می‌شود.\n"
        "• اولین بازیکنی که تمام کارت‌های دستش را بازی کند، برنده کل شرط‌هاست. 🏆"
    ),
    "pets": (
        "🐾 راهنمای حیوانات / Pet System\n\n"
        "• 🐺 گرگ → +20 قدرت مبارزه ⚔️\n"
        "• 🦊 روباه → +5٪ شانس برد در ترید و مبارزه 🍀\n"
        "• 🐯 ببر → +30 قدرت مبارزه ⚔️\n"
        "• 🦅 عقاب → +25٪ XP از بردها 🧠\n"
        "• 🐉 اژدها → +40 قدرت مبارزه و +50٪ XP؛ بسیار کمیاب 🔥\n\n"
        "🐾 حیوان خریداری‌شده وارد «آیتم‌های من» می‌شود.\n"
        "• فقط یک حیوان می‌تواند هم‌زمان فعال باشد.\n"
        "• از «🐾 حیوانات من» حیوان را فعال/غیرفعال کن.\n"
        "• حیوان فعال واقعاً روی مبارزه، شانس یا XP اثر می‌گذارد. ✨\n"
        "• حیوانات آیتم واقعی‌اند و در سیستم بازار/حراج هم قابل معامله‌اند. 🛒"
    ),
    "rank": (
        "🏆 راهنمای رنک و لیگ\n\n"
        "رنک بر اساس امتیاز League تعیین می‌شود: ⭐\n"
        "🥉 برنز: ۰+\n"
        "🥈 نقره: ۱۰۰+\n"
        "🥇 طلا: ۳۰۰+\n"
        "💎 الماس: ۷۰۰+\n"
        "👑 مستر: ۱۵۰۰+\n\n"
        "🏆 برد: +25 امتیاز\n"
        "🤝 مساوی: +5 امتیاز\n"
        "💔 باخت: -10 امتیاز\n\n"
        "«رنک» یا دکمه «🥇 رنک و لیگ» وضعیت فعلی را نشان می‌دهد."
    ),
    "tournament": (
        "🏆 راهنمای تورنمنت و قهرمان\n\n"
        "• «تورنمنت 1000» در گروه → ساخت تورنمنت ۸ نفره 🏆\n"
        "• بازیکنان همان مبلغ ورودی را می‌پردازند.\n"
        "• با تکمیل ظرفیت، یک‌چهارم، نیمه‌نهایی و فینال اجرا می‌شود.\n"
        "• قدرت تجهیزات روی نتیجه احتمالی اثر دارد. ⚔️\n"
        "• اگر تا ۱۲۰ ثانیه کامل نشود، ورودی‌ها برگشت داده می‌شوند.\n"
        "• «قهرمان» → رکورد قهرمانی و آمار قهرمان 👑\n"
        "• سیستم قهرمان از رنک و لیدربورد عادی جداست.\n"    ),
    "mafia": (
        "🎭 راهنمای بازی مافیا\n\n"
        "• «بازی مافیا» → شروع بازی در گروه 🎭\n"
        "• «پایه‌ام» → ورود به بازی؛ ربات باید در پیوی /start شده باشد و عضویت لازم انجام شده باشد.\n"
        "• نقش‌ها در پیوی ارسال می‌شوند.\n"
        "• تایمر صحبت، چالش، دفاع، رأی و شب نمایش داده می‌شود. ⏳\n"
        "• «پایان بازی» یا «بایان بازی» → پایان و پاک‌سازی بازی فعال 🛑"
    ),
    "property": (
        "🏠 راهنمای ملک، ساخت و دارایی‌ها\n\n"
        "• «🏠 املاک» → ابتدا بین «زمین» و «مغازه در پاساژ» انتخاب می‌کنی.\n"
        "• زمین → یکی از ۱۰ منطقه و سپس متراژ ۵۰، ۱۰۰، ۱۵۰ یا ۲۰۰ متر را انتخاب می‌کنی.\n"
        "• قیمت زمین = قیمت هر متر منطقه × متراژ و قبل از پرداخت تأیید می‌شود.\n"
        "• مغازه پاساژ → قیمت پیش‌فرض هر متر ۳۰۰,۰۰۰ آریور و متراژهای ۱، ۱۰، ۳۰، ۵۰، ۶۰، ۱۰۰، ۱۵۰، ۲۰۰، ۳۰۰ و ۶۰۰ متر دارد.\n"
        "• خرید مغازه هم قبل از پرداخت صفحه تأیید دارد و مغازه در «املاک» نمایش داده می‌شود.\n"
        "• «🧱 مصالح ساختمانی» → فقط بعد از خرید زمین فعال است و مقدار هر مصالح بر اساس متراژ همان زمین محاسبه می‌شود.\n"
        "• با خرید تمام مصالح، زمین خودکار به خانه تبدیل می‌شود. 🏠\n"
        "• «💼 دارایی‌ها» → تعداد خانه‌ها و زمین‌ها و ارزش فروش آن‌ها را می‌بینی.\n"
        "• فروش خانه = قیمت زمین + مجموع هزینه مصالح + ۲۰٪. فروش زمین خالی = ۸۰٪ قیمت خرید زمین.\n"
        "• تمام قیمت‌های ملک و مصالح از پنل آرسین قابل تغییر هستند.\n"
    ),
    "decor": (
        "🛋️ راهنمای دکوراسیون داخلی\n\n"
        "• این بخش فقط برای خانه ساخته‌شده فعال است.\n"
        "• تمام لوازم آشپزخانه، پذیرایی و اتاق خواب در فهرست خرید هستند.\n"
        "• قیمت همه آیتم‌های دکوراسیون از پنل آرسین قابل تغییر است.\n"
        "• تخت خواب، میز تحریر و میز مطالعه قابلیت خرید چندباره برای ارتقا دارند.\n"
    ),
    "business": (
        "🏢 راهنمای کسب و کار و مغازه پاساژ\n\n"
        "• برای شروع کسب و کار باید حداقل یک «مغازه در پاساژ» بخری.\n"
        "• لوازم کسب و کار فقط برای مغازه‌های پاساژ قابل خرید هستند.\n"
        "• اگر چند مغازه داشته باشی، هنگام خرید هر وسیله از فروشگاه از تو می‌پرسد وسیله به کدام مغازه اضافه شود.\n"
        "• هر ۲ متر مغازه ظرفیت یک پک کامل دارد.\n"
        "• پک ۱: مانیتور + پایه مانیتور + یک کنسول بازی + مبل تک‌نفره.\n"
        "• پک ۲: مانیتور + پایه مانیتور + کامپیوتر + پک کیبورد و موس + مبل تک‌نفره.\n"
        "• هر PS4، PS5، Xbox Series S یا Xbox Series X می‌تواند بخش کنسول پک ۱ باشد.\n"
        "• تعداد پک کامل بر اساس تجهیزات موجود و ظرفیت متراژ محاسبه می‌شود.\n"
        "• درآمد روزانه هر مغازه = مجموع هزینه خرید لوازم آن مغازه ÷ ۳۰، به شرط داشتن حداقل یک پک کامل.\n"
        "• درآمد هر ۲۴ ساعت به‌صورت خودکار به بانک واریز می‌شود.\n"
        "• «🏢 کسب و کار» تعداد مغازه‌ها، پک‌های کامل و درآمد روزانه را نشان می‌دهد.\n"
        "• «🧰 لوازم کسب و کار» وسایل، کد هر وسیله و تعداد پک‌های کامل را نشان می‌دهد.\n"
        "• فروش وسیله: «فروش کد»؛ ربات همان وسیله را با ۲۰٪ کمتر از قیمت فعلی فروشگاه از شما می‌خرد.\n"
        "• کدهای فعلی: K01 تا K09 و هر کد فقط برای یک آیتم است.\n"
        "• فروش مغازه: ۸۰٪ قیمت خرید مغازه.\n"
        "• قیمت مغازه و تمام لوازم کسب‌وکار از پنل آرسین قابل تغییر هستند.\n"
    ),
    "football": (
        "⚽ راهنمای کامل تیم و باشگاه فوتبال\n\n"
        "• «⚽ ساخت تیم» از منو → با پرداخت ۲۰,۰۰۰,۰۰۰ آریور باشگاهت را می‌سازی.\n"
        "• نام باشگاه باید یکتا باشد و دو باشگاه نمی‌توانند نام یکسان داشته باشند.\n"
        "• بعد از ساخت، دکمه «مدیریت تیم» پنل تیم را در پیوی می‌فرستد.\n"
        "• تیم حداکثر ۲۲ بازیکن دارد.\n"
        "• ترکیب کامل برای بازی: ۱ دروازه‌بان، ۴ دفاع، ۴ هافبک و ۳ مهاجم.\n"
        "• خرید مربی و بازیکن با قرارداد ۱ ماهه، ۱ ساله یا ۳ ساله انجام می‌شود.\n"
        "• هر بازی فوتبال یک روز از قرارداد مربی و بازیکنان کم می‌کند.\n"
        "• فاصله دو بازی فوتبال برای هر تیم باید حداقل ۱ ساعت باشد.\n"
        "• در کمتر از ۱۰ روز باقی‌مانده قرارداد، گزینه تمدید و پیام هشدار نمایش داده می‌شود.\n"
        "• فسخ قرارداد با پرداخت ۳/۱۰ مبلغ همان قرارداد انجام می‌شود.\n"
        "• «بازی فوتبال مبلغ» با ریپلای روی بازیکن حریف، دعوت بازی فوتبال را ایجاد می‌کند.\n"
        "• نتیجه بازی بر اساس ۵۰٪ قدرت بازیکنان، ۲۰٪ شانس، ۱۰٪ فاصله آخرین بازی و ۲۰٪ تجربه/قدرت/سابقه تیم محاسبه می‌شود.\n"
        "• برنده کل شرط دو طرف را دریافت می‌کند.\n"
        "• بازیکنان معروف مثل رونالدو، مسی، امباپه، هالند و... در لیست حضور دارند.\n"
        "• آرسین می‌تواند قیمت بازیکنان را تغییر دهد و بازیکن جدید با نام، پست، قدرت و قیمت اضافه کند.\n"
        "• «مدیریت تیم» → باز کردن مستقیم پنل تیم در پیوی.\n"
    ),
    "aunt": (
        "👑 راهنمای خاله‌بازی 💧👸\n\n"
        "• «انتخاب خاله» با ریپلای روی یک نفر → شما و آن فرد خاله یکدیگر می‌شوید. 💧👸\n"
        "• رابطه خاله کاملاً دوطرفه و یک‌به‌یک است؛ وقتی دو نفر خاله یکدیگر شدند، هیچ‌کدام نمی‌تواند فرد دیگری را انتخاب کند. 🔒\n"
        "• «خاله» → خاله فعلی شما را نشان می‌دهد. 👸\n"
        "• «تعویض خاله» با ریپلای روی فرد جدید → رابطه قبلی کامل قطع می‌شود و با پرداخت ۳,۰۰۰ آریور، رابطه جدید دوطرفه ساخته می‌شود. 🔄💎\n"
        "• «حذف خاله» → رابطه خاله‌ای هر دو نفر کامل حذف می‌شود و هر دو دوباره آزاد می‌شوند. 💧\n"
        "• «خاله بازی» → هر دو نفر ۵,۰۰۰ آریور می‌گیرند و هر نفر هر ۲۵ دقیقه یک بار می‌تواند انجامش دهد. ⏳🎁\n"
        "• اگر خاله نداری، اول «انتخاب خاله» را انجام بده.\n"
        "• تعداد خاله‌بازی‌ها در پروفایل و آمار نمایش داده می‌شود. 👑"
    ),
    "general": (
        "🎁 راهنمای کد هدیه، عضویت و دستورات عمومی\n\n"
        "• «کد هدیه CODE» → استفاده از کد هدیه 🎁\n"
        "• هر کاربر فقط یک‌بار از هر کد استفاده می‌کند.\n"
        "• «/start» → ثبت‌نام و آماده‌سازی حساب.\n"
        "• «عضو شدم» → بررسی دوباره عضویت در لینک‌های لازم.\n"
        "• «آریو» → پاسخ مخصوص 🤖\n"
        "• «آرسین» یا «ارسین» → پاسخ مخصوص 😤\n"
        "• «راهنما» / «راهنما آریو» → باز کردن دسته‌بندی راهنما 📚\n\n"
        "🛠️ توسعه‌دهنده: @arsin_mo"
    ),
}

def help_topic_keyboard():
    return keyboard([[button("🔙 برگشت به دسته‌بندی راهنما", "help:categories")], [button("🏠 برگشت به منو", "user:menu")], [button("❌ بستن منو", "menu:close")]])

@dp.callback_query(F.data == "help:categories")
async def help_categories(query: CallbackQuery):
    await query.message.edit_text("📚 راهنمای آریو\n\nموضوع موردنظرت رو انتخاب کن 👇✨", reply_markup=help_categories_keyboard())
    await query.answer()

@dp.callback_query(F.data.startswith("help:cat:"))
async def help_category(query: CallbackQuery):
    key=query.data.split(":",2)[2]
    text=HELP_CATEGORY_TEXTS.get(key)
    if not text:
        await query.answer("❌ موضوع نامعتبر است.", show_alert=True); return
    await query.message.edit_text(text, reply_markup=help_topic_keyboard())
    await query.answer()

def user_help_text():
    return "📚 راهنمای آریو\n\nموضوع موردنظرت رو انتخاب کن 👇✨"

def help_keyboard(page=0):
    return help_categories_keyboard()


@dp.callback_query(F.data.startswith("seven:lobby:"))
async def seven_lobby_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: gid=int(parts[2]); action=parts[3]
    except Exception:
        await query.answer("❌ لابی نامعتبر است.",show_alert=True); return
    g=SEVEN_GAMES.get(gid)
    if not g or g.get("status")!="waiting":
        await query.answer("❌ این لابی دیگر فعال نیست.",show_alert=True); return
    uid=query.from_user.id

    if action in ("2","3","4"):
        if uid!=g["creator_id"]:
            await query.answer("فقط سازنده بازی تعداد نفرات را تعیین می‌کند.",show_alert=True); return
        if len(g["players"])>1:
            await query.answer("بعد از ورود بازیکن دیگر، تعداد نفرات قابل تغییر نیست.",show_alert=True); return
        g["max_players"]=int(action)
        seven_persist(g)
        await query.message.edit_text(seven_lobby_text(g,"تعداد نفرات را انتخاب کن و بقیه روی «شرکت در بازی» بزنند."),reply_markup=seven_lobby_keyboard(g),parse_mode="HTML")
        await query.answer(); return

    if action=="close":
        if uid!=g["creator_id"]:
            await query.answer("❌ فقط سازنده لابی می‌تواند لابی را ببندد.",show_alert=True); return
        await seven_finish_refund(g,"بستن لابی توسط سازنده")
        await query.answer("🔒 لابی بسته شد و ورودی‌ها برگشت داده شد.")
        return

    if action=="join":
        g,status=seven_join(gid,uid)
        if status=="self":
            await query.answer("😄 خودت سازنده‌ای و قبلاً وارد شدی.",show_alert=True); return
        if status=="funds":
            await query.answer("❌ موجودی آریورت برای ورود کافی نیست.",show_alert=True); return
        if status in ("closed","full"):
            await query.answer("❌ این لابی بسته یا پر شده است.",show_alert=True); return
        seven_persist(g)
        if len(g["players"])==g["max_players"]:
            await seven_start_after_lobby(g)
            await query.answer("🎮 وارد شدی؛ بازی شروع شد!")
            return
        await query.message.edit_text(seven_lobby_text(g),reply_markup=seven_lobby_keyboard(g),parse_mode="HTML")
        await query.answer("🎮 وارد بازی شدی!")


@dp.callback_query(F.data=="seven:turn")
async def seven_turn_info(query: CallbackQuery):
    # Find the active game containing this user.
    g=next((x for x in SEVEN_GAMES.values() if x.get("status") in ("active","waiting") and query.from_user.id in x.get("players",[])),None)
    if not g: await query.answer("❌ بازی هفت خبیث فعالی نداری.",show_alert=True); return
    uid=g["players"][g["turn_index"]] if g.get("status")=="active" else None
    if uid==query.from_user.id: await query.answer("🟢 نوبت توعه",show_alert=True)
    elif uid: await query.answer(f"🎯 نوبت {display_name_by_id(uid)}",show_alert=True)
    else: await query.answer(f"👥 {len(g['players'])}/{g['max_players']}",show_alert=True)


@dp.callback_query(F.data.startswith("seven:draw:"))
async def seven_draw_callback(query: CallbackQuery):
    try: gid=int(query.data.split(":")[2])
    except Exception: await query.answer("❌ بازی نامعتبر است.",show_alert=True); return
    g=seven_get_game(gid); uid=query.from_user.id
    if not g or g.get("status")!="active" or uid not in g["players"]: await query.answer("❌ این بازی برای شما فعال نیست.",show_alert=True); return
    lock=SEVEN_LOCKS.setdefault(gid,asyncio.Lock())
    async with lock:
        if uid!=g["turn_uid"]: await query.answer("⏳ الان نوبت شما نیست.",show_alert=True); return
        if g.get("pending_jack_uid")==uid:
            await query.answer("🃏 اول خال جک را انتخاب کن.",show_alert=True); return
        g.setdefault("missed_turns",{})[str(uid)]=0
        penalty=g.get("penalty",0)
        if penalty:
            drawn=seven_draw_one(g,uid,penalty); g["penalty"]=0; seven_move_to_next(g)
            notice=f"🔥 {seven_player_name(uid)} جریمه را گرفت: {len(drawn)} کارت.\n➡️ نوبت {seven_player_name(g['turn_uid'])} شد."
        elif g.get("pending_bonus"):
            drawn=seven_draw_one(g,uid,1); g["pending_bonus"]=False; seven_move_to_next(g)
            notice=f"⚠️ {seven_player_name(uid)} کارت جایزه نداشت؛ {len(drawn)} کارت کشید و نوبتش رد شد."
        else:
            drawn=seven_draw_one(g,uid,1); seven_move_to_next(g)
            notice=f"🎴 {seven_player_name(uid)} یک کارت کشید.\n➡️ نوبت {seven_player_name(g['turn_uid'])} شد."
        seven_persist(g); await query.answer("🎴 کارت کشیده شد")
        if await seven_finish_if_empty(g,uid):
            return
        await seven_public_update(g,notice); await seven_refresh_private(g,notice); seven_schedule_timer(g)


@dp.callback_query(F.data.startswith("seven:play:"))
async def seven_play_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: gid=int(parts[2]); index=int(parts[3])
    except Exception: await query.answer("❌ کارت نامعتبر است.",show_alert=True); return
    g=seven_get_game(gid); uid=query.from_user.id
    if not g or g.get("status")!="active" or uid not in g["players"]: await query.answer("❌ این بازی برای شما فعال نیست.",show_alert=True); return
    lock=SEVEN_LOCKS.setdefault(gid,asyncio.Lock())
    async with lock:
        if uid!=g["turn_uid"]: await query.answer("⏳ الان نوبت شما نیست.",show_alert=True); return
        try: await query.answer("🎴 در حال ثبت حرکت...")
        except Exception: pass
        # If a Jack is awaiting suit selection, no second card can be played.
        if g.get("pending_jack_uid")==uid: await query.answer("🃏 اول خال جک را انتخاب کن.",show_alert=True); return
        # Use chosen suit from Jack as active suit override.
        hand=g["hands"].get(str(uid),[])
        if index<0 or index>=len(hand): await query.answer("❌ این کارت دیگر در دستت نیست.",show_alert=True); return
        card=hand[index]
        if g.get("penalty",0)>0:
            if seven_card_rank(card)!="7": await query.answer("🔥 فقط ۷ می‌تواند جریمه را ادامه دهد؛ یا «کشیدن» را بزن.",show_alert=True); return
        active=g["active_card"]
        override=g.get("active_suit_override")
        playable=(seven_is_joker(card) or seven_card_rank(card)=="J")
        if not playable:
            playable=(seven_card_rank(card)==seven_card_rank(active) or seven_card_suit(card)==active.split("|",1)[1] if not seven_is_joker(active) else True)
        if override and not seven_is_joker(card):
            playable = seven_card_suit(card)==override or seven_card_rank(card)==seven_card_rank(active)
        if not playable:
            await query.answer("❌ این کارت قابل بازی نیست؛ باید هم‌خال یا هم‌شماره باشد.",show_alert=True); return
        ok,why,notice=seven_play_card(g,uid,index)
        if not ok: await query.answer("❌ این کارت قابل بازی نیست.",show_alert=True); return
        g.setdefault("missed_turns",{})[str(uid)]=0
        # Clear override once a normal card is played; Jack sets a new one after selection.
        if seven_card_rank(card)!="J": g["active_suit_override"]=None
        seven_persist(g)
        if await seven_finish_if_empty(g,uid):
            return
        await seven_public_update(g,notice); await seven_refresh_private(g,notice)
        if g.get("pending_jack_uid"):
            suit_msg=await bot.send_message(uid,"🃏 خال جدید را انتخاب کن:",reply_markup=keyboard([[button("♥️ دل","seven:suit:♥️"),button("♦️ خشت","seven:suit:♦️")],[button("♣️ گشنیز","seven:suit:♣️"),button("♠️ پیک","seven:suit:♠️")]]))
            g.setdefault("extra_private_messages",{}).setdefault(str(uid),[]).append(suit_msg.message_id)
            seven_persist(g)
        else:
            seven_schedule_timer(g)


@dp.callback_query(F.data.startswith("seven:surrender:"))
async def seven_surrender_callback(query: CallbackQuery):
    try: gid=int(query.data.split(":")[2])
    except Exception: await query.answer("❌ بازی نامعتبر است.",show_alert=True); return
    g=seven_get_game(gid); uid=query.from_user.id
    if not g or g.get("status")!="active" or uid not in g["players"]:
        await query.answer("❌ این بازی برای شما فعال نیست.",show_alert=True); return
    lock=SEVEN_LOCKS.setdefault(gid,asyncio.Lock())
    async with lock:
        removed,next_uid=seven_remove_player(g,uid,"تسلیم شدن")
        if not removed:
            await query.answer("❌ انصراف انجام نشد.",show_alert=True); return
        notice=f"🏳️ {seven_player_name(uid)} از بازی تسلیم شد و از بازی خارج شد.\n💎 مبلغ شرط او برگشت داده نمی‌شود."
        winner=await seven_try_finish_after_elimination(g)
        if winner:
            # Finish helper already deleted all game messages and sent the PV winner notice.
            await query.answer("🏳️ از بازی خارج شدی")
            return
        elif next_uid:
            notice+=f"\n➡️ نوبت {seven_player_name(next_uid)} شد."
        seven_persist(g)
        await query.answer("🏳️ از بازی خارج شدی")
        await seven_public_update(g,notice)
        seven_schedule_timer(g)
        try: await seven_send_private(g,uid,notice+"\n❌ شما دیگر در این بازی نیستید.")
        except Exception: pass
        await seven_refresh_private(g,notice)


@dp.callback_query(F.data.startswith("seven:suit:"))
async def seven_suit_callback(query: CallbackQuery):
    suit=query.data.split(":",2)[2]
    uid=query.from_user.id
    g=next((x for x in SEVEN_GAMES.values() if x.get("status")=="active" and x.get("pending_jack_uid")==uid),None)
    if not g or suit not in SEVEN_SUITS: await query.answer("❌ انتخاب خال نامعتبر است.",show_alert=True); return
    lock=SEVEN_LOCKS.setdefault(g["id"],asyncio.Lock())
    async with lock:
        if not seven_jack_choose(g,uid,suit): await query.answer("❌ انتخاب خال انجام نشد.",show_alert=True); return
        for prompt_mid in list(g.get("extra_private_messages",{}).get(str(uid),[]) or []):
            try: await bot.delete_message(uid,prompt_mid)
            except Exception: pass
        g.get("extra_private_messages",{}).pop(str(uid),None)
        g["active_suit_override"]=suit
        # The displayed background becomes the selected-suit Jack (e.g. J♥️).
        g["active_card"]=f"J|{suit}"
        notice=f"🃏 {seven_player_name(uid)} سرباز بازی کرد و خال را {suit} انتخاب کرد.\n➡️ نوبت {seven_player_name(g['turn_uid'])} شد."
        seven_persist(g)
        await query.message.edit_text(f"✅ خال جدید: {suit}\n⏭️ نوبت {seven_player_name(g['turn_uid'])} شد.",parse_mode="HTML")
        await query.answer("✅ خال انتخاب شد")
        await seven_public_update(g,notice)
        await seven_refresh_private(g,notice); seven_schedule_timer(g)

@dp.callback_query(F.data.startswith("wager:join:"))
async def wager_join_callback(query: CallbackQuery):
    try: wid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ بازی نامعتبر است.",show_alert=True); return
    w, status=join_wager(wid,query.from_user.id)
    if status=="missing":
        await query.answer("❌ این بازی پیدا نشد.",show_alert=True); return
    if status=="closed":
        await query.answer("❌ این بازی قبلاً شروع یا تمام شده.",show_alert=True); return
    if status=="expired":
        await refund_wager(wid)
        await query.answer("⏰ زمان شرکت تمام شده.",show_alert=True); return
    if status=="self":
        await query.answer("😄 خودت سازنده بازی هستی؛ نفر دوم باید شرکت کند.",show_alert=True); return
    if status=="funds":
        await query.answer("❌ موجودی آریورت برای ورود کافی نیست.",show_alert=True); return
    try:
        await query.message.edit_text(
            f"🎮 {WAGER_GAME_NAMES[w['game_type']]} شروع شد!\n\n"
            f"👤 بازیکن اول: {display_name_by_id(w['creator_id'])}\n"
            f"👤 بازیکن دوم: {display_name_by_id(w['opponent_id'])}\n"
            f"💎 ورودی هر نفر: {format_coins(w['stake'])} آریور\n"
            f"🏆 جایزه برنده: {format_coins(w['stake']*2)} آریور"
        )
    except Exception:
        pass
    await query.answer("🎮 وارد بازی شدی!")
    await start_wager_game(w)

@dp.callback_query(F.data.startswith("wager:dooz:"))
async def wager_dooz_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: wid=int(parts[2]); idx=int(parts[3])
    except Exception:
        await query.answer("❌ حرکت نامعتبر.",show_alert=True); return
    w=wager_games.get(wid)
    if not w or w.get("status")!="active":
        await query.answer("❌ بازی فعال نیست.",show_alert=True); return
    if query.from_user.id not in (w["creator_id"],w["opponent_id"]):
        await query.answer("❌ شما بازیکن این بازی نیستی.",show_alert=True); return
    if query.from_user.id != w.get("turn"):
        await query.answer("⏳ الان نوبت شما نیست.",show_alert=True); return
    board=w["board"]
    if not 0<=idx<9 or board[idx]:
        await query.answer("❌ این خانه پر است.",show_alert=True); return
    mark="🟢" if query.from_user.id==w["creator_id"] else "🔴"
    board[idx]=mark
    refresh_wager_timeout(wid)
    result=dooz_winner(board)
    if result:
        if result=="draw":
            finish_wager(wid,draw=True)
            text="🤝 دوز مساوی شد!\n💎 ورودی هر دو نفر برگشت داده شد.\n\n"+wager_ids_text(w)
        else:
            # Dooz uses the same marks that are written onto the board.
            # The old code compared against ⭕, while the callback writes 🟢/🔴,
            # which caused every completed game to award the opponent.
            winner=w["creator_id"] if result=="🟢" else w["opponent_id"]
            finish_wager(wid,winner)
            text=f"🏆 برنده دوز: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور\n\n{wager_ids_text(w)}"
        await query.message.edit_text(text, parse_mode="HTML")
    else:
        w["turn"]=w["opponent_id"] if query.from_user.id==w["creator_id"] else w["creator_id"]
        await query.message.edit_text(
            f"🟢🔴 دوز — نوبت {mention_by_id(w['turn'])}\n💎 جایزه فعلی: {format_coins(w['stake']*2)} آریور\n\n{wager_ids_text(w)}",
            reply_markup=dooz_keyboard(wid), parse_mode="HTML"
        )
    await query.answer()

@dp.callback_query(F.data.startswith("wager:rps:"))
async def wager_rps_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: wid=int(parts[2]); choice=parts[3]
    except Exception:
        await query.answer("❌ انتخاب نامعتبر.",show_alert=True); return
    w=wager_games.get(wid)
    if not w or w.get("status")!="active":
        await query.answer("❌ بازی فعال نیست.",show_alert=True); return
    if query.from_user.id not in (w["creator_id"],w["opponent_id"]):
        await query.answer("❌ شما بازیکن این بازی نیستی.",show_alert=True); return
    w.setdefault("choices",{})[query.from_user.id]=choice
    refresh_wager_timeout(wid)
    await query.answer("✅ انتخاب ثبت شد.")
    if len(w["choices"])<2: return
    a=w["choices"][w["creator_id"]]; b=w["choices"][w["opponent_id"]]
    winmap={"rock":"scissors","scissors":"paper","paper":"rock"}
    if a==b: winner=None
    elif winmap[a]==b: winner=w["creator_id"]
    else: winner=w["opponent_id"]
    finish_wager(wid,winner,draw=winner is None)
    names={"rock":"✊ سنگ","paper":"📄 کاغذ","scissors":"✂️ قیچی"}
    text=f"✊✋✌️ نتیجه بازی\n\n👤 اول: {names[a]}\n👤 دوم: {names[b]}\n\n{wager_ids_text(w)}\n\n"
    text += "🤝 مساوی شد؛ ورودی‌ها برگشت." if winner is None else f"🏆 برنده: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور"
    await query.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(F.data.startswith("wager:evenodd:"))
async def wager_evenodd_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: wid=int(parts[2]); choice=parts[3]
    except Exception:
        await query.answer("❌ انتخاب نامعتبر.",show_alert=True); return
    w=wager_games.get(wid)
    if not w or w.get("status")!="active":
        await query.answer("❌ بازی فعال نیست.",show_alert=True); return
    if query.from_user.id not in (w["creator_id"],w["opponent_id"]):
        await query.answer("❌ شما بازیکن این بازی نیستی.",show_alert=True); return
    w.setdefault("choices",{})[query.from_user.id]=choice
    await query.answer("✅ انتخاب ثبت شد.")
    if len(w["choices"])<2: return
    if w["choices"][w["creator_id"]]==w["choices"][w["opponent_id"]]:
        finish_wager(wid,draw=True)
        await query.message.edit_text("🤝 هر دو یک گزینه را انتخاب کردند؛ ورودی‌ها برگشت.")
        return
    number=random.randint(1,100)
    winner_choice="even" if number%2==0 else "odd"
    winner=w["creator_id"] if w["choices"][w["creator_id"]]==winner_choice else w["opponent_id"]
    finish_wager(wid,winner)
    await query.message.edit_text(f"🎯 عدد قرعه: {number} — {'زوج 🔵' if winner_choice=='even' else 'فرد 🟣'}\n\n🏆 برنده: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور\n\n{wager_ids_text(w)}", parse_mode="HTML")

@dp.callback_query(F.data.startswith("wager:guess:"))
async def wager_guess_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: wid=int(parts[2])
    except Exception: await query.answer("❌ بازی نامعتبر است.",show_alert=True); return
    w=wager_games.get(wid)
    if not w or w.get("status")!="active": await query.answer("❌ بازی فعال نیست.",show_alert=True); return
    if len(parts)>=5 and parts[3]=="secret":
        value=int(parts[4])
        if query.from_user.id!=w["creator_id"]: await query.answer("🎯 فقط سازنده عدد مخفی را انتخاب می‌کند.",show_alert=True); return
        if w.get("target") is not None: await query.answer("⚠️ عدد مخفی قبلاً انتخاب شده.",show_alert=True); return
        w["target"]=value
        refresh_wager_timeout(wid)
        await query.message.edit_text(f"🔢 عدد مخفی ثبت شد!\n\n{wager_ids_text(w)}\n\n🎯 {display_name_by_id(w['opponent_id'])} حالا حدس بزند.",reply_markup=keyboard([[button(str(i),f"wager:guess:{wid}:try:{i}") for i in range(1,6)],[button(str(i),f"wager:guess:{wid}:try:{i}") for i in range(6,11)]]))
        await query.answer("✅ ثبت شد")
        return
    if len(parts)>=5 and parts[3]=="try":
        guess=int(parts[4])
        if query.from_user.id!=w["opponent_id"]: await query.answer("🎯 فقط بازیکن دوم حدس می‌زند.",show_alert=True); return
        if w.get("target") is None: await query.answer("⏳ هنوز عدد مخفی انتخاب نشده.",show_alert=True); return
        winner=w["opponent_id"] if guess==w["target"] else w["creator_id"]
        target=w["target"]; finish_wager(wid,winner)
        await query.message.edit_text(f"🔢 عدد مخفی: {target}\n🎯 حدس بازیکن دوم: {guess}\n\n🏆 برنده: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور\n\n{wager_ids_text(w)}", parse_mode="HTML")
        await query.answer()


@dp.callback_query(F.data.startswith("wager:draw:"))
async def wager_draw_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: wid=int(parts[2])
    except Exception: await query.answer("❌ بازی نامعتبر است.",show_alert=True); return
    w=wager_games.get(wid)
    if not w or w.get("status")!="active" or query.from_user.id not in (w["creator_id"],w["opponent_id"]): await query.answer("❌ این بازی برای شما فعال نیست.",show_alert=True); return
    rolls=w.setdefault("rolls",{})
    if query.from_user.id in rolls: await query.answer("⚠️ انتخابت قبلاً ثبت شده.",show_alert=True); return
    typ=w["game_type"]; rolls[query.from_user.id]=random.randint(1,13) if typ=="cards" else random.randint(1,6) if typ=="dice" else random.randint(1,100)
    refresh_wager_timeout(wid)
    await query.answer("✅ ثبت شد")
    if len(rolls)<2: return
    a,b=rolls[w["creator_id"]],rolls[w["opponent_id"]]
    winner=w["creator_id"] if a>b else w["opponent_id"] if b>a else None
    finish_wager(wid,winner,draw=winner is None)
    unit="کارت" if typ=="cards" else "تاس" if typ=="dice" else "عدد"
    text=f"{unit}‌ها: {a} مقابل {b}\n\n{wager_ids_text(w)}\n\n" + ("🤝 مساوی شد؛ ورودی‌ها برگشت." if winner is None else f"🏆 برنده: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور")
    await query.message.edit_text(text, parse_mode="HTML")

@dp.callback_query(F.data.startswith("wager:blackjack:"))
async def wager_blackjack_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: wid=int(parts[2]); action=parts[3]
    except Exception: await query.answer("❌ حرکت نامعتبر.",show_alert=True); return
    w=wager_games.get(wid)
    if not w or w.get("status")!="active": await query.answer("❌ بازی فعال نیست.",show_alert=True); return
    uid=query.from_user.id
    if uid!=w.get("bj_turn"): await query.answer("⏳ الان نوبت شما نیست.",show_alert=True); return
    hand=w["hands"][uid]; total=sum(hand)
    if action=="hit":
        if not w["deck"]: w["deck"]= [1,2,3,4,5,6,7,8,9,10,10,10,10]*4; random.shuffle(w["deck"])
        hand.append(w["deck"].pop()); total=sum(hand)
        refresh_wager_timeout(wid)
        if total>21:
            winner=w["opponent_id"] if uid==w["creator_id"] else w["creator_id"]; finish_wager(wid,winner)
            await query.message.edit_text(f"🃏 {display_name_by_id(uid)} از ۲۱ عبور کرد.\n🏆 برنده: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور\n\n{wager_ids_text(w)}", parse_mode="HTML"); await query.answer(); return
        await query.message.edit_text(f"🃏 نوبت {display_name_by_id(uid)}\n🎴 دست: {total}",reply_markup=keyboard([[button("🃏 کارت بگیر",f"wager:blackjack:{wid}:hit"),button("✋ ایست",f"wager:blackjack:{wid}:stand")]])); await query.answer(); return
    w["stood"][uid]=True
    refresh_wager_timeout(wid)
    other=w["opponent_id"] if uid==w["creator_id"] else w["creator_id"]
    if w["stood"].get(other):
        a=sum(w["hands"][w["creator_id"]]); b=sum(w["hands"][w["opponent_id"]]); winner=w["creator_id"] if a>b else w["opponent_id"] if b>a else None
        finish_wager(wid,winner,draw=winner is None)
        await query.message.edit_text(f"🃏 پایان بلک‌جک\n👤 {display_name_by_id(w['creator_id'])}: {a}\n👤 {display_name_by_id(w['opponent_id'])}: {b}\n\n{wager_ids_text(w)}\n\n"+("🤝 مساوی؛ ورودی‌ها برگشت." if winner is None else f"🏆 برنده: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور"), parse_mode="HTML"); await query.answer(); return
    w["bj_turn"]=other
    await query.message.edit_text(f"🃏 نوبت {display_name_by_id(other)}\n🎴 دست فعلی: {sum(w['hands'][other])}\n\n{wager_ids_text(w)}",reply_markup=keyboard([[button("🃏 کارت بگیر",f"wager:blackjack:{wid}:hit"),button("✋ ایست",f"wager:blackjack:{wid}:stand")]])); await query.answer()

@dp.callback_query(F.data.startswith("wager:quickmath:"))
async def wager_quickmath_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: wid=int(parts[2]); answer=int(parts[3])
    except Exception: await query.answer("❌ پاسخ نامعتبر.",show_alert=True); return
    w=wager_games.get(wid)
    if not w or w.get("status")!="active": await query.answer("❌ بازی فعال نیست.",show_alert=True); return
    if answer!=w.get("math_answer"):
        await query.answer("❌ جواب اشتباهه! سریع‌تر دوباره امتحان کن.",show_alert=True); return
    winner=query.from_user.id
    if winner not in (w["creator_id"],w["opponent_id"]): await query.answer("❌ شما بازیکن این بازی نیستی.",show_alert=True); return
    elapsed=max(0,time.time()-w.get("math_started",time.time())); refresh_wager_timeout(wid); finish_wager(wid,winner)
    await query.message.edit_text(f"⚡ پاسخ درست ثبت شد!\n⏱️ زمان پاسخ: {elapsed:.2f} ثانیه\n🏆 برنده سرعت: {mention_by_id(winner)}\n💎 جایزه: {format_coins(w['stake']*2)} آریور\n\n{wager_ids_text(w)}", parse_mode="HTML")
    await query.answer("🏆 بردی!")

@dp.callback_query(F.data.startswith("combat:join:"))
async def combat_join_callback(query: CallbackQuery):
    try: bid=int(query.data.rsplit(":",1)[1])
    except Exception: await query.answer("❌ مبارزه نامعتبر است.",show_alert=True); return
    b,status=combat_join(bid,query.from_user.id)
    if status=="missing": await query.answer("❌ مبارزه پیدا نشد.",show_alert=True); return
    if status=="closed": await query.answer("❌ این مبارزه دیگر فعال نیست.",show_alert=True); return
    if status=="self": await query.answer("😄 خودت سازنده‌ای؛ نفر دوم باید شرکت کند.",show_alert=True); return
    if status=="funds": await query.answer("❌ موجودی آریورت برای ورود کافی نیست.",show_alert=True); return
    b=combat_get(bid); duel_init(bid)
    await query.message.edit_text(duel_text(bid,"🚦 مبارزه شروع شد؛ نوبت نفر اول است."),reply_markup=duel_keyboard(bid),parse_mode="HTML")
    await query.answer("🥊 مبارزه شروع شد!")

@dp.callback_query(F.data.startswith("combat:action:"))
async def combat_action_callback(query: CallbackQuery):
    parts=query.data.split(":")
    try: bid=int(parts[2]); action=parts[3]
    except Exception: await query.answer("❌ حرکت نامعتبر است.",show_alert=True); return
    lock=combat_action_locks.setdefault(bid,asyncio.Lock())
    async with lock:
        b=combat_get(bid); d=duel_get(bid)
        if not b or b["status"]!="active" or not d: await query.answer("❌ مبارزه تمام شده.",show_alert=True); return
        uid=query.from_user.id
        if uid not in (b["creator_id"],b["opponent_id"]): await query.answer("❌ شما بازیکن این مبارزه نیستی.",show_alert=True); return
        if uid!=d["turn_user"]: await query.answer("⏳ الان نوبت حریف است؛ صبر کن.",show_alert=True); return
        result,status=duel_action(bid,uid,action)
        if status!="ok": await query.answer("❌ حرکت انجام نشد.",show_alert=True); return
        if result["finished"]:
            text=(f"🏁 مبارزه تمام شد!\\n\\n🏆 برنده: {mention_by_id(result['winner'])}\\n"
                  f"💎 جایزه: {format_coins(result['pot'])} آریور\\n"
                  f"💥 آسیب نهایی: {result['damage']}\\n🛡️ آسیب خنثی‌شده: {result['blocked']}\\n"
                  f"❤️ وضعیت نهایی: {result['hp_a']} - {result['hp_b']}\\n\\n{combat_players_text(b)}")
            await query.message.edit_text(text,parse_mode="HTML")
            combat_action_locks.pop(bid,None); await query.answer("🏆 مبارزه تمام شد!"); return
        if action=="attack":
            action_text=f"⚔️ {mention_by_id(uid)} حمله کرد و {result['damage']} آسیب وارد کرد."
            if result.get("dodged"): action_text="💨 حمله جاخالی داده شد و آسیبی وارد نشد."
            if result.get("critical"): action_text += " 💥 ضربه بحرانی!"
            if result.get("blocked"): action_text+=f" 🛡️ {result['blocked']} آسیب خنثی شد."
            if result.get("counter"): action_text+=f" 🔁 {result['counter']} آسیب بازتاب داده شد."
        else:
            action_text=f"🛡️ {mention_by_id(uid)} دفاع کرد؛ {result['defense_pct']}٪ از حمله بعدی خنثی می‌شود."
        next_user=result["state"]["turn_user"]
        action_text+=f"\\n➡️ الان نوبت {mention_by_id(next_user)} است.\\n🚫 نوبت بازیکن دیگر نیست."
        await query.message.edit_text(duel_text(bid,action_text),reply_markup=duel_keyboard(bid),parse_mode="HTML")
        await query.answer("✅ حرکت ثبت شد؛ نوبت حریف شد.")

@dp.callback_query(F.data.startswith("combat:potions:"))
async def combat_potions_callback(query:CallbackQuery):
    try: bid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ مبارزه نامعتبر است.",show_alert=True); return
    b=combat_get(bid); d=duel_get(bid)
    if not b or b.get("status")!="active" or not d:
        await query.answer("❌ مبارزه تمام شده.",show_alert=True); return
    if query.from_user.id!=d.get("turn_user"):
        await query.answer("⏳ فقط در نوبت خودت می‌توانی معجون استفاده کنی.",show_alert=True); return
    await query.message.edit_text(
        "🧪 معجون‌های مبارزه\n\n۱۰ معجون اثرگذار + ۱۰ معجون دفاعی یک‌بارمصرف\nهر بار استفاده، همان واحد از کوله‌پشتی کم می‌شود.\nمعجون دفاعی فقط برای همین نبرد مصرف می‌شود.\n\nیکی را انتخاب کن:",
        reply_markup=combat_potion_keyboard(bid,query.from_user.id))
    await query.answer()

@dp.callback_query(F.data.startswith("combat:potion:"))
async def combat_potion_use_callback(query:CallbackQuery):
    parts=query.data.split(":")
    try: bid=int(parts[2]); code=int(parts[3])
    except Exception:
        await query.answer("❌ آیتم نامعتبر است.",show_alert=True); return
    b=combat_get(bid); d=combat_states.get(bid) or duel_get(bid)
    if not b or b.get("status")!="active" or not d:
        await query.answer("❌ مبارزه تمام شده.",show_alert=True); return
    uid=query.from_user.id
    if uid!=d.get("turn_user"):
        await query.answer("⏳ الان نوبت تو نیست.",show_alert=True); return
    all_items=list(COMBAT_POTIONS)+list(COMBAT_DEFENSE_POTIONS)
    if code<0 or code>=len(all_items):
        await query.answer("❌ آیتم نامعتبر.",show_alert=True); return
    item=all_items[code]
    ok,msg=add_combat_potion_effect(d,uid,item)
    if not ok:
        await query.answer("❌ "+msg,show_alert=True); return
    # Persist the consumed potion state immediately so simultaneous clicks cannot duplicate it.
    combat_states[bid]=dict(d)
    payload=json.dumps({"potion_effects":d.get("potion_effects",{}),"defense_potion":d.get("defense_potion",{})},ensure_ascii=False,separators=(",",":"))
    with db() as c:
        c.execute("UPDATE combat_duels SET potion_state=? WHERE battle_id=?",(payload,bid)); c.commit()
    await query.answer("🧪 معجون مصرف شد!")
    await query.message.edit_text(duel_text(bid,f"🧪 {item} استفاده شد: {msg}"),reply_markup=duel_keyboard(bid),parse_mode="HTML")

@dp.callback_query(F.data.startswith("combat:potionback:"))
async def combat_potion_back_callback(query:CallbackQuery):
    try: bid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer(); return
    await query.message.edit_text(duel_text(bid),reply_markup=duel_keyboard(bid),parse_mode="HTML")
    await query.answer()

@dp.callback_query(F.data=="user:blackshop")
async def user_blackshop(query: CallbackQuery):
    global _black_shop_view_uid
    _black_shop_view_uid=menu_owner_id(query)
    await query.message.edit_text(black_shop_text(),reply_markup=black_shop_keyboard()); await query.answer()


@dp.callback_query(F.data.startswith("blackshop:buy:"))
async def blackshop_buy_callback(query: CallbackQuery):
    try:
        idx=int(query.data.rsplit(":",1)[1])
        item=list(BLACK_SHOP_ITEMS.keys())[idx-1]
    except Exception:
        await query.answer("❌ آیتم نامعتبر است.",show_alert=True); return
    ok,why,cost=black_shop_buy(menu_owner_id(query),item)
    if not ok:
        if why=="owned": msg="🎒 این آیتم را از قبل در کوله‌پشتی داری؛ خرید دوباره مجاز نیست."
        elif why=="max": msg="🏆 این آیتم به حداکثر سطح خودش رسیده است."
        elif why=="funds": msg=f"❌ {format_coins(cost)} آریور لازم داری."
        else: msg="❌ آیتم پیدا نشد."
        await query.answer(msg,show_alert=True); return
    await query.answer(f"✅ {item} خریداری/ارتقا داده شد!")
    global _black_shop_view_uid
    _black_shop_view_uid=menu_owner_id(query)
    try:
        await query.message.edit_text(black_shop_text(), reply_markup=black_shop_keyboard())
    except Exception as exc:
        # Telegram returns "message is not modified" when the rendered message
        # and keyboard are already identical. This is harmless.
        if "message is not modified" not in str(exc).lower():
            raise

@dp.callback_query(F.data=="user:combat")
async def user_combat(query: CallbackQuery):
    await query.message.edit_text("🥊 مبارزه نوبتی ⚔️\n\nفرمت: «مبارزه 1000» در گروه\n❤️ هر نفر 100 جان دارد.\n⚔️ حمله = آسیب بر اساس سلاح‌های خریداری‌شده\n🛡️ دفاع = با تجهیزات دفاعی فروشگاه سیاه، ۱۰ تا ۵۰٪ حمله بعدی خنثی می‌شود\n🏆 برنده کل دو ورودی را می‌گیرد.\n⏳ هر نوبت ۶۰ ثانیه فرصت دارد.",reply_markup=keyboard([[button("🕶️ فروشگاه سیاه","user:blackshop")],[button("🎒 تجهیزات من","user:inventory")],[button("🔙 برگشت","user:menu")]])); await query.answer()

@dp.callback_query(F.data=="user:petshop")
async def user_petshop(query: CallbackQuery):
    await query.message.edit_text(pet_shop_text(menu_owner_id(query)), reply_markup=pet_shop_keyboard(menu_owner_id(query))); await query.answer()

@dp.callback_query(F.data=="user:pets")
async def user_pets(query: CallbackQuery):
    uid=menu_owner_id(query); active=active_pet(uid)
    owned=[p for p in PETS if inventory_qty(uid,p)>0]
    text="🐾 حیوانات من\n\n"
    if not owned: text += "هنوز حیوانی نداری. از فروشگاه حیوانات یکی تهیه کن. 🛒"
    else:
        for pet in owned:
            text += f"{'✅' if active==pet else '⚪'} {pet} — {pet_effect_description(pet)}\n"
        text += f"\n🐾 حیوان فعال: {active or 'هیچ‌کدام'}"
    rows=[]
    for i,pet in enumerate(owned,1):
        if active==pet: rows.append([button(f"❌ غیرفعال {pet}",f"pet:ownedoff:{i}")])
        else: rows.append([button(f"✅ فعال کردن {pet}",f"pet:ownedon:{i}")])
    rows.append([button("🛍️ فروشگاه حیوانات","user:petshop"),button("🔙 برگشت","user:menu")])
    await query.message.edit_text(text,reply_markup=keyboard(rows)); await query.answer()

def _owned_pet_by_index(uid, idx):
    owned=[p for p in PETS if inventory_qty(uid,p)>0]
    return owned[idx-1] if 1<=idx<=len(owned) else None

@dp.callback_query(F.data.startswith("pet:buy:"))
async def pet_buy_callback(query: CallbackQuery):
    try: idx=int(query.data.rsplit(":",1)[1]); pet=list(PETS)[idx-1]
    except Exception: await query.answer("❌ حیوان نامعتبر است.",show_alert=True); return
    cost=get_price(price_key_for("pets", pet), PETS[pet][0])
    if inventory_qty(menu_owner_id(query),pet)>0: await query.answer("🐾 این حیوان را داری.",show_alert=True); return
    if get_balance(menu_owner_id(query))<cost: await query.answer(f"❌ {format_coins(cost)} آریور لازم داری.",show_alert=True); return
    add_coins(menu_owner_id(query),-cost); add_item(menu_owner_id(query),pet,1); log_tx(menu_owner_id(query),"pet_buy",-cost,pet)
    set_active_pet(menu_owner_id(query),pet)
    await query.answer(f"🐾 {pet} خریداری و فعال شد!"); await user_petshop(query)

@dp.callback_query(F.data.startswith("pet:on:"))
async def pet_on_callback(query: CallbackQuery):
    try: pet=list(PETS)[int(query.data.rsplit(":",1)[1])-1]
    except Exception: await query.answer("❌ حیوان نامعتبر.",show_alert=True); return
    if not set_active_pet(menu_owner_id(query),pet): await query.answer("❌ این حیوان را نداری.",show_alert=True); return
    await query.answer(f"✅ {pet} فعال شد!"); await user_petshop(query)

@dp.callback_query(F.data.startswith("pet:off:"))
async def pet_off_callback(query: CallbackQuery):
    set_active_pet(menu_owner_id(query),""); await query.answer("🐾 حیوان غیرفعال شد."); await user_petshop(query)

@dp.callback_query(F.data.startswith("pet:ownedon:"))
async def pet_owned_on_callback(query: CallbackQuery):
    try: pet=_owned_pet_by_index(menu_owner_id(query),int(query.data.rsplit(":",1)[1]))
    except Exception: pet=None
    if not pet: await query.answer("❌ حیوان نامعتبر.",show_alert=True); return
    set_active_pet(menu_owner_id(query),pet); await query.answer(f"✅ {pet} فعال شد!"); await user_pets(query)

@dp.callback_query(F.data.startswith("pet:ownedoff:"))
async def pet_owned_off_callback(query: CallbackQuery):
    set_active_pet(menu_owner_id(query),""); await query.answer("🐾 حیوان غیرفعال شد."); await user_pets(query)

@dp.callback_query(F.data=="user:champion")
async def user_champion(query: CallbackQuery):
    ch=champion_record(menu_owner_id(query))
    await query.message.edit_text(f"👑 سیستم قهرمان\n\n👤 {display_name_by_id(menu_owner_id(query))}\n🏆 قهرمانی‌ها: {ch['titles']}\n⚔️ بردهای ثبت‌شده: {ch['wins']}\n💪 بیشترین قدرت ثبت‌شده: {ch['best_power']}\n\nبا قهرمانی در تورنمنت، رکورد قهرمانی شما افزایش پیدا می‌کند. 🔥",reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:rank")
async def user_rank(query:CallbackQuery):
    rank,points=player_rank(menu_owner_id(query)); st=player_stats(menu_owner_id(query))
    await query.message.edit_text(f"🥇 رنک و لیگ\n\n🏆 {rank}\n⭐ امتیاز: {points}\n🔥 بهترین استریک: {st['best_streak']}\n\nهر برد ۲۵ امتیاز می‌دهد؛ مساوی ۵ امتیاز و باخت ۱۰ امتیاز کم می‌کند.",reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:stats")
async def user_stats(query:CallbackQuery):
    uid=menu_owner_id(query); st=player_stats(uid); rank,points=player_rank(uid)
    wr=(st["wins"]*100//st["games"]) if st["games"] else 0
    await query.message.edit_text(f"📊 آمار کامل بازیکن\n\n🏆 رنک: {rank}\n⭐ امتیاز: {points}\n🎮 بازی‌ها: {st['games']}\n🏆 برد: {st['wins']}\n💔 باخت: {st['losses']}\n🤝 مساوی: {st['draws']}\n📈 درصد برد: {wr}%\n💰 بهترین جایزه: {format_coins(st['best_win'])} آریور\n🧠 XP: {st['xp']}\n👑 خاله‌بازی: {aunt_record(uid)['games_count']} بار",reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:achievements")
async def user_achievements(query:CallbackQuery):
    owned=set(achievements_list(menu_owner_id(query))); lines=[]
    for code,(name,desc,target) in ACHIEVEMENT_DEFS.items(): lines.append(f"{'✅' if code in owned else '🔒'} {name} — {desc}")
    await query.message.edit_text("🏅 دستاوردها\n\n"+"\n".join(lines),reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:inventory")
async def user_inventory(query:CallbackQuery):
    await query.message.edit_text(inventory_text(menu_owner_id(query)),reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:tournament")
async def user_tournament_help(query:CallbackQuery):
    await query.message.edit_text("🏆 تورنمنت ۸ نفره\n\n👥 ظرفیت: ۸ بازیکن\n💎 ورودی هر نفر: مبلغی که سازنده تعیین می‌کند\n🏆 کل ورودی‌ها جایزه نهایی است.\n🥊 ساختار: یک‌چهارم نهایی → نیمه‌نهایی → فینال\n⏳ اگر تا ۱۲۰ ثانیه ظرفیت کامل نشود، ورودی‌ها به شرکت‌کنندگان برمی‌گردد.\n\n📌 دستور: تورنمنت 1000",reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data.startswith("tournament:join:"))
async def tournament_join_callback(query:CallbackQuery):
    try: tid=int(query.data.rsplit(":",1)[1])
    except Exception: await query.answer("❌ تورنمنت نامعتبر است.",show_alert=True); return
    t,status=tournament_join(tid,menu_owner_id(query))
    if status=="funds": await query.answer("❌ موجودی کافی نیست.",show_alert=True); return
    if status=="self": await query.answer("😄 خودت قبلاً وارد شدی.",show_alert=True); return
    if status=="full": await query.answer("❌ ظرفیت پر است.",show_alert=True); return
    if status=="expired": await query.answer("⏰ زمان ثبت‌نام تمام شده.",show_alert=True); return
    if status=="closed": await query.answer("❌ تورنمنت بسته شده.",show_alert=True); return
    ps=tournament_players(tid); await query.answer(f"✅ وارد شدی! {len(ps)}/8 نفر")
    try: await query.message.edit_text(f"🏆 تورنمنت در حال ثبت‌نام است!\n\n👥 بازیکنان: {len(ps)}/8\n💎 ورودی: {format_coins(t['stake'])} آریور\n🏆 جایزه فعلی: {format_coins(t['prize'])} آریور\n\n⏳ با تکمیل ۸ نفر، یک‌چهارم نهایی شروع می‌شود.",reply_markup=keyboard([[button("🏆 شرکت در تورنمنت",f"tournament:join:{tid}")]]))
    except Exception: pass
    if len(ps)>=8:
        await bot.send_message(t["chat_id"],f"🏆 تورنمنت #{tid} با ۸ بازیکن کامل شد!\n🥊 مرحله یک‌چهارم نهایی شروع می‌شود...")
        result=tournament_round(tid)
        if result and result[0]=="round":
            await bot.send_message(t["chat_id"],"🏆 نتایج مرحله یک‌چهارم نهایی:\n\n"+"\n".join(f"⚔️ {display_name_by_id(a)} ({pa} قدرت) × {display_name_by_id(b)} ({pb} قدرت) → 🏆 {mention_by_id(w)}" for a,b,w,l,pa,pb,chance in result[3])+"\n\n➡️ مرحله بعدی: نیمه‌نهایی", parse_mode="HTML")
            result2=tournament_round(tid)
            if result2 and result2[0]=="round":
                await bot.send_message(t["chat_id"],"🔥 نتایج نیمه‌نهایی:\n\n"+"\n".join(f"⚔️ {display_name_by_id(a)} ({pa} قدرت) × {display_name_by_id(b)} ({pb} قدرت) → 🏆 {mention_by_id(w)}" for a,b,w,l,pa,pb,chance in result2[3])+"\n\n➡️ فینال", parse_mode="HTML")
                result3=tournament_round(tid)
                if result3 and result3[0]=="final": await bot.send_message(t["chat_id"],f"👑 قهرمان تورنمنت #{tid}: {mention_by_id(result3[1])}\n💎 جایزه: {format_coins(result3[2])} آریور", parse_mode="HTML")

# ================================================================
# PROPERTY / BUILDING / DECORATION SYSTEM
# ================================================================
def property_region(region_id):
    for rid,name,price in PROPERTY_REGIONS:
        if rid==int(region_id):
            return rid,name,price
    return None

def property_land_price(region_id, area):
    row=property_region(region_id)
    return int(row[2])*int(area) if row else 0

def user_properties(uid, status=None):
    with db() as c:
        if status:
            return c.execute("SELECT id,region_id,region_name,area,land_price,status,purchased_at FROM properties WHERE user_id=? AND status=? ORDER BY id",(uid,status)).fetchall()
        return c.execute("SELECT id,region_id,region_name,area,land_price,status,purchased_at FROM properties WHERE user_id=? ORDER BY id",(uid,)).fetchall()

def property_by_id(pid, uid=None):
    with db() as c:
        if uid is None:
            r=c.execute("SELECT id,user_id,region_id,region_name,area,land_price,status,purchased_at FROM properties WHERE id=?",(pid,)).fetchone()
        else:
            r=c.execute("SELECT id,user_id,region_id,region_name,area,land_price,status,purchased_at FROM properties WHERE id=? AND user_id=?",(pid,uid)).fetchone()
    return r

def material_required_qty(material, area):
    for name,unit,base_qty,package_size,package_price,icon in BUILDING_MATERIALS:
        if name==material:
            return float(base_qty)*float(area)/100.0
    return 0.0

def material_price(material, area):
    required=material_required_qty(material,area)
    for name,unit,base_qty,package_size,package_price,icon in BUILDING_MATERIALS:
        if name==material:
            package_price=get_price(f"materials:{name}",package_price)
            packages=required/float(package_size)
            return int(round(packages*package_price))
    return 0

def material_qty_text(material, qty):
    for name,unit,base_qty,package_size,package_price,icon in BUILDING_MATERIALS:
        if name==material:
            if unit in ("تن","لیتر"):
                return f"{qty:g} {unit}"
            return f"{int(round(qty)):,} {unit}"
    return str(qty)

def property_material_status(pid, area):
    with db() as c:
        purchased={r[0]:int(r[1]) for r in c.execute("SELECT material,purchased FROM property_materials WHERE property_id=?",(pid,)).fetchall()}
    return [(name,unit,material_required_qty(name,area),material_price(name,area),bool(purchased.get(name,0)),icon) for name,unit,*_rest,icon in BUILDING_MATERIALS]

def all_materials_purchased(pid, area):
    rows=property_material_status(pid,area)
    return bool(rows) and all(x[4] for x in rows)

def maybe_build_property(pid):
    row=property_by_id(pid)
    if not row: return False
    if row[6] != "land": return row[6]=="house"
    if not all_materials_purchased(pid,row[4]): return False
    with db() as c:
        c.execute("UPDATE properties SET status='house' WHERE id=?",(pid,)); c.commit()
    return True

def property_text(row):
    pid,rid,name,area,land_price,status,purchased_at=row
    status_text="🏠 خانه" if status=="house" else "🌱 زمین خالی"
    return f"#{pid} {status_text} — منطقه {rid} ({name}) — {area} متر\n💰 قیمت زمین: {format_coins(land_price)} آریور"

def property_keyboard(rows, action="materials"):
    kb=[]
    # user_properties() هفت مقدار برای هر ملک برمی‌گرداند؛ قبلاً اینجا
    # شش مقدار unpack می‌شد و همین باعث باگ دکوراسیون/مصالح می‌شد.
    for pid,rid,name,area,land_price,status,purchased_at in rows:
        label=f"#{pid} {'🏠' if status=='house' else '🌱'} منطقه {rid} — {area}متر"
        kb.append([button(label,f"property:{action}:{pid}")])
    kb.append([button("🔙 برگشت به منو","user:menu"),button("❌ بستن منو","menu:close")])
    return keyboard(kb)

def property_regions_keyboard():
    rows=[]
    for rid,name,price in PROPERTY_REGIONS:
        current=get_price(f"property:region:{rid}",price)
        rows.append([button(f"منطقه {rid} ({name}) — متری {format_coins(current)} آریور",f"property:region:{rid}")])
    rows.append([button("🔙 برگشت به منو","user:menu"),button("❌ بستن منو","menu:close")])
    return keyboard(rows)

def property_sizes_keyboard(region_id):
    return keyboard([[button(f"{area} متر",f"property:size:{region_id}:{area}")] for area in PROPERTY_SIZES] + [[button("🔙 مناطق","user:property")],[button("❌ بستن منو","menu:close")]])

def material_keyboard(pid, area):
    rows=[]
    for name,unit,qty,cost,purchased,icon in property_material_status(pid,area):
        if purchased:
            label=f"✅ {icon} {name} — خریداری شد"
        else:
            label=f"🛒 {icon} {name} — {format_coins(cost)} آریور"
        rows.append([button(label,f"material:buy:{pid}:{BUILDING_MATERIALS.index(next(x for x in BUILDING_MATERIALS if x[0]==name))}")])
    rows.append([button("🔙 انتخاب زمین/خانه","user:materials"),button("🏠 دارایی‌ها","user:assets")])
    rows.append([button("❌ بستن منو","menu:close")])
    return keyboard(rows)

def decoration_price(item):
    for name,price,cat in DECORATION_ITEMS:
        if name==item: return get_price(f"decor:{name}",price)
    return 0

def decoration_qty(pid,item):
    with db() as c:
        r=c.execute("SELECT quantity FROM property_decor WHERE property_id=? AND item=?",(pid,item)).fetchone()
    return int(r[0] or 0) if r else 0

def decoration_is_upgradeable(item):
    return item in ("تخت خواب","میز تحریر","میز مطالعه")

def decor_keyboard(pid):
    rows=[]
    for i,(item,default,cat) in enumerate(DECORATION_ITEMS):
        q=decoration_qty(pid,item); price=decoration_price(item)
        suffix=f" | تعداد {q}" if q else ""
        rows.append([button(f"🛋️ {item} — {format_coins(price)} آریور{suffix}",f"decor:buy:{pid}:{i}")])
    rows.append([button("🔙 انتخاب خانه","user:decor"),button("💼 دارایی‌ها","user:assets")])
    rows.append([button("❌ بستن منو","menu:close")])
    return keyboard(rows)

def property_assets_text(uid):
    rows=user_properties(uid)
    if not rows: return "💼 دارایی‌های شما\n\n🌱 هنوز هیچ زمینی خریداری نکرده‌ای."
    houses=sum(1 for r in rows if r[5]=="house")
    lands=len(rows)-houses
    lines=[f"💼 دارایی‌های شما\n\n🏠 خانه‌ها: {houses}\n🌱 زمین‌های خالی: {lands}\n"]
    for r in rows:
        pid,rid,name,area,land_price,status,purchased_at=r
        lines.append(property_text(r))
    return "\n".join(lines)

def property_sell_value(row):
    pid,uid,rid,name,area,land_price,status,purchased_at=row
    if status=="house":
        build_cost=sum(material_price(m[0],area) for m in BUILDING_MATERIALS)
        base=land_price+build_cost
        return int(round(base*1.20)), build_cost
    return int(round(land_price*0.80)), 0

def property_entry_keyboard():
    return keyboard([
        [button("🌱 زمین", "property:land")],
        [button("🏬 مغازه در پاساژ", "property:store")],
        [button("🔙 برگشت به منو", "user:menu")],
        [button("❌ بستن منو", "menu:close")],
    ])

def mall_store_sizes_keyboard():
    rows=[[button(f"🏬 {area} متری", f"store:size:{area}")] for area in MALL_STORE_SIZES]
    rows += [[button("🔙 انتخاب زمین/مغازه", "user:property")],[button("❌ بستن منو", "menu:close")]]
    return keyboard(rows)

def mall_store_price_per_meter():
    return get_price("mall_store:per_meter", MALL_STORE_PRICE_PER_METER)


# ================================================================
# ⚽ FOOTBALL TEAM / CLUB SYSTEM
# ================================================================
def football_team(uid):
    with db() as c:
        r=c.execute("SELECT id,user_id,club_name,club_name_norm,wins,losses,draws,games,experience,last_game_at,created_at,last_income_at FROM football_teams WHERE user_id=?",(int(uid),)).fetchone()
    if not r: return None
    return dict(id=r[0],user_id=r[1],club_name=r[2],club_name_norm=r[3],wins=r[4],losses=r[5],draws=r[6],games=r[7],experience=r[8],last_game_at=r[9],created_at=r[10],last_income_at=r[11])

def normalize_club_name(name):
    name=(name or "").strip().casefold().replace("‌", "").replace("ي","ی").replace("ك","ک")
    name=re.sub(r"\s+"," ",name)
    return name

def football_team_players(team_id, position=None):
    with db() as c:
        if position:
            return c.execute("SELECT id,player_id,position,power,monthly_price,contract_days,contract_started_at,games_played,in_lineup,contract_notice_sent,contract_paid FROM football_team_players WHERE team_id=? AND position=? ORDER BY power DESC,id",(team_id,position)).fetchall()
        return c.execute("SELECT id,player_id,position,power,monthly_price,contract_days,contract_started_at,games_played,in_lineup,contract_notice_sent,contract_paid FROM football_team_players WHERE team_id=? ORDER BY position,power DESC,id",(team_id,)).fetchall()

def football_coach(team_id):
    with db() as c:
        r=c.execute("SELECT tc.coach_id,c.name,c.power,c.monthly_price,tc.contract_days,tc.contract_started_at,tc.contract_notice_sent,tc.contract_paid FROM football_team_coaches tc JOIN football_coaches c ON c.id=tc.coach_id WHERE tc.team_id=?",(team_id,)).fetchone()
    return r

def football_days_left(days):
    return max(0,int(days))

def football_contract_active(days): return int(days)>0

def football_lineup_counts(team_id):
    with db() as c:
        rows=c.execute("SELECT position,COUNT(*) FROM football_team_players WHERE team_id=? AND in_lineup=1 AND contract_days>0 GROUP BY position",(team_id,)).fetchall()
    d={p:0 for p in FOOTBALL_POSITIONS}
    for p,n in rows: d[p]=int(n)
    return d

def football_lineup_valid(team_id):
    c=football_lineup_counts(team_id)
    return all(c[p] >= FOOTBALL_LINEUP_LIMITS[p] for p in FOOTBALL_POSITIONS)

def football_team_power(team_id):
    with db() as c:
        rows=c.execute("SELECT power FROM football_team_players WHERE team_id=? AND in_lineup=1 AND contract_days>0",(team_id,)).fetchall()
        coach=c.execute("SELECT c.power FROM football_team_coaches tc JOIN football_coaches c ON c.id=tc.coach_id WHERE tc.team_id=? AND tc.contract_days>0",(team_id,)).fetchone()
    player_avg=sum(int(x[0]) for x in rows)/len(rows) if rows else 0
    return int(round(player_avg + ((int(coach[0])-70)*0.25 if coach else 0)))

def football_income_rate_per_power():
    try:
        return max(0, int(get_setting("football:daily_income_per_power") or FOOTBALL_DAILY_INCOME_DEFAULT_PER_POWER))
    except Exception:
        return FOOTBALL_DAILY_INCOME_DEFAULT_PER_POWER

def football_team_is_income_eligible(team_id):
    if not football_lineup_valid(team_id):
        return False
    coach=football_coach(team_id)
    return bool(coach and int(coach[4])>0)

def football_daily_income_amount(team_id):
    return max(0, int(football_team_power(team_id))*football_income_rate_per_power()) if football_team_is_income_eligible(team_id) else 0

async def process_football_income_once():
    now=int(time.time())
    with db() as c:
        teams=c.execute("SELECT id,user_id,last_income_at FROM football_teams ORDER BY id").fetchall()
    for team_id,uid,last_income_at in teams:
        if not football_team_is_income_eligible(team_id):
            if last_income_at:
                with db() as c:
                    c.execute("UPDATE football_teams SET last_income_at=? WHERE id=?",(now,team_id)); c.commit()
            continue
        if not last_income_at:
            with db() as c:
                c.execute("UPDATE football_teams SET last_income_at=? WHERE id=? AND last_income_at=0",(now,team_id)); c.commit()
            continue
        periods=(now-int(last_income_at))//86400
        if periods<=0:
            continue
        daily=football_daily_income_amount(team_id)
        if daily<=0:
            with db() as c:
                c.execute("UPDATE football_teams SET last_income_at=? WHERE id=?",(now,team_id)); c.commit()
            continue
        total=daily*periods
        add_coins(uid,total)
        log_tx(uid,"football_daily_income",total,f"team={team_id};days={periods};daily={daily};power={football_team_power(team_id)}")
        with db() as c:
            c.execute("UPDATE football_teams SET last_income_at=? WHERE id=?",(int(last_income_at)+periods*86400,team_id)); c.commit()
        try:
            await bot.send_message(uid,f"💰 درآمد روزانه فوتبال شما به مقدار {format_coins(total)} آریور واریز شد.\n⚽ درآمد روزانه فعلی: {format_coins(daily)} آریور")
        except Exception:
            pass

async def football_income_loop():
    while True:
        try:
            await process_football_income_once()
        except Exception as exc:
            print(f"Football income error: {exc}")
        await asyncio.sleep(60)

def football_team_text(uid):
    t=football_team(uid)
    if not t: return "⚽ ساخت تیم\n\nبرای ساخت تیم و باشگاه خودت باید ۲۰,۰۰۰,۰۰۰ آریور پرداخت کنی."
    rows=football_team_players(t['id'])
    counts={p:0 for p in FOOTBALL_POSITIONS}
    for r in rows: counts[r[2]]+=1
    coach=football_coach(t['id'])
    coach_active=bool(coach and int(coach[4])>0)
    lineup=football_lineup_counts(t['id'])
    return (f"⚽ تیم {t['club_name']}\n\n"
            f"💪 قدرت تیم: {football_team_power(t['id'])}\n"
            f"💰 درآمد روزانه فوتبال: {format_coins(football_daily_income_amount(t['id']))} آریور\n"
            f"👥 تعداد بازیکنان: {len(rows)}/{FOOTBALL_MAX_PLAYERS}\n"
            f"🏆 برد: {t['wins']} | 💔 باخت: {t['losses']} | 🤝 مساوی: {t['draws']}\n"
            f"🧠 تجربه تیم: {t['experience']}\n"
            f"🛡️ دفاع: {counts['دفاع']} | 🎯 هافبک: {counts['هافبک']} | ⚔️ حمله: {counts['حمله']} | 🧤 دروازه‌بان: {counts['دروازه بان']}\n"
            f"📋 ترکیب فعلی: 🛡️ {lineup['دفاع']}/4 | 🎯 {lineup['هافبک']}/4 | ⚔️ {lineup['حمله']}/3 | 🧤 {lineup['دروازه بان']}/1\n"
            f"👔 مربی: {'✅ دارد' if coach_active else '❌ ندارد/قرارداد تمام شده'}")

def football_team_keyboard(uid):
    t=football_team(uid)
    if not t: return keyboard([[button("⚽ ساخت تیم — ۲۰,۰۰۰,۰۰۰ آریور","football:create")],[button("🔙 برگشت به منو","user:menu")],[button("❌ بستن منو","menu:close")]])
    coach=football_coach(t['id']); active=bool(coach and int(coach[4])>0)
    coach_label="👔 مدیریت مربی" if active else "👔 خرید مربی"
    return keyboard([
        [button(coach_label,"football:coach")],
        [button("🛒 خرید بازیکن","football:buy_player")],
        [button("📋 بازیکنان داخل ترکیب","football:lineup")],
        [button("👥 تمامی بازیکنان تیم","football:all_players")],
        [button("🛠️ مدیریت بازیکنان تیم","football:manage_players")],
        [button("🔙 برگشت به منو","user:menu")],[button("❌ بستن منو","menu:close")]
    ])

def football_position_keyboard(prefix):
    return keyboard([[button("🧤 دروازه بان",f"{prefix}:دروازه بان"),button("⚔️ حمله",f"{prefix}:حمله")],[button("🎯 هافبک",f"{prefix}:هافبک"),button("🛡️ دفاع",f"{prefix}:دفاع")],[button("🔙 مدیریت تیم","football:panel")],[button("❌ بستن منو","menu:close")]])

def football_players_keyboard(team_id, position, mode="all", page=0):
    rows=football_team_players(team_id,position)
    page=max(0,int(page)); start=page*10; chunk=rows[start:start+10]; out=[]
    for r in chunk:
        tid,pid,pos,power,monthly,days,started,games,selected,notice,paid=r
        label=f"{'🟢 ' if selected else ''}{football_player_name(pid)} | 💪{power} | {days}روز"
        cb=f"football:toggle:{tid}" if mode=="lineup" else f"football:player:{tid}:{mode}"
        out.append([button(label[:60],cb,"success" if selected and mode=="lineup" else None)])
    nav=[]
    if page>0: nav.append(button("⬅️ قبلی",f"football:plist:{mode}:{position}:{page-1}"))
    if start+10<len(rows): nav.append(button("بعدی ➡️",f"football:plist:{mode}:{position}:{page+1}"))
    if nav: out.append(nav)
    back="football:lineup" if mode=="lineup" else ("football:manage_players" if mode=="manage" else "football:all_players")
    out.append([button("🔙 برگشت",back),button("⚽ پنل تیم","football:panel")])
    return keyboard(out)

def football_player_name(pid):
    with db() as c:
        r=c.execute("SELECT name FROM football_players WHERE id=?",(int(pid),)).fetchone()
    return r[0] if r else "بازیکن"

def football_coaches_keyboard(page=0):
    with db() as c: rows=c.execute("SELECT id,name,power,monthly_price FROM football_coaches ORDER BY power DESC,id").fetchall()
    page=max(0,int(page)); start=page*10; out=[]
    for cid,name,power,monthly in rows[start:start+10]: out.append([button(f"👔 {name} | 💪{power} | {format_coins(monthly)}/ماه"[:60],f"football:coach_select:{cid}")])
    nav=[]
    if page>0: nav.append(button("⬅️ قبلی",f"football:coach_list:{page-1}"))
    if start+10<len(rows): nav.append(button("بعدی ➡️",f"football:coach_list:{page+1}"))
    if nav: out.append(nav)
    out.append([button("🔙 پنل تیم","football:panel")]); return keyboard(out)

def football_contract_keyboard(prefix, entity_id, monthly):
    return keyboard([[button("📅 1 ماهه",f"{prefix}:contract:{entity_id}:1"),button("📅 1 ساله",f"{prefix}:contract:{entity_id}:12")],[button("📅 3 ساله",f"{prefix}:contract:{entity_id}:36")],[button("🔙 برگشت","football:panel"),button("❌ بستن منو","menu:close")]])

def football_price_for_player(pid):
    with db() as c: r=c.execute("SELECT monthly_price FROM football_players WHERE id=?",(int(pid),)).fetchone()
    return int(r[0]) if r else 0

def football_player_info_text(tp_id):
    with db() as c:
        r=c.execute("SELECT tp.id,p.name,tp.position,tp.power,tp.monthly_price,tp.contract_days,tp.games_played,tp.in_lineup FROM football_team_players tp JOIN football_players p ON p.id=tp.player_id WHERE tp.id=?",(tp_id,)).fetchone()
    if not r:return "❌ بازیکن پیدا نشد."
    tid,name,pos,power,monthly,days,games,lineup=r
    return f"👤 {name}\n\n📌 پست: {pos}\n💪 قدرت: {power}\n💰 قیمت ماهانه: {format_coins(monthly)} آریور\n📅 قرارداد باقی‌مانده: {days} روز\n🎮 تعداد بازی برای تیم: {games}\n📋 داخل ترکیب: {'✅ بله' if lineup else '❌ خیر'}"

def football_team_stats_update(c,team_id,winner,loser,draw=False):
    now=int(time.time())
    if draw:
        c.execute("UPDATE football_teams SET games=games+1,draws=draws+1,experience=experience+2,last_game_at=? WHERE id=?",(now,team_id))
    else:
        c.execute("UPDATE football_teams SET games=games+1,wins=wins+?,losses=losses+?,experience=experience+?,last_game_at=? WHERE id=?",(1 if winner else 0,1 if loser else 0,5 if winner else 1,now,team_id))

def football_consume_game_day(team_id):
    with db() as c:
        c.execute("UPDATE football_team_players SET contract_days=MAX(0,contract_days-1),games_played=games_played+1,contract_notice_sent=CASE WHEN contract_days-1<=10 THEN 0 ELSE contract_notice_sent END WHERE team_id=?",(team_id,))
        c.execute("UPDATE football_team_coaches SET contract_days=MAX(0,contract_days-1),contract_notice_sent=CASE WHEN contract_days-1<=10 THEN 0 ELSE contract_notice_sent END WHERE team_id=?",(team_id,))
        c.commit()

def football_last_game_remaining(team_id):
    with db() as c:r=c.execute("SELECT last_game_at FROM football_teams WHERE id=?",(team_id,)).fetchone()
    return max(0,FOOTBALL_GAME_COOLDOWN-int(time.time()-(int(r[0]) if r and r[0] else 0)))

def football_player_component(team_id):
    with db() as c:r=c.execute("SELECT power FROM football_team_players WHERE team_id=? AND in_lineup=1 AND contract_days>0",(team_id,)).fetchall()
    return sum(int(x[0]) for x in r)/12.0 if r else 0

def football_experience_component(team_id):
    t=football_team_by_id(team_id)
    coach=football_coach(team_id); coachp=int(coach[2]) if coach and int(coach[4])>0 else 0
    raw=50 + int(t['wins'])*3 - int(t['losses'])*2 + int(t['experience'])*0.5 + max(0,coachp-70)*0.3
    return max(0,min(100,raw))

def football_team_by_id(team_id):
    with db() as c:r=c.execute("SELECT id,user_id,club_name,club_name_norm,wins,losses,draws,games,experience,last_game_at,created_at FROM football_teams WHERE id=?",(team_id,)).fetchone()
    if not r:return None
    return dict(id=r[0],user_id=r[1],club_name=r[2],club_name_norm=r[3],wins=r[4],losses=r[5],draws=r[6],games=r[7],experience=r[8],last_game_at=r[9],created_at=r[10])

def football_calc_score(team_id, opponent_id):
    a=football_player_component(team_id); b=football_player_component(opponent_id)
    player_score=100*a/max(1,a+b)
    luck=random.uniform(0,100)
    ra=football_last_game_remaining(team_id); rb=football_last_game_remaining(opponent_id)
    # More rest (while both satisfy the 1h rule) gives a small advantage.
    rest_a=max(0,min(100,(FOOTBALL_GAME_COOLDOWN-ra)/FOOTBALL_GAME_COOLDOWN*100))
    rest_b=max(0,min(100,(FOOTBALL_GAME_COOLDOWN-rb)/FOOTBALL_GAME_COOLDOWN*100))
    ea=football_experience_component(team_id); eb=football_experience_component(opponent_id)
    exp_score=100*ea/max(1,ea+eb)
    # 50/20/10/20 requested weights.
    score_a=0.50*player_score+0.20*luck+0.10*rest_a+0.20*exp_score
    score_b=0.50*(100-player_score)+0.20*random.uniform(0,100)+0.10*rest_b+0.20*(100-exp_score)
    return score_a,score_b,player_score,luck,rest_a,exp_score

def football_match_keyboard(match_id, creator_id):
    return keyboard([[button("⚽ قبول بازی",f"football:accept:{match_id}"),button("❌ رد بازی",f"football:reject:{match_id}")]])

async def football_notify_contracts(uid):
    t=football_team(uid)
    if not t:return
    messages=[]
    with db() as c:
        coach=c.execute("SELECT c.name,c.power,tc.contract_days,tc.contract_notice_sent FROM football_team_coaches tc JOIN football_coaches c ON c.id=tc.coach_id WHERE tc.team_id=?",(t['id'],)).fetchone()
        if coach and 0<int(coach[2])<=FOOTBALL_CONTRACT_NOTICE_DAYS and not int(coach[3]):
            messages.append(f"⚠️ کمتر از ۱۰ روز از قرارداد مربی «{coach[0]}» با قدرت {coach[1]} مانده است.\n📅 باقی‌مانده: {coach[2]} روز\n🔄 جهت تمدید قرارداد کلمه «مدیریت تیم» را ارسال کنید.")
            c.execute("UPDATE football_team_coaches SET contract_notice_sent=1 WHERE team_id=?",(t['id'],))
        players=c.execute("SELECT tp.id,p.name,tp.power,tp.position,tp.contract_days,tp.contract_notice_sent FROM football_team_players tp JOIN football_players p ON p.id=tp.player_id WHERE tp.team_id=? AND tp.contract_days BETWEEN 1 AND 10",(t['id'],)).fetchall()
        for tp_id,name,power,pos,days,sent in players:
            if not int(sent):
                messages.append(f"⚠️ کمتر از ۱۰ روز از قرارداد بازیکن «{name}» با قدرت {power} و پست {pos} مانده است.\n📅 باقی‌مانده: {days} روز\n🔄 جهت تمدید قرارداد کلمه «مدیریت تیم» را ارسال کنید.")
                c.execute("UPDATE football_team_players SET contract_notice_sent=1 WHERE id=?",(tp_id,))
        c.commit()
    for msg in messages:
        try: await bot.send_message(uid,msg)
        except Exception: pass

async def football_contract_notice_loop():
    while True:
        try:
            with db() as c: uids=[r[0] for r in c.execute("SELECT user_id FROM football_teams").fetchall()]
            for uid in uids: await football_notify_contracts(uid)
        except Exception as exc: print(f"Football contract notice error: {exc}")
        await asyncio.sleep(1800)

@dp.callback_query(F.data=="user:football")
async def user_football(query:CallbackQuery):
    uid=menu_owner_id(query)
    t=football_team(uid)
    if t:
        # Requirement: management panel goes to private chat.
        try:
            await bot.send_message(uid,football_team_text(uid),reply_markup=football_team_keyboard(uid))
            await query.answer("⚽ پنل مدیریت تیم به پیویت ارسال شد.")
        except Exception:
            await query.answer("❌ اول پیوی ربات را باز کن و /start بزن.",show_alert=True)
    else:
        await query.message.edit_text("⚽ ساخت تیم و باشگاه\n\n💎 هزینه ساخت: ۲۰,۰۰۰,۰۰۰ آریور\n\nبا تأیید، مبلغ از کیف پولت کسر می‌شود و بعد نام باشگاه را انتخاب می‌کنی.",reply_markup=football_team_keyboard(uid)); await query.answer()

@dp.callback_query(F.data=="football:create")
async def football_create(query:CallbackQuery):
    uid=menu_owner_id(query)
    if football_team(uid): await query.answer("⚽ شما از قبل تیم دارید.",show_alert=True); return
    if get_balance(uid)<FOOTBALL_TEAM_CREATION_COST:
        await query.answer(f"❌ {format_coins(FOOTBALL_TEAM_CREATION_COST)} آریور لازم داری.",show_alert=True); return
    await query.message.edit_text(f"⚽ تأیید ساخت تیم\n\n💎 هزینه: {format_coins(FOOTBALL_TEAM_CREATION_COST)} آریور\n💰 موجودی فعلی: {format_coins(get_balance(uid))} آریور\n\nپرداخت و ساخت تیم را تأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید پرداخت", "football:create_confirm"),button("❌ لغو","user:menu")]])); await query.answer()

@dp.callback_query(F.data=="football:create_confirm")
async def football_create_confirm(query:CallbackQuery):
    uid=menu_owner_id(query)
    if football_team(uid): await query.answer("⚽ تیم شما قبلاً ساخته شده است.",show_alert=True); return
    norm=normalize_club_name("__pending__")
    if get_balance(uid)<FOOTBALL_TEAM_CREATION_COST: await query.answer("❌ موجودی کافی نیست.",show_alert=True); return
    add_coins(uid,-FOOTBALL_TEAM_CREATION_COST); log_tx(uid,"football_team_create",-FOOTBALL_TEAM_CREATION_COST,"team_creation")
    pending_admin[uid]=pending_admin.get(uid) # no-op, do not share admin state
    football_name_pending[uid]=True
    await query.message.edit_text("✅ پرداخت ساخت تیم انجام شد.\n\n🏷️ حالا اسم تیم و باشگاهت را ارسال کن.\n⚠️ نام باید یکتا باشد و قبلاً توسط باشگاه دیگری انتخاب نشده باشد.",reply_markup=keyboard([[button("❌ انصراف","football:name_cancel")]])); await query.answer("💎 پرداخت تأیید شد")

@dp.callback_query(F.data=="football:name_cancel")
async def football_name_cancel(query:CallbackQuery):
    football_name_pending.pop(menu_owner_id(query),None)
    await query.message.edit_text("❌ انتخاب نام لغو شد. مبلغ پرداخت‌شده قابل برگشت خودکار نیست.",reply_markup=keyboard([[button("⚽ پنل فوتبال","user:football")],[button("🔙 منو","user:menu")]])); await query.answer()

@dp.callback_query(F.data=="football:panel")
async def football_panel_callback(query:CallbackQuery):
    uid=menu_owner_id(query)
    if not football_team(uid): await query.answer("❌ هنوز تیم نساختی.",show_alert=True); return
    await query.message.edit_text(football_team_text(uid),reply_markup=football_team_keyboard(uid)); await query.answer()

@dp.callback_query(F.data=="football:coach")
async def football_coach_callback(query:CallbackQuery):
    t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ اول تیم بساز.",show_alert=True); return
    c=football_coach(t['id'])
    if c and int(c[4])>0:
        name,power,monthly,days=c[1],c[2],c[3],c[4]
        text=f"👔 مدیریت مربی\n\n👤 {name}\n💪 قدرت: {power}\n💰 قیمت ماهانه: {format_coins(monthly)} آریور\n📅 مدت باقی‌مانده: {days} روز"
        rows=[]
        if days<=FOOTBALL_CONTRACT_NOTICE_DAYS: rows.append([button("🔄 تمدید قرارداد","football:coach_renew")])
        rows.append([button("❌ فسخ قرارداد","football:coach_cancel")])
        rows.append([button("🔙 مدیریت تیم","football:panel")])
        await query.message.edit_text(text,reply_markup=keyboard(rows)); await query.answer(); return
    await query.message.edit_text("👔 خرید مربی\n\n۱۰۰ مربی آماده‌اند. قدرت و قیمت ماهانه هر مربی روی دکمه نمایش داده می‌شود.",reply_markup=football_coaches_keyboard(0)); await query.answer()

@dp.callback_query(F.data.startswith("football:coach_list:"))
async def football_coach_list(query:CallbackQuery):
    try:p=int(query.data.rsplit(":",1)[1])
    except:p=0
    await query.message.edit_text("👔 انتخاب مربی\n\nقدرت و قیمت ماهانه را مقایسه کن:",reply_markup=football_coaches_keyboard(p)); await query.answer()

@dp.callback_query(F.data.startswith("football:coach_select:"))
async def football_coach_select(query:CallbackQuery):
    cid=int(query.data.rsplit(":",1)[1]); t=football_team(menu_owner_id(query))
    with db() as c:r=c.execute("SELECT id,name,power,monthly_price FROM football_coaches WHERE id=?",(cid,)).fetchone()
    if not t or not r: await query.answer("❌ مربی پیدا نشد.",show_alert=True); return
    await query.message.edit_text(f"👔 مربی انتخاب‌شده: {r[1]}\n💪 قدرت: {r[2]}\n💰 قیمت ماهانه: {format_coins(r[3])} آریور\n\nمدت قرارداد را انتخاب کن:",reply_markup=football_contract_keyboard("football:coach",cid,r[3])); await query.answer()

@dp.callback_query(F.data.startswith("football:coach:contract:"))
async def football_coach_contract(query:CallbackQuery):
    parts=query.data.split(":"); cid=int(parts[3]); months=int(parts[4]); t=football_team(menu_owner_id(query))
    with db() as c:r=c.execute("SELECT name,power,monthly_price FROM football_coaches WHERE id=?",(cid,)).fetchone()
    if not t or not r: await query.answer("❌ اطلاعات مربی نامعتبر است.",show_alert=True); return
    total=int(r[2])*months
    await query.message.edit_text(f"👔 خرید مربی\n\n👤 {r[0]}\n💪 قدرت: {r[1]}\n📅 مدت: {months} ماه\n💰 قیمت نهایی: {format_coins(total)} آریور\n\nپرداخت را تأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید خرید",f"football:coach_buy:{cid}:{months}"),button("❌ لغو","football:coach")]])); await query.answer()

@dp.callback_query(F.data.startswith("football:coach_buy:"))
async def football_coach_buy(query:CallbackQuery):
    _,_,cid_s,months_s=query.data.split(":"); cid=int(cid_s); months=int(months_s); uid=menu_owner_id(query); t=football_team(uid)
    with db() as c:r=c.execute("SELECT name,power,monthly_price FROM football_coaches WHERE id=?",(cid,)).fetchone()
    if not t or not r or months not in (1,12,36): await query.answer("❌ خرید نامعتبر.",show_alert=True); return
    total=int(r[2])*months; days={1:30,12:365,36:1095}[months]
    if get_balance(uid)<total: await query.answer(f"❌ {format_coins(total)} آریور لازم داری.",show_alert=True); return
    add_coins(uid,-total); log_tx(uid,"football_coach_buy",-total,f"team={t['id']};coach={cid};months={months}")
    with db() as c:
        c.execute("INSERT INTO football_team_coaches(team_id,coach_id,contract_days,contract_started_at,contract_notice_sent,contract_paid) VALUES(?,?,?,?,0,?) ON CONFLICT(team_id) DO UPDATE SET coach_id=excluded.coach_id,contract_days=excluded.contract_days,contract_started_at=excluded.contract_started_at,contract_notice_sent=0,contract_paid=excluded.contract_paid",(t['id'],cid,days,int(time.time()),total)); c.commit()
    await query.message.edit_text(f"✅ مربی خریداری شد!\n\n👤 {r[0]}\n💪 قدرت: {r[1]}\n📅 قرارداد: {days} روز\n💰 مبلغ: {format_coins(total)} آریور",reply_markup=football_team_keyboard(uid)); await query.answer("👔 مربی به تیم اضافه شد")

@dp.callback_query(F.data=="football:coach_cancel")
async def football_coach_cancel(query:CallbackQuery):
    t=football_team(menu_owner_id(query)); c=football_coach(t['id']) if t else None
    if not t or not c: await query.answer("❌ مربی فعالی وجود ندارد.",show_alert=True); return
    paid=int(c[7]); fee=(paid*3)//10
    await query.message.edit_text(f"❌ فسخ قرارداد مربی\n\n👤 {c[1]}\n💰 مبلغ قرارداد: {format_coins(paid)} آریور\n💸 هزینه فسخ (۳/۱۰): {format_coins(fee)} آریور\n\nتأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید فسخ",f"football:coach_cancel_confirm:{t['id']}"),button("❌ لغو","football:coach")]])); await query.answer()

@dp.callback_query(F.data.startswith("football:coach_cancel_confirm:"))
async def football_coach_cancel_confirm(query:CallbackQuery):
    tid=int(query.data.rsplit(":",1)[1]); t=football_team(menu_owner_id(query)); c=football_coach(t['id']) if t else None
    if not t or t['id']!=tid or not c: await query.answer("❌ قرارداد پیدا نشد.",show_alert=True); return
    fee=(int(c[7])*3)//10
    if get_balance(menu_owner_id(query))<fee: await query.answer(f"❌ {format_coins(fee)} آریور لازم داری.",show_alert=True); return
    add_coins(menu_owner_id(query),-fee); log_tx(menu_owner_id(query),"football_coach_cancel",-fee,f"team={tid}")
    with db() as cc: cc.execute("DELETE FROM football_team_coaches WHERE team_id=?",(tid,)); cc.commit()
    await query.message.edit_text("✅ قرارداد مربی فسخ شد و مربی از تیم حذف شد.",reply_markup=football_team_keyboard(menu_owner_id(query))); await query.answer("❌ قرارداد فسخ شد")

@dp.callback_query(F.data=="football:coach_renew")
async def football_coach_renew(query:CallbackQuery):
    t=football_team(menu_owner_id(query)); c=football_coach(t['id']) if t else None
    if not t or not c or int(c[4])>10: await query.answer("🔒 تمدید فقط وقتی ۱۰ روز یا کمتر باقی مانده باشد.",show_alert=True); return
    await query.message.edit_text(f"🔄 تمدید قرارداد {c[1]}\n\n💪 قدرت: {c[2]}\n💰 قیمت ماهانه: {format_coins(c[3])} آریور\n\nمدت تمدید را انتخاب کن:",reply_markup=football_contract_keyboard("football:coachrenew",c[0],c[3])); await query.answer()

@dp.callback_query(F.data.startswith("football:coachrenew:contract:"))
async def football_coachrenew_contract(query:CallbackQuery):
    parts=query.data.split(":"); cid=int(parts[3]); months=int(parts[4]); t=football_team(menu_owner_id(query))
    with db() as c:r=c.execute("SELECT name,power,monthly_price FROM football_coaches WHERE id=?",(cid,)).fetchone()
    if not t or not r or months not in (1,12,36): await query.answer("❌ نامعتبر.",show_alert=True); return
    total=int(r[2])*months
    await query.message.edit_text(f"🔄 تمدید مربی\n\n👤 {r[0]}\n📅 {months} ماه\n💰 مبلغ: {format_coins(total)} آریور\n\nتأیید پرداخت؟",reply_markup=keyboard([[button("✅ تأیید تمدید",f"football:coachrenew_buy:{cid}:{months}"),button("❌ لغو","football:coach")]])); await query.answer()

@dp.callback_query(F.data.startswith("football:coachrenew_buy:"))
async def football_coachrenew_buy(query:CallbackQuery):
    _,_,cid_s,months_s=query.data.split(":"); cid=int(cid_s); months=int(months_s); uid=menu_owner_id(query); t=football_team(uid); c=football_coach(t['id']) if t else None
    if not t or not c or c[0]!=cid or months not in (1,12,36): await query.answer("❌ قرارداد نامعتبر.",show_alert=True); return
    total=int(c[3])*months; days={1:30,12:365,36:1095}[months]
    if get_balance(uid)<total: await query.answer(f"❌ {format_coins(total)} آریور لازم داری.",show_alert=True); return
    add_coins(uid,-total); log_tx(uid,"football_coach_renew",-total,f"team={t['id']};coach={cid};months={months}")
    with db() as cc: cc.execute("UPDATE football_team_coaches SET contract_days=contract_days+?,contract_notice_sent=0,contract_paid=contract_paid+? WHERE team_id=?",(days,total,t['id'])); cc.commit()
    await query.message.edit_text(f"✅ قرارداد مربی تمدید شد.\n📅 {days} روز به قرارداد اضافه شد.",reply_markup=football_team_keyboard(uid)); await query.answer()

@dp.callback_query(F.data=="football:buy_player")
async def football_buy_player(query:CallbackQuery):
    t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ اول تیم بساز.",show_alert=True); return
    with db() as c: count=int(c.execute("SELECT COUNT(*) FROM football_team_players WHERE team_id=?",(t['id'],)).fetchone()[0])
    if count>=FOOTBALL_MAX_PLAYERS: await query.answer("❌ تعداد بازیکنان شما به حد مجاز رسیده.",show_alert=True); return
    await query.message.edit_text(f"🛒 خرید بازیکن\n\n👥 بازیکنان تیم: {count}/{FOOTBALL_MAX_PLAYERS}\nپست موردنظر را انتخاب کن:",reply_markup=football_position_keyboard("football:buypos")); await query.answer()

@dp.callback_query(F.data.startswith("football:buypos:"))
async def football_buy_position(query:CallbackQuery):
    pos=query.data.split(":",2)[2]; t=football_team(menu_owner_id(query))
    if not t or pos not in FOOTBALL_POSITIONS: await query.answer("❌ پست نامعتبر.",show_alert=True); return
    with db() as c: count=int(c.execute("SELECT COUNT(*) FROM football_team_players WHERE team_id=?",(t['id'],)).fetchone()[0])
    if count>=FOOTBALL_MAX_PLAYERS: await query.answer("❌ ظرفیت تیم تکمیل است.",show_alert=True); return
    with db() as c: rows=c.execute("SELECT id,name,power,monthly_price FROM football_players WHERE position=? ORDER BY power DESC,id",(pos,)).fetchall()
    out=[]
    for pid,name,power,monthly in rows:
        out.append([button(f"{name} | 💪{power} | {format_coins(monthly)}/ماه"[:60],f"football:player_select:{pid}")])
    # Telegram keyboards can handle the 50 entries; split is unnecessary, but keep a back button.
    out.append([button("🔙 پست‌ها","football:buy_player")]); out.append([button("⚽ پنل تیم","football:panel")])
    await query.message.edit_text(f"🛒 بازیکنان پست {pos}\n\n۵۰ بازیکن این پست در لیست هستند:",reply_markup=keyboard(out)); await query.answer()

@dp.callback_query(F.data.startswith("football:player_select:"))
async def football_player_select(query:CallbackQuery):
    pid=int(query.data.rsplit(":",1)[1]); t=football_team(menu_owner_id(query))
    with db() as c:r=c.execute("SELECT id,name,position,power,monthly_price FROM football_players WHERE id=?",(pid,)).fetchone()
    if not t or not r: await query.answer("❌ بازیکن پیدا نشد.",show_alert=True); return
    await query.message.edit_text(f"👤 {r[1]}\n\n📌 پست: {r[2]}\n💪 قدرت: {r[3]}\n💰 قیمت ماهانه: {format_coins(r[4])} آریور\n\nمدت قرارداد را انتخاب کن:",reply_markup=football_contract_keyboard("football:player",pid,r[4])); await query.answer()

@dp.callback_query(F.data.startswith("football:player:contract:"))
async def football_player_contract(query:CallbackQuery):
    _,_,_,pid_s,months_s=query.data.split(":"); pid=int(pid_s); months=int(months_s); uid=menu_owner_id(query); t=football_team(uid)
    with db() as c:r=c.execute("SELECT name,position,power,monthly_price FROM football_players WHERE id=?",(pid,)).fetchone()
    if not t or not r or months not in (1,12,36): await query.answer("❌ خرید نامعتبر.",show_alert=True); return
    total=int(r[3])*months
    await query.message.edit_text(f"👤 خرید بازیکن\n\n{r[0]}\n📌 {r[1]} | 💪 {r[2]}\n📅 {months} ماه\n💰 مبلغ نهایی: {format_coins(total)} آریور\n\nپرداخت را تأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید خرید",f"football:player_buy:{pid}:{months}"),button("❌ لغو","football:buy_player")]])); await query.answer()

@dp.callback_query(F.data.startswith("football:player_buy:"))
async def football_player_buy(query:CallbackQuery):
    _,_,pid_s,months_s=query.data.split(":"); pid=int(pid_s); months=int(months_s); uid=menu_owner_id(query); t=football_team(uid)
    with db() as c:r=c.execute("SELECT name,position,power,monthly_price FROM football_players WHERE id=?",(pid,)).fetchone()
    if not t or not r or months not in (1,12,36): await query.answer("❌ خرید نامعتبر.",show_alert=True); return
    with db() as c:
        count=int(c.execute("SELECT COUNT(*) FROM football_team_players WHERE team_id=?",(t['id'],)).fetchone()[0])
        owned=c.execute("SELECT 1 FROM football_team_players WHERE team_id=? AND player_id=?",(t['id'],pid)).fetchone()
    if count>=FOOTBALL_MAX_PLAYERS: await query.answer("❌ تعداد بازیکنان شما به حد مجاز رسیده.",show_alert=True); return
    if owned: await query.answer("❌ این بازیکن را قبلاً خریدی.",show_alert=True); return
    total=int(r[3])*months; days={1:30,12:365,36:1095}[months]
    if get_balance(uid)<total: await query.answer(f"❌ {format_coins(total)} آریور لازم داری.",show_alert=True); return
    add_coins(uid,-total); log_tx(uid,"football_player_buy",-total,f"team={t['id']};player={pid};months={months}")
    with db() as c:
        c.execute("INSERT INTO football_team_players(team_id,player_id,position,power,monthly_price,contract_days,contract_started_at,games_played,in_lineup,contract_notice_sent,contract_paid) VALUES(?,?,?,?,?,?,?,0,0,0,?)",(t['id'],pid,r[1],r[2],r[3],days,int(time.time()),total)); c.commit()
    await query.message.edit_text(f"✅ {r[0]} به تیم اضافه شد!\n📌 پست: {r[1]}\n💪 قدرت: {r[2]}\n📅 قرارداد: {days} روز\n💰 مبلغ: {format_coins(total)} آریور",reply_markup=football_team_keyboard(uid)); await query.answer("👤 بازیکن خریداری شد")

@dp.callback_query(F.data=="football:lineup")
async def football_lineup(query:CallbackQuery):
    t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ تیم نداری.",show_alert=True); return
    await query.message.edit_text("📋 بازیکنان داخل ترکیب\n\nپست را انتخاب کن؛ بازیکن انتخاب‌شده سبز نمایش داده می‌شود.",reply_markup=football_position_keyboard("football:lineuppos")); await query.answer()

@dp.callback_query(F.data.startswith("football:lineuppos:"))
async def football_lineup_position(query:CallbackQuery):
    pos=query.data.split(":",2)[2]; t=football_team(menu_owner_id(query))
    if not t or pos not in FOOTBALL_POSITIONS: await query.answer("❌ پست نامعتبر.",show_alert=True); return
    limit=FOOTBALL_LINEUP_LIMITS[pos]; rows=football_team_players(t['id'],pos); selected=sum(1 for r in rows if int(r[8]) and int(r[5])>0)
    await query.message.edit_text(f"📋 ترکیب {pos}\n\n🟢 انتخاب‌شده: {selected}/{limit}\nروی بازیکن بزن تا به ترکیب اضافه/حذف شود.\n⚠️ بازیکن با قرارداد تمام‌شده قابل انتخاب نیست.",reply_markup=football_players_keyboard(t['id'],pos,"lineup",0)); await query.answer()

@dp.callback_query(F.data.startswith("football:plist:"))
async def football_player_list_page(query:CallbackQuery):
    parts=query.data.split(":"); mode=parts[2]; pos=parts[3]; page=int(parts[4]); t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ تیم نداری.",show_alert=True); return
    title="📋 انتخاب ترکیب" if mode=="lineup" else ("🛠️ مدیریت بازیکنان" if mode=="manage" else "👥 تمامی بازیکنان")
    await query.message.edit_text(f"{title}\n\nپست: {pos}",reply_markup=football_players_keyboard(t['id'],pos,mode,page)); await query.answer()

@dp.callback_query(F.data.startswith("football:toggle:"))
async def football_toggle_lineup(query:CallbackQuery):
    tp_id=int(query.data.rsplit(":",1)[1]); uid=menu_owner_id(query); t=football_team(uid)
    with db() as c:r=c.execute("SELECT id,team_id,position,contract_days,in_lineup FROM football_team_players WHERE id=?",(tp_id,)).fetchone()
    if not t or not r or r[1]!=t['id']: await query.answer("❌ بازیکن پیدا نشد.",show_alert=True); return
    if int(r[3])<=0: await query.answer("❌ قرارداد این بازیکن تمام شده؛ اول تمدیدش کن.",show_alert=True); return
    current=int(r[4]); limit=FOOTBALL_LINEUP_LIMITS[r[2]]
    if not current:
        counts=football_lineup_counts(t['id'])
        if counts[r[2]]>=limit: await query.answer(f"❌ سقف پست {r[2]} پر شده ({limit} نفر).",show_alert=True); return
    with db() as c:c.execute("UPDATE football_team_players SET in_lineup=? WHERE id=? AND team_id=?",(0 if current else 1,tp_id,t['id'])); c.commit()
    await query.answer("🟢 به ترکیب اضافه شد." if not current else "⚪ از ترکیب خارج شد.")
    rows=football_team_players(t['id'],r[2]); selected=sum(1 for x in rows if int(x[8]) and int(x[5])>0)
    await query.message.edit_text(f"📋 ترکیب {r[2]}\n\n🟢 انتخاب‌شده: {selected}/{limit}",reply_markup=football_players_keyboard(t['id'],r[2],"lineup",0))

@dp.callback_query(F.data=="football:all_players")
async def football_all_players(query:CallbackQuery):
    t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ تیم نداری.",show_alert=True); return
    await query.message.edit_text("👥 تمامی بازیکنان تیم\n\nپست را انتخاب کن:",reply_markup=football_position_keyboard("football:allpos")); await query.answer()

@dp.callback_query(F.data.startswith("football:allpos:"))
async def football_all_position(query:CallbackQuery):
    pos=query.data.split(":",2)[2]; t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ تیم نداری.",show_alert=True); return
    rows=football_team_players(t['id'],pos); lines=[f"👥 بازیکنان {pos}\n"]
    for r in rows: lines.append(f"• {football_player_name(r[1])} — 💪 {r[3]} — 📅 {r[5]} روز — {'🟢 ترکیب' if r[8] else '⚪ ذخیره'}")
    await query.message.edit_text("\n".join(lines) if rows else f"👥 بازیکنان {pos}\n\n❌ بازیکنی نداری.",reply_markup=keyboard([[button("🔙 مدیریت تیم","football:panel")]])); await query.answer()

@dp.callback_query(F.data=="football:manage_players")
async def football_manage_players(query:CallbackQuery):
    t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ تیم نداری.",show_alert=True); return
    await query.message.edit_text("🛠️ مدیریت بازیکنان تیم\n\nپست را انتخاب کن:",reply_markup=football_position_keyboard("football:managepos")); await query.answer()

@dp.callback_query(F.data.startswith("football:managepos:"))
async def football_manage_position(query:CallbackQuery):
    pos=query.data.split(":",2)[2]; t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ تیم نداری.",show_alert=True); return
    await query.message.edit_text(f"🛠️ مدیریت بازیکنان — {pos}\n\nبازیکن را انتخاب کن:",reply_markup=football_players_keyboard(t['id'],pos,"manage",0)); await query.answer()

@dp.callback_query(F.data.startswith("football:player:"))
async def football_player_manage(query:CallbackQuery):
    parts=query.data.split(":"); tp_id=int(parts[2]); mode=parts[3]; t=football_team(menu_owner_id(query))
    if not t: await query.answer("❌ تیم نداری.",show_alert=True); return
    text=football_player_info_text(tp_id); with_team=football_team_players(t['id'])
    r=next((x for x in with_team if int(x[0])==tp_id),None)
    if not r: await query.answer("❌ این بازیکن متعلق به تیم شما نیست.",show_alert=True); return
    rows=[]
    days=int(r[5]); paid=int(r[10])
    if days<=FOOTBALL_CONTRACT_NOTICE_DAYS: rows.append([button("🔄 تمدید قرارداد",f"football:playerrenew:{tp_id}")])
    rows.append([button("❌ فسخ قرارداد",f"football:playercancel:{tp_id}")])
    rows.append([button("🔙 برگشت",f"football:managepos:{r[2]}")])
    await query.message.edit_text(text,reply_markup=keyboard(rows)); await query.answer()

@dp.callback_query(F.data.startswith("football:playercancel:"))
async def football_player_cancel(query:CallbackQuery):
    tp_id=int(query.data.rsplit(":",1)[1]); t=football_team(menu_owner_id(query))
    with db() as c:r=c.execute("SELECT p.name,tp.position,tp.power,tp.contract_paid,tp.team_id FROM football_team_players tp JOIN football_players p ON p.id=tp.player_id WHERE tp.id=?",(tp_id,)).fetchone()
    if not t or not r or r[4]!=t['id']: await query.answer("❌ بازیکن پیدا نشد.",show_alert=True); return
    fee=(int(r[3])*3)//10
    await query.message.edit_text(f"❌ فسخ قرارداد بازیکن\n\n👤 {r[0]}\n📌 {r[1]} | 💪 {r[2]}\n💰 قرارداد: {format_coins(r[3])} آریور\n💸 هزینه فسخ ۳/۱۰: {format_coins(fee)} آریور\n\nتأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید فسخ",f"football:playercancel_confirm:{tp_id}"),button("❌ لغو",f"football:player:{tp_id}:manage")]])); await query.answer()

@dp.callback_query(F.data.startswith("football:playercancel_confirm:"))
async def football_player_cancel_confirm(query:CallbackQuery):
    tp_id=int(query.data.rsplit(":",1)[1]); uid=menu_owner_id(query); t=football_team(uid)
    with db() as c:r=c.execute("SELECT p.name,tp.position,tp.contract_paid,tp.team_id FROM football_team_players tp JOIN football_players p ON p.id=tp.player_id WHERE tp.id=?",(tp_id,)).fetchone()
    if not t or not r or r[3]!=t['id']: await query.answer("❌ بازیکن پیدا نشد.",show_alert=True); return
    fee=(int(r[2])*3)//10
    if get_balance(uid)<fee: await query.answer(f"❌ {format_coins(fee)} آریور لازم داری.",show_alert=True); return
    add_coins(uid,-fee); log_tx(uid,"football_player_cancel",-fee,f"team={t['id']};player={tp_id}")
    with db() as c:c.execute("DELETE FROM football_team_players WHERE id=? AND team_id=?",(tp_id,t['id'])); c.commit()
    await query.message.edit_text(f"✅ قرارداد {r[0]} فسخ شد و بازیکن از تیم حذف شد.",reply_markup=football_team_keyboard(uid)); await query.answer()

@dp.callback_query(F.data.startswith("football:playerrenew:"))
async def football_player_renew(query:CallbackQuery):
    tp_id=int(query.data.rsplit(":",1)[1]); t=football_team(menu_owner_id(query))
    with db() as c:r=c.execute("SELECT p.name,p.power,p.monthly_price,tp.contract_days,tp.team_id,tp.player_id FROM football_team_players tp JOIN football_players p ON p.id=tp.player_id WHERE tp.id=?",(tp_id,)).fetchone()
    if not t or not r or r[4]!=t['id'] or int(r[3])>10: await query.answer("🔒 تمدید فقط وقتی ۱۰ روز یا کمتر باقی مانده باشد.",show_alert=True); return
    await query.message.edit_text(f"🔄 تمدید قرارداد {r[0]}\n\n💪 قدرت: {r[1]}\n💰 ماهانه: {format_coins(r[2])} آریور\n📅 باقی‌مانده: {r[3]} روز\n\nمدت تمدید را انتخاب کن:",reply_markup=football_contract_keyboard("football:playerrenew",r[5],r[2])); await query.answer()

@dp.callback_query(F.data.startswith("football:playerrenew:contract:"))
async def football_playerrenew_contract(query:CallbackQuery):
    parts=query.data.split(":"); pid=int(parts[3]); months=int(parts[4]); t=football_team(menu_owner_id(query))
    with db() as c:r=c.execute("SELECT p.name,p.power,p.monthly_price,tp.contract_days,tp.id FROM football_team_players tp JOIN football_players p ON p.id=tp.player_id WHERE tp.player_id=? AND tp.team_id=?",(pid,t['id'] if t else 0)).fetchone()
    if not t or not r or months not in (1,12,36): await query.answer("❌ نامعتبر.",show_alert=True); return
    total=int(r[2])*months
    await query.message.edit_text(f"🔄 تمدید {r[0]}\n\n📅 {months} ماه\n💰 مبلغ: {format_coins(total)} آریور\n\nتأیید پرداخت؟",reply_markup=keyboard([[button("✅ تأیید تمدید",f"football:playerrenew_buy:{r[4]}:{months}"),button("❌ لغو",f"football:player:{r[4]}:manage")]])); await query.answer()

@dp.callback_query(F.data.startswith("football:playerrenew_buy:"))
async def football_playerrenew_buy(query:CallbackQuery):
    _,_,tp_s,months_s=query.data.split(":"); tp_id=int(tp_s); months=int(months_s); uid=menu_owner_id(query); t=football_team(uid)
    with db() as c:r=c.execute("SELECT p.name,p.monthly_price,tp.contract_days,tp.team_id FROM football_team_players tp JOIN football_players p ON p.id=tp.player_id WHERE tp.id=?",(tp_id,)).fetchone()
    if not t or not r or r[3]!=t['id'] or months not in (1,12,36): await query.answer("❌ قرارداد نامعتبر.",show_alert=True); return
    total=int(r[1])*months; days={1:30,12:365,36:1095}[months]
    if get_balance(uid)<total: await query.answer(f"❌ {format_coins(total)} آریور لازم داری.",show_alert=True); return
    add_coins(uid,-total); log_tx(uid,"football_player_renew",-total,f"team={t['id']};player={tp_id};months={months}")
    with db() as c:c.execute("UPDATE football_team_players SET contract_days=contract_days+?,contract_notice_sent=0,contract_paid=contract_paid+? WHERE id=?",(days,total,tp_id)); c.commit()
    await query.message.edit_text(f"✅ قرارداد {r[0]} تمدید شد.\n📅 {days} روز اضافه شد.",reply_markup=football_team_keyboard(uid)); await query.answer()

# ---------- Football wager game ----------
@dp.message(F.text.regexp(r"^بازی فوتبال\s+[0-9][0-9,]*$"))
async def football_game_command(message:Message):
    uid=message.from_user.id; text=(message.text or "").strip()
    target=message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
    if target and target.id==uid:
        await message.reply("❌ نمی‌توانی با خودت بازی فوتبال کنی."); return
    t1=football_team(uid)
    if not t1:
        await message.reply("❌ اول تیم فوتبال خودت را بساز."); return
    t2=football_team(target.id) if target else None
    if target and not t2:
        await message.reply("❌ کاربر موردنظر هنوز تیم فوتبال ندارد."); return
    try: stake=int(text.split()[-1].replace(",",""))
    except: await message.reply("❌ مبلغ شرط نامعتبر است."); return
    if stake<FOOTBALL_MIN_STAKE: await message.reply("❌ مبلغ شرط باید مثبت باشد."); return
    if football_last_game_remaining(t1['id'])>0 or (t2 and football_last_game_remaining(t2['id'])>0):
        await message.reply("⏳ بین هر دو بازی فوتبال هر تیم باید حداقل ۱ ساعت فاصله باشد."); return
    if not football_lineup_valid(t1['id']) or (t2 and not football_lineup_valid(t2['id'])):
        await message.reply("❌ هر دو تیم باید ترکیب کامل داشته باشند: ۱ دروازه‌بان، ۴ دفاع، ۴ هافبک و ۳ مهاجم."); return
    c1=football_coach(t1['id']); c2=football_coach(t2['id']) if t2 else None
    if not c1 or int(c1[4])<=0 or (target and (not c2 or int(c2[4])<=0)):
        await message.reply("❌ تیم باید مربی با قرارداد فعال داشته باشد."); return
    if target:
        if get_balance(uid)<stake or get_balance(target.id)<stake:
            await message.reply("❌ موجودی کیف پول یکی از دو بازیکن برای شرط کافی نیست."); return
    else:
        if get_balance(uid)<stake:
            await message.reply("❌ موجودی کیف پولت برای شرط کافی نیست."); return
    add_coins(uid,-stake); log_tx(uid,"football_wager_lock",-stake,f"target={target.id if target else 0}")
    opponent_team_id=t2['id'] if t2 else 0
    opponent_user_id=target.id if target else 0
    with db() as c:
        cur=c.execute("INSERT INTO football_matches(chat_id,message_id,creator_team_id,opponent_team_id,creator_user_id,opponent_user_id,stake,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(message.chat.id,message.message_id,t1['id'],opponent_team_id,uid,opponent_user_id,stake,"waiting",int(time.time()))); mid=cur.lastrowid; c.commit()
    if target:
        invite_text=f"⚽ دعوت بازی فوتبال\n\n🏠 {t1['club_name']} 🆚 {t2['club_name']}\n💎 شرط: {format_coins(stake)} آریور برای هر نفر\n\n👤 {display_name_by_id(uid)} حریف را دعوت کرده است."
    else:
        invite_text=f"⚽ بازی فوتبال آزاد\n\n🏠 {t1['club_name']} منتظر حریف است!\n💎 شرط: {format_coins(stake)} آریور برای هر نفر\n\n👥 هر کاربری که تیم فوتبال داشته باشد می‌تواند با دکمه زیر وارد بازی شود."
    await message.reply(invite_text,reply_markup=football_match_keyboard(mid,uid))

@dp.callback_query(F.data.startswith("football:accept:"))
async def football_accept(query:CallbackQuery):
    mid=int(query.data.rsplit(":",1)[1]); uid=menu_owner_id(query)
    with db() as c:r=c.execute("SELECT id,chat_id,creator_team_id,opponent_team_id,creator_user_id,opponent_user_id,stake,status FROM football_matches WHERE id=?",(mid,)).fetchone()
    if not r or r[7]!="waiting": await query.answer("❌ این دعوت دیگر فعال نیست.",show_alert=True); return
    if uid==r[4]: await query.answer("😄 سازنده نمی‌تواند وارد بازی خودش شود؛ یک حریف باید شرکت کند.",show_alert=True); return
    if r[5] and uid!=r[5]: await query.answer("❌ این بازی برای حریف دیگری ثبت شده است.",show_alert=True); return
    if get_balance(uid)<r[6]: await query.answer("❌ موجودی آریورت برای شرط کافی نیست.",show_alert=True); return
    t1=football_team_by_id(r[2]); t2=football_team(uid)
    if not t1 or not t2: await query.answer("❌ هر دو بازیکن باید تیم فوتبال داشته باشند.",show_alert=True); return
    if not football_lineup_valid(t1['id']) or not football_lineup_valid(t2['id']): await query.answer("❌ شرایط بازی دیگر برقرار نیست.",show_alert=True); return
    if football_last_game_remaining(t1['id'])>0 or football_last_game_remaining(t2['id'])>0: await query.answer("⏳ حداقل فاصله یک ساعت رعایت نشده.",show_alert=True); return
    c1=football_coach(t1['id']); c2=football_coach(t2['id'])
    if not c1 or int(c1[4])<=0 or not c2 or int(c2[4])<=0: await query.answer("❌ هر دو تیم باید مربی با قرارداد فعال داشته باشند.",show_alert=True); return
    # Claim an open challenge atomically before taking the second stake.
    with db() as c:
        cur=c.execute("UPDATE football_matches SET opponent_team_id=?,opponent_user_id=? WHERE id=? AND status='waiting' AND opponent_user_id=0",(t2['id'],uid,mid))
        if cur.rowcount==0:
            await query.answer("❌ یک نفر دیگر این بازی را قبول کرد.",show_alert=True); return
        c.commit()
    add_coins(uid,-r[6]); log_tx(uid,"football_wager_lock",-r[6],f"match={mid}")
    score1,score2,pc,luck,rest,exp=football_calc_score(t1['id'],t2['id'])
    winner=t1 if score1>=score2 else t2; loser=t2 if winner['id']==t1['id'] else t1; winner_uid=winner['user_id']; loser_uid=loser['user_id']; prize=r[6]*2
    with db() as c:
        c.execute("UPDATE football_matches SET status='finished',winner_user_id=?,accepted_at=?,finished_at=? WHERE id=? AND status='waiting'",(winner_uid,int(time.time()),int(time.time()),mid))
        c.execute("UPDATE football_teams SET games=games+1,wins=wins+1,experience=experience+5,last_game_at=? WHERE id=?",(int(time.time()),winner['id']))
        c.execute("UPDATE football_teams SET games=games+1,losses=losses+1,experience=experience+1,last_game_at=? WHERE id=?",(int(time.time()),loser['id']))
        c.commit()
    add_coins(winner_uid,prize); log_tx(winner_uid,"football_win",prize,f"match={mid};loser={loser_uid}")
    try:
        await bot.send_message(winner_uid,f"🏆 جایزه بازی فوتبال شما به مقدار {format_coins(prize)} آریور واریز شد.")
    except Exception:
        pass
    football_consume_game_day(t1['id']); football_consume_game_day(t2['id'])
    await query.message.edit_text(f"🏁 بازی فوتبال تمام شد!\n\n🏆 برنده: {winner['club_name']}\n💎 جایزه: {format_coins(prize)} آریور\n\n📊 عوامل نتیجه:\n⚽ قدرت بازیکنان: ۵۰٪\n🍀 شانس: ۲۰٪\n⏳ فاصله بازی: ۱۰٪\n🧠 تجربه و سابقه تیم: ۲۰٪\n\n📉 امتیاز نهایی: {score1:.1f} - {score2:.1f}\n\n📅 از قرارداد مربی و بازیکنان هر تیم ۱ روز کم شد.",reply_markup=keyboard([[button("⚽ مدیریت تیم","football:panel"),button("🔙 منو","user:menu")]])); await query.answer("🏆 بازی تمام شد")

@dp.callback_query(F.data.startswith("football:reject:"))
async def football_reject(query:CallbackQuery):
    mid=int(query.data.rsplit(":",1)[1]); uid=menu_owner_id(query)
    with db() as c:r=c.execute("SELECT creator_user_id,opponent_user_id,stake,status FROM football_matches WHERE id=?",(mid,)).fetchone()
    if not r or r[3]!="waiting" or uid!=r[1]: await query.answer("❌ این دعوت فعال نیست.",show_alert=True); return
    add_coins(r[0],r[2]); log_tx(r[0],"football_wager_refund",r[2],f"match={mid}")
    with db() as c:c.execute("UPDATE football_matches SET status='rejected',finished_at=? WHERE id=? AND status='waiting'",(int(time.time()),mid)); c.commit()
    await query.message.edit_text("❌ دعوت بازی فوتبال رد شد و شرط به سازنده برگشت."); await query.answer()

@dp.callback_query(F.data=="user:property")
async def user_property(query:CallbackQuery):
    await query.message.edit_text("🏠 املاک\n\nنوع ملک را انتخاب کن:",reply_markup=property_entry_keyboard()); await query.answer()

@dp.callback_query(F.data=="property:land")
async def property_land_callback(query:CallbackQuery):
    await query.message.edit_text("🌱 خرید زمین\n\nیکی از مناطق را انتخاب کن:",reply_markup=property_regions_keyboard()); await query.answer()

@dp.callback_query(F.data=="property:store")
async def property_store_callback(query:CallbackQuery):
    price=mall_store_price_per_meter()
    await query.message.edit_text(f"🏬 مغازه در پاساژ\n\n💎 قیمت هر متر: {format_coins(price)} آریور\n\nمتراژ مغازه را انتخاب کن:",reply_markup=mall_store_sizes_keyboard()); await query.answer()

@dp.callback_query(F.data.startswith("store:size:"))
async def mall_store_size_callback(query:CallbackQuery):
    try: area=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ متراژ نامعتبر است.",show_alert=True); return
    if area not in MALL_STORE_SIZES:
        await query.answer("❌ متراژ نامعتبر است.",show_alert=True); return
    price=mall_store_price_per_meter(); total=price*area
    await query.message.edit_text(
        f"🏬 خرید مغازه در پاساژ\n\n📐 متراژ: {area} متر\n💎 قیمت هر متر: {format_coins(price)} آریور\n💰 قیمت نهایی: {format_coins(total)} آریور\n\nآیا پرداخت و خرید این مغازه را تأیید می‌کنی؟",
        reply_markup=keyboard([[button("✅ بله، می‌خرم",f"store:confirm:{area}"),button("❌ نه، نمی‌خرم","store:cancel")],[button("🔙 انتخاب متراژ","property:store")],[button("❌ بستن منو","menu:close")]])
    ); await query.answer()

@dp.callback_query(F.data=="store:cancel")
async def mall_store_cancel_callback(query:CallbackQuery):
    await query.message.edit_text("❌ خرید مغازه لغو شد.",reply_markup=keyboard([[button("🏬 املاک","user:property")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data.startswith("store:confirm:"))
async def mall_store_confirm_callback(query:CallbackQuery):
    try: area=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ متراژ نامعتبر است.",show_alert=True); return
    if area not in MALL_STORE_SIZES:
        await query.answer("❌ متراژ نامعتبر است.",show_alert=True); return
    uid=menu_owner_id(query); price=mall_store_price_per_meter(); total=price*area
    if get_balance(uid)<total:
        await query.answer(f"❌ {format_coins(total)} آریور لازم داری.",show_alert=True); return
    add_coins(uid,-total); now=int(time.time())
    with db() as c:
        cur=c.execute("INSERT INTO mall_stores(user_id,area,purchase_price,purchased_at,last_income_at) VALUES(?,?,?,?,0)",(uid,area,total,now)); sid=cur.lastrowid; c.commit()
    log_tx(uid,"mall_store_buy",-total,f"store={sid};area={area}")
    await query.message.edit_text(f"✅ مغازه پاساژ خریداری شد!\n\n🏬 مغازه #{sid}\n📐 متراژ: {area} متر\n💰 مبلغ پرداخت‌شده: {format_coins(total)} آریور\n\nحالا از «فروشگاه» لوازم کسب‌وکار را برای این مغازه تهیه کن.",reply_markup=keyboard([[button("🛍️ فروشگاه","user:shop")],[button("🧰 لوازم کسب و کار","user:business_items")],[button("💼 دارایی‌ها","user:assets")],[button("🔙 منو","user:menu")]])); await query.answer("🏬 مغازه خریداری شد!")

@dp.callback_query(F.data.startswith("property:region:"))
async def property_region_callback(query:CallbackQuery):
    rid=int(query.data.rsplit(":",1)[1]); row=property_region(rid)
    if not row: await query.answer("❌ منطقه نامعتبر.",show_alert=True); return
    await query.message.edit_text(f"🏠 منطقه {rid} ({row[1]})\n\nمتراژ را انتخاب کنید:",reply_markup=property_sizes_keyboard(rid)); await query.answer()

@dp.callback_query(F.data.startswith("property:size:"))
async def property_size_callback(query:CallbackQuery):
    _,_,rid_s,area_s=query.data.split(":"); rid=int(rid_s); area=int(area_s)
    base=get_price(f"property:region:{rid}",property_region(rid)[2]); total=base*area
    await query.message.edit_text(f"🏠 خرید ملک\n\n📍 منطقه {rid} ({property_region(rid)[1]})\n📐 متراژ: {area} متر\n💎 قیمت هر متر: {format_coins(base)} آریور\n💰 قیمت نهایی: {format_coins(total)} آریور\n\nآیا پرداخت و خرید این زمین را تأیید می‌کنی؟",reply_markup=keyboard([[button("✅ بله، می‌خرم",f"property:confirm:{rid}:{area}"),button("❌ نه، نمی‌خرم","property:cancel")],[button("🔙 انتخاب متراژ",f"property:region:{rid}")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="property:cancel")
async def property_cancel_callback(query:CallbackQuery):
    await query.message.edit_text("❌ خرید ملک لغو شد.\n\nاگر خواستی دوباره می‌توانی از بخش «خرید ملک» منطقه و متراژ را انتخاب کنی.",reply_markup=keyboard([[button("🏠 خرید ملک","user:property")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]]))
    await query.answer("خرید لغو شد")

@dp.callback_query(F.data.startswith("property:confirm:"))
async def property_confirm_callback(query:CallbackQuery):
    _,_,rid_s,area_s=query.data.split(":"); rid=int(rid_s); area=int(area_s)
    row=property_region(rid); price=get_price(f"property:region:{rid}",row[2]); total=price*area
    if get_balance(menu_owner_id(query))<total:
        await query.answer(f"❌ {format_coins(total)} آریور لازم داری.",show_alert=True); return
    add_coins(menu_owner_id(query),-total); now=int(time.time())
    with db() as c:
        cur=c.execute("INSERT INTO properties(user_id,region_id,region_name,area,land_price,status,purchased_at) VALUES(?,?,?,?,?,'land',?)",(menu_owner_id(query),rid,row[1],area,total,now)); pid=cur.lastrowid
        for name,*_ in BUILDING_MATERIALS:
            c.execute("INSERT OR IGNORE INTO property_materials(property_id,material,purchased,purchased_at) VALUES(?,?,0,0)",(pid,name))
        c.commit()
    log_tx(menu_owner_id(query),"property_land_buy",-total,f"property={pid};region={rid};area={area}")
    await query.message.edit_text(f"✅ زمین خریداری شد!\n\n🏡 ملک #{pid}\n📍 منطقه {rid} ({row[1]})\n📐 متراژ: {area} متر\n💰 مبلغ پرداخت‌شده: {format_coins(total)} آریور\n\nحالا می‌توانی از بخش «مصالح ساختمانی» برای ساخت خانه استفاده کنی.",reply_markup=keyboard([[button("🧱 مصالح ساختمانی",f"property:materials:{pid}")],[button("💼 دارایی‌ها","user:assets")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer("🏠 زمین خریداری شد!")

@dp.callback_query(F.data=="user:materials")
async def user_materials(query:CallbackQuery):
    rows=user_properties(menu_owner_id(query))
    if not rows:
        await query.message.edit_text("🧱 مصالح ساختمانی\n\n❌ ابتدا زمین بخرید تا مصالح متناسب با متراژ آن نمایش داده شود.",reply_markup=keyboard([[button("🏠 خرید ملک","user:property")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer(); return
    text="🧱 مصالح ساختمانی\n\nزمین/خانه موردنظر را انتخاب کن. برای هر ملک، مقدار موردنیاز و قیمت هر مصالح بر اساس متراژ همان ملک محاسبه می‌شود."
    await query.message.edit_text(text,reply_markup=property_keyboard(rows,"materials")); await query.answer()

@dp.callback_query(F.data.startswith("property:materials:"))
async def property_materials_callback(query:CallbackQuery):
    pid=int(query.data.rsplit(":",1)[1]); row=property_by_id(pid,menu_owner_id(query))
    if not row: await query.answer("❌ ملک پیدا نشد.",show_alert=True); return
    if row[6]=="house":
        await query.message.edit_text("🏠 این زمین به خانه تبدیل شده است.\n\nحالا می‌توانی وارد دکوراسیون داخلی شوی.",reply_markup=keyboard([[button("🛋️ دکوراسیون داخلی","user:decor")],[button("💼 دارایی‌ها","user:assets")],[button("🔙 منو","user:menu")]])); await query.answer(); return
    lines=[f"🧱 مصالح ملک #{row[0]}\n📍 منطقه {row[2]} ({row[3]})\n📐 متراژ: {row[4]} متر\n"]
    for name,unit,qty,cost,purchased,icon in property_material_status(pid,row[4]):
        lines.append(f"{'✅' if purchased else '⬜'} {icon} {name}: {material_qty_text(name,qty)} — {format_coins(cost)} آریور")
    done=sum(1 for x in property_material_status(pid,row[4]) if x[4]); total=len(BUILDING_MATERIALS)
    lines.append(f"\n📦 مصالح خریداری‌شده: {done}/{total}")
    await query.message.edit_text("\n".join(lines),reply_markup=material_keyboard(pid,row[4])); await query.answer()

@dp.callback_query(F.data.startswith("material:buy:"))
async def material_buy_callback(query:CallbackQuery):
    parts=query.data.split(":"); pid=int(parts[2]); idx=int(parts[3])
    row=property_by_id(pid,menu_owner_id(query))
    if not row: await query.answer("❌ ملک پیدا نشد.",show_alert=True); return
    if row[6]=="house": await query.answer("🏠 این ملک قبلاً خانه شده است.",show_alert=True); return
    if idx<0 or idx>=len(BUILDING_MATERIALS): await query.answer("❌ مصالح نامعتبر.",show_alert=True); return
    name=BUILDING_MATERIALS[idx][0]; cost=material_price(name,row[4])
    with db() as c: r=c.execute("SELECT purchased FROM property_materials WHERE property_id=? AND material=?",(pid,name)).fetchone()
    if r and int(r[0]): await query.answer("✅ این مصالح قبلاً خریداری شده.",show_alert=True); return
    if get_balance(menu_owner_id(query))<cost: await query.answer(f"❌ {format_coins(cost)} آریور لازم داری.",show_alert=True); return
    add_coins(menu_owner_id(query),-cost)
    with db() as c:
        c.execute("INSERT INTO property_materials(property_id,material,purchased,purchased_at) VALUES(?,?,1,?) ON CONFLICT(property_id,material) DO UPDATE SET purchased=1,purchased_at=excluded.purchased_at",(pid,name,int(time.time()))); c.commit()
    log_tx(menu_owner_id(query),"building_material_buy",-cost,f"property={pid};material={name}")
    built=maybe_build_property(pid)
    if built:
        await query.message.edit_text(f"🎉 تبریک!\n\nتمام مصالح ملک #{pid} خریداری شد و زمین به 🏠 خانه تبدیل شد.\n📐 متراژ: {row[4]} متر\n\nحالا می‌توانی دکوراسیون داخلی را شروع کنی.",reply_markup=keyboard([[button("🛋️ دکوراسیون داخلی","user:decor")],[button("💼 دارایی‌ها","user:assets")],[button("🔙 منو","user:menu")]])); await query.answer("🏠 خانه ساخته شد!"); return
    await query.answer(f"✅ {name} خریداری شد!")
    await property_materials_callback(query)

@dp.callback_query(F.data=="user:assets")
async def user_assets(query:CallbackQuery):
    rows=user_properties(menu_owner_id(query))
    text=property_assets_text(menu_owner_id(query))
    stores=user_mall_stores(menu_owner_id(query))
    if stores:
        text += "\n\n" + business_assets_text(menu_owner_id(query))
    elif not rows:
        text="💼 دارایی‌های شما\n\n❌ هنوز ملک یا مغازه‌ای ندارید."
    kb=[]
    for pid,rid,name,area,land_price,status,purchased_at in rows:
        value,_build=property_sell_value((pid,menu_owner_id(query),rid,name,area,land_price,status,purchased_at))
        kb.append([button(f"💰 فروش زمین/خانه #{pid} — {format_coins(value)} آریور",f"property:sell:{pid}")])
    for sid,area,purchase_price,purchased_at,last_income_at in stores:
        kb.append([button(f"💰 فروش مغازه #{sid} — {format_coins(int(round(purchase_price*0.80)))} آریور",f"store:sell:{sid}")])
    kb += [[button("🏠 خرید ملک","user:property")],[button("🧰 لوازم کسب و کار","user:business_items")],[button("🧱 مصالح ساختمانی","user:materials")],[button("🛋️ دکوراسیون داخلی","user:decor")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]]
    await query.message.edit_text(text,reply_markup=keyboard(kb)); await query.answer()

@dp.callback_query(F.data.startswith("store:sell:"))
async def mall_store_sell_callback(query:CallbackQuery):
    sid=int(query.data.rsplit(":",1)[1]); uid=menu_owner_id(query)
    with db() as c:
        row=c.execute("SELECT id,area,purchase_price FROM mall_stores WHERE id=? AND user_id=?",(sid,uid)).fetchone()
    if not row:
        await query.answer("❌ مغازه پیدا نشد.",show_alert=True); return
    value=int(round(int(row[2])*0.80))
    await query.message.edit_text(f"💰 فروش مغازه #{sid}\n\n🏬 مغازه پاساژ\n📐 متراژ: {row[1]} متر\n💵 مبلغ فروش: {format_coins(value)} آریور\n\nآیا فروش را تأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید فروش",f"store:sellconfirm:{sid}")],[button("🔙 دارایی‌ها","user:assets")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data.startswith("store:sellconfirm:"))
async def mall_store_sellconfirm_callback(query:CallbackQuery):
    sid=int(query.data.rsplit(":",1)[1]); uid=menu_owner_id(query)
    with db() as c:
        row=c.execute("SELECT id,area,purchase_price FROM mall_stores WHERE id=? AND user_id=?",(sid,uid)).fetchone()
        if not row:
            await query.answer("❌ مغازه پیدا نشد.",show_alert=True); return
        value=int(round(int(row[2])*0.80))
        c.execute("DELETE FROM business_items WHERE store_id=?",(sid,)); c.execute("DELETE FROM mall_stores WHERE id=? AND user_id=?",(sid,uid)); c.commit()
    add_coins(uid,value); log_tx(uid,"mall_store_sell",value,f"store={sid}")
    await query.message.edit_text(f"✅ مغازه #{sid} فروخته شد.\n💰 مبلغ واریزشده: {format_coins(value)} آریور",reply_markup=keyboard([[button("💼 دارایی‌ها","user:assets")],[button("🏬 املاک","user:property")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer("💰 فروش مغازه انجام شد!")

@dp.callback_query(F.data.startswith("property:sell:"))
async def property_sell_callback(query:CallbackQuery):
    pid=int(query.data.rsplit(":",1)[1]); row=property_by_id(pid,menu_owner_id(query))
    if not row: await query.answer("❌ ملک پیدا نشد.",show_alert=True); return
    value,build_cost=property_sell_value(row)
    status="خانه" if row[6]=="house" else "زمین خالی"
    extra=f"🏗️ هزینه مصالح: {format_coins(build_cost)} آریور\n" if row[6]=="house" else ""
    await query.message.edit_text(f"💰 فروش ملک #{pid}\n\n🏡 نوع: {status}\n📍 منطقه {row[2]} ({row[3]})\n📐 متراژ: {row[4]} متر\n💵 مبلغ فروش: {format_coins(value)} آریور\n{extra}\nآیا فروش را تأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید فروش",f"property:sellconfirm:{pid}")],[button("🔙 دارایی‌ها","user:assets")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data.startswith("property:sellconfirm:"))
async def property_sellconfirm_callback(query:CallbackQuery):
    pid=int(query.data.rsplit(":",1)[1]); row=property_by_id(pid,menu_owner_id(query))
    if not row: await query.answer("❌ ملک پیدا نشد.",show_alert=True); return
    value,_=property_sell_value(row)
    add_coins(menu_owner_id(query),value)
    with db() as c:
        c.execute("DELETE FROM property_materials WHERE property_id=?",(pid,)); c.execute("DELETE FROM property_decor WHERE property_id=?",(pid,)); c.execute("DELETE FROM properties WHERE id=? AND user_id=?",(pid,menu_owner_id(query))); c.commit()
    log_tx(menu_owner_id(query),"property_sell",value,f"property={pid}")
    await query.message.edit_text(f"✅ ملک #{pid} فروخته شد.\n💰 مبلغ واریزشده: {format_coins(value)} آریور",reply_markup=keyboard([[button("💼 دارایی‌ها","user:assets")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer("💰 فروش انجام شد!")

@dp.callback_query(F.data=="user:decor")
async def user_decor(query:CallbackQuery):
    rows=user_properties(menu_owner_id(query),"house")
    if not rows:
        await query.message.edit_text("🛋️ دکوراسیون داخلی\n\n❌ ابتدا یک خانه بسازید تا بتوانید دکوراسیون داخلی بخرید.",reply_markup=keyboard([[button("🏠 دارایی‌ها","user:assets")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer(); return
    await query.message.edit_text("🛋️ دکوراسیون داخلی\n\nخانه موردنظر را انتخاب کن:",reply_markup=property_keyboard(rows,"decor")); await query.answer()

@dp.callback_query(F.data.startswith("property:decor:"))
async def property_decor_callback(query:CallbackQuery):
    pid=int(query.data.rsplit(":",1)[1]); row=property_by_id(pid,menu_owner_id(query))
    if not row or row[6]!="house": await query.answer("❌ ابتدا خانه بسازید.",show_alert=True); return
    await query.message.edit_text(f"🛋️ دکوراسیون خانه #{pid}\n📍 منطقه {row[3]} — {row[4]} متر\n\nهر مورد را برای خرید انتخاب کن. تخت خواب، میز تحریر و میز مطالعه قابل ارتقا هستند.",reply_markup=decor_keyboard(pid)); await query.answer()

@dp.callback_query(F.data.startswith("decor:buy:"))
async def decor_buy_callback(query:CallbackQuery):
    parts=query.data.split(":"); pid=int(parts[2]); idx=int(parts[3])
    row=property_by_id(pid,menu_owner_id(query))
    if not row or row[6]!="house": await query.answer("❌ ابتدا خانه بسازید.",show_alert=True); return
    if idx<0 or idx>=len(DECORATION_ITEMS): await query.answer("❌ آیتم نامعتبر.",show_alert=True); return
    item,default,cat=DECORATION_ITEMS[idx]; price=decoration_price(item); current=decoration_qty(pid,item)
    if current>0 and not decoration_is_upgradeable(item): await query.answer("🎒 این وسیله را قبلاً خریده‌ای.",show_alert=True); return
    if get_balance(menu_owner_id(query))<price: await query.answer(f"❌ {format_coins(price)} آریور لازم داری.",show_alert=True); return
    add_coins(menu_owner_id(query),-price)
    with db() as c:
        c.execute("INSERT INTO property_decor(property_id,item,quantity,purchased_at) VALUES(?,?,1,?) ON CONFLICT(property_id,item) DO UPDATE SET quantity=quantity+1,purchased_at=excluded.purchased_at",(pid,item,int(time.time()))); c.commit()
    log_tx(menu_owner_id(query),"decor_buy",-price,f"property={pid};item={item}")
    await query.answer(f"✅ {item} خریداری شد!")
    await property_decor_callback(query)

# ================================================================
# MALL BUSINESS SYSTEM
# ================================================================
def user_mall_stores(uid):
    with db() as c:
        return c.execute("SELECT id,area,purchase_price,purchased_at,last_income_at FROM mall_stores WHERE user_id=? ORDER BY id",(uid,)).fetchall()

def store_items(store_id):
    with db() as c:
        return c.execute("SELECT item,quantity,total_spent FROM business_items WHERE store_id=? AND quantity>0 ORDER BY item",(store_id,)).fetchall()

def business_item_price(item):
    default=BUSINESS_ITEM_DEFAULTS[item][0]
    return get_price(price_key_for("shop",item),default)

def business_item_label(item):
    return f"{item} [{BUSINESS_ITEM_CODES[item]}]"

def business_pack_count(store_id, area):
    rows={item:int(qty) for item,qty,_spent in store_items(store_id)}
    monitors=rows.get("🖥️ مانیتور 24 اینچ سونی",0)
    stands=rows.get("🪛 پایه دیواری مانیتور 24 سونی",0)
    sofas=rows.get("🛋️ مبل تک نفره",0)
    consoles=sum(rows.get(x,0) for x in ("🎮 کنسول PS4","🎮 کنسول PS5","🎮 کنسول Xbox Series S","🎮 کنسول Xbox Series X"))
    pc_pack=min(rows.get("🖥️ کامپیوتر PC نسل 9 گیمینگ",0),rows.get("⌨️🖱️ پک کیبورد و موس ریزر گیمینگ",0))
    device_packs=consoles+pc_pack
    capacity=max(0,int(area)//2)
    return max(0,min(monitors,stands,sofas,device_packs,capacity))

def store_equipment_spent(store_id):
    with db() as c:
        r=c.execute("SELECT COALESCE(SUM(total_spent),0) FROM business_items WHERE store_id=? AND quantity>0",(store_id,)).fetchone()
    return int(r[0] or 0)

def store_daily_income(store_id, area):
    packs=business_pack_count(store_id,area)
    if packs<1: return 0
    return int(store_equipment_spent(store_id)//30)

def business_total_packs(uid):
    return sum(business_pack_count(sid,area) for sid,area,*_ in user_mall_stores(uid))

def business_total_daily_income(uid):
    return sum(store_daily_income(sid,area) for sid,area,*_ in user_mall_stores(uid))

def business_items_text(uid):
    stores=user_mall_stores(uid)
    if not stores:
        return "🧰 لوازم کسب و کار\n\n❌ ابتدا یک مغازه در پاساژ بخرید."
    lines=["🧰 لوازم کسب و کار\n"]
    aggregate={}
    for sid,area,purchase_price,purchased_at,last_income_at in stores:
        lines.append(f"🏬 مغازه #{sid} — {area} متر — 📦 {business_pack_count(sid,area)} پک کامل")
        for item,qty,spent in store_items(sid):
            aggregate[item]=aggregate.get(item,0)+int(qty)
            lines.append(f"   • {business_item_label(item)} × {qty}")
    lines.append(f"\n📦 مجموع پک‌های کامل: {business_total_packs(uid)}")
    lines.append("\n💡 فروش هر وسیله: «فروش کد»؛ هر آیتم ۲۰٪ زیر قیمت فعلی فروشگاه از شما خریداری می‌شود.")
    return "\n".join(lines)

def business_assets_text(uid):
    stores=user_mall_stores(uid)
    if not stores:
        return "🏬 املاک شما\n\n❌ هنوز مغازه‌ای در پاساژ ندارید."
    lines=["🏬 املاک شما\n"]
    for sid,area,purchase_price,purchased_at,last_income_at in stores:
        packs=business_pack_count(sid,area)
        daily=store_daily_income(sid,area)
        lines.append(f"🏬 مغازه پاساژ #{sid}\n📐 {area} متر\n💰 قیمت خرید: {format_coins(purchase_price)} آریور\n📦 پک کامل: {packs}\n💵 درآمد روزانه: {format_coins(daily)} آریور")
    return "\n\n".join(lines)

def business_item_store_keyboard(item, uid):
    rows=[]
    for sid,area,purchase_price,purchased_at,last_income_at in user_mall_stores(uid):
        rows.append([button(f"🏬 مغازه #{sid} — {area} متر",f"bizbuy:{BUSINESS_ITEM_CODES[item]}:{sid}")])
    rows.append([button("🔙 فروشگاه","user:shop"),button("❌ بستن منو","menu:close")])
    return keyboard(rows)

def business_shop_buy(uid,item,store_id):
    stores={sid for sid,*_ in user_mall_stores(uid)}
    if store_id not in stores: return False,"store",0
    price=business_item_price(item)
    if get_balance(uid)<price: return False,"funds",price
    add_coins(uid,-price)
    with db() as c:
        c.execute("INSERT INTO business_items(store_id,item,quantity,total_spent) VALUES(?,?,1,?) ON CONFLICT(store_id,item) DO UPDATE SET quantity=quantity+1,total_spent=total_spent+excluded.total_spent",(store_id,item,price)); c.commit()
    log_tx(uid,"business_item_buy",-price,f"store={store_id};item={item};code={BUSINESS_ITEM_CODES[item]}")
    return True,"ok",price

def sell_business_item_by_code(uid,code):
    code=code.upper().strip()
    item=next((x for x,c in BUSINESS_ITEM_CODES.items() if c==code),None)
    if not item: return False,"code",0,0,None
    price=int(round(business_item_price(item)*0.80))
    with db() as c:
        row=c.execute("SELECT bi.store_id,bi.quantity,bi.total_spent,ms.area FROM business_items bi JOIN mall_stores ms ON ms.id=bi.store_id WHERE ms.user_id=? AND bi.item=? AND bi.quantity>0 ORDER BY bi.store_id LIMIT 1",(uid,item)).fetchone()
        if not row: return False,"owned",price,0,item
        sid,qty,total_spent,area=row
        avg_cost=float(total_spent)/float(qty) if qty else 0
        new_qty=qty-1; new_spent=max(0,int(round(total_spent-avg_cost)))
        if new_qty<=0:
            c.execute("DELETE FROM business_items WHERE store_id=? AND item=?",(sid,item))
        else:
            c.execute("UPDATE business_items SET quantity=?,total_spent=? WHERE store_id=? AND item=?",(new_qty,new_spent,sid,item))
        c.commit()
    add_coins(uid,price); log_tx(uid,"business_item_sell",price,f"store={sid};item={item};code={code}")
    return True,"ok",price,1,item

async def process_business_income_once():
    now=int(time.time())
    stores=[]
    with db() as c:
        stores=c.execute("SELECT id,user_id,area,last_income_at FROM mall_stores ORDER BY id").fetchall()
    for sid,uid,area,last_income_at in stores:
        packs=business_pack_count(sid,area)
        if packs<1:
            if last_income_at:
                with db() as c:
                    c.execute("UPDATE mall_stores SET last_income_at=0 WHERE id=?",(sid,)); c.commit()
            continue
        if not last_income_at:
            with db() as c:
                c.execute("UPDATE mall_stores SET last_income_at=? WHERE id=? AND last_income_at=0",(now,sid)); c.commit()
            continue
        periods=(now-int(last_income_at))//86400
        if periods<=0:
            continue
        income=store_daily_income(sid,area)
        if income<=0:
            with db() as c:
                c.execute("UPDATE mall_stores SET last_income_at=? WHERE id=?",(now,sid)); c.commit()
            continue
        total=income*periods
        with db() as c:
            c.execute("INSERT INTO bank(user_id,balance) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance",(uid,total))
            c.execute("UPDATE mall_stores SET last_income_at=? WHERE id=?",(int(last_income_at)+periods*86400,sid)); c.commit()
        log_tx(uid,"business_income",total,f"store={sid};days={periods};daily={income};packs={packs}")

async def business_income_loop():
    while True:
        try:
            await process_business_income_once()
        except Exception as exc:
            print(f"Business income error: {exc}")
        await asyncio.sleep(60)

@dp.callback_query(F.data=="user:business")
async def user_business(query:CallbackQuery):
    stores=user_mall_stores(menu_owner_id(query))
    if not stores:
        text="🏢 کسب و کار\n\n❌ کسب و کار فعالی نداری.\n\nبرای کسب درآمد باید حداقل یک مغازه در پاساژ و حداقل یک پک کامل داخل آن داشته باشی."
    else:
        lines=["🏢 کسب و کار\n"]
        for sid,area,purchase_price,purchased_at,last_income_at in stores:
            packs=business_pack_count(sid,area); daily=store_daily_income(sid,area)
            status="✅ فعال" if packs>0 else "⏸️ غیرفعال — هنوز پک کامل نداری"
            lines.append(f"🏬 مغازه #{sid} — {area} متر\n{status}\n📦 پک کامل: {packs}\n💵 درآمد روزانه: {format_coins(daily)} آریور")
        lines.append(f"\n💰 مجموع درآمد روزانه: {format_coins(business_total_daily_income(menu_owner_id(query)))} آریور\n🏦 درآمد هر ۲۴ ساعت خودکار به بانک واریز می‌شود.")
        text="\n\n".join(lines)
    await query.message.edit_text(text,reply_markup=keyboard([[button("🧰 لوازم کسب و کار","user:business_items")],[button("🏠 املاک","user:assets")],[button("🛍️ فروشگاه","user:shop")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:business_items")
async def user_business_items(query:CallbackQuery):
    await query.message.edit_text(business_items_text(menu_owner_id(query)),reply_markup=keyboard([[button("🛍️ فروشگاه","user:shop")],[button("🏢 کسب و کار","user:business")],[button("🏠 املاک","user:assets")],[button("🔙 منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data.startswith("bizbuy:"))
async def business_buy_store_callback(query:CallbackQuery):
    parts=query.data.split(":")
    if len(parts)!=3: await query.answer("❌ خرید نامعتبر است.",show_alert=True); return
    code=parts[1].upper()
    try: sid=int(parts[2])
    except Exception: await query.answer("❌ مغازه نامعتبر است.",show_alert=True); return
    item=next((x for x,c in BUSINESS_ITEM_CODES.items() if c==code),None)
    if not item: await query.answer("❌ کد آیتم نامعتبر است.",show_alert=True); return
    ok,why,price=business_shop_buy(menu_owner_id(query),item,sid)
    if not ok:
        await query.answer(f"❌ {format_coins(price)} آریور لازم داری." if why=="funds" else "❌ این مغازه متعلق به شما نیست.",show_alert=True); return
    await query.answer(f"✅ {item} به مغازه #{sid} اضافه شد!")
    await query.message.edit_text(normal_shop_text(menu_owner_id(query)),reply_markup=normal_shop_keyboard(menu_owner_id(query)))

def normal_shop_items():
    # هر چیزی که در فروشگاه سیاه است، فقط در فروشگاه سیاه نمایش داده می‌شود.
    return [(item, data) for item, data in SHOP_ITEMS_V2.items() if item not in BLACK_SHOP_ITEMS]

def normal_shop_text(uid):
    lines=["🛍️ فروشگاه عادی\n"]
    stores=user_mall_stores(uid)
    for i,(item,(base_cost,desc)) in enumerate(normal_shop_items(),1):
        cost=get_price(price_key_for("shop", item), base_cost)
        if item in BUSINESS_ITEM_CODES:
            status="🏬 قابل خرید برای مغازه" if stores else "🔒 ابتدا مغازه پاساژ بخر"
            lines.append(f"{i}. {business_item_label(item)} — 💎 {format_coins(cost)} آریور\n   {desc} | {status}")
        else:
            owned=inventory_qty(uid,item)
            status="🎒 داری" if owned else "🛒 خرید"
            lines.append(f"{i}. {item} — 💎 {format_coins(cost)} آریور\n   {desc} | {status}")
    lines.append("\n💡 لوازم کسب‌وکار فقط در صورتی قابل خرید هستند که حداقل یک مغازه پاساژ داشته باشی.")
    lines.append("💡 کد فروش لوازم کسب‌وکار در بخش «لوازم کسب و کار» نمایش داده می‌شود.")
    return "\n".join(lines)

def normal_shop_keyboard(uid):
    rows=[]
    stores=user_mall_stores(uid)
    for i,(item,(base_cost,_desc)) in enumerate(normal_shop_items(),1):
        cost=get_price(price_key_for("shop", item), base_cost)
        if item in BUSINESS_ITEM_CODES:
            rows.append([button(f"🏬 {business_item_label(item)} — {format_coins(cost)}", f"shopv2:buy:{i}")])
        else:
            owned=inventory_qty(uid,item)
            rows.append([button(f"🎒 {item} — {format_coins(cost)}" if owned else f"🛒 خرید {item} — {format_coins(cost)}", f"shopv2:buy:{i}")])
    rows += [[button("🕶️ فروشگاه سیاه","user:blackshop"),button("🐾 حیوانات","user:petshop")],[button("🔙 برگشت","user:passage")],[button("❌ بستن منو","menu:close")]]
    return keyboard(rows)

@dp.callback_query(F.data.startswith("shopv2:buy:"))
async def shop_v2_buy_callback(query:CallbackQuery):
    try:
        idx=int(query.data.rsplit(":",1)[1]); item=normal_shop_items()[idx-1][0]
    except Exception:
        await query.answer("❌ آیتم نامعتبر است.",show_alert=True); return
    if item in BUSINESS_ITEM_CODES:
        stores=user_mall_stores(menu_owner_id(query))
        if not stores:
            await query.answer("❌ ابتدا یک مغازه در پاساژ بخرید.",show_alert=True); return
        await query.message.edit_text(f"🏬 افزودن {item}\n\nاین وسیله را به کدام مغازه اضافه کنم؟",reply_markup=business_item_store_keyboard(item,menu_owner_id(query))); await query.answer(); return
    if inventory_qty(menu_owner_id(query),item)>0:
        await query.answer("🎒 این آیتم را از قبل داری.",show_alert=True); return
    ok,why,cost=shop_v2_buy(menu_owner_id(query),item)
    if not ok:
        msg=f"❌ {format_coins(cost)} آریور لازم داری." if why=="funds" else "❌ خرید انجام نشد."
        await query.answer(msg,show_alert=True); return
    await query.answer(f"✅ {item} خریداری شد!")
    await query.message.edit_text(normal_shop_text(menu_owner_id(query)),reply_markup=normal_shop_keyboard(menu_owner_id(query)))

@dp.callback_query(F.data=="user:daily")
async def user_daily(query:CallbackQuery):
    ok,st,remain,reward=claim_daily_box(menu_owner_id(query))
    if not ok:
        await query.answer(f"⏳ جایزه بعدی حدود {max(1,remain//3600)} ساعت دیگر آماده می‌شود.",show_alert=True); return
    await query.message.edit_text(f"🎁 جعبه روزانه باز شد!\n\n💎 جایزه: {format_coins(reward)} آریور\n🔥 استریک: {st['streak']} روز",reply_markup=user_menu_keyboard(menu_owner_id(query))); await query.answer("🎁 جایزه گرفتی!")

@dp.callback_query(F.data=="user:missions")
async def user_missions(query:CallbackQuery):
    rows=mission_rows(menu_owner_id(query))
    text="🎯 ماموریت‌های امروز\n\n"+"\n".join(f"{'✅' if claimed else ('🟢' if progress>=target else '⬜')} {mission_label(typ)} — {progress}/{target} — 🎁 {format_coins(reward)}" for typ,target,progress,reward,claimed in rows)
    kb=[]
    for typ,target,progress,reward,claimed in rows:
        if not claimed and progress>=target: kb.append([button(f"🎁 دریافت {mission_label(typ)}",f"mission:claim:{typ}")])
    kb.append([button("🔙 برگشت به منو","user:menu")])
    await query.message.edit_text(text,reply_markup=keyboard(kb)); await query.answer()

@dp.callback_query(F.data.startswith("mission:claim:"))
async def mission_claim(query:CallbackQuery):
    typ=query.data.split(":",2)[2]; ok,why,reward=claim_mission(menu_owner_id(query),typ)
    if not ok:
        await query.answer("❌ هنوز کامل نشده یا قبلاً گرفته‌ای.",show_alert=True); return
    await query.answer(f"🎁 {format_coins(reward)} آریور گرفتی!")
    await user_missions(query)

@dp.callback_query(F.data=="user:bank")
async def user_bank(query:CallbackQuery):
    if is_arsin_user(query.from_user):
        text = "🏦 بانک آریور\n\n💳 موجودی قابل استفاده: & آریور\n🔒 وضعیت حساب مدیریتی: بدون محدودیت\n\nحساب آرسین ویژه و غیرقابل هدف‌گیری است. 👑"
    else:
        text = f"🏦 بانک آریور\n\n💳 موجودی قابل استفاده: {format_coins(bank_balance(menu_owner_id(query)))} آریور\n🔒 مبلغ بلوکه‌شده: {format_coins(bank_blocked_amount(menu_owner_id(query)))} آریور\n\nبرای واریز: «واریز 1000»\nبرای برداشت: «برداشت 1000»"
    await query.message.edit_text(text,reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:shop")
async def user_shop(query:CallbackQuery):
    await query.message.edit_text(normal_shop_text(menu_owner_id(query)), reply_markup=normal_shop_keyboard(menu_owner_id(query)))
    await query.answer()

@dp.callback_query(F.data=="user:wealth")
async def user_wealth(query:CallbackQuery):
    rows=leaderboard_wealth(5)
    text="💰 پولدارای بازی\n\n"
    if not rows: text+="هنوز بازیکنی ثبت نشده است."
    for i,(uid,username,full_name,wealth) in enumerate(rows,1):
        name='@'+username if username else (full_name or display_name_by_id(uid))
        text+=f"{i}. {name} — 💎 {format_coins(wealth)} آریور\n"
    text+="\n🏦 موجودی بانک هم در این رتبه‌بندی حساب می‌شود."
    await query.message.edit_text(text,reply_markup=keyboard([[button("🔙 برگشت به منو","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()


@dp.callback_query(F.data=="user:leaderboard")
async def user_leaderboard(query:CallbackQuery):
    rows=leaderboard(); text="🏆 رتبه‌بندی آریور\n\n"
    for i,(uid,username,balance,level,luck,exp) in enumerate(rows,1):
        name='@'+username if username else display_name_by_id(uid)
        text+=f"{i}. {name} — 💎 {format_coins(balance)} — ⭐ لول {level}\n"
    await query.message.edit_text(text or "هنوز داده‌ای نیست.",reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:games")
async def user_games(query:CallbackQuery):
    await query.message.edit_text("🎮 بازی‌های شرطی دو نفره آریور 💎\n\n"
"⭕️ دوز: «دوز 100»\n✊ سنگ کاغذ قیچی: «سنگ کاغذ قیچی 100»\n🃏 جنگ کارت: «جنگ کارت 100»\n🎯 زوج یا فرد: «زوج یا فرد 100»\n🔢 حدس عدد: «حدس عدد 100»\n📈 بالاتر: «بالاتر 100»\n🎲 تاس جنگ: «تاس جنگ 100»\n🃏 بلک‌جک: «بلک‌جک ساده 100»\n⚡ مسابقه سرعت: «مسابقه سرعت 100»\n🥊 مبارزه: «مبارزه 100»\n\n👥 همه بازی‌های بالا دو نفره‌اند. سازنده مبلغ ورودی را می‌پردازد و نفر دوم با همان مبلغ وارد می‌شود.\n"
"⏰ اگر تا ۶۰ ثانیه کسی وارد نشود، مبلغ سازنده کامل برمی‌گردد.\n🤝 بازی مساوی = برگشت ورودی‌ها.\n🥊 در مبارزه، قدرت تجهیزات روی شانس برد اثر مستقیم دارد.",reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:history")
async def user_history(query:CallbackQuery):
    rows=recent_transactions(menu_owner_id(query)); text="📜 تاریخچه آریور\n\n"
    for kind,amount,bal,note,ts in rows:
        sign='+' if amount>0 else ''
        text+=f"• {kind}: {sign}{format_coins(amount)} 💎 | موجودی {format_coins(bal)}\n"
    await query.message.edit_text(text or "هنوز تراکنشی ثبت نشده.",reply_markup=keyboard([[button("🔙 برگشت","user:menu")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="user:market")
async def user_market(query:CallbackQuery):
    rows=active_market(); text="🛒 بازار آریور\n\n"
    kb=[]
    for lid,seller,amount,price,created in rows:
        name=display_name_by_id(seller)
        text+=f"#{lid} — 💎 {format_coins(amount)} آریور با قیمت {format_coins(price)} آریور\n"
        kb.append([button(f"🛒 خرید #{lid}",f"market:buy:{lid}")])
    text += "\nفروش: «فروش مقدار قیمت»\nمثال: فروش 1000 1200"
    kb += [[button("🔙 برگشت","user:menu")]]
    await query.message.edit_text(text,reply_markup=keyboard(kb)); await query.answer()

@dp.callback_query(F.data.startswith("market:buy:"))
async def market_buy(query:CallbackQuery):
    try: lid=int(query.data.rsplit(":",1)[1])
    except Exception: await query.answer("❌ آگهی نامعتبر.",show_alert=True); return
    ok,why,price,amount=buy_market_listing(menu_owner_id(query),lid)
    if not ok:
        msg={"missing":"آگهی پیدا نشد.","inactive":"آگهی قبلاً فروخته شده.","self":"نمی‌توانی آگهی خودت را بخری.","funds":f"{format_coins(price)} آریور لازم داری."}.get(why,"خرید انجام نشد.")
        await query.answer("❌ "+msg,show_alert=True); return
    await query.answer(f"✅ {format_coins(amount)} آریور خریدی!"); await user_market(query)

_menu_close_tasks = {}
_menu_owners = {}

def _menu_snapshot(message):
    if message is None:
        return None
    markup = getattr(message, "reply_markup", None)
    # InlineKeyboardMarkup is Pydantic; model_dump gives us a safe copy.
    try:
        markup_copy = markup.model_copy(deep=True) if markup is not None else None
    except Exception:
        markup_copy = markup
    return (str(getattr(message, "text", "") or ""), markup_copy)

def _menu_snapshot_key(snapshot):
    if not snapshot:
        return None
    text, markup = snapshot
    try:
        return (text, markup.model_dump_json() if markup is not None else None)
    except Exception:
        return (text, repr(markup))

def _menu_history_key(message):
    return (message.chat.id, message.message_id) if message is not None else None

def _menu_history_push(message):
    key=_menu_history_key(message)
    if not key:
        return
    snap=_menu_snapshot(message)
    if not snap:
        return
    hist=_MENU_HISTORY.setdefault(key,[])
    skey=_menu_snapshot_key(snap)
    if not hist or _menu_snapshot_key(hist[-1]) != skey:
        hist.append(snap)
    # Keep memory bounded.
    if len(hist)>30:
        del hist[:-30]

def _menu_history_clear(message):
    key=_menu_history_key(message)
    if key:
        _MENU_HISTORY.pop(key,None)

def register_menu_owner(message, owner_id):
    if message is None or not owner_id:
        return
    _menu_owners[(message.chat.id, message.message_id)] = int(owner_id)

def menu_owner_id(query):
    key=(query.message.chat.id, query.message.message_id) if query.message else None
    owner=_menu_owners.get(key) if key else None
    return int(owner) if owner else int(query.from_user.id)

def mark_menu_activity(message, owner_id=None):
    if message is None:
        return
    key=(message.chat.id,message.message_id)
    if owner_id:
        _menu_owners[key]=int(owner_id)
    old=_menu_close_tasks.pop(key,None)
    if old and not old.done():
        old.cancel()
    _menu_close_tasks[key]=asyncio.create_task(_auto_close_menu(message.chat.id,message.message_id))

async def _auto_close_menu(chat_id,message_id):
    try:
        await asyncio.sleep(MENU_INACTIVITY_TIMEOUT)
        try:
            await bot.delete_message(chat_id,message_id)
        except Exception:
            pass
    except asyncio.CancelledError:
        return
    finally:
        _menu_close_tasks.pop((chat_id,message_id),None)

def menu_share_keyboard():
    # این صفحه فقط صفحه انتخاب محل ارسال منو است؛ دکمه برگشت نباید
    # بعد از «ارسال در گروه» دوباره کاربر را به همین صفحه برگرداند.
    return keyboard([[button("📢 ارسال در گروه","menu:group"),button("💬 ارسال در پیوی","menu:private")],[button("❌ بستن منو","menu:close")]])


class MenuActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, CallbackQuery) and event.message is not None:
            key=(event.message.chat.id,event.message.message_id)
            owner=_menu_owners.get(key)
            if owner and int(event.from_user.id) != int(owner) and not is_arsin_id(event.from_user.id):
                await event.answer("🔒 این منو متعلق به کاربر دیگری است و فقط صاحب منو یا آرسین می‌تواند آن را کنترل کند.", show_alert=True)
                return
            mark_menu_activity(event.message)

            # Telegram's CallbackQuery.message is a snapshot and is not updated
            # after edit_text(), so navigation history must be saved BEFORE the
            # callback handler runs. Each navigation callback therefore pushes
            # the page the user is currently seeing.
            if event.data == "menu:back":
                hist=_MENU_HISTORY.get(key,[])
                if hist:
                    previous=hist.pop()
                    text,markup=previous
                    try:
                        await event.message.edit_text(text,reply_markup=markup)
                        register_menu_owner(event.message, owner or event.from_user.id)
                        await event.answer("🔙 برگشت")
                    except Exception:
                        await event.answer("❌ امکان برگشت نیست.",show_alert=True)
                else:
                    await event.answer("❌ صفحه قبلی وجود ندارد.",show_alert=True)
                return

            before=_menu_snapshot(event.message)
            # menu:home is a root jump and must never preserve the group/private
            # share page. The handler itself resets the history.
            if event.data != "menu:home" and before:
                _menu_history_push(event.message)
            await handler(event, data)
            return
        return await handler(event, data)

dp.callback_query.outer_middleware(MenuActivityMiddleware())

@dp.callback_query(F.data=="user:menu")
async def user_menu(query:CallbackQuery):
    if query.message.chat.type in ("group","supergroup"):
        await query.message.edit_text("📋 منو را کجا می‌خواهی دریافت کنی؟",reply_markup=menu_share_keyboard())
        register_menu_owner(query.message, menu_owner_id(query))
    else:
        await query.message.edit_text(profile_text(menu_owner_id(query)),reply_markup=user_menu_keyboard(menu_owner_id(query)))
    # Main menu is the root of navigation history.
    _MENU_HISTORY[_menu_history_key(query.message)] = [_menu_snapshot(query.message)]
    await query.answer()


@dp.callback_query(F.data=="menu:home")
async def menu_home(query:CallbackQuery):
    owner=menu_owner_id(query)
    await query.message.edit_text(profile_text(owner),reply_markup=user_menu_keyboard(owner))
    register_menu_owner(query.message, owner)
    _MENU_HISTORY.pop(_menu_history_key(query.message),None)
    await query.answer("🏠 منوی اصلی")


@dp.callback_query(F.data=="menu:group")
async def menu_send_group(query:CallbackQuery):
    if query.message.chat.type not in ("group","supergroup"):
        await query.answer("❌ این گزینه فقط داخل گروه است.",show_alert=True); return
    owner=menu_owner_id(query)
    await query.message.edit_text(profile_text(owner),reply_markup=user_menu_keyboard(owner))
    register_menu_owner(query.message, owner)
    _MENU_HISTORY.pop(_menu_history_key(query.message),None)
    await query.answer("📢 منوی اصلی باز شد.")


@dp.callback_query(F.data=="menu:private")
async def menu_send_private(query:CallbackQuery):
    uid=menu_owner_id(query)
    me=await bot.get_me()
    private_url=f"https://t.me/{me.username}?start=menu_after_join"
    with db() as c: row=c.execute("SELECT started FROM users WHERE id=?",(uid,)).fetchone()
    started=bool(row and row[0])
    if not started:
        rows=[]
        for slot in configured_link_slots():
            link=get_setting("link" + str(slot))
            if link:
                url=link_display_url(link)
                rows.append([InlineKeyboardButton(text=f"🔗 عضویت در لینک {slot}",url=url)])
        rows.append([InlineKeyboardButton(text="💬 ورود به پیوی ربات",url=private_url)])
        rows.append([button("✅ عضو شدم","check_membership")])
        await query.answer("💬 اول وارد پیوی ربات شو و /start بزن.",show_alert=True)
        await query.message.edit_text("🔒 اول وارد پیوی ربات شو و /start بزن.\nبعد از عضویت در لینک‌ها، منو در پیوی برایت باز می‌شود.",reply_markup=keyboard(rows)); return
    if not await check_memberships(uid):
        rows=[]
        for slot in configured_link_slots():
            link=get_setting("link" + str(slot))
            if link:
                url=link_display_url(link)
                rows.append([InlineKeyboardButton(text=f"🔗 عضویت در لینک {slot}",url=url)])
        rows.append([InlineKeyboardButton(text="💬 رفتن به پیوی ربات",url=private_url)])
        rows.append([button("✅ عضو شدم","check_membership")])
        await query.answer("❌ هنوز در لینک‌ها عضو نیستی.",show_alert=True)
        await query.message.edit_text("🔒 برای ارسال منو در پیوی، ابتدا در همه لینک‌ها عضو شو.\nبعد از عضویت «عضو شدم» را بزن.",reply_markup=keyboard(rows)); return
    try:
        await bot.send_message(uid,profile_text(uid),reply_markup=user_menu_keyboard(uid))
        await query.message.edit_text("💬 منو پیویت ارسال شد.")
        await query.answer("💬 منو در پیوی ارسال شد.")
    except Exception:
        await query.answer("❌ ارسال پیوی ممکن نشد؛ پیوی ربات را باز کن و /start بزن.",show_alert=True)

@dp.callback_query(F.data=="user:upgrade_menu")
async def user_upgrade_menu(query:CallbackQuery):
    await query.message.edit_text("⬆️ بخش ارتقا\n\nیکی از سه مورد زیر را برای ارتقا انتخاب کن:",reply_markup=upgrade_menu_keyboard())
    await query.answer()

@dp.callback_query(F.data=="user:passage")
async def user_passage(query:CallbackQuery):
    await query.message.edit_text("🏬 پاساژ\n\nیکی از بخش‌های زیر را انتخاب کن:",reply_markup=passage_keyboard())
    await query.answer()

@dp.callback_query(F.data=="user:assets_menu")
async def user_assets_menu(query:CallbackQuery):
    await query.message.edit_text("💼 دارایی ها\n\nبخش موردنظر را انتخاب کن:",reply_markup=assets_menu_keyboard())
    await query.answer()

@dp.callback_query(F.data=="user:leaderboard_menu")
async def user_leaderboard_menu(query:CallbackQuery):
    await query.message.edit_text("🏆 لیدر بورد\n\nدسته‌بندی موردنظر را انتخاب کن:",reply_markup=leaderboard_menu_keyboard())
    await query.answer()

@dp.callback_query(F.data=="user:best_leaderboard")
async def user_best_leaderboard(query:CallbackQuery):
    with db() as c:
        rows=c.execute(
            "SELECT u.id,u.username,u.full_name,s.xp,s.points FROM users u JOIN player_stats s ON s.user_id=u.id "
            "WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) "
            "AND lower(COALESCE(u.username,'')) != lower(?) "
            "ORDER BY s.xp DESC,s.points DESC,u.id ASC LIMIT 5",
            (ARSIN_USERNAME,)
        ).fetchall()
    lines=["⭐ بهترین های بازی — ۵ نفر برتر بر اساس XP\n"]
    if not rows:
        lines.append("هنوز داده‌ای برای نمایش وجود ندارد.")
    else:
        for i,(uid,username,full_name,xp,points) in enumerate(rows,1):
            name='@'+username if username else (full_name or display_name_by_id(uid))
            rank,_=player_rank(uid)
            lines.append(f"{i}. {name}\n   🧠 XP: {xp} | 🏆 رنک: {rank} | ⭐ امتیاز: {points}")
    await query.message.edit_text("\n".join(lines),reply_markup=keyboard([[button("🔙 لیدر بورد","user:leaderboard_menu")],[button("❌ بستن منو","menu:close")]]))
    await query.answer()

@dp.callback_query(F.data=="user:football_leaderboard")
async def user_football_leaderboard(query:CallbackQuery):
    with db() as c:
        rows=c.execute(
            "SELECT t.id,t.user_id,t.club_name,t.wins,t.losses,t.draws,t.games,u.username,u.full_name "
            "FROM football_teams t JOIN users u ON u.id=t.user_id "
            "WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=t.user_id) "
            "AND lower(COALESCE(u.username,'')) != lower(?) AND (t.wins+t.losses)>0 "
            "ORDER BY CAST(t.wins AS REAL)/NULLIF(t.wins+t.losses,0) DESC, (t.wins+t.losses) DESC, t.wins DESC, t.id ASC LIMIT 5",
            (ARSIN_USERNAME,)
        ).fetchall()
    lines=["⚽ بهترین تیم های فوتبال — ۵ رتبه برتر\n", "📊 معیار رتبه‌بندی: میانگین/درصد برد و باخت؛ قدرت تیم در رتبه‌بندی محاسبه نمی‌شود.\n"]
    if not rows:
        lines.append("هنوز تیم فوتبالی با سابقه برد/باخت ثبت نشده است.")
    else:
        for i,(tid,uid,club,wins,losses,draws,games,username,full_name) in enumerate(rows,1):
            played=int(wins)+int(losses)
            rate=(int(wins)*100/played) if played else 0
            owner='@'+username if username else (full_name or display_name_by_id(uid))
            lines.append(f"{i}. ⚽ {club}\n   👤 {owner}\n   🏆 برد: {wins} | 💔 باخت: {losses} | 📈 درصد برد: {rate:.1f}%")
    await query.message.edit_text("\n".join(lines),reply_markup=keyboard([[button("🔙 لیدر بورد","user:leaderboard_menu")],[button("❌ بستن منو","menu:close")]]))
    await query.answer()

@dp.callback_query(F.data=="user:activity_leaderboard")
async def user_activity_leaderboard(query:CallbackQuery):
    with db() as c:
        wins=c.execute("SELECT u.id,u.username,u.full_name,s.wins,s.points FROM users u JOIN player_stats s ON s.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) ORDER BY s.wins DESC,s.points DESC LIMIT 5").fetchall()
        games=c.execute("SELECT u.id,u.username,u.full_name,s.games,s.xp FROM users u JOIN player_stats s ON s.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) ORDER BY s.games DESC,s.xp DESC LIMIT 5").fetchall()
        aunt=c.execute("SELECT u.id,u.username,u.full_name,a.games_count FROM users u JOIN aunt_game_stats a ON a.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) ORDER BY a.games_count DESC,u.id ASC LIMIT 5").fetchall()
        props=c.execute("SELECT u.id,u.username,u.full_name,COUNT(p.id) FROM users u LEFT JOIN properties p ON p.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) GROUP BY u.id ORDER BY COUNT(p.id) DESC,u.id ASC LIMIT 5").fetchall()
    def n(uid,username,full_name): return '@'+username if username else (full_name or display_name_by_id(uid))
    lines=["📊 لیدر بورد فعالیت‌ها\n"]
    lines.append("🏆 بیشترین برد")
    lines.extend(f"{i}. {n(uid,un,fn)} — {w} برد" for i,(uid,un,fn,w,pts) in enumerate(wins,1))
    lines.append("\n🎮 بیشترین بازی")
    lines.extend(f"{i}. {n(uid,un,fn)} — {g} بازی" for i,(uid,un,fn,g,xp) in enumerate(games,1))
    lines.append("\n👑 بیشترین خاله‌بازی")
    lines.extend(f"{i}. {n(uid,un,fn)} — {cnt} بار" for i,(uid,un,fn,cnt) in enumerate(aunt,1))
    lines.append("\n🏠 بیشترین املاک")
    lines.extend(f"{i}. {n(uid,un,fn)} — {cnt} ملک" for i,(uid,un,fn,cnt) in enumerate(props,1))
    await query.message.edit_text("\n".join(lines),reply_markup=keyboard([[button("🔙 لیدر بورد","user:leaderboard_menu")],[button("❌ بستن منو","menu:close")]]))
    await query.answer()

@dp.callback_query(F.data=="user:trade")
async def user_trade(query:CallbackQuery): await query.message.edit_text("📈 ترید آریور 🎲\n\nمبلغ را انتخاب کن:",reply_markup=trade_keyboard()); await query.answer()

@dp.callback_query(F.data=="user:level")
async def user_level(query:CallbackQuery):
    ok,r,c=upgrade_level(menu_owner_id(query))
    if not ok: await query.answer(f"❌ {format_coins(c)} آریور برای ارتقای لول لازم داری.",show_alert=True); return
    await query.message.edit_text(f"🎉 لول ارتقا یافت! ⭐\n💸 {format_coins(c)} آریور کسر شد.\n\n{profile_text(menu_owner_id(query))}",reply_markup=user_menu_keyboard(menu_owner_id(query))); await query.answer()

@dp.callback_query(F.data=="user:luck")
async def user_luck(query:CallbackQuery):
    ok,r,c,why=upgrade_stat(menu_owner_id(query),"luck_level")
    if not ok: await query.answer("🏆 لول شانس کامل است." if why=="max" else f"❌ {format_coins(c)} آریور لازم داری.",show_alert=True); return
    await query.message.edit_text(f"🍀 لول شانس ارتقا یافت!\n💸 {format_coins(c)} آریور کسر شد.\n\n{profile_text(menu_owner_id(query))}",reply_markup=user_menu_keyboard(menu_owner_id(query))); await query.answer()

@dp.callback_query(F.data=="user:exp")
async def user_exp(query:CallbackQuery):
    ok,r,c,why=upgrade_stat(menu_owner_id(query),"exp_level")
    if not ok: await query.answer("🏆 لول تجربه کامل است." if why=="max" else f"❌ {format_coins(c)} آریور لازم داری.",show_alert=True); return
    await query.message.edit_text(f"🧠 لول تجربه ارتقا یافت!\n💸 {format_coins(c)} آریور کسر شد.\n\n{profile_text(menu_owner_id(query))}",reply_markup=user_menu_keyboard(menu_owner_id(query))); await query.answer()

@dp.callback_query(F.data.startswith("trade:"))
async def trade_callback(query:CallbackQuery):
    amount=int(query.data.split(":",1)[1]); net,r,status=do_trade(menu_owner_id(query),amount)
    if status=="funds": await query.answer("❌ موجودی آریورت کافی نیست.",show_alert=True); return
    if status=="minimum": await query.answer("❌ برای ترید، مبلغ باید حداقل 2 آریور باشد و سود/ضرر حداقل یک‌سوم مبلغ ترید است.",show_alert=True); return
    result=f"🟢 {format_coins(net)} آریور سود کردی! 📈" if net>0 else f"🔴 {format_coins(abs(net))} آریور ضرر کردی. 📉"
    await query.message.edit_text(f"🎲 نتیجه ترید {format_coins(amount)} آریور\n\n{result}\n{balance_display(menu_owner_id(query))}",reply_markup=user_menu_keyboard(menu_owner_id(query))); await query.answer("🎲 ترید انجام شد!")

@dp.callback_query(F.data=="user:help")
async def user_help(query:CallbackQuery):
    await query.message.edit_text(user_help_text(),reply_markup=help_categories_keyboard()); await query.answer()

@dp.callback_query(F.data=="user:transfer")
async def user_transfer(query:CallbackQuery): transfer_pending[menu_owner_id(query)]="amount"; await query.message.answer("💸 مقدار آریور را بفرست؛ بعد روی پیام فرد موردنظر ریپلای کن.\nمثال: 500"); await query.answer()

# ================================================================
# ARSIN COIN / GIFT ADMIN
# ================================================================
@dp.callback_query(F.data == "menu:close")
async def close_menu_callback(query: CallbackQuery):
    key=(query.message.chat.id,query.message.message_id)
    _MENU_HISTORY.pop(key,None)
    _menu_owners.pop(key,None)
    task=_menu_close_tasks.pop(key,None)
    if task and not task.done():
        task.cancel()
    try:
        await query.message.delete()
    except Exception:
        try:
            await query.message.edit_text("✅ منو بسته شد.")
        except Exception:
            pass
    await query.answer("منو بسته شد")



@dp.callback_query(F.data == "admin:football")
async def admin_football(query:CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"football"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    rate=football_income_rate_per_power()
    await query.message.edit_text(f"⚽ مدیریت فوتبال\n\nاز اینجا می‌توانی قیمت بازیکنان، مربی‌ها و درآمد روزانه فوتبال را مدیریت کنی.\n\n💰 نرخ درآمد فعلی: {format_coins(rate)} آریور به ازای هر ۱ قدرت تیم در روز",reply_markup=keyboard([[button("💰 تغییر قیمت بازیکنان","ftadmin:pricepos"),button("➕ افزودن بازیکن","ftadmin:add")],[button("👔 افزودن مربی","ftadmin:coach_add")],[button("💵 تغییر درآمد روزانه","ftadmin:income_rate")],[button("🔙 پنل مدیریت","admin:panel")],[button("❌ بستن پنل","menu:close")]])); await query.answer()

@dp.callback_query(F.data=="ftadmin:income_rate")
async def ftadmin_income_rate(query:CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"football"):
        await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    pending_admin[query.from_user.id]=( "football_income_rate", )
    await query.message.answer(f"💵 نرخ درآمد روزانه فوتبال\n\nمقدار فعلی: {format_coins(football_income_rate_per_power())} آریور برای هر ۱ قدرت در روز\n\nمقدار جدید را فقط به صورت عدد ارسال کن:")
    await query.answer()

@dp.callback_query(F.data=="ftadmin:add")
async def ftadmin_add(query:CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"football"): await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    pending_admin[query.from_user.id]=( "football_add_position", )
    await query.message.answer("➕ افزودن بازیکن\n\nپست بازیکن را فقط یکی از این‌ها ارسال کن:\nدفاع\nهافبک\nحمله\nدروازه بان")
    await query.answer()

@dp.callback_query(F.data=="ftadmin:coach_add")
async def ftadmin_coach_add(query:CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"football"):
        await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    pending_admin[query.from_user.id]=( "football_add_coach_name", )
    await query.message.answer("👔 افزودن مربی جدید\n\nنام مربی را ارسال کن:")
    await query.answer()


@dp.callback_query(F.data=="ftadmin:pricepos")
async def ftadmin_pricepos(query:CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"football"): await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    await query.message.edit_text("💰 تغییر قیمت بازیکنان\n\nپست را انتخاب کن:",reply_markup=keyboard([[button("🛡️ دفاع","ftadmin:pricepos:دفاع"),button("🎯 هافبک","ftadmin:pricepos:هافبک")],[button("⚔️ حمله","ftadmin:pricepos:حمله"),button("🧤 دروازه بان","ftadmin:pricepos:دروازه بان")],[button("🔙 مدیریت فوتبال","admin:football")]])); await query.answer()

@dp.callback_query(F.data.startswith("ftadmin:pricepos:"))
async def ftadmin_price_list(query:CallbackQuery):
    pos=query.data.split(":",2)[2]
    with db() as c: rows=c.execute("SELECT id,name,power,monthly_price FROM football_players WHERE position=? ORDER BY power DESC,id",(pos,)).fetchall()
    out=[]
    for pid,name,power,price in rows: out.append([button(f"{name} | 💪{power} | {format_coins(price)}"[:60],f"ftadmin:price:{pid}")])
    out.append([button("🔙 مدیریت فوتبال","admin:football")])
    await query.message.edit_text(f"💰 قیمت بازیکنان {pos}\n\nروی بازیکن بزن و قیمت جدید را ارسال کن:",reply_markup=keyboard(out)); await query.answer()

@dp.callback_query(F.data.startswith("ftadmin:price:"))
async def ftadmin_price_edit(query:CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"football"): await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    pid=int(query.data.rsplit(":",1)[1])
    with db() as c:r=c.execute("SELECT name,power,position,monthly_price FROM football_players WHERE id=?",(pid,)).fetchone()
    if not r: await query.answer("❌ بازیکن پیدا نشد.",show_alert=True); return
    pending_admin[query.from_user.id]=( "football_price", pid )
    await query.message.answer(f"💰 بازیکن: {r[0]}\n📌 پست: {r[2]} | 💪 قدرت: {r[1]}\n💵 قیمت فعلی ماهانه: {format_coins(r[3])}\n\nقیمت جدید ماهانه را فقط به صورت عدد ارسال کن:")
    await query.answer()

@dp.callback_query(F.data == "admin:lb_rewards")
async def admin_leaderboard_rewards(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"addcoins"):
        await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    await query.message.edit_text("🏆 جایزه لیدربورد\n\nلیدربورد موردنظر را انتخاب کن:",reply_markup=leaderboard_reward_keyboard())
    await query.answer()

@dp.callback_query(F.data.startswith("lbr:board:"))
async def leaderboard_reward_board(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"addcoins"):
        await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    board=query.data.rsplit(":",1)[1]
    if board not in LEADERBOARD_BOARDS:
        await query.answer("❌ لیدربورد نامعتبر.",show_alert=True); return
    await query.message.edit_text(f"🏆 {LEADERBOARD_BOARDS[board]}\n\nدوره جایزه را انتخاب کن:",reply_markup=leaderboard_reward_period_keyboard(board))
    await query.answer()

@dp.callback_query(F.data.startswith("lbr:period:"))
async def leaderboard_reward_period(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"addcoins"):
        await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    _,_,board,period=query.data.split(":")
    if board not in LEADERBOARD_BOARDS or period not in LEADERBOARD_PERIODS:
        await query.answer("❌ انتخاب نامعتبر.",show_alert=True); return
    await query.message.edit_text(f"🏆 {LEADERBOARD_BOARDS[board]}\n{LEADERBOARD_PERIODS[period]}\n\nرتبه موردنظر را انتخاب کن:",reply_markup=leaderboard_reward_rank_keyboard(board,period))
    await query.answer()

@dp.callback_query(F.data.startswith("lbr:set:"))
async def leaderboard_reward_set(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"addcoins"):
        await query.answer("❌ دسترسی ندارید.",show_alert=True); return
    _,_,board,period,rank_s=query.data.split(":")
    try: rank=int(rank_s)
    except Exception: rank=0
    if board not in LEADERBOARD_BOARDS or period not in LEADERBOARD_PERIODS or rank not in range(1,6):
        await query.answer("❌ انتخاب نامعتبر.",show_alert=True); return
    pending_admin[query.from_user.id]=( "leaderboard_reward_amount", board, period, rank )
    current=leaderboard_reward_amount(board,period,rank)
    await query.message.answer(f"🏆 {LEADERBOARD_BOARDS[board]}\n{LEADERBOARD_PERIODS[period]}\n🥇 رتبه {rank}\n\n💰 مقدار فعلی: {format_coins(current)} آریور\n✏️ مقدار جایزه جدید را فقط به صورت عدد ارسال کن:")
    await query.answer()

# ================================================================
# LOTTERY SYSTEM
# ================================================================
def lottery_code(lid):
    return f"L-{int(lid):06d}"

def lottery_joined(lid, uid):
    with db() as c:
        return c.execute("SELECT 1 FROM lottery_players WHERE lottery_id=? AND user_id=?", (int(lid),int(uid))).fetchone() is not None

def lottery_rows(chat_id=None, active_only=True):
    sql="SELECT id,code,chat_id,message_id,creator_id,prize,draw_at,min_players,max_players,status,created_at FROM lotteries"
    args=[]
    cond=[]
    if chat_id is not None:
        cond.append("chat_id=?"); args.append(int(chat_id))
    if active_only:
        cond.append("status='active'")
    if cond: sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY id DESC"
    with db() as c:
        return c.execute(sql,args).fetchall()

def lottery_participant_count(lid):
    with db() as c:
        return int(c.execute("SELECT COUNT(*) FROM lottery_players WHERE lottery_id=?",(int(lid),)).fetchone()[0])

async def lottery_broadcast_targets():
    targets=[]
    with db() as c:
        targets.extend((int(r[0]),"private") for r in c.execute(
            "SELECT id FROM users WHERE started=1 AND NOT EXISTS "
            "(SELECT 1 FROM bot_bans bb WHERE bb.user_id=users.id)"
        ).fetchall())
        targets.extend((int(r[0]),r[1]) for r in c.execute(
            "SELECT chat_id,chat_type FROM known_chats WHERE active=1"
        ).fetchall())
    seen=set()
    out=[]
    for chat_id,chat_type in targets:
        if chat_id in seen:
            continue
        seen.add(chat_id)
        out.append((chat_id,chat_type))
    return out

async def lottery_store_message(lid, chat_id, message_id):
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO lottery_messages(lottery_id,chat_id,message_id) VALUES(?,?,?)",
            (int(lid),int(chat_id),int(message_id))
        )
        c.commit()

def lottery_text(row, uid=None):
    lid,code,chat_id,message_id,creator,prize,draw_at,min_players,max_players,status,created=row
    count=lottery_participant_count(lid)
    left=max(0,int(draw_at)-int(time.time()))
    hours=left//3600; mins=(left%3600)//60
    time_txt=f"{hours} ساعت و {mins} دقیقه" if hours else f"{mins} دقیقه"
    min_txt="نامحدود" if int(min_players)==0 else f"{int(min_players):,} نفر"
    max_txt="نامحدود" if int(max_players)==0 else f"{int(max_players):,} نفر"
    joined=lottery_joined(lid,uid) if uid else False
    capacity=(f"{count:,}/{int(max_players):,}" if int(max_players)>0 else f"{count:,}/نامحدود")
    return (f"🎟️ قرعه‌کشی {code}\n\n"
            f"💰 جایزه: {format_coins(prize)} آریور\n"
            f"⏳ زمان قرعه‌کشی: {time_txt} دیگر\n"
            f"👥 شرکت‌کنندگان: {capacity}\n"
            f"🔽 حداقل شرکت‌کننده: {min_txt}\n"
            f"🔼 حداکثر شرکت‌کننده: {max_txt}\n\n"
            f"{'✅ شما در این قرعه‌کشی شرکت کرده‌اید.' if joined else '❌ شما هنوز در این قرعه‌کشی شرکت نکرده‌اید.'}")

def lottery_live_buttons(lid):
    with db() as c:
        row=c.execute("SELECT draw_at,max_players,status FROM lotteries WHERE id=?",(int(lid),)).fetchone()
    if not row or row[2] != "active":
        return []
    draw_at=int(row[0]); maxp=int(row[1])
    left=max(0, draw_at-int(time.time()))
    h=left//3600; m=(left%3600)//60; sec=left%60
    if h:
        time_txt=f"{h:02d}:{m:02d}:{sec:02d}"
    else:
        time_txt=f"{m:02d}:{sec:02d}"
    count=lottery_participant_count(lid)
    if maxp>0 and count>=maxp:
        count_txt=f"👥 تکمیل ({count:,})"
    elif maxp>0:
        count_txt=f"👥 {count:,}/{maxp:,}"
    else:
        count_txt=f"👥 {count:,}/∞"
    return [
        button(f"⏳ {time_txt}","lottery:time"),
        button(count_txt,"lottery:count")
    ]

def lottery_group_keyboard(lid):
    rows=[[button("🎟️ شرکت در قرعه‌کشی",f"lottery:join:{lid}")]]
    live=lottery_live_buttons(lid)
    if live:
        rows.append(live)
    return keyboard(rows)

def lottery_user_keyboard(lid, uid):
    with db() as c:
        row=c.execute("SELECT max_players,status FROM lotteries WHERE id=?",(int(lid),)).fetchone()
    if not row or row[1] != "active":
        return keyboard([[button("🏠 برگشت به منو","menu:home")]])
    maxp=int(row[0]); count=lottery_participant_count(lid)
    joined=lottery_joined(lid,uid)
    rows=[]
    if joined:
        rows.append([button("🎟️ شرکت در قرعه‌کشی",f"lottery:join:{lid}")])
    elif maxp>0 and count>=maxp:
        rows.append([button("🎟️ شرکت در قرعه‌کشی",f"lottery:join:{lid}")])
    else:
        rows.append([button("🎟️ شرکت در قرعه‌کشی",f"lottery:join:{lid}")])
    live=lottery_live_buttons(lid)
    if live:
        rows.append(live)
    rows.append([button("🔙 قرعه‌کشی‌ها","user:lotteries"),button("🏠 برگشت به منو","menu:home")])
    return keyboard(rows)

def lottery_list_keyboard(rows, uid):
    out=[]
    for row in rows:
        lid,code,chat_id,message_id,creator,prize,draw_at,minp,maxp,status,created=row
        count=lottery_participant_count(lid)
        joined=lottery_joined(lid,uid)
        cap="∞" if int(maxp)==0 else str(int(maxp))
        mark="✅" if joined else "❌"
        out.append([button(f"{mark} {code} | 💰 {format_coins(prize)} | 👥 {count}/{cap}",f"lottery:view:{lid}")])
    # فقط یک مسیر خروج از فهرست قرعه‌کشی‌ها؛ از نمایش دکمه‌های خروج تکراری جلوگیری می‌شود.
    out.append([button("🏠 برگشت به منو","menu:home")])
    return keyboard(out)

@dp.callback_query(F.data == "user:lotteries")
async def user_lotteries(query: CallbackQuery):
    uid=menu_owner_id(query)
    # منوی قرعه‌کشی باید قرعه‌کشی‌های فعال را مستقل از چتی که منو در آن باز شده نشان دهد.
    # برای همین در منوی خصوصی، همه قرعه‌کشی‌های فعال نمایش داده می‌شوند.
    rows=lottery_rows(None,True)
    if not rows:
        await query.message.edit_text("🎟️ قرعه‌کشی‌ها\n\nفعلاً قرعه‌کشی فعالی وجود ندارد.",reply_markup=keyboard([[button("🏠 برگشت به منو","menu:home")]]))
    else:
        await query.message.edit_text("🎟️ قرعه‌کشی‌های فعال\n\nعلامت ✅ یعنی شما قبلاً در آن شرکت کرده‌اید.",reply_markup=lottery_list_keyboard(rows,uid))
    await query.answer()

@dp.callback_query(F.data.startswith("lottery:view:"))
async def lottery_view(query: CallbackQuery):
    try: lid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ قرعه‌کشی نامعتبر است.",show_alert=True); return
    with db() as c: row=c.execute("SELECT id,code,chat_id,message_id,creator_id,prize,draw_at,min_players,max_players,status,created_at FROM lotteries WHERE id=?",(lid,)).fetchone()
    if not row or row[9] != "active":
        await query.answer("❌ این قرعه‌کشی دیگر فعال نیست.",show_alert=True); return
    uid=menu_owner_id(query)
    await query.message.edit_text(lottery_text(row,uid),reply_markup=lottery_user_keyboard(lid,uid))
    await query.answer()

@dp.callback_query(F.data.startswith("lottery:join:"))
async def lottery_join(query: CallbackQuery):
    try: lid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ قرعه‌کشی نامعتبر است.",show_alert=True); return
    uid=query.from_user.id
    with db() as c:
        row=c.execute("SELECT id,code,chat_id,message_id,creator_id,prize,draw_at,min_players,max_players,status,created_at FROM lotteries WHERE id=?",(lid,)).fetchone()
        if not row or row[9] != "active":
            await query.answer("❌ قرعه‌کشی دیگر فعال نیست.",show_alert=True); return
        if c.execute("SELECT 1 FROM lottery_players WHERE lottery_id=? AND user_id=?",(lid,uid)).fetchone():
            await query.answer("✅ شما قبلاً در این قرعه‌کشی شرکت کرده‌اید.",show_alert=True); return
        maxp=int(row[8])
        count=int(c.execute("SELECT COUNT(*) FROM lottery_players WHERE lottery_id=?",(lid,)).fetchone()[0])
        if maxp>0 and count>=maxp:
            await query.answer("⛔ ظرفیت قرعه‌کشی تکمیل شده است.",show_alert=True); return
        c.execute("INSERT INTO lottery_players(lottery_id,user_id,joined_at) VALUES(?,?,?)",(lid,uid,int(time.time())))
        c.commit()
    # پیام قرعه‌کشی اصلی نباید بعد از شرکت یک کاربر ویرایش شود؛
    # بنابراین دکمه برای همه کاربران باقی می‌ماند و فقط کاربرِ تکراری خطا می‌گیرد.
    try:
        if query.message.chat.type == "private":
            await query.message.edit_text(lottery_text(row,uid),reply_markup=lottery_user_keyboard(lid,uid))
    except Exception:
        pass
    try:
        await bot.send_message(uid,f"🎟️ شما در قرعه‌کشی با کد {row[1]} شرکت کردید.\n\n💰 مقدار جایزه: {format_coins(row[5])} آریور\n🔽 حداقل شرکت‌کننده: {'نامحدود' if int(row[7])==0 else format_coins(row[7])+' نفر'}\n🔼 حداکثر شرکت‌کننده: {'نامحدود' if int(row[8])==0 else format_coins(row[8])+' نفر'}\n⏳ قرعه‌کشی در زمان تعیین‌شده انجام می‌شود.\n\nموفق باشی 🍀")
    except Exception:
        pass
    await query.answer("🎟️ با موفقیت در قرعه‌کشی شرکت کردی.")

@dp.callback_query(F.data == "lottery:time")
async def lottery_time_info(query: CallbackQuery):
    await query.answer("⏳ زمان باقی‌مانده به‌صورت زنده نمایش داده می‌شود.", show_alert=False)

@dp.callback_query(F.data == "lottery:count")
async def lottery_count_info(query: CallbackQuery):
    await query.answer("👥 تعداد شرکت‌کنندگان در دکمه نمایش داده می‌شود.", show_alert=False)

@dp.callback_query(F.data == "lottery:nope")
async def lottery_nope(query: CallbackQuery):
    await query.answer("ℹ️ این دکمه در حال حاضر قابل استفاده نیست.",show_alert=True)

@dp.callback_query(F.data == "lottery:create")
async def lottery_create(query: CallbackQuery):
    if not is_arsin_id(query.from_user.id):
        await query.answer("❌ فقط آرسین.",show_alert=True); return
    LOTTERY_PENDING[query.from_user.id]={"step":"prize","chat_id":query.message.chat.id,"message_id":query.message.message_id}
    await query.message.answer("🎟️ ساخت قرعه‌کشی\n\n💰 مقدار جایزه را وارد کن:")
    await query.answer()

@dp.callback_query(F.data == "lottery:min_limited_prompt")
async def lottery_min_limited_prompt(query: CallbackQuery):
    if not is_arsin_id(query.from_user.id): await query.answer("❌ فقط آرسین.",show_alert=True); return
    st=LOTTERY_PENDING.get(query.from_user.id)
    if not st: await query.answer("❌ مرحله ساخت منقضی شده.",show_alert=True); return
    st["step"]="min_value"
    await query.message.edit_text("🔢 حداقل تعداد شرکت‌کننده را به صورت عدد وارد کن:")
    await query.answer()

@dp.callback_query(F.data == "lottery:min_unlimited")
async def lottery_min_unlimited(query: CallbackQuery):
    await lottery_min_choice(query,0)

@dp.callback_query(F.data.startswith("lottery:min_limited:"))
async def lottery_min_limited(query: CallbackQuery):
    try: n=int(query.data.rsplit(":",1)[1])
    except Exception: n=0
    await lottery_min_choice(query,n)

async def lottery_min_choice(query, value):
    state=LOTTERY_PENDING.get(query.from_user.id)
    if not state: await query.answer("❌ مرحله ساخت منقضی شده.",show_alert=True); return
    state["min_players"]=int(value)
    state["step"]="max_choice"
    await query.message.edit_text("🔼 حداکثر تعداد شرکت‌کننده را مشخص کن:",reply_markup=keyboard([[button("♾️ نامحدود","lottery:max_unlimited")],[button("🔢 محدود","lottery:max_limited")],[button("❌ بستن منو","menu:close")]]))
    await query.answer()

@dp.callback_query(F.data == "lottery:max_unlimited")
async def lottery_max_unlimited(query: CallbackQuery):
    await lottery_max_choice(query,0)

@dp.callback_query(F.data == "lottery:max_limited")
async def lottery_max_limited(query: CallbackQuery):
    state=LOTTERY_PENDING.get(query.from_user.id)
    if not state: await query.answer("❌ مرحله ساخت منقضی شده.",show_alert=True); return
    state["step"]="max_value"
    await query.message.edit_text("🔢 حداکثر تعداد شرکت‌کننده را به صورت عدد وارد کن:")
    await query.answer()

async def lottery_max_choice(query, value):
    state=LOTTERY_PENDING.get(query.from_user.id)
    if not state: await query.answer("❌ مرحله ساخت منقضی شده.",show_alert=True); return
    value=int(value); minp=int(state.get("min_players",0))
    if value and minp and value<minp:
        await query.answer("❌ حداکثر نمی‌تواند کمتر از حداقل باشد.",show_alert=True); return
    state["max_players"]=value
    state["step"]="confirm"
    await query.message.edit_text(lottery_pending_preview(state),reply_markup=keyboard([[button("✅ تأیید و انتشار","lottery:confirm")],[button("❌ لغو","menu:close")]]))
    await query.answer()

def lottery_pending_preview(st):
    draw_at=int(st["draw_at"]); left=max(0,draw_at-int(time.time())); h=left//3600; m=(left%3600)//60
    return (f"🎟️ پیش‌نمایش قرعه‌کشی\n\n💰 جایزه: {format_coins(st['prize'])} آریور\n⏳ مهلت: {h} ساعت و {m} دقیقه\n"
            f"🔽 حداقل: {'نامحدود' if not st.get('min_players') else format_coins(st['min_players'])+' نفر'}\n"
            f"🔼 حداکثر: {'نامحدود' if not st.get('max_players') else format_coins(st['max_players'])+' نفر'}\n\nآیا تأیید و منتشر شود؟")

@dp.callback_query(F.data == "lottery:confirm")
async def lottery_confirm(query: CallbackQuery):
    if not is_arsin_id(query.from_user.id):
        await query.answer("❌ فقط آرسین.",show_alert=True); return
    st=LOTTERY_PENDING.get(query.from_user.id)
    if not st or st.get("step")!="confirm":
        await query.answer("❌ مرحله ساخت پیدا نشد.",show_alert=True); return
    if int(st.get("max_players",0)) and int(st.get("min_players",0))>int(st.get("max_players",0)):
        await query.answer("❌ حداقل بیشتر از حداکثر است.",show_alert=True); return
    with db() as c:
        cur=c.execute("INSERT INTO lotteries(code,chat_id,message_id,creator_id,prize,draw_at,min_players,max_players,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",("TEMP",int(st["chat_id"]),0,query.from_user.id,int(st["prize"]),int(st["draw_at"]),int(st.get("min_players",0)),int(st.get("max_players",0)),"active",int(time.time())))
        lid=cur.lastrowid; code=lottery_code(lid); c.execute("UPDATE lotteries SET code=? WHERE id=?",(code,lid)); c.commit()
    row=(lid,code,int(st["chat_id"]),0,query.from_user.id,int(st["prize"]),int(st["draw_at"]),int(st.get("min_players",0)),int(st.get("max_players",0)),"active",int(time.time()))
    text=lottery_text(row,None).replace("❌ شما هنوز در این قرعه‌کشی شرکت نکرده‌اید.","🎟️ برای شرکت، دکمه زیر را بزنید.")
    kb=lottery_group_keyboard(lid)

    targets=await lottery_broadcast_targets()
    # همیشه مقصدی که از پنل در آن قرعه‌کشی ساخته شده را هم در اولویت قرار بده.
    if int(st["chat_id"]) not in {x[0] for x in targets}:
        targets.insert(0,(int(st["chat_id"]),"private"))

    sent_count=0
    failed_count=0
    first_sent=None
    for target_id,target_type in targets:
        try:
            sent=await bot.send_message(int(target_id),text,reply_markup=kb)
            await lottery_store_message(lid,int(target_id),sent.message_id)
            if first_sent is None:
                first_sent=(int(target_id),sent.message_id)
            sent_count+=1
        except Exception as e:
            failed_count+=1
            if target_type in ("group","supergroup","channel"):
                with db() as c:
                    c.execute("UPDATE known_chats SET active=0 WHERE chat_id=?",(int(target_id),))
                    c.commit()
            print(f"Lottery broadcast failed for {target_id}: {e}")
        await asyncio.sleep(0.03)

    if first_sent is None:
        with db() as c:
            c.execute("UPDATE lotteries SET status='cancelled' WHERE id=?",(lid,))
            c.commit()
        LOTTERY_PENDING.pop(query.from_user.id,None)
        await query.message.edit_text(f"❌ انتشار قرعه‌کشی انجام نشد.\n\nموفق: 0\nناموفق: {failed_count}")
        await query.answer("❌ انتشار ناموفق بود.",show_alert=True)
        return

    with db() as c:
        c.execute("UPDATE lotteries SET chat_id=?,message_id=? WHERE id=?",(first_sent[0],first_sent[1],lid))
        c.commit()

    LOTTERY_PENDING.pop(query.from_user.id,None)
    await query.message.edit_text(
        f"✅ قرعه‌کشی {code} منتشر شد.\n\n"
        f"📨 ارسال موفق: {sent_count}\n"
        f"❌ ارسال ناموفق: {failed_count}\n"
        f"💰 جایزه: {format_coins(st['prize'])} آریور"
    )
    await query.answer("🎟️ قرعه‌کشی برای همه مقصدهای فعال ارسال شد.")

@dp.callback_query(F.data == "lottery:manage")
async def lottery_manage(query: CallbackQuery):
    if not is_arsin_id(query.from_user.id): await query.answer("❌ فقط آرسین.",show_alert=True); return
    rows=lottery_rows(None,True)
    if not rows:
        await query.message.edit_text("🗂️ مدیریت قرعه‌کشی‌ها\n\nقرعه‌کشی فعالی وجود ندارد.",reply_markup=keyboard([[button("🔙 پنل مدیریت","admin:panel")],[button("❌ بستن منو","menu:close")]])); await query.answer(); return
    kb=[]
    for row in rows:
        lid,code,chat_id,message_id,creator,prize,draw_at,minp,maxp,status,created=row
        count=lottery_participant_count(lid)
        kb.append([button(f"{code} | 💰 {format_coins(prize)} | 👥 {count}",f"lottery:admin:{lid}")])
    kb.append([button("🔙 پنل مدیریت","admin:panel")]); kb.append([button("❌ بستن منو","menu:close")])
    await query.message.edit_text("🗂️ قرعه‌کشی‌های فعال",reply_markup=keyboard(kb)); await query.answer()

@dp.callback_query(F.data.startswith("lottery:admin:"))
async def lottery_admin_view(query: CallbackQuery):
    if not is_arsin_id(query.from_user.id): await query.answer("❌ فقط آرسین.",show_alert=True); return
    try: lid=int(query.data.rsplit(":",1)[1])
    except: await query.answer("❌ نامعتبر.",show_alert=True); return
    with db() as c: row=c.execute("SELECT id,code,chat_id,message_id,creator_id,prize,draw_at,min_players,max_players,status,created_at FROM lotteries WHERE id=?",(lid,)).fetchone()
    if not row or row[9] != "active": await query.answer("❌ قرعه‌کشی فعال نیست.",show_alert=True); return
    count=lottery_participant_count(lid)
    txt=lottery_text(row,None)+f"\n\n👥 تعداد شرکت‌کننده فعلی: {count:,} نفر"
    await query.message.edit_text(txt,reply_markup=keyboard([[button("🚫 لغو قرعه‌کشی",f"lottery:cancel:{lid}")],[button("🔙 قرعه‌کشی‌های فعال","lottery:manage")],[button("❌ بستن منو","menu:close")]])); await query.answer()

@dp.callback_query(F.data.startswith("lottery:cancel:"))
async def lottery_cancel(query: CallbackQuery):
    if not is_arsin_id(query.from_user.id): await query.answer("❌ فقط آرسین.",show_alert=True); return
    try: lid=int(query.data.rsplit(":",1)[1])
    except: await query.answer("❌ نامعتبر.",show_alert=True); return
    with db() as c: row=c.execute("SELECT id,code,chat_id,message_id,creator_id,prize,draw_at,min_players,max_players,status,created_at FROM lotteries WHERE id=?",(lid,)).fetchone()
    if not row or row[9] != "active": await query.answer("❌ این قرعه‌کشی دیگر فعال نیست.",show_alert=True); return
    with db() as c: c.execute("UPDATE lotteries SET status='cancelled' WHERE id=?",(lid,)); c.commit()
    notice=f"🚫 قرعه‌کشی با کد {row[1]} لغو شد.\n\n💰 جایزه: {format_coins(row[5])} آریور\n👥 تعداد شرکت‌کنندگان: {lottery_participant_count(lid):,} نفر"
    try: await bot.send_message(row[2],notice)
    except Exception: pass
    await lottery_manage(query)

async def lottery_draw_once():
    now=int(time.time())
    with db() as c:
        rows=c.execute("SELECT id,code,chat_id,message_id,creator_id,prize,draw_at,min_players,max_players,status,created_at FROM lotteries WHERE status='active' AND draw_at<=? ORDER BY id",(now,)).fetchall()
    for row in rows:
        lid,code,chat_id,message_id,creator,prize,draw_at,minp,maxp,status,created=row
        with db() as c:
            users=[int(x[0]) for x in c.execute("SELECT user_id FROM lottery_players WHERE lottery_id=?",(lid,)).fetchall()]
            current=c.execute("SELECT status FROM lotteries WHERE id=?",(lid,)).fetchone()
            if not current or current[0]!="active": continue
            if len(users)<int(minp):
                c.execute("UPDATE lotteries SET status='completed' WHERE id=?",(lid,)); c.commit()
                try: await bot.send_message(chat_id,f"ℹ️ قرعه‌کشی با کد {code} به پایان رسید، اما حداقل تعداد شرکت‌کننده ({int(minp):,} نفر) تکمیل نشد و قرعه‌کشی بدون برنده پایان یافت.")
                except Exception: pass
                continue
            winner=random.choice(users) if users else None
            c.execute("UPDATE lotteries SET status='completed' WHERE id=?",(lid,)); c.commit()
        if not winner:
            try: await bot.send_message(chat_id,f"ℹ️ قرعه‌کشی با کد {code} به پایان رسید، اما شرکت‌کننده‌ای نداشت.")
            except Exception: pass
            continue
        add_coins(winner,int(prize))
        log_tx(winner,"lottery_prize",int(prize),f"lottery={code}")
        try: await bot.send_message(winner,f"🎉 شما در قرعه‌کشی برنده شدید!\n\n🎟️ کد قرعه‌کشی: {code}\n💰 جایزه برنده‌شده: {format_coins(prize)} آریور\n\nمبلغ جایزه به موجودی شما واریز شد. 🏆")
        except Exception: pass
        with db() as c:
            messages=c.execute(
                "SELECT chat_id,message_id FROM lottery_messages WHERE lottery_id=?",
                (int(lid),)
            ).fetchall()
        if not messages and int(message_id or 0):
            messages=[(chat_id,message_id)]
        for msg_chat_id,msg_message_id in messages:
            try:
                await bot.edit_message_reply_markup(
                    int(msg_chat_id),int(msg_message_id),reply_markup=None
                )
            except Exception:
                pass

async def lottery_live_update_once():
    with db() as c:
        rows=c.execute("SELECT id,status,draw_at FROM lotteries WHERE status='active'").fetchall()
    for lid,status,draw_at in rows:
        if int(draw_at) <= int(time.time()):
            continue
        with db() as c:
            messages=c.execute(
                "SELECT chat_id,message_id FROM lottery_messages WHERE lottery_id=?",
                (int(lid),)
            ).fetchall()
        # سازگاری با قرعه‌کشی‌های قدیمی که قبل از جدول lottery_messages ساخته شده‌اند.
        if not messages:
            with db() as c:
                old=c.execute(
                    "SELECT chat_id,message_id FROM lotteries WHERE id=?",
                    (int(lid),)
                ).fetchone()
            messages=[old] if old and int(old[1] or 0) else []
        for chat_id,message_id in messages:
            try:
                await bot.edit_message_reply_markup(
                    chat_id=int(chat_id),
                    message_id=int(message_id),
                    reply_markup=lottery_group_keyboard(int(lid))
                )
            except Exception:
                pass

async def lottery_live_loop():
    while True:
        try:
            await lottery_live_update_once()
        except Exception as exc:
            print(f"Lottery live update error: {exc}")
        await asyncio.sleep(5)

async def lottery_loop():
    while True:
        try: await lottery_draw_once()
        except Exception as exc: print(f"Lottery loop error: {exc}")
        await asyncio.sleep(5)

@dp.callback_query(F.data == "admin:panel")
async def admin_panel_callback(query: CallbackQuery):
    if not is_admin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True); return
    await query.message.edit_text(admin_panel_text(), reply_markup=admin_panel_keyboard(query.from_user.id))
    await query.answer()


@dp.callback_query(F.data == "admin:started_users")
async def admin_started_users(query: CallbackQuery):
    if not is_arsin_id(query.from_user.id):
        await query.answer("❌ فقط آرسین.",show_alert=True); return
    with db() as c:
        count=int(c.execute("SELECT COUNT(*) FROM users WHERE started=1").fetchone()[0])
    await query.message.edit_text(f"👥 کاربران استارت‌کرده ربات\n\n📊 تعداد: {count:,} نفر",reply_markup=keyboard([[button("🔙 پنل مدیریت","admin:panel")],[button("❌ بستن پنل","menu:close")]]))
    await query.answer()


@dp.callback_query(F.data == "admin:help")
async def admin_help(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "help"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    await query.message.edit_text(admin_help_text(), reply_markup=keyboard([[button("🔙 پنل مدیریت","admin:panel")],[button("❌ بستن پنل","menu:close")]]))
    await query.answer()


@dp.callback_query(F.data == "admin:prices")
async def admin_prices(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "prices"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    await query.message.edit_text("🏷️ مدیریت قیمت‌ها\n\nیک بخش را انتخاب کن:", reply_markup=admin_prices_keyboard())
    await query.answer()


@dp.callback_query(F.data.startswith("admin:prices:cat:"))
async def admin_prices_category(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "prices"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    category=query.data.rsplit(":",1)[1]
    if category not in PRICE_CATEGORIES:
        await query.answer("❌ دسته نامعتبر.", show_alert=True); return
    title,_=PRICE_CATEGORIES[category]
    await query.message.edit_text(f"{title}\n\nروی هر مورد بزن تا قیمتش را تغییر بدهی:", reply_markup=admin_price_category_keyboard(category))
    await query.answer()


@dp.callback_query(F.data.startswith("admin:price:"))
async def admin_price_edit(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "prices"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    parts=query.data.split(":")
    try:
        category=parts[2]; idx=int(parts[3])
        item=PRICE_CATEGORIES[category][1][idx]
    except Exception:
        await query.answer("❌ قیمت نامعتبر.", show_alert=True); return
    key=price_key_admin(category,item); current=get_price(key,price_default(category,item))
    pending_admin[query.from_user.id]=( "set_price", category, idx )
    await query.message.answer(f"🏷️ {item}\n\n💎 قیمت فعلی: {format_coins(current)} آریور\n✏️ قیمت جدید را فقط به صورت عدد مثبت یا صفر ارسال کن:")
    await query.answer()


@dp.callback_query(F.data == "admin:removebalance")
async def admin_removebalance(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "removebalance"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    pending_admin[query.from_user.id]="remove_user"
    await query.message.answer("➖ کسر موجودی\n\nآیدی عددی یا @username کاربر را ارسال کن؛ یا یک پیام از خودِ کاربر را همینجا فوروارد کن:")
    await query.answer()


@dp.callback_query(F.data == "admin:addadmin")
async def admin_addadmin(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین اصلی می‌تواند مدیر جدید اضافه کند.", show_alert=True); return
    pending_admin[query.from_user.id] = "add_admin_user"
    await query.message.answer("👑 روی پیام کاربر موردنظر ریپلای کن و همان پیام را ارسال کن، یا یک پیام فورواردشده از خود کاربر بفرست.")
    await query.answer()


@dp.callback_query(F.data == "admin:admins")
async def admin_admins(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین اصلی.", show_alert=True); return
    rows=admin_rows()
    text="👑 لیست ادمین‌های ربات\n\n" + ("\n".join(f"• {('@'+u) if u else (n or str(uid))} — {uid}" for uid,u,n,_ in rows) if rows else "هیچ ادمین دیگری ثبت نشده است.")
    await query.message.edit_text(text, reply_markup=admin_list_keyboard())
    await query.answer()


@dp.callback_query(F.data.startswith("admin:admin:"))
async def admin_admin_detail(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین اصلی.", show_alert=True); return
    try: uid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ مدیر نامعتبر.",show_alert=True); return
    if is_arsin_id(uid):
        await query.answer("آرسین مدیر اصلی است و حذف نمی‌شود.",show_alert=True); return
    with db() as c:
        row=c.execute("SELECT username,full_name FROM admin_users WHERE user_id=?",(uid,)).fetchone()
    if not row:
        await query.answer("❌ این مدیر دیگر وجود ندارد.",show_alert=True); return
    username,full_name=row
    label=f"@{username}" if username else (full_name or str(uid))
    await query.message.edit_text(f"👑 مدیر: {label}\n🆔 {uid}\n\n{admin_permission_text(uid)}", reply_markup=keyboard([
        [button("🔐 تنظیم دسترسی‌ها",f"admin:perms:{uid}")],
        [button("❌ حذف شوشول",f"admin:removeadmin:{uid}")],
        [button("🔙 لیست ادمین‌ها","admin:admins")],
        [button("❌ بستن پنل","menu:close")],
    ]))
    await query.answer()


@dp.callback_query(F.data.startswith("admin:perms:"))
async def admin_permissions(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین اصلی.", show_alert=True); return
    try: uid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ مدیر نامعتبر.",show_alert=True); return
    if not is_admin_user_id(uid) or is_arsin_id(uid):
        await query.answer("❌ این کاربر مدیر قابل تنظیم نیست.",show_alert=True); return
    await query.message.edit_text(f"🔐 تنظیم دسترسی مدیر\n\n{admin_permission_text(uid)}",reply_markup=admin_permission_keyboard(uid))
    await query.answer()


@dp.callback_query(F.data.startswith("adminperm:"))
async def admin_permission_toggle(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین اصلی.", show_alert=True); return
    try:
        _,uid_s,section,enabled_s=query.data.split(":",3)
        uid=int(uid_s); enabled=int(enabled_s)
    except Exception:
        await query.answer("❌ دسترسی نامعتبر.",show_alert=True); return
    if section not in ADMIN_SECTIONS or not is_admin_user_id(uid) or is_arsin_id(uid):
        await query.answer("❌ مورد نامعتبر.",show_alert=True); return
    set_admin_permission(uid,section,enabled)
    await query.message.edit_text(f"🔐 تنظیم دسترسی مدیر\n\n{admin_permission_text(uid)}",reply_markup=admin_permission_keyboard(uid))
    await query.answer("✅ تغییر کرد")


@dp.callback_query(F.data.startswith("admin:removeadmin:"))
async def admin_removeadmin(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین اصلی.", show_alert=True); return
    try: uid=int(query.data.rsplit(":",1)[1])
    except Exception:
        await query.answer("❌ مدیر نامعتبر.",show_alert=True); return
    if is_arsin_id(uid):
        await query.answer("آرسین اصلی حذف نمی‌شود.",show_alert=True); return
    if not remove_admin_user(uid):
        await query.answer("❌ این کاربر مدیر نیست.",show_alert=True); return
    try: await bot.send_message(uid,"❌ دسترسی مدیریت شما توسط آرسین حذف شد.")
    except Exception: pass
    await query.message.edit_text("✅ این شوشول از مدیریت ربات حذف شد.",reply_markup=admin_list_keyboard())
    await query.answer("حذف شد")


@dp.callback_query(F.data == "admin:banned")
async def admin_banned(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "banned"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    rows=banned_rows()
    if not rows:
        await query.message.edit_text("🚫 هیچ کاربری بن نشده است.",reply_markup=admin_banned_keyboard())
    else:
        text="🚫 کاربران بن‌شده\n\n"+"\n".join(f"• {uid} — @{username}" if username else f"• {uid} — {full_name or 'بدون نام'}" for uid,username,full_name,w,b,t in rows)
        await query.message.edit_text(text,reply_markup=admin_banned_keyboard())
    await query.answer()


@dp.callback_query(F.data.startswith("admin:unban:"))
async def admin_unban_callback(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "banned"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    try: uid=int(query.data.rsplit(":",1)[1])
    except Exception: await query.answer("❌ کاربر نامعتبر.",show_alert=True); return
    ok,total=unban_user(uid)
    if not ok:
        await query.answer("❌ این کاربر بن نیست.",show_alert=True); return
    try: await bot.send_message(uid,f"✅ شوشول شما توسط مدیر ربات برگردانده شد.\n💎 کل موجودی قبلی شما: {format_coins(total)} آریور\n🤖 ربات دوباره برای شما فعال است.")
    except Exception: pass
    await query.message.edit_text(f"✅ کاربر {uid} از بن خارج شد.\n💎 کل موجودی برگشت داده شد: {format_coins(total)} آریور",reply_markup=admin_banned_keyboard())
    await query.answer("✅ برگردانده شد")


async def send_announcement(text, url=None, button_name=None, sender_id=0, duration_minutes=0):
    await bot.send_message(sender_id, "📢 اطلاعیه در حال ارسال است...")
    sent_count=0; failed_count=0
    targets=[]
    with db() as c:
        targets.extend((int(r[0]),"private") for r in c.execute("SELECT id FROM users WHERE started=1 AND NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=users.id)").fetchall())
        targets.extend((int(r[0]),r[1]) for r in c.execute("SELECT chat_id,chat_type FROM known_chats WHERE active=1").fetchall())
    markup=None
    if url and button_name:
        markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=button_name, url=url)]])
    seen=set()
    delete_at=int(time.time()) + max(0,int(duration_minutes))*60 if int(duration_minutes)>0 else 0
    for chat_id,chat_type in targets:
        if chat_id in seen: continue
        seen.add(chat_id)
        try:
            send_kwargs={"reply_markup":markup} if markup else {}
            if "<code>" in str(text): send_kwargs["parse_mode"]="HTML"
            sent=await bot.send_message(chat_id,text,**send_kwargs)
            sent_count+=1
            if delete_at:
                with db() as c:
                    c.execute("INSERT INTO scheduled_announcements(chat_id,message_id,delete_at) VALUES(?,?,?)",(chat_id,int(sent.message_id),delete_at)); c.commit()
        except Exception:
            failed_count+=1
            if chat_type in ("group","supergroup","channel"):
                with db() as c: c.execute("UPDATE known_chats SET active=0 WHERE chat_id=?",(chat_id,)); c.commit()
        await asyncio.sleep(0.03)
    mode_txt=f"\n⏱️ زمان حذف: {int(duration_minutes)} دقیقه" if int(duration_minutes)>0 else "\n♾️ زمان حذف: نامحدود"
    await bot.send_message(sender_id, f"✅ اطلاعیه ارسال شد.\n📨 موفق: {sent_count}\n❌ ناموفق: {failed_count}{mode_txt}")


async def scheduled_announcement_delete_loop():
    while True:
        try:
            now=int(time.time())
            with db() as c:
                rows=c.execute("SELECT id,chat_id,message_id FROM scheduled_announcements WHERE delete_at<=? ORDER BY id LIMIT 200",(now,)).fetchall()
            for row_id,chat_id,message_id in rows:
                try:
                    await bot.delete_message(int(chat_id),int(message_id))
                except Exception:
                    pass
                with db() as c:
                    c.execute("DELETE FROM scheduled_announcements WHERE id=?",(int(row_id),)); c.commit()
                await asyncio.sleep(0.03)
        except Exception as exc:
            print(f"Scheduled announcement delete error: {exc}")
        await asyncio.sleep(5)


@dp.callback_query(F.data.startswith("announce_time:"))
async def announcement_time_choice(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "announce"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    pending=pending_admin.get(query.from_user.id)
    if not (isinstance(pending,tuple) and pending[0]=="announcement_time_choice"):
        await query.answer("⏳ این مرحله منقضی شده است.",show_alert=True); return
    choice=query.data.split(":",1)[1]
    announcement_text=pending[1]
    if choice=="unlimited":
        pending_admin[query.from_user.id]=( "announcement_link_choice", announcement_text, 0 )
        await query.message.answer("📢 زمان اطلاعیه: نامحدود.\n\nحالا مشخص کن لینک شیشه‌ای داشته باشد یا نه:", reply_markup=keyboard([[button("🔗 با لینک شیشه‌ای", "announce_link:yes")],[button("➡️ بدون لینک شیشه‌ای", "announce_link:no")],[button("❌ بستن پنل", "menu:close")]]))
        await query.answer(); return
    if choice=="limited":
        pending_admin[query.from_user.id]=( "announcement_time_minutes", announcement_text )
        await query.message.answer("⏱️ مدت نمایش اطلاعیه را به دقیقه وارد کن.\nمثلاً: 30")
        await query.answer(); return
    await query.answer("❌ انتخاب نامعتبر.",show_alert=True)


@dp.callback_query(F.data.startswith("announce_link:"))
async def announcement_link_choice(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "announce"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    pending=pending_admin.get(query.from_user.id)
    if not (isinstance(pending,tuple) and pending[0]=="announcement_link_choice"):
        await query.answer("⏳ این مرحله منقضی شده است.",show_alert=True); return
    choice=query.data.split(":",1)[1]
    announcement_text=pending[1]
    duration_minutes=int(pending[2])
    if choice=="yes":
        pending_admin[query.from_user.id]=( "announcement_link_url", announcement_text, duration_minutes )
        await query.message.answer("🔗 لینک را بفرست:")
        await query.answer(); return
    if choice=="no":
        pending_admin.pop(query.from_user.id,None)
        await send_announcement(announcement_text, sender_id=query.from_user.id, duration_minutes=duration_minutes)
        await query.answer(); return
    await query.answer("❌ انتخاب نامعتبر.",show_alert=True)


@dp.callback_query(F.data == "admin:announce")
async def admin_announce(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "announce"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    pending_admin[query.from_user.id]="announcement"
    await query.message.answer("📢 متن اطلاعیه را ارسال کن.\n\nاین متن برای کاربران استارت‌کرده و گروه/کانال‌های شناخته‌شده ربات ارسال می‌شود.")
    await query.answer()


@dp.callback_query(F.data == "admin:addcoins")
async def admin_addcoins(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "addcoins"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    pending_admin[query.from_user.id] = "add_amount"
    await query.message.answer("تعداد آریور را ارسال کنید")
    await query.answer()


@dp.callback_query(F.data == "admin:gift")
async def admin_gift(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "gift"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    pending_admin[query.from_user.id] = "gift_amount"
    await query.message.answer("🎁 تعداد آریور کد هدیه را ارسال کن:")
    await query.answer()


def gift_keyboard():
    rows = []
    for code, amount, mode, max_uses, used_count in active_gifts():
        kind = "👤 تک‌کاربره" if mode == "single" else "👥 چندکاربره"
        cap = "∞" if int(max_uses or 0) <= 0 else format_coins(max_uses)
        rows.append([button(f"{code} — {format_coins(amount)} 💎 — {kind} — استفاده: {used_count}/{cap}", f"gift:expire:{code}")])
    return keyboard(rows) if rows else keyboard([[button("کد فعالی وجود ندارد", "gift:none")]])


@dp.callback_query(F.data.startswith("giftannounce:"))
async def gift_announce(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"gift"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    p=pending_admin.get(query.from_user.id)
    if not (isinstance(p,tuple) and p[0]=="gift_announce"): await query.answer("⏳ این مرحله منقضی شده است.",show_alert=True); return
    choice=query.data.split(":",1)[1]; pending_admin.pop(query.from_user.id,None)
    if choice=="yes":
        code,amount,mode=p[1],p[2],p[3]
        safe_code=html.escape(str(code))
        text=f"🎁 کد هدیه جدید آریو\n\n<code>کد هدیه {safe_code}</code>\n\n💎 مبلغ: {format_coins(amount)} آریور\n🎯 نوع: {mode}\n\n📌 برای استفاده، کد را کپی و در ربات ارسال کنید."
        await send_announcement(text,sender_id=query.from_user.id)
    else: await query.message.answer("👌 اطلاعیه پخش نشد؛ کد هدیه فقط ثبت شد.")
    await query.answer("✅ انجام شد")

@dp.callback_query(F.data.startswith("giftmode:"))
async def admin_gift_mode(query: CallbackQuery):
    if not is_admin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True); return
    mode = query.data.split(":", 1)[1]
    pending = pending_admin.get(query.from_user.id)
    if not (isinstance(pending, tuple) and pending[0] == "gift_mode"):
        await query.answer("⏳ این درخواست منقضی شده است.", show_alert=True); return
    if mode not in ("single", "multi"):
        await query.answer("❌ نوع کد نامعتبر است.", show_alert=True); return
    amount = pending[1]
    if mode == "single":
        pending_admin[query.from_user.id] = ("gift_code", amount, mode, 1)
        await query.message.answer("✅ نوع کد: تک‌کاربره 👤\n🔑 حالا کد هدیه را وارد کن:")
    else:
        pending_admin[query.from_user.id] = ("gift_limit", amount)
        await query.message.answer("👥 این کد برای چند کاربر قابل استفاده باشد؟\n🔢 فقط یک عدد مثبت بفرست؛ مثلاً 20")
    await query.answer()


@dp.callback_query(F.data == "admin:gifts")
async def admin_gifts(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "gifts"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    gifts = active_gifts()
    if not gifts:
        await query.message.answer("کد هدیه فعالی وجود ندارد.")
    else:
        await query.message.answer("کدهای هدیه فعال؛ برای منقضی کردن روی کد بزن:", reply_markup=gift_keyboard())
    await query.answer()


@dp.callback_query(F.data.startswith("gift:expire:"))
async def admin_expire_gift(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id, "gifts"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.", show_alert=True); return
    code = query.data.split(":", 2)[2].strip()
    changed = expire_gift(code)
    if not changed:
        await query.answer("⚠️ این کد دیگر فعال نیست.", show_alert=True)
        return
    await query.message.edit_text("✅ کد هدیه منقضی شد.\n\nکدهای فعال باقی‌مانده:", reply_markup=gift_keyboard())
    await query.answer("✅ حذف شد")


@dp.callback_query(F.data == "gift:none")
async def gift_none(query: CallbackQuery):
    await query.answer("کدی وجود ندارد.")


@dp.callback_query(F.data == "admin:autoreply")
async def admin_autoreply(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"autoreply"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    text="💬 پاسخ‌های خودکار فعلی\n\n"+(("\n".join(f"🔹 {r[1]} → {r[2][:100]}" for r in get_auto_replies())) or "هنوز موردی ثبت نشده است.")
    await query.message.edit_text(text,reply_markup=auto_reply_panel_keyboard()); await query.answer()

@dp.callback_query(F.data == "autoreply:add")
async def autoreply_add(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"autoreply"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    pending_admin[query.from_user.id]="autoreply_keyword"; await query.message.answer("💬 کلمه یا عبارت موردنظر را بفرست:"); await query.answer()

@dp.callback_query(F.data.startswith("autoreply:del:"))
async def autoreply_del(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"autoreply"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    try: rid=int(query.data.rsplit(":",1)[1])
    except Exception: await query.answer("❌ مورد نامعتبر.",show_alert=True); return
    delete_auto_reply(rid); await query.message.edit_text("💬 پاسخ‌های خودکار فعلی\n\n"+(("\n".join(f"🔹 {r[1]} → {r[2][:100]}" for r in get_auto_replies())) or "هنوز موردی ثبت نشده است."),reply_markup=auto_reply_panel_keyboard()); await query.answer("✅ حذف شد")

@dp.callback_query(F.data == "admin:welcome")
async def admin_welcome(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"welcome"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    await query.message.edit_text(welcome_preview_text(),reply_markup=welcome_panel_keyboard()); await query.answer()

@dp.callback_query(F.data == "welcome:text")
async def welcome_text_edit(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"welcome"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    pending_admin[query.from_user.id]="welcome_text"; await query.message.answer("👋 متن جدید ولکام بات را بفرست:"); await query.answer()

@dp.callback_query(F.data == "welcome:addbtn")
async def welcome_addbtn(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"welcome"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    pending_admin[query.from_user.id]="welcome_btn_text"; await query.message.answer("🔗 متن روی لینک شیشه‌ای را بفرست:"); await query.answer()

@dp.callback_query(F.data.startswith("welcome:delbtn:"))
async def welcome_delbtn(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"welcome"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    try: idx=int(query.data.rsplit(":",1)[1])
    except Exception: await query.answer("❌ لینک نامعتبر.",show_alert=True); return
    items=welcome_buttons()
    if 0<=idx<len(items): items.pop(idx); save_welcome_buttons(items)
    await query.message.edit_text(welcome_preview_text(),reply_markup=welcome_panel_keyboard()); await query.answer("✅ حذف شد")

@dp.callback_query(F.data == "admin:moderation")
async def admin_moderation(query: CallbackQuery):
    if not is_admin_user(query.from_user) or not admin_has_permission(query.from_user.id,"moderation"):
        await query.answer("❌ دسترسی این بخش برای شما فعال نیست.",show_alert=True); return
    await query.message.edit_text("🛡️ دستورات اخراج\n\n• صیک + ریپلای: اخراج از همین گروه\n• صیک پلاس + ریپلای: اخراج از همه گروه‌های شناخته‌شده\n\nربات باید دسترسی اخراج اعضا داشته باشد.",reply_markup=keyboard([[button("🔙 پنل مدیریت","admin:panel")]])); await query.answer()

# ================================================================
# ARSIN LINK SETUP
# ================================================================
@dp.callback_query(F.data.startswith("link:"))
async def callback_link(query: CallbackQuery):
    if not is_admin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True)
        return

    slot = query.data.split(":", 1)[1]
    if slot == "add":
        slot = str(next_link_slot())
        action_text = f"🔗 لینک جدید شماره {slot}"
    else:
        action_text = f"🔗 لینک {slot}"
    pending_link[query.from_user.id] = (slot, "url")
    await query.answer()
    await bot.send_message(
        query.from_user.id,
        f"{action_text} را ارسال کن.\n\nمثال: https://t.me/channel یا https://t.me/+InviteLink\n\nبعد از آن اطلاعات لازم را خودکار بررسی می‌کنم. 🤖",
    )


# ================================================================
# SHOSHUL BARI — RISK / TOOLS / DEFENSE
# ================================================================
def shoshol_tool_bonus(uid):
    bonus=0
    owned=[]
    for item, (_cost, pct, _desc) in SHOSHUL_TOOLS.items():
        if inventory_qty(uid,item)>0:
            bonus += pct
            owned.append((item,pct))
    return min(30, bonus), owned

def shoshol_defense_reduction(uid):
    reduction=0
    owned=[]
    for item, (_cost, pct, _desc) in SHOSHUL_DEFENSES.items():
        if inventory_qty(uid,item)>0:
            reduction += pct
            owned.append((item,pct))
    return min(25, reduction), owned

def shoshol_chance(thief_id, target_id):
    tool_bonus, tools = shoshol_tool_bonus(thief_id)
    defense_reduction, defenses = shoshol_defense_reduction(target_id)
    guardian_reduction = 10 if shoshol_guardian_level(target_id) else 0
    total_reduction = defense_reduction + guardian_reduction
    chance=max(0, min(80, 50 + tool_bonus - total_reduction))
    return chance, tool_bonus, total_reduction, tools, defenses

def shoshol_max_amount(target_id):
    # فقط کیف پول عادی هدف قابل دزدی است؛ بانک هرگز درگیر نمی‌شود.
    return get_balance(target_id)//30

def hack_last_used(uid):
    with db() as c:
        row=c.execute("SELECT last_used FROM hack_cooldowns WHERE user_id=?", (uid,)).fetchone()
    return int(row[0] or 0) if row else 0


def set_hack_used(uid, ts=None):
    if ts is None:
        ts=int(time.time())
    with db() as c:
        c.execute("INSERT INTO hack_cooldowns(user_id,last_used) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET last_used=excluded.last_used", (uid,int(ts)))
        c.commit()


async def handle_bank_hack(message):
    if message.chat.type not in ("group","supergroup"):
        await message.reply("❌ هک فقط داخل گروه انجام می‌شود. 👥")
        return True
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("❌ برای هک باید روی پیام کاربر موردنظر ریپلای کنی و بنویسی «هک». ↩️")
        return True
    attacker=message.from_user.id
    target=message.reply_to_message.from_user
    if target.id==attacker:
        await message.reply("❌ نمی‌تونی بانک خودت رو هک کنی! 😄")
        return True
    if is_arsin_target(target):
        await message.reply("👑 آرسین از تمام عملیات هدف‌گیری مصون است؛ هک روی آرسین امکان‌پذیر نیست. 🛡️")
        return True
    lvl=hack_level(attacker)
    if lvl<=0:
        await message.reply("❌ برای هک کردن باید اول آیتم «💻 هکر» را از فروشگاه سیاه بخری. 🕶️")
        return True
    last_used=hack_last_used(attacker)
    remaining=HACK_COOLDOWN-int(time.time()-last_used)
    if remaining>0:
        mins,secs=divmod(remaining,60)
        await message.reply(f"⏳ هک هنوز آماده نیست! 💻\n🕐 {mins} دقیقه و {secs} ثانیه مونده.\n🔐 هر 7 دقیقه یک بار می‌تونی هک انجام بدی.")
        return True
    set_hack_used(attacker)
    release_due_bank_hacks(attacker)
    release_due_bank_hacks(target.id)
    target_bank=bank_balance(target.id)
    if target_bank<=0:
        await message.reply(f"❌ موجودی قابل هک در بانک {display_name_by_id(target.id)} صفر است. 🏦")
        return True
    chance,raw_chance,reduction=hack_success_chance(attacker,target.id)
    success=random.random() < chance/100.0
    catch=random.random() < HACK_CATCH_CHANCE/100.0
    target_label=display_name_by_id(target.id)
    attacker_label=display_name_by_id(attacker)
    stolen=0
    if success:
        min_take=max(0,target_bank//10)
        max_take=max(min_take,target_bank*3//10)
        stolen=random.randint(min_take,max_take) if max_take>0 else 0
        if stolen>0:
            with db() as c:
                c.execute("UPDATE bank SET balance=balance-? WHERE user_id=?",(stolen,target.id)); c.commit()
            add_coins(attacker,stolen)
            log_tx(target.id,"hack_bank_loss",-stolen,f"by={attacker}")
            log_tx(attacker,"hack_bank_profit",stolen,f"from={target.id}")
    blocked=0
    if catch:
        attacker_bank=bank_balance(attacker)
        blocked=attacker_bank//2
        if blocked>0:
            unlock=int(time.time())+86400
            with db() as c:
                c.execute("INSERT INTO bank_hack_blocks(user_id,amount,unlock_at,created_at) VALUES(?,?,?,?)",(attacker,blocked,unlock,int(time.time()))); c.commit()
            log_tx(attacker,"hack_caught_block",0,f"blocked={blocked};unlock={unlock}")
    lines=["💻 نتیجه عملیات هک 🕶️","",f"👤 هکر: {attacker_label}",f"🎯 هدف: {target_label}",f"📊 سطح هکر: {lvl}/{HACKER_MAX_LEVEL}",f"🎯 شانس هک: {chance}% (پایه {raw_chance}% | ضد هک هدف: -{reduction}%)"]
    if success:
        lines += ["","✅ هک موفق شد!",f"💰 مبلغ سرقت‌شده از بانک: {format_coins(stolen)} آریور"]
    else:
        lines += ["","❌ هک ناموفق بود؛ چیزی از بانک هدف برداشته نشد."]
    if catch:
        penalty=blocked//10
        return_amount=max(0,blocked-penalty)
        lines += ["","🚨 اما عملیات لو رفت!",f"🔒 نصف بانک فعلی شما یعنی {format_coins(blocked)} آریور به مدت ۲۴ ساعت بلوکه شد.",f"📅 پس از ۲۴ ساعت {format_coins(return_amount)} آریور برمی‌گردد و {format_coins(penalty)} آریور جریمه می‌شود."]
    else:
        lines += ["","🕵️ این بار شناسایی نشدی و بانک شما بلوکه نشد."]
    await message.reply("\n".join(lines))
    return True

def shoshol_last_used(uid):
    with db() as c:
        row = c.execute("SELECT last_used FROM shoshol_cooldowns WHERE user_id=?", (uid,)).fetchone()
    return int(row[0] or 0) if row else 0

def set_shoshol_used(uid, ts=None):
    if ts is None:
        ts = int(time.time())
    with db() as c:
        c.execute(
            "INSERT INTO shoshol_cooldowns(user_id,last_used) VALUES(?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET last_used=excluded.last_used",
            (uid, int(ts)),
        )
        c.commit()

async def handle_shoshol_bari(message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("❌ شوشول بری فقط داخل گروه انجام می‌شود. 👥")
        return True
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("❌ برای شوشول بری باید روی پیام کاربر موردنظر ریپلای کنی. ↩️")
        return True
    thief=message.from_user.id
    target=message.reply_to_message.from_user
    if target.id==thief:
        await message.reply("❌ نمی‌تونی شوشول خودت رو ببری! 😂")
        return True
    if is_arsin_target(target):
        await message.reply("👑 آرسین از شوشول بری و تمام عملیات هدف‌گیری مصون است. 🛡️")
        return True
    target_balance=get_balance(target.id)
    if target_balance < 500:
        await message.reply(f"❌ موجودی کیف پول این کاربر حداقل باید 500 آریور باشد.\n💰 موجودی قابل هدف: {format_coins(target_balance)} آریور\n🏦 موجودی بانک در شوشول بری حساب نمی‌شود.")
        return True

    last_used = shoshol_last_used(thief)
    remaining = SHOSHOL_COOLDOWN - int(time.time() - last_used)
    if remaining > 0:
        mins, secs = divmod(remaining, 60)
        await message.reply(f"⏳ شوشول بری هنوز آماده نیست! 😈\n🕐 {mins} دقیقه و {secs} ثانیه مونده.\n✂️ هر 7 دقیقه یک بار می‌تونی شوشول بری انجام بدی.")
        return True

    # Cooldown starts when the actual operation is accepted, just like Ario.
    set_shoshol_used(thief)

    chance, tool_bonus, defense_reduction, tools, defenses = shoshol_chance(thief,target.id)
    max_amount=target_balance//30
    amount=random.randint(0,max_amount)
    success=random.random() < chance/100.0
    thief_label=display_name_by_id(thief)
    target_label=display_name_by_id(target.id)

    if success:
        if amount>0:
            add_coins(target.id,-amount)
            add_coins(thief,amount)
            log_tx(target.id,"shoshol_bari_loss",-amount,f"by={thief}")
            log_tx(thief,"shoshol_bari_profit",amount,f"from={target.id}")
        tool_text=f"+{tool_bonus}% از ابزارها" if tool_bonus else "بدون ابزار اضافی"
        defense_text=f"-{defense_reduction}% از ضدشوشول‌ها" if defense_reduction else "بدون دفاع ضدشوشول"
        await message.reply(
            f"🕶️✂️ شوشول بری با موفقیت انجام شد! 😈\n\n"
            f"👤 هدف: {target_label}\n"
            f"🎯 شانس نهایی موفقیت: {chance}%\n"
            f"🧰 {tool_text} | 🛡️ {defense_text}\n\n"
            f"💎 سود شما: {format_coins(amount)} آریور\n"
            f"💰 موجودی کیف پول شما: {format_coins(get_balance(thief))} آریور\n"
            f"🏦 بانک شما: {format_coins(bank_balance(thief))} آریور")
    else:
        penalty=amount
        current=get_balance(thief)
        actual_penalty=min(current, penalty)
        if actual_penalty>0:
            add_coins(thief,-actual_penalty)
            log_tx(thief,"shoshol_bari_penalty",-actual_penalty,f"target={target.id};requested={penalty}")
        tool_text=f"+{tool_bonus}% از ابزارها" if tool_bonus else "بدون ابزار اضافی"
        defense_text=f"-{defense_reduction}% از ضدشوشول‌ها" if defense_reduction else "بدون دفاع ضدشوشول"
        await message.reply(
            f"🚨 شوشول بری لو رفت! 😵‍💫\n\n"
            f"👤 هدف: {target_label}\n"
            f"🎯 شانس موفقیت شما: {chance}%\n"
            f"🧰 {tool_text} | 🛡️ {defense_text}\n\n"
            f"💸 جریمه شما: {format_coins(actual_penalty)} آریور\n"
            f"💰 موجودی کیف پول شما: {format_coins(get_balance(thief))} آریور\n"
            f"🏦 بانک شما: {format_coins(bank_balance(thief))} آریور")
    return True

# ================================================================
# COMBAT / BLACK SHOP
# ================================================================
# ================================================================
# TURN-BASED COMBAT DUEL
# ================================================================
def duel_get(bid):
    cached=combat_states.get(bid)
    if cached is not None: return dict(cached)
    with db() as c:
        r=c.execute("SELECT battle_id,turn_user,hp_a,hp_b,defending_user,special_a,special_b,turn_no,updated_at,COALESCE(potion_state,'') FROM combat_duels WHERE battle_id=?",(bid,)).fetchone()
    if not r: return None
    state={"battle_id":r[0],"turn_user":r[1],"hp_a":r[2],"hp_b":r[3],"defending_user":r[4],"special_a":r[5],"special_b":r[6],"turn_no":r[7],"updated_at":r[8],"potion_effects":{},"defense_potion":{}}
    try:
        ps=json.loads(r[9]) if r[9] else {}
        state["potion_effects"]=ps.get("potion_effects",{})
        state["defense_potion"]=ps.get("defense_potion",{})
    except Exception:
        pass
    combat_states[bid]=state
    return dict(state)

def duel_init(bid):
    b=combat_get(bid)
    if not b: return None
    now=int(time.time())
    state={"battle_id":bid,"turn_user":b["creator_id"],"hp_a":100,"hp_b":100,"defending_user":0,"special_a":0,"special_b":0,"turn_no":1,"updated_at":now,"potion_effects":{},"defense_potion":{}}
    with db() as c:
        c.execute("INSERT OR REPLACE INTO combat_duels(battle_id,turn_user,hp_a,hp_b,defending_user,special_a,special_b,turn_no,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                  (bid,state["turn_user"],100,100,0,0,0,1,now)); c.commit()
    combat_states[bid]=state
    refresh_combat_timeout(bid)
    return dict(state)

def duel_text(bid,last_action=""):
    b=combat_get(bid); d=duel_get(bid)
    if not b or not d: return "🥊 مبارزه پیدا نشد."
    cp=b.get("creator_power") or combat_attack_power(b["creator_id"])
    op=b.get("opponent_power") or combat_attack_power(b["opponent_id"])
    da,ia=combat_defense_percent(b["creator_id"]); dbp,ib=combat_defense_percent(b["opponent_id"])
    lines=[
        "🥊 مبارزه نوبتی — فقط حمله و دفاع","",
        f"👤 {mention_by_id(b['creator_id'])}: ❤️ {d['hp_a']}/100 | ⚔️ قدرت سلاح {cp}",
        f"👤 {mention_by_id(b['opponent_id'])}: ❤️ {d['hp_b']}/100 | ⚔️ قدرت سلاح {op}",
        "",
        f"🛡️ دفاع {mention_by_id(b['creator_id'])}: {da}%" + (f" ({ia})" if ia else ""),
        f"🛡️ دفاع {mention_by_id(b['opponent_id'])}: {dbp}%" + (f" ({ib})" if ib else ""),
        "",
        f"🔢 حرکت {d['turn_no']}",
        f"🎯 نوبت: {mention_by_id(d['turn_user'])}",
    ]
    if last_action: lines += ["",last_action]
    return "\n".join(lines)

def duel_keyboard(bid):
    return keyboard([[button("⚔️ حمله",f"combat:action:{bid}:attack"),button("🛡️ دفاع",f"combat:action:{bid}:defend")],[button("🧪 معجون‌ها",f"combat:potions:{bid}")]])

def duel_action(bid,uid,action):
    if action not in ("attack","defend"): return None,"invalid_action"
    b=combat_get(bid); d=combat_states.get(bid) or duel_get(bid)
    if not b or b["status"]!="active" or not d: return None,"closed"
    if uid not in (b["creator_id"],b["opponent_id"]): return d,"player"
    if uid!=d["turn_user"]: return d,"turn"
    defender=b["opponent_id"] if uid==b["creator_id"] else b["creator_id"]
    damage=0; blocked=0; defense_pct=0; counter=0; dodged=False; critical=False
    if action=="defend":
        defense_pct,_=combat_defense_percent(uid)
        d["defending_user"]=uid
        d["turn_user"]=defender; d["turn_no"]+=1; d["updated_at"]=int(time.time())
    else:
        # Read and consume attacker's one-use effects.
        atk_effects=_effect_list(d,uid)
        rage=_take_effect(d,uid,"rage")
        accuracy=_take_effect(d,uid,"accuracy")
        crit_potion=_take_effect(d,uid,"critical")
        heal=_take_effect(d,uid,"heal")
        focus=_take_effect(d,uid,"focus")
        # A "freeze_target" stored on the attacker means the defender's next attack is weakened.
        # It is converted to a defender debuff when the potion was activated.
        freeze_marker=_take_effect(d,uid,"freeze_target")
        if freeze_marker:
            _effect_list(d,defender).append("freeze")
        damage=combat_attack_damage(uid)
        if rage: damage=int(round(damage*1.30))
        if focus: damage+=5
        if crit_potion and random.random()<0.25:
            damage*=2; critical=True

        # Defender-side temporary effects.
        dodge_potion=False
        defense_potions=d.setdefault("defense_potion",{})
        defender_potion=defense_potions.pop(str(defender),None)
        if defender_potion:
            ditem=defender_potion.get("item","")
            if ditem=="🧴 معجون جاخالی":
                dodge_potion=True
            elif ditem in COMBAT_DEFENSE_POTIONS:
                defense_pct=COMBAT_DEFENSE_POTIONS[ditem][1]

        if _take_effect(d,defender,"dodge"):
            dodge_potion=True
        dodge_chance=20 if dodge_potion else 0
        if accuracy:
            dodge_chance=max(0,dodge_chance-15)
        if dodge_chance and random.random()<dodge_chance/100.0:
            dodged=True
        if not dodged:
            # Normal defend action.
            if d.get("defending_user")==defender:
                if not defense_pct:
                    defense_pct,_=combat_defense_percent(defender)
                if _take_effect(d,defender,"shatter"):
                    defense_pct=int(round(defense_pct*0.70))
                if _take_effect(d,defender,"armor"):
                    defense_pct=min(90,defense_pct+30)
                blocked=int(round(damage*defense_pct/100))
                damage=max(0,damage-blocked); d["defending_user"]=0
            else:
                # Standalone defense potion works without pressing the defend button.
                if defense_pct:
                    blocked=int(round(damage*defense_pct/100)); damage=max(0,damage-blocked)
                if _take_effect(d,defender,"armor"):
                    armor_block=int(round(damage*30/100)); blocked+=armor_block; damage=max(0,damage-armor_block)
                if _take_effect(d,defender,"shatter"):
                    armor,_=combat_defense_percent(defender)
                    extra=int(round(damage*(armor*0.30)/100)); blocked+=extra; damage=max(0,damage-extra)
            # Freeze weakens this attack by 30%.
            if _take_effect(d,uid,"freeze"):
                freeze_block=int(round(damage*30/100)); blocked+=freeze_block; damage=max(0,damage-freeze_block)
            # Apply HP damage.
            if defender==b["creator_id"]: d["hp_a"]=max(0,d["hp_a"]-damage)
            else: d["hp_b"]=max(0,d["hp_b"]-damage)
            # Counter potion reflects 25% of final damage.
            if _take_effect(d,defender,"counter") and damage>0:
                counter=int(round(damage*25/100))
                if uid==b["creator_id"]: d["hp_a"]=max(0,d["hp_a"]-counter)
                else: d["hp_b"]=max(0,d["hp_b"]-counter)
            if heal:
                if uid==b["creator_id"]: d["hp_a"]=min(100,d["hp_a"]+25)
                else: d["hp_b"]=min(100,d["hp_b"]+25)

        if (not dodged) and (d["hp_a"]<=0 or d["hp_b"]<=0):
            winner=b["creator_id"] if d["hp_a"]>0 else b["opponent_id"] if d["hp_b"]>0 else uid
            pot=b["stake"]*2; add_coins(winner,pot)
            loser=b["opponent_id"] if winner==b["creator_id"] else b["creator_id"]
            record_game(winner,"win",pot,"combat"); record_game(loser,"loss",0,"combat"); log_tx(winner,"combat_duel_win",pot,f"battle={bid}")
            with db() as c:
                c.execute("UPDATE combat_battles SET status='finished',winner_id=? WHERE id=? AND status='active'",(winner,bid))
                c.execute("DELETE FROM combat_duels WHERE battle_id=?",(bid,)); c.commit()
            combat_states.pop(bid,None); combat_timeout_tokens.pop(bid,None)
            return {"finished":True,"winner":winner,"damage":damage,"blocked":blocked,"defense_pct":defense_pct,"pot":pot,"hp_a":d["hp_a"],"hp_b":d["hp_b"],"dodged":dodged,"critical":critical,"counter":counter},"ok"
        d["turn_user"]=defender; d["turn_no"]+=1; d["updated_at"]=int(time.time())
    combat_states[bid]=dict(d)
    payload=json.dumps({"potion_effects":d.get("potion_effects",{}),"defense_potion":d.get("defense_potion",{})},ensure_ascii=False,separators=(",",":"))
    with db() as c:
        c.execute("UPDATE combat_duels SET turn_user=?,hp_a=?,hp_b=?,defending_user=?,special_a=0,special_b=0,turn_no=?,updated_at=?,potion_state=? WHERE battle_id=?",
                  (d["turn_user"],d["hp_a"],d["hp_b"],d["defending_user"],d["turn_no"],d["updated_at"],payload,bid)); c.commit()
    refresh_combat_timeout(bid)
    return {"finished":False,"action":action,"damage":damage,"blocked":blocked,"defense_pct":defense_pct,"dodged":dodged,"critical":critical,"counter":counter,"state":dict(d)},"ok"

def black_shop_text():
    lines=["🕶️ فروشگاه سیاه — تجهیزات مبارزه و امنیت ⚔️\n"]
    for i,(item,(cost,desc)) in enumerate(BLACK_SHOP_ITEMS.items(),1):
        if item==HACKER_ITEM:
            lvl=hack_level(_black_shop_view_uid) if _black_shop_view_uid else 0
            next_cost=hack_next_cost(_black_shop_view_uid,HACKER_ITEM) if _black_shop_view_uid else HACKER_BASE_COST
            effect=f"💻 سطح {lvl}/{HACKER_MAX_LEVEL} | 🎯 شانس پایه فعلی: {80 if lvl==5 else (30+(lvl-1)*10 if lvl else 0)}% | 💎 خرید/ارتقای بعدی: {format_coins(next_cost) if next_cost else 'تکمیل'}"
        elif item==ANTI_HACK_ITEM:
            lvl=anti_hack_level(_black_shop_view_uid) if _black_shop_view_uid else 0
            next_cost=hack_next_cost(_black_shop_view_uid,ANTI_HACK_ITEM) if _black_shop_view_uid else ANTI_HACK_BASE_COST
            effect=f"🛡️ سطح {lvl}/{ANTI_HACK_MAX_LEVEL} | ➖ کاهش شانس هکر: {lvl*10}% | 💎 خرید/ارتقای بعدی: {format_coins(next_cost) if next_cost else 'تکمیل'}"
        elif item==TRADE_POTION_ITEM:
            qty=inventory_qty(_black_shop_view_uid,TRADE_POTION_ITEM) if _black_shop_view_uid else 0
            effect=f"🎲 +5٪ شانس ترید | 🎒 موجودی: {qty} | هر ترید یک عدد مصرف می‌شود"
        else:
            power = COMBAT_POWER.get(item, 0)
            effect = f"⚔️ قدرت مبارزه: +{power}" if power > 0 else f"✨ {desc}"
        display_cost = hack_next_cost(_black_shop_view_uid,item) if item in (HACKER_ITEM,ANTI_HACK_ITEM) and _black_shop_view_uid else get_price(price_key_for("black", item), cost)
        lines.append(f"{i}. {item} — 💎 {format_coins(display_cost) if display_cost else 'تکمیل شده'}\n   {effect}")
    return "\n".join(lines)

_black_shop_view_uid = 0

def black_shop_keyboard():
    rows=[]
    uid=_black_shop_view_uid
    for i,item in enumerate(BLACK_SHOP_ITEMS,1):
        if item==HACKER_ITEM:
            lvl=hack_level(uid) if uid else 0
            cost=hack_next_cost(uid,HACKER_ITEM) if uid else get_price(price_key_for("black", item), HACKER_BASE_COST)
            label="🏆 تکمیل شده" if lvl>=HACKER_MAX_LEVEL else (f"⬆️ {item} → سطح {lvl+1} — {format_coins(cost)}" if lvl else f"🛒 {item} سطح 1 — {format_coins(cost)}")
        elif item==ANTI_HACK_ITEM:
            lvl=anti_hack_level(uid) if uid else 0
            cost=hack_next_cost(uid,ANTI_HACK_ITEM) if uid else get_price(price_key_for("black", item), ANTI_HACK_BASE_COST)
            label="🏆 تکمیل شده" if lvl>=ANTI_HACK_MAX_LEVEL else (f"⬆️ {item} → سطح {lvl+1} — {format_coins(cost)}" if lvl else f"🛒 {item} سطح 1 — {format_coins(cost)}")
        elif item==TRADE_POTION_ITEM:
            base_cost=BLACK_SHOP_ITEMS[item][0]
            cost=get_price(price_key_for("black", item), base_cost)
            qty=inventory_qty(uid,TRADE_POTION_ITEM) if uid else 0
            label=f"🧪 {item} — {format_coins(cost)} | موجودی: {qty}"
        else:
            base_cost=BLACK_SHOP_ITEMS[item][0]
            cost=get_price(price_key_for("black", item), base_cost)
            label=f"🛒 {item} — {format_coins(cost)}"
        rows.append([button(label,f"blackshop:buy:{i}")])
    rows.append([button("🎒 آیتم‌های من","user:inventory"),button("🔙 منو","user:menu")])
    rows.append([button("❌ بستن منو","menu:close")])
    return keyboard(rows)

def combat_players_text(b):
    return (f"👤 بازیکن اول: {mention_by_id(b['creator_id'])}\n"
            f"👤 بازیکن دوم: {mention_by_id(b['opponent_id'])}")


def refresh_combat_timeout(bid):
    b=combat_get(bid)
    if not b or b.get("status")!="active": return
    token=int(combat_timeout_tokens.get(bid,0))+1
    combat_timeout_tokens[bid]=token
    asyncio.create_task(combat_inactivity_timeout(bid,token))


async def combat_inactivity_timeout(bid,token):
    await asyncio.sleep(WAGER_WAIT_SECONDS)
    if combat_timeout_tokens.get(bid)!=token: return
    b=combat_get(bid); d=duel_get(bid)
    if not b or not d or b.get("status")!="active": return
    expected=d["turn_user"]
    winner=b["opponent_id"] if expected==b["creator_id"] else b["creator_id"]
    pot=b["stake"]*2
    add_coins(winner,pot)
    log_tx(winner,"combat_timeout_win",pot,f"battle={bid}")
    record_game(winner,"win",pot,"combat")
    record_game(expected,"loss",0,"combat")
    with db() as c:
        c.execute("UPDATE combat_battles SET status='finished',winner_id=? WHERE id=? AND status='active'",(winner,bid))
        c.execute("DELETE FROM combat_duels WHERE battle_id=?",(bid,)); c.commit()
    combat_timeout_tokens.pop(bid,None)
    combat_states.pop(bid,None)
    combat_action_locks.pop(bid,None)
    try:
        await bot.send_message(b["chat_id"],
            f"⏰ یک دقیقه از نوبت {display_name_by_id(expected)} گذشت.\n"
            f"🚫 به دلیل عدم انجام حرکت، حریف برنده اعلام شد.\n"
            f"🏆 برنده: {mention_by_id(winner)}\n"
            f"💎 جایزه: {format_coins(pot)} آریور\n\n{combat_players_text(b)}", parse_mode="HTML")
    except Exception: pass


def combat_create(chat_id,creator_id,stake):
    if stake<=0 or get_balance(creator_id)<stake:return None,"funds"
    add_coins(creator_id,-stake); log_tx(creator_id,"combat_lock",-stake,"combat")
    with db() as c:
        cur=c.execute("INSERT INTO combat_battles(chat_id,creator_id,stake,status,created_at) VALUES(?,?,?,?,?)",(chat_id,creator_id,stake,"waiting",int(time.time()))); bid=cur.lastrowid; c.commit()
    return bid,"ok"

def combat_get(bid):
    with db() as c:r=c.execute("SELECT id,chat_id,message_id,creator_id,opponent_id,stake,status,creator_power,opponent_power,winner_id,created_at FROM combat_battles WHERE id=?",(bid,)).fetchone()
    if not r:return None
    return {"id":r[0],"chat_id":r[1],"message_id":r[2],"creator_id":r[3],"opponent_id":r[4],"stake":r[5],"status":r[6],"creator_power":r[7],"opponent_power":r[8],"winner_id":r[9],"created_at":r[10]}

def combat_join(bid,uid):
    b=combat_get(bid)
    if not b:return None,"missing"
    if b["status"]!="waiting":return b,"closed"
    if uid==b["creator_id"]:return b,"self"
    if get_balance(uid)<b["stake"]:return b,"funds"
    add_coins(uid,-b["stake"]); log_tx(uid,"combat_lock",-b["stake"],"combat")
    cp=combat_power(b["creator_id"])
    op=combat_power(uid)
    with db() as c:
        c.execute(
            "UPDATE combat_battles SET opponent_id=?,status='active',creator_power=?,opponent_power=? WHERE id=? AND status='waiting'",
            (uid,cp,op,bid)
        )
        c.commit()
    return combat_get(bid),"ok"

def resolve_combat(bid):
    b=combat_get(bid)
    if not b or b["status"]!="active":return None
    cp,op=combat_power(b["creator_id"]),combat_power(b["opponent_id"])
    bonus_c=10 if remove_item(b["creator_id"],"🍀 شانس ویژه",1) else 0
    bonus_o=10 if remove_item(b["opponent_id"],"🍀 شانس ویژه",1) else 0
    cchance=max(10,min(90,50+(cp-op)*2+bonus_c-bonus_o))
    winner=b["creator_id"] if random.random()<cchance/100 else b["opponent_id"]
    loser=b["opponent_id"] if winner==b["creator_id"] else b["creator_id"]
    # 🛡️ Shield protects the loser once: both stakes are returned and the shield is consumed.
    protected=remove_item(loser,"🛡️ سپر انرژی",1)
    pot=b["stake"]*2
    if protected:
        add_coins(b["creator_id"],b["stake"]); add_coins(b["opponent_id"],b["stake"])
        log_tx(b["creator_id"],"combat_shield_refund",b["stake"],"shield")
        log_tx(b["opponent_id"],"combat_shield_refund",b["stake"],"shield")
        record_game(b["creator_id"],"draw",b["stake"],"combat")
        record_game(b["opponent_id"],"draw",b["stake"],"combat")
        winner=None
    else:
        add_coins(winner,pot); log_tx(winner,"combat_win",pot,"combat")
        record_game(winner,"win",pot,"combat"); record_game(loser,"loss",0,"combat")
    with db() as c:c.execute("UPDATE combat_battles SET status='finished',creator_power=?,opponent_power=?,winner_id=? WHERE id=?",(cp,op,winner or 0,bid)); c.commit()
    return {"battle":b,"creator_power":cp,"opponent_power":op,"creator_chance":cchance,"winner":winner,"loser":loser,"pot":pot,"bonus_creator":bonus_c,"bonus_opponent":bonus_o,"protected":protected}

async def combat_expiry_task(bid):
    await asyncio.sleep(WAGER_WAIT_SECONDS)
    b=combat_get(bid)
    if not b or b["status"]!="waiting":return
    add_coins(b["creator_id"],b["stake"]); log_tx(b["creator_id"],"combat_refund",b["stake"],"combat")
    with db() as c:c.execute("UPDATE combat_battles SET status='refunded' WHERE id=? AND status='waiting'",(bid,)); c.commit()
    try:await bot.edit_message_text(f"⏰ زمان دعوت مبارزه تمام شد.\n💎 {format_coins(b['stake'])} آریور به سازنده برگشت.",chat_id=b["chat_id"],message_id=b["message_id"])
    except Exception:pass

# ================================================================
# ORIGINAL BOT HANDLERS
# ================================================================
LEADERBOARD_BOARDS = {
    "wealth": "💰 پولدارترین‌ها",
    "best": "⭐ بهترین‌ها",
    "activity": "📊 فعالیت‌ها",
    "football": "⚽ بهترین تیم‌های فوتبال",
}
LEADERBOARD_PERIODS = {
    "daily": "🗓 روزانه",
    "weekly": "📅 هفتگی",
    "monthly": "🗓 ماهانه",
}

def leaderboard_reward_key(board, period, rank):
    return f"lb_reward:{board}:{period}:{int(rank)}"

def leaderboard_reward_amount(board, period, rank):
    try:
        return max(0,int(get_setting(leaderboard_reward_key(board,period,rank)) or 0))
    except Exception:
        return 0

def leaderboard_reward_keyboard():
    return keyboard([[button(title,f"lbr:board:{board}")] for board,title in LEADERBOARD_BOARDS.items()] + [[button("🔙 پنل مدیریت","admin:panel")]])

def leaderboard_reward_period_keyboard(board):
    return keyboard([[button(title,f"lbr:period:{board}:{period}")] for period,title in LEADERBOARD_PERIODS.items()] + [[button("🔙 جایزه لیدربورد","admin:lb_rewards")]])

def leaderboard_reward_rank_keyboard(board,period):
    rows=[]
    for rank in range(1,6):
        amount=leaderboard_reward_amount(board,period,rank)
        rows.append([button(f"🥇 جایزه رتبه {rank} — {format_coins(amount)} آریور",f"lbr:set:{board}:{period}:{rank}")])
    rows.append([button("🔙 دوره‌ها",f"lbr:board:{board}")])
    rows.append([button("❌ بستن پنل","menu:close")])
    return keyboard(rows)

def leaderboard_rows_for_board(board, limit=5):
    with db() as c:
        if board=="wealth":
            return [(int(r[0]),) for r in c.execute("SELECT u.id FROM users u LEFT JOIN coins co ON co.user_id=u.id LEFT JOIN bank b ON b.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) AND lower(COALESCE(u.username,'')) != lower(?) ORDER BY (COALESCE(co.balance,0)+COALESCE(b.balance,0)) DESC,u.id ASC LIMIT ?",(ARSIN_USERNAME,limit)).fetchall()]
        if board=="best":
            return [(int(r[0]),) for r in c.execute("SELECT u.id FROM users u JOIN player_stats s ON s.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) AND lower(COALESCE(u.username,'')) != lower(?) ORDER BY s.xp DESC,s.points DESC,u.id ASC LIMIT ?",(ARSIN_USERNAME,limit)).fetchall()]
        if board=="activity":
            return [(int(r[0]),) for r in c.execute("SELECT u.id FROM users u JOIN player_stats s ON s.user_id=u.id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=u.id) AND lower(COALESCE(u.username,'')) != lower(?) ORDER BY s.games DESC,s.xp DESC,u.id ASC LIMIT ?",(ARSIN_USERNAME,limit)).fetchall()]
        if board=="football":
            rows=c.execute("SELECT t.user_id FROM football_teams t JOIN users u ON u.id=t.user_id WHERE NOT EXISTS (SELECT 1 FROM bot_bans bb WHERE bb.user_id=t.user_id) AND lower(COALESCE(u.username,'')) != lower(?) AND (t.wins+t.losses)>0 ORDER BY CAST(t.wins AS REAL)/NULLIF(t.wins+t.losses,0) DESC,(t.wins+t.losses) DESC,t.wins DESC,t.id ASC LIMIT ?",(ARSIN_USERNAME,limit)).fetchall()
            return [(int(r[0]),) for r in rows]
    return []

def _lb_period_key(period, dt):
    if period=="daily":
        return dt.strftime("%Y-%m-%d")
    if period=="weekly":
        iso=dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return dt.strftime("%Y-%m")

def _lb_current_period_keys():
    dt=datetime.now(ZoneInfo("Asia/Tehran"))
    return {p:_lb_period_key(p,dt) for p in LEADERBOARD_PERIODS}

async def process_leaderboard_rewards_once():
    keys=_lb_current_period_keys()
    for period,current_key in keys.items():
        state_key=f"lb_last_seen:{period}"
        previous=get_setting(state_key)
        if previous is None:
            set_setting(state_key,current_key)
            continue
        if previous==current_key:
            continue
        # The ranking is evaluated once at the period boundary and protected by a DB run key.
        for board in LEADERBOARD_BOARDS:
            with db() as c:
                exists=c.execute("SELECT 1 FROM leaderboard_reward_runs WHERE period_type=? AND period_key=? AND board=?",(period,previous,board)).fetchone()
                if exists:
                    continue
                c.execute("INSERT INTO leaderboard_reward_runs(period_type,period_key,board,paid_at) VALUES(?,?,?,?)",(period,previous,board,int(time.time())))
                c.commit()
            rows=leaderboard_rows_for_board(board,5)
            for rank,(uid,) in enumerate(rows,1):
                amount=leaderboard_reward_amount(board,period,rank)
                if amount<=0:
                    continue
                add_coins(uid,amount)
                log_tx(uid,"leaderboard_reward",amount,f"board={board};period={period};period_key={previous};rank={rank}")
                try:
                    await bot.send_message(uid,f"🏆 جایزه {LEADERBOARD_BOARDS[board]}\n🥇 رتبه {rank}\n💰 جایزه شما به مقدار {format_coins(amount)} آریور واریز شد.")
                except Exception:
                    pass
        set_setting(state_key,current_key)

async def leaderboard_reward_loop():
    while True:
        try:
            await process_leaderboard_rewards_once()
        except Exception as exc:
            print(f"Leaderboard reward error: {exc}")
        await asyncio.sleep(30)

def get_auto_replies():
    with db() as c:
        return c.execute("SELECT id,keyword,response,active FROM auto_replies ORDER BY id ASC").fetchall()

def add_auto_reply(keyword,response):
    keyword=str(keyword or "").strip(); response=str(response or "").strip()
    if not keyword or not response: return False
    with db() as c:
        try:
            c.execute("INSERT INTO auto_replies(keyword,response,active,created_at) VALUES(?,?,1,?)",(keyword,response,int(time.time())))
            c.commit(); return True
        except sqlite3.IntegrityError: return False

def delete_auto_reply(rid):
    with db() as c:
        cur=c.execute("DELETE FROM auto_replies WHERE id=?",(int(rid),)); c.commit(); return cur.rowcount>0

def welcome_text():
    return get_setting("welcome_text") or "سلام به همگی! من آریو هستم 🤖✨\nخوش اومدین! آماده‌ام برای بازی‌ها و امکانات گروه."

def welcome_buttons():
    try:
        x=json.loads(get_setting("welcome_buttons") or "[]")
        return x if isinstance(x,list) else []
    except Exception: return []

def save_welcome_buttons(items):
    set_setting("welcome_buttons",json.dumps(items,ensure_ascii=False))

def welcome_markup():
    rows=[]
    for item in welcome_buttons():
        if item.get("url"):
            rows.append([InlineKeyboardButton(text=str(item.get("text") or "🔗 لینک")[:64],url=str(item["url"]))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

def welcome_preview_text():
    n=len(welcome_buttons())
    return "👋 ولکام بات فعلی:\n\n"+welcome_text()+f"\n\n🔗 لینک‌های شیشه‌ای: {n} عدد"

def auto_reply_panel_keyboard():
    rows=[[button("➕ افزودن پاسخ خودکار","autoreply:add")]]
    for rid,kw,resp,active in get_auto_replies(): rows.append([button(f"🗑️ {kw}"[:60],f"autoreply:del:{rid}")])
    rows.append([button("🔙 پنل مدیریت","admin:panel")]); return keyboard(rows)

def welcome_panel_keyboard():
    rows=[[button("✏️ تغییر متن ولکام","welcome:text")],[button("➕ افزودن لینک شیشه‌ای","welcome:addbtn")]]
    for i,item in enumerate(welcome_buttons()): rows.append([button(f"🗑️ {item.get('text','لینک')}"[:60],f"welcome:delbtn:{i}")])
    rows.append([button("🔙 پنل مدیریت","admin:panel")]); return keyboard(rows)

async def bot_can_kick(chat_id):
    try:
        me=await bot.get_me()
        m=await bot.get_chat_member(chat_id,me.id)
        status=str(getattr(m,"status","") or "")
        if status in ("creator","owner"):
            return True
        if status != "administrator":
            return False
        # aiogram/Telegram normally exposes this as can_restrict_members.
        # Keep a defensive fallback for versions/objects where the field is absent.
        return bool(getattr(m,"can_restrict_members",False))
    except Exception as exc:
        print(f"Permission check error chat={chat_id}: {exc}")
        return False

async def kick_member(chat_id,user_id):
    # Do not reject based only on the cached/parsed administrator flag.
    # Telegram itself is the final authority for whether this bot can ban the user.
    try:
        await bot.ban_chat_member(chat_id,user_id)
        try:
            await bot.unban_chat_member(chat_id,user_id,only_if_banned=True)
        except Exception as exc:
            print(f"Kick unban warning chat={chat_id} user={user_id}: {exc}")
        return True,"ok"
    except Exception as exc:
        err=str(exc)
        print(f"Kick error chat={chat_id} user={user_id}: {err}")
        low=err.lower()
        if any(x in low for x in ("not enough rights","not enough privileges","forbidden","have no rights","can't restrict","cannot restrict","administrator rights")):
            return False,"no_permission"
        return False,"error"

async def execute_kick_command(message):
    if message.chat.type not in ("group","supergroup") or not is_arsin_id(message.from_user.id): return False
    cmd=(message.text or "").strip().replace("ي","ی").replace("ك","ک")
    if cmd not in ("صیک","صیک پلاس"): return False
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("❌ برای اجرای این دستور باید روی پیام کاربر ریپلای کنی."); return True
    target=message.reply_to_message.from_user
    if target.id==message.from_user.id or is_arsin_target(target):
        await message.reply("❌ این کاربر قابل اخراج با این دستور نیست."); return True
    if cmd=="صیک":
        ok,_=await kick_member(message.chat.id,target.id)
        await message.reply(f"✂️ کاربر {target.full_name or target.id} از این گروه اخراج شد." if ok else "❌ دسترسی ندارم؛ ربات در این گروه اجازه اخراج اعضا را ندارد.")
        return True
    with db() as c: chats=[int(r[0]) for r in c.execute("SELECT chat_id FROM known_chats WHERE active=1 AND chat_type IN ('group','supergroup')").fetchall()]
    ok_count=0; fail_count=0
    for chat_id in dict.fromkeys(chats):
        ok,_=await kick_member(chat_id,target.id)
        ok_count += int(ok); fail_count += int(not ok); await asyncio.sleep(.05)
    if not chats: msg="ℹ️ هنوز هیچ گروه فعالی برای اجرای «صیک پلاس» ثبت نشده است."
    elif ok_count: msg=f"✂️ صیک پلاس انجام شد.\n📊 موفق: {ok_count} گروه\n⚠️ ناموفق/بدون دسترسی: {fail_count} گروه"
    else: msg="❌ دسترسی ندارم؛ ربات در گروه‌های لازم اجازه اخراج اعضا را ندارد."
    await message.reply(msg); return True

async def handle_auto_reply(message):
    if message.chat.type not in ("group","supergroup") or not message.text or message.from_user.is_bot: return False
    t=message.text.strip().casefold()
    for _,kw,resp,active in get_auto_replies():
        keyword=str(kw or "").strip().casefold()
        if int(active) and keyword and keyword in t:
            try:
                await message.reply(resp)
            except Exception as exc:
                print(f"Auto-reply error chat={message.chat.id}: {exc}")
            return True
    return False

def admin_panel_keyboard(user_id=None):
    uid = int(user_id or 0)
    rows=[]
    def add(label, section, callback):
        if is_arsin_id(uid) or admin_has_permission(uid, section):
            rows.append([button(label, callback)])
    add("💎 افزایش موجودی","addcoins","admin:addcoins")
    add("➖ کسر موجودی","removebalance","admin:removebalance")
    add("🏷️ قیمت‌ها","prices","admin:prices")
    add("🚫 کاربران بن‌شده","banned","admin:banned")
    if is_arsin_id(uid):
        rows.append([button("👑 افزودن شوشول","admin:addadmin"),button("🗂️ لیست ادمین‌ها","admin:admins")])
        rows.append([button("🔐 دسترسی ادمین‌ها","admin:admins")])
    add("📢 اطلاعیه","announce","admin:announce")
    if is_arsin_id(uid):
        rows.append([button("👥 کاربران استارت‌کرده","admin:started_users")])
    add("⚽ مدیریت فوتبال","football","admin:football")
    add("📚 راهنمای آرسین","help","admin:help")
    add("💬 پاسخ خودکار","autoreply","admin:autoreply")
    add("👋 ولکام بات","welcome","admin:welcome")
    add("🛡️ دستورات اخراج","moderation","admin:moderation")
    add("🎁 کد هدیه","gift","admin:gift")
    add("🏆 جایزه لیدربورد","addcoins","admin:lb_rewards")
    if is_arsin_id(uid):
        rows.append([button("🎟️ قرعه‌کشی","lottery:create")])
        rows.append([button("🗂️ مدیریت قرعه‌کشی‌ها","lottery:manage")])
    add("📋 لیست کد هدیه","gifts","admin:gifts")
    if is_arsin_id(uid) or admin_has_permission(uid,"links"):
        link_slots = configured_link_slots()
        for i in range(0, len(link_slots), 2):
            row = []
            for slot in link_slots[i:i+2]:
                row.append(button(f"🔗 لینک {slot}", f"link:{slot}"))
            rows.append(row)
        rows.append([button("➕ افزودن لینک", "link:add")])
    rows.append([button("❌ بستن پنل","menu:close")])
    return keyboard(rows)


PRICE_CATEGORIES = {
    "shop": ("🛍️ فروشگاه عادی", [item for item,_data in normal_shop_items()]),
    "black": ("🕶️ فروشگاه سیاه", list(BLACK_SHOP_ITEMS.keys())),
    "pets": ("🐾 فروشگاه حیوانات", list(PETS.keys())),
    "upgrade": ("⬆️ ارتقاها", ["ارتقای لول اصلی", "ارتقای شانس", "ارتقای تجربه"]),
    "property": ("🏠 قیمت متری مناطق", [f"منطقه {rid} ({name})" for rid,name,_price in PROPERTY_REGIONS]),
    "business": ("🏬 پاساژ", ["قیمت هر متر مغازه پاساژ"]),
    "materials": ("🧱 مصالح ساختمانی", [x[0] for x in BUILDING_MATERIALS]),
    "decor": ("🛋️ دکوراسیون داخلی", [x[0] for x in DECORATION_ITEMS]),
}


def price_default(category, item):
    if category=="shop": return SHOP_ITEMS_V2[item][0]
    if category=="black": return BLACK_SHOP_ITEMS[item][0]
    if category=="pets": return PETS[item][0]
    if category=="upgrade" and item=="ارتقای لول اصلی": return LEVEL_UP_BASE_COST
    if category=="upgrade" and item in ("ارتقای شانس","ارتقای تجربه"): return UPGRADE_STAT_BASE_COST
    if category=="property":
        rid=int(item.split(" ")[1]); return property_region(rid)[2]
    if category=="business": return MALL_STORE_PRICE_PER_METER
    if category=="materials":
        for name,unit,base_qty,package_size,package_price,icon in BUILDING_MATERIALS:
            if name==item: return package_price
    if category=="decor":
        for name,price,cat in DECORATION_ITEMS:
            if name==item: return price
    return 0


def price_key_admin(category,item):
    if category=="upgrade":
        if item=="ارتقای لول اصلی": return "upgrade:level"
        if item=="ارتقای شانس": return "upgrade:luck"
        return "upgrade:exp"
    if category=="property":
        rid=int(item.split(" ")[1]); return f"property:region:{rid}"
    if category=="business": return "mall_store:per_meter"
    if category=="materials": return f"materials:{item}"
    if category=="decor": return f"decor:{item}"
    return price_key_for(category,item)


def admin_prices_keyboard():
    rows=[]
    for cat,(title,_items) in PRICE_CATEGORIES.items():
        rows.append([button(title,f"admin:prices:cat:{cat}")])
    rows.append([button("🔙 پنل مدیریت","admin:panel")])
    return keyboard(rows)


def admin_price_category_keyboard(category):
    title,items=PRICE_CATEGORIES[category]
    rows=[]
    for idx,item in enumerate(items):
        key=price_key_admin(category,item)
        current=get_price(key,price_default(category,item))
        rows.append([button(f"{item} — 💎 {format_coins(current)}",f"admin:price:{category}:{idx}")])
    rows.append([button("🔙 دسته‌بندی قیمت‌ها","admin:prices")])
    rows.append([button("❌ بستن پنل","menu:close")])
    return keyboard(rows)


def admin_banned_keyboard():
    rows=[]
    for uid,username,full_name,wallet,bank,banned_at in banned_rows():
        label=f"🚫 {(' @'+username) if username else (full_name or str(uid))} | {uid}"
        rows.append([button(label[:60],f"admin:unban:{uid}")])
    rows.append([button("🔙 پنل مدیریت","admin:panel")])
    rows.append([button("❌ بستن پنل","menu:close")])
    return keyboard(rows)


def admin_panel_text():
    return "👑 پنل مدیریت آرسین\n\n🛡️ بخش‌های فعال برای حساب شما در دکمه‌های زیر نمایش داده می‌شوند.\n💎 موجودی آرسین: &"


def admin_help_text():
    return (
        "📚 راهنمای کامل پنل آرسین\n\n"
        "👑 آرسین اصلی و مدیرانی که آرسین اضافه کرده می‌توانند پنل را باز کنند.\n"
        "هر زمان در پیوی یا گروه بنویسی «پنل»، پنل مدیریتی باز می‌شود.\n\n"
        "🛠️ بخش‌های پنل\n"
        "• 💎 افزایش موجودی: انتخاب کاربر و اضافه‌کردن آریور به کیف پول.\n"
        "• ➖ کسر موجودی: از موجودی کل کاربر کم می‌کند؛ اول کیف پول و سپس بانک. می‌توانی آیدی/@username یا یک پیام فورواردشده از کاربر را بدهی.\n"
        "• 🏷️ قیمت‌ها: قیمت‌های فروشگاه، فروشگاه سیاه، حیوانات، ارتقاها، ملک، مصالح و دکوراسیون را تغییر می‌دهد.\n"
        "• 🚫 کاربران بن‌شده: لیست کاربران بریده‌شده و دکمه بازگردانی.\n"
        "• 📢 اطلاعیه: یک پیام را برای کاربران استارت‌کرده و چت‌های شناخته‌شده ربات ارسال می‌کند.\n"
        "• ⚽ مدیریت فوتبال: تغییر قیمت بازیکنان، افزودن بازیکن/مربی و تنظیم درآمد روزانه فوتبال.\n"
        "• 👑 افزودن شوشول: فقط آرسین اصلی می‌تواند با ریپلای یک کاربر را مدیر کند.\n"
        "• 🎁 کد هدیه: ساخت کد هدیه با ظرفیت مشخص؛ تعداد استفاده‌شده در لیست نمایش داده می‌شود.\n"
        "• 📋 لیست کد هدیه: مشاهده و منقضی‌کردن کدها.\n"
        "• 🔗 لینک‌ها: مدیریت لینک‌های عضویت؛ می‌توانی با «➕ افزودن لینک» هر تعداد لینک که لازم داری اضافه کنی.\n"
        "• 💬 پاسخ خودکار: ثبت کلمه/عبارت و پاسخ دلخواه برای گروه‌ها.\n"
        "• 👋 ولکام بات: تغییر متن پیام ورود ربات و افزودن هر تعداد لینک شیشه‌ای.\n"
        "• 🛡️ دستورات اخراج: «صیک» و «صیک پلاس» با ریپلای.\n\n"
        "⌨️ دستورات مستقیم آرسین\n"
        "• «پنل» → بازکردن پنل در پیوی یا گروه.\n"
        "• «راهنمای آرسین» → نمایش همین راهنما.\n"
        "• ریپلای روی کاربر + «خطنه» → بریدن کامل کاربر و ذخیره موجودی کیف پول و بانک.\n"
        "• ریپلای روی کاربر + «شوشولشو برگردون» → خروج از بن و برگشت کامل موجودی ذخیره‌شده.\n"
        "• ریپلای + «افزایش موجودی 1000» → اضافه‌کردن آریور.\n"
        "• ریپلای + «شوشولشو ببر 1000» → کسر آریور از موجودی کل؛ اول کیف پول و سپس بانک.\n\n"
        "🛡️ قانون آرسین\n"
        "• موجودی آرسین در نمایش‌ها «&» است.\n"
        "• هیچ کاربری نمی‌تواند آرسین را هک یا شوشول‌بری کند.\n"
        "• آرسین در عملیات هدف‌گیری بازی مافیا نیز قابل انتخاب نیست.\n"
        "• آرسین قابل بن‌شدن نیست.\n"
        "• عملیات مدیریتی روی حساب آرسین هم مسدود است تا موجودی ویژه او تغییر نکند."
    )


@dp.message(CommandStart())
async def command_start(message: Message):
    remember(message.from_user)
    if message.chat.type != "private":
        if is_banned(message.from_user.id):
            return
        return
    if not is_arsin_user(message.from_user) and is_banned(message.from_user.id):
        await message.answer("✂️ شوشول شما توسط مدیر ربات کامل بریده شده است و دیگر جایی در ربات ندارید.\n🚫 دسترسی به امکانات ربات برای شما غیرفعال است.")
        return
    parts=(message.text or "").split(maxsplit=1)
    start_arg=parts[1].strip() if len(parts)>1 else ""
    if is_arsin_user(message.from_user):
        await message.answer(admin_panel_text(), reply_markup=admin_panel_keyboard(message.from_user.id))
        return
    if start_arg == "menu_after_join":
        if await check_memberships(message.from_user.id):
            sent_menu = await message.answer(profile_text(message.from_user.id),reply_markup=user_menu_keyboard(message.from_user.id))
            mark_menu_activity(sent_menu, message.from_user.id)
        else:
            await message.answer("🔒 برای باز شدن منو، ابتدا در هر دو لینک عضو شو.\n\n👇 بعد از عضویت روی «عضو شدم» بزن.",reply_markup=await membership_keyboard())
        return

    await message.answer(
        "🔒 برای استفاده از ربات، ابتدا در لینک‌های زیر عضو شو.\n\n"
        "👇 بعد از عضویت روی «عضو شدم» بزن تا عضویتت بررسی شود.\n\n"
        "🛠 توسعه‌یافته توسط @arsin_mo",
        reply_markup=await membership_keyboard(),
    )


@dp.callback_query(F.data == "check_membership")
async def callback_check_membership(query: CallbackQuery):
    with db() as c:
        row = c.execute("SELECT started FROM users WHERE id=?", (query.from_user.id,)).fetchone()
    if not row or not row[0]:
        await query.answer("❌ ابتدا ربات را استارت کن.", show_alert=True)
        await send_join_buttons(query.message.chat.id, include_start=True)
        return
    if not await check_memberships(query.from_user.id):
        await query.answer("❌ هنوز در همه لینک‌ها عضو نشدی.", show_alert=True)
        return
    await query.answer("✅ عضویت تأیید شد!")
    if query.message.chat.type == "private":
        sent_menu = await query.message.answer(profile_text(query.from_user.id),reply_markup=user_menu_keyboard(query.from_user.id))
        mark_menu_activity(sent_menu, query.from_user.id)
        return
    me = await bot.get_me()
    add_url = f"https://t.me/{me.username}?startgroup=true"
    await query.message.answer(
        "🎉 عضویتت تأیید شد!\n\n"
        "🤖 من آریو هستم؛ ربات اجرای بازی مافیا و امکانات گروه.\n\n"
        "🎭 اجرای بازی مافیا\n💎 سیستم آریور و موجودی\n🎁 کدهای هدیه\n👥 مدیریت مراحل بازی\n\n"
        "🛠 توسط @arsin_mo توسعه داده شده‌ام.",
        reply_markup=keyboard([[InlineKeyboardButton(text="➕ افزودن ربات به گروه", url=add_url)]])
    )


@dp.channel_post()
async def remember_channel_post(message: Message):
    remember_chat(message.chat)


@dp.my_chat_member()
async def remember_bot_chat(update: ChatMemberUpdated):
    chat=update.chat
    if chat.type not in ("group","supergroup","channel"):
        return
    new_status=getattr(update.new_chat_member,"status","")
    active=new_status not in ("left","kicked")
    remember_chat(chat)
    with db() as c:
        c.execute("UPDATE known_chats SET active=?,updated_at=? WHERE chat_id=?",(1 if active else 0,int(time.time()),chat.id)); c.commit()


@dp.message(F.new_chat_members)
async def welcome(message: Message):
    remember_chat(message.chat)
    me = await bot.get_me()
    for member in message.new_chat_members:
        if member.id == me.id:
            await message.answer(welcome_text(), reply_markup=welcome_markup())


def deduct_blocked_bank(user_id, amount):
    """Deduct money from currently blocked bank funds without allowing a later release to restore it."""
    amount=int(amount)
    if amount<=0:
        return 0
    now=int(time.time())
    remaining=amount
    deducted=0
    with db() as c:
        rows=c.execute("SELECT id,amount FROM bank_hack_blocks WHERE user_id=? AND unlock_at>? ORDER BY unlock_at ASC,id ASC",(int(user_id),now)).fetchall()
        for block_id,block_amount in rows:
            if remaining<=0:
                break
            take=min(int(block_amount),remaining)
            new_amount=int(block_amount)-take
            if new_amount>0:
                c.execute("UPDATE bank_hack_blocks SET amount=? WHERE id=?",(new_amount,block_id))
            else:
                c.execute("DELETE FROM bank_hack_blocks WHERE id=?",(block_id,))
            remaining-=take
            deducted+=take
        c.commit()
    if deducted:
        log_tx(user_id,"admin_blocked_deduction",-deducted,f"blocked_deduction={deducted}")
    return deducted


def shoshol_rain_inventory_item_for_command(text):
    return {
        "بارش شوشول": "🌧️ بارش شوشول",
        "بارش شوشول نانو": "🌧️ بارش شوشول نانو",
        "بارش شوشول طلایی": "🌧️ بارش شوشول طلایی",
    }.get(text.strip())

def remove_total_assets_for_rain(uid, amount):
    amount=max(0,int(amount))
    if amount<=0: return 0
    # Wallet first, then available bank. Blocked bank money is intentionally
    # excluded because it is not currently spendable/transferable.
    wallet=get_balance(uid)
    take_wallet=min(wallet,amount)
    if take_wallet:
        add_coins(uid,-take_wallet)
        amount-=take_wallet
    taken=take_wallet
    if amount:
        release_due_bank_hacks(uid)
        with db() as c:
            row=c.execute("SELECT COALESCE(balance,0) FROM bank WHERE user_id=?",(uid,)).fetchone()
            bank=int(row[0] or 0) if row else 0
            take_bank=min(bank,amount)
            if take_bank:
                c.execute("UPDATE bank SET balance=balance-? WHERE user_id=?",(take_bank,uid)); c.commit()
                taken+=take_bank
    return taken

def shoshol_rain_defense_reduction(target_id, item):
    for defense,(_cost,target_item,reduction,_desc) in SHOSHOL_RAIN_DEFENSES.items():
        if target_item==item and inventory_qty(target_id,defense)>0:
            return reduction,defense
    return 0,""

async def handle_shoshol_rain(message: Message):
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("❌ برای بارش شوشول باید روی پیام کاربر هدف ریپلای کنی و دستور را بفرستی.")
        return True
    attacker=message.from_user.id; target=message.reply_to_message.from_user
    if target.id==attacker:
        await message.reply("❌ نمی‌توانی روی خودت بارش شوشول اجرا کنی.")
        return True
    if is_arsin_target(target):
        await message.reply("👑 آرسین از بارش شوشول مصون است. 🛡️")
        return True
    item=shoshol_rain_inventory_item_for_command(message.text or message.caption or "")
    if not item: return False
    if inventory_qty(attacker,item)<=0:
        await message.reply("❌ این بارش را نداری. ابتدا آن را از فروشگاه سیاه بخر. 🕶️")
        return True
    cost,chance,loss_pct,desc=SHOSHOL_RAIN_ITEMS[item]
    reduction,defense_item=shoshol_rain_defense_reduction(target.id,item)
    final_chance=max(0,chance-reduction)
    if not consume_combat_item(attacker,item):
        await message.reply("❌ این واحد بارش دیگر موجود نیست.")
        return True
    success=random.random()<final_chance/100.0
    target_total=total_wealth(target.id)
    if success:
        loss=(target_total*loss_pct)//100
        taken=remove_total_assets_for_rain(target.id,loss)
        log_tx(attacker,"shoshol_rain_win",taken,f"target={target.id};item={item};chance={final_chance}%")
        if taken:
            add_coins(attacker,taken)
            log_tx(attacker,"shoshol_rain_profit",taken,f"from={target.id};item={item}")
        defense_text=f"🛡️ پدافند: {defense_item} (−{reduction} واحد درصد)" if defense_item else "🛡️ پدافند: نداشت"
        await message.reply(f"🌧️ بارش شوشول موفق شد! 😈\n\n👤 هدف: {display_name_by_id(target.id)}\n🎯 شانس نهایی: {final_chance}%\n{defense_text}\n💸 دارایی هدف قبل از عملیات: {format_coins(target_total)} آریور\n📉 مقدار کسرشده: {format_coins(taken)} آریور\n💰 این مقدار به کیف پول شما اضافه شد.")
    else:
        log_tx(attacker,"shoshol_rain_fail",0,f"target={target.id};item={item};chance={final_chance}%")
        defense_text=f"🛡️ پدافند: {defense_item} (−{reduction} واحد درصد)" if defense_item else "🛡️ پدافند: نداشت"
        await message.reply(f"🌧️ بارش شوشول شکست خورد! 😵‍💫\n\n👤 هدف: {display_name_by_id(target.id)}\n🎯 شانس نهایی: {final_chance}%\n{defense_text}\n❌ هیچ دارایی‌ای از هدف کسر نشد.")
    return True

@dp.message(F.text == "منو کاربر")
async def user_menu_by_reply(message: Message):
    if not is_arsin_user(message.from_user):
        await message.reply("❌ فقط آرسین می‌تواند منوی کاربر را با ریپلای باز کند.")
        return
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("❌ روی پیام همان کاربر ریپلای کن و بنویس «منو کاربر».")
        return
    target_id = message.reply_to_message.from_user.id
    sent=await message.answer(profile_text(target_id), reply_markup=user_menu_keyboard(target_id))
    register_menu_owner(sent,target_id)
    _MENU_HISTORY.pop(_menu_history_key(sent),None)
    mark_menu_activity(sent)

@dp.message(F.text | F.forward_origin)
async def handle_text(message: Message):
    text = (message.text or message.caption or "").strip()
    is_arsin = is_arsin_user(message.from_user)
    if not is_arsin and is_banned(message.from_user.id):
        if message.chat.type in ("group", "supergroup") and consume_group_ban_notice(message.from_user.id):
            await message.reply("✂️ شوشولت خطنه شده و دسترسی‌ات به ربات غیرفعال است.")
        return
    if message.chat.type in ("group","supergroup","channel"):
        remember_chat(message.chat)

    if is_arsin and message.chat.type in ("group","supergroup") and await execute_kick_command(message):
        return
    if await handle_auto_reply(message):
        return

    # Arsin panel commands work in both private and group chats.
    if is_admin_user(message.from_user) and text.lower() in ("پنل", "/پنل", "panel", "/panel"):
        await message.answer(admin_panel_text(), reply_markup=admin_panel_keyboard(message.from_user.id))
        return

    # Lottery creation wizard for Arsin. It works in the same chat where the
    # wizard was started, including groups.
    if is_arsin_id(message.from_user.id) and message.from_user.id in LOTTERY_PENDING:
        st=LOTTERY_PENDING[message.from_user.id]
        if st.get("chat_id") != message.chat.id:
            return
        raw=text.replace(",","").replace("٬","").strip()
        try:
            value=int(raw)
        except Exception:
            await message.reply("❌ مقدار باید فقط عدد باشد.")
            return
        if value<=0:
            await message.reply("❌ مقدار باید بیشتر از صفر باشد.")
            return
        if st.get("step")=="prize":
            st["prize"]=value; st["step"]="hours"
            await message.answer("⏳ مهلت قرعه‌کشی را وارد کن. چند ساعت دیگر قرعه‌کشی انجام شود؟")
            return
        if st.get("step")=="hours":
            if value<=0:
                await message.reply("❌ تعداد ساعت باید بیشتر از صفر باشد."); return
            st["draw_at"]=int(time.time())+value*3600; st["step"]="min_choice"
            await message.answer("🔽 حداقل تعداد شرکت‌کننده را مشخص کن:",reply_markup=keyboard([[button("♾️ نامحدود","lottery:min_unlimited")],[button("🔢 محدود","lottery:min_limited_prompt")],[button("❌ لغو","menu:close")]]))
            return
        if st.get("step")=="min_value":
            st["min_players"]=value; st["step"]="max_choice"
            await message.answer("🔼 حداکثر تعداد شرکت‌کننده را مشخص کن:",reply_markup=keyboard([[button("♾️ نامحدود","lottery:max_unlimited")],[button("🔢 محدود","lottery:max_limited")],[button("❌ لغو","menu:close")]])); return
        if st.get("step")=="max_value":
            minp=int(st.get("min_players",0))
            if value<minp: await message.reply("❌ حداکثر نمی‌تواند کمتر از حداقل باشد."); return
            st["max_players"]=value; st["step"]="confirm"
            await message.answer(lottery_pending_preview(st),reply_markup=keyboard([[button("✅ تأیید و انتشار","lottery:confirm")],[button("❌ لغو","menu:close")]])); return

    if is_arsin and text in ("راهنمای ارسین", "راهنما ارسین", "راهنمای پنل ارسین"):
        await message.answer(admin_help_text(), reply_markup=keyboard([[button("🔙 پنل مدیریت","admin:panel")],[button("❌ بستن پنل","menu:close")]]))
        return
    if is_arsin and text in ("موجودی", "balance"):
        await message.reply("👑 موجودی آرسین: & آریور")
        return

    # Admin private workflows. Do NOT remember group messages as /start.
    if message.chat.type == "private" and is_admin_user(message.from_user):
        pending = pending_admin.get(message.from_user.id)
        if isinstance(pending, tuple) and pending and pending[0] == "football_income_rate":
            if not admin_has_permission(message.from_user.id,"football"):
                pending_admin.pop(message.from_user.id,None); await message.answer("❌ دسترسی این بخش برای شما فعال نیست."); return
            try:
                rate=int(text.replace(",","")); assert rate>=0
            except Exception:
                await message.answer("❌ نرخ باید عددی صفر یا بیشتر باشد."); return
            set_setting("football:daily_income_per_power",str(rate))
            pending_admin.pop(message.from_user.id,None)
            await message.answer(f"✅ نرخ درآمد فوتبال روی {format_coins(rate)} آریور به ازای هر ۱ قدرت در روز تنظیم شد.",reply_markup=keyboard([[button("⚽ مدیریت فوتبال","admin:football")]]))
            return
        if isinstance(pending, tuple) and pending and pending[0] == "leaderboard_reward_amount":
            if not admin_has_permission(message.from_user.id,"addcoins"):
                pending_admin.pop(message.from_user.id,None); await message.answer("❌ دسترسی این بخش برای شما فعال نیست."); return
            try:
                amount=int(text.replace(",","")); assert amount>=0
            except Exception:
                await message.answer("❌ مقدار جایزه باید عددی صفر یا بیشتر باشد."); return
            _,board,period,rank=pending
            set_setting(leaderboard_reward_key(board,period,rank),str(amount))
            pending_admin.pop(message.from_user.id,None)
            await message.answer(f"✅ جایزه رتبه {rank} در {LEADERBOARD_BOARDS[board]} برای {LEADERBOARD_PERIODS[period]} روی {format_coins(amount)} آریور تنظیم شد.",reply_markup=keyboard([[button("🏆 جایزه لیدربورد","admin:lb_rewards")],[button("⚽ مدیریت فوتبال","admin:football")]]))
            return
        if isinstance(pending, tuple) and pending and pending[0] == "football_price":
            if not admin_has_permission(message.from_user.id,"football"):
                pending_admin.pop(message.from_user.id,None); await message.answer("❌ دسترسی این بخش برای شما فعال نیست."); return
            try: price=int(text.replace(",","")); assert price>=5_000_000
            except Exception:
                await message.answer("❌ قیمت ماهانه بازیکن باید حداقل 5,000,000 آریور باشد."); return
            pid=int(pending[1])
            with db() as c:c.execute("UPDATE football_players SET monthly_price=? WHERE id=?",(price,pid)); c.commit()
            pending_admin.pop(message.from_user.id,None)
            await message.answer(f"✅ قیمت ماهانه بازیکن روی {format_coins(price)} آریور تنظیم شد.",reply_markup=keyboard([[button("⚽ مدیریت فوتبال","admin:football")]])); return
        if isinstance(pending, tuple) and pending and pending[0] == "football_add_coach_name":
            if not text or len(text)>80:
                await message.answer("❌ نام مربی نامعتبر است."); return
            pending_admin[message.from_user.id]=( "football_add_coach_power", text )
            await message.answer("💪 قدرت مربی را ارسال کن (مثلاً 88):"); return
        if isinstance(pending, tuple) and pending and pending[0] == "football_add_coach_power":
            name=pending[1]
            try: power=int(text); assert 1<=power<=100
            except Exception:
                await message.answer("❌ قدرت باید عددی بین 1 تا 100 باشد."); return
            pending_admin[message.from_user.id]=( "football_add_coach_price", name, power )
            await message.answer("💰 قیمت ماهانه مربی را ارسال کن (حداقل 5,000,000 آریور):"); return
        if isinstance(pending, tuple) and pending and pending[0] == "football_add_coach_price":
            name,power=pending[1],pending[2]
            try: price=int(text.replace(",","")); assert price>=5_000_000
            except Exception:
                await message.answer("❌ قیمت باید حداقل 5,000,000 آریور باشد."); return
            try:
                with db() as c:
                    c.execute("INSERT INTO football_coaches(name,power,monthly_price) VALUES(?,?,?)",(name,power,price)); c.commit()
            except sqlite3.IntegrityError:
                await message.answer("❌ مربی‌ای با این نام قبلاً ثبت شده است."); return
            pending_admin.pop(message.from_user.id,None)
            await message.answer(f"✅ مربی جدید اضافه شد.\n👔 {name}\n💪 قدرت: {power}\n💰 ماهانه: {format_coins(price)} آریور",reply_markup=keyboard([[button("⚽ مدیریت فوتبال","admin:football")]])); return
        if isinstance(pending, tuple) and pending and pending[0] == "football_add_position":
            if text not in FOOTBALL_POSITIONS:
                await message.answer("❌ پست نامعتبر است. یکی از این‌ها را ارسال کن: دفاع، هافبک، حمله، دروازه بان"); return
            pending_admin[message.from_user.id]=( "football_add_name", text )
            await message.answer("👤 نام بازیکن جدید را ارسال کن:"); return
        if isinstance(pending, tuple) and pending and pending[0] == "football_add_name":
            pos=pending[1]
            if not text or len(text)>80:
                await message.answer("❌ نام بازیکن نامعتبر است."); return
            pending_admin[message.from_user.id]=( "football_add_power", pos, text )
            await message.answer("💪 قدرت بازیکن را ارسال کن (مثلاً 88):"); return
        if isinstance(pending, tuple) and pending and pending[0] == "football_add_power":
            pos,name=pending[1],pending[2]
            try: power=int(text); assert 1<=power<=100
            except Exception:
                await message.answer("❌ قدرت باید عددی بین 1 تا 100 باشد."); return
            pending_admin[message.from_user.id]=( "football_add_price", pos, name, power )
            await message.answer("💰 قیمت ماهانه بازیکن را ارسال کن (حداقل 5,000,000 آریور):"); return
        if isinstance(pending, tuple) and pending and pending[0] == "football_add_price":
            pos,name,power=pending[1],pending[2],pending[3]
            try: price=int(text.replace(",","")); assert price>=5_000_000
            except Exception:
                await message.answer("❌ قیمت باید حداقل 5,000,000 آریور باشد."); return
            try:
                with db() as c:
                    c.execute("INSERT INTO football_players(name,position,power,monthly_price) VALUES(?,?,?,?)",(name,pos,power,price)); c.commit()
            except sqlite3.IntegrityError:
                await message.answer("❌ بازیکنی با این مشخصات/نام قبلاً ثبت شده است."); return
            pending_admin.pop(message.from_user.id,None)
            await message.answer(f"✅ بازیکن جدید اضافه شد.\n👤 {name}\n📌 {pos}\n💪 قدرت: {power}\n💰 ماهانه: {format_coins(price)} آریور",reply_markup=keyboard([[button("⚽ مدیریت فوتبال","admin:football")]])); return
        if pending == "add_amount" and not admin_has_permission(message.from_user.id,"addcoins"):
            pending_admin.pop(message.from_user.id,None); await message.answer("❌ دسترسی این بخش برای شما فعال نیست."); return
        if pending == "remove_user" and not admin_has_permission(message.from_user.id,"removebalance"):
            pending_admin.pop(message.from_user.id,None); await message.answer("❌ دسترسی این بخش برای شما فعال نیست."); return
        if isinstance(pending,tuple) and pending and pending[0] in ("remove_amount","set_price") and not admin_has_permission(message.from_user.id,"prices" if pending[0]=="set_price" else "removebalance"):
            pending_admin.pop(message.from_user.id,None); await message.answer("❌ دسترسی این بخش برای شما فعال نیست."); return
        if pending == "add_admin_user":
            target = message.reply_to_message.from_user if message.reply_to_message and message.reply_to_message.from_user else None
            if target is None:
                target_id = forwarded_user_id(message)
                target_record = get_user_record(target_id) if target_id else None
                if target_record:
                    class _AdminTarget: pass
                    target = _AdminTarget(); target.id = target_id; target.username = target_record[1] or ""; target.full_name = target_record[2] or ""
            if target is None:
                await message.answer("❌ باید روی پیام کاربر ریپلای کنی یا پیام فورواردشده از خود کاربر را بفرستی."); return
            if is_arsin_target(target):
                await message.answer("👑 آرسین خودش مدیر اصلی است."); return
            if is_banned(target.id):
                await message.answer("❌ این کاربر بن است. اول شوشولش را برگردان."); return
            add_admin_user(target, message.from_user.id)
            for _section in ADMIN_SECTIONS:
                set_admin_permission(target.id, _section, True)
            pending_admin.pop(message.from_user.id, None)
            label = f"@{target.username}" if getattr(target, "username", None) else (getattr(target, "full_name", None) or str(target.id))
            await message.answer(f"👑 {label} مدیر ربات شد.\n\nپنل مدیریت برای او فعال شد.")
            try: await bot.send_message(target.id, "👑 شما توسط آرسین مدیر ربات شدید.\n\nبرای باز کردن پنل مدیریت، «پنل» را ارسال کن.", reply_markup=admin_panel_keyboard(target.id))
            except Exception: pass
            return
        if pending == "remove_user":
            target_id=forwarded_user_id(message)
            if target_id is None:
                target_id=resolve_user_id(text)
            if target_id is None:
                await message.answer("❌ کاربر پیدا نشد. آیدی عددی، @username یا پیام خودِ کاربر را فوروارد کن."); return
            pending_admin[message.from_user.id]=( "remove_amount", target_id )
            await message.answer(f"👤 کاربر: {display_name_by_id(target_id)}\n💰 موجودی کیف پول: {format_coins(get_balance(target_id))}\n🏦 بانک: {format_coins(bank_balance(target_id))}\n\n💎 حالا مقدار کسر را ارسال کن:")
            return
        if isinstance(pending, tuple) and pending[0] == "remove_amount":
            try:
                amount=int(text.replace(",",""))
                if amount<=0: raise ValueError
            except ValueError:
                await message.answer("❌ مقدار باید عدد مثبت باشد."); return
            target_id=int(pending[1])
            ok,new_total,wallet,bank=change_total_balance(target_id,-amount)
            if not ok:
                await message.answer(f"❌ موجودی کل کاربر کافی نیست.\n💎 موجودی کل: {format_coins(new_total)}"); return
            pending_admin.pop(message.from_user.id,None)
            await message.answer(f"✅ {format_coins(amount)} آریور کسر شد.\n👤 کاربر: {display_name_by_id(target_id)}\n💰 کیف پول: {format_coins(wallet)}\n🏦 بانک: {format_coins(bank)}\n💎 مجموع: {format_coins(new_total)}")
            try: await bot.send_message(target_id,f"⚠️ مدیر ربات {format_coins(amount)} آریور از موجودی شما کسر کرد.\n💎 موجودی کل جدید: {format_coins(new_total)} آریور")
            except Exception: pass
            return
        if isinstance(pending, tuple) and pending[0] == "set_price":
            try:
                value=int(text.replace(",",""))
                if value<0: raise ValueError
            except ValueError:
                await message.answer("❌ قیمت باید عدد صحیح صفر یا بیشتر باشد."); return
            category,idx=pending[1],int(pending[2])
            try: item=PRICE_CATEGORIES[category][1][idx]
            except Exception:
                pending_admin.pop(message.from_user.id,None); await message.answer("❌ مورد قیمت پیدا نشد."); return
            set_price(price_key_admin(category,item),value)
            pending_admin.pop(message.from_user.id,None)
            await message.answer(f"✅ قیمت «{item}» روی {format_coins(value)} آریور تنظیم شد.",reply_markup=admin_price_category_keyboard(category))
            return
        if pending == "announcement":
            pending_admin[message.from_user.id] = ("announcement_time_choice", text)
            await message.answer("📢 اطلاعیه آماده است.\n\n⏱️ زمان نمایش اطلاعیه را انتخاب کن:", reply_markup=keyboard([
                [button("♾️ نامحدود", "announce_time:unlimited")],
                [button("⏱️ محدود", "announce_time:limited")],
                [button("❌ بستن پنل", "menu:close")],
            ]))
            return
        if isinstance(pending, tuple) and pending[0] == "announcement_time_minutes":
            try:
                minutes=int(text.replace(",",""))
                if minutes <= 0 or minutes > 525600: raise ValueError
            except ValueError:
                await message.answer("❌ زمان باید یک عدد صحیح مثبت به دقیقه باشد.\nمثلاً: 30")
                return
            pending_admin[message.from_user.id] = ("announcement_link_choice", pending[1], minutes)
            await message.answer("📢 زمان تنظیم شد.\n\nآیا اطلاعیه دکمه لینک شیشه‌ای داشته باشد؟", reply_markup=keyboard([
                [button("🔗 با لینک شیشه‌ای", "announce_link:yes")],
                [button("➡️ بدون لینک شیشه‌ای", "announce_link:no")],
                [button("❌ بستن پنل", "menu:close")],
            ]))
            return
        if isinstance(pending, tuple) and pending[0] == "announcement_link_url":
            url = text.strip()
            if not re.match(r"^https?://\S+$", url):
                await message.answer("❌ لینک نامعتبر است. لینک باید با http:// یا https:// شروع شود.")
                return
            announcement_text = pending[1]
            duration_minutes = int(pending[2])
            pending_admin[message.from_user.id] = ("announcement_link_name", announcement_text, url, duration_minutes)
            await message.answer("🔘 حالا اسم دکمه لینک را بفرست:")
            return
        if isinstance(pending, tuple) and pending[0] == "announcement_link_name":
            name = text.strip()
            if not name or len(name) > 64:
                await message.answer("❌ اسم لینک باید بین 1 تا 64 کاراکتر باشد.")
                return
            announcement_text, url, duration_minutes = pending[1], pending[2], int(pending[3])
            pending_admin.pop(message.from_user.id, None)
            await send_announcement(announcement_text, url=url, button_name=name, sender_id=message.from_user.id, duration_minutes=duration_minutes)
            return
        if isinstance(pending, tuple) and pending[0] == "announcement_no_link":
            pending_admin.pop(message.from_user.id, None)
            await send_announcement(pending[1], sender_id=message.from_user.id, duration_minutes=int(pending[2]) if len(pending)>2 else 0)
            return
        if pending == "add_amount":
            try:
                amount = int(text)
                if amount <= 0: raise ValueError
            except ValueError:
                await message.answer("❌ تعداد آریور باید عدد مثبت باشد. 💎"); return
            pending_admin[message.from_user.id] = ("add_user", amount)
            await message.answer("👤 آیدی کاربر را ارسال کن؛ مثلاً @arsin_mo")
            return
        if isinstance(pending, tuple) and pending[0] == "add_user":
            target_username = text if text.startswith("@") else "@" + text
            username = target_username[1:].lower()
            with db() as c:
                row = c.execute("SELECT id FROM users WHERE lower(username)=?", (username,)).fetchone()
            if not row:
                await message.answer("❌ این کاربر هنوز ربات را استارت نکرده یا آیدی او ثبت نشده است. ابتدا /start بزند.")
                return
            amount = pending[1]
            target_id = row[0]
            balance = add_coins(target_id, amount)
            pending_admin.pop(message.from_user.id, None)
            await message.answer(f"✅ به کاربر {target_username} تعداد {format_coins(amount)} 💎 آریور اضافه کردی.\n\n💰 موجودی جدید: {format_coins(balance)} 💎")
            try:
                await bot.send_message(target_id, f"🎁 {format_coins(amount)} 💎 آریور به موجودی شما اضافه شد.\n💰 موجودی آریور‌ها: {format_coins(balance)} 💎")
            except Exception:
                pass
            return
        if pending == "autoreply_keyword":
            if not text: await message.answer("❌ کلمه/عبارت نمی‌تواند خالی باشد."); return
            pending_admin[message.from_user.id]=( "autoreply_response",text ); await message.answer("💬 حالا پاسخ این کلمه/عبارت را بفرست:"); return
        if isinstance(pending,tuple) and pending[0]=="autoreply_response":
            if not add_auto_reply(pending[1],text): await message.answer("⚠️ این کلمه/عبارت قبلاً ثبت شده است."); return
            pending_admin.pop(message.from_user.id,None); await message.answer("✅ پاسخ خودکار ثبت شد.",reply_markup=auto_reply_panel_keyboard()); return
        if pending == "welcome_text":
            if not text: await message.answer("❌ متن خالی است."); return
            set_setting("welcome_text",text); pending_admin.pop(message.from_user.id,None); await message.answer("✅ متن ولکام تغییر کرد.",reply_markup=welcome_panel_keyboard()); return
        if pending == "welcome_btn_text":
            if not text: await message.answer("❌ متن دکمه خالی است."); return
            pending_admin[message.from_user.id]=( "welcome_btn_url",text ); await message.answer("🔗 حالا URL لینک را بفرست:"); return
        if isinstance(pending,tuple) and pending[0]=="welcome_btn_url":
            url=text.strip()
            if not re.match(r"^https?://\S+$",url): await message.answer("❌ لینک نامعتبر است."); return
            items=welcome_buttons(); items.append({"text":pending[1],"url":url}); save_welcome_buttons(items); pending_admin.pop(message.from_user.id,None); await message.answer("✅ لینک شیشه‌ای اضافه شد.",reply_markup=welcome_panel_keyboard()); return
        if pending == "gift_amount":
            try:
                amount = int(text)
                if amount <= 0: raise ValueError
            except ValueError:
                await message.answer("❌ تعداد آریور باید عدد مثبت باشد. 🎁"); return
            pending_admin[message.from_user.id] = ("gift_mode", amount)
            await message.answer("🎁 نوع استفاده از کد هدیه را انتخاب کن:", reply_markup=keyboard([[button("👤 تک کاربر", "giftmode:single"), button("👥 چند کاربر", "giftmode:multi")]]))
            return
        if isinstance(pending, tuple) and pending[0] == "gift_limit":
            try:
                max_uses = int(text.replace(",", ""))
                if max_uses <= 0: raise ValueError
            except ValueError:
                await message.answer("❌ تعداد کاربران باید یک عدد صحیح مثبت باشد."); return
            amount = pending[1]
            pending_admin[message.from_user.id] = ("gift_code", amount, "multi", max_uses)
            await message.answer(f"✅ ظرفیت کد: {format_coins(max_uses)} کاربر\n🔑 حالا کد هدیه را وارد کن:")
            return
        if isinstance(pending, tuple) and pending[0] == "gift_code":
            code = text
            if not code or len(code) > 100 or " " in code:
                await message.answer("❌ کد هدیه نامعتبر است؛ بدون فاصله ارسال کن."); return
            max_uses = int(pending[3]) if len(pending) > 3 else (1 if pending[2] == "single" else 0)
            if not create_gift(code, pending[1], pending[2], max_uses):
                await message.answer("⚠️ این کد هدیه قبلاً ثبت شده است؛ یک کد دیگر انتخاب کن."); return
            mode_label = "تک‌کاربره 👤" if pending[2] == "single" else f"چندکاربره 👥 — ظرفیت {format_coins(max_uses)} نفر"
            pending_admin[message.from_user.id]=( "gift_announce",code,pending[1],mode_label )
            await message.answer(f"✅ کد هدیه {code} با {pending[1]} 💎 آریور ثبت شد.\n🎯 نوع: {mode_label}\n\n📢 کد هدیه به صورت اطلاعیه پخش شود؟",reply_markup=keyboard([[button("✅ بله","giftannounce:yes"),button("❌ خیر","giftannounce:no")]]))
            return
        if message.from_user.id in pending_link:
            state = pending_link[message.from_user.id]
            if isinstance(state, tuple) and state[1] == "url":
                if not text.startswith(("http://", "https://", "@")):
                    await message.answer("❌ لینک نامعتبر است. 🔗 یک لینک t.me یا @username ارسال کن.")
                    return
                slot = state[0]
                link_value = text.strip()
                target = target_from_link(link_value)
                if target is not None:
                    try:
                        chat = await bot.get_chat(target)
                        chat_id = chat.id
                        if not await bot_is_admin(chat_id):
                            await message.answer(
                                f"❌ ربات هنوز در لینک {slot} ادمین نیست. 🤖🛡️\n\n"
                                f"ربات را وارد همان کانال/گروه کن و ادمینش کن، بعد دوباره لینک را ثبت کن.\n"
                            )
                            return
                        set_setting("link" + slot, link_value)
                        set_setting("link" + slot + "_chat_id", str(chat_id))
                        pending_link.pop(message.from_user.id, None)
                        title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)
                        await message.answer(
                            f"✅ لینک {slot} با موفقیت ذخیره شد. 🔗🤖\n\n📌 چت: {title}\n🛡️ وضعیت ربات: ادمین\n\n🎯 از این به بعد عضویت کاربران با Chat ID واقعی و Telegram getChatMember بررسی می‌شود. ✅",
                            parse_mode="HTML",
                        )
                    except Exception as exc:
                        print(f"Auto chat-id lookup failed for {link_value}: {exc}")
                        await message.answer("❌ نتونستم این چت را از روی لینک پیدا کنم. 🤖 ربات باید داخل همان چت باشد و دسترسی لازم داشته باشد. 🔄 اگر لینک خصوصی است، یک پیام از همان چت را برای ربات فوروارد کن تا Chat ID را خودکار پیدا کنم. 📎")
                    return
                if re.match(r"https?://t\.me/\+", link_value):
                    pending_link[message.from_user.id] = (slot, "forward_chat", link_value)
                    await message.answer(f"🔐 این لینک خصوصی است و تلگرام Chat ID را از خود لینک به ربات نمی‌دهد.\n\n📎 یک پیام از همان کانال/گروه را همینجا فوروارد کن.\n🤖 من Chat ID را خودکار پیدا می‌کنم و لینک {slot} را ذخیره می‌کنم.")
                    return
                await message.answer("❌ نتونستم Chat ID این لینک را پیدا کنم. 🔗 لینک را بررسی کن یا یک پیام از همان چت فوروارد کن. 📎")
                return
            if isinstance(state, tuple) and state[1] == "forward_chat":
                slot, _, link_value = state
                forwarded_chat = message.forward_from_chat
                if not forwarded_chat:
                    await message.answer("❌ این پیام از کانال/گروه قابل تشخیص نیست. 📎 یک پیام را مستقیم از همان چت فوروارد کن.")
                    return
                chat_id = forwarded_chat.id
                if not await bot_is_admin(chat_id):
                    await message.answer(
                        f"❌ ربات در این چت ادمین نیست. 🤖🛡️\n\n"
                        f"اول ربات را داخل همان کانال/گروه ادمین کن و سپس پیام را دوباره فوروارد کن.\n"
                    )
                    return
                set_setting("link" + slot, link_value)
                set_setting("link" + slot + "_chat_id", str(chat_id))
                pending_link.pop(message.from_user.id, None)
                title = getattr(forwarded_chat, "title", None) or getattr(forwarded_chat, "username", None) or str(chat_id)
                await message.answer(
                    f"✅ لینک {slot} ذخیره شد. 🔗🤖\n\n📌 چت: {title}\n🛡️ وضعیت ربات: ادمین\n\n🎯 بررسی عضویت از این به بعد مستقیم با Chat ID واقعی انجام می‌شود. ✅",
                    parse_mode="HTML",
                )
                return
        return

    # 👑 دستورات مستقیم مدیریت آرسین با ریپلای
    if is_arsin:
        if text == "افزودن شوشول":
            if not message.reply_to_message or not message.reply_to_message.from_user:
                await message.reply("❌ برای افزودن شوشول باید روی پیام کاربر موردنظر ریپلای کنی."); return
            target = message.reply_to_message.from_user
            if target.id == message.from_user.id or is_arsin_target(target):
                await message.reply("👑 آرسین مدیر اصلی است و نیازی به افزودن ندارد."); return
            if is_banned(target.id):
                await message.reply("❌ این کاربر بن است. اول شوشولش را برگردان."); return
            add_admin_user(target, message.from_user.id)
            for _section in ADMIN_SECTIONS:
                set_admin_permission(target.id, _section, True)
            label = f"@{target.username}" if target.username else target.full_name
            await message.reply(f"👑 {label} از این لحظه مدیر ربات است. پنل ارسین برای او فعال شد.")
            try:
                await bot.send_message(target.id, "👑 شما توسط آرسین مدیر ربات شدید.\n\nبرای باز کردن پنل مدیریت، «پنل» را ارسال کن.", reply_markup=admin_panel_keyboard(target.id))
            except Exception: pass
            return
        if text == "خطنه":
            if not message.reply_to_message or not message.reply_to_message.from_user:
                await message.reply("❌ برای خطنه باید روی پیام کاربر موردنظر ریپلای کنی."); return
            target=message.reply_to_message.from_user
            if target.id == message.from_user.id or is_arsin_user(target):
                await message.reply("❌ آرسین قابل بن شدن نیست."); return
            ok,total=ban_user(target.id,message.from_user.id)
            if not ok:
                await message.reply("⚠️ این کاربر از قبل توسط مدیر ربات بریده شده است."); return
            label=f"@{target.username}" if target.username else target.full_name
            await message.reply(f"✂️ شوشول {label} کامل بریده شد و دیگه جایی در ربات نداره.")
            try: await bot.send_message(target.id,"✂️ شوشول شما توسط مدیر ربات کامل بریده شده است و دیگر جایی در ربات ندارید.")
            except Exception: pass
            return
        if text == "شوشولشو برگردون":
            if not message.reply_to_message or not message.reply_to_message.from_user:
                await message.reply("❌ برای برگرداندن باید روی پیام کاربر موردنظر ریپلای کنی."); return
            target=message.reply_to_message.from_user
            ok,total=unban_user(target.id)
            if not ok:
                await message.reply("❌ این کاربر در لیست بن‌شده‌ها نیست."); return
            await message.reply(f"✅ شوشول {display_name_by_id(target.id)} برگشت داده شد.\n💎 کل موجودی قبلی: {format_coins(total)} آریور\n🤖 ربات دوباره برای او فعال است.")
            try: await bot.send_message(target.id,f"✅ شوشول شما توسط مدیر ربات برگردانده شد.\n💎 کل موجودی قبلی شما: {format_coins(total)} آریور\n🤖 ربات دوباره برای شما فعال است.")
            except Exception: pass
            return
        admin_add = re.fullmatch(r"افزایش موجودی\s+([0-9][0-9,]*)", text)
        admin_remove = re.fullmatch(r"شوشولشو ببر\s+([0-9][0-9,]*)", text)
        if admin_add or admin_remove:
            if not message.reply_to_message or not message.reply_to_message.from_user:
                await message.reply("❌ برای این دستور باید روی پیام کاربر موردنظر ریپلای کنی. 👤↩️")
                return
            try:
                amount = int((admin_add or admin_remove).group(1).replace(",", ""))
                if amount <= 0:
                    raise ValueError
            except ValueError:
                await message.reply("❌ مقدار آریور باید یک عدد مثبت باشد. 💎")
                return
            target = message.reply_to_message.from_user
            if target.id == message.from_user.id:
                await message.reply("❌ نمی‌تونی موجودی خودت رو با این دستور تغییر بدی. 👑")
                return
            if admin_add:
                new_balance = add_coins(target.id, amount)
                action_text = f"➕ {format_coins(amount)} آریور به موجودی"
                try:
                    await bot.send_message(target.id, f"🎁 آرسین {format_coins(amount)} آریور به موجودی شما اضافه کرد. 💎\n💰 موجودی جدید: {format_coins(new_balance)} آریور")
                except Exception:
                    pass
            else:
                wallet = get_balance(target.id)
                bank = bank_balance(target.id)
                blocked = bank_blocked_amount(target.id)
                total_available = wallet + bank + blocked
                if total_available < amount:
                    await message.reply(
                        f"❌ موجودی کل {label_player({'username': target.username or '', 'id': target.id})} کافی نیست. 💎\n"
                        f"💰 کیف پول: {format_coins(wallet)} آریور\n"
                        f"🏦 بانک: {format_coins(bank)} آریور\n"
                        f"🔒 بلوکه‌شده: {format_coins(blocked)} آریور\n"
                        f"💎 مجموع: {format_coins(total_available)} آریور"
                    )
                    return

                remaining = amount

                # First deduct from the normal wallet.
                wallet_deduct = min(wallet, remaining)
                if wallet_deduct:
                    add_coins(target.id, -wallet_deduct)
                    remaining -= wallet_deduct

                # Then deduct any remainder from the available bank balance.
                bank_deduct = min(bank, remaining)
                if bank_deduct:
                    with db() as c:
                        c.execute("UPDATE bank SET balance=balance-? WHERE user_id=?",(bank_deduct,target.id))
                        c.commit()
                    remaining -= bank_deduct

                # Finally deduct from currently blocked bank funds.
                blocked_deduct = 0
                if remaining:
                    blocked_deduct = deduct_blocked_bank(target.id, remaining)
                    remaining -= blocked_deduct

                new_balance = get_balance(target.id)
                action_text = f"➖ {format_coins(amount)} آریور از موجودی کل"
                try:
                    await bot.send_message(target.id, f"⚠️ آرسین {format_coins(amount)} آریور از موجودی شما کسر کرد. 💎\n💰 موجودی جدید: {format_coins(new_balance)} آریور")
                except Exception:
                    pass
            target_label = f"@{target.username}" if target.username else display_name_by_id(target.id)
            await message.reply(f"✅ {action_text} {target_label} انجام شد. 💎\n💰 موجودی جدید: {format_coins(new_balance)} آریور")
            return


    # 👑 ریست کامل حساب با ریپلای — فقط آرسین
    if is_arsin and text == "ریست":
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply("❌ برای ریست باید روی پیام کاربر موردنظر ریپلای کنی. 👤↩️")
            return
        target=message.reply_to_message.from_user
        if target.id==message.from_user.id:
            await message.reply("❌ آرسین نمی‌تواند حساب خودش را ریست کند. 👑")
            return
        reset_user_data(target.id)
        await message.reply(f"♻️ حساب {mention_by_id(target.id)} کامل ریست شد.\n\n💎 موجودی: 0 آریور\n🎒 تمام آیتم‌ها: 0\n⭐ لول‌ها و شانس: 0\n📊 آمار و دستاوردها: 0\n👑 خاله و تعداد خاله‌بازی: 0\n🎁 وضعیت روزانه و مأموریت‌ها: از اول شروع شد.",parse_mode="HTML")
        try:
            await bot.send_message(target.id,"♻️ آرسین حساب شما را کامل ریست کرد.\n\n💎 موجودی: 0 آریور\n🎒 آیتم‌ها: 0\n📊 آمار و دستاوردها: 0\n👑 خاله: انتخاب نشده")
        except Exception:
            pass
        return

    # 👑 خاله‌بازی — روابط کاملاً دوطرفه و یک‌به‌یک
    if text == "انتخاب خاله":
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply("❌ برای انتخاب خاله باید روی پیام فرد موردنظر ریپلای کنی. 💧👸")
            return
        target=message.reply_to_message.from_user
        uid=int(message.from_user.id); target_id=int(target.id)
        if target_id==uid:
            await message.reply("❌ خودت نمی‌تونی خاله خودت باشی. 💧👸")
            return

        # اگر هرکدام از دو نفر در یک رابطه باشند، انتخاب خاله جدید ممنوع است.
        if aunt_pair_for(uid):
            await message.reply("⚠️ شما قبلاً خاله دارید. برای پایان این رابطه از «تعویض خاله» یا «حذف خاله» استفاده کن. 💧👸")
            return
        if aunt_pair_for(target_id):
            await message.reply(f"❌ {mention_by_id(target_id)} در حال حاضر خاله یک نفر دیگر است و نمی‌تواند خاله شما شود. 💧👸",parse_mode="HTML")
            return

        remember(target)
        set_aunt_pair(uid,target_id)
        await message.reply(f"💧👸 شما {mention_by_id(target_id)} را برای خاله بازی انتخاب کردید.\n\nاز این لحظه شما خاله یکدیگر هستید و هر دو می‌توانید «خاله بازی» بفرستید. 💧👸",parse_mode="HTML")
        return

    if text == "خاله":
        rec=aunt_record(message.from_user.id)
        if not rec["aunt_id"]:
            await message.reply("❌ ابتدا با دستور «انتخاب خاله» یک خاله را برای خاله بازی انتخاب کن. 💧👸")
            return
        if message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.id!=rec["aunt_id"]:
            await message.reply(f"⚠️ شما قبلاً {mention_by_id(rec['aunt_id'])} را برای خاله بازی انتخاب کرده‌اید. 💧👸",parse_mode="HTML")
            return
        await message.reply(f"💧👸 خاله فعلی شما {mention_by_id(rec['aunt_id'])} است.",parse_mode="HTML")
        return

    if text == "تعویض خاله":
        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply("❌ برای تعویض خاله باید روی فرد جدید ریپلای کنی. 💧👸")
            return
        target=message.reply_to_message.from_user
        uid=int(message.from_user.id); target_id=int(target.id)
        if target_id==uid:
            await message.reply("❌ خودت نمی‌تونی خاله خودت باشی. 💧👸")
            return
        current=aunt_pair_for(uid)
        if not current:
            await message.reply("❌ شما در حال حاضر خاله ندارید؛ اول «انتخاب خاله» را بزن. 💧👸")
            return
        if target_id==current:
            await message.reply(f"ℹ️ {mention_by_id(target_id)} همین الان خاله شماست. 💧👸",parse_mode="HTML")
            return
        if aunt_pair_for(target_id):
            await message.reply(f"❌ {mention_by_id(target_id)} در حال حاضر خاله یک نفر دیگر است و نمی‌تواند خاله جدید شما شود. 💧👸",parse_mode="HTML")
            return
        cost=3000
        if get_balance(uid)<cost:
            await message.reply(f"❌ برای تعویض خاله {format_coins(cost)} آریور لازم داری. 💎")
            return
        remember(target)
        # اول رابطه قبلی A-B کامل قطع می‌شود؛ سپس A-C به‌صورت دوطرفه ساخته می‌شود.
        clear_aunt_pair(uid)
        add_coins(uid,-cost)
        set_aunt_pair(uid,target_id)
        await message.reply(f"🔄💧👸 خاله شما به {mention_by_id(target_id)} تغییر کرد.\n💎 هزینه تعویض: {format_coins(cost)} آریور\n{balance_display(uid)}",parse_mode="HTML")
        return

    if text == "حذف خاله":
        current=aunt_pair_for(message.from_user.id)
        if not current:
            await message.reply("ℹ️ شما در حال حاضر خاله‌ای ندارید. 💧")
            return
        clear_aunt_pair(message.from_user.id)
        await message.reply(f"✅ رابطه خاله‌ای شما با {mention_by_id(current)} حذف شد.\n💧 از این لحظه هیچ‌کدام خاله دیگری نیستید و برای خاله بازی باید دوباره «انتخاب خاله» کنید.",parse_mode="HTML")
        return

    if text in ("خاله بازی","خاله‌بازی"):
        aunt_id=aunt_pair_for(message.from_user.id)
        if not aunt_id:
            # اگر رکورد قدیمی یک‌طرفه/خراب مانده باشد، پاکش می‌کنیم تا بازی با رابطه ناقص انجام نشود.
            rec=aunt_record(message.from_user.id)
            if rec.get("aunt_id"):
                clear_aunt_pair(message.from_user.id)
            await message.reply("❌ ابتدا با دستور «انتخاب خاله» یک خاله رو برای خاله بازی انتخاب کن. 💧👸")
            return
        initiator_remaining=aunt_game_remaining(message.from_user.id)
        if initiator_remaining>0:
            mins,secs=divmod(initiator_remaining,60)
            await message.reply(f"⏳ خاله‌بازی هنوز برای شما آماده نیست! 👑\n🕐 {mins} دقیقه و {secs} ثانیه مونده.\n💧 هر ۲۵ دقیقه یک بار می‌تونی خاله‌بازی کنی.")
            return
        aunt_remaining=aunt_game_remaining(aunt_id)
        if aunt_remaining>0:
            mins,secs=divmod(aunt_remaining,60)
            await message.reply(f"⏳ {mention_by_id(aunt_id)} هنوز خاله‌بازی‌اش آماده نیست. 👑\n🕐 {mins} دقیقه و {secs} ثانیه مونده.\n💧 تا آماده شدن دوباره او صبر کنید.",parse_mode="HTML")
            return
        reward=5000
        add_coins(message.from_user.id,reward)
        add_coins(aunt_id,reward)
        count=increment_aunt_games(message.from_user.id,True)
        aunt_count=increment_aunt_games(aunt_id,True)
        try:
            await bot.send_message(aunt_id,f"💧👸 {mention_by_id(message.from_user.id)} با شما خاله بازی کرد.\n💎 ۵,۰۰۰ آریور به شما تعلق گرفت.\n👑 تعداد خاله‌بازی‌های شما: {aunt_count}",parse_mode="HTML")
        except Exception:
            pass
        await message.reply(f"💧👸 {mention_by_id(message.from_user.id)} با {mention_by_id(aunt_id)} رفتن پشت گپ و خاله بازی کردن.\n\n💎 به هرکدومشون {format_coins(reward)} آریور تعلق گرفت.\n👑 تعداد خاله‌بازی‌های شما: {count}",parse_mode="HTML")
        return

    # ⚽ Football commands
    if text in ("مدیریت تیم", "مدیریت باشگاه", "تیم من", "ساخت تیم"):
        uid=message.from_user.id
        if football_team(uid):
            try:
                sent=await bot.send_message(uid,football_team_text(uid),reply_markup=football_team_keyboard(uid))
                mark_menu_activity(sent, message.from_user.id)
                if message.chat.type != "private": await message.reply("⚽ پنل مدیریت تیم به پیویت ارسال شد.")
            except Exception:
                await message.reply("❌ اول پیوی ربات را باز کن و /start بزن.")
        else:
            await message.reply("⚽ هنوز تیم نداری. از منو روی «⚽ ساخت تیم» بزن.")
        return

    if message.from_user.id in football_name_pending:
        if not text:
            await message.reply("❌ نام باشگاه نمی‌تواند خالی باشد."); return
        if len(text)>40:
            await message.reply("❌ نام باشگاه حداکثر ۴۰ کاراکتر باشد."); return
        norm=normalize_club_name(text)
        if not norm:
            await message.reply("❌ نام باشگاه نامعتبر است."); return
        with db() as c:
            exists=c.execute("SELECT 1 FROM football_teams WHERE club_name_norm=?",(norm,)).fetchone()
            mine=c.execute("SELECT 1 FROM football_teams WHERE user_id=?",(message.from_user.id,)).fetchone()
            if mine:
                football_name_pending.pop(message.from_user.id,None)
                await message.reply("⚽ شما از قبل تیم دارید."); return
            if exists:
                await message.reply("❌ این نام باشگاه قبلاً انتخاب شده است. یک نام دیگر بفرست."); return
            now=int(time.time())
            try:
                c.execute("INSERT INTO football_teams(user_id,club_name,club_name_norm,created_at) VALUES(?,?,?,?)",(message.from_user.id,text,norm,now))
                c.commit()
            except sqlite3.IntegrityError:
                await message.reply("❌ این نام یا حساب هم‌اکنون ثبت شده است؛ یک نام دیگر امتحان کن."); return
        football_name_pending.pop(message.from_user.id,None)
        await message.reply(f"🎉 باشگاه با موفقیت ساخته شد!\n\n⚽ نام تیم: {text}\n💎 هزینه ساخت: {format_coins(FOOTBALL_TEAM_CREATION_COST)} آریور\n\nحالا از «مدیریت تیم» می‌توانی مربی و بازیکن بخری و ترکیبت را بسازی.",reply_markup=football_team_keyboard(message.from_user.id))
        return

    # User commands work in private and group chats.
    if text in ("کسب و کار","کسب‌وکار","business"):
        stores=user_mall_stores(message.from_user.id)
        if not stores:
            await message.reply("🏢 کسب و کار\n\n❌ ابتدا یک مغازه در پاساژ بخرید و حداقل یک پک کامل داخل آن قرار دهید.")
        else:
            lines=["🏢 کسب و کار\n"]
            for sid,area,purchase_price,purchased_at,last_income_at in stores:
                packs=business_pack_count(sid,area); daily=store_daily_income(sid,area)
                lines.append(f"🏬 مغازه #{sid} — {area} متر\n📦 پک کامل: {packs}\n💵 درآمد روزانه: {format_coins(daily)} آریور")
            lines.append(f"\n💰 مجموع درآمد روزانه: {format_coins(business_total_daily_income(message.from_user.id))} آریور")
            lines.append("🏦 درآمد هر ۲۴ ساعت خودکار به بانک واریز می‌شود.")
            await message.reply("\n\n".join(lines))
        return
    if text in ("منو","menu"):
        if message.chat.type in ("group","supergroup"):
            sent_menu = await message.answer("📋 منو را کجا می‌خواهی دریافت کنی؟",reply_markup=menu_share_keyboard())
            mark_menu_activity(sent_menu)
        else:
            sent_menu = await message.answer(profile_text(message.from_user.id),reply_markup=user_menu_keyboard(message.from_user.id))
            mark_menu_activity(sent_menu, message.from_user.id)
        return
    if text in ("راهنما","راهنما آریو"):
        await message.answer(user_help_text(),reply_markup=help_categories_keyboard()); return
    if text in ("جایزه روزانه","جایزه روزانه 🎁"):
        ok,st,remain,reward=claim_daily_box(message.from_user.id)
        if not ok: await message.reply(f"⏳ جایزه روزانه‌ات هنوز آماده نیست؛ حدود {max(1,remain//3600)} ساعت دیگر. 🎁"); return
        await message.reply(f"🎁 جعبه روزانه باز شد!\n💎 {format_coins(reward)} آریور گرفتی.\n🔥 استریک: {st['streak']} روز"); return
    if text in ("استریک","استریک روزانه"):
        st=get_daily_state(message.from_user.id); await message.reply(f"🔥 استریک روزانه: {st['streak']} روز\n🎁 جایزه جعبه روزانه با ادامه استریک بیشتر می‌شود."); return
    if text in ("ماموریت ها","ماموریت‌ها","ماموریت"):
        rows=mission_rows(message.from_user.id); await message.reply("🎯 ماموریت‌های امروز:\n\n"+"\n".join(f"{'✅' if claimed else '⬜'} {mission_label(typ)} — {progress}/{target} — 🎁 {format_coins(reward)}" for typ,target,progress,reward,claimed in rows)); return
    m=re.fullmatch(r"واریز\s+([0-9,]+)",text)
    if m:
        amount=int(m.group(1).replace(',','')); ok,b=bank_deposit(message.from_user.id,amount); await message.reply(f"{'✅ واریز شد.' if ok else '❌ موجودی کافی نیست.'} 🏦\n💳 بانک: {format_coins(b)} آریور"); return
    m=re.fullmatch(r"برداشت\s+([0-9,]+)",text)
    if m:
        amount=int(m.group(1).replace(',','')); ok,b=bank_withdraw(message.from_user.id,amount); await message.reply(f"{'✅ برداشت شد.' if ok else '❌ موجودی بانک کافی نیست.'} 🏦\n💳 بانک: {format_coins(b)} آریور"); return
    if text in ("بانک","بانک آریور"):
        await message.reply(f"🏦 موجودی بانک: {format_coins(bank_balance(message.from_user.id))} آریور 💎\n🔒 بلوکه‌شده: {format_coins(bank_blocked_amount(message.from_user.id))} آریور"); return
    if text in ("آمار","آمار کامل","stats"):
        st=player_stats(message.from_user.id); rank,points=player_rank(message.from_user.id); wr=(st["wins"]*100//st["games"]) if st["games"] else 0
        await message.reply(f"📊 آمار کامل\n🏆 رنک: {rank}\n⭐ امتیاز: {points}\n🎮 بازی: {st['games']}\n🏆 برد: {st['wins']}\n💔 باخت: {st['losses']}\n🤝 مساوی: {st['draws']}\n📈 درصد برد: {wr}%\n💰 بهترین جایزه: {format_coins(st['best_win'])} آریور\n🧠 XP: {st['xp']}"); return
    if text in ("دستاوردها","دستاورد ها"):
        owned=set(achievements_list(message.from_user.id)); await message.reply("🏅 دستاوردها\n\n"+"\n".join(f"{'✅' if code in owned else '🔒'} {name} — {desc}" for code,(name,desc,target) in ACHIEVEMENT_DEFS.items())); return
    if text in ("رنک","rank"):
        rank,points=player_rank(message.from_user.id); await message.reply(f"🏆 رنک شما: {rank}\n⭐ امتیاز: {points}"); return
    if text in ("آیتم‌ها","آیتم ها","اینونتوری"):
        await message.reply(inventory_text(message.from_user.id)); return
    if text in ("حیوانات من","حیوانات","پت من"):
        uid=message.from_user.id; active=active_pet(uid); owned=[p for p in PETS if inventory_qty(uid,p)>0]
        await message.reply("🐾 حیوانات من\n\n"+"\n".join(f"{'✅' if active==p else '⚪'} {p} — {pet_effect_description(p)}" for p in owned) if owned else "🐾 هنوز حیوانی نداری.")
        return
    if text in ("فروشگاه حیوانات","پت شاپ","pet shop"):
        await message.answer(pet_shop_text(message.from_user.id),reply_markup=pet_shop_keyboard(message.from_user.id)); return
    if text in ("فروشگاه سیاه","فروشگاه مبارزه"):
        global _black_shop_view_uid
        _black_shop_view_uid=message.from_user.id
        await message.answer(black_shop_text(),reply_markup=black_shop_keyboard()); return
    if text in ("قهرمان","قهرمانی","champion"):
        ch=champion_record(message.from_user.id); await message.reply(f"👑 قهرمان\n\n🏆 قهرمانی‌ها: {ch['titles']}\n⚔️ بردهای قهرمانی: {ch['wins']}\n💪 بیشترین قدرت ثبت‌شده: {ch['best_power']}"); return
    if text in ("فروشگاه سیاه","فروشگاه مبارزه"):
        await message.answer(black_shop_text(),reply_markup=black_shop_keyboard()); return
    if text in ("قهرمان","قهرمانی","champion"):
        ch=champion_record(message.from_user.id); await message.reply(f"👑 قهرمان\n\n🏆 تعداد قهرمانی: {ch['titles']}\n⚔️ بردهای قهرمانی: {ch['wins']}\n💪 بیشترین قدرت ثبت‌شده: {ch['best_power']}"); return
    if text in ("فروشگاه","shop"):
        await message.answer(normal_shop_text(message.from_user.id), reply_markup=normal_shop_keyboard(message.from_user.id)); return
    if text in ("پولدارا","پولدارها","پولدار ترین ها","پولدارترین‌ها"):
        rows=leaderboard_wealth(5); lines=["💰 پولدارای بازی\n"]
        for i,(uid,username,full_name,wealth) in enumerate(rows,1):
            name='@'+username if username else (full_name or display_name_by_id(uid))
            lines.append(f"{i}. {name} — 💎 {format_coins(wealth)} آریور")
        await message.reply("\n".join(lines)); return
    if text in ("رتبه بندی","رتبه‌بندی","لیدربورد"):
        rows=leaderboard(); await message.reply("🏆 رتبه‌بندی:\n\n"+"\n".join(f"{i}. {'@'+u if u else display_name_by_id(uid)} — 💎 {format_coins(b)} — ⭐ {lv}" for i,(uid,u,b,lv,l,e) in enumerate(rows,1))); return
    if text in ("تاریخچه","تاریخچه آریور"):
        rows=recent_transactions(message.from_user.id); await message.reply("📜 آخرین تراکنش‌ها:\n\n"+"\n".join(f"• {k}: {('+' if a>0 else '')}{format_coins(a)} 💎 | {format_coins(b)}" for k,a,b,n,t in rows) or "📜 هنوز تراکنشی نیست."); return
    m=re.fullmatch(r"فروش\s+([A-Za-z0-9]+)",text)
    if m:
        ok,why,price,qty,item=sell_business_item_by_code(message.from_user.id,m.group(1))
        if ok:
            await message.reply(f"✅ {item} با کد {m.group(1).upper()} فروخته شد.\n💰 مبلغ دریافتی: {format_coins(price)} آریور\n🎒 تعداد فروخته‌شده: {qty}")
        elif why=="code":
            await message.reply("❌ کد آیتم نامعتبر است. کد را از بخش «لوازم کسب و کار» ببین.")
        else:
            await message.reply("❌ این آیتم را در لوازم کسب و کارت نداری.")
        return
    m=re.fullmatch(r"ترید\s+([0-9][0-9,]*)",text)
    if m:
        amount=int(m.group(1).replace(",","")); net,r,status=do_trade(message.from_user.id,amount)
        if status=="amount": await message.reply("❌ مبلغ ترید باید بیشتر از صفر باشد. 🎲💎"); return
        if status=="funds": await message.reply("❌ موجودی آریورت برای این ترید کافی نیست. 💰"); return
        if status=="minimum": await message.reply("❌ مبلغ ترید باید حداقل 2 آریور باشد و سود/ضرر حداقل یک‌سوم مبلغ ترید است. 🎲💎"); return
        result=f"🟢 {format_coins(net)} آریور سود کردی! 📈" if net>0 else f"🔴 {format_coins(abs(net))} آریور ضرر کردی. 📉"
        await message.reply(f"🎲 ترید {format_coins(amount)} آریور انجام شد!\n\n{result}\n{balance_display(message.from_user.id)}"); return
    if text=="ارتقای لول":
        ok,r,c=upgrade_level(message.from_user.id); await message.reply(f"🎉 لول ارتقا یافت! ⭐\n💸 {format_coins(c)} آریور کسر شد." if ok else f"❌ {format_coins(c)} آریور برای ارتقا لازم داری. 💰"); return
    if text in ("ارتقای لول شانس","ارتقای لول تجربه"):
        stat="luck_level" if "شانس" in text else "exp_level"; ok,r,c,why=upgrade_stat(message.from_user.id,stat)
        if ok: await message.reply(f"🎉 ارتقای {'🍀 شانس' if stat=='luck_level' else '🧠 تجربه'} انجام شد!\n💸 {format_coins(c)} آریور کسر شد.")
        elif why=="max": await message.reply("🏆 این لول به 10 رسیده است.")
        else: await message.reply(f"❌ {format_coins(c)} آریور برای این ارتقا لازم داری. 💰")
        return
    direct_transfer=re.fullmatch(r"انتقال\s+([0-9,]+)",text)
    if direct_transfer and message.reply_to_message:
        try: amount=int(direct_transfer.group(1).replace(",","")); assert amount>0
        except Exception: await message.reply("❌ مقدار انتقال باید عدد مثبت باشد. 💸"); return
        target=message.reply_to_message.from_user
        if not target or target.id==message.from_user.id: await message.reply("❌ انتقال به خودت ممکن نیست. 🙅"); return
        if is_arsin_target(target):
            await message.reply("👑 آرسین از عملیات روی حسابش مصون است. 🛡️")
            return
        if get_balance(message.from_user.id)<amount: await message.reply("❌ موجودی آریور کافی نیست. 💰"); return
        transfer_pending[message.from_user.id]=("confirm",amount,target.id,target.username or "")
        label='@'+target.username if target.username else display_name_by_id(target.id)
        await message.reply(f"⚠️ تأیید انتقال\n\n💸 مبلغ: {format_coins(amount)} آریور\n👤 گیرنده: {label}\n\nتأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید انتقال",f"transfer:confirm:{message.from_user.id}"),button("❌ لغو",f"transfer:cancel:{message.from_user.id}")]])); return

    if message.from_user.id in transfer_pending:
        state=transfer_pending[message.from_user.id]
        if state=="amount":
            try: amount=int(text.replace(",","")); assert amount>0
            except Exception: await message.reply("❌ مقدار انتقال باید عدد مثبت باشد. 💸"); return
            transfer_pending[message.from_user.id]=amount; await message.reply("👤 حالا روی پیام فرد موردنظر ریپلای کن. 💸"); return
        if isinstance(state,int) and message.reply_to_message:
            target=message.reply_to_message.from_user
            if not target or target.id==message.from_user.id: await message.reply("❌ انتقال به خودت ممکن نیست. 🙅"); return
            if is_arsin_target(target):
                await message.reply("👑 آرسین از عملیات روی حسابش مصون است. 🛡️")
                transfer_pending.pop(message.from_user.id,None)
                return
            if get_balance(message.from_user.id)<state: await message.reply("❌ موجودی آریور کافی نیست. 💰"); transfer_pending.pop(message.from_user.id,None); return
            transfer_pending[message.from_user.id]=("confirm",state,target.id,target.username or "")
            label='@'+target.username if target.username else display_name_by_id(target.id)
            await message.reply(f"⚠️ تأیید انتقال\n\n💸 مبلغ: {format_coins(state)} آریور\n👤 گیرنده: {label}\n\nتأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید انتقال",f"transfer:confirm:{message.from_user.id}"),button("❌ لغو",f"transfer:cancel:{message.from_user.id}")]])); return

    if text in ("استریک","streak"):
        await message.reply(streak_text(message.from_user.id)); return
    if text in ("آمار من","آمار","stats"):
        st=player_stats(message.from_user.id); rank,points=player_rank(message.from_user.id); wr=(st["wins"]*100//st["games"]) if st["games"] else 0
        await message.reply(f"📊 آمار کامل\n🏆 رنک: {rank}\n⭐ امتیاز: {points}\n🎮 بازی: {st['games']}\n🏆 برد: {st['wins']}\n💔 باخت: {st['losses']}\n🤝 مساوی: {st['draws']}\n📈 درصد برد: {wr}%\n💰 بهترین جایزه: {format_coins(st['best_win'])} آریور\n🧠 XP: {st['xp']}\n🔥 استریک برد: {st['win_streak']}\n👑 بهترین استریک: {st['best_streak']}"); return
    if text in ("رنک","rank"):
        rank,points=player_rank(message.from_user.id); await message.reply(f"🥇 رنک شما: {rank}\n⭐ امتیاز: {points}"); return
    if text in ("لیدربورد برد","بردها"):
        rows=leaderboard_wins(); await message.reply("🏆 لیدربورد برد\n\n"+"\n".join(f"{i}. {'@'+u if u else 'بازیکن'} — 🏆 {w} برد" for i,(uid,u,w,g,p) in enumerate(rows,1))); return
    if text in ("لیدربورد امتیاز","امتیازات"):
        rows=leaderboard_points(); await message.reply("⭐ لیدربورد امتیاز\n\n"+"\n".join(f"{i}. {'@'+u if u else 'بازیکن'} — ⭐ {p}" for i,(uid,u,p,w,g,bs) in enumerate(rows,1))); return
    if text in ("آیتم‌ها","آیتم ها","اینونتوری"):
        await message.reply(inventory_text(message.from_user.id)); return
    if text in ("حیوانات من","حیوانات","پت من"):
        uid=message.from_user.id; active=active_pet(uid); owned=[p for p in PETS if inventory_qty(uid,p)>0]
        await message.reply("🐾 حیوانات من\n\n"+"\n".join(f"{'✅' if active==p else '⚪'} {p} — {pet_effect_description(p)}" for p in owned) if owned else "🐾 هنوز حیوانی نداری.")
        return
    if text in ("فروشگاه حیوانات","پت شاپ","pet shop"):
        await message.answer(pet_shop_text(message.from_user.id),reply_markup=pet_shop_keyboard(message.from_user.id)); return
    if text in ("فروشگاه سیاه","فروشگاه مبارزه"):
        await message.answer(black_shop_text(),reply_markup=black_shop_keyboard()); return
    if text in ("قهرمان","قهرمانی","champion"):
        ch=champion_record(message.from_user.id); await message.reply(f"👑 قهرمان\n\n🏆 قهرمانی‌ها: {ch['titles']}\n⚔️ بردهای قهرمانی: {ch['wins']}\n💪 بیشترین قدرت ثبت‌شده: {ch['best_power']}"); return
    am=re.fullmatch(r"حراج آیتم\s+(.+?)\s+(\d+)\s+([0-9][0-9,]*)\s+(\d+)",text)
    if am:
        item=am.group(1).strip(); qty=int(am.group(2)); start_price=int(am.group(3).replace(',','')); minutes=int(am.group(4))
        aid,status=create_auction(message.from_user.id,item,qty,start_price,minutes)
        if status!='ok': await message.reply("❌ آیتم/تعداد/قیمت/مدت نامعتبر است یا موجودی کافی نیست. 🎒"); return
        sent=await message.answer(f"🔨 حراج واقعی آیتم #{aid} ساخته شد!\n\n🎁 آیتم: {item} × {qty}\n💎 قیمت شروع: {format_coins(start_price)} آریور\n📈 حداقل افزایش هر پیشنهاد: {format_coins(max(1,start_price//10))}\n⏳ مدت: {minutes} دقیقه\n\nفرمت پیشنهاد: «پیشنهاد حراج {aid} مبلغ»\nمثال: «پیشنهاد حراج {aid} {start_price + max(1,start_price//10)}»")
        asyncio.create_task(auction_expiry_task(aid)); return
    if text in ("حراج","حراج‌ها","حراج ها"):
        rows=active_auctions();
        lines=[]
        for aid,seller,item,qty,start,current,bidder,inc,end in rows:
            left=max(0,end-int(time.time())); price=current if current else start
            lines.append(f"🔨 #{aid} — {item} × {qty}\n💎 قیمت فعلی: {format_coins(price)} | افزایش بعدی: +{format_coins(inc)}\n⏳ {left//60}دقیقه {left%60}ثانیه | 👤 فروشنده: {display_name_by_id(seller)}")
        await message.reply("🔨 حراج‌های فعال\n\n"+("\n\n".join(lines) if lines else "حراج فعالی نیست.")); return
    bm=re.fullmatch(r"پیشنهاد حراج\s+(\d+)\s+([0-9][0-9,]*)",text)
    if bm:
        aid=int(bm.group(1)); amount=int(bm.group(2).replace(',','')); ok,why,val=place_auction_bid(aid,message.from_user.id,amount)
        if ok:
            a=auction_get(aid); await message.reply(f"✅ پیشنهاد ثبت شد! 🔨\n💎 پیشنهاد شما: {format_coins(amount)} آریور\n🎁 {a['item']} × {a['quantity']}\n⏳ زمان باقی‌مانده: {max(0,a['end_at']-int(time.time()))//60} دقیقه")
        elif why=='minimum': await message.reply(f"❌ پیشنهاد باید حداقل {format_coins(val)} آریور باشد. 📈")
        elif why=='funds': await message.reply("❌ موجودی کیف پول کافی نیست. 💎")
        elif why=='seller': await message.reply("❌ فروشنده نمی‌تواند روی حراج خودش پیشنهاد بدهد. 😄")
        else: await message.reply("❌ این حراج بسته یا تمام شده است. 🔨")
        return

    cm=re.fullmatch(r"مبارزه\s+([0-9][0-9,]*)",text)
    if cm and message.chat.type in ("group","supergroup"):
        stake=int(cm.group(1).replace(",",""))
        if stake<=0: await message.reply("❌ مبلغ مبارزه باید بیشتر از صفر باشد. 💎"); return
        bid,status=combat_create(message.chat.id,message.from_user.id,stake)
        if status=="funds": await message.reply("❌ موجودی آریور برای ساخت مبارزه کافی نیست. 💎"); return
        sent=await message.answer(f"🥊 مبارزه ساخته شد! ⚔️\n\n👤 مبارز اول: {mention_by_id(message.from_user.id)}\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n🏆 جایزه: {format_coins(stake*2)} آریور\n⏳ فرصت شرکت: {WAGER_WAIT_SECONDS} ثانیه\n\n👥 نفر دوم روی «شرکت کردن» بزند.", reply_markup=keyboard([[button("🥊 شرکت کردن",f"combat:join:{bid}")]]), parse_mode="HTML")
        with db() as c:c.execute("UPDATE combat_battles SET message_id=? WHERE id=?",(sent.message_id,bid)); c.commit()
        asyncio.create_task(combat_expiry_task(bid)); return
    tm=re.fullmatch(r"تورنمنت\s+([0-9][0-9,]*)",text)
    if tm and message.chat.type in ("group","supergroup"):
        stake=int(tm.group(1).replace(",","")); tid,status=tournament_create(message.chat.id,message.from_user.id,stake)
        if status=="funds": await message.reply("❌ موجودی کافی نیست. 💎"); return
        sent=await message.answer(f"🏆 تورنمنت ۸ نفره ساخته شد!\n\n👤 سازنده: {display_name_by_id(message.from_user.id)}\n💎 ورودی هر نفر: {format_coins(stake)} آریور\n🏆 جایزه فعلی: {format_coins(stake)} آریور\n👥 ظرفیت: 1/8\n⏳ فرصت تکمیل: {TOURNAMENT_WAIT_SECONDS} ثانیه",reply_markup=keyboard([[button("🏆 شرکت در تورنمنت",f"tournament:join:{tid}")]]))
        with db() as c: c.execute("UPDATE tournaments SET message_id=? WHERE id=?",(sent.message_id,tid)); c.commit()
        async def expire_tournament():
            await asyncio.sleep(TOURNAMENT_WAIT_SECONDS); t=tournament_get(tid)
            if not t or t["status"]!="waiting": return
            ps=tournament_players(tid)
            for u in ps: add_coins(u,t["stake"]); log_tx(u,"tournament_refund",t["stake"],f"tid={tid}")
            with db() as c: c.execute("UPDATE tournaments SET status='refunded' WHERE id=?",(tid,)); c.commit()
            try: await bot.edit_message_text(f"⏰ تورنمنت #{tid} لغو شد؛ ظرفیت ۸ نفر تکمیل نشد.\n💎 ورودی همه بازیکنان برگشت داده شد.",chat_id=t["chat_id"],message_id=t["message_id"])
            except Exception: pass
        asyncio.create_task(expire_tournament()); return
    # 🃏 هفت خبیث — 2 تا 4 نفر
    if message.chat.type in ("group", "supergroup"):
        sm=re.fullmatch(r"بازی\s+(?:7\s*خبیث|هفت\s*خبیث)\s+([0-9][0-9,]*)",text)
        if sm:
            stake=int(sm.group(1).replace(",",""))
            if stake<=0:
                await message.reply("❌ مبلغ شرط باید بیشتر از صفر باشد. 💎"); return
            gid,status=seven_create(message.chat.id,message.from_user.id,stake,2)
            if status=="funds":
                await message.reply(f"❌ برای ساخت بازی حداقل {format_coins(stake)} آریور موجودی لازم داری. 💎"); return
            g=SEVEN_GAMES[gid]
            sent=await message.answer(seven_lobby_text(g,"اول تعداد نفرات را مشخص کن؛ ۲ تا ۴ نفر می‌توانند بازی کنند."),reply_markup=seven_lobby_keyboard(g),parse_mode="HTML")
            g["message_id"]=sent.message_id; seven_persist(g); asyncio.create_task(seven_lobby_expiry(gid)); return

        wager_patterns = [
            (r"دوز\s+([0-9][0-9,]*)", "dooz"),
            (r"سنگ\s+کاغذ\s+قیچی\s+([0-9][0-9,]*)", "rps"),
            (r"جنگ\s+کارت\s+([0-9][0-9,]*)", "cards"),
            (r"زوج\s+یا\s+فرد\s+([0-9][0-9,]*)", "evenodd"),
            (r"حدس\s+عدد\s+([0-9][0-9,]*)", "guess"),
            (r"بالاتر\s+([0-9][0-9,]*)", "higher"),
            (r"تاس جنگ\s+([0-9][0-9,]*)", "dice"),
            (r"بلک‌جک ساده\s+([0-9][0-9,]*)", "blackjack"),
            (r"مسابقه سرعت\s+([0-9][0-9,]*)", "quickmath"),
        ]
        for pattern, game_type in wager_patterns:
            wm = re.fullmatch(pattern, text)
            if wm:
                stake = int(wm.group(1).replace(",", ""))
                if stake <= 0:
                    await message.reply("❌ مبلغ ورودی باید بیشتر از صفر باشد. 💎")
                    return
                wid, status = create_wager(message.chat.id, message.from_user.id, game_type, stake)
                if status == "funds":
                    await message.reply(f"❌ برای ساخت این بازی حداقل {format_coins(stake)} آریور موجودی لازم داری. 💎")
                    return
                name = WAGER_GAME_NAMES[game_type]
                sent = await message.answer(
                    f"🎮 بازی «{name}» ساخته شد! 🔥\n\n"
                    f"👤 سازنده: {('@'+message.from_user.username) if message.from_user.username else message.from_user.full_name}\n"
                    f"💎 مبلغ ورودی هر نفر: {format_coins(stake)} آریور\n"
                    f"🏆 جایزه برنده: {format_coins(stake*2)} آریور\n"
                    f"⏳ فرصت شرکت: {WAGER_WAIT_SECONDS} ثانیه\n\n"
                    f"👥 یک نفر روی «شرکت کردن» بزند تا بازی شروع شود.",
                    reply_markup=wager_invite_keyboard(wid)
                )
                set_wager_message(wid, sent.message_id)
                asyncio.create_task(wager_expiry_task(wid))
                return

    if text in ("بارش شوشول", "بارش شوشول نانو", "بارش شوشول طلایی"):
        if await handle_shoshol_rain(message):
            return

    if text in ("هک", "hack"):
        await handle_bank_hack(message)
        return

    if text in ("شوشول بری", "شوشول‌بری", "شوشول بري"):
        await handle_shoshol_bari(message)
        return

    # Safe in-game mini-games using Arioor only.
    if text.startswith("حدس عدد"):
        parts=text.split()
        if len(parts)!=2 or not parts[1].isdigit(): await message.reply("🔢 فرمت: حدس عدد 7"); return
        guess=int(parts[1]); target=random.randint(1,10)
        if not 1<=guess<=10: await message.reply("❌ عدد باید بین 1 تا 10 باشد."); return
        reward=500 if guess==target else 0
        if reward: add_coins(message.from_user.id,reward); log_tx(message.from_user.id,"guess",reward,"حدس عدد")
        await message.reply(f"🔢 عدد درست: {target}\n"+(f"🎉 {format_coins(reward)} آریور جایزه گرفتی!" if reward else "😅 این بار نشد؛ دوباره امتحان کن.")); return
    if message.chat.type in ("group", "supergroup"):
        normalized = text.replace("‌", "").strip().lower()
        if "آرسین" in text or "ارسین" in text:
            await message.reply("😒 با شوهر من چیکار داری ؟؟ ها؟؟ 😤🫵❤️")
            return
        if normalized == "راهنما آریو":
            await message.reply(user_help_text(),reply_markup=help_categories_keyboard())
            return
        if text in ("آریو", "اریو"):
            last=coin_cooldown(message.from_user.id); remaining=COIN_COOLDOWN-int(time.time()-last)
            if remaining>0:
                mins,secs=divmod(remaining,60); await message.reply(f"⏳ تازه آریو استخراج کردی! 😄\n🕐 {mins} دقیقه و {secs} ثانیه مونده.\n💎 بعدش دوباره میتونی آریو استخراج کنی.")
            else:
                r=process_ah(message.from_user.id); ario_amount=r["reward"]*2; extra=f"\n🎉 لول ارتقا یافت و {format_coins(r['level_reward'])} آریور جایزه گرفتی! ⭐" if r["leveled_up"] else ""
                await message.reply(f"⛏️ شما {format_coins(ario_amount)} آریو استخراج کردی.\n💰 معادل {format_coins(r['reward'])} آریور.\n💰 موجودی: {format_coins(r['balance'])} آریور\n⭐ لول کاربر: {r['level']}\n⏰ 5 دقیقه دیگه میتونی آریو استخراج کنی 💖{extra}")
            return
        if text == "موجودی": await message.reply(f"{balance_display(message.from_user.id)}"); return
        if text.startswith("کد هدیه "):
            code = text[len("کد هدیه "):].strip()
            amount, status = redeem_gift(code, message.from_user.id)
            if status == "invalid":
                await message.reply("❌ این کد هدیه وجود ندارد یا منقضی شده است."); return
            if status == "used":
                await message.reply("⚠️ شما قبلاً از این کد هدیه استفاده کرده‌اید."); return
            if status == "expired":
                await message.reply("❌ این کد هدیه تک‌کاربره قبلاً توسط یک نفر استفاده شده و دیگر قابل استفاده نیست."); return
            await message.reply(f"🎉 کد هدیه فعال شد!\n💎 {format_coins(amount)} آریور به موجودی شما اضافه شد.\n💰 موجودی شما: {format_coins(get_balance(message.from_user.id))} 💎")
            return
        if text in ("بازی مافیا", "بازی مافیا 🎭"):
            await start_game_setup(message); return
        if text in ("پایان بازی", "بایان بازی"):
            if message.chat.id in games:
                await cancel_game(message.chat.id)
                await safe_delete(message)
            else:
                await message.reply("ℹ️ بازی فعالی در این گروه وجود ندارد.")
            return

    # AI is disabled: do not reply to ordinary messages.
    return


@dp.callback_query(F.data.startswith("transfer:"))
async def transfer_callback(query:CallbackQuery):
    parts=query.data.split(":"); sender=int(parts[2]); action=parts[1]
    if query.from_user.id!=sender: await query.answer("❌ فقط فرستنده می‌تواند تأیید کند.",show_alert=True); return
    pending=transfer_pending.get(sender)
    if not isinstance(pending,tuple): await query.answer("⚠️ انتقال دیگر فعال نیست.",show_alert=True); return
    if action=="cancel": transfer_pending.pop(sender,None); await query.message.edit_text("❌ انتقال لغو شد."); await query.answer(); return
    amount,target_id,username=pending[1:]
    if get_balance(sender)<amount: transfer_pending.pop(sender,None); await query.message.edit_text("❌ موجودی آریور کافی نیست. 💰"); await query.answer(); return
    add_coins(sender,-amount); add_coins(target_id,amount); log_tx(sender,"transfer",-amount,f"to={target_id}"); log_tx(target_id,"transfer",amount,f"from={sender}"); bump_mission(sender,"transfer"); transfer_pending.pop(sender,None)
    target_label='@'+username if username else display_name_by_id(target_id)
    await query.message.edit_text(f"✅ انتقال انجام شد! 💸\n\n💰 {format_coins(amount)} آریور به {target_label} منتقل شد.\n💳 موجودی شما: {format_coins(get_balance(sender))} آریور")
    try: await bot.send_message(target_id,f"🎁 {format_coins(amount)} آریور برای شما انتقال داده شد. 💸\n💰 موجودی: {format_coins(get_balance(target_id))} آریور")
    except Exception: pass
    await query.answer("💸 انجام شد!")

# ================================================================
# MAIN
# ================================================================
async def restore_seven_games():
    with db() as c:
        rows=c.execute("SELECT id FROM seven_games WHERE status IN ('active','waiting') ORDER BY id").fetchall()
    for (gid,) in rows:
        g=seven_load_game_from_db(int(gid))
        if not g:
            continue
        if g.get("status")=="active":
            # If a restart happened while a turn was already overdue, process it immediately.
            if float(g.get("deadline",0))<=time.time():
                g["turn_token"]=int(g.get("turn_token",0))+1
            seven_schedule_timer(g)
        elif g.get("status")=="waiting":
            remaining=max(1,int(float(g.get("expires_at",time.time()+SEVEN_WAIT_SECONDS))-time.time()))
            async def resume_lobby_timer(game_id, delay):
                await asyncio.sleep(delay)
                game=SEVEN_GAMES.get(game_id)
                if game and game.get("status")=="waiting" and len(game.get("players",[]))<game.get("max_players",2):
                    await seven_finish_refund(game,"عدم تکمیل لابی پس از راه‌اندازی مجدد ربات")
            asyncio.create_task(resume_lobby_timer(int(gid),remaining))


async def main():
    init_db()
    await restore_seven_games()
    asyncio.create_task(business_income_loop())
    asyncio.create_task(football_income_loop())
    asyncio.create_task(football_contract_notice_loop())
    asyncio.create_task(leaderboard_reward_loop())
    asyncio.create_task(lottery_loop())
    asyncio.create_task(lottery_live_loop())
    asyncio.create_task(scheduled_announcement_delete_loop())
    print(f"SQLite database: {DB}")
    print("آریو آنلاین شد و منتظر آرسین است...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
