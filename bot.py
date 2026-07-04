import os
import shutil
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

# ===== FFMPEG STARTUP CHECK =====
# Bu tekshiruv bot ishga tushishi bilan (birinchi ovozli xabar kutmasdan)
# Railway logiga ffmpeg topilganmi-yo'qmi aniq yozadi.
FFMPEG_PATH = shutil.which("ffmpeg")
if FFMPEG_PATH:
    try:
        v = subprocess.run([FFMPEG_PATH, "-version"], capture_output=True, text=True, timeout=10)
        first_line = v.stdout.splitlines()[0] if v.stdout else "?"
        logger.info(f"[FFMPEG OK] Topildi: {FFMPEG_PATH} — {first_line}")
    except Exception as e:
        logger.error(f"[FFMPEG XATO] Topildi lekin ishlamayapti: {e}")
else:
    logger.error("[FFMPEG YO'Q] ffmpeg PATH'da topilmadi! nixpacks.toml'da "
                 "[phases.setup] aptPkgs=['ffmpeg'] borligini tekshiring va "
                 "Railway'da 'Clear build cache' qilib qayta deploy qiling.")

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
    """mp3 baytlarni Telegram voice-note uchun ogg/opus baytlarga o'giradi.
    Muvaffaqiyatsiz bo'lsa None qaytaradi va sababini logga yozadi."""
    if not FFMPEG_PATH:
        logger.error("mp3_to_ogg: ffmpeg mavjud emas, konvertatsiya o'tkazib yuborildi")
        return None

    def _convert():
        mp3 = ogg = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(data)
                mp3 = f.name
            ogg = mp3.replace(".mp3", ".ogg")
            result = subprocess.run(
                [FFMPEG_PATH, "-y", "-i", mp3, "-ar", "48000", "-ac", "1",
                 "-c:a", "libopus", "-b:a", "48k", ogg],
                capture_output=True, timeout=30
            )
            if result.returncode != 0:
                stderr = result.stderr.decode(errors="ignore")[-800:]
                logger.error(f"ffmpeg qaytish kodi {result.returncode}: {stderr}")
                return None
            if not os.path.exists(ogg) or os.path.getsize(ogg) == 0:
                logger.error("ffmpeg 0 baytli yoki mavjud bo'lmagan ogg fayl yaratdi")
                return None
            with open(ogg, "rb") as fh:
                return fh.read()
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg 30 soniyada tugamadi (timeout)")
            return None
        except Exception as e:
            logger.error(f"mp3_to_ogg kutilmagan xato: {e}")
            return None
        finally:
            for p in (mp3, ogg):
                if p and os.path.exists(p):
                    try: os.unlink(p)
                    except Exception: pass

    return await asyncio.to_thread(_convert)


async def send_voice(update, text, reply_markup=None):
    if not EL_KEY:
        logger.error("send_voice: ELEVENLABS_API_KEY o'rnatilmagan")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}",
                headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
            )
        if r.status_code != 200:
            logger.error(f"ElevenLabs xato {r.status_code}: {r.text[:300]}")
            return
        ogg = await mp3_to_ogg(r.content)
        if ogg:
            await update.message.reply_voice(voice=ogg, reply_markup=reply_markup)
        else:
            logger.warning("send_voice: ogg konvertatsiya muvaffaqiyatsiz, mp3 fayl fallback sifatida yuborilyapti")
            await update.message.reply_audio(audio=r.content, filename="reply.mp3", reply_markup=reply_markup)
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
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Matnni ko'rish", callback_data=f"txt:{tid}"),
        InlineKeyboardButton("✅ Xatolar", callback_data=f"err:{tid}")
    ]])
    await send_voice(update, reply, reply_markup=kb)


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
    kb2 = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Matnni ko'rish", callback_data=f"txt:{tid}")
    ]])
    await send_voice(update, reply, reply_markup=kb2)


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
