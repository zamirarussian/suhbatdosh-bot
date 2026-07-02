import logging
import os
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # https://worker-production-0725.up.railway.app
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
LID_TOKEN = os.environ.get("LID_BOT_TOKEN", "")


def setup_webhooks():
    """Botlarni webhook rejimiga o'tkazish"""
    import requests, time
    time.sleep(1)
    if TOKEN and WEBHOOK_URL:
        url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
        r = requests.post(url, json={"url": f"{WEBHOOK_URL}/webhook/main"})
        logger.info(f"Main bot webhook: {r.json()}")
    if LID_TOKEN and WEBHOOK_URL:
        url = f"https://api.telegram.org/bot{LID_TOKEN}/setWebhook"
        r = requests.post(url, json={"url": f"{WEBHOOK_URL}/webhook/lid"})
        logger.info(f"Lid bot webhook: {r.json()}")


if __name__ == '__main__':
    from database import init_db, init_lid_tables
    init_db()
    init_lid_tables()
    logger.info("Bazalar tayyor")

    # Webhook sozlash
    wh = threading.Thread(target=setup_webhooks, daemon=True)
    wh.start()

    # Scheduler
    from scheduler import start_scheduler
    start_scheduler()

    # Flask — asosiy thread
    from admin import app
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Flask {port} portda ishga tushmoqda...")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
