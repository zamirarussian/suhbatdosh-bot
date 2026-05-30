import os
import asyncio
import logging
import httpx
from groq import Groq
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
ELEVENLABS_KEY   = os.environ["ELEVENLABS_API_KEY"]
GROQ_KEY         = os.environ["GROQ_API_KEY"]
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

groq_client = Groq(api_key=GROQ_KEY)

SYSTEM = {
    "role": "system",
    "content": """Ты — помощник для практики разговорного русского языка.

Правила:
1. Отвечай коротко — 1-2 предложения, без вступлений
2. Если пользователь даёт роль ("будь журналистом", "ты врач" и т.д.) — играй эту роль
3. Если роли нет — веди обычный разговор
4. Задавай один короткий вопрос в конце
5. Ошибку исправь в скобках в конце
6. Никогда не выходи из русского языка"""
}

# Har foydalanuvchining suhbat tarixi
histories = {}


def get_history(uid):
    if uid not in histories:
        histories[uid] = []
    return histories[uid]


def get_groq_reply(uid, text):
    history = get_history(uid)
    history.append({"role": "user", "content": text})
    if len(history) > 20:
        history = history[-20:]
        histories[uid] = history

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[SYSTEM] + history,
        max_tokens=300,
    )
    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})
    return reply


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
    histories.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "Привет! 👋 Я помогу вам практиковать русский язык.\n\n"
        "✍️ Напишите текст по-русски\n"
        "🎤 Или отправьте голосовое сообщение\n"
        "🔊 Я отвечу текстом + голосом\n\n"
        "/reset — начать заново"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    histories.pop(update.effective_user.id, None)
    await update.message.reply_text("Разговор начат заново! 🔄")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        reply = get_groq_reply(uid, text)
    except Exception as e:
        logger.error(f"Groq xato: {e}")
        await update.message.reply_text("Ошибка. Попробуйте ещё раз.")
        return
    await update.message.reply_text(reply)
    await send_voice_reply(update, reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await context.bot.send_chat_action(update.effective_chat.id, "typing")
    try:
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
    except Exception as e:
        logger.error(f"Fayl yuklab olish xato: {e}")
        await update.message.reply_text("Ovoz xabarini o'qib bo'lmadi.")
        return
    try:
        transcription = groq_client.audio.transcriptions.create(
            file=("voice.ogg", bytes(voice_bytes)),
            model="whisper-large-v3",
            language="ru",
        )
        text = transcription.text
    except Exception as e:
        logger.error(f"Whisper xato: {e}")
        await update.message.reply_text("Ovozni tanib bo'lmadi. Qayta urinib ko'ring.")
        return
    await update.message.reply_text(f"🎤 *{text}*", parse_mode="Markdown")
    try:
        reply = get_groq_reply(uid, text)
    except Exception as e:
        logger.error(f"Groq xato: {e}")
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
