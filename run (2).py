import asyncio
import threading
import logging
import os
from database import init_db, init_lid_tables

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def run_suhbatdosh():
    from bot import run
    asyncio.run(run())


def run_lid():
    from lid_bot import run
    asyncio.run(run())


if __name__ == '__main__':
    init_db()
    init_lid_tables()
    logger.info("Bazalar tayyor")

    # Suhbatdosh bot — alohida thread
    t1 = threading.Thread(target=run_suhbatdosh, daemon=True)
    t1.start()
    logger.info("Suhbatdosh bot thread ishga tushdi")

    # Lid magnit bot — alohida thread
    t2 = threading.Thread(target=run_lid, daemon=True)
    t2.start()
    logger.info("Lid magnit bot thread ishga tushdi")

    # Scheduler
    from scheduler import start_scheduler
    start_scheduler()

    # Flask — asosiy thread
    from admin import app
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Flask {port} portda ishga tushdi")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
