import sqlite3
import os
from datetime import date, datetime

DB_PATH = os.environ.get("DB_PATH", "zamira.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id   INTEGER UNIQUE NOT NULL,
        name          TEXT,
        username      TEXT,
        status        TEXT DEFAULT 'trial',
        trial_start   TEXT,
        trial_days    INTEGER DEFAULT 3,
        streak        INTEGER DEFAULT 0,
        last_active   TEXT,
        msg_today     INTEGER DEFAULT 0,
        msg_date      TEXT,
        created_at    TEXT DEFAULT (date('now'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS topics (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        description TEXT,
        ord         INTEGER DEFAULT 0,
        active      INTEGER DEFAULT 1
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS streak_messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        range_start INTEGER NOT NULL,
        range_end   INTEGER,
        message     TEXT NOT NULL
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key   TEXT PRIMARY KEY,
        value TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS broadcasts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        text         TEXT,
        media_type   TEXT,
        media_file_id TEXT,
        target       TEXT DEFAULT 'all',
        scheduled_at TEXT,
        sent_at      TEXT,
        status       TEXT DEFAULT 'pending',
        created_at   TEXT DEFAULT (datetime('now'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        role        TEXT,
        content     TEXT,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")

    conn.commit()
    _seed_defaults(conn)
    conn.close()


def _seed_defaults(conn):
    c = conn.cursor()

    defaults = {
        "free_daily_limit": "3",
        "admin_login": "admin",
        "admin_password": "zamira2024",
        "welcome_text": "Salom! Men Zamira — rus tili muallimingizman 🎓\n\nSiz uchun 3 kunlik bepul sinov tayyorladim: kuniga 3 ta suhbat.\n\nBoshlaylikmi? 🚀",
        "welcome_media_type": "",
        "welcome_media_file_id": "",
        "daily_text": "Bugun ham mashq qilish vaqti! 🔥 Bir suhbat boshlaylikmi?",
        "daily_media_type": "",
        "daily_media_file_id": "",
        "daily_time": "09:00",
        "daily_enabled": "1",
        "daily_target": "all",
        "trial_expired_text": "Sinov muddatingiz tugadi 😔\n\nAdmin bilan bog'laning yoki premium oling!",
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    streak_msgs = [
        (1, 2, "1-kunlik mashq bo'ldi! Ajoyib start 💪"),
        (3, 4, "{streak} kundan beri tinmayapsiz! Davom eting 🎯"),
        (5, 9, "Qoyilman! {streak} kun bo'ldi, zo'r boryapsiz 🔥"),
        (10, 19, "{streak} kun ketma-ket. Dahshat! 🚀"),
        (20, 29, "{streak} kun! Siz haqiqiy chempionsiz 🏆"),
        (30, 59, "Legendar {streak} kun! Siz rus tilini zabt etdingiz 👑"),
        (60, None, "{streak} kun! Siz allaqachon ustasiz! 🌟"),
    ]
    for rs, re, msg in streak_msgs:
        c.execute("INSERT OR IGNORE INTO streak_messages (range_start, range_end, message) VALUES (?, ?, ?)",
                  (rs, re, msg))

    topics = [
        ("O'zingni tanishtir", "Ism, kasb, shahar haqida", 1),
        ("Do'st topish", "Yangi tanishuvlar", 2),
        ("Kafeda buyurtma", "Ovqat, ichimlik", 3),
        ("Ish haqida", "Kasb, ish joyi", 4),
        ("Sayohat", "Shaharlar, reyslar", 5),
        ("Kundalik hayot", "Erkin mavzu", 6),
    ]
    for title, desc, ord in topics:
        c.execute("INSERT OR IGNORE INTO topics (title, description, ord) VALUES (?, ?, ?)",
                  (title, desc, ord))

    conn.commit()


# ===== USER HELPERS =====

def get_user(telegram_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    conn.close()
    return user


def create_user(telegram_id, name, username):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO users (telegram_id, name, username, status, trial_start) VALUES (?,?,?,'trial',?)",
        (telegram_id, name, username, str(date.today()))
    )
    conn.commit()
    conn.close()


def update_user(telegram_id, **kwargs):
    if not kwargs:
        return
    fields = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [telegram_id]
    conn = get_db()
    conn.execute(f"UPDATE users SET {fields} WHERE telegram_id=?", vals)
    conn.commit()
    conn.close()


def check_access(telegram_id):
    """
    Returns: 'ok', 'limit', 'expired', 'blocked'
    """
    user = get_user(telegram_id)
    if not user:
        return 'new'
    if user['status'] == 'blocked':
        return 'blocked'
    if user['status'] == 'premium':
        return 'ok'

    today = str(date.today())
    if user['status'] == 'trial':
        from datetime import timedelta
        trial_start = datetime.strptime(user['trial_start'], '%Y-%m-%d').date()
        trial_end = trial_start + timedelta(days=user['trial_days'])
        if date.today() > trial_end:
            update_user(telegram_id, status='expired')
            return 'expired'

        msg_today = user['msg_today'] if user['msg_date'] == today else 0
        limit = int(get_setting('free_daily_limit') or 3)
        if msg_today >= limit:
            return 'limit'
        return 'ok'

    if user['status'] == 'expired':
        return 'expired'
    return 'expired'


def increment_messages(telegram_id):
    today = str(date.today())
    conn = get_db()
    user = conn.execute("SELECT msg_today, msg_date FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
    if user:
        count = user['msg_today'] if user['msg_date'] == today else 0
        conn.execute("UPDATE users SET msg_today=?, msg_date=?, last_active=? WHERE telegram_id=?",
                     (count + 1, today, today, telegram_id))
        conn.commit()
    conn.close()


def update_streak(telegram_id):
    user = get_user(telegram_id)
    if not user:
        return 0
    today = str(date.today())
    last = user['last_active']
    from datetime import timedelta
    if last == today:
        return user['streak']
    yesterday = str(date.today() - timedelta(days=1))
    new_streak = (user['streak'] + 1) if last == yesterday else 1
    update_user(telegram_id, streak=new_streak, last_active=today)
    return new_streak


def get_streak_message(streak):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM streak_messages ORDER BY range_start"
    ).fetchall()
    conn.close()
    msg = None
    for row in rows:
        rs = row['range_start']
        re = row['range_end']
        if re is None:
            if streak >= rs:
                msg = row['message']
        elif rs <= streak <= re:
            msg = row['message']
            break
    if msg:
        return msg.replace('{streak}', str(streak))
    return None


# ===== SETTINGS =====

def get_setting(key):
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else None


def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()


# ===== TOPICS =====

def get_topics():
    conn = get_db()
    rows = conn.execute("SELECT * FROM topics WHERE active=1 ORDER BY ord").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ===== CHAT HISTORY =====

def get_history(telegram_id, limit=20):
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM chat_history WHERE telegram_id=? ORDER BY id DESC LIMIT ?",
        (telegram_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r['role'], "content": r['content']} for r in reversed(rows)]


def add_history(telegram_id, role, content):
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_history (telegram_id, role, content) VALUES (?,?,?)",
        (telegram_id, role, content)
    )
    conn.commit()
    conn.close()


def clear_history(telegram_id):
    conn = get_db()
    conn.execute("DELETE FROM chat_history WHERE telegram_id=?", (telegram_id,))
    conn.commit()
    conn.close()


# ===== BROADCASTS =====

def get_pending_broadcasts():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM broadcasts WHERE status='pending' AND (scheduled_at IS NULL OR scheduled_at <= datetime('now'))"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_users_by_target(target):
    conn = get_db()
    if target == 'all':
        rows = conn.execute("SELECT telegram_id FROM users WHERE status != 'blocked'").fetchall()
    elif target == 'premium':
        rows = conn.execute("SELECT telegram_id FROM users WHERE status='premium'").fetchall()
    elif target == 'trial':
        rows = conn.execute("SELECT telegram_id FROM users WHERE status='trial'").fetchall()
    elif target == 'expired':
        rows = conn.execute("SELECT telegram_id FROM users WHERE status='expired'").fetchall()
    elif target.startswith('inactive_'):
        days = int(target.split('_')[1])
        from datetime import timedelta
        cutoff = str(date.today() - timedelta(days=days))
        rows = conn.execute(
            "SELECT telegram_id FROM users WHERE status != 'blocked' AND (last_active < ? OR last_active IS NULL)",
            (cutoff,)
        ).fetchall()
    elif target.startswith('streak_'):
        streak_val = int(target.split('_')[1])
        rows = conn.execute(
            "SELECT telegram_id FROM users WHERE streak=?", (streak_val,)
        ).fetchall()
    else:
        rows = []
    conn.close()
    return [r['telegram_id'] for r in rows]
