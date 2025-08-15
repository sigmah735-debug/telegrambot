"""
Telegram Channel Manager Bot — Advanced Starter

Requirements:
  pip install "python-telegram-bot>=21,<22"

Environment:
  - Set your token as an environment variable named TELEGRAM_TOKEN
    (NEVER hardcode your token. If it was exposed, revoke it in @BotFather and create a new one.)

What this bot can do:
  - /start, /help: basics
  - /setchannel <@username or numeric id>: connect a channel
  - /post <text>: post text to the connected channel
  - Reply with /post_photo to a photo to publish it to the channel (with optional caption)
  - /schedule_in <minutes> <text>: schedule a message to the channel
  - /pin_last: pin the last message sent by the bot in the channel
  - /addadmin <user_id>: add additional admin(s) who can control the bot
  - /status: show current config

Notes:
  1) Add this bot as an ADMIN in your Telegram Channel with permissions to "Post Messages" and "Pin Messages".
  2) If you use @username for the channel, Telegram will resolve it automatically when sending.
  3) Only admin_ids listed in config.json can use control commands.
"""

from __future__ import annotations
import os
import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional

from telegram import Update, Message, ChatPermissions
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackContext, ContextTypes, filters
)

CONFIG_FILE = "config.json"
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
LOGGER = logging.getLogger("ChannelManagerBot")

@dataclass
class BotConfig:
    channel_id: Optional[str] = None  # can be numeric id like -100123... or @username
    admin_ids: list[int] = None
    last_channel_message_id: Optional[int] = None

    @staticmethod
    def load(path: str = CONFIG_FILE) -> "BotConfig":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return BotConfig(**data)
        # Default: the first user who sends /start becomes admin
        return BotConfig(channel_id=None, admin_ids=[])

    def save(self, path: str = CONFIG_FILE) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

# -------------------- Helpers --------------------

def get_token() -> str:
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        raise RuntimeError(
            "Missing TELEGRAM_TOKEN environment variable. Export your bot token before running."
        )
    return token

async def is_admin(update: Update, cfg: BotConfig) -> bool:
    user = update.effective_user
    return user and cfg.admin_ids and user.id in cfg.admin_ids

async def admin_guard(update: Update, context: ContextTypes.DEFAULT_TYPE, cfg: BotConfig) -> bool:
    if not await is_admin(update, cfg):
        await update.effective_message.reply_text("❌ यह कमांड केवल एडमिन्स के लिए है.")
        return False
    return True

# -------------------- Commands --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    user = update.effective_user
    if user and (not cfg.admin_ids):
        cfg.admin_ids = [user.id]
        cfg.save()
        first_admin_note = "\n\n✅ आपको एडमिन बनाया गया है (पहला उपयोगकर्ता)."
    else:
        first_admin_note = ""

    text = (
        "नमस्ते! मैं आपका चैनल मैनेजर बॉट हूँ.\n"
        "कमांड सूची देखने के लिए /help भेजें." + first_admin_note
    )
    await update.message.reply_text(text)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "उपलब्ध कमांड्स:\n"
        "/setchannel <@username या -100...id> — चैनल जोड़ें\n"
        "/post <टेक्स्ट> — चैनल पर पोस्ट करें\n"
        "/post_photo (फोटो पर रिप्लाई करें) — फोटो चैनल पर पोस्ट करें\n"
        "/schedule_in <मिनट> <टेक्स्ट> — शेड्यूल पोस्ट\n"
        "/pin_last — बॉट द्वारा भेजे गए आखिरी चैनल मैसेज को पिन करें\n"
        "/addadmin <user_id> — नया एडमिन जोड़ें\n"
        "/status — वर्तमान सेटिंग्स\n"
    )
    await update.message.reply_text(text)

async def setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    if not await admin_guard(update, context, cfg):
        return
    if not context.args:
        await update.message.reply_text("उपयोग: /setchannel <@username या -100...id>")
        return
    channel = context.args[0]
    cfg.channel_id = channel
    cfg.save()
    await update.message.reply_text(f"✅ चैनल सेट: {channel}\nबॉट को उस चैनल में एडमिन बनाना न भूलें.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    text = (
        f"Channel: {cfg.channel_id}\n"
        f"Admins: {cfg.admin_ids}\n"
        f"Last Channel Msg ID: {cfg.last_channel_message_id}"
    )
    await update.message.reply_text(text)

async def addadmin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    if not await admin_guard(update, context, cfg):
        return
    if not context.args:
        await update.message.reply_text("उपयोग: /addadmin <user_id>")
        return
    try:
        uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("user_id संख्यात्मक होना चाहिए.")
        return
    if uid not in cfg.admin_ids:
        cfg.admin_ids.append(uid)
        cfg.save()
    await update.message.reply_text(f"✅ एडमिन जोड़ा गया: {uid}")

async def post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    if not await admin_guard(update, context, cfg):
        return
    if not cfg.channel_id:
        await update.message.reply_text("पहले /setchannel चलाएँ.")
        return
    if not context.args:
        await update.message.reply_text("उपयोग: /post <टेक्स्ट>")
        return
    text = " ".join(context.args)
    msg = await context.bot.send_message(chat_id=cfg.channel_id, text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
    cfg.last_channel_message_id = msg.message_id
    cfg.save()
    await update.message.reply_text("✅ पोस्ट कर दिया गया.")

async def post_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    if not await admin_guard(update, context, cfg):
        return
    if not cfg.channel_id:
        await update.message.reply_text("पहले /setchannel चलाएँ.")
        return
    reply: Message | None = update.message.reply_to_message
    if not reply or not reply.photo:
        await update.message.reply_text("किसी फोटो पर /post_photo रिप्लाई करें (कैप्शन वैकल्पिक).")
        return
    caption = reply.caption or ""
    file_id = reply.photo[-1].file_id  # best quality
    msg = await context.bot.send_photo(chat_id=cfg.channel_id, photo=file_id, caption=caption)
    cfg.last_channel_message_id = msg.message_id
    cfg.save()
    await update.message.reply_text("✅ फोटो पोस्ट कर दिया गया.")

async def schedule_in(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    if not await admin_guard(update, context, cfg):
        return
    if not cfg.channel_id:
        await update.message.reply_text("पहले /setchannel चलाएँ.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("उपयोग: /schedule_in <मिनट> <टेक्स्ट>")
        return
    try:
        minutes = float(context.args[0])
    except ValueError:
        await update.message.reply_text("मिनट संख्या में दें.")
        return
    text = " ".join(context.args[1:])

    async def job_callback(ctx: CallbackContext) -> None:
        msg = await ctx.bot.send_message(chat_id=cfg.channel_id, text=text, parse_mode=ParseMode.HTML)
        cfg.last_channel_message_id = msg.message_id
        cfg.save()

    job = context.job_queue.run_once(job_callback, when=minutes * 60)
    await update.message.reply_text(f"⏱️ शेड्यूल हो गया — {minutes} मिनट बाद पोस्ट होगा.")

async def pin_last(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg: BotConfig = context.bot_data["cfg"]
    if not await admin_guard(update, context, cfg):
        return
    if not cfg.channel_id or not cfg.last_channel_message_id:
        await update.message.reply_text("कोई हालिया चैनल मैसेज नहीं मिला.")
        return
    try:
        await context.bot.pin_chat_message(chat_id=cfg.channel_id, message_id=cfg.last_channel_message_id)
        await update.message.reply_text("📌 पिन कर दिया गया.")
    except Exception as e:
        LOGGER.exception("Pin failed: %s", e)
        await update.message.reply_text("पिन करते समय त्रुटि हुई. सुनिश्चित करें कि बॉट के पास पिन करने की अनुमति है.")

# -------------------- Main --------------------

def main() -> None:
    token = get_token()
    app = Application.builder().token(token).build()

    # Load config into bot_data so all handlers can access
    cfg = BotConfig.load()
    app.bot_data["cfg"] = cfg

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("setchannel", setchannel))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("addadmin", addadmin))
    app.add_handler(CommandHandler("post", post))
    app.add_handler(CommandHandler("post_photo", post_photo))
    app.add_handler(CommandHandler("schedule_in", schedule_in))
    app.add_handler(CommandHandler("pin_last", pin_last))

    LOGGER.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
