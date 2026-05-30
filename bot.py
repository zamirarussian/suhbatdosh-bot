import os
import asyncio
import logging
import httpx
import google.generativeai as genai
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY       = os.environ["GEMINI_API_KEY"]
ELEVENLABS_KEY   = os.environ["ELEVENLABS_API_KEY"]
GROQ_KEY         = os.environ["GROQ_API_KEY"]
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-lite",
    system_instruction="""Ты — AI-собеседник для практики разговорного русского языка.
Правила:
1. Отвечай ТОЛЬКО на русском языке, коротко и разговорно (2-4 предложения)
2. После ответа задай один простой вопрос, чтобы продолжить разговор
3. Если пользователь допустил грамматическую ошибку, мягко исправь в конце
4. Стиль: дружелюбный, живой, как настоящий собеседник"""
)

groq_client = Groq(api_key=GROQ_KEY)
sessions = {}


def get_session(uid):
    if uid not in sessions:
        sessions[uid] = model.start_chat(history=[])
    return sessions[uid]


async def get_gemini_reply(uid, text):
    chat  = get_session(uid)
    resp  = chat.send_message(text)
    return resp.text


async def send_voice_reply(update, reply):
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
            await update.message.reply_audio(audio=tts.content, filename="reply.mp3")
        else:
            logger.error(f"ElevenLabs {tts.status_code}: {tts.text}")
    except Exception as e:
        logger.error(f"Ovoz xato: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "Привет! 👋 Я помогу вам практиковать русский язык.\n\n"
        "✍️ Напишите текст по-русски\n"
        "🎤 Или отправьте голосовое сообщение\n"
        "🔊 Я отвечу текстом + голосом\n\n"
        "/reset — начать заново"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("Разговор начат заново! 🔄")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        reply = await get_gemini_reply(uid, text)
    except Exception as e:
        logger.error(f"Gemini xato: {e}")
        await update.message.reply_text("Ошибка. Попробуйте ещё раз.")
        return
    await update.message.reply_text(reply)
    await send_voice_reply(update, reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    # Ovozni yuklab olish
    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
    except Exception as e:
        logger.error(f"Fayl yuklab olish xato: {e}")
        await update.message.reply_text("Овoz xabarini o'qib bo'lmadi.")
        return

    # Groq Whisper bilan matnга aylantirish
    try:
        transcription = groq_client.audio.transcriptions.create(
            file=("voice.ogg", bytes(voice_bytes)),
            model="whisper-large-v3",
            language="ru",
        )
        text = transcription.text
        logger.info(f"Transkriptsiya: {text}")
    except Exception as e:
        logger.error(f"Whisper xato: {e}")
        await update.message.reply_text("Ovozni tanib bo'lmadi. Qayta urinib ko'ring.")
        return

    await update.message.reply_text(f"🎤 *{text}*", parse_mode="Markdown")

    # Gemini javob
    try:
        reply = await get_gemini_reply(uid, text)
    except Exception as e:
        logger.error(f"Gemini xato: {e}")
        await update.message.reply_text("Ошибка. Попробуйте ещё раз.")
        return

    await update.message.reply_text(reply)
    await send_voice_reply(update, reply)


async def run():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    logger.info("Bot ishga tushdi...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
