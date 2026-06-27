import os
import logging
from datetime import datetime, date
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_setting, get_users_by_target, get_pending_broadcasts, get_db

logger = logging.getLogger(__name__)
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")


def send_tg(chat_id, text=None, media_type=None, media_file_id=None):
    import requests
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        if media_type == "photo" and media_file_id:
            requests.post(f"{base}/sendPhoto", json={"chat_id": chat_id, "photo": media_file_id, "caption": text}, timeout=10)
        elif media_type == "video" and media_file_id:
            requests.post(f"{base}/sendVideo", json={"chat_id": chat_id, "video": media_file_id, "caption": text}, timeout=10)
        elif media_type == "video_note" and media_file_id:
            requests.post(f"{base}/sendVideoNote", json={"chat_id": chat_id, "video_note": media_file_id}, timeout=10)
            if text:
                requests.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
        elif media_type == "audio" and media_file_id:
            requests.post(f"{base}/sendAudio", json={"chat_id": chat_id, "audio": media_file_id, "caption": text}, timeout=10)
        elif media_type == "voice" and media_file_id:
            requests.post(f"{base}/sendVoice", json={"chat_id": chat_id, "voice": media_file_id, "caption": text}, timeout=10)
        elif text:
            requests.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        logger.error(f"TG send error {chat_id}: {e}")


def send_daily_message():
    """Kundalik eslatma xabarini yuborish"""
    enabled = get_setting('daily_enabled')
    if enabled != '1':
        return

    send_time = get_setting('daily_time') or '09:00'
    now_time = datetime.now().strftime('%H:%M')
    if now_time != send_time:
        return

    text = get_setting('daily_text') or ''
    media_type = get_setting('daily_media_type') or ''
    media_file_id = get_setting('daily_media_file_id') or ''
    target = get_setting('daily_target') or 'all'

    tids = get_users_by_target(target)
    logger.info(f"Kundalik xabar: {len(tids)} ta userlarga")
    for tid in tids:
        send_tg(tid, text=text, media_type=media_type, media_file_id=media_file_id)


def process_scheduled_broadcasts():
    """Rejalashtirilgan broadcast xabarlarni yuborish"""
    broadcasts = get_pending_broadcasts()
    if not broadcasts:
        return

    conn = get_db()
    for bc in broadcasts:
        tids = get_users_by_target(bc['target'])
        logger.info(f"Broadcast #{bc['id']}: {len(tids)} ta userlarga")
        for tid in tids:
            send_tg(tid, text=bc['text'], media_type=bc['media_type'], media_file_id=bc['media_file_id'])
        conn.execute("UPDATE broadcasts SET status='sent', sent_at=datetime('now') WHERE id=?", (bc['id'],))
    conn.commit()
    conn.close()


def check_trial_expired():
    """Sinov muddati tugagan userlarga xabar yuborish"""
    from datetime import timedelta
    conn = get_db()
    users = conn.execute(
        "SELECT telegram_id, trial_start, trial_days FROM users WHERE status='trial'"
    ).fetchall()

    expired_text = get_setting('trial_expired_text') or 'Sinov muddatingiz tugadi.'
    now_date = date.today()

    for u in users:
        if not u['trial_start']:
            continue
        try:
            start = datetime.strptime(u['trial_start'], '%Y-%m-%d').date()
            end = start + timedelta(days=u['trial_days'] or 3)
            if now_date > end:
                conn.execute("UPDATE users SET status='expired' WHERE telegram_id=?", (u['telegram_id'],))
                send_tg(u['telegram_id'], text=expired_text)
        except Exception as e:
            logger.error(f"Trial check: {e}")

    conn.commit()
    conn.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_daily_message, 'interval', minutes=1, id='daily_msg')
    scheduler.add_job(process_scheduled_broadcasts, 'interval', minutes=5, id='broadcasts')
    scheduler.add_job(check_trial_expired, 'interval', hours=6, id='trial_check')
    scheduler.start()
    logger.info("Scheduler ishga tushdi")
    return scheduler
