import os
import asyncio
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_bot():
    async def _run():
        from database import init
        init()
        from bot import build_app
        app = build_app()
        logger.info("Bot ishga tushdi!")
        async with app:
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            await asyncio.Event().wait()
    asyncio.run(_run())


if __name__ == "__main__":
    from database import init
    init()

    # Bot — background thread
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()

    # Scheduler
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error(f"Scheduler: {e}")

    # Flask — asosiy thread
    from admin import app
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Flask {port} portda ishga tushdi")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
