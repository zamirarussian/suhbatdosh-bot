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
    add_history, clear_history, update_user,
    set_mode, clear_mode, inc_exam_step,
)
from lesson_api import get_lesson, get_week_lessons, build_daily_prompt, build_exam_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN      = os.environ["TELEGRAM_TOKEN"]
GROQ_KEY   = os.environ["GROQ_API_KEY"]
EL_KEY     = os.environ.get("ELEVENLABS_API_KEY", "")
EL_VOICE   = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
MINIAPP_URL = os.environ.get("MINIAPP_URL", "")
def get_exam_questions_count():
    try:
        return max(1, int(gs("exam_questions") or 5))
    except (TypeError, ValueError):
        return 5

groq = Groq(api_key=GROQ_KEY)

FREE_SYSTEM = """Ты — собеседник для практики разговорного русского языка.
1. Отвечай коротко — 1-2 предложения, без вступлений
2. Если пользователь даёт роль — играй её
3. Задавай один короткий вопрос в конце
4. Никогда не исправляй ошибки во время разговора
5. Говори только по-русски"""

bot_replies = {}
last_texts = {}
lesson_system = {}   # tid -> joriy dars/imtihon system prompt (xotirada)

FFMPEG_PATH = shutil.which("ffmpeg")
if FFMPEG_PATH:
    logger.info(f"[FFMPEG OK] {FFMPEG_PATH}")
else:
    logger.error("[FFMPEG YO'Q] nixpacks.toml'da aptPkgs=['ffmpeg'] tekshiring")


def groq_chat(tid, text, system_override=None):
    hist = get_history(tid)
    add_history(tid, "user", text)
    sys_msg = {"role": "system", "content": system_override or FREE_SYSTEM}
    resp = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[sys_msg] + hist + [{"role": "user", "content": text}],
        max_tokens=250
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
    if not FFMPEG_PATH:
        return None

    def _convert():
        mp3 = ogg = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(data); mp3 = f.name
            ogg = mp3.replace(".mp3", ".ogg")
            result = subprocess.run(
                [FFMPEG_PATH, "-y", "-i", mp3, "-ar", "48000", "-ac", "1",
                 "-c:a", "libopus", "-b:a", "48k", ogg],
                capture_output=True, timeout=30
            )
            if result.returncode != 0:
                logger.error(f"ffmpeg xato: {result.stderr.decode(errors='ignore')[-500:]}")
                return None
            if not os.path.exists(ogg) or os.path.getsize(ogg) == 0:
                return None
            with open(ogg, "rb") as fh:
                return fh.read()
        except Exception as e:
            logger.error(f"mp3_to_ogg: {e}")
            return None
        finally:
            for p in (mp3, ogg):
                if p and os.path.exists(p):
                    try: os.unlink(p)
                    except Exception: pass

    return await asyncio.to_thread(_convert)


async def send_voice(update, text, reply_markup=None):
    if not EL_KEY: return
    try:
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{EL_VOICE}",
                headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2",
                      "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
            )
        if r.status_code != 200:
            logger.error(f"ElevenLabs {r.status_code}: {r.text[:300]}")
            return
        ogg = await mp3_to_ogg(r.content)
        if ogg:
            await update.message.reply_voice(voice=ogg, reply_markup=reply_markup)
        else:
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
        from database import effective_daily_limit
        u = get_user(tid)
        lim = effective_daily_limit(u) if u else (gs("free_limit") or 3)
        await update.message.reply_text(f"⏰ Bugungi {lim} ta xabaringiz tugadi. Ertaga davom eting!")
        return False
    return True


# ===== /start payload parser =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    create_user(tid, update.effective_user.full_name, update.effective_user.username or "")
    clear_history(tid)
    clear_mode(tid)
    lesson_system.pop(tid, None)

    payload = context.args[0] if context.args else ""
    parts = payload.split("_")

    if len(parts) == 3 and parts[0] == "d":
        level, day = parts[1], int(parts[2])
        lesson = get_lesson(level, day)
        if not lesson:
            await update.message.reply_text("Hozircha bu dars tayyor emas 😔 Birozdan keyin urinib ko'ring.")
            return
        set_mode(tid, "daily", level=level, day=day)
        lesson_system[tid] = build_daily_prompt(lesson)
        await update.message.reply_text(
            f"Salom! Bugun «{lesson.get('topic','')}» mavzusida gaplashamiz. Tayyormisiz? Ketdik! 🚀"
        )
        return

    if len(parts) == 3 and parts[0] == "ex":
        level, week = parts[1], int(parts[2])
        lessons = get_week_lessons(level, week)
        if not lessons:
            await update.message.reply_text("Hozircha bu imtihon tayyor emas 😔 Birozdan keyin urinib ko'ring.")
            return
        set_mode(tid, "exam", level=level, week=week)
        lesson_system[tid] = build_exam_prompt(lessons, level)
        await update.message.reply_text(
            f"📝 {week}-hafta og'zaki imtihoni boshlandi! {get_exam_questions_count()} ta savol beraman. Tayyor bo'lsangiz javob yozing yoki ovoz yuboring."
        )
        try:
            reply = groq_chat(tid, "Boshladik", lesson_system[tid])
            await send_voice(update, reply)
            await update.message.reply_text(reply)
        except Exception as e:
            logger.error(f"exam start groq: {e}")
        return

    await send_welcome(update)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    clear_history(tid)
    clear_mode(tid)
    lesson_system.pop(tid, None)
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
    clear_mode(tid)
    lesson_system.pop(tid, None)
    await update.message.reply_text(f"*Suhbat yakuni:*\n\n{score}", parse_mode="Markdown")


async def _process_turn(update, tid, text):
    """Matn yoki ovozdan kelgan xabarni mode (free/daily/exam) ga qarab yuritadi."""
    u = get_user(tid)
    mode = u["mode"] if u else ""
    sys_prompt = lesson_system.get(tid)
    finished_exam = False

    if mode == "exam":
        step = inc_exam_step(tid)
        if step >= get_exam_questions_count():
            finished_exam = True
            sys_prompt = (sys_prompt or "") + (
                "\n\nBu foydalanuvchining oxirgi javobi edi. Endi yangi savol berma — "
                "barcha javoblarni hisobga olib umumiy X/10 baho va qisqa fikr ber, "
                "imtihon tugaganini ayt."
            )

    try:
        reply = groq_chat(tid, text, sys_prompt)
    except Exception as e:
        logger.error(f"Groq: {e}")
        await update.message.reply_text("Xatolik. Qayta urinib ko'ring.")
        return

    bot_replies[tid] = reply

    if finished_exam:
        clear_mode(tid)
        clear_history(tid)
        lesson_system.pop(tid, None)
        await send_voice(update, reply)
        await update.message.reply_text(f"🏁 {reply}")
        return

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("📝 Matnni ko'rish", callback_data=f"txt:{tid}"),
        InlineKeyboardButton("✅ Xatolar", callback_data=f"err:{tid}")
    ]])
    await send_voice(update, reply, reply_markup=kb)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    if not await check(update, tid): return
    inc_msg(tid)
    streak = update_streak(tid)
    last_texts[tid] = update.message.text
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    sm = get_streak_msg(streak)
    if sm: await update.message.reply_text(f"🔥 {sm}")
    await _process_turn(update, tid, update.message.text)


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
    await update.message.reply_text(f"🎤 {text}")
    sm = get_streak_msg(streak)
    if sm: await update.message.reply_text(f"🔥 {sm}")
    await _process_turn(update, tid, text)


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
