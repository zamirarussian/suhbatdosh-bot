import os
import asyncio
import logging
import httpx
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
GEMINI_KEY       = os.environ["GEMINI_API_KEY"]
ELEVENLABS_KEY   = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE = os.environ.get("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    system_instruction="""Ты — AI-собеседник для практики разговорного русского языка.
Правила:
1. Отвечай ТОЛЬКО на русском языке, коротко и разговорно (2-4 предложения)
2. После ответа задай один простой вопрос, чтобы продолжить разговор
3. Если пользователь допустил грамматическую ошибку, мягко исправь в конце
4. Стиль: дружелюбный, живой, как настоящий собеседник"""
)

sessions = {}


def get_session(uid):
    if uid not in sessions:
        sessions[uid] = model.start_chat(history=[])
    return sessions[uid]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text(
        "Привет! 👋 Я помогу вам практиковать русский язык.\n\n"
        "✍️ Напишите мне что-нибудь по-русски\n"
        "🔊 Я отвечу текстом + голосом\n\n"
        "/reset — начать разговор заново"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sessions.pop(update.effective_user.id, None)
    await update.message.reply_text("Разговор начат заново! 🔄")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text

    await context.bot.send_chat_action(update.effective_chat.id, "typing")

    try:
        chat  = get_session(uid)
        resp  = chat.send_message(text)
        reply = resp.text
    except Exception as e:
        logger.error(f"Gemini xato: {e}")
        await update.message.reply_text("Ошибка. Попробуйте ещё раз.")
        return

    await update.message.reply_text(reply)

    try:
        await context.bot.send_chat_action(update.effective_chat.id, "upload_voice")
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
            logger.error(f"ElevenLabs {tts.status_code}")
    except Exception as e:
        logger.error(f"Ovoz xato: {e}")


async def run():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot ishga tushdi...")
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run())
