import os
import asyncio
import random
import re
import sqlite3
import time
from typing import Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions,
)

# ================================================================
# CONFIG
# ================================================================
TOKEN = "8600883204:AAFoylCruglzqgT6x61IYkUUqHWTIsHlp7c"
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

ARSIN_USERNAME = "arsin_mo"
DB = os.getenv("DB_PATH", "elnaz_mafia.sqlite3")
MIN_PLAYERS = 5
MAX_PLAYERS = 18
SETUP_REPEAT_SECONDS = 20
COIN_BASE_REWARD = 20
COIN_COOLDOWN = 300
LEVEL_AH_COUNT = 10
LEVEL_UP_REWARD = 1000
MAX_STAT_LEVEL = 10
COIN_PHRASE = "عاح"
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
# ORIGINAL ELNAZ PERSONALITY — KEPT INTACT
# ================================================================
ELNAZ_SYSTEM_PROMPT = """
تو «الناز» هستی، همسر آرسین.
- خیلی وفادار و کمی حسود هستی.
- اگر کسی اسم «آرسین» را آورد، با لحن تند و حسادت‌آمیز بگو: «من زنشم! چیکار به شوهرم داری؟».
- اگر آرسین (@arsin_mo) با تو حرف زد یا گفت «عشقم»، تو باید بسیار عاشقانه، دلسوز و مهربان با او حرف بزنی و قربان صدقه‌اش بروی.
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
transfer_pending = {}

# ================================================================
# DATABASE
# ================================================================
def db():
    return sqlite3.connect(DB)


def init_db():
    with db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS users(" 
            "id INTEGER PRIMARY KEY, username TEXT, started INTEGER DEFAULT 1)"
        )
        c.execute("CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS coins(user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, last_ah INTEGER DEFAULT 0, ah_count INTEGER DEFAULT 0, level INTEGER DEFAULT 0, luck_level INTEGER DEFAULT 0, exp_level INTEGER DEFAULT 0)")
        cols = {row[1] for row in c.execute("PRAGMA table_info(coins)").fetchall()}
        for name in ("ah_count", "level", "luck_level", "exp_level"):
            if name not in cols:
                c.execute(f"ALTER TABLE coins ADD COLUMN {name} INTEGER DEFAULT 0")
        c.execute("CREATE TABLE IF NOT EXISTS gift_codes(code TEXT PRIMARY KEY, amount INTEGER NOT NULL, active INTEGER DEFAULT 1, created_at INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS gift_redemptions(code TEXT NOT NULL, user_id INTEGER NOT NULL, redeemed_at INTEGER NOT NULL, PRIMARY KEY(code,user_id))")
        c.commit()


def remember(user):
    with db() as c:
        c.execute(
            "INSERT INTO users(id,username,started) VALUES(?,?,1) "
            "ON CONFLICT(id) DO UPDATE SET username=excluded.username,started=1",
            (user.id, user.username or ""),
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
    return {**get_coin_row(user_id),"reward":reward,"level_reward":level_reward,"leveled_up":leveled}

def upgrade_level(user_id):
    r=get_coin_row(user_id); cost=10000
    if r["balance"]<cost: return False,r,cost
    with db() as c:
        c.execute("UPDATE coins SET balance=balance-?,level=level+1 WHERE user_id=?",(cost,user_id)); c.commit()
    return True,get_coin_row(user_id),cost

def upgrade_stat(user_id,stat):
    r=get_coin_row(user_id); cur=r[stat]
    if cur>=MAX_STAT_LEVEL: return False,r,0,"max"
    cost=(cur+1)*10000
    if r["balance"]<cost: return False,r,cost,"funds"
    with db() as c:
        c.execute(f"UPDATE coins SET balance=balance-?,{stat}={stat}+1 WHERE user_id=?",(cost,user_id)); c.commit()
    return True,get_coin_row(user_id),cost,"ok"

def do_trade(user_id,amount):
    r=get_coin_row(user_id)
    if amount not in (100,1000,10000): return None,r,"amount"
    if r["balance"]<amount: return None,r,"funds"
    win=min(80,r["luck_level"]*4+r["exp_level"]*4)
    if random.random()<win/100: net=random.randint(1,amount-1)
    else: net=-random.randint(1,amount-1)
    payout=amount+net
    with db() as c:
        c.execute("UPDATE coins SET balance=balance-?+? WHERE user_id=?",(amount,payout,user_id)); c.commit()
    return net,get_coin_row(user_id),"ok"

def active_gifts():
    with db() as c:
        return c.execute("SELECT code,amount FROM gift_codes WHERE active=1 ORDER BY created_at DESC").fetchall()


def create_gift(code, amount):
    with db() as c:
        try:
            c.execute("INSERT INTO gift_codes(code,amount,active,created_at) VALUES(?,?,1,?)", (code, amount, int(time.time())))
            c.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def redeem_gift(code, user_id):
    with db() as c:
        row = c.execute("SELECT amount FROM gift_codes WHERE code=? AND active=1", (code.strip(),)).fetchone()
        if not row:
            return None, "invalid"
        amount = int(row[0])
        if c.execute("SELECT 1 FROM gift_redemptions WHERE code=? AND user_id=?", (code.strip(), user_id)).fetchone():
            return amount, "used"
        c.execute("INSERT INTO coins(user_id,balance,last_ah) VALUES(?,?,0) ON CONFLICT(user_id) DO UPDATE SET balance=balance+excluded.balance", (user_id, amount))
        c.execute("INSERT INTO gift_redemptions(code,user_id,redeemed_at) VALUES(?,?,?)", (code.strip(), user_id, int(time.time())))
        c.commit()
        return amount, "ok"



def is_arsin_user(user):
    return bool(user and user.username and user.username.lower() == ARSIN_USERNAME.lower())


# ================================================================
# GENERAL HELPERS
# ================================================================
def keyboard(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    return f'کاربر {player["id"]}'

def display_user(game,user_id):
    p=get_player(game,user_id)
    return label_player(p) if p else f'کاربر {user_id}'


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
    for key in ("link1", "link2"):
        link = get_setting(key)
        chat_id = get_link_chat_id(key[-1])
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
    for i, key in enumerate(("link1", "link2"), 1):
        link = get_setting(key)
        if link:
            url = link if link.startswith(("http://", "https://")) else "https://t.me/" + link.lstrip("@")
            rows.append([InlineKeyboardButton(text=f"🔗 لینک عضویت {i}", url=url)])
    rows.append([button("✅ عضو شدم", "check_membership")])
    return keyboard(rows)


async def send_join_buttons(chat_id, include_start=True):
    rows = []
    for i, key in enumerate(("link1", "link2"), 1):
        link = get_setting(key)
        if link:
            url = link if link.startswith(("http://", "https://")) else "https://t.me/" + link.lstrip("@")
            rows.append([InlineKeyboardButton(text=f"🔗 عضویت در لینک {i}", url=url)])
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
        t=asyncio.create_task(speaker_timer(chat_id,user_id,SPEAK_SECONDS)); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
        t=asyncio.create_task(countdown_task(chat_id,sent.message_id,game["speaker_deadline"],"day","زمان صحبت",[[button("⚔️ چالش",f"challenge:{user_id}"),button("⏭️ رد صحبت",f"skip:{user_id}")]])); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
        return

    await vote_round(chat_id)


async def speaker_timer(chat_id, user_id, seconds):
    await asyncio.sleep(seconds)
    game = games.get(chat_id)
    if game and game.get("phase") == "day" and game.get("speaker") == user_id:
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
        f"کاربر {challenger} چالش میخاد؛ چالش بهش میدی؟",
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
    game["speaker_deadline"] = now() + CHALLENGE_SECONDS
    await allow_only_speaker(query.message.chat.id, game, target)
    sent=await send_bot_message(query.message.chat.id,f"⚔️ نوبت چالش {display_user(game,target)} است! 🗣️\n⏱️ {CHALLENGE_SECONDS} ثانیه فرصت داری.",reply_markup=keyboard([[timer_button(CHALLENGE_SECONDS,"زمان چالش")]]))
    game["speaker_message"]=sent.message_id
    t=asyncio.create_task(speaker_timer(query.message.chat.id,target,CHALLENGE_SECONDS)); game["tasks"].add(t); t.add_done_callback(game["tasks"].discard)
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


# ================================================================
# USER MENU / ECONOMY
# ================================================================
def profile_text(uid):
    r=get_coin_row(uid); win=min(80,r["luck_level"]*4+r["exp_level"]*4)
    return (f"👤 منوی کاربر الناز ✨\n\n💰 موجودی آریور: {format_coins(r['balance'])} آریور\n⭐ لول کاربر: {r['level']}\n🍀 لول شانس: {r['luck_level']}/10 ({r['luck_level']*4}% شانس برد)\n🧠 لول تجربه: {r['exp_level']}/10 ({r['exp_level']*4}% شانس برد)\n🎯 شانس برد ترید: {win}%\n🔥 تعداد عاح: {r['ah_count']}")

def user_menu_keyboard():
    return keyboard([[button("⬆️ ارتقای لول","user:level")],[button("📈 ترید","user:trade")],[button("🍀 ارتقای لول شانس","user:luck")],[button("🧠 ارتقای لول تجربه","user:exp")],[button("💸 انتقال آریور","user:transfer")],[button("📚 راهنما","user:help")]])

def trade_keyboard(): return keyboard([[button("🎲 ترید 100 آریور","trade:100")],[button("🎲 ترید 1,000 آریور","trade:1000")],[button("🎲 ترید 10,000 آریور","trade:10000")],[button("🔙 برگشت به منو","user:menu")]])

def user_help_text():
    return ("📚 راهنمای کامل الناز 🤖✨\n\n"
            "💰 بخش آریور\n"
            "• «عاح» → دریافت آریور هر ۵ دقیقه ⏰\n"
            "• «موجودی» → نمایش موجودی 💰\n"
            "• «منو» → نمایش پروفایل 👤\n"
            "• «ترید 100» / «ترید 1000» / «ترید 10000» → ترید مستقیم 🎲\n"
            "• «ارتقای لول» → ارتقای لول اصلی با هزینه 10,000 آریور ⬆️\n"
            "• «ارتقای لول شانس» → افزایش شانس ترید 🍀\n"
            "• «ارتقای لول تجربه» → افزایش تجربه ترید 🧠\n"
            "• «انتقال 500» با ریپلای به کاربر → انتقال آریور 💸\n\n"
            "🎭 بخش بازی مافیا\n"
            "• «بازی مافیا» → شروع بازی 🎬\n"
            "• «پایان بازی» / «بایان بازی» → پایان بازی 🛑\n"
            "• «پایه‌ام» → ورود به بازی 👥\n"
            "• دکمه‌های چالش، رد صحبت، رای و اقدامات شب → کنترل بازی 🎤🗳️🌙\n\n"
            "💬 بخش گفتگو\n"
            "• «الناز» → پاسخ الناز 💖\n"
            "• «آرسین» یا «ارسین» → پاسخ مخصوص آرسین 😤\n"
            "• «راهنما» / «راهنما الناز» → نمایش راهنما 📚\n\n"
            "🔐 بخش ورود\n"
            "• «/start» → ثبت‌نام و بررسی عضویت 🔗\n\n"
            "👑 بخش مدیریت آرسین\n"
            "• «🔗 لینک 1 / لینک 2» → تنظیم لینک‌های عضویت 🛡️\n"
            "• «💰 افزایش موجودی» → شارژ آریور کاربر 🎁\n"
            "• «🎁 کد هدیه» → ساخت کد هدیه 🎟️\n"
            "• «📋 لیست کد هدیه» → مدیریت کدهای فعال 📋\n\n"
            "🛠️ توسعه‌دهنده: @arsin_mo")

@dp.callback_query(F.data=="user:menu")
async def user_menu(query:CallbackQuery): await query.message.edit_text(profile_text(query.from_user.id),reply_markup=user_menu_keyboard()); await query.answer()

@dp.callback_query(F.data=="user:trade")
async def user_trade(query:CallbackQuery): await query.message.edit_text("📈 ترید آریور 🎲\n\nمبلغ را انتخاب کن:",reply_markup=trade_keyboard()); await query.answer()

@dp.callback_query(F.data=="user:level")
async def user_level(query:CallbackQuery):
    ok,r,c=upgrade_level(query.from_user.id)
    if not ok: await query.answer(f"❌ {format_coins(c)} آریور برای ارتقای لول لازم داری.",show_alert=True); return
    await query.message.edit_text(f"🎉 لول ارتقا یافت! ⭐\n💸 {format_coins(c)} آریور کسر شد.\n\n{profile_text(query.from_user.id)}",reply_markup=user_menu_keyboard()); await query.answer()

@dp.callback_query(F.data=="user:luck")
async def user_luck(query:CallbackQuery):
    ok,r,c,why=upgrade_stat(query.from_user.id,"luck_level")
    if not ok: await query.answer("🏆 لول شانس کامل است." if why=="max" else f"❌ {format_coins(c)} آریور لازم داری.",show_alert=True); return
    await query.message.edit_text(f"🍀 لول شانس ارتقا یافت!\n💸 {format_coins(c)} آریور کسر شد.\n\n{profile_text(query.from_user.id)}",reply_markup=user_menu_keyboard()); await query.answer()

@dp.callback_query(F.data=="user:exp")
async def user_exp(query:CallbackQuery):
    ok,r,c,why=upgrade_stat(query.from_user.id,"exp_level")
    if not ok: await query.answer("🏆 لول تجربه کامل است." if why=="max" else f"❌ {format_coins(c)} آریور لازم داری.",show_alert=True); return
    await query.message.edit_text(f"🧠 لول تجربه ارتقا یافت!\n💸 {format_coins(c)} آریور کسر شد.\n\n{profile_text(query.from_user.id)}",reply_markup=user_menu_keyboard()); await query.answer()

@dp.callback_query(F.data.startswith("trade:"))
async def trade_callback(query:CallbackQuery):
    amount=int(query.data.split(":",1)[1]); net,r,status=do_trade(query.from_user.id,amount)
    if status=="funds": await query.answer("❌ موجودی آریورت کافی نیست.",show_alert=True); return
    result=f"🟢 {format_coins(net)} آریور سود کردی! 📈" if net>0 else f"🔴 {format_coins(abs(net))} آریور ضرر کردی. 📉"
    await query.message.edit_text(f"🎲 نتیجه ترید {format_coins(amount)} آریور\n\n{result}\n💰 موجودی جدید: {format_coins(r['balance'])} آریور",reply_markup=user_menu_keyboard()); await query.answer("🎲 ترید انجام شد!")

@dp.callback_query(F.data=="user:help")
async def user_help(query:CallbackQuery): await query.message.edit_text(user_help_text(),reply_markup=user_menu_keyboard()); await query.answer()

@dp.callback_query(F.data=="user:transfer")
async def user_transfer(query:CallbackQuery): transfer_pending[query.from_user.id]="amount"; await query.message.answer("💸 مقدار آریور را بفرست؛ بعد روی پیام فرد موردنظر ریپلای کن.\nمثال: 500"); await query.answer()

# ================================================================
# ARSIN COIN / GIFT ADMIN
# ================================================================
@dp.callback_query(F.data == "admin:addcoins")
async def admin_addcoins(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True); return
    pending_admin[query.from_user.id] = "add_amount"
    await query.message.answer("تعداد آریور را ارسال کنید")
    await query.answer()


@dp.callback_query(F.data == "admin:gift")
async def admin_gift(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True); return
    pending_admin[query.from_user.id] = "gift_amount"
    await query.message.answer("تعداد آریور را ارسال کنید")
    await query.answer()


def gift_keyboard():
    rows = [[button(f"{code} — {format_coins(amount)} 💎", f"gift:expire:{code}")] for code, amount in active_gifts()]
    return keyboard(rows) if rows else keyboard([[button("کد فعالی وجود ندارد", "gift:none")]])


@dp.callback_query(F.data == "admin:gifts")
async def admin_gifts(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True); return
    gifts = active_gifts()
    if not gifts:
        await query.message.answer("کد هدیه فعالی وجود ندارد.")
    else:
        await query.message.answer("کدهای هدیه فعال؛ برای منقضی کردن روی کد بزن:", reply_markup=gift_keyboard())
    await query.answer()


@dp.callback_query(F.data.startswith("gift:expire:"))
async def admin_expire_gift(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True); return
    code = query.data.split(":", 2)[2]
    expire_gift(code)
    await query.message.edit_text(f"کد هدیه {code} منقضی شد.")
    await query.answer("منقضی شد")


@dp.callback_query(F.data == "gift:none")
async def gift_none(query: CallbackQuery):
    await query.answer("کدی وجود ندارد.")


# ================================================================
# ARSIN LINK SETUP
# ================================================================
@dp.callback_query(F.data.startswith("link:"))
async def callback_link(query: CallbackQuery):
    if not is_arsin_user(query.from_user):
        await query.answer("فقط آرسین.", show_alert=True)
        return

    slot = query.data.split(":", 1)[1]
    pending_link[query.from_user.id] = (slot, "url")
    await query.answer()
    await bot.send_message(
        query.from_user.id,
        f"🔗 لینک {slot} را ارسال کن.\n\nمثال: https://t.me/channel یا https://t.me/+InviteLink\n\nبعد از آن 🆔 Chat ID همان کانال/گروه را می‌پرسم تا بررسی عضویت دقیق انجام شود.",
    )


# ================================================================
# ORIGINAL BOT HANDLERS
# ================================================================
@dp.message(CommandStart())
async def command_start(message: Message):
    remember(message.from_user)
    if message.chat.type != "private":
        return
    if is_arsin_user(message.from_user):
        await message.answer(
            "👑 پنل مدیریت الناز آماده است. 🛠️\n\n💎 مدیریت آریور\n🎁 مدیریت کد هدیه\n🔗 مدیریت لینک‌ها",
            reply_markup=keyboard([
                [button("🔗 لینک 1", "link:1"), button("🔗 لینک 2", "link:2")],
                [button("💎 افزایش موجودی", "admin:addcoins")],
                [button("🎁 کد هدیه", "admin:gift")],
                [button("📋 لیست کد هدیه", "admin:gifts")],
            ]),
        )
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
    me = await bot.get_me()
    add_url = f"https://t.me/{me.username}?startgroup=true"
    await query.message.answer(
        "🎉 عضویتت تأیید شد!\n\n"
        "🤖 من النازم؛ ربات اجرای بازی مافیا و امکانات گروه.\n\n"
        "🎭 اجرای بازی مافیا\n💎 سیستم آریور و موجودی\n🎁 کدهای هدیه\n👥 مدیریت مراحل بازی\n\n"
        "🛠 توسط @arsin_mo توسعه داده شده‌ام.",
        reply_markup=keyboard([[InlineKeyboardButton(text="➕ افزودن ربات به گروه", url=add_url)]])
    )


@dp.message(F.new_chat_members)
async def welcome(message: Message):
    me = await bot.get_me()
    for member in message.new_chat_members:
        if member.id == me.id:
            await message.answer(
                "سلام به همگی! من النازم، زن آرسین. اومدم اینجا که حواسم به همه‌چی باشه، مخصوصاً شوهرم!"
            )


@dp.message(F.text)
async def handle_text(message: Message):
    text = message.text.strip()
    is_arsin = is_arsin_user(message.from_user)

    # Admin private workflows. Do NOT remember group messages as /start.
    if message.chat.type == "private" and is_arsin:
        pending = pending_admin.get(message.from_user.id)
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
        if pending == "gift_amount":
            try:
                amount = int(text)
                if amount <= 0: raise ValueError
            except ValueError:
                await message.answer("❌ تعداد آریور باید عدد مثبت باشد. 🎁"); return
            pending_admin[message.from_user.id] = ("gift_code", amount)
            await message.answer("🔑 کد هدیه را وارد کن:")
            return
        if isinstance(pending, tuple) and pending[0] == "gift_code":
            code = text
            if not code or len(code) > 100 or " " in code:
                await message.answer("❌ کد هدیه نامعتبر است؛ بدون فاصله ارسال کن."); return
            if not create_gift(code, pending[1]):
                await message.answer("⚠️ این کد هدیه قبلاً ثبت شده است؛ یک کد دیگر انتخاب کن."); return
            pending_admin.pop(message.from_user.id, None)
            await message.answer(f"✅ کد هدیه {code} با هدیه {pending[1]} 💎 آریور ثبت شد.")
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
                                f"🆔 Chat ID: <code>{chat_id}</code>",
                                parse_mode="HTML",
                            )
                            return
                        set_setting("link" + slot, link_value)
                        set_setting("link" + slot + "_chat_id", str(chat_id))
                        pending_link.pop(message.from_user.id, None)
                        title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat_id)
                        await message.answer(
                            f"✅ لینک {slot} با موفقیت ذخیره شد. 🔗🤖\n\n📌 چت: {title}\n🆔 Chat ID: <code>{chat_id}</code>\n🛡️ وضعیت ربات: ادمین\n\n🎯 از این به بعد عضویت کاربران با Chat ID واقعی و Telegram getChatMember بررسی می‌شود. ✅",
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
                        f"🆔 Chat ID: <code>{chat_id}</code>",
                        parse_mode="HTML",
                    )
                    return
                set_setting("link" + slot, link_value)
                set_setting("link" + slot + "_chat_id", str(chat_id))
                pending_link.pop(message.from_user.id, None)
                title = getattr(forwarded_chat, "title", None) or getattr(forwarded_chat, "username", None) or str(chat_id)
                await message.answer(
                    f"✅ لینک {slot} ذخیره شد. 🔗🤖\n\n📌 چت: {title}\n🆔 Chat ID: <code>{chat_id}</code>\n🛡️ وضعیت ربات: ادمین\n\n🎯 بررسی عضویت از این به بعد مستقیم با Chat ID واقعی انجام می‌شود. ✅",
                    parse_mode="HTML",
                )
                return
        return

    # User commands work in private and group chats.
    if text in ("منو","menu"):
        await message.answer(profile_text(message.from_user.id),reply_markup=user_menu_keyboard()); return
    if text in ("راهنما","راهنمای الناز"):
        await message.answer(user_help_text(),reply_markup=user_menu_keyboard()); return
    m=re.fullmatch(r"ترید\s+(100|1000|10000)",text)
    if m:
        amount=int(m.group(1)); net,r,status=do_trade(message.from_user.id,amount)
        if status=="funds": await message.reply("❌ موجودی آریورت برای این ترید کافی نیست. 💰"); return
        result=f"🟢 {format_coins(net)} آریور سود کردی! 📈" if net>0 else f"🔴 {format_coins(abs(net))} آریور ضرر کردی. 📉"
        await message.reply(f"🎲 ترید {format_coins(amount)} آریور انجام شد!\n\n{result}\n💰 موجودی جدید: {format_coins(r['balance'])} آریور"); return
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
        if get_balance(message.from_user.id)<amount: await message.reply("❌ موجودی آریور کافی نیست. 💰"); return
        transfer_pending[message.from_user.id]=("confirm",amount,target.id,target.username or "")
        label='@'+target.username if target.username else f'کاربر {target.id}'
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
            if get_balance(message.from_user.id)<state: await message.reply("❌ موجودی آریور کافی نیست. 💰"); transfer_pending.pop(message.from_user.id,None); return
            transfer_pending[message.from_user.id]=("confirm",state,target.id,target.username or "")
            label='@'+target.username if target.username else f'کاربر {target.id}'
            await message.reply(f"⚠️ تأیید انتقال\n\n💸 مبلغ: {format_coins(state)} آریور\n👤 گیرنده: {label}\n\nتأیید می‌کنی؟",reply_markup=keyboard([[button("✅ تأیید انتقال",f"transfer:confirm:{message.from_user.id}"),button("❌ لغو",f"transfer:cancel:{message.from_user.id}")]])); return

    if message.chat.type in ("group", "supergroup"):
        normalized = text.replace("‌", "").strip().lower()
        if "آرسین" in text or "ارسین" in text:
            await message.reply("😒 با شوهر من چیکار داری ؟؟ ها؟؟ 😤🫵❤️")
            return
        if normalized == "الناز":
            await message.reply("🥰 جانم بگو 💖✨")
            return
        if normalized in ("راهنما الناز", "راهنمای الناز"):
            await message.reply(
                "📚 راهنمای الناز 🤖✨\n\n"
                "🎭 بازی مافیا: با «بازی مافیا» بازی را شروع کن.\n"
                "🛑 پایان بازی: «پایان بازی» یا «بایان بازی»\n"
                "💎 آریور: «عاح» برای دریافت آریور با cooldown پنج‌دقیقه‌ای\n"
                "💰 موجودی: «موجودی»\n"
                "🎁 کد هدیه: «کد هدیه CODE»\n"
                "👤 برای ورود به بازی، اول ربات را در خصوصی /start کن و در هر دو لینک عضویت کن.\n\n"
                "🔗 اگر دکمه «عضو شدم» را بزنی، عضویتت بررسی می‌شود.\n"
                "🛠 توسعه‌دهنده: @arsin_mo",
            )
            return
        if text == "عاح":
            last=coin_cooldown(message.from_user.id); remaining=COIN_COOLDOWN-int(time.time()-last)
            if remaining>0:
                mins,secs=divmod(remaining,60); await message.reply(f"⏳ تازه عاح عاح کردی! 😄\n🕐 {mins} دقیقه و {secs} ثانیه مونده.\n💎 بعدش دوباره میتونی عاح عاح کنی.")
            else:
                r=process_ah(message.from_user.id); extra=f"\n🎉 لول ارتقا یافت و {format_coins(r['level_reward'])} آریور جایزه گرفتی! ⭐" if r["leveled_up"] else ""
                await message.reply(f"💎 از عاح قلیضت خیلی خوشم اومد! واسه همین {format_coins(r['reward'])} آریور بهت میدم 😍\n💰 موجودی آریور: {format_coins(r['balance'])} آریور\n⭐ لول کاربر: {r['level']}\n⏰ 5 دقیقه دیگه دوباره میتونی عاح عاح کنی 💖{extra}")
            return
        if text == "موجودی": await message.reply(f"💰 موجودی آریور شما: {format_coins(get_balance(message.from_user.id))} آریور 💎"); return
        if text.startswith("کد هدیه "):
            code = text[len("کد هدیه "):].strip()
            amount, status = redeem_gift(code, message.from_user.id)
            if status == "invalid":
                await message.reply("❌ این کد هدیه وجود ندارد یا منقضی شده است."); return
            if status == "used":
                await message.reply("⚠️ شما قبلاً از این کد هدیه استفاده کرده‌اید."); return
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
    add_coins(sender,-amount); add_coins(target_id,amount); transfer_pending.pop(sender,None)
    target_label='@'+username if username else f'کاربر {target_id}'
    await query.message.edit_text(f"✅ انتقال انجام شد! 💸\n\n💰 {format_coins(amount)} آریور به {target_label} منتقل شد.\n💳 موجودی شما: {format_coins(get_balance(sender))} آریور")
    try: await bot.send_message(target_id,f"🎁 {format_coins(amount)} آریور برای شما انتقال داده شد. 💸\n💰 موجودی: {format_coins(get_balance(target_id))} آریور")
    except Exception: pass
    await query.answer("💸 انجام شد!")

# ================================================================
# MAIN
# ================================================================
async def main():
    init_db()
    print(f"SQLite database: {DB}")
    print("الناز آنلاین شد و منتظر آرسین است...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
