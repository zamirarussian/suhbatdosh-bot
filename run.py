import asyncio
import threading
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)


def run_suhbatdosh():
    try:
        from bot import run
        asyncio.run(run())
    except Exception as e:
        logger.error(f"Suhbatdosh bot xato: {e}")


def run_lid():
    try:
        from lid_bot import run
        asyncio.run(run())
    except Exception as e:
        logger.error(f"Lid bot xato: {e}")


def start_bots():
    """Botlarni Flask dan keyin ishga tushirish"""
    import time
    time.sleep(2)  # Flask port ochilguncha kutish

    t1 = threading.Thread(target=run_suhbatdosh, daemon=True)
    t1.start()
    logger.info("Suhbatdosh bot thread ishga tushdi")

    t2 = threading.Thread(target=run_lid, daemon=True)
    t2.start()
    logger.info("Lid bot thread ishga tushdi")

    from scheduler import start_scheduler
    start_scheduler()
    logger.info("Scheduler ishga tushdi")


if __name__ == '__main__':
    from database import init_db, init_lid_tables
    init_db()
    init_lid_tables()
    logger.info("Bazalar tayyor")

    # Botlarni background da ishga tushirish
    bg = threading.Thread(target=start_bots, daemon=True)
    bg.start()

    # Flask — asosiy thread, darhol ishga tushadi
    from admin import app
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Flask {port} portda ishga tushmoqda...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
