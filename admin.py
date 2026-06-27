import os
import json
import asyncio
from datetime import datetime, date, timedelta
from functools import wraps
from flask import (
    Flask, render_template_string, request, redirect,
    url_for, session, jsonify, flash, send_from_directory
)
from database import (
    get_db, get_setting, set_setting, get_topics,
    get_users_by_target, init_db
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "zamira-secret-2024")

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")


@app.route("/miniapp.html")
def miniapp():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base_dir, "miniapp.html")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def send_tg_message(chat_id, text=None, media_type=None, media_file_id=None, caption=None):
    import requests
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        if media_type == "photo" and media_file_id:
            requests.post(f"{base}/sendPhoto", json={"chat_id": chat_id, "photo": media_file_id, "caption": caption or text})
        elif media_type == "video" and media_file_id:
            requests.post(f"{base}/sendVideo", json={"chat_id": chat_id, "video": media_file_id, "caption": caption or text})
        elif media_type == "video_note" and media_file_id:
            requests.post(f"{base}/sendVideoNote", json={"chat_id": chat_id, "video_note": media_file_id})
            if text:
                requests.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": text})
        elif media_type == "audio" and media_file_id:
            requests.post(f"{base}/sendAudio", json={"chat_id": chat_id, "audio": media_file_id, "caption": caption or text})
        elif media_type == "voice" and media_file_id:
            requests.post(f"{base}/sendVoice", json={"chat_id": chat_id, "voice": media_file_id, "caption": caption or text})
        elif text:
            requests.post(f"{base}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        print(f"TG error {chat_id}: {e}")


TEMPLATE = """
<!DOCTYPE html>
<html lang="uz">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zamira Admin</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#f5f7fb;color:#1a1a2e;font-size:14px}
.layout{display:flex;min-height:100vh}
.sidebar{width:220px;background:#fff;border-right:1px solid #e8ecf6;padding:20px 0;position:fixed;top:0;left:0;bottom:0;overflow-y:auto}
.sidebar-logo{padding:0 20px 16px;border-bottom:1px solid #e8ecf6;margin-bottom:12px;font-weight:700;font-size:15px;color:#1f54e0;display:flex;align-items:center;gap:8px}
.nav-item{display:flex;align-items:center;gap:10px;padding:9px 20px;font-size:13px;color:#5a6070;text-decoration:none;transition:.15s}
.nav-item:hover{background:#f0f4ff;color:#1f54e0}
.nav-item.active{background:#e8f0ff;color:#1f54e0;font-weight:500}
.nav-item i{font-size:17px}
.main{margin-left:220px;padding:24px;flex:1}
.page-title{font-size:20px;font-weight:700;color:#1a1a2e;margin-bottom:20px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:24px}
.kpi{background:#fff;border-radius:10px;padding:16px;border:1px solid #e8ecf6}
.kpi .num{font-size:26px;font-weight:700;color:#1a1a2e;margin-bottom:4px}
.kpi .label{font-size:12px;color:#7a8398}
.kpi.blue .num{color:#1f54e0}
.kpi.green .num{color:#1baf7a}
.kpi.red .num{color:#e42a3b}
.card{background:#fff;border-radius:10px;border:1px solid #e8ecf6;margin-bottom:20px;overflow:hidden}
.card-header{padding:14px 18px;border-bottom:1px solid #e8ecf6;font-weight:600;font-size:14px;display:flex;align-items:center;justify-content:space-between}
.card-body{padding:18px}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:12px;color:#7a8398;font-weight:500;padding:0 12px 10px;border-bottom:1px solid #e8ecf6}
td{padding:10px 12px;border-bottom:1px solid #f0f2f8;font-size:13px;vertical-align:middle}
tr:last-child td{border-bottom:none}
.badge{display:inline-block;padding:3px 8px;border-radius:5px;font-size:11px;font-weight:500}
.badge-premium{background:#deeaff;color:#1f54e0}
.badge-trial{background:#fff8ec;color:#7a4a00}
.badge-expired{background:#f0f2f8;color:#7a8398}
.badge-blocked{background:#fde8ea;color:#c42b3a}
input,select,textarea{width:100%;padding:8px 10px;border:1px solid #e0e4ef;border-radius:7px;font-size:13px;font-family:inherit;background:#fff;color:#1a1a2e}
input:focus,select:focus,textarea:focus{outline:none;border-color:#1f54e0}
.btn{padding:8px 16px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;border:none;font-family:inherit;transition:.15s}
.btn-primary{background:#1f54e0;color:#fff}
.btn-primary:hover{background:#1644c0}
.btn-danger{background:#e42a3b;color:#fff}
.btn-sm{padding:4px 10px;font-size:12px}
.btn-outline{background:#fff;border:1px solid #e0e4ef;color:#5a6070}
.btn-outline:hover{border-color:#1f54e0;color:#1f54e0}
.form-group{margin-bottom:14px}
.form-group label{display:block;font-size:12px;font-weight:500;color:#5a6070;margin-bottom:5px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.three-col{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
.alert{padding:10px 14px;border-radius:7px;font-size:13px;margin-bottom:14px}
.alert-success{background:#e4f5e0;color:#1a6020}
.alert-error{background:#fde8ea;color:#c42b3a}
.chip{display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;font-size:12px;border:1px solid #e0e4ef;cursor:pointer;margin:3px;background:#fff;color:#5a6070}
.chip.on{background:#deeaff;border-color:#1f54e0;color:#1f54e0;font-weight:500}
.media-btn{display:flex;align-items:center;gap:6px;padding:8px 12px;border:1px solid #e0e4ef;border-radius:7px;cursor:pointer;font-size:12px;color:#5a6070;background:#fff;margin-right:6px;margin-bottom:6px}
.media-btn:hover{border-color:#1f54e0;color:#1f54e0}
.streak-row{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f2f8}
.streak-row:last-child{border-bottom:none}
.streak-badge{background:#fff8ec;color:#7a4a00;border-radius:5px;padding:3px 9px;font-size:12px;font-weight:500;white-space:nowrap;min-width:80px;text-align:center}
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#f0f4ff}
.login-card{background:#fff;border-radius:14px;padding:36px 32px;width:340px;border:1px solid #e8ecf6}
.login-logo{text-align:center;margin-bottom:24px}
.login-logo i{font-size:40px;color:#1f54e0}
.login-logo h2{font-size:18px;font-weight:700;margin-top:8px}
</style>
</head>
<body>
{% if not logged_in %}
<div class="login-wrap">
<div class="login-card">
  <div class="login-logo">
    <i class="ti ti-robot"></i>
    <h2>Zamira Admin</h2>
  </div>
  {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
  <form method="POST" action="/admin/login">
    <div class="form-group"><label>Login</label><input name="login" placeholder="admin" required></div>
    <div class="form-group"><label>Parol</label><input type="password" name="password" placeholder="••••••••" required></div>
    <button class="btn btn-primary" style="width:100%;margin-top:8px">Kirish</button>
  </form>
</div>
</div>
{% else %}
<div class="layout">
<div class="sidebar">
  <div class="sidebar-logo"><i class="ti ti-robot"></i> Zamira Admin</div>
  <a href="/admin" class="nav-item {% if page=='dashboard' %}active{% endif %}"><i class="ti ti-chart-bar"></i> Dashboard</a>
  <a href="/admin/users" class="nav-item {% if page=='users' %}active{% endif %}"><i class="ti ti-users"></i> Foydalanuvchilar</a>
  <a href="/admin/streak" class="nav-item {% if page=='streak' %}active{% endif %}"><i class="ti ti-flame"></i> Streak xabarlari</a>
  <a href="/admin/topics" class="nav-item {% if page=='topics' %}active{% endif %}"><i class="ti ti-books"></i> Mavzular</a>
  <a href="/admin/broadcast" class="nav-item {% if page=='broadcast' %}active{% endif %}"><i class="ti ti-speakerphone"></i> Xabar yuborish</a>
  <a href="/admin/settings" class="nav-item {% if page=='settings' %}active{% endif %}"><i class="ti ti-settings"></i> Sozlamalar</a>
  <a href="/admin/logout" class="nav-item" style="margin-top:auto;color:#e42a3b"><i class="ti ti-logout"></i> Chiqish</a>
</div>
<div class="main">
{% block content %}{% endblock %}
</div>
</div>
{% endif %}
</body>
</html>
"""


def render_page(block_content, **kwargs):
    logged_in = session.get('logged_in', False)
    full = TEMPLATE.replace("{% block content %}{% endblock %}", block_content)
    full = full.replace("{% if not logged_in %}", "")
    full = full.replace("{% endif %}", "")
    return render_template_string(full, logged_in=logged_in, **kwargs)


@app.route('/admin/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        lg = request.form.get('login')
        pw = request.form.get('password')
        if lg == get_setting('admin_login') and pw == get_setting('admin_password'):
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        return render_template_string(TEMPLATE, logged_in=False, error="Login yoki parol noto'g'ri", page='')
    return render_template_string(TEMPLATE, logged_in=False, error=None, page='')


@app.route('/admin/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/admin')
@login_required
def dashboard():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()['c']
    premium = conn.execute("SELECT COUNT(*) as c FROM users WHERE status='premium'").fetchone()['c']
    trial = conn.execute("SELECT COUNT(*) as c FROM users WHERE status='trial'").fetchone()['c']
    expired = conn.execute("SELECT COUNT(*) as c FROM users WHERE status='expired'").fetchone()['c']
    today = str(date.today())
    active_today = conn.execute("SELECT COUNT(*) as c FROM users WHERE last_active=?", (today,)).fetchone()['c']
    msgs_today = conn.execute("SELECT SUM(msg_today) as s FROM users WHERE msg_date=?", (today,)).fetchone()['s'] or 0

    cutoff3 = str(date.today() - timedelta(days=3))
    cutoff5 = str(date.today() - timedelta(days=5))
    cutoff10 = str(date.today() - timedelta(days=10))
    inactive3 = conn.execute("SELECT COUNT(*) as c FROM users WHERE status!='blocked' AND last_active < ?", (cutoff3,)).fetchone()['c']
    inactive5 = conn.execute("SELECT COUNT(*) as c FROM users WHERE status!='blocked' AND last_active < ?", (cutoff5,)).fetchone()['c']
    inactive10 = conn.execute("SELECT COUNT(*) as c FROM users WHERE status!='blocked' AND last_active < ?", (cutoff10,)).fetchone()['c']
    conn.close()

    content = f"""
<div class="page-title">Dashboard</div>
<div class="kpi-grid">
  <div class="kpi"><div class="num">{total}</div><div class="label">Jami userlar</div></div>
  <div class="kpi blue"><div class="num">{active_today}</div><div class="label">Bugun faol</div></div>
  <div class="kpi"><div class="num">{msgs_today}</div><div class="label">Bugun xabarlar</div></div>
  <div class="kpi green"><div class="num">{premium}</div><div class="label">Premium</div></div>
  <div class="kpi"><div class="num">{trial}</div><div class="label">Sinov</div></div>
  <div class="kpi red"><div class="num">{expired}</div><div class="label">Tugagan</div></div>
</div>
<div class="two-col">
<div class="card"><div class="card-header">Faolsizlar</div><div class="card-body">
  <table><tr><td>3+ kun kelmagan</td><td style="text-align:right;color:#e42a3b;font-weight:600">{inactive3} ta</td></tr>
  <tr><td>5+ kun kelmagan</td><td style="text-align:right;color:#e42a3b;font-weight:600">{inactive5} ta</td></tr>
  <tr><td>10+ kun kelmagan</td><td style="text-align:right;color:#7a8398;font-weight:600">{inactive10} ta</td></tr></table>
</div></div>
<div class="card"><div class="card-header">Tezkor harakatlar</div><div class="card-body">
  <a href="/admin/broadcast?target=inactive_3" class="btn btn-outline btn-sm" style="display:block;margin-bottom:8px">📨 3+ kun kelmayotganlarga xabar</a>
  <a href="/admin/broadcast?target=expired" class="btn btn-outline btn-sm" style="display:block;margin-bottom:8px">📨 Muddati tugaganlarga</a>
  <a href="/admin/broadcast?target=all" class="btn btn-outline btn-sm" style="display:block">📨 Hammaga xabar</a>
</div></div>
</div>
"""
    return render_template_string(TEMPLATE.replace("{% block content %}{% endblock %}", content),
                                  logged_in=True, page='dashboard')


@app.route('/admin/users')
@login_required
def users():
    q = request.args.get('q', '')
    status_filter = request.args.get('status', 'all')
    conn = get_db()
    sql = "SELECT * FROM users WHERE 1=1"
    params = []
    if q:
        sql += " AND (name LIKE ? OR username LIKE ? OR telegram_id LIKE ?)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if status_filter != 'all':
        sql += " AND status=?"
        params.append(status_filter)
    sql += " ORDER BY created_at DESC LIMIT 100"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    badge_map = {
        'premium': 'premium', 'trial': 'trial',
        'expired': 'expired', 'blocked': 'blocked'
    }

    rows_html = ""
    for r in rows:
        b = badge_map.get(r['status'], 'expired')
        status_labels = {'premium': 'Premium', 'trial': 'Sinov', 'expired': 'Tugagan', 'blocked': 'Bloklangan'}
        sl = status_labels.get(r['status'], r['status'])
        today = str(date.today())
        msgs = r['msg_today'] if r['msg_date'] == today else 0

        action_opts = ""
        if r['status'] == 'premium':
            action_opts = '<option value="trial">Sinovga tushirish</option><option value="blocked">Bloklash</option>'
        elif r['status'] in ('trial', 'expired'):
            action_opts = '<option value="premium">✅ Premium berish</option><option value="trial_extend">🔄 +3 kun sinov</option><option value="blocked">🚫 Bloklash</option>'
        elif r['status'] == 'blocked':
            action_opts = '<option value="trial">🔓 Ochish (sinov)</option><option value="premium">✅ Premium berish</option>'

        rows_html += f"""
        <tr>
          <td>{r['name'] or '—'}</td>
          <td style="color:#7a8398">{r['telegram_id']}</td>
          <td>{'🔥 ' + str(r['streak']) if r['streak'] else '—'}</td>
          <td>{msgs}/{3 if r['status']!='premium' else '∞'}</td>
          <td>{r['last_active'] or '—'}</td>
          <td><span class="badge badge-{b}">{sl}</span></td>
          <td>
            <form method="POST" action="/admin/users/action" style="display:flex;gap:4px">
              <input type="hidden" name="telegram_id" value="{r['telegram_id']}">
              <select name="action" style="width:auto;font-size:12px;padding:3px 6px">
                <option value="">Amal...</option>
                {action_opts}
              </select>
              <button type="submit" class="btn btn-sm btn-outline">OK</button>
            </form>
          </td>
        </tr>"""

    content = f"""
<div class="page-title">Foydalanuvchilar</div>
<div class="card">
<div class="card-header">
  <form method="GET" style="display:flex;gap:8px;align-items:center;flex:1">
    <input name="q" value="{q}" placeholder="Ism yoki ID qidirish..." style="max-width:200px">
    <select name="status" style="width:auto">
      <option value="all" {'selected' if status_filter=='all' else ''}>Hammasi</option>
      <option value="premium" {'selected' if status_filter=='premium' else ''}>Premium</option>
      <option value="trial" {'selected' if status_filter=='trial' else ''}>Sinov</option>
      <option value="expired" {'selected' if status_filter=='expired' else ''}>Tugagan</option>
      <option value="blocked" {'selected' if status_filter=='blocked' else ''}>Bloklangan</option>
    </select>
    <button class="btn btn-outline btn-sm">Qidirish</button>
  </form>
</div>
<div class="card-body" style="padding:0">
<table>
<thead><tr><th>Ism</th><th>Telegram ID</th><th>Streak</th><th>Bugun</th><th>So'nggi</th><th>Status</th><th>Amal</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
</div>

<div class="card">
<div class="card-header">Tez dostup berish</div>
<div class="card-body">
<form method="POST" action="/admin/users/grant">
  <div style="display:flex;gap:8px;align-items:flex-end">
    <div class="form-group" style="flex:1;margin:0"><label>Telegram ID</label><input name="telegram_id" placeholder="12345678"></div>
    <div class="form-group" style="width:200px;margin:0"><label>Tur</label>
      <select name="access_type">
        <option value="premium">Premium — cheksiz</option>
        <option value="trial_3">Sinov — 3 kun</option>
        <option value="trial_7">Sinov — 7 kun</option>
        <option value="trial_30">Sinov — 30 kun</option>
      </select>
    </div>
    <button type="submit" class="btn btn-primary">Berish</button>
  </div>
</form>
</div>
</div>
"""
    return render_template_string(TEMPLATE.replace("{% block content %}{% endblock %}", content),
                                  logged_in=True, page='users')


@app.route('/admin/users/action', methods=['POST'])
@login_required
def user_action():
    tid = int(request.form['telegram_id'])
    action = request.form.get('action')
    conn = get_db()
    if action == 'premium':
        conn.execute("UPDATE users SET status='premium' WHERE telegram_id=?", (tid,))
    elif action == 'trial':
        conn.execute("UPDATE users SET status='trial', trial_start=?, trial_days=3 WHERE telegram_id=?",
                     (str(date.today()), tid))
    elif action == 'trial_extend':
        u = conn.execute("SELECT trial_days FROM users WHERE telegram_id=?", (tid,)).fetchone()
        days = (u['trial_days'] or 3) + 3
        conn.execute("UPDATE users SET status='trial', trial_days=?, trial_start=? WHERE telegram_id=?",
                     (days, str(date.today()), tid))
    elif action == 'blocked':
        conn.execute("UPDATE users SET status='blocked' WHERE telegram_id=?", (tid,))
    conn.commit()
    conn.close()
    return redirect(url_for('users'))


@app.route('/admin/users/grant', methods=['POST'])
@login_required
def user_grant():
    tid = int(request.form['telegram_id'])
    access_type = request.form.get('access_type', 'premium')
    conn = get_db()
    if access_type == 'premium':
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, name, status) VALUES (?,?,?)", (tid, 'Unknown', 'premium'))
        conn.execute("UPDATE users SET status='premium' WHERE telegram_id=?", (tid,))
    elif access_type.startswith('trial_'):
        days = int(access_type.split('_')[1])
        conn.execute("INSERT OR IGNORE INTO users (telegram_id, name, status, trial_start, trial_days) VALUES (?,?,'trial',?,?)",
                     (tid, 'Unknown', str(date.today()), days))
        conn.execute("UPDATE users SET status='trial', trial_start=?, trial_days=? WHERE telegram_id=?",
                     (str(date.today()), days, tid))
    conn.commit()
    conn.close()
    return redirect(url_for('users'))


@app.route('/admin/streak', methods=['GET', 'POST'])
@login_required
def streak_messages():
    conn = get_db()
    if request.method == 'POST':
        rows = conn.execute("SELECT id FROM streak_messages ORDER BY range_start").fetchall()
        for row in rows:
            msg = request.form.get(f"msg_{row['id']}", "")
            conn.execute("UPDATE streak_messages SET message=? WHERE id=?", (msg, row['id']))
        conn.commit()
        flash("Saqlandi!")

    msgs = conn.execute("SELECT * FROM streak_messages ORDER BY range_start").fetchall()
    conn.close()

    rows_html = ""
    for m in msgs:
        re_label = f"–{m['range_end']}" if m['range_end'] else "+"
        rows_html += f"""
        <div class="streak-row">
          <span class="streak-badge">{m['range_start']}{re_label} kun</span>
          <input name="msg_{m['id']}" value="{m['message']}" style="flex:1">
        </div>"""

    content = f"""
<div class="page-title">Streak xabarlari</div>
<div class="card">
<div class="card-header">Xabarlarni tahrirlash</div>
<div class="card-body">
<p style="font-size:12px;color:#7a8398;margin-bottom:14px">💡 <code>{{streak}}</code> — avtomatik kun soni qo'yiladi</p>
<form method="POST">{rows_html}
<button type="submit" class="btn btn-primary" style="margin-top:16px">Saqlash</button>
</form>
</div>
</div>
"""
    return render_template_string(TEMPLATE.replace("{% block content %}{% endblock %}", content),
                                  logged_in=True, page='streak')


@app.route('/admin/topics', methods=['GET', 'POST'])
@login_required
def topics():
    conn = get_db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update':
            ids = request.form.getlist('id[]')
            titles = request.form.getlist('title[]')
            descs = request.form.getlist('desc[]')
            for i, tid in enumerate(ids):
                conn.execute("UPDATE topics SET title=?, description=?, ord=? WHERE id=?",
                             (titles[i], descs[i], i+1, tid))
            conn.commit()
            flash("Saqlandi!")
        elif action == 'add':
            title = request.form.get('new_title', '')
            desc = request.form.get('new_desc', '')
            if title:
                max_ord = conn.execute("SELECT MAX(ord) as m FROM topics").fetchone()['m'] or 0
                conn.execute("INSERT INTO topics (title, description, ord) VALUES (?,?,?)", (title, desc, max_ord+1))
                conn.commit()
        elif action == 'delete':
            tid = request.form.get('del_id')
            conn.execute("DELETE FROM topics WHERE id=?", (tid,))
            conn.commit()

    rows = conn.execute("SELECT * FROM topics ORDER BY ord").fetchall()
    conn.close()

    rows_html = ""
    for r in rows:
        rows_html += f"""
        <tr>
          <input type="hidden" name="id[]" value="{r['id']}">
          <td style="width:30px;color:#7a8398">{r['ord']}</td>
          <td><input name="title[]" value="{r['title']}" style="font-size:13px"></td>
          <td><input name="desc[]" value="{r['description'] or ''}" style="font-size:13px"></td>
          <td>
            <form method="POST" style="display:inline">
              <input type="hidden" name="action" value="delete">
              <input type="hidden" name="del_id" value="{r['id']}">
              <button type="submit" class="btn btn-danger btn-sm">O'chirish</button>
            </form>
          </td>
        </tr>"""

    content = f"""
<div class="page-title">Mavzular</div>
<div class="card">
<div class="card-header">Mavzularni boshqarish</div>
<div class="card-body">
<form method="POST">
  <input type="hidden" name="action" value="update">
  <table>
    <thead><tr><th>#</th><th>Sarlavha</th><th>Tavsif</th><th></th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <button type="submit" class="btn btn-primary" style="margin-top:14px">Saqlash</button>
</form>
<hr style="margin:20px 0;border:none;border-top:1px solid #e8ecf6">
<form method="POST">
  <input type="hidden" name="action" value="add">
  <div style="display:flex;gap:8px;align-items:flex-end">
    <div class="form-group" style="flex:1;margin:0"><label>Yangi mavzu sarlavhasi</label><input name="new_title" placeholder="Masalan: Sport haqida"></div>
    <div class="form-group" style="flex:1;margin:0"><label>Tavsif</label><input name="new_desc" placeholder="Qisqa tavsif"></div>
    <button type="submit" class="btn btn-primary">Qo'shish</button>
  </div>
</form>
</div>
</div>
"""
    return render_template_string(TEMPLATE.replace("{% block content %}{% endblock %}", content),
                                  logged_in=True, page='topics')


@app.route('/admin/broadcast', methods=['GET', 'POST'])
@login_required
def broadcast():
    msg = None
    default_target = request.args.get('target', 'all')

    if request.method == 'POST':
        text = request.form.get('text', '')
        media_type = request.form.get('media_type', '')
        media_file_id = request.form.get('media_file_id', '')
        target = request.form.get('target', 'all')
        scheduled_at = request.form.get('scheduled_at', '')
        now_send = request.form.get('send_now') == '1'

        conn = get_db()
        conn.execute(
            "INSERT INTO broadcasts (text, media_type, media_file_id, target, scheduled_at, status) VALUES (?,?,?,?,?,?)",
            (text, media_type, media_file_id, target,
             None if now_send else scheduled_at,
             'pending')
        )
        conn.commit()
        conn.close()

        if now_send:
            tids = get_users_by_target(target)
            for tid in tids:
                send_tg_message(tid, text=text, media_type=media_type, media_file_id=media_file_id)
            conn = get_db()
            conn.execute("UPDATE broadcasts SET status='sent', sent_at=datetime('now') WHERE status='pending' AND scheduled_at IS NULL")
            conn.commit()
            conn.close()
            msg = f"✅ {len(tids)} ta userlarga yuborildi!"
        else:
            msg = f"⏰ Xabar {scheduled_at} ga rejalashtildi."

    targets = [
        ('all', 'Hammaga'),
        ('premium', 'Faqat premiumga'),
        ('trial', 'Faqat sinov userlarga'),
        ('expired', 'Muddati tugaganlarga'),
        ('inactive_3', '3+ kun kelmayotganlarga'),
        ('inactive_5', '5+ kun kelmayotganlarga'),
        ('inactive_10', '10+ kun kelmayotganlarga'),
        ('streak_5', 'Streak 5 kun 🔥'),
        ('streak_10', 'Streak 10 kun 🔥'),
        ('streak_15', 'Streak 15 kun'),
        ('streak_20', 'Streak 20 kun'),
        ('streak_30', 'Streak 30 kun'),
        ('streak_50', 'Streak 50 kun'),
        ('streak_60', 'Streak 60 kun'),
    ]

    target_opts = ""
    for val, label in targets:
        sel = "selected" if val == default_target else ""
        target_opts += f'<option value="{val}" {sel}>{label}</option>'

    media_types = [
        ('', 'Faqat matn'),
        ('photo', '🖼 Rasm'),
        ('video', '🎬 Video'),
        ('video_note', '⭕ Dumaloq video'),
        ('audio', '🎵 Audio'),
        ('voice', '🎤 Ovozli xabar'),
    ]
    mt_opts = "".join(f'<option value="{v}">{l}</option>' for v, l in media_types)

    msg_html = f'<div class="alert alert-success">{msg}</div>' if msg else ''

    conn = get_db()
    hist = conn.execute("SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT 10").fetchall()
    conn.close()
    hist_html = ""
    for h in hist:
        hist_html += f"<tr><td>{h['target']}</td><td>{(h['text'] or '')[:40]}...</td><td>{h['status']}</td><td>{h['created_at']}</td></tr>"

    content = f"""
<div class="page-title">Xabar yuborish</div>
{msg_html}
<div class="two-col">
<div class="card">
<div class="card-header">Yangi xabar</div>
<div class="card-body">
<form method="POST">
  <div class="form-group"><label>Kimga?</label><select name="target">{target_opts}</select></div>
  <div class="form-group"><label>Matn</label><textarea name="text" rows="4" placeholder="Xabar matni..."></textarea></div>
  <div class="two-col">
    <div class="form-group"><label>Media turi</label><select name="media_type">{mt_opts}</select></div>
    <div class="form-group"><label>Media File ID (Telegramdan)</label><input name="media_file_id" placeholder="AgACAgI..."></div>
  </div>
  <hr style="margin:12px 0;border:none;border-top:1px solid #e8ecf6">
  <div class="form-group">
    <label><input type="checkbox" name="send_now" value="1" checked style="width:auto;margin-right:6px">Hozir yuborish</label>
  </div>
  <div class="form-group"><label>Yoki vaqt belgilang</label><input type="datetime-local" name="scheduled_at"></div>
  <button type="submit" class="btn btn-primary">Yuborish</button>
</form>
</div>
</div>

<div class="card">
<div class="card-header">So'nggi xabarlar</div>
<div class="card-body" style="padding:0">
<table>
<thead><tr><th>Kimga</th><th>Matn</th><th>Status</th><th>Sana</th></tr></thead>
<tbody>{hist_html}</tbody>
</table>
</div>
</div>
</div>
"""
    return render_template_string(TEMPLATE.replace("{% block content %}{% endblock %}", content),
                                  logged_in=True, page='broadcast')


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def settings():
    msg = None
    if request.method == 'POST':
        section = request.form.get('section')
        if section == 'bot':
            set_setting('free_daily_limit', request.form.get('free_daily_limit', '3'))
            set_setting('welcome_text', request.form.get('welcome_text', ''))
            set_setting('welcome_media_type', request.form.get('welcome_media_type', ''))
            set_setting('welcome_media_file_id', request.form.get('welcome_media_file_id', ''))
            set_setting('daily_text', request.form.get('daily_text', ''))
            set_setting('daily_media_type', request.form.get('daily_media_type', ''))
            set_setting('daily_media_file_id', request.form.get('daily_media_file_id', ''))
            set_setting('daily_time', request.form.get('daily_time', '09:00'))
            set_setting('daily_enabled', '1' if request.form.get('daily_enabled') else '0')
            set_setting('daily_target', request.form.get('daily_target', 'all'))
            set_setting('trial_expired_text', request.form.get('trial_expired_text', ''))
            msg = "✅ Bot sozlamalari saqlandi!"
        elif section == 'admin':
            new_pw = request.form.get('new_password', '')
            if new_pw:
                set_setting('admin_password', new_pw)
            set_setting('admin_login', request.form.get('admin_login', 'admin'))
            msg = "✅ Admin ma'lumotlari saqlandi!"

    def gs(k):
        return get_setting(k) or ''

    media_opts = lambda cur: "".join(
        f'<option value="{v}" {"selected" if v==cur else ""}>{l}</option>'
        for v, l in [('','Faqat matn'),('photo','🖼 Rasm'),('video','🎬 Video'),
                     ('video_note','⭕ Dumaloq'),('audio','🎵 Audio'),('voice','🎤 Ovozli')]
    )

    target_opts = lambda cur: "".join(
        f'<option value="{v}" {"selected" if v==cur else ""}>{l}</option>'
        for v, l in [('all','Hammaga'),('trial','Sinov userlarga'),('premium','Premiumga')]
    )

    msg_html = f'<div class="alert alert-success">{msg}</div>' if msg else ''

    content = f"""
<div class="page-title">Sozlamalar</div>
{msg_html}
<div class="two-col">
<div>
  <div class="card">
  <div class="card-header">Bot sozlamalari</div>
  <div class="card-body">
  <form method="POST">
    <input type="hidden" name="section" value="bot">
    <div class="form-group"><label>Bepul kunlik limit (xabar soni)</label><input type="number" name="free_daily_limit" value="{gs('free_daily_limit')}"></div>

    <hr style="margin:12px 0;border:none;border-top:1px solid #e8ecf6">
    <div style="font-weight:600;font-size:13px;margin-bottom:10px">Salomlashuv xabari</div>
    <div class="form-group"><label>Matn</label><textarea name="welcome_text" rows="3">{gs('welcome_text')}</textarea></div>
    <div class="two-col">
      <div class="form-group"><label>Media turi</label><select name="welcome_media_type">{media_opts(gs('welcome_media_type'))}</select></div>
      <div class="form-group"><label>File ID</label><input name="welcome_media_file_id" value="{gs('welcome_media_file_id')}" placeholder="Telegram File ID"></div>
    </div>

    <hr style="margin:12px 0;border:none;border-top:1px solid #e8ecf6">
    <div style="font-weight:600;font-size:13px;margin-bottom:10px">Kundalik eslatma</div>
    <div class="form-group"><label>Matn</label><textarea name="daily_text" rows="2">{gs('daily_text')}</textarea></div>
    <div class="two-col">
      <div class="form-group"><label>Media turi</label><select name="daily_media_type">{media_opts(gs('daily_media_type'))}</select></div>
      <div class="form-group"><label>File ID</label><input name="daily_media_file_id" value="{gs('daily_media_file_id')}" placeholder="Telegram File ID"></div>
    </div>
    <div class="three-col">
      <div class="form-group"><label>Yuborish vaqti</label><input type="time" name="daily_time" value="{gs('daily_time') or '09:00'}"></div>
      <div class="form-group"><label>Kimga</label><select name="daily_target">{target_opts(gs('daily_target'))}</select></div>
      <div class="form-group"><label>Holati</label>
        <label style="display:flex;align-items:center;gap:6px;margin-top:8px">
          <input type="checkbox" name="daily_enabled" value="1" {'checked' if gs('daily_enabled')=='1' else ''} style="width:auto">
          Yoqilgan
        </label>
      </div>
    </div>

    <hr style="margin:12px 0;border:none;border-top:1px solid #e8ecf6">
    <div class="form-group"><label>Sinov tugaganda xabar</label><textarea name="trial_expired_text" rows="2">{gs('trial_expired_text')}</textarea></div>

    <button type="submit" class="btn btn-primary">Saqlash</button>
  </form>
  </div>
  </div>
</div>

<div>
  <div class="card">
  <div class="card-header">Admin kirish</div>
  <div class="card-body">
  <form method="POST">
    <input type="hidden" name="section" value="admin">
    <div class="form-group"><label>Login</label><input name="admin_login" value="{gs('admin_login')}"></div>
    <div class="form-group"><label>Yangi parol (bo'sh qoldirsangiz o'zgarmaydi)</label><input type="password" name="new_password" placeholder="Yangi parol..."></div>
    <button type="submit" class="btn btn-primary">Saqlash</button>
  </form>
  </div>
  </div>

  <div class="card">
  <div class="card-header">File ID olish yo'riqnomasi</div>
  <div class="card-body">
    <p style="font-size:12px;color:#5a6070;line-height:1.7">
    Rasm/video/audio File ID olish uchun:<br>
    1. Botga rasm/video yuboring<br>
    2. Bot adminka URL ga forward qiling<br>
    3. Yoki <code>@getidsbot</code> ga yuboring<br><br>
    File ID ni settings sahifasiga kiriting.
    </p>
  </div>
  </div>
</div>
</div>
"""
    return render_template_string(TEMPLATE.replace("{% block content %}{% endblock %}", content),
                                  logged_in=True, page='settings')


# Mini App API endpoints
@app.route('/api/miniapp/profile')
def api_profile():
    tid = request.args.get('telegram_id')
    if not tid:
        return jsonify({'error': 'no id'}), 400
    from database import get_user
    user = get_user(int(tid))
    if not user:
        return jsonify({'error': 'not found'}), 404

    conn = get_db()
    active_days = conn.execute(
        "SELECT DISTINCT DATE(created_at) as d FROM chat_history WHERE telegram_id=?", (tid,)
    ).fetchall()
    conn.close()

    return jsonify({
        'name': user['name'],
        'streak': user['streak'],
        'status': user['status'],
        'last_active': user['last_active'],
        'created_at': user['created_at'],
    })


@app.route('/api/miniapp/topics')
def api_topics():
    topics = get_topics()
    return jsonify(topics)


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
