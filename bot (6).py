import os
import asyncio
import logging
import tempfile
import subprocess
from groq import Groq
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
import httpx
from database import (
    get_user, create_user, check_access, increment_messages,
    update_streak, get_streak_message, get_setting, get_history,
    add_history, clear_history, update_user
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN         = os.environ["TELEGRAM_TOKEN"]
GROQ_KEY      = os.environ["GROQ_API_KEY"]
EL_KEY        = os.environ.get("ELEVENLABS_API_KEY", "")
EL_VOICE      = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
MINIAPP_URL   = os.environ.get("MINIAPP_URL", "")

groq_client = Groq(api_key=GROQ_KEY)

SYSTEM = {
    "role": "system",
    "content": """Ты — собеседник для практики разговорного русского языка.
Правила:
1. Отвечай коротко — 1-2 предложения, без вступлений
2. Если пользователь даёт роль — играй её
3. Задавай один короткий вопрос в конце
4. Никогда не исправляй ошибки во время разговора
5. Говори только по-русски"""
}

bot_replies = {}


def get_groq_reply(telegram_id, text):
    history = get_history(telegram_id)
    add_history(telegram_id, "user", text)
    messages = [SYSTEM] + history + [{"role": "user", "content": text}]
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=200,
    )
    reply = resp.choices[0].message.content
    add_history(telegram_id, "assistant", reply)
    return reply


def correct_errors(text):
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": """Ты — учитель русского языка.
Найди грамматические ошибки и исправь.
Формат: ❌ [ошибка] → ✅ [исправление] — [объяснение]
Если ошибок нет: ✅ Всё правильно!"""},
            {"role": "user", "content": f"Проверь: {text}"}
        ],
        max_tokens=300,
    )
    return resp.choices[0].message.content


def get_score(text):
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": """Оцени речь пользователя.
Формат:
🎯 Оценка: X/10
✅ Хорошо: [что получилось]
📈 Улучшить: [что исправить]"""},
            {"role": "user", "content": f"Оцени: {text}"}
        ],
        max_tokens=200,
    )
    return resp.choices[0].message.content


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
        logger.error(f"ffmpeg: {e}")
        return None
    finally:
        os.unlink(mp3_path)
        if os.path.exists(ogg_path):
            os.unlink(ogg_path)


async def send_voice(update, text):
    if not EL_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            tts = await http.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}",
                headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}},
            )
        if tts.status_code == 200:
            ogg = await mp3_to_ogg(tts.content)
            if ogg:
                await update.message.reply_voice(voice=ogg)
            else:
                await update.message.reply_audio(audio=tts.content, filename="reply.mp3")
    except Exception as e:
        logger.error(f"TTS: {e}")


def main_keyboard(miniapp_url=""):
    buttons = []
    if miniapp_url:
        buttons.append([KeyboardButton("📱 Mini App", web_app=WebAppInfo(url=miniapp_url))])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True) if buttons else None


async def send_welcome(update, user):
    text = get_setting("welcome_text") or "Salom! Men Zamira 🎓"
    media_type = get_setting("welcome_media_type") or ""
    media_id = get_setting("welcome_media_file_id") or ""
    kb = main_keyboard(MINIAPP_URL)

    if media_type == "photo" and media_id:
        await update.message.reply_photo(photo=media_id, caption=text, reply_markup=kb)
    elif media_type == "video" and media_id:
        await update.message.reply_video(video=media_id, caption=text, reply_markup=kb)
    elif media_type == "video_note" and media_id:
        await update.message.reply_video_note(video_note=media_id)
        await update.message.reply_text(text, reply_markup=kb)
    elif media_type == "audio" and media_id:
        await update.message.reply_audio(audio=media_id, caption=text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


# ===== COMMANDS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    name = update.effective_user.full_name
    username = update.effective_user.username or ""

    create_user(uid, name, username)
    user = get_user(uid)

    if user['status'] == 'blocked':
        await update.message.reply_text("Sizning kirishingiz cheklangan.")
        return

    clear_history(uid)
    await send_welcome(update, user)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    clear_history(uid)
    await update.message.reply_text("Yangi suhbat boshlandi! 🔄")


async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    history = get_history(uid)
    if not history:
        await update.message.reply_text("Suhbat hali boshlanmagan.")
        return
    user_msgs = [m["content"] for m in history if m["role"] == "user"]
    full_text = " ".join(user_msgs)
    await update.message.reply_text("📊 Tahlil qilyapman...")
    try:
        score = get_score(full_text)
        clear_history(uid)
        await update.message.reply_text(f"*Suhbat yakuni:*\n\n{score}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Score: {e}")


# ===== ACCESS CHECK =====

async def _check_and_proceed(update, telegram_id):
    access = check_access(telegram_id)
    if access == 'new':
        await start(update, None)
        return False
    if access == 'blocked':
        await update.message.reply_text("Sizning kirishingiz cheklangan.")
        return False
    if access == 'expired':
        text = get_setting("trial_expired_text") or "Sinov muddatingiz tugadi."
        await update.message.reply_text(text)
        return False
    if access == 'limit':
        limit = get_setting("free_daily_limit") or "3"
        await update.message.reply_text(
            f"⏰ Bugungi {limit} ta sinov xabaringiz tugadi.\n"
            "Ertaga davom eting yoki admin bilan bog'laning!"
        )
        return False
    return True


# ===== MESSAGE HANDLERS =====

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text

    if not await _check_and_proceed(update, uid):
        return

    increment_messages(uid)
    streak = update_streak(uid)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        reply = get_groq_reply(uid, text)
    except Exception as e:
        logger.error(f"Groq: {e}")
        await update.message.reply_text("Xatolik. Qayta urinib ko'ring.")
        return

    bot_replies[uid] = reply

    streak_msg = get_streak_message(streak)

    user_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Xatolarimni ko'rish", callback_data=f"correct:{uid}")
    ]])

    bot_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Matn", callback_data=f"show_text:{uid}"),
        InlineKeyboardButton("❓ Yordam", callback_data=f"help:{uid}")
    ]])

    await update.message.reply_text(reply, reply_markup=bot_kb)

    if streak_msg and streak > 0:
        await update.message.reply_text(f"🔥 {streak_msg}")

    await send_voice(update, reply)


async def handle_voice_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not await _check_and_proceed(update, uid):
        return

    increment_messages(uid)
    streak = update_streak(uid)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        transcription = groq_client.audio.transcriptions.create(
            file=("voice.ogg", bytes(voice_bytes)),
            model="whisper-large-v3",
            language="ru",
        )
        text = transcription.text
    except Exception as e:
        logger.error(f"Whisper: {e}")
        await update.message.reply_text("Ovozni tanib bo'lmadi.")
        return

    from database import get_user as _gu
    _last_texts = getattr(context.bot_data, 'last_texts', {})
    context.bot_data['last_texts'] = _last_texts
    context.bot_data['last_texts'][uid] = text

    user_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📖 Tushuntir", callback_data=f"explain:{uid}"),
        InlineKeyboardButton("🎯 Baho", callback_data=f"score:{uid}")
    ]])
    await update.message.reply_text(f"🎤 {text}", reply_markup=user_kb)

    try:
        reply = get_groq_reply(uid, text)
    except Exception as e:
        logger.error(f"Groq: {e}")
        await update.message.reply_text("Xatolik.")
        return

    bot_replies[uid] = reply
    streak_msg = get_streak_message(streak)

    bot_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Matn", callback_data=f"show_text:{uid}"),
        InlineKeyboardButton("❓ Yordam", callback_data=f"help:{uid}")
    ]])

    if streak_msg and streak > 0:
        await update.message.reply_text(f"🔥 {streak_msg}")

    await send_voice(update, reply)
    await update.message.reply_text(reply, reply_markup=bot_kb)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    uid = update.effective_user.id
    last_texts = context.bot_data.get('last_texts', {})

    if data.startswith("correct:"):
        text = last_texts.get(uid, "")
        if not text:
            await q.message.reply_text("Tekshiriladigan matn yo'q.")
            return
        await q.message.reply_text("🔍 Tekshiryapman...")
        result = correct_errors(text)
        await q.message.reply_text(result)

    elif data.startswith("explain:"):
        text = last_texts.get(uid, "")
        if not text:
            await q.message.reply_text("Matn yo'q.")
            return
        await q.message.reply_text("🔍 Tushuntiryapman...")
        result = correct_errors(text)
        await q.message.reply_text(result)

    elif data.startswith("score:"):
        text = last_texts.get(uid, "")
        if not text:
            await q.message.reply_text("Matn yo'q.")
            return
        await q.message.reply_text("🎯 Baholayman...")
        result = get_score(text)
        await q.message.reply_text(result)

    elif data.startswith("show_text:"):
        reply = bot_replies.get(uid)
        if reply:
            await q.message.reply_text(f"🤖 {reply}")

    elif data.startswith("help:"):
        await q.message.reply_text(
            "💡 *Yordam:*\n\n"
            "🎤 Ovozli xabar yuboring\n"
            "✍️ Matn yozing\n"
            "📖 Tushuntir — xatolar tushuntiriladi\n"
            "🎯 Baho — gapirish darajasi\n"
            "/end — suhbat yakuni\n"
            "/reset — yangi suhbat",
            parse_mode="Markdown"
        )


# Bot handlerlari webhook_handler.py orqali ishlatiladi
