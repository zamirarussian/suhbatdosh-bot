import os
import asyncio
import logging
import tempfile
import subprocess
import httpx
from groq import Groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from database import (
    get_user, create_user, check_access, inc_msg,
    update_streak, get_streak_msg, gs, get_history,
    add_history, clear_history, update_user
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN      = os.environ["TELEGRAM_TOKEN"]
GROQ_KEY   = os.environ["GROQ_API_KEY"]
EL_KEY     = os.environ.get("ELEVENLABS_API_KEY", "")
EL_VOICE   = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
MINIAPP_URL = os.environ.get("MINIAPP_URL", "")

groq = Groq(api_key=GROQ_KEY)

SYSTEM = {"role": "system", "content": """Ты — собеседник для практики разговорного русского языка.
1. Отвечай коротко — 1-2 предложения, без вступлений
2. Если пользователь даёт роль — играй её
3. Задавай один короткий вопрос в конце
4. Никогда не исправляй ошибки во время разговора
5. Говори только по-русски"""}

bot_replies = {}
last_texts = {}


def groq_chat(tid, text):
    hist = get_history(tid)
    add_history(tid, "user", text)
    resp = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[SYSTEM] + hist + [{"role":"user","content":text}],
        max_tokens=200
    )
    reply = resp.choices[0].message.content
    add_history(tid, "assistant", reply)
    return reply


def groq_correct(text):
    resp = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role":"system","content":"Ты — учитель русского. Найди ошибки: ❌ [ошибка] → ✅ [правильно] — [объяснение]. Если ошибок нет: ✅ Всё правильно!"},
            {"role":"user","content":f"Проверь: {text}"}
        ], max_tokens=300
    )
    return resp.choices[0].message.content


def groq_score(text):
    resp = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role":"system","content":"Оцени речь: 🎯 Оценка: X/10\n✅ Хорошо: ...\n📈 Улучшить: ..."},
            {"role":"user","content":f"Оцени: {text}"}
        ], max_tokens=200
    )
    return resp.choices[0].message.content


async def mp3_to_ogg(data):
    try:
        proc = subprocess.run(
            ["ffmpeg", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "48k", "-f", "ogg", "pipe:1"],
            input=data, capture_output=True, check=True
        )
        return proc.stdout if proc.stdout else None
    except Exception as e:
        logger.error(f"ffmpeg pipe: {e}")
        return None


async def send_voice(update, text, tid=None):
    if not EL_KEY: return
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Matnni ko\'rish", callback_data=f"txt:{tid}")
    ]]) if tid is not None else None
    try:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}",
                headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"},
                json={
                    "text": text,
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
                }
            )
        if r.status_code == 200:
            ogg = await mp3_to_ogg(r.content)
            if ogg:
                await update.message.reply_voice(voice=ogg, reply_markup=kb)
            else:
                await update.message.reply_audio(audio=r.content, filename="reply.mp3", reply_markup=kb)
        else:
            logger.error(f"ElevenLabs {r.status_code}")
    except Exception as e:
        logger.error(f"TTS: {e}")


async def send_welcome(update):
    text = gs("welcome_text") or "Salom! 👋"
    mt = gs("welcome_media_type") or ""
    mid = gs("welcome_media_file_id") or ""
    if mt == "photo" and mid:
        await update.message.reply_photo(photo=mid, caption=text)
    elif mt == "video" and mid:
        await update.message.reply_video(video=mid, caption=text)
    else:
        await update.message.reply_text(text)


async def check(update, tid):
    a = check_access(tid)
    if a == "new":
        create_user(tid, update.effective_user.full_name, update.effective_user.username or "")
        return True
    if a == "blocked":
        await update.message.reply_text("Sizning kirishingiz cheklangan.")
        return False
    if a == "expired":
        await update.message.reply_text(gs("trial_expired_text") or "Sinov muddati tugadi.")
        return False
    if a == "limit":
        lim = gs("free_limit") or "3"
        await update.message.reply_text(f"⏰ Bugungi {lim} ta xabaringiz tugadi. Ertaga davom eting!")
        return False
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    create_user(tid, update.effective_user.full_name, update.effective_user.username or "")
    clear_history(tid)
    await send_welcome(update)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history(update.effective_user.id)
    await update.message.reply_text("Yangi suhbat boshlandi! 🔄")


async def end_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    hist = get_history(tid)
    if not hist:
        await update.message.reply_text("Suhbat hali boshlanmagan.")
        return
    msgs = " ".join(m["content"] for m in hist if m["role"]=="user")
    await update.message.reply_text("📊 Tahlil qilyapman...")
    score = groq_score(msgs)
    clear_history(tid)
    await update.message.reply_text(f"*Suhbat yakuni:*\n\n{score}", parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    if not await check(update, tid): return
    inc_msg(tid)
    streak = update_streak(tid)
    last_texts[tid] = update.message.text
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        reply = groq_chat(tid, update.message.text)
    except Exception as e:
        logger.error(f"Groq: {e}")
        await update.message.reply_text("Xatolik. Qayta urinib ko'ring.")
        return
    bot_replies[tid] = reply
    sm = get_streak_msg(streak)
    if sm: await update.message.reply_text(f"🔥 {sm}")
    await update.message.reply_text(reply)
    await send_voice(update, reply, tid)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    if not await check(update, tid): return
    inc_msg(tid)
    streak = update_streak(tid)
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        vf = await update.message.voice.get_file()
        vb = await vf.download_as_bytearray()
        tr = groq.audio.transcriptions.create(file=("v.ogg", bytes(vb)), model="whisper-large-v3", language="ru")
        text = tr.text
    except Exception as e:
        logger.error(f"Whisper: {e}")
        await update.message.reply_text("Ovozni tanib bo'lmadi.")
        return
    last_texts[tid] = text
    kb1 = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Xatolarimni ko'rish", callback_data=f"err:{tid}")
    ]])
    await update.message.reply_text(f"🎤 {text}", reply_markup=kb1)
    try:
        reply = groq_chat(tid, text)
    except Exception as e:
        logger.error(f"Groq: {e}"); return
    bot_replies[tid] = reply
    sm = get_streak_msg(streak)
    if sm: await update.message.reply_text(f"🔥 {sm}")
    await send_voice(update, reply, tid)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    d = q.data

    if d.startswith("txt:"):
        r = bot_replies.get(uid)
        if r: await q.message.reply_text(f"🤖 {r}")
    elif d.startswith("err:"):
        t = last_texts.get(uid)
        if not t: return
        await q.message.reply_text("🔍 Tekshiryapman...")
        await q.message.reply_text(groq_correct(t))
    elif d.startswith("score:"):
        t = last_texts.get(uid)
        if not t: return
        await q.message.reply_text("🎯 Baholayman...")
        await q.message.reply_text(groq_score(t))
    elif d.startswith("help:"):
        await q.message.reply_text(
            "💡 *Yordam:*\n\n🎤 Ovoz yuboring\n✍️ Matn yozing\n"
            "📖 Tushuntir — xatolar\n🎯 Baho — daraja\n"
            "/end — suhbat yakuni\n/reset — yangi suhbat",
            parse_mode="Markdown"
        )


def build_app():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("end", end_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app
