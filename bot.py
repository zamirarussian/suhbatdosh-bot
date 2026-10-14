import os
import json
import time
import asyncio
import logging
import httpx
from groq import Groq
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup,
                      ReplyKeyboardMarkup, KeyboardButton, WebAppInfo)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from database import (
    get_user, create_user, check_access, inc_msg,
    update_streak, get_streak_msg, gs, get_history,
    add_history, clear_history, update_user,
    set_mode, clear_mode, inc_exam_step, get_topics,
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
EDGE_VOICE = os.environ.get("EDGE_VOICE", "ru-RU-SvetlanaNeural")

# DIQQAT: llama-3.3-70b-versatile va llama-3.1-8b-instant Groq tomonidan
# 2026-08-16 da butunlay o'chirildi (rasmiy eskirish). Yangi modellar:
PRIMARY_MODEL  = os.environ.get("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

GENERIC_ERROR_TEXT = "Hozircha band bo'lib turibman 😔 Bir necha soniyadan keyin qayta urinib ko'ring."
TTS_ERROR_NOTE = "\n\n_(hozircha ovoz bilan javob bera olmayapman, texnik ish ketyapti 🔧)_"


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

FREE_SYSTEM = """Ты — дружелюбный собеседник для практики разговорного русского языка. Собеседник — узбекоязычный ученик.
1. Говори простым русским языком, короткими понятными предложениями
2. Сначала отреагируй на ответ ученика (например: «Ой, как интересно!», «Понятно», «Здорово!»), потом задай ОДИН открытый вопрос (почему? как? расскажи подробнее)
3. Если ученик отвечает коротко — мягко попроси рассказать больше
4. Если ученик даёт роль — играй её
5. Никогда не исправляй ошибки во время разговора
6. Отвечай 2-3 предложения, говори только по-русски"""

TOPIC_SYSTEM = """Ты — дружелюбный собеседник для практики разговорного русского языка. Собеседник — узбекоязычный ученик начального уровня.
Тема разговора: «{title}».
Подсказка по теме (для тебя): {desc}
1. Веди разговор строго вокруг этой темы, но естественно, как живой человек
2. Говори простым русским языком, короткими понятными предложениями
3. Сначала отреагируй на ответ ученика (например: «Понятно!», «Как здорово!»), потом задай ОДИН открытый вопрос по теме
4. Если ученик отвечает коротко — мягко попроси рассказать больше
5. Если тема — ситуация (кафе, магазин и т.п.), играй роль (например, официанта) и веди диалог
6. Никогда не исправляй ошибки во время разговора
7. Отвечай 2-3 предложения, говори только по-русски"""

bot_replies = {}
last_texts = {}
lesson_system = {}   # tid -> joriy dars/imtihon system prompt (xotirada)

if YANDEX_API_KEY and YANDEX_FOLDER_ID:
    logger.info("[YANDEX TTS OK] sozlangan")
else:
    logger.error("[YANDEX TTS YO'Q] YANDEX_API_KEY / YANDEX_FOLDER_ID o'rnatilmagan")

logger.info(f"[GROQ] Asosiy model: {PRIMARY_MODEL}, zaxira model: {FALLBACK_MODEL}")


def _tag_groq_error(model, e):
    """Xato matniga qarab sababni ANIQLAB loglaydi (foydalanuvchiga hech qachon ko'rsatilmaydi,
    faqat admin loglarda ko'radi — 'pul/limit tugadi' bilan 'boshqa texnik xato'ni farqlash uchun)."""
    msg = str(e).lower()
    if any(k in msg for k in ("insufficient", "billing", "payment", "quota", "credit")):
        logger.error(f"[GROQ TO'LOV/BALANS MUAMMOSI] ({model}): {e}")
    elif any(k in msg for k in ("rate_limit", "429", "rate limit")):
        logger.error(f"[GROQ LIMIT TUGADI] ({model}): {e}")
    else:
        logger.error(f"[GROQ BOSHQA XATO] ({model}): {e}")


_reasoning_effort_supported = True


def _create_completion(model, messages, max_tokens):
    """gpt-oss modellari uchun reasoning_effort=low (bo'sh javob xavfini kamaytiradi).
    Eski groq SDK'da to'g'ridan-to'g'ri kwarg xato berishi mumkin, shuning uchun extra_body orqali."""
    global _reasoning_effort_supported
    if _reasoning_effort_supported:
        try:
            return groq.chat.completions.create(
                model=model, messages=messages, max_tokens=max_tokens,
                extra_body={"reasoning_effort": "low"},
            )
        except TypeError as e:
            logger.warning(f"reasoning_effort qo'llab-quvvatlanmaydi, o'chirildi: {e}")
            _reasoning_effort_supported = False
    return groq.chat.completions.create(model=model, messages=messages, max_tokens=max_tokens)


def _groq_complete(messages, max_tokens):
    """Groq'ga so'rov yuboradi: avval asosiy model bilan, agar u band/xato/bo'sh javob
    bersa (gpt-oss modellari 'reasoning' modeli — token yetmasa bo'sh qaytishi mumkin)
    avtomatik zaxira modelga o'tadi. Ikkalasi ham ishlamasa — xatoni tepaga uzatadi.
    Foydalanuvchi hech qachon xato sababini (pul/limit) ko'rmaydi — faqat umumiy
    xushmuomala xabar oladi (GENERIC_ERROR_TEXT); sabab faqat loglarda ko'rinadi."""
    last_err = None
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            resp = _create_completion(model, messages, max_tokens)
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("Groq bo'sh javob qaytardi (reasoning token yetishmagan bo'lishi mumkin)")
            if model != PRIMARY_MODEL:
                logger.warning(f"[GROQ FALLBACK] {PRIMARY_MODEL} ishlamadi, {model} bilan javob berildi")
            return content
        except Exception as e:
            last_err = e
            _tag_groq_error(model, e)
            continue
    raise last_err


def groq_chat(tid, text, system_override=None):
    hist = get_history(tid)
    add_history(tid, "user", text)
    sys_msg = {"role": "system", "content": system_override or FREE_SYSTEM}
    reply = _groq_complete([sys_msg] + hist + [{"role": "user", "content": text}], max_tokens=900)
    add_history(tid, "assistant", reply)
    return reply


def groq_correct(text):
    return _groq_complete([
        {"role": "system", "content": "Ты — учитель русского. Найди ошибки: ❌ [ошибка] → ✅ [правильно] — [объяснение]. Если ошибок нет: ✅ Всё правильно!"},
        {"role": "user", "content": f"Проверь: {text}"}
    ], max_tokens=900)


def groq_score(text):
    return _groq_complete([
        {"role": "system", "content": "Оцени речь: 🎯 Оценка: X/10\n✅ Хорошо: ...\n📈 Улучшить: ..."},
        {"role": "user", "content": f"Оцени: {text}"}
    ], max_tokens=800)


_yandex_down_until = 0.0   # Yandex ishlamasa, shu vaqtgacha uni o'tkazib yuboramiz (kutib qolmaslik uchun)


async def _tts_yandex(text):
    """Yandex SpeechKit -> OggOpus baytlari. Xatoda None (sabab logda aniq belgilanadi)."""
    global _yandex_down_until
    if not (YANDEX_API_KEY and YANDEX_FOLDER_ID):
        logger.error("[YANDEX SOZLANMAGAN] YANDEX_API_KEY yoki YANDEX_FOLDER_ID yo'q")
        return None
    if time.time() < _yandex_down_until:
        return None
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
        async with httpx.AsyncClient(timeout=10) as h:
            r = await h.post(
                "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
                headers={"Authorization": f"Api-Key {YANDEX_API_KEY}"},
                data=payload
            )
        if r.status_code != 200:
            body_lower = (r.text or "").lower()
            if r.status_code in (402, 403) or "insufficient" in body_lower or "payment" in body_lower or "balance" in body_lower:
                logger.error(f"[YANDEX BALANS TUGAGAN] {r.status_code}: {r.text[:300]}")
            else:
                logger.error(f"[YANDEX TTS XATO] {r.status_code}: {r.text[:300]}")
            _yandex_down_until = time.time() + 300
            return None
        _yandex_down_until = 0.0
        return r.content
    except Exception as e:
        logger.error(f"[YANDEX TTS XATO] tarmoq/boshqa: {e}")
        _yandex_down_until = time.time() + 300   # 5 daqiqa Yandex'ni o'tkazib yuboramiz
        return None


async def _tts_edge(text):
    """edge-tts (bepul, zaxira) -> MP3 -> ffmpeg orqali OggOpus. Xatoda None."""
    try:
        import edge_tts
        async def _synth():
            mp3 = bytearray()
            async for ch in edge_tts.Communicate(text, EDGE_VOICE).stream():
                if ch["type"] == "audio":
                    mp3.extend(ch["data"])
            return bytes(mp3)
        mp3 = await asyncio.wait_for(_synth(), timeout=25)
        if not mp3:
            raise ValueError("edge-tts bo'sh audio qaytardi")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-loglevel", "error", "-i", "pipe:0",
            "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(mp3), timeout=20)
        if proc.returncode != 0 or not out:
            raise RuntimeError(f"ffmpeg xato: {err[:200]!r}")
        return out
    except Exception as e:
        logger.error(f"[EDGE-TTS XATO] {e}")
        return None


async def send_voice(update, text, reply_markup=None):
    """Ovozli xabar yuboradi: avval Yandex, ishlamasa edge-tts (zaxira). Muvaffaqiyatli bo'lsa True,
    ikkalasi ham ishlamasa False (chaqiruvchi matnni ko'rinadigan holda yuboradi, foydalanuvchi
    "jim qolib" ketmasin). Sabab logda aniq belgilanadi."""
    audio = await _tts_yandex(text)
    if audio is None:
        audio = await _tts_edge(text)
        if audio is not None:
            logger.warning("[TTS ZAXIRA] Yandex ishlamadi, edge-tts bilan ovoz yuborildi")
    if audio is None:
        return False
    try:
        await update.message.reply_voice(voice=audio, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"[TELEGRAM VOICE XATO] {e}")
        return False


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


class _FauxUpdate:
    """Callback tugmalardan kelganda update.message o'rniga ishlatiladi."""
    def __init__(self, message): self.message = message


def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Mavzu tanlash", callback_data="menu:topics")],
        [InlineKeyboardButton("💬 Erkin suhbat", callback_data="menu:free")],
    ])


MENU_TEXT = "Qanday suhbat qilamiz? 👇\n\n📚 *Mavzu tanlash* — tayyor mavzu bo'yicha gaplashamiz\n💬 *Erkin suhbat* — xohlagan narsa haqida"


BTN_TOPICS = "📚 Mavzu tanlash"
BTN_FREE = "💬 Erkin suhbat"
BTN_PROFILE = "👤 Profil"
BTN_HELP = "❓ Yordam"
HELP_TEXT = ("❓ *Yordam*\n\n"
             "📚 *Mavzu tanlash* — tayyor mavzu bo'yicha gaplashing\n"
             "💬 *Erkin suhbat* — xohlagan narsa haqida\n"
             "🎤 Ovoz yuborsangiz ham bo'ladi, men ovoz bilan javob beraman\n"
             "🔄 /reset — suhbatni boshidan boshlash\n"
             "📋 /menu — menyuni ochish")


def bottom_keyboard():
    """Chat pastidagi doimiy tugmalar."""
    row2 = [KeyboardButton(BTN_HELP)]
    if MINIAPP_URL:
        row2.insert(0, KeyboardButton(BTN_PROFILE, web_app=WebAppInfo(url=MINIAPP_URL)))
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_TOPICS), KeyboardButton(BTN_FREE)], row2],
        resize_keyboard=True,
    )


async def send_menu(message):
    await message.reply_text("👇", reply_markup=bottom_keyboard())
    await message.reply_text(MENU_TEXT, reply_markup=menu_keyboard(), parse_mode="Markdown")


def _topic_groups(topics):
    groups = {"A1": [], "B1": [], "other": []}
    for t in topics:
        title = t["title"]
        if title.startswith("A1 · "): groups["A1"].append(t)
        elif title.startswith("B1 · "): groups["B1"].append(t)
        else: groups["other"].append(t)
    return groups


async def send_topics_list(message, level=None):
    topics = get_topics()
    if not topics:
        await message.reply_text("Hozircha mavzular yo'q. Erkin suhbatni tanlang 👇", reply_markup=menu_keyboard())
        return
    g = _topic_groups(topics)
    if level is None and (g["A1"] or g["B1"]):
        rows = []
        if g["A1"]: rows.append([InlineKeyboardButton("📗 A1 mavzular", callback_data="menu:topics:A1")])
        if g["B1"]: rows.append([InlineKeyboardButton("📘 B1 mavzular", callback_data="menu:topics:B1")])
        if g["other"]: rows.append([InlineKeyboardButton("⭐ Boshqa mavzular", callback_data="menu:topics:other")])
        rows.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="menu:back")])
        await message.reply_text("📚 Darajani tanlang:", reply_markup=InlineKeyboardMarkup(rows))
        return
    items = g[level] if level in g else topics
    rows = []
    for t in items:
        label = t["title"].split(" · ", 1)[1] if level in ("A1", "B1") and " · " in t["title"] else t["title"]
        rows.append([InlineKeyboardButton(label, callback_data=f"topic:{t['id']}")])
    rows.append([InlineKeyboardButton("⬅️ Darajalar", callback_data="menu:topics")])
    await message.reply_text("📚 Mavzuni tanlang:", reply_markup=InlineKeyboardMarkup(rows))


async def start_free_chat(update, context):
    uid = update.effective_user.id
    fu = _FauxUpdate(update.message)
    if not await check(fu, uid): return
    clear_history(uid); clear_mode(uid); lesson_system.pop(uid, None)
    set_mode(uid, "free")
    lesson_system[uid] = FREE_SYSTEM
    await update.message.reply_text("💬 Erkin suhbat boshlandi! Ovoz yuboring yoki yozing.\n/menu — menyuga qaytish")
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    await _process_turn(fu, uid, "Начинаем. Поприветствуй меня и задай один открытый вопрос о моей жизни.")


async def start_topic(message, context, uid, topic_id):
    fu = _FauxUpdate(message)
    if not await check(fu, uid): return
    topic = next((t for t in get_topics() if t["id"] == topic_id), None)
    if not topic:
        await message.reply_text("Bu mavzu topilmadi 😔", reply_markup=menu_keyboard())
        return
    clear_history(uid); clear_mode(uid); lesson_system.pop(uid, None)
    set_mode(uid, "topic")
    lesson_system[uid] = TOPIC_SYSTEM.format(title=topic["title"], desc=(topic.get("description") or topic["title"]))
    await message.reply_text(f"📚 Mavzu: *{topic['title']}*\nBoshlaymiz! Ovoz yuboring yoki yozing.\n/menu — menyuga qaytish", parse_mode="Markdown")
    await context.bot.send_chat_action(message.chat_id, "typing")
    await _process_turn(fu, uid, "Начинаем.")


async def webapp_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mini ilovadan (Profil tugmasi) kelgan tanlov."""
    try:
        data = json.loads(update.effective_message.web_app_data.data)
    except Exception:
        return
    uid = update.effective_user.id
    create_user(uid, update.effective_user.full_name, update.effective_user.username or "")
    if data.get("a") == "free":
        await start_free_chat(update, context)
    elif data.get("a") == "topic":
        try:
            await start_topic(update.effective_message, context, uid, int(data.get("id")))
        except (TypeError, ValueError):
            return


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    create_user(tid, update.effective_user.full_name, update.effective_user.username or "")
    await send_menu(update.message)


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
    await send_menu(update.message)


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    clear_history(tid)
    clear_mode(tid)
    lesson_system.pop(tid, None)
    await update.message.reply_text("Yangi suhbat boshlandi! 🔄")
    await send_menu(update.message)


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
    ok = await send_voice(update, reply, reply_markup=kb)
    if not ok:
        # Ovoz yuborilmadi (Yandex bilan muammo) — foydalanuvchi "jim qolib" ketmasin,
        # javobni to'g'ridan-to'g'ri ko'rinadigan matn qilib yuboramiz.
        await update.message.reply_text(reply + TTS_ERROR_NOTE, reply_markup=kb, parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = update.effective_user.id
    _t = (update.message.text or "").strip()
    if _t == BTN_TOPICS:
        await send_topics_list(update.message); return
    if _t == BTN_FREE:
        await start_free_chat(update, context); return
    if _t == BTN_HELP:
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown"); return
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
    elif d.startswith("menu:"):
        action = d.split(":", 1)[1]
        if action.startswith("topics"):
            parts = action.split(":")
            await send_topics_list(q.message, parts[1] if len(parts) > 1 else None)
        elif action == "back":
            await send_menu(q.message)
        elif action == "free":
            fu = _FauxUpdate(q.message)
            if not await check(fu, uid): return
            clear_history(uid); clear_mode(uid); lesson_system.pop(uid, None)
            set_mode(uid, "free")
            lesson_system[uid] = FREE_SYSTEM
            await q.message.reply_text("💬 Erkin suhbat boshlandi! Ovoz yuboring yoki yozing.\n/menu — menyuga qaytish")
            await context.bot.send_chat_action(q.message.chat_id, "typing")
            await _process_turn(fu, uid, "Начинаем. Поприветствуй меня и задай один открытый вопрос о моей жизни.")
    elif d.startswith("topic:"):
        try:
            tid_topic = int(d.split(":", 1)[1])
        except ValueError:
            return
        await start_topic(q.message, context, uid, tid_topic)
    elif d.startswith("godaily:"):
        if lesson_system.get(uid) is None:
            await q.message.reply_text("Sessiya eskirgan, iltimos ilovadan qayta kiring.")
            return
        await context.bot.send_chat_action(q.message.chat_id, "typing")
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
    app.add_handler(CommandHandler("menu", menu_cmd))
    app.add_handler(CommandHandler("end", end_cmd))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app
