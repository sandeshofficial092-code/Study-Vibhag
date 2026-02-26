"""
🚀 Clean & Beautiful File Sharing Bot (Unicode Edition)
Features: Stunning UI, Force Join (Req + Join), File Batching, Fast Broadcast, Stats, Auto-Delete & Forward Protect
"""

import logging
import sqlite3
import asyncio
import uuid
from datetime import datetime
from typing import List, Tuple

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    ChatJoinRequestHandler
)
from telegram.error import BadRequest, Forbidden, TelegramError

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# ⚠️ REPLACE WITH YOUR TOKEN
BOT_TOKEN = "7830067873:AAEjLwoLF4H4bs464toXrRiq-usjme3R0mY" 

# ⚠️ REPLACE WITH YOUR ADMIN IDs
ADMIN_IDS = [8344443883] 

DB_FILE = "file_share_clean.db"
WELCOME_IMAGE = "https://telegra.ph/file/a46bcde86bdd36db82c87-a5320310b1e3d7162a.jpg"

# Auto-Delete Timer (30 minutes in seconds)
AUTO_DELETE_SECONDS = 1800

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation States
(
    ADD_CHANNEL_FWD, ADD_CHANNEL_LINK, 
    CREATE_LINK_WAIT, CREATE_LINK_CONFIRM,
    BROADCAST_CHOOSE_TYPE, BROADCAST_RECEIVE_MSG
) = range(6)

# ==============================================================================
# DATABASE MANAGER
# ==============================================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS channels (
        chat_id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        invite_link TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS join_requests (
        user_id INTEGER,
        chat_id INTEGER,
        request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, chat_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS batches (
        batch_id TEXT PRIMARY KEY,
        file_count INTEGER DEFAULT 0,
        is_protected BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        from_chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        caption TEXT,
        FOREIGN KEY(batch_id) REFERENCES batches(batch_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS access_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        batch_id TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    conn.commit()
    conn.close()
    migrate_db()

def migrate_db():
    # To add new columns if database already exists
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try: c.execute("ALTER TABLE batches ADD COLUMN is_protected BOOLEAN DEFAULT 0")
    except sqlite3.OperationalError: pass
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def generate_unique_id() -> str:
    return str(uuid.uuid4())[:8]

def add_user(user):
    if not user or user.is_bot: return
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
              (user.id, user.first_name, user.username))
    conn.commit()
    conn.close()

def log_access(user_id: int, batch_id: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO access_logs (user_id, batch_id) VALUES (?, ?)", (user_id, batch_id))
    conn.commit()
    conn.close()

async def check_user_subscription(user_id: int, bot) -> List[Tuple[str, str]]:
    if is_admin(user_id): return []
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT chat_id, title, invite_link FROM channels")
    channels = c.fetchall()
    conn.close()
    
    missing_channels = []
    for (chat_id, title, invite_link) in channels:
        is_verified = False
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ['member', 'administrator', 'creator', 'restricted']:
                is_verified = True
        except BadRequest: pass
        
        if not is_verified:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT 1 FROM join_requests WHERE user_id = ? AND chat_id = ?", (user_id, chat_id))
            if c.fetchone(): is_verified = True
            conn.close()
            
        if not is_verified:
            missing_channels.append((title, invite_link))
            
    return missing_channels

# ==============================================================================
# MAIN HANDLERS
# ==============================================================================
async def global_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user:
        add_user(update.effective_user)

async def process_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat = update.chat_join_request.chat
        user = update.chat_join_request.from_user
        add_user(user) 
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO join_requests (user_id, chat_id) VALUES (?, ?)", (user.id, chat.id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving join request: {e}")

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    add_user(user)

    if args:
        payload = args[0]
        await process_payload(update, context, payload)
        return

    # Beautiful Welcome UI with Unicode Fonts
    welcome_text = (
    f"<b>›› ʜᴇʏ!!, {user.first_name} ~</b>\n\n"
    f"<b>ɪ ᴀᴍ ғɪʟᴇ sᴛᴏʀᴇ ʙᴏᴛ,</b>\n"
    f"<blockquote>"
    f"<b>ɪ ᴄᴀɴ sᴛᴏʀᴇ ᴘʀɪᴠᴀᴛᴇ ғɪʟᴇs ɪɴ sᴘᴇᴄɪғɪᴇᴅ ᴄʜᴀɴɴᴇʟ "
    f"ᴀɴᴅ ᴏᴛʜᴇʀ ᴜsᴇʀs ᴄᴀɴ ᴀᴄᴄᴇss ɪᴛ ғʀᴏᴍ sᴘᴇᴄɪᴀʟ ʟɪɴᴋ.</b>"
    f"</blockquote>\n\n"
    f"♻️ <b>ᴍʏ ᴍᴀsᴛᴇʀ :</b> <b>@downfall_01</b>"
)
    
    # NEW BUTTONS ADDED HERE
    keyboard = [
        [
            InlineKeyboardButton("📢 ᴜᴘᴅᴀᴛᴇ ᴄʜᴀɴɴᴇʟ", url="https://t.me/SG_BOTS_UPDATE"),
            InlineKeyboardButton("💬 sᴜᴘᴘᴏʀᴛ ᴄʜᴀᴛ", url="https://t.me/SG_CHAT_GROUP")
        ]
    ]
    if is_admin(user.id):
        keyboard.append([InlineKeyboardButton("⚙️ ᴀᴅᴍɪɴ ᴘᴀɴᴇʟ", callback_data="admin_home")])

    await context.bot.send_photo(
        chat_id=user.id,
        photo=WELCOME_IMAGE,
        caption=welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
        parse_mode=ParseMode.HTML
    )

async def process_payload(update: Update, context: ContextTypes.DEFAULT_TYPE, batch_id: str):
    user = update.effective_user
    missing = await check_user_subscription(user.id, context.bot)
    
    if missing:
        buttons = []
        for title, link in missing:
            buttons.append([InlineKeyboardButton(f"➕ ᴊᴏɪɴ {title}", url=link)])
        
        buttons.append([InlineKeyboardButton("🟢 ᴠᴇʀɪꜰʏ", callback_data="verify_join")])
        context.user_data['pending_batch'] = batch_id
        
        # New Force Join Message Design
        join_txt = (
            f"🔒 <b>ᴄᴏɴᴛᴇɴᴛ ʟᴏᴄᴋᴇᴅ</b>\n\n"
            f"<blockquote>"
            f"🚫 <b>ᴍᴜꜱᴛ ᴊᴏɪɴ ᴀʟʟ ᴄʜᴀɴɴᴇʟꜱ ᴛᴏ ᴜꜱᴇ ᴍᴇ</b>\n\n"
            f"ᴘʟᴇᴀꜱᴇ ᴄʟɪᴄᴋ ᴛʜᴇ <b>ᴊᴏɪɴ</b> ʙᴜᴛᴛᴏɴꜱ ʙᴇʟᴏᴡ, "
            f"ᴛʜᴇɴ ᴛᴀᴘ <b>ᴠᴇʀɪꜰʏ</b> ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ."
            f"</blockquote>"
        )
        await context.bot.send_message(user.id, join_txt, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)
        return

    await send_batch_files(update, context, batch_id)

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()
    
    missing = await check_user_subscription(user.id, context.bot)
    
    if not missing:
        try: await query.message.delete()
        except: pass
        
        await context.bot.send_message(user.id, "✅ <b>ᴠᴇʀɪꜰɪᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ!</b>\n<i>ꜱᴇɴᴅɪɴɢ ʏᴏᴜʀ ꜰɪʟᴇꜱ...</i>", parse_mode=ParseMode.HTML)
        batch_id = context.user_data.pop('pending_batch', None)
        if batch_id:
            await send_batch_files(update, context, batch_id)
    else:
        await query.answer("❌ ᴠᴇʀɪꜰɪᴄᴀᴛɪᴏɴ ꜰᴀɪʟᴇᴅ! ᴘʟᴇᴀꜱᴇ ᴊᴏɪɴ ᴀʟʟ ᴄʜᴀɴɴᴇʟꜱ ꜰɪʀꜱᴛ.", show_alert=True)

# ─── FILE SHARING & 30 MIN AUTO-DELETE LOGIC ───
async def send_batch_files(update: Update, context: ContextTypes.DEFAULT_TYPE, batch_id: str):
    user_id = update.effective_user.id
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. SAFELY FETCH FILES FIRST (SUPPORTS OLD LINKS WITHOUT BATCH HEADER)
    c.execute("SELECT from_chat_id, message_id, caption FROM files WHERE batch_id = ? ORDER BY id", (batch_id,))
    files = c.fetchall()

    if not files:
        await context.bot.send_message(user_id, "🚫 <b>ᴇʀʀᴏʀ:</b> ꜰɪʟᴇ ɴᴏᴛ ꜰᴏᴜɴᴅ ᴏʀ ᴅᴇʟᴇᴛᴇᴅ.", parse_mode=ParseMode.HTML)
        conn.close()
        return

    # 2. SAFELY FETCH IS_PROTECTED STATUS
    is_protected = False
    try:
        c.execute("SELECT is_protected FROM batches WHERE batch_id = ?", (batch_id,))
        batch_res = c.fetchone()
        if batch_res:
            is_protected = bool(batch_res[0])
    except Exception:
        pass # Ignore error if table structure is old
        
    conn.close()

    log_access(user_id, batch_id)
    status_msg = await context.bot.send_message(user_id, "⏳ <code>ᴘʀᴏᴄᴇꜱꜱɪɴɢ ʏᴏᴜʀ ꜰɪʟᴇꜱ...</code>", parse_mode=ParseMode.HTML)

    sent_msg_ids = []
    for from_chat, msg_id, caption in files:
        try:
            msg = await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=from_chat,
                message_id=msg_id,
                caption=caption,
                protect_content=is_protected, # Applied forwarding logic
                parse_mode=ParseMode.HTML
            )
            sent_msg_ids.append(msg.message_id)
            await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Send Error: {e}")

    await status_msg.delete()
    
    # Send 30 Min Alert Notification
    alert_txt = (
        f"⚠️ <b>ᴀʟᴇʀᴛ :</b>\n"
        f"<blockquote>ᴛʜᴇꜱᴇ ꜰɪʟᴇꜱ ᴡɪʟʟ ʙᴇ ᴀᴜᴛᴏᴍᴀᴛɪᴄᴀʟʟʏ ᴅᴇʟᴇᴛᴇᴅ ɪɴ <b>30 ᴍɪɴᴜᴛᴇꜱ</b> ꜰᴏʀ ꜱᴇᴄᴜʀɪᴛʏ. ᴘʟᴇᴀꜱᴇ ᴡᴀᴛᴄʜ ᴏʀ ꜱᴀᴠᴇ ᴛʜᴇᴍ!</blockquote>"
    )
    alert_msg = await context.bot.send_message(user_id, alert_txt, parse_mode=ParseMode.HTML)
    sent_msg_ids.append(alert_msg.message_id)

    # Start 30 min (1800s) delete schedule
    asyncio.create_task(schedule_auto_delete(context.bot, user_id, sent_msg_ids, AUTO_DELETE_SECONDS, batch_id))

async def schedule_auto_delete(bot, chat_id, message_ids, delay, batch_id):
    await asyncio.sleep(delay)
    deleted = False
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=mid)
            deleted = True
        except: pass 

    if deleted:
        keyboard = [[InlineKeyboardButton("🔄 ɢᴇᴛ ꜰɪʟᴇꜱ ᴀɢᴀɪɴ", callback_data=f"get_again_{batch_id}")]]
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="🗑️ <b>ᴛɪᴍᴇ ᴜᴘ! ꜰɪʟᴇꜱ ᴅᴇʟᴇᴛᴇᴅ.</b>\n\n<i>30 ᴍɪɴᴜᴛᴇꜱ ᴛɪᴍᴇ ʟɪᴍɪᴛ ᴇxᴘɪʀᴇᴅ.</i>",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.HTML
            )
        except: pass

async def get_again_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    batch_id = query.data.split("_")[2]
    await query.answer()
    
    try: await query.message.delete()
    except: pass
    
    await send_batch_files(update, context, batch_id)

# ==============================================================================
# ADMIN PANEL 
# ==============================================================================
async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛡️ <b>ᴀᴅᴍɪɴ ᴅᴀꜱʜʙᴏᴀʀᴅ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<blockquote>ᴍᴀɴᴀɢᴇ ʏᴏᴜʀ ꜰɪʟᴇꜱ, ʙʀᴏᴀᴅᴄᴀꜱᴛꜱ, ᴀɴᴅ ᴠɪᴇᴡ ʙᴏᴛ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ ꜰʀᴏᴍ ʜᴇʀᴇ.</blockquote>\n\n"
        "<i>ᴘʟᴇᴀꜱᴇ ꜱᴇʟᴇᴄᴛ ᴀɴ ᴏᴘᴛɪᴏɴ ʙᴇʟᴏᴡ:</i>"
    )
    keyboard = [
        [InlineKeyboardButton("📂 ᴄʀᴇᴀᴛᴇ ꜰɪʟᴇ ʟɪɴᴋ", callback_data="admin_create_link")],
        [InlineKeyboardButton("📡 ʙʀᴏᴀᴅᴄᴀꜱᴛ / ꜰᴏʀᴇᴄᴀꜱᴛ", callback_data="broadcast_menu")],
        [InlineKeyboardButton("➕ ᴀᴅᴅ ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟ", callback_data="admin_add_force"),
         InlineKeyboardButton("➖ ʀᴇᴍᴏᴠᴇ ᴄʜᴀɴɴᴇʟ", callback_data="admin_rem_channel")],
        [InlineKeyboardButton("📊 ᴜꜱᴇʀ & ʟɪɴᴋ ꜱᴛᴀᴛꜱ", callback_data="admin_stats")]
    ]
    if update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

# --- FORCE CHANNELS ---
async def admin_add_force_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "📌 <b>ᴀᴅᴅ ꜰᴏʀᴄᴇ ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ</b>\n\n"
        "<blockquote>ꜰᴏʀᴡᴀʀᴅ ᴀɴʏ ᴍᴇꜱꜱᴀɢᴇ ꜰʀᴏᴍ ᴛʜᴇ ᴄʜᴀɴɴᴇʟ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴀᴅᴅ.\n"
        "⚠️ ɴᴏᴛᴇ: ɪ ᴍᴜꜱᴛ ʙᴇ ᴀɴ ᴀᴅᴍɪɴ ɪɴ ᴛʜᴀᴛ ᴄʜᴀɴɴᴇʟ.</blockquote>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ᴄᴀɴᴄᴇʟ", callback_data="admin_home")]]),
        parse_mode=ParseMode.HTML
    )
    return ADD_CHANNEL_FWD

async def admin_add_force_fwd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    origin = getattr(msg, 'forward_origin', None)
    if not origin or origin.type != 'channel':
        await msg.reply_text("❌ ᴘʟᴇᴀꜱᴇ ꜰᴏʀᴡᴀʀᴅ ꜰʀᴏᴍ ᴀ <b>ᴄʜᴀɴɴᴇʟ</b>.", parse_mode=ParseMode.HTML)
        return ADD_CHANNEL_FWD

    chat = origin.chat
    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status != 'administrator':
            await msg.reply_text("⚠️ ɪ ᴀᴍ ɴᴏᴛ ᴀɴ ᴀᴅᴍɪɴ ᴛʜᴇʀᴇ! ᴘʟᴇᴀꜱᴇ ᴘʀᴏᴍᴏᴛᴇ ᴍᴇ ꜰɪʀꜱᴛ.")
            return ADD_CHANNEL_FWD
    except:
        await msg.reply_text("⚠️ ᴇʀʀᴏʀ ᴀᴄᴄᴇꜱꜱɪɴɢ ᴄʜᴀɴɴᴇʟ.")
        return ADD_CHANNEL_FWD

    context.user_data['new_channel_id'] = chat.id
    context.user_data['new_channel_title'] = chat.title or "Unknown"

    invite_link = None
    try: 
        link_obj = await context.bot.create_chat_invite_link(chat.id, "ForceJoinBot", creates_join_request=True)
        invite_link = link_obj.invite_link
    except: 
        try: invite_link = await context.bot.export_chat_invite_link(chat.id)
        except: pass

    if invite_link:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO channels (chat_id, title, invite_link) VALUES (?, ?, ?)", (chat.id, chat.title, invite_link))
        conn.commit()
        conn.close()
        await msg.reply_text(f"✅ <b>ᴄʜᴀɴɴᴇʟ ᴀᴅᴅᴇᴅ:</b> {chat.title}\n<code>ʟɪɴᴋ: {invite_link}</code>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ᴍᴇɴᴜ", callback_data="admin_home")]]), parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    await msg.reply_text(f"✅ ᴅᴇᴛᴇᴄᴛᴇᴅ: {chat.title}\n❌ ᴀᴜᴛᴏ-ʟɪɴᴋ ꜰᴀɪʟᴇᴅ. ꜱᴇɴᴅ <b>ɪɴᴠɪᴛᴇ ʟɪɴᴋ</b> ᴍᴀɴᴜᴀʟʟʏ.", parse_mode=ParseMode.HTML)
    return ADD_CHANNEL_LINK

async def admin_add_force_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    c_id = context.user_data['new_channel_id']
    title = context.user_data['new_channel_title']
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO channels (chat_id, title, invite_link) VALUES (?, ?, ?)", (c_id, title, link))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ <b>ᴀᴅᴅᴇᴅ:</b> {title}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ᴍᴇɴᴜ", callback_data="admin_home")]]), parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_remove_channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT chat_id, title FROM channels")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await query.message.edit_text("❌ ɴᴏ ᴄʜᴀɴɴᴇʟꜱ ꜰᴏᴜɴᴅ.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_home")]]))
        return
    buttons = [[InlineKeyboardButton(f"❌ {r[1]}", callback_data=f"del_ch_{r[0]}")] for r in rows]
    buttons.append([InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_home")])
    await query.message.edit_text("📋 <b>ꜱᴇʟᴇᴄᴛ ᴄʜᴀɴɴᴇʟ ᴛᴏ ʀᴇᴍᴏᴠᴇ</b>", reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML)

async def delete_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cid = int(query.data.split("_")[2])
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM channels WHERE chat_id = ?", (cid,))
    conn.commit()
    conn.close()
    await query.answer("ᴄʜᴀɴɴᴇʟ ᴅᴇʟᴇᴛᴇᴅ!")
    await show_admin_panel(update, context)

# --- CREATE LINK WITH PROTECTION OPTION ---
async def admin_create_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['batch_files'] = []
    
    msg = (
        "📂 <b>ᴄʀᴇᴀᴛᴇ ꜰɪʟᴇ ʟɪɴᴋ</b>\n\n"
        "<blockquote>ꜱᴇɴᴅ ʏᴏᴜʀ ꜰɪʟᴇꜱ/ᴠɪᴅᴇᴏꜱ ʜᴇʀᴇ. ʏᴏᴜ ᴄᴀɴ ꜱᴇɴᴅ ᴍᴜʟᴛɪᴘʟᴇ ꜰɪʟᴇꜱ ᴀᴛ ᴏɴᴄᴇ.</blockquote>\n\n"
        "<i>ᴡʜᴇɴ ꜰɪɴɪꜱʜᴇᴅ, ᴛʏᴘᴇ <code>/done</code>.</i>"
    )
    
    await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ᴄᴀɴᴄᴇʟ", callback_data="admin_home")]]), parse_mode=ParseMode.HTML)
    return CREATE_LINK_WAIT

async def admin_create_link_collect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text.startswith('/'): return CREATE_LINK_WAIT
    file_info = {
        'chat_id': update.message.chat.id,
        'message_id': update.message.message_id,
        'caption': update.message.caption_html or ""
    }
    context.user_data['batch_files'].append(file_info)
    await update.message.reply_text(f"✅ <i>ꜰɪʟᴇ #{len(context.user_data['batch_files'])} ᴀᴅᴅᴇᴅ.</i>", parse_mode=ParseMode.HTML)
    return CREATE_LINK_WAIT

async def admin_create_link_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    files = context.user_data.get('batch_files')
    if not files:
        await update.message.reply_text("❌ ɴᴏ ꜰɪʟᴇꜱ ꜱᴇɴᴛ.")
        return ConversationHandler.END
        
    await update.message.reply_text(
        "🔐 <b>ᴇɴᴀʙʟᴇ ᴄᴏɴᴛᴇɴᴛ ᴘʀᴏᴛᴇᴄᴛɪᴏɴ?</b>\n"
        "<i>(ᴘʀᴇᴠᴇɴᴛꜱ ᴜꜱᴇʀꜱ ꜰʀᴏᴍ ꜰᴏʀᴡᴀʀᴅɪɴɢ ᴏʀ ꜱᴀᴠɪɴɢ)</i>", 
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 ᴘʀᴏᴛᴇᴄᴛᴇᴅ (ᴏɴ)", callback_data="prot_yes")], 
            [InlineKeyboardButton("🔓 ᴘᴜʙʟɪᴄ (ᴏꜰꜰ)", callback_data="prot_no")]
        ]), 
        parse_mode=ParseMode.HTML
    )
    return CREATE_LINK_CONFIRM

async def admin_create_link_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    is_protected = 1 if query.data == "prot_yes" else 0
    batch_id = generate_unique_id()
    files = context.user_data['batch_files']
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO batches (batch_id, file_count, is_protected) VALUES (?, ?, ?)", (batch_id, len(files), is_protected))
    for f in files:
        c.execute("INSERT INTO files (batch_id, from_chat_id, message_id, caption) VALUES (?, ?, ?, ?)", 
                  (batch_id, f['chat_id'], f['message_id'], f['caption']))
    conn.commit()
    conn.close()
    
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={batch_id}"
    
    prot_status = "ᴇɴᴀʙʟᴇᴅ 🔒" if is_protected else "ᴅɪꜱᴀʙʟᴇᴅ 🔓"
    res_msg = (
        f"✅ <b>ꜰɪʟᴇ ʟɪɴᴋ ᴄʀᴇᴀᴛᴇᴅ!</b>\n\n"
        f"<b>ᴛᴏᴛᴀʟ ꜰɪʟᴇꜱ:</b> {len(files)}\n"
        f"<b>ᴘʀᴏᴛᴇᴄᴛɪᴏɴ:</b> {prot_status}\n"
        f"<b>ꜱʜᴀʀᴇᴀʙʟᴇ ʟɪɴᴋ:</b>\n<pre>{link}</pre>"
    )
    
    await query.message.edit_text(res_msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ᴍᴇɴᴜ", callback_data="admin_home")]]), parse_mode=ParseMode.HTML)
    return ConversationHandler.END


# --- BROADCAST ---
async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        f"📡 <b>ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜱʏꜱᴛᴇᴍ</b>\n\n"
        "<blockquote expandable>"
        "<b>📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ (ᴄᴏᴘʏ):</b> ᴍᴇꜱꜱᴀɢᴇ ɪꜱ ᴄᴏᴘɪᴇᴅ ᴀɴᴅ ꜱᴇɴᴛ.\n\n"
        "<b>⏩ ꜰᴏʀᴇᴄᴀꜱᴛ (ꜰᴏʀᴡᴀʀᴅ):</b> ᴍᴇꜱꜱᴀɢᴇ ɪꜱ ꜰᴏʀᴡᴀʀᴅᴇᴅ ᴡɪᴛʜ ᴛᴀɢ."
        "</blockquote>\n\n"
        "👇 <b>ꜱᴇʟᴇᴄᴛ ᴛʏᴘᴇ:</b>"
    )
    keyboard = [
        [InlineKeyboardButton("📢 ʙʀᴏᴀᴅᴄᴀꜱᴛ (ᴄᴏᴘʏ)", callback_data="mode_broadcast")],
        [InlineKeyboardButton("⏩ ꜰᴏʀᴇᴄᴀꜱᴛ (ꜰᴏʀᴡᴀʀᴅ)", callback_data="mode_forecast")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_home")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return BROADCAST_CHOOSE_TYPE

async def broadcast_ask_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data['broadcast_mode'] = query.data
    context.user_data['broadcast_msg'] = None
    
    await query.message.edit_text(
        f"📩 <b>ꜱᴇɴᴅ ʏᴏᴜʀ ᴍᴇꜱꜱᴀɢᴇ ɴᴏᴡ.</b>\n"
        "<i>ʏᴏᴜ ᴄᴀɴ ꜱᴇɴᴅ ᴘʜᴏᴛᴏ, ᴠɪᴅᴇᴏ, ᴏʀ ᴛᴇxᴛ.</i>\n\n", 
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("ᴄᴀɴᴄᴇʟ", callback_data="admin_home")]]), 
        parse_mode=ParseMode.HTML
    )
    return BROADCAST_RECEIVE_MSG

async def broadcast_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    mode = context.user_data.get('broadcast_mode')
    
    await update.message.reply_text("🚀 <b>ʙʀᴏᴀᴅᴄᴀꜱᴛɪɴɢ ꜱᴛᴀʀᴛᴇᴅ...</b>", parse_mode=ParseMode.HTML)
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()
    
    success, failed = 0, 0
    for uid in users:
        try:
            if mode == "mode_broadcast":
                await context.bot.copy_message(chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
            else:
                await context.bot.forward_message(chat_id=uid, from_chat_id=msg.chat_id, message_id=msg.message_id)
            success += 1
            await asyncio.sleep(0.05)
        except:
            failed += 1
            
    await update.message.reply_text(
        f"✅ <b>ʙʀᴏᴀᴅᴄᴀꜱᴛ ꜰɪɴɪꜱʜᴇᴅ!</b>\n\n"
        f"🟢 <b>ꜱᴜᴄᴄᴇꜱꜱ:</b> {success}\n"
        f"🔴 <b>ꜰᴀɪʟᴇᴅ/ʙʟᴏᴄᴋᴇᴅ:</b> {failed}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 ᴍᴇɴᴜ", callback_data="admin_home")]]),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


# --- STATISTICS ---
async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # User Stats
    user_count = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    ch_count = c.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
    link_count = c.execute("SELECT COUNT(*) FROM batches").fetchone()[0]
    
    # Top 5 Links Stats
    c.execute("""
        SELECT b.batch_id, COUNT(a.id), b.file_count 
        FROM batches b 
        LEFT JOIN access_logs a ON b.batch_id = a.batch_id 
        GROUP BY b.batch_id 
        ORDER BY COUNT(a.id) DESC 
        LIMIT 5
    """)
    top_links = c.fetchall()
    conn.close()
    
    stats_text = (
        f"📊 <b>ʙᴏᴛ & ʟɪɴᴋ ꜱᴛᴀᴛɪꜱᴛɪᴄꜱ</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>ᴛᴏᴛᴀʟ ᴜꜱᴇʀꜱ:</b> <code>{user_count}</code>\n"
        f"📢 <b>ꜰᴏʀᴄᴇ ᴄʜᴀɴɴᴇʟꜱ:</b> <code>{ch_count}</code>\n"
        f"🔗 <b>ᴛᴏᴛᴀʟ ʟɪɴᴋꜱ:</b> <code>{link_count}</code>\n\n"
        f"🏆 <b>ᴛᴏᴘ 5 ʟɪɴᴋꜱ (ᴍᴏꜱᴛ ᴏᴘᴇɴᴇᴅ):</b>\n"
        f"<blockquote>\n"
    )
    
    if not top_links:
        stats_text += "ɴᴏ ᴅᴀᴛᴀ ᴀᴠᴀɪʟᴀʙʟᴇ ʏᴇᴛ.\n"
    else:
        for bid, hits, f_count in top_links:
            stats_text += f"ɪᴅ: <code>{bid}</code> | 👁 {hits} ᴠɪᴇᴡꜱ | 📂 {f_count} ꜰɪʟᴇꜱ\n"
            
    stats_text += "</blockquote>"
    
    await query.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="admin_home")]]),
        parse_mode=ParseMode.HTML
    )

async def cancel_op(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_admin_panel(update, context)
    return ConversationHandler.END

# ==============================================================================
# MAIN INIT
# ==============================================================================
async def post_init_logic(app: Application):
    await app.bot.set_my_commands([
        BotCommand("start", "Start Bot"), 
        BotCommand("admin", "Admin Panel")
    ])

def main():
    init_db()
    application = Application.builder().token(BOT_TOKEN).post_init(post_init_logic).build()

    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, global_message_handler), group=1)
    
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("admin", lambda u, c: show_admin_panel(u, c) if is_admin(u.effective_user.id) else None))
    
    application.add_handler(ChatJoinRequestHandler(process_join_request))
    application.add_handler(CallbackQueryHandler(verify_callback, pattern="^verify_join$"))
    
    # Reload files button handler
    application.add_handler(CallbackQueryHandler(get_again_callback, pattern="^get_again_"))

    # Force Channels
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_force_start, pattern="^admin_add_force$")],
        states={
            ADD_CHANNEL_FWD: [MessageHandler(filters.FORWARDED, admin_add_force_fwd)],
            ADD_CHANNEL_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_force_save)],
        },
        fallbacks=[CallbackQueryHandler(cancel_op, pattern="^admin_home$")]
    ))
    
    # Create Links
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_create_link_start, pattern="^admin_create_link$")],
        states={
            CREATE_LINK_WAIT: [
                MessageHandler(filters.ALL & ~filters.COMMAND, admin_create_link_collect),
                CommandHandler("done", admin_create_link_done)
            ],
            CREATE_LINK_CONFIRM: [
                CallbackQueryHandler(admin_create_link_save, pattern="^prot_")
            ]
        },
        fallbacks=[CallbackQueryHandler(cancel_op, pattern="^admin_home$")]
    ))

    # Broadcast
    application.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_menu, pattern="^broadcast_menu$")],
        states={
            BROADCAST_CHOOSE_TYPE: [CallbackQueryHandler(broadcast_ask_msg, pattern="^mode_")],
            BROADCAST_RECEIVE_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_run)]
        },
        fallbacks=[CallbackQueryHandler(cancel_op, pattern="^admin_home$")]
    ))

    application.add_handler(CallbackQueryHandler(show_admin_panel, pattern="^admin_home$"))
    application.add_handler(CallbackQueryHandler(admin_remove_channel_menu, pattern="^admin_rem_channel$"))
    application.add_handler(CallbackQueryHandler(delete_channel_callback, pattern="^del_ch_"))
    application.add_handler(CallbackQueryHandler(show_statistics, pattern="^admin_stats$"))
    
    logger.info("🤖 Clean Unicode File Sharing Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
