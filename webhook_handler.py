import os
import asyncio
import logging
from flask import request, jsonify

logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
LID_TOKEN = os.environ.get("LID_BOT_TOKEN", "")

_main_app = None
_lid_app = None
_main_loop = None
_lid_loop = None


def _build_main_app():
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
    import bot as b

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", b.start))
    app.add_handler(CommandHandler("reset", b.reset))
    app.add_handler(CommandHandler("end", b.end_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, b.handle_message))
    app.add_handler(MessageHandler(filters.VOICE, b.handle_voice_msg))
    app.add_handler(CallbackQueryHandler(b.handle_callback))
    return app


def _build_lid_app():
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    import lid_bot as lb

    app = Application.builder().token(LID_TOKEN).build()
    app.add_handler(CommandHandler("start", lb.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lb.handle_message))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.AUDIO |
        filters.VOICE | filters.Document.ALL | filters.VIDEO_NOTE,
        lb.handle_media_message
    ))
    return app


def init_apps():
    global _main_app, _lid_app, _main_loop, _lid_loop

    if TOKEN:
        _main_loop = asyncio.new_event_loop()
        _main_app = _build_main_app()
        _main_loop.run_until_complete(_main_app.initialize())
        logger.info("Main bot webhook app tayyor")

    if LID_TOKEN:
        _lid_loop = asyncio.new_event_loop()
        _lid_app = _build_lid_app()
        _lid_loop.run_until_complete(_lid_app.initialize())
        logger.info("Lid bot webhook app tayyor")


def register_webhook_routes(flask_app):

    @flask_app.route('/webhook/main', methods=['POST'])
    def webhook_main():
        if not _main_app:
            return jsonify({"ok": False, "error": "app not ready"})
        try:
            from telegram import Update
            data = request.get_json(force=True)
            update = Update.de_json(data, _main_app.bot)
            _main_loop.run_until_complete(_main_app.process_update(update))
        except Exception as e:
            logger.error(f"Main webhook: {e}")
        return jsonify({"ok": True})

    @flask_app.route('/webhook/lid', methods=['POST'])
    def webhook_lid():
        if not _lid_app:
            return jsonify({"ok": False, "error": "app not ready"})
        try:
            from telegram import Update
            data = request.get_json(force=True)
            update = Update.de_json(data, _lid_app.bot)
            _lid_loop.run_until_complete(_lid_app.process_update(update))
        except Exception as e:
            logger.error(f"Lid webhook: {e}")
        return jsonify({"ok": True})

    @flask_app.route('/webhook/status')
    def webhook_status():
        return jsonify({
            "main_bot": _main_app is not None,
            "lid_bot": _lid_app is not None,
        })

    # App ni ishga tushirish
    with flask_app.app_context():
        try:
            init_apps()
        except Exception as e:
            logger.error(f"App init xato: {e}")
