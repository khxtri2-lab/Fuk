#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
 SUNRAKU — ADVANCED FILE RUNNER BOT 
- User file upload karega
- Bot automatically BOT_TOKEN + CHAT_ID replace karega
- Approval system (owner approve karega)
- Run/Stop/Logs/Status/Speed controls
- LIVE STATUS + SPEED FIXED
- Default file (fast hits) bhi available
- Dev: @SunrakuV2 | Channel: @Anishpy | @VOUCH_R
"""
import os
import sys
import time
import random
import json
import re
import select
import requests
import threading
import subprocess
import shutil
import unicodedata
from datetime import datetime, timedelta
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
# ============================================================
#  ENVIRONMENT VARIABLE
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    print("❌ BOT_TOKEN environment variable not set!")
    sys.exit()
bot = TeleBot(BOT_TOKEN)
# ============================================================
#  GLOBALS
# ============================================================
user_sessions = {}
lock = threading.Lock()
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
#  Owner Chat ID (Approval ke liye)
OWNER_CHAT_ID = 8641613327

# ============================================================
#  USERS / CREDITS / ADMIN DATA
# ============================================================
# Data is kept in a small JSON file so credits and user IDs survive
# a bot restart.  One credit activates 24 hours of access on first use.
USER_DATA_FILE = "users_data.json"
CREDIT_HOURS = 24
user_data_lock = threading.Lock()
user_data = {}
pending_broadcast = {}

def load_user_data():
    global user_data
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as data_file:
            loaded = json.load(data_file)
        user_data = loaded if isinstance(loaded, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        user_data = {}

def save_user_data():
    temp_file = f"{USER_DATA_FILE}.tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as data_file:
            json.dump(user_data, data_file, ensure_ascii=False, indent=2)
        os.replace(temp_file, USER_DATA_FILE)
    except OSError as exc:
        print(f"⚠️ Could not save user data: {exc}")

def ensure_user_record(chat_id, user=None):
    key = str(chat_id)
    with user_data_lock:
        record = user_data.setdefault(key, {
            "credits": 0,
            "active_until": None,
            "blocked": False,
            "name": "",
            "username": "",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "last_seen": datetime.now().isoformat(timespec="seconds"),
        })
        if user is not None:
            record["name"] = " ".join(
                part for part in [user.first_name, user.last_name] if part
            ).strip()
            record["username"] = user.username or ""
        record["last_seen"] = datetime.now().isoformat(timespec="seconds")
        save_user_data()
        return record.copy()

def is_admin(chat_id):
    return int(chat_id) == int(OWNER_CHAT_ID)

def active_until_for(record):
    raw_value = record.get("active_until")
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(raw_value)
    except (TypeError, ValueError):
        return None

def access_status(chat_id):
    if is_admin(chat_id):
        return True, "♾️ Admin access"
    record = ensure_user_record(chat_id)
    active_until = active_until_for(record)
    now = datetime.now()
    if active_until and active_until > now:
        remaining = active_until - now
        hours = max(1, int(remaining.total_seconds() // 3600))
        return True, f"✅ Active — about {hours} hour(s) left"
    if record.get("credits", 0) > 0:
        return False, f"💳 {record['credits']} credit(s) available"
    return False, "❌ No active credit"

def activate_credit(chat_id):
    """Use one credit only when the user first starts using the service."""
    if is_admin(chat_id):
        return True, "♾️ Admin access"
    with user_data_lock:
        record = user_data.setdefault(str(chat_id), {
            "credits": 0,
            "active_until": None,
            "blocked": False,
            "name": "",
            "username": "",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "last_seen": datetime.now().isoformat(timespec="seconds"),
        })
        if record.get("blocked"):
            return False, "🚫 Your access is blocked by the admin."
        current_until = active_until_for(record)
        now = datetime.now()
        if current_until and current_until > now:
            return True, f"✅ Access active until {current_until.strftime('%d-%m-%Y %H:%M')}"
        if int(record.get("credits", 0)) <= 0:
            return False, "❌ No credit available. Contact the admin."
        record["credits"] = int(record.get("credits", 0)) - 1
        record["active_until"] = (now + timedelta(hours=CREDIT_HOURS)).isoformat(timespec="seconds")
        save_user_data()
        return True, f"✅ 1 credit activated for {CREDIT_HOURS} hours."

def require_access(message, activate=True):
    chat_id = message.chat.id
    record = ensure_user_record(chat_id, getattr(message, "from_user", None))
    if record.get("blocked") and not is_admin(chat_id):
        bot.reply_to(message, "🚫 **Your access is blocked by the admin.**", parse_mode="Markdown")
        return False
    allowed, status = access_status(chat_id)
    if allowed:
        return True
    if activate:
        allowed, status = activate_credit(chat_id)
        if allowed:
            bot.reply_to(message, status, parse_mode="Markdown")
            return True
    bot.reply_to(
        message,
        "🔒 **Active credit required.**\n\n"
        f"{status}\n"
        "Please contact the admin to get credits.",
        parse_mode="Markdown",
    )
    return False

def credits_text(chat_id):
    if is_admin(chat_id):
        return "💳 **CREDITS**\n\n♾️ You are the owner — unlimited access."
    record = ensure_user_record(chat_id)
    active_until = active_until_for(record)
    if active_until and active_until > datetime.now():
        active_line = f"✅ Active until: `{active_until.strftime('%d-%m-%Y %H:%M')}`"
    else:
        active_line = "⏳ No active 24-hour session"
    return (
        "💳 **MY CREDITS**\n\n"
        f"Available credits: `{record.get('credits', 0)}`\n"
        f"{active_line}\n\n"
        "1 credit = 24 hours. A credit is used only when you start using "
        "the service, and it can be used anytime during that 24-hour window."
    )

load_user_data()
# ============================================================
#  USER SESSION MANAGER (Fully Fixed)
# ============================================================
class UserSession:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.file_path = None
        self.process = None
        self.is_running = False
        self.is_approved = False
        self.logs = []
        self.start_time = None
        self.end_time = None
        self.speed = 0
        self.total_checks = 0
        self.installed_packages = []
        self.awaiting_input = False
        self.input_prompt = ""
        self.files = []
        self.lock = threading.Lock()
    def add_log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {msg}")
        if len(self.logs) > 200:
            self.logs.pop(0)
    def get_logs(self, lines=25):
        return "\n".join(self.logs[-lines:]) if self.logs else "No logs yet."
    def get_runtime(self):
        if self.start_time:
            end_time = self.end_time or datetime.now()
            diff = end_time - self.start_time
            return str(diff).split('.')[0]
        return "N/A"
    def get_speed(self):
        if self.start_time:
            end_time = self.end_time or datetime.now()
            runtime_seconds = max((end_time - self.start_time).total_seconds(), 1)
            speed = int((self.total_checks / runtime_seconds) * 60)
            self.speed = speed
            return speed
        return self.speed or 0
ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
INPUT_PROMPT_RE = re.compile(
    r"(chat\s*id|user\s*name|username|password|token|email|phone|"
    r"number|choice|select|option|proxy|path|file|url|key|code|"
    r"confirm|yes/no|enter|input|➜|:\s*$)",
    re.IGNORECASE
)
def clean_console_prompt(text):
    """Remove ANSI styling before sending a terminal prompt to Telegram."""
    text = ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\x00", "").strip()
    return text[-700:] if len(text) > 700 else text
def looks_like_input_prompt(text):
    return bool(text and INPUT_PROMPT_RE.search(text))
def ask_user_for_process_input(session, prompt):
    """Forward an interactive child-process prompt to the user's Telegram chat."""
    prompt = clean_console_prompt(prompt)
    if not prompt or session.awaiting_input:
        return
    session.awaiting_input = True
    session.input_prompt = prompt
    session.add_log(f" Waiting for input: {prompt}")
    try:
        # Show the complete stored log before asking for the next value.
        full_log = session.get_logs(200)
        if not full_log:
            full_log = "No log output yet."
        log_chunks = [
            full_log[i:i + 3500]
            for i in range(0, len(full_log), 3500)
        ]
        for chunk_number, chunk in enumerate(log_chunks, start=1):
            header = " FULL FILE LOG"
            if len(log_chunks) > 1:
                header += f" ({chunk_number}/{len(log_chunks)})"
            bot.send_message(session.chat_id, f"{header}\n\n{chunk}")
        prompt_message = bot.send_message(
            session.chat_id,
            " Your file needs input:\n\n"
            f"{prompt}\n\n"
            "Reply to this message with the value. "
            "I will send it to the running file automatically.",
        )
        bot.register_next_step_handler(prompt_message, send_process_input)
    except Exception as e:
        session.awaiting_input = False
        session.add_log(f"❌ Could not request input: {e}")
def add_file_to_session(session, file_path, file_name, approved=False):
    """Add or replace a file record for this user's file list."""
    session.files = [
        entry for entry in session.files
        if entry.get("path") != file_path
    ]
    session.files.append({
        "path": file_path,
        "name": file_name,
        "approved": approved
    })
def discover_user_files(session):
    """Restore this user's uploaded files after a bot restart."""
    try:
        for file_name in os.listdir(UPLOAD_DIR):
            if not file_name.endswith(".py"):
                continue
            if not file_name.startswith(f"{session.chat_id}_"):
                continue
            file_path = os.path.join(UPLOAD_DIR, file_name)
            if not os.path.isfile(file_path):
                continue
            if not any(entry.get("path") == file_path for entry in session.files):
                add_file_to_session(session, file_path, file_name, approved=False)
    except OSError:
        pass
def get_file_entry(session, index):
    if index < 0 or index >= len(session.files):
        return None
    entry = session.files[index]
    if not os.path.exists(entry.get("path", "")):
        return None
    return entry
def file_manager_markup(session):
    markup = InlineKeyboardMarkup(row_width=2)
    for index, entry in enumerate(session.files):
        if not os.path.exists(entry.get("path", "")):
            continue
        selected = "⭐ " if entry.get("path") == session.file_path else ""
        approved = "✅" if entry.get("approved") else "⏳"
        label = f"{approved} {selected}{index + 1}. {entry.get('name', 'file')}"
        markup.add(
            InlineKeyboardButton(
                label[:60],
                callback_data=f"select_file_{session.chat_id}_{index}"
            ),
            InlineKeyboardButton(
                " DELETE",
                callback_data=f"delete_file_{session.chat_id}_{index}"
            )
        )
    return markup
def file_manager_text(session):
    existing = [
        entry for entry in session.files
        if os.path.exists(entry.get("path", ""))
    ]
    if not existing:
        return (
            " MY FILES\n\n"
            "No uploaded files found.\n"
            "Use UPLOAD FILE to add one."
        )
    lines = [" MY FILES", "", "Tap a file button to select it:"]
    for index, entry in enumerate(session.files):
        if not os.path.exists(entry.get("path", "")):
            continue
        selected = " ⭐ SELECTED" if entry.get("path") == session.file_path else ""
        status = "APPROVED" if entry.get("approved") else "PENDING"
        lines.append(f"{index + 1}. {entry.get('name', 'file')} — {status}{selected}")
    lines.append("")
    lines.append("Selected file can be run with RUN FILE.")
    return "\n".join(lines)
# ============================================================
#  APPROVAL SYSTEM
# ============================================================
def send_approval_request(user_chat_id, file_name, file_path):
    msg = f"""
 **NEW FILE UPLOADED - APPROVAL NEEDED**
 User ID: `{user_chat_id}`
 File: `{file_name}`
 Path: `{file_path}`
 Click Approve to allow user to run this file.
"""
    markup = InlineKeyboardMarkup(row_width=2)
    btn_approve = InlineKeyboardButton(
        text="✅ APPROVE",
        callback_data=f"approve_{user_chat_id}_{file_path}"
    )
    btn_reject = InlineKeyboardButton(
        text="❌ REJECT",
        callback_data=f"reject_{user_chat_id}"
    )
    markup.add(btn_approve, btn_reject)
    try:
        bot.send_message(OWNER_CHAT_ID, msg, reply_markup=markup, parse_mode='Markdown')
        return True
    except Exception as e:
        print(f"Approval send error: {e}")
        return False
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def approve_file(call):
    data = call.data.split("_")
    user_chat_id = int(data[1])
    file_path = "_".join(data[2:])
    with lock:
        if user_chat_id not in user_sessions:
            bot.answer_callback_query(call.id, "❌ User session not found!")
            return
        session = user_sessions[user_chat_id]
        session.is_approved = True
        for entry in session.files:
            if entry.get("path") == file_path:
                entry["approved"] = True
        session.add_log("✅ File approved by owner")
    bot.edit_message_text(
        f"✅ **File Approved!**\n User: `{user_chat_id}`\n File: `{os.path.basename(file_path)}`\n\nUser can now run the file.",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    try:
        bot.send_message(
            user_chat_id,
            f"✅ **Your file has been approved!**\n\n `{os.path.basename(file_path)}`\n Click **RUN FILE** to start.",
            parse_mode='Markdown'
        )
    except:
        pass
    bot.answer_callback_query(call.id, "✅ Approved!")
@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_"))
def reject_file(call):
    user_chat_id = int(call.data.split("_")[1])
    with lock:
        if user_chat_id in user_sessions:
            session = user_sessions[user_chat_id]
            session.is_approved = False
            for entry in session.files:
                if entry.get("path") == session.file_path:
                    entry["approved"] = False
            session.add_log("❌ File rejected by owner")
    bot.edit_message_text(
        f"❌ **File Rejected!**\n User: `{user_chat_id}`\n\nFile has been rejected by owner.",
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown'
    )
    try:
        bot.send_message(
            user_chat_id,
            "❌ **Your file has been rejected by the owner.**\n\nPlease contact @SunrakuV2 for approval.",
            parse_mode='Markdown'
        )
    except:
        pass
    bot.answer_callback_query(call.id, "❌ Rejected!")
# ============================================================
#  BOT COMMANDS & BUTTONS
# ============================================================
def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        KeyboardButton("➕ 𝑨𝑫𝑫 𝑪𝑹𝑬𝑫𝑰𝑻𝑺"),
        KeyboardButton("➖ 𝑹𝑬𝑴𝑶𝑽𝑬 𝑪𝑹𝑬𝑫𝑰𝑻𝑺"),
        KeyboardButton("📢 𝑩𝑹𝑶𝑨𝑫𝑪𝑨𝑺𝑻"),
        KeyboardButton("👥 𝑼𝑺𝑬𝑹𝑺"),
        KeyboardButton("🔙 𝑴𝑨𝑰𝑵 𝑴𝑬𝑵𝑼"),
    )
    return markup

def admin_only(message):
    if not is_admin(message.chat.id):
        bot.reply_to(message, "❌ **Admin-only button.**", parse_mode="Markdown")
        return False
    return True

def admin_panel_message(message):
    if not admin_only(message):
        return
    bot.reply_to(
        message,
        "🛠 **ADMIN PANEL**\n\n"
        "➕ Add credits: `user_id amount`\n"
        "➖ Remove credits: `user_id amount`\n"
        "📢 Broadcast a text message to all users\n"
        "👥 View registered users and their access status",
        reply_markup=admin_menu(),
        parse_mode="Markdown",
    )

@bot.message_handler(commands=["admin"])
def admin_command(message):
    admin_panel_message(message)

@bot.message_handler(func=lambda msg: msg.text == "🛠  𝑨𝑫𝑴𝑰𝑵 𝑷𝑨𝑵𝑬𝑳")
def admin_panel_button(message):
    admin_panel_message(message)

@bot.message_handler(func=lambda msg: msg.text == "🔙 𝑴𝑨𝑰𝑵 𝑴𝑬𝑵𝑼")
def back_to_main_menu(message):
    if not admin_only(message):
        return
    bot.reply_to(message, "✅ **Main menu opened.**", reply_markup=main_menu(message.chat.id), parse_mode="Markdown")

def credit_change_prompt(message, operation):
    if not admin_only(message):
        return
    prompt = bot.reply_to(
        message,
        f"{'➕ ADD' if operation == 'add' else '➖ REMOVE'} **CREDITS**\n\n"
        "Send: `user_id amount`\n"
        "Example: `123456789 3`\n\n"
        "Type `/cancel` to cancel.",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(prompt, process_credit_change, operation)

@bot.message_handler(func=lambda msg: msg.text == "➕ 𝑨𝑫𝑫 𝑪𝑹𝑬𝑫𝑰𝑻𝑺")
def add_credits_button(message):
    credit_change_prompt(message, "add")

@bot.message_handler(func=lambda msg: msg.text == "➖ 𝑹𝑬𝑴𝑶𝑽𝑬 𝑪𝑹𝑬𝑫𝑰𝑻𝑺")
def remove_credits_button(message):
    credit_change_prompt(message, "remove")

def process_credit_change(message, operation):
    if not is_admin(message.chat.id):
        return
    raw_text = (message.text or "").strip()
    if raw_text.lower() == "/cancel":
        bot.reply_to(message, "❎ **Cancelled.**", reply_markup=admin_menu(), parse_mode="Markdown")
        return
    parts = raw_text.split()
    if len(parts) != 2:
        bot.reply_to(
            message,
            "❌ Format galat. Example: `123456789 3`",
            parse_mode="Markdown",
        )
        return
    try:
        target_id = int(parts[0])
        amount = int(parts[1])
        if target_id <= 0 or amount <= 0 or amount > 100000:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "❌ User ID aur amount valid positive numbers hone chahiye.")
        return
    record = ensure_user_record(target_id)
    with user_data_lock:
        current = int(record.get("credits", 0))
        new_value = current + amount if operation == "add" else max(0, current - amount)
        user_data[str(target_id)]["credits"] = new_value
        save_user_data()
    action = "added to" if operation == "add" else "removed from"
    bot.reply_to(
        message,
        f"✅ `{amount}` credit(s) {action} `{target_id}`.\n"
        f"New balance: `{new_value}`",
        reply_markup=admin_menu(),
        parse_mode="Markdown",
    )
    try:
        bot.send_message(
            target_id,
            f"💳 **Credit update**\n\n"
            f"{'Added' if operation == 'add' else 'Removed'}: `{amount}`\n"
            f"Available balance: `{new_value}`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        print(f"Credit notification error: {exc}")

def users_report():
    lines = ["👥 **REGISTERED USERS**", ""]
    now = datetime.now()
    for index, (chat_id, record) in enumerate(user_data.items(), start=1):
        active_until = active_until_for(record)
        if active_until and active_until > now:
            access = f"active till {active_until.strftime('%d-%m %H:%M')}"
        else:
            access = "inactive"
        name = record.get("name") or "Unknown"
        username = f" @{record['username']}" if record.get("username") else ""
        lines.append(
            f"{index}. `{chat_id}` — {name}{username}\n"
            f"   Credits: `{record.get('credits', 0)}` | {access}"
        )
        if len("\n".join(lines)) > 3500:
            lines.append("\n…more users not shown in this message.")
            break
    if len(lines) == 2:
        lines.append("No users have started the bot yet.")
    return "\n".join(lines)

@bot.message_handler(func=lambda msg: msg.text == "👥 𝑼𝑺𝑬𝑹𝑺")
def show_users(message):
    if not admin_only(message):
        return
    with user_data_lock:
        report = users_report()
    bot.reply_to(message, report, reply_markup=admin_menu())

def broadcast_prompt(message):
    if not admin_only(message):
        return
    prompt = bot.reply_to(
        message,
        "📢 **BROADCAST**\n\n"
        "Ab woh text bhejo jo sab registered users ko send karna hai.\n"
        "Preview ke baad confirmation button aayega.\n"
        "Type `/cancel` to cancel.",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(prompt, prepare_broadcast)

@bot.message_handler(commands=["broadcast"])
def broadcast_command(message):
    broadcast_prompt(message)

@bot.message_handler(func=lambda msg: msg.text == "📢 𝑩𝑹𝑶𝑨𝑫𝑪𝑨𝑺𝑻")
def broadcast_button(message):
    broadcast_prompt(message)

def prepare_broadcast(message):
    if not is_admin(message.chat.id):
        return
    text = (message.text or "").strip()
    if not text or text.lower() == "/cancel":
        bot.reply_to(message, "❎ **Broadcast cancelled.**", reply_markup=admin_menu(), parse_mode="Markdown")
        return
    if len(text) > 4000:
        bot.reply_to(message, "❌ Broadcast 4000 characters se chhota rakho.")
        return
    pending_broadcast[message.chat.id] = text
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ SEND NOW", callback_data="broadcast_confirm"),
        InlineKeyboardButton("❌ CANCEL", callback_data="broadcast_cancel"),
    )
    bot.send_message(
        message.chat.id,
        f"📢 **BROADCAST PREVIEW**\n\n{text}\n\n"
        f"Recipients: `{len(user_data)}` registered user(s)\n"
        "Send karna hai?",
        reply_markup=markup,
    )

@bot.callback_query_handler(func=lambda call: call.data in ["broadcast_confirm", "broadcast_cancel"])
def broadcast_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Admin only.")
        return
    if call.data == "broadcast_cancel":
        pending_broadcast.pop(call.from_user.id, None)
        bot.edit_message_text("❎ **Broadcast cancelled.**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "Cancelled")
        return
    text = pending_broadcast.pop(call.from_user.id, None)
    if not text:
        bot.answer_callback_query(call.id, "No pending broadcast.")
        return
    sent = 0
    failed = 0
    with user_data_lock:
        recipients = [
            int(chat_id) for chat_id, record in user_data.items()
            if not record.get("blocked")
        ]
    for recipient in recipients:
        try:
            bot.send_message(recipient, f"📢 Announcement\n\n{text}")
            sent += 1
        except Exception:
            failed += 1
    bot.edit_message_text(
        f"✅ **Broadcast complete.**\n\nSent: `{sent}`\nFailed: `{failed}`",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id, "Broadcast sent")

def main_menu(chat_id=None):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Telegram does not support custom button colors, so colored emoji
    # markers are used to make every button visually distinct.
    btn1 = KeyboardButton("🟦  𝑼𝑷𝑳𝑶𝑨𝑫 𝑭𝑰𝑳𝑬")
    btn2 = KeyboardButton("🟢  𝑹𝑼𝑵 𝑭𝑰𝑳𝑬")
    btn3 = KeyboardButton("⏹️  𝑺𝑻𝑶𝑷 𝑭𝑰𝑳𝑬")
    btn4 = KeyboardButton("🟡  𝑽𝑰𝑬𝑾 𝑳𝑶𝑮𝑺")
    btn5 = KeyboardButton("🟣  𝑳𝑰𝑽𝑬 𝑺𝑻𝑨𝑻𝑼𝑺")
    btn6 = KeyboardButton("🟠 ⚡ 𝑺𝑷𝑬𝑬𝑫")
    btn7 = KeyboardButton("🟤  INSTALL PIP")
    btn8 = KeyboardButton("📁  MY FILES")
    btn9 = KeyboardButton("✏️  SEND INPUT")
    btn10 = KeyboardButton("⚫  𝑫𝑬𝑽")
    btn11 = KeyboardButton("💳  𝑴𝒀 𝑪𝑹𝑬𝑫𝑰𝑻𝑺")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11)
    if chat_id is not None and is_admin(chat_id):
        markup.add(KeyboardButton("🛠  𝑨𝑫𝑴𝑰𝑵 𝑷𝑨𝑵𝑬𝑳"))
    return markup

@bot.message_handler(commands=["credits"])
@bot.message_handler(func=lambda msg: msg.text == "💳  𝑴𝒀 𝑪𝑹𝑬𝑫𝑰𝑻𝑺")
def show_credits(message):
    ensure_user_record(message.chat.id, getattr(message, "from_user", None))
    bot.reply_to(message, credits_text(message.chat.id), parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    ensure_user_record(chat_id, getattr(message, "from_user", None))
    with lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = UserSession(chat_id)
    welcome_msg = f"""
☠️ 𝑺𝑼𝑵𝑹𝑨𝑲𝑼 — 𝑭𝑰𝑳𝑬 𝑹𝑼𝑵𝑵𝑬𝑹 ☠️
 𝑪𝒍𝒊𝒄𝒌 𝒃𝒖𝒕𝒕𝒐𝒏𝒔 𝒃𝒆𝒍𝒐𝒘 𝒕𝒐 𝒄𝒐𝒏𝒕𝒓𝒐𝒍.
 **File Upload requires approval!**
   Owner will approve before you can run.
🟦 𝑼𝒑𝒍𝒐𝒂𝒅 𝒚𝒐𝒖𝒓 .𝒑𝒚 𝒇𝒊𝒍𝒆
🟢 𝑹𝒖𝒏 𝒂𝒑𝒑𝒓𝒐𝒗𝒆𝒅 𝒇𝒊𝒍𝒆
🟡 𝑽𝒊𝒆𝒘 𝒍𝒊𝒗𝒆 𝒍𝒐𝒈𝒔
🟣 𝑳𝒊𝒗𝒆 𝑺𝒕𝒂𝒕𝒖𝒔
🟠 𝑺𝒑𝒆𝒆𝒅
 𝑰𝒏𝒔𝒕𝒂𝒍𝒍 𝒑𝒊𝒑 𝒑𝒂𝒄𝒌𝒂𝒈𝒆𝒔 𝒇𝒐𝒓 𝒚𝒐𝒖𝒓 𝒇𝒊𝒍𝒆 (𝒐𝒓 𝒖𝒔𝒆 /pip)
 𝑴𝒂𝒏𝒂𝒈𝒆 𝒚𝒐𝒖𝒓 𝒖𝒑𝒍𝒐𝒂𝒅𝒆𝒅 𝒇𝒊𝒍𝒆𝒔
 𝑺𝒆𝒏𝒅 𝒊𝒏𝒑𝒖𝒕 𝒕𝒐 𝒂 𝒓𝒖𝒏𝒏𝒊𝒏𝒈 𝒇𝒊𝒍𝒆 (𝒐𝒓 𝒖𝒔𝒆 /input)
 𝑫𝒆𝒗: @𝑺𝒖𝒏𝒓𝒂𝒌𝒖𝑽2
 𝑪𝒉𝒂𝒏𝒏𝒆𝒍: @𝑨𝒏𝒊𝒔𝒉𝒑𝒚 | @𝑽𝑶𝑼𝑪𝑯_𝑹
"""
    bot.reply_to(message, welcome_msg, reply_markup=main_menu(chat_id))
# ============================================================
#  UPLOAD FILE
# ============================================================
@bot.message_handler(func=lambda msg: msg.text == "🟦  𝑼𝑷𝑳𝑶𝑨𝑫 𝑭𝑰𝑳𝑬")
def upload_file(message):
    if not require_access(message):
        return
    msg1 = bot.reply_to(
        message,
        " **Send your .py file now.**\n\n"
        "No token or Chat ID is needed here. "
        "After approval, the file will ask for each input in Telegram.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg1, handle_file_upload)
# ============================================================
#  MY FILES
# ============================================================
def normalized_button_text(message):
    """Make ReplyKeyboard labels tolerant of emoji, fonts, and spaces."""
    text = unicodedata.normalize("NFKC", message.text or "")
    return " ".join(text.split()).casefold()

@bot.message_handler(func=lambda msg: normalized_button_text(msg).endswith("my files"))
def show_my_files(message):
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = UserSession(chat_id)
        session = user_sessions[chat_id]
    discover_user_files(session)
    bot.reply_to(
        message,
        file_manager_text(session),
        reply_markup=file_manager_markup(session)
    )
@bot.callback_query_handler(func=lambda call: call.data.startswith("select_file_"))
def select_user_file(call):
    try:
        parts = call.data.split("_")
        requested_chat_id = int(parts[-2])
        file_index = int(parts[-1])
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "❌ Invalid file selection.")
        return
    if call.message.chat.id != requested_chat_id:
        bot.answer_callback_query(call.id, "❌ This file menu is not yours.")
        return
    session = user_sessions.get(requested_chat_id)
    if not session:
        bot.answer_callback_query(call.id, "❌ Session not found.")
        return
    if session.is_running:
        bot.answer_callback_query(call.id, "⏹ Stop the running file first.")
        return
    entry = get_file_entry(session, file_index)
    if not entry:
        bot.answer_callback_query(call.id, "❌ File no longer exists.")
        return
    session.file_path = entry["path"]
    session.is_approved = bool(entry.get("approved"))
    session.start_time = None
    session.end_time = None
    session.total_checks = 0
    session.speed = 0
    session.add_log(f" Selected file: {entry.get('name', 'file')}")
    bot.answer_callback_query(call.id, "✅ File selected.")
    bot.edit_message_text(
        file_manager_text(session),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=file_manager_markup(session)
    )
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_file_"))
def delete_user_file(call):
    try:
        parts = call.data.split("_")
        requested_chat_id = int(parts[-2])
        file_index = int(parts[-1])
    except (ValueError, IndexError):
        bot.answer_callback_query(call.id, "❌ Invalid file selection.")
        return
    if call.message.chat.id != requested_chat_id:
        bot.answer_callback_query(call.id, "❌ This file menu is not yours.")
        return
    session = user_sessions.get(requested_chat_id)
    if not session:
        bot.answer_callback_query(call.id, "❌ Session not found.")
        return
    entry = get_file_entry(session, file_index)
    if not entry:
        bot.answer_callback_query(call.id, "❌ File no longer exists.")
        return
    if session.is_running and entry["path"] == session.file_path:
        bot.answer_callback_query(call.id, "⏹ Stop this file before deleting it.")
        return
    file_path = os.path.abspath(entry["path"])
    upload_root = os.path.abspath(UPLOAD_DIR) + os.sep
    if not file_path.startswith(upload_root):
        bot.answer_callback_query(call.id, "❌ Unsafe file path.")
        return
    try:
        os.remove(file_path)
        deleted_name = entry.get("name", "file")
        was_selected = session.file_path == entry["path"]
        session.files.pop(file_index)
        if was_selected:
            session.file_path = None
            session.is_approved = False
            session.start_time = None
            session.end_time = None
            session.total_checks = 0
            session.speed = 0
            for fallback in reversed(session.files):
                if os.path.exists(fallback.get("path", "")):
                    session.file_path = fallback["path"]
                    session.is_approved = bool(fallback.get("approved"))
                    break
        session.add_log(f" Deleted file: {deleted_name}")
        bot.answer_callback_query(call.id, " File deleted.")
        bot.edit_message_text(
            file_manager_text(session),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=file_manager_markup(session)
        )
    except OSError as e:
        bot.answer_callback_query(call.id, f"❌ Delete failed: {e}")
# ============================================================
#  INSTALL PIP PACKAGE FOR USER FILE
# ============================================================
PACKAGE_SPEC_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:\[[A-Za-z0-9_,.-]+\])?"
    r"(?:(?:==|!=|~=|>=|<=|>|<)[A-Za-z0-9.*+!_-]+)?$"
)
@bot.message_handler(commands=['pip'])
@bot.message_handler(
    func=lambda msg: normalized_button_text(msg).endswith("install pip")
)
def install_pip_button(message):
    if not require_access(message):
        return
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = UserSession(chat_id)
        session = user_sessions[chat_id]
    if not session.file_path or not os.path.exists(session.file_path):
        bot.reply_to(
            message,
            " **Pehle apni .py file upload ya select karo.**\n\n"
            "Uske baad is button se us file ki requirements install kar sakte ho.",
            parse_mode='Markdown'
        )
        return
    prompt = bot.reply_to(
        message,
        f" **Packages for:** `{os.path.basename(session.file_path)}`\n\n"
        "Package names space se separate karke bhejo.\n\n"
        "Example:\n`requests pyTelegramBotAPI`\n"
        "or:\n`requests==2.32.3`\n\n"
        "Type `/cancel` to cancel.",
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(prompt, install_pip_packages)
def install_pip_packages(message):
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = UserSession(chat_id)
        session = user_sessions[chat_id]
    if not session.file_path or not os.path.exists(session.file_path):
        bot.reply_to(message, " **File not found. Upload/select your file first.**", parse_mode='Markdown')
        return
    package_text = (message.text or "").strip()
    if package_text.lower() == "/cancel":
        bot.reply_to(message, "❎ **Pip installation cancelled.**", parse_mode='Markdown')
        return
    packages = package_text.split()
    if not packages:
        bot.reply_to(message, "❌ **No package name received.**", parse_mode='Markdown')
        return
    if len(packages) > 20 or any(not PACKAGE_SPEC_RE.fullmatch(pkg) for pkg in packages):
        bot.reply_to(
            message,
            "❌ **Invalid package list.**\n\n"
            "Use normal PyPI names only, for example:\n"
            "`requests flask==3.0.3`",
            parse_mode='Markdown'
        )
        return
    package_list = " ".join(packages)
    bot.reply_to(
        message,
        f"⏳ **Installing:** `{package_list}`\n\nPlease wait...",
        parse_mode='Markdown'
    )
    def pip_worker():
        try:
            package_names = {
                re.split(r"==|!=|~=|>=|<=|>|<", package, maxsplit=1)[0]
                .split("[", 1)[0]
                .lower()
                for package in packages
            }
            # Repair the common python-telegram-bot dependency mismatch
            # without changing the normal install behavior for other packages.
            dependency_repair = bool(
                package_names.intersection(
                    {"anyio", "httpx", "httpcore", "python-telegram-bot"}
                )
            )
            pip_command = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
            ]
            if dependency_repair:
                pip_command.extend(["--upgrade", "--force-reinstall", "--no-cache-dir"])
            pip_command.extend(packages)
            result = subprocess.run(
                pip_command,
                capture_output=True,
                text=True,
                timeout=180
            )
            output = (result.stdout or "") + (result.stderr or "")
            output = output.strip() or "No output returned."
            if len(output) > 3500:
                output = output[-3500:]
            if result.returncode == 0:
                title = "✅ Pip installation completed."
                session.installed_packages.extend(packages)
                session.add_log(f" Packages installed: {package_list}")
            else:
                title = f"❌ Pip installation failed (exit code {result.returncode})."
                session.add_log(f"❌ Pip installation failed: {package_list}")
            bot.send_message(message.chat.id, f"{title}\n\n{output}")
        except subprocess.TimeoutExpired:
            bot.send_message(message.chat.id, "⏱️ Pip installation timed out after 180 seconds.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Pip error: {e}")
    threading.Thread(target=pip_worker, daemon=True).start()
@bot.message_handler(content_types=['document'])
def handle_file_upload(message):
    chat_id = message.chat.id
    if not require_access(message, activate=False):
        return
    if not message.document:
        bot.reply_to(message, "❌ **Please send a .py document file.**", parse_mode='Markdown')
        return
    file_id = message.document.file_id
    if not message.document.file_name.endswith('.py'):
        bot.reply_to(message, "❌ **Only .py files are allowed!**", parse_mode='Markdown')
        return
    if message.document.file_size > 5 * 1024 * 1024:
        bot.reply_to(message, "❌ **File too large! Max 5MB.**", parse_mode='Markdown')
        return
    with lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = UserSession(chat_id)
        session = user_sessions[chat_id]
        session.is_approved = False
    try:
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        file_path = os.path.join(UPLOAD_DIR, f"{chat_id}_{message.document.file_name}")
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        session.file_path = file_path
        add_file_to_session(
            session,
            file_path,
            message.document.file_name,
            approved=False
        )
        session.add_log(f" File uploaded: {message.document.file_name}")
        success = send_approval_request(
            chat_id, 
            message.document.file_name, 
            file_path
        )
        if success:
            bot.reply_to(message, f"✅ **File uploaded successfully!**\n `{message.document.file_name}`\n\n⏳ **Waiting for owner approval...**\nYou will be notified when approved.", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"⚠️ **File uploaded but approval failed!**\nPlease contact @SunrakuV2 manually.", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ **Upload failed:** {str(e)}", parse_mode='Markdown')
# ============================================================
#  RUN FILE
# ============================================================
@bot.message_handler(func=lambda msg: msg.text == "🟢  𝑹𝑼𝑵 𝑭𝑰𝑳𝑬")
def run_file(message):
    if not require_access(message):
        return
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            user_sessions[chat_id] = UserSession(chat_id)
        session = user_sessions[chat_id]
    if not session.is_approved:
        bot.reply_to(message, "❌ **File not approved!**\n\n Upload a file and wait for owner approval.", parse_mode='Markdown')
        return
    if session.is_running:
        bot.reply_to(message, "⚠️ **File is already running!**\nClick **STOP FILE** first.", parse_mode='Markdown')
        return
    if not session.file_path or not os.path.exists(session.file_path):
        session.add_log("❌ No file found! Upload a .py file.")
        bot.reply_to(message, "❌ **No file found!**\n\n Upload a .py file first.", parse_mode='Markdown')
        return
    try:
        session.process = subprocess.Popen(
            # -u makes Python child scripts flush output immediately.
            [sys.executable, "-u", session.file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        session.is_running = True
        session.start_time = datetime.now()
        session.end_time = None
        session.total_checks = 0
        session.speed = 0
        session.add_log(f" File started: {os.path.basename(session.file_path)}")
        def read_logs():
            # Read one byte at a time so prompts from input("...") are
            # visible even when they do not end with a newline.
            stdout = session.process.stdout
            partial_output = ""
            prompt_sent = False
            while True:
                try:
                    if stdout is None:
                        break
                    ready, _, _ = select.select([stdout], [], [], 0.25)
                    if ready:
                        chunk = os.read(stdout.fileno(), 4096)
                        if not chunk:
                            break
                        text = chunk.decode("utf-8", errors="replace")
                        partial_output += text
                        prompt_sent = False
                        # Store complete output lines as logs.
                        while "\n" in partial_output:
                            line, partial_output = partial_output.split("\n", 1)
                            line = line.rstrip("\r")
                            if line.strip():
                                session.add_log(line.strip())
                                session.total_checks += 1
                    else:
                        # input("...") usually leaves its prompt in the
                        # partial buffer because there is no newline.
                        prompt = clean_console_prompt(partial_output)
                        if (
                            prompt
                            and not prompt_sent
                            and session.process.poll() is None
                            and looks_like_input_prompt(prompt)
                        ):
                            ask_user_for_process_input(session, prompt)
                            partial_output = ""
                            prompt_sent = True
                    if session.process.poll() is not None:
                        break
                except Exception as e:
                    session.add_log(f"⚠️ Log reader error: {e}")
                    break
            remaining = clean_console_prompt(partial_output)
            if remaining and not session.awaiting_input:
                session.add_log(remaining)
            return_code = session.process.poll()
            session.awaiting_input = False
            session.input_prompt = ""
            session.is_running = False
            session.end_time = datetime.now()
            if return_code == 0:
                session.add_log("✅ File finished")
            elif return_code is not None:
                session.add_log(f"⚠️ File exited with code {return_code}")
        threading.Thread(target=read_logs, daemon=True).start()
        bot.reply_to(message, f"✅ **File started!**\n `{os.path.basename(session.file_path)}`\n\n Click **VIEW LOGS** to see output.\n Click **LIVE STATUS** to check progress.", parse_mode='Markdown')
    except Exception as e:
        session.is_running = False
        session.add_log(f"❌ Run error: {str(e)}")
        bot.reply_to(message, f"❌ **Error:** {str(e)}", parse_mode='Markdown')
# ============================================================
# ⏹ STOP FILE
# ============================================================
@bot.message_handler(func=lambda msg: normalized_button_text(msg).endswith("stop file"))
def stop_file(message):
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            bot.reply_to(message, "❌ No session found!", parse_mode='Markdown')
            return
        session = user_sessions[chat_id]
    if not session.is_running:
        bot.reply_to(message, "⚠️ **No file is running!**", parse_mode='Markdown')
        return
    try:
        # Set this before terminate so the status changes immediately.
        session.is_running = False
        session.process.terminate()
        time.sleep(1)
        if session.process.poll() is None:
            session.process.kill()
        session.end_time = datetime.now()
        session.add_log("⏹ File stopped")
        bot.reply_to(message, "⏹ **File stopped successfully!**", parse_mode='Markdown')
    except Exception as e:
        bot.reply_to(message, f"❌ **Stop error:** {str(e)}", parse_mode='Markdown')
# ============================================================
#  VIEW LOGS
# ============================================================
@bot.message_handler(func=lambda msg: msg.text == "🟡  𝑽𝑰𝑬𝑾 𝑳𝑶𝑮𝑺")
def view_logs(message):
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            bot.reply_to(message, "❌ No session found!", parse_mode='Markdown')
            return
        session = user_sessions[chat_id]
    logs = session.get_logs(25)
    if not logs:
        bot.reply_to(message, " **No logs yet.**\n\nRun a file to see output.", parse_mode='Markdown')
        return
    bot.reply_to(message, f" **Recent Logs:**\n```\n{logs}\n```", parse_mode='Markdown')
# ============================================================
#  LIVE STATUS (Fixed — Proper Working)
# ============================================================
@bot.message_handler(func=lambda msg: msg.text == "🟣  𝑳𝑰𝑽𝑬 𝑺𝑻𝑨𝑻𝑼𝑺")
def show_live_status(message):
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            bot.reply_to(message, "❌ **No session found!**\n\n Please /start first.", parse_mode='Markdown')
            return
        session = user_sessions[chat_id]
    # Catch a child process that ended between two status button presses.
    if session.process and session.process.poll() is not None and session.is_running:
        session.is_running = False
        session.end_time = session.end_time or datetime.now()
    status_icon = "🟢" if session.is_running else ""
    status_text = "RUNNING" if session.is_running else "STOPPED"
    approved_text = "✅ Approved" if session.is_approved else "⏳ Pending Approval"
    file_name = os.path.basename(session.file_path) if session.file_path else "None"
    runtime = session.get_runtime()
    speed = session.get_speed()
    input_state = " Waiting for your reply" if session.awaiting_input else "No"
    status_msg = f"""
 **LIVE STATUS**
 **File:** `{file_name}`
{status_icon} **Status:** `{status_text}`
✅ **Approval:** `{approved_text}`
⏱ **Runtime:** `{runtime}`
 **Checks:** `{session.total_checks}`
 **Speed:** `{speed}` checks/min
 **Input:** `{input_state}`
 **Logs:** `{len(session.logs)}` lines
━━━━━━━━━━━━━━━━━━━━━━━━━
 @SunrakuV2 |  @Anishpy | @VOUCH_R
"""
    bot.reply_to(message, status_msg, parse_mode='Markdown')
# ============================================================
# ⚡ SPEED (Fixed — Proper Working)
# ============================================================
@bot.message_handler(func=lambda msg: msg.text == "🟠 ⚡ 𝑺𝑷𝑬𝑬𝑫")
def show_speed(message):
    chat_id = message.chat.id
    with lock:
        if chat_id not in user_sessions:
            bot.reply_to(message, "❌ **No session found!**\n\n Please /start first.", parse_mode='Markdown')
            return
        session = user_sessions[chat_id]
    if not session.start_time:
        bot.reply_to(message, "⚠️ **No file has been run yet!**\n\n Start a file first using **RUN FILE**.", parse_mode='Markdown')
        return
    if session.process and session.process.poll() is not None and session.is_running:
        session.is_running = False
        session.end_time = session.end_time or datetime.now()
    runtime = session.get_runtime()
    speed = session.get_speed()
    run_state = "🟢 Running" if session.is_running else " Stopped/Finished"
    speed_msg = f"""
⚡ **SPEED REPORT**
 **State:** `{run_state}`
 **Total Checks:** `{session.total_checks}`
⏱ **Runtime:** `{runtime}`
⚡ **Speed:** `{speed}` checks/min
 **Performance:** {' Fast' if speed > 100 else ' Slow' if speed < 30 else '⚡ Average'}
━━━━━━━━━━━━━━━━━━━━━━━━━
 @SunrakuV2 |  @Anishpy | @VOUCH_R
"""
    bot.reply_to(message, speed_msg, parse_mode='Markdown')
# ============================================================
#  PROCESS INPUT
# ============================================================
@bot.message_handler(func=lambda msg: normalized_button_text(msg).endswith("send input"))
@bot.message_handler(commands=['input'])
def request_process_input(message):
    if not require_access(message, activate=False):
        return
    chat_id = message.chat.id
    with lock:
        session = user_sessions.get(chat_id)
    if not session or not session.process or not session.is_running:
        bot.reply_to(
            message,
            "⚠️ **No running file is waiting for input.**",
            parse_mode='Markdown'
        )
        return
    prompt = bot.reply_to(
        message,
        " **Send the next input value for your running file.**\n\n"
        "The value will be sent to its `input()` prompt.\n"
        "Type `/cancel` to cancel.",
        parse_mode='Markdown'
    )
    session.awaiting_input = True
    session.input_prompt = "Manual input requested"
    bot.register_next_step_handler(prompt, send_process_input)
def send_process_input(message):
    chat_id = message.chat.id
    with lock:
        session = user_sessions.get(chat_id)
    if not session or not session.process or not session.is_running:
        bot.reply_to(message, "⚠️ **The file is no longer running.**", parse_mode='Markdown')
        return
    value = message.text or ""
    if value.strip().lower() == "/cancel":
        bot.reply_to(message, "❎ **Input cancelled.**", parse_mode='Markdown')
        return
    try:
        if session.process.stdin is None:
            raise RuntimeError("stdin pipe is not available")
        session.process.stdin.write(value + "\n")
        session.process.stdin.flush()
        session.awaiting_input = False
        session.input_prompt = ""
        session.add_log(" Input sent from Telegram")
        bot.reply_to(message, "✅ **Input sent to the running file.**", parse_mode='Markdown')
    except (BrokenPipeError, OSError, ValueError) as e:
        session.awaiting_input = False
        session.input_prompt = ""
        session.is_running = False
        session.end_time = session.end_time or datetime.now()
        session.add_log(f"❌ Input error: {e}")
        bot.reply_to(message, "❌ **File closed its input channel or has stopped.**", parse_mode='Markdown')
# ============================================================
#  DEV
# ============================================================
@bot.message_handler(func=lambda msg: msg.text == "⚫  𝑫𝑬𝑽")
def show_dev(message):
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("👨‍💻 @SunrakuV2", url="https://t.me/SunrakuV2")
    btn2 = InlineKeyboardButton("📢 @Anishpy", url="https://t.me/Anishpy")
    btn3 = InlineKeyboardButton("✅ @VOUCH_R", url="https://t.me/VOUCH_R")
    markup.add(btn1, btn2, btn3)
    bot.reply_to(message, " **Developer & Channels:**", reply_markup=markup, parse_mode='Markdown')
# ============================================================
#  START BOT
# ============================================================
print("✅ Bot is running...")
print(" Bot Username: @" + bot.get_me().username)
print(" Advanced File Runner Bot Active")
print(f" Owner Chat ID: {OWNER_CHAT_ID}")
while True:
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"⚠️ Polling error: {e}")
        time.sleep(5)
        continue

