import os
import asyncio
import logging
import tempfile
import subprocess
from datetime import date
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
ELEVENLABS_KEY   = os.environ["ELEVENLABS_API_KEY"]
GROQ_KEY         = os.environ["GROQ_API_KEY"]
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ADMIN_IDS        = list(map(int, os.environ.get("ADMIN_IDS", "").split(","))) if os.environ.get("ADMIN_IDS") else []
FREE_LIMIT       = int(os.environ.get("FREE_LIMIT", "10"))

groq_client = Groq(api_key=GROQ_KEY)

SYSTEM = {
    "role": "system",
    "content": """Ты — собеседник для практики разговорного русского языка.
Правила:
1. Отвечай коротко — 1-2 предложения, без вступлений типа "Отлично!" или "Интересно!"
2. Если пользователь даёт роль — играй её
3. Задавай один короткий вопрос в конце
4. Никогда не исправляй ошибки во время разговора — только отвечай естественно
5. Говори только по-русски"""
}

histories   = {}   # {uid: [...messages]}
premiums    = set()
usage       = {}   # {uid: {date: count}}
last_texts  = {}   # {uid: user_text} — xato tekshirish uchun
bot_replies = {}   # {uid: bot_reply} — matnni ko'rish uchun


def is_premium(uid):
    return uid in premiums or uid in ADMIN_IDS


def check_limit(uid):
    if is_premium(uid):
        return True
    today = str(date.today())
    return usage.get(uid, {}).get(today, 0) < FREE_LIMIT


def increment_usage(uid):
    today = str(date.today())
    if uid not in usage:
        usage[uid] = {}
    usage[uid][today] = usage[uid].get(today, 0) + 1


def get_history(uid):
    if uid not in histories:
        histories[uid] = []
    return histories[uid]


def get_groq_reply(uid, text):
    history = get_history(uid)
    history.append({"role": "user", "content": text})
    if len(history) > 20:
        histories[uid] = history[-20:]
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[SYSTEM] + histories[uid],
        max_tokens=200,
    )
    reply = response.choices[0].message.content
    histories[uid].append({"role": "assistant", "content": reply})
    return reply


def correct_errors(text):
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": """Ты — учитель русского языка.
Найди грамматические ошибки в тексте и исправь их.
Формат:
❌ [с ошибкой] → ✅ [исправлено] — [краткое объяснение]

Если ошибок нет: ✅ Ошибок нет! Отлично говоришь!
Отвечай только по-русски."""
            },
            {"role": "user", "content": f"Проверь: {text}"}
        ],
        max_tokens=300,
    )
    return response.choices[0].message.content


async def mp3_to_ogg(mp3_bytes):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(mp3_bytes)
        mp3_path = f.name
    ogg_path = mp3_path.replace(".mp3", ".ogg")
    try:
        subprocess.run(
            ["ffmpeg", "-i", mp3_path, "-c:a", "libopus", "-b:a", "48k", ogg_path, "-y"],
            check=True, capture_output=True
        )
        with open(ogg_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"ffmpeg xato: {e}")
        return None
    finally:
        os.unlink(mp3_path)
        if os.path.exists(ogg_path):
            os.unlink(ogg_path)


async def send_voice_with_button(update, reply, uid):
    """Bot ovozini yuboradi + 'Matnni ko'rish' knopkasi"""
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Matnni ko'rish", callback_data=f"show_bot_text:{uid}")
    ]])
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            tts = await http.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE}",
                headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json"},
                json={
                    "text": reply,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
            )
        if tts.status_code == 200:
            ogg = await mp3_to_ogg(tts.content)
            if ogg:
                await update.message.reply_voice(voice=ogg, reply_markup=keyboard)
            else:
                await update.message.reply_audio(
                    audio=tts.content, filename="reply.mp3", reply_markup=keyboard
                )
        else:
            logger.error(f"ElevenLabs {tts.status_code}")
            await update.message.reply_text(reply, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ovoz xato: {e}")
        await update.message.reply_text(reply, reply_markup=keyboard)


# ===== COMMANDS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    histories.pop(uid, None)
    limit_info = "♾️ Cheksiz" if is_premium(uid) else f"Kuniga {FREE_LIMIT} ta xabar (bepul)"
    await update.message.reply_text(
        "Привет! 👋 Мен сизга рус тилида гаплашишга ёрдам бераман.\n\n"
        "✍️ Матн ёзинг ёки 🎤 овозли хабар юборинг\n"
        f"📊 Лимит: {limit_info}\n\n"
        "/reset — янги суҳбат\n"
        "/end — хатоларни кўриш"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    histories.pop(uid, None)
    last_texts.pop(uid, None)
    bot_replies.pop(uid, None)
    await update.message.reply_text("Разговор начат заново! 🔄")


async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    history = get_history(uid)
    if not history:
        await update.message.reply_text("Суҳбат ҳали бошланмаган.")
        return
    user_messages = [m["content"] for m in history if m["role"] == "user"]
    full_text = " ".join(user_messages)
    await update.message.reply_text("🔍 Барча хатоларни текшираман...")
    try:
        correction = correct_errors(full_text)
        histories.pop(uid, None)
        await update.message.reply_text(
            f"📝 *Суҳбат хулосаси:*\n\n{correction}", parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"end xato: {e}")
        await update.message.reply_text("Хатоларни текшира олмадим.")


# ===== ADMIN =====

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today = str(date.today())
    total = sum(u.get(today, 0) for u in usage.values())
    await update.message.reply_text(
        f"📊 *Statistika:*\n"
        f"👥 Jami: {len(usage)}\n"
        f"💎 Premium: {len(premiums)}\n"
        f"💬 Bugun: {total} xabar\n"
        f"🔒 Limit: {FREE_LIMIT}/kun",
        parse_mode="Markdown"
    )


async def admin_addpremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /addpremium [user_id]")
        return
    uid = int(context.args[0])
    premiums.add(uid)
    await update.message.reply_text(f"✅ {uid} — premium.")


async def admin_removepremium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish: /removepremium [user_id]")
        return
    uid = int(context.args[0])
    premiums.discard(uid)
    await update.message.reply_text(f"✅ {uid} — bepul.")


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    today = str(date.today())
    lines = []
    for uid, u in usage.items():
        p = "💎" if uid in premiums else "👤"
        lines.append(f"{p} `{uid}`: {u.get(today, 0)} xabar")
    text = "\n".join(lines) if lines else "Hali hech kim yo'q."
    await update.message.reply_text(f"👥 *Userlar:*\n{text}", parse_mode="Markdown")


# ===== MESSAGE HANDLERS =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text

    if not check_limit(uid):
        await update.message.reply_text(
            f"⏰ Bugungi {FREE_LIMIT} ta bepul xabaringiz tugadi.\n"
            f"Ertaga davom eting yoki premium oling! 🌙"
        )
        return

    increment_usage(uid)
    last_texts[uid] = text
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        reply = get_groq_reply(uid, text)
    except Exception as e:
        logger.error(f"Groq xato: {e}")
        await update.message.reply_text("Ошибка. Попробуйте ещё раз.")
        return

    bot_replies[uid] = reply

    # Matn javob + xatolarni ko'rish knopkasi
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Xatolarimni ko'rish", callback_data=f"correct:{uid}")
    ]])
    await update.message.reply_text(reply, reply_markup=keyboard)

    # Ovoz + matnni ko'rish knopkasi
    await send_voice_with_button(update, reply, uid)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not check_limit(uid):
        await update.message.reply_text(
            f"⏰ Bugungi {FREE_LIMIT} ta bepul xabaringiz tugadi.\n"
            f"Ertaga davom eting! 🌙"
        )
        return

    increment_usage(uid)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    # 1. Ovozni yuklab olish
    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
    except Exception as e:
        logger.error(f"Yuklab olish xato: {e}")
        await update.message.reply_text("Ovoz xabarini o'qib bo'lmadi.")
        return

    # 2. Matnга aylantirish
    try:
        transcription = groq_client.audio.transcriptions.create(
            file=("voice.ogg", bytes(voice_bytes)),
            model="whisper-large-v3",
            language="ru",
        )
        text = transcription.text
    except Exception as e:
        logger.error(f"Whisper xato: {e}")
        await update.message.reply_text("Ovozni tanib bo'lmadi.")
        return

    last_texts[uid] = text

    # 3. USER matnini ko'rsatish + xatolarni ko'rish knopkasi
    user_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Xatolarimni ko'rish", callback_data=f"correct:{uid}")
    ]])
    await update.message.reply_text(
        f"🎤 {text}",
        reply_markup=user_keyboard
    )

    # 4. Bot javobini olish
    try:
        reply = get_groq_reply(uid, text)
    except Exception as e:
        logger.error(f"Groq xato: {e}")
        await update.message.reply_text("Ошибка. Попробуйте ещё раз.")
        return

    bot_replies[uid] = reply

    # 5. Bot ovozini yuborish + matnni ko'rish knopkasi
    await send_voice_with_button(update, reply, uid)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid  = update.effective_user.id

    if data.startswith("correct:"):
        text = last_texts.get(uid)
        if not text:
            await query.message.reply_text("Tekshiriladigan matn topilmadi.")
            return
        await query.message.reply_text("🔍 Xatolarni tekshiraman...")
        try:
            correction = correct_errors(text)
            await query.message.reply_text(correction)
        except Exception as e:
            logger.error(f"Correction xato: {e}")

    elif data.startswith("show_bot_text:"):
        reply = bot_replies.get(uid)
        if not reply:
            await query.message.reply_text("Matn topilmadi.")
            return
        await query.message.reply_text(f"🤖 {reply}")


# ===== MAIN =====

async def run():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("end", end_command))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("addpremium", admin_addpremium))
    app.add_handler(CommandHandler("removepremium", admin_removepremium))
    app.add_handler(CommandHandler("users", admin_users))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot ishga tushdi...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
