import os
import logging
import requests
from datetime import datetime, date, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from database import gs, get_users_for_broadcast

logger = logging.getLogger(__name__)
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")


def tg_send(chat_id, text="", media_type="", file_id=""):
    base = f"https://api.telegram.org/bot{TOKEN}"
    try:
        if media_type == "photo" and file_id:
            requests.post(f"{base}/sendPhoto", json={"chat_id":chat_id,"photo":file_id,"caption":text}, timeout=10)
        elif media_type == "video" and file_id:
            requests.post(f"{base}/sendVideo", json={"chat_id":chat_id,"video":file_id,"caption":text}, timeout=10)
        elif media_type == "audio" and file_id:
            requests.post(f"{base}/sendAudio", json={"chat_id":chat_id,"audio":file_id,"caption":text}, timeout=10)
        elif media_type == "voice" and file_id:
            requests.post(f"{base}/sendVoice", json={"chat_id":chat_id,"voice":file_id,"caption":text}, timeout=10)
        elif text:
            requests.post(f"{base}/sendMessage", json={"chat_id":chat_id,"text":text,"parse_mode":"HTML"}, timeout=10)
    except Exception as e:
        logger.error(f"tg_send {chat_id}: {e}")


def daily_message():
    if gs("daily_enabled") != "1":
        return
    send_time = gs("daily_time") or "09:00"
    if datetime.now().strftime("%H:%M") != send_time:
        return
    text = gs("daily_text") or ""
    mt = gs("daily_media_type") or ""
    mid = gs("daily_media_file_id") or ""
    target = gs("daily_target") or "all"
    tids = get_users_for_broadcast(target)
    for tid in tids:
        tg_send(tid, text, mt, mid)
    logger.info(f"Kundalik xabar: {len(tids)} ta")


def check_trial_expired():
    from database import db
    conn = db()
    users = conn.execute("SELECT telegram_id, trial_start, trial_days FROM users WHERE status='trial'").fetchall()
    expired_text = gs("trial_expired_text") or "Sinov muddatingiz tugadi."
    for u in users:
        if not u["trial_start"]:
            continue
        try:
            start = datetime.strptime(u["trial_start"], "%Y-%m-%d").date()
            if date.today() > start + timedelta(days=u["trial_days"] or 3):
                conn.execute("UPDATE users SET status='expired' WHERE telegram_id=?", (u["telegram_id"],))
                tg_send(u["telegram_id"], expired_text)
        except Exception as e:
            logger.error(f"trial check: {e}")
    conn.commit()
    conn.close()


def start_scheduler():
    s = BackgroundScheduler()
    s.add_job(daily_message, "interval", minutes=1)
    s.add_job(check_trial_expired, "interval", hours=6)
    s.start()
    logger.info("Scheduler ishga tushdi")
    return s
