import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from database import get_db, get_setting_for_bot, set_setting_for_bot, lid_create_user, lid_get_user, lid_increment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LID_TOKEN    = os.environ.get("LID_BOT_TOKEN", "")
ADMIN_ID     = int(os.environ.get("ADMIN_ID", "799996142"))
BOT_ID       = "lid"


async def send_media(update_or_chat, context, text, media_type, media_file_id, reply_markup=None):
    """Universal media yuborish"""
    chat_id = update_or_chat.effective_chat.id if hasattr(update_or_chat, 'effective_chat') else update_or_chat
    try:
        if media_type == "photo" and media_file_id:
            await context.bot.send_photo(chat_id, photo=media_file_id, caption=text, reply_markup=reply_markup)
        elif media_type == "video" and media_file_id:
            await context.bot.send_video(chat_id, video=media_file_id, caption=text, reply_markup=reply_markup)
        elif media_type == "video_note" and media_file_id:
            await context.bot.send_video_note(chat_id, video_note=media_file_id)
            if text:
                await context.bot.send_message(chat_id, text=text, reply_markup=reply_markup)
        elif media_type == "audio" and media_file_id:
            await context.bot.send_audio(chat_id, audio=media_file_id, caption=text, reply_markup=reply_markup)
        elif media_type == "voice" and media_file_id:
            await context.bot.send_voice(chat_id, voice=media_file_id, caption=text, reply_markup=reply_markup)
        elif media_type == "document" and media_file_id:
            await context.bot.send_document(chat_id, document=media_file_id, caption=text, reply_markup=reply_markup)
        elif text:
            await context.bot.send_message(chat_id, text=text, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Media yuborish xato: {e}")


async def run_flow(chat_id, flow_steps, context):
    """Flow qadamlarini ketma-ket yuborish"""
    for step in flow_steps:
        await asyncio.sleep(step.get('delay', 0))
        text = step.get('text', '')
        media_type = step.get('media_type', '')
        media_file_id = step.get('media_file_id', '')
        buttons = step.get('buttons', [])

        kb = None
        if buttons:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(b['text'], callback_data=b.get('data', 'none'))]
                for b in buttons
            ])
        await send_media(chat_id, context, text, media_type, media_file_id, kb)


async def get_flow_steps(flow_id):
    """Bazadan flow qadamlarini olish"""
    import json
    conn = get_db()
    row = conn.execute(
        "SELECT steps FROM lid_flows WHERE flow_id=? AND active=1", (flow_id,)
    ).fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row['steps'])
        except:
            return []
    return []


async def notify_admin(context, user, text):
    """Adminga xabar forward qilish"""
    msg = (
        f"📨 <b>Yangi xabar:</b>\n"
        f"👤 {user.full_name} (@{user.username or 'yo'q'})\n"
        f"🆔 <code>{user.id}</code>\n\n"
        f"💬 {text}"
    )
    try:
        await context.bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Admin notify: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    username = update.effective_user.username or ""
    args = context.args

    lid_create_user(uid, name, username, BOT_ID)
    lid_increment(uid, BOT_ID)

    # Deep link tekshirish
    if args:
        source = args[0]
        lid_create_user(uid, name, username, BOT_ID, source=source)

        # Flow bormi?
        flow_steps = await get_flow_steps(source)
        if flow_steps:
            await run_flow(update.effective_chat.id, flow_steps, context)
            return

        # Flow yo'q — oddiy link xabari
        link_msg = get_setting_for_bot(BOT_ID, f"link_{source}_text")
        link_media_type = get_setting_for_bot(BOT_ID, f"link_{source}_media_type")
        link_media_id = get_setting_for_bot(BOT_ID, f"link_{source}_media_id")

        if link_msg or link_media_id:
            await send_media(update, context, link_msg, link_media_type, link_media_id)
            return

    # Oddiy /start — salomlashuv
    text = get_setting_for_bot(BOT_ID, "welcome_text") or (
        "Assalomu alaykum! 👋\n\n"
        "Zamira Turganbayeva botiga yozdingiz.\n"
        "Sizga qanday yordam bera olaman?"
    )
    media_type = get_setting_for_bot(BOT_ID, "welcome_media_type") or ""
    media_id = get_setting_for_bot(BOT_ID, "welcome_media_file_id") or ""
    await send_media(update, context, text, media_type, media_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text or ""

    # Agar admin o'zi yozayotgan bo'lsa va reply bo'lsa — userga yuborish
    if uid == ADMIN_ID and update.message.reply_to_message:
        reply_text = update.message.reply_to_message.text or ""
        # ID ni reply xabardan ajratib olish
        import re
        match = re.search(r'🆔 <code>(\d+)</code>', reply_text)
        if not match:
            match = re.search(r'(\d{7,12})', reply_text)
        if match:
            target_id = int(match.group(1))
            try:
                await context.bot.send_message(target_id, text)
                await update.message.reply_text("✅ Yuborildi")
            except Exception as e:
                await update.message.reply_text(f"❌ Xato: {e}")
            return

    # Oddiy user xabari — adminga forward
    await notify_admin(context, update.effective_user, text)
    auto_reply = get_setting_for_bot(BOT_ID, "auto_reply_text")
    if auto_reply:
        await update.message.reply_text(auto_reply)


async def handle_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasm/video/audio xabarlarni adminga forward"""
    uid = update.effective_user.id
    if uid == ADMIN_ID:
        return

    msg = update.message
    file_id = ""
    media_type = ""

    if msg.photo:
        file_id = msg.photo[-1].file_id
        media_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        media_type = "video"
    elif msg.audio:
        file_id = msg.audio.file_id
        media_type = "audio"
    elif msg.voice:
        file_id = msg.voice.file_id
        media_type = "voice"
    elif msg.document:
        file_id = msg.document.file_id
        media_type = "document"
    elif msg.video_note:
        file_id = msg.video_note.file_id
        media_type = "video_note"

    caption = msg.caption or ""
    info = (
        f"📨 <b>Media xabar:</b> [{media_type}]\n"
        f"👤 {update.effective_user.full_name} (@{update.effective_user.username or 'yo'q'})\n"
        f"🆔 <code>{uid}</code>\n"
        f"📝 {caption}"
    )
    try:
        await context.bot.send_message(ADMIN_ID, info, parse_mode="HTML")
        await send_media(ADMIN_ID, context, "", media_type, file_id)
    except Exception as e:
        logger.error(f"Media forward: {e}")


async def run():
    if not LID_TOKEN:
        logger.warning("LID_BOT_TOKEN yo'q, lid bot ishga tushmaydi")
        return

    from database import init_lid_tables
    init_lid_tables()

    app = Application.builder().token(LID_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.AUDIO |
        filters.VOICE | filters.Document.ALL | filters.VIDEO_NOTE,
        handle_media_message
    ))

    logger.info("Lid magnit bot ishga tushdi!")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()
