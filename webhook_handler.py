"""
Flask route lari — main bot va lid bot uchun webhook handler
Bu faylni admin.py ga import qilamiz
"""
import os
import json
import logging
from flask import request, jsonify

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
LID_TOKEN = os.environ.get("LID_BOT_TOKEN", "")

_main_app = None
_lid_app = None


def get_main_app():
    global _main_app
    if _main_app is None:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
        import bot as bot_module
        import asyncio

        _main_app = Application.builder().token(TOKEN).build()
        _main_app.add_handler(CommandHandler("start", bot_module.start))
        _main_app.add_handler(CommandHandler("reset", bot_module.reset))
        _main_app.add_handler(CommandHandler("end", bot_module.end_command))
        _main_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_module.handle_message))
        _main_app.add_handler(MessageHandler(filters.VOICE, bot_module.handle_voice_msg))
        _main_app.add_handler(CallbackQueryHandler(bot_module.handle_callback))

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_main_app.initialize())
        _main_app._loop = loop
    return _main_app


def get_lid_app():
    global _lid_app
    if _lid_app is None and LID_TOKEN:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters
        import lid_bot as lid_module
        import asyncio

        _lid_app = Application.builder().token(LID_TOKEN).build()
        _lid_app.add_handler(CommandHandler("start", lid_module.start))
        _lid_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lid_module.handle_message))
        _lid_app.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.AUDIO |
            filters.VOICE | filters.Document.ALL | filters.VIDEO_NOTE,
            lid_module.handle_media_message
        ))

        loop = asyncio.new_event_loop()
        loop.run_until_complete(_lid_app.initialize())
        _lid_app._loop = loop
    return _lid_app


def register_webhook_routes(flask_app):
    """Flask app ga webhook routelarni qo'shish"""

    @flask_app.route('/webhook/main', methods=['POST'])
    def webhook_main():
        if not TOKEN:
            return jsonify({"ok": False})
        try:
            import asyncio
            from telegram import Update
            data = request.get_json()
            app = get_main_app()
            update = Update.de_json(data, app.bot)
            loop = app._loop
            loop.run_until_complete(app.process_update(update))
        except Exception as e:
            logger.error(f"Main webhook xato: {e}")
        return jsonify({"ok": True})

    @flask_app.route('/webhook/lid', methods=['POST'])
    def webhook_lid():
        if not LID_TOKEN:
            return jsonify({"ok": False})
        try:
            import asyncio
            from telegram import Update
            data = request.get_json()
            app = get_lid_app()
            if app:
                update = Update.de_json(data, app.bot)
                loop = app._loop
                loop.run_until_complete(app.process_update(update))
        except Exception as e:
            logger.error(f"Lid webhook xato: {e}")
        return jsonify({"ok": True})

    @flask_app.route('/webhook/status')
    def webhook_status():
        return jsonify({
            "main_bot": bool(TOKEN),
            "lid_bot": bool(LID_TOKEN),
            "webhook_url": os.environ.get("WEBHOOK_URL", "")
        })
