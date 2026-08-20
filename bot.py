import os
import logging
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
YANDEX_API_KEY   = os.environ.get("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.environ.get("YANDEX_FOLDER_ID", "")
YANDEX_VOICE     = os.environ.get("YANDEX_VOICE", "jane")
YANDEX_ROLE      = os.environ.get("YANDEX_ROLE", "good")
MINIAPP_URL = os.environ.get("MINIAPP_URL", "")

# DIQQAT: llama-3.3-70b-versatile va llama-3.1-8b-instant Groq tomonidan
# 2026-08-16 da butunlay o'chirildi (rasmiy eskirish). Yangi modellar:
PRIMARY_MODEL  = os.environ.get("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

GENERIC_ERROR_TEXT = "Hozircha band bo'lib turibman 😔 Bir necha soniyadan keyin qayta urinib ko'ring."


def get_exam_questions_count(tid=None):
    if tid is not None:
        u = get_user(tid)
        if u:
            from database import effective_exam_limit
            return effective_exam_limit(u)
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

if YANDEX_API_KEY and YANDEX_FOLDER_ID:
    logger.info("[YANDEX TTS OK] sozlangan")
else:
    logger.error("[YANDEX TTS YO'Q] YANDEX_API_KEY / YANDEX_FOLDER_ID o'rnatilmagan")

logger.info(f"[GROQ] Asosiy model: {PRIMARY_MODEL}, zaxira model: {FALLBACK_MODEL}")


def _groq_complete(messages, max_tokens):
    """Groq'ga so'rov yuboradi: avval asosiy model bilan, agar u band/xato/bo'sh javob
    bersa (gpt-oss modellari 'reasoning' modeli — token yetmasa bo'sh qaytishi mumkin)
    avtomatik zaxira modelga o'tadi. Ikkalasi ham ishlamasa — xatoni tepaga uzatadi."""
    last_err = None
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            resp = groq.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                reasoning_effort="low",  # gpt-oss modellari uchun: kam fikrlash, ko'proq joy javobga
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("Groq bo'sh javob qaytardi (reasoning token yetishmagan bo'lishi mumkin)")
            if model != PRIMARY_MODEL:
                logger.warning(f"[GROQ FALLBACK] {PRIMARY_MODEL} ishlamadi, {model} bilan javob berildi")
            return content
        except Exception as e:
            last_err = e
            logger.error(f"Groq ({model}) xato: {e}")
            continue
    raise last_err


def groq_chat(tid, text, system_override=None):
    hist = get_history(tid)
    add_history(tid, "user", text)
    sys_msg = {"role": "system", "content": system_override or FREE_SYSTEM}
    reply = _groq_complete([sys_msg] + hist + [{"role": "user", "content": text}], max_tokens=600)
    add_history(tid, "assistant", reply)
    return reply


def groq_correct(text):
    return _groq_complete([
        {"role": "system", "content": "Ты — учитель русского. Найди ошибки: ❌ [ошибка] → ✅ [правильно] — [объяснение]. Если ошибок нет: ✅ Всё правильно!"},
        {"role": "user", "content": f"Проверь: {text}"}
    ], max_tokens=600)


def groq_score(text):
    return _groq_complete([
        {"role": "system", "content": "Оцени речь: 🎯 Оценка: X/10\n✅ Хорошо: ...\n📈 Улучшить: ..."},
        {"role": "user", "content": f"Оцени: {text}"}
    ], max_tokens=500)


async def send_voice(update, text, reply_markup=None):
    if not (YANDEX_API_KEY and YANDEX_FOLDER_ID):
        return
    try:
        payload = {
            "text": text,
            "lang": "ru-RU",
            "voice": YANDEX_VOICE,
            "folderId": YANDEX_FOLDER_ID,
            "format": "oggopus",
        }
        # "emotion" faqat jane/omazh ovozlari uchun rasmiy qo'llab-quvvatlanadi
        if YANDEX_VOICE in ("jane", "omazh") and YANDEX_ROLE:
            payload["emotion"] = YANDEX_ROLE
        async with httpx.AsyncClient(timeout=30) as h:
            r = await h.post(
                "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                headers={"Authorization": f"Api-Key {YANDEX_API_KEY}"},
                data=payload
            )
        if r.status_code != 200:
            logger.error(f"Yandex TTS {r.status_code}: {r.text[:300]}")
            return
        # Yandex javobi to'g'ridan-to'g'ri OggOpus — ffmpeg konvertatsiyasiz Telegram voice sifatida yuboriladi
        await update.message.reply_voice(voice=r.content, reply_markup=reply_markup)
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
        tpl = gs("daily_start_text") or "Salom! Bugun «{topic}» mavzusida gaplashamiz. Tayyormisiz?"
        text = tpl.replace("{topic}", lesson.get("topic", ""))
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Ketdik!", callback_data=f"godaily:{tid}")]])
        await update.message.reply_text(text, reply_markup=kb)
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
            f"📝 {week}-hafta og'zaki imtihoni boshlandi! {get_exam_questions_count(tid)} ta savol beraman. Tayyor bo'lsangiz javob yozing yoki ovoz yuboring."
        )
        try:
            reply = groq_chat(tid, "Начинаем.", lesson_system[tid])
            await send_voice(update, reply)
            await update.message.reply_text(reply)
        except Exception as e:
            logger.error(f"exam start groq: {e}")
            await update.message.reply_text(GENERIC_ERROR_TEXT)
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
    try:
        score = groq_score(msgs)
    except Exception as e:
        logger.error(f"end_cmd score: {e}")
        await update.message.reply_text(GENERIC_ERROR_TEXT)
        return
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
        if step >= get_exam_questions_count(tid):
            finished_exam = True
            sys_prompt = (sys_prompt or "") + (
                "\n\nBu foydalanuvchining oxirgi javobi edi. Endi yangi savol berma — "
                "barcha javoblarni hisobga olib umumiy X/10 baho va qisqa fikr ber, "
                "imtihon tugaganini ayt."
            )

    try:
        reply = groq_chat(tid, text, sys_prompt)
    except Exception as e:
        logger.error(f"Groq (_process_turn): {e}")
        await update.message.reply_text(GENERIC_ERROR_TEXT)
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
        await update.message.reply_text("Ovozni tanib bo'lmadi. Birozdan keyin qayta urinib ko'ring.")
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
        try:
            await q.message.reply_text(groq_correct(t))
        except Exception as e:
            logger.error(f"groq_correct callback: {e}")
            await q.message.reply_text(GENERIC_ERROR_TEXT)
    elif d.startswith("score:"):
        t = last_texts.get(uid)
        if not t: return
        await q.message.reply_text("🎯 Baholayman...")
        try:
            await q.message.reply_text(groq_score(t))
        except Exception as e:
            logger.error(f"groq_score callback: {e}")
            await q.message.reply_text(GENERIC_ERROR_TEXT)
    elif d.startswith("godaily:"):
        if lesson_system.get(uid) is None:
            await q.message.reply_text("Sessiya eskirgan, iltimos ilovadan qayta kiring.")
            return
        await context.bot.send_chat_action(q.message.chat_id, "typing")
        class _FauxUpdate:
            def __init__(self, message): self.message = message
        await _process_turn(_FauxUpdate(q.message), uid, "Начинаем.")
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
