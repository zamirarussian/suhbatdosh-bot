import asyncio
import threading
import logging
import os
from database import init_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def run_admin():
    from admin import app
    from scheduler import start_scheduler
    start_scheduler()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


def run_bot():
    from bot import run
    asyncio.run(run())


if __name__ == '__main__':
    init_db()
    logger.info("Ma'lumotlar bazasi tayyor")

    admin_thread = threading.Thread(target=run_admin, daemon=True)
    admin_thread.start()
    logger.info("Admin panel ishga tushdi")

    run_bot()
