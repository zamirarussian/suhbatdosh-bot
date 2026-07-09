import sqlite3
import os
from datetime import date, datetime, timedelta

DB = os.environ.get("DB_PATH", "zamira.db")


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def _add_col(c, table, col, coltype):
    try:
        c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")
    except sqlite3.OperationalError:
        pass  # ustun allaqachon bor


def init():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        name TEXT, username TEXT,
        status TEXT DEFAULT 'trial',
        trial_start TEXT, trial_days INTEGER DEFAULT 3,
        streak INTEGER DEFAULT 0,
        last_active TEXT,
        msg_today INTEGER DEFAULT 0,
        msg_date TEXT,
        created_at TEXT DEFAULT (date('now'))
    )""")
    # Dars-asosli suhbat/imtihon holati uchun yangi ustunlar (mavjud bazaga migratsiya)
    _add_col(c, "users", "mode", "TEXT DEFAULT ''")
    _add_col(c, "users", "cur_level", "TEXT DEFAULT ''")
    _add_col(c, "users", "cur_day", "INTEGER")
    _add_col(c, "users", "cur_week", "INTEGER")
    _add_col(c, "users", "exam_step", "INTEGER DEFAULT 0")
    # Har bir user uchun alohida kunlik xabar limiti: NULL = standart (free_limit),
    # 0 = cheksiz, musbat son = shu userga xos limit
    _add_col(c, "users", "daily_limit", "INTEGER")

    c.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY, value TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS streak_msgs (
        id INTEGER PRIMARY KEY,
        range_start INTEGER, range_end INTEGER,
        message TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS topics (
        id INTEGER PRIMARY KEY,
        title TEXT, description TEXT,
        ord INTEGER DEFAULT 0, active INTEGER DEFAULT 1
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER, role TEXT, content TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    c.commit()
    _seed(c)
    c.close()


def _seed(c):
    defs = {
        "free_limit": "3",
        "admin_login": "admin",
        "admin_password": "zamira2024",
        "welcome_text": "Salom! 👋 Men Zamira — rus tili muallimingizman.\n\n3 kunlik bepul sinov boshlaylikmi? 🚀",
        "welcome_media_type": "", "welcome_media_file_id": "",
        "daily_text": "Bugun ham mashq qilish vaqti! 🔥",
        "daily_media_type": "", "daily_media_file_id": "",
        "daily_time": "09:00", "daily_enabled": "1", "daily_target": "all",
        "trial_expired_text": "Sinov muddatingiz tugadi 😔\nAdmin bilan bog'laning!",
    }
    for k, v in defs.items():
        c.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))
    streaks = [
        (1,2,"1-kunlik mashq! Ajoyib start 💪"),
        (3,4,"{streak} kundan beri tinmayapsiz! Davom eting 🎯"),
        (5,9,"Qoyilman! {streak} kun bo'ldi 🔥"),
        (10,19,"{streak} kun ketma-ket. Dahshat! 🚀"),
        (20,29,"{streak} kun! Haqiqiy chempion 🏆"),
        (30,None,"Legendar {streak} kun! 👑"),
    ]
    for rs, re, m in streaks:
        c.execute("INSERT OR IGNORE INTO streak_msgs (range_start,range_end,message) VALUES (?,?,?)", (rs,re,m))
    tops = [
        ("O'zingni tanishtir","Ism, kasb, shahar",1),
        ("Do'st topish","Yangi tanishuvlar",2),
        ("Kafeda buyurtma","Ovqat, ichimlik",3),
        ("Ish haqida","Kasb, ish joyi",4),
        ("Sayohat","Shaharlar, reyslar",5),
    ]
    for t,d,o in tops:
        c.execute("INSERT OR IGNORE INTO topics (title,description,ord) VALUES (?,?,?)", (t,d,o))
    c.commit()


# ===== SETTINGS =====
def gs(key):
    c = db(); r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone(); c.close()
    return r["value"] if r else None

def ss(key, val):
    c = db(); c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key,val)); c.commit(); c.close()


# ===== USERS =====
def get_user(tid):
    c = db(); r = c.execute("SELECT * FROM users WHERE telegram_id=?", (tid,)).fetchone(); c.close(); return r

def create_user(tid, name, username):
    c = db()
    c.execute("INSERT OR IGNORE INTO users (telegram_id,name,username,trial_start) VALUES (?,?,?,?)",
              (tid, name, username, str(date.today())))
    c.commit(); c.close()

def update_user(tid, **kw):
    if not kw: return
    f = ",".join(f"{k}=?" for k in kw)
    c = db(); c.execute(f"UPDATE users SET {f} WHERE telegram_id=?", list(kw.values())+[tid]); c.commit(); c.close()

def effective_daily_limit(u):
    """None = cheksiz, son = shu userga qo'llanadigan kunlik xabar limiti.
    u['daily_limit']: NULL -> standart qiymat ishlatiladi (status'ga qarab),
    0 -> cheksiz, musbat son -> shu userga xos aniq limit (statusdan qat'i nazar)."""
    dl = u["daily_limit"] if "daily_limit" in u.keys() else None
    if dl is not None:
        return None if dl == 0 else dl
    if u["status"] == "premium":
        return None
    return int(gs("free_limit") or 3)

def check_access(tid):
    u = get_user(tid)
    if not u: return "new"
    if u["status"] == "blocked": return "blocked"
    if u["status"] == "trial":
        start = datetime.strptime(u["trial_start"], "%Y-%m-%d").date()
        if date.today() > start + timedelta(days=u["trial_days"] or 3):
            update_user(tid, status="expired"); return "expired"
    elif u["status"] == "expired":
        return "expired"
    limit = effective_daily_limit(u)
    if limit is not None:
        today = str(date.today())
        count = u["msg_today"] if u["msg_date"] == today else 0
        if count >= limit:
            return "limit"
    return "ok"

def set_daily_limit(tid, value):
    """value: None -> standart qiymatga qaytarish, 0 -> cheksiz, musbat son -> shu userga xos limit"""
    update_user(tid, daily_limit=value)

def inc_msg(tid):
    today = str(date.today())
    u = get_user(tid)
    if not u: return
    count = u["msg_today"] if u["msg_date"] == today else 0
    update_user(tid, msg_today=count+1, msg_date=today, last_active=today)

def update_streak(tid):
    u = get_user(tid)
    if not u: return 0
    today = str(date.today())
    yesterday = str(date.today() - timedelta(days=1))
    if u["last_active"] == today: return u["streak"] or 0
    new_streak = (u["streak"] or 0) + 1 if u["last_active"] == yesterday else 1
    update_user(tid, streak=new_streak, last_active=today)
    return new_streak

def get_streak_msg(streak):
    c = db()
    rows = c.execute("SELECT * FROM streak_msgs ORDER BY range_start").fetchall()
    c.close()
    for r in rows:
        if r["range_end"] is None:
            if streak >= r["range_start"]: return r["message"].replace("{streak}", str(streak))
        elif r["range_start"] <= streak <= r["range_end"]:
            return r["message"].replace("{streak}", str(streak))
    return None


# ===== DARS-ASOSLI SUHBAT / IMTIHON HOLATI =====
def set_mode(tid, mode, level=None, day=None, week=None):
    kw = {"mode": mode, "exam_step": 0}
    if level is not None: kw["cur_level"] = level
    if day is not None: kw["cur_day"] = day
    if week is not None: kw["cur_week"] = week
    update_user(tid, **kw)

def clear_mode(tid):
    update_user(tid, mode="", cur_level="", cur_day=None, cur_week=None, exam_step=0)

def inc_exam_step(tid):
    u = get_user(tid)
    step = (u["exam_step"] or 0) + 1 if u else 1
    update_user(tid, exam_step=step)
    return step


# ===== HISTORY =====
def get_history(tid, limit=20):
    c = db()
    rows = c.execute("SELECT role,content FROM history WHERE telegram_id=? ORDER BY id DESC LIMIT ?", (tid,limit)).fetchall()
    c.close()
    return [{"role":r["role"],"content":r["content"]} for r in reversed(rows)]

def add_history(tid, role, content):
    c = db(); c.execute("INSERT INTO history (telegram_id,role,content) VALUES (?,?,?)", (tid,role,content)); c.commit(); c.close()

def clear_history(tid):
    c = db(); c.execute("DELETE FROM history WHERE telegram_id=?", (tid,)); c.commit(); c.close()


# ===== TOPICS =====
def get_topics():
    c = db(); rows = c.execute("SELECT * FROM topics WHERE active=1 ORDER BY ord").fetchall(); c.close()
    return [dict(r) for r in rows]


# ===== BROADCAST =====
def get_users_for_broadcast(target):
    c = db()
    today = str(date.today())
    if target == "all":
        rows = c.execute("SELECT telegram_id FROM users WHERE status!='blocked'").fetchall()
    elif target == "premium":
        rows = c.execute("SELECT telegram_id FROM users WHERE status='premium'").fetchall()
    elif target == "trial":
        rows = c.execute("SELECT telegram_id FROM users WHERE status='trial'").fetchall()
    elif target == "expired":
        rows = c.execute("SELECT telegram_id FROM users WHERE status='expired'").fetchall()
    elif target.startswith("inactive_"):
        days = int(target.split("_")[1])
        cutoff = str(date.today() - timedelta(days=days))
        rows = c.execute("SELECT telegram_id FROM users WHERE status!='blocked' AND (last_active < ? OR last_active IS NULL)", (cutoff,)).fetchall()
    elif target.startswith("streak_"):
        s = int(target.split("_")[1])
        rows = c.execute("SELECT telegram_id FROM users WHERE streak=?", (s,)).fetchall()
    else:
        rows = []
    c.close()
    return [r["telegram_id"] for r in rows]
