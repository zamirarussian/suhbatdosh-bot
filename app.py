import os, logging, asyncio, threading, time
from flask import Flask, request, jsonify, session, redirect, render_template_string, send_from_directory
from functools import wraps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "zamira2024")

TOKEN      = os.environ.get("TELEGRAM_TOKEN", "")
LID_TOKEN  = os.environ.get("LID_BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

_tg = {}  # {token: (app, loop)}


def get_tg(token, name):
    if token in _tg:
        return _tg[token]
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
    tg_app = Application.builder().token(token).build()
    if name == "main":
        import bot as b
        tg_app.add_handler(CommandHandler("start", b.start))
        tg_app.add_handler(CommandHandler("reset", b.reset))
        tg_app.add_handler(CommandHandler("end", b.end_command))
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, b.handle_message))
        tg_app.add_handler(MessageHandler(filters.VOICE, b.handle_voice_msg))
        tg_app.add_handler(CallbackQueryHandler(b.handle_callback))
    else:
        import lid_bot as lb
        tg_app.add_handler(CommandHandler("start", lb.start))
        tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lb.handle_message))
        tg_app.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.AUDIO |
            filters.VOICE | filters.Document.ALL | filters.VIDEO_NOTE,
            lb.handle_media_message))
    loop = asyncio.new_event_loop()
    loop.run_until_complete(tg_app.initialize())
    _tg[token] = (tg_app, loop)
    logger.info(f"{name} bot tayyor")
    return _tg[token]


def setup_webhooks():
    time.sleep(3)
    import requests
    if TOKEN and WEBHOOK_URL:
        r = requests.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                         json={"url": f"{WEBHOOK_URL}/webhook/main", "drop_pending_updates": True})
        logger.info(f"Main webhook: {r.json().get('description')}")
    if LID_TOKEN and WEBHOOK_URL:
        r = requests.post(f"https://api.telegram.org/bot{LID_TOKEN}/setWebhook",
                         json={"url": f"{WEBHOOK_URL}/webhook/lid", "drop_pending_updates": True})
        logger.info(f"Lid webhook: {r.json().get('description')}")


@app.route("/status")
def status():
    return jsonify({"ok": True, "webhook": WEBHOOK_URL})


@app.route("/webhook/main", methods=["POST"])
def wh_main():
    try:
        from telegram import Update
        tg_app, loop = get_tg(TOKEN, "main")
        loop.run_until_complete(tg_app.process_update(
            Update.de_json(request.get_json(force=True), tg_app.bot)))
    except Exception as e:
        logger.error(f"wh_main: {e}")
    return jsonify({"ok": True})


@app.route("/webhook/lid", methods=["POST"])
def wh_lid():
    if not LID_TOKEN:
        return jsonify({"ok": False})
    try:
        from telegram import Update
        tg_app, loop = get_tg(LID_TOKEN, "lid")
        loop.run_until_complete(tg_app.process_update(
            Update.de_json(request.get_json(force=True), tg_app.bot)))
    except Exception as e:
        logger.error(f"wh_lid: {e}")
    return jsonify({"ok": True})


@app.route("/miniapp.html")
def miniapp():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "miniapp.html")


# ===== ADMIN =====

def login_required(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get("logged_in"):
            return redirect("/admin/login")
        return f(*a, **kw)
    return d


BASE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Zamira Admin</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#f5f7fb;color:#1a1a2e;font-size:14px}
.layout{display:flex;min-height:100vh}
.sidebar{width:220px;background:#fff;border-right:1px solid #e8ecf6;padding:20px 0;position:fixed;top:0;left:0;bottom:0;overflow-y:auto}
.logo{padding:0 20px 16px;border-bottom:1px solid #e8ecf6;margin-bottom:12px;font-weight:700;font-size:15px;color:#1f54e0}
.nav{display:flex;align-items:center;gap:10px;padding:9px 20px;font-size:13px;color:#5a6070;text-decoration:none;transition:.15s}
.nav:hover{background:#f0f4ff;color:#1f54e0}
.nav.on{background:#e8f0ff;color:#1f54e0;font-weight:500}
.nav i{font-size:17px}
.nav-sep{padding:6px 20px;font-size:10px;font-weight:700;color:#7a8398;text-transform:uppercase;letter-spacing:.6px;margin-top:8px}
.main{margin-left:220px;padding:24px;flex:1}
.title{font-size:20px;font-weight:700;margin-bottom:20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:24px}
.kpi{background:#fff;border-radius:10px;padding:16px;border:1px solid #e8ecf6}
.kpi .n{font-size:26px;font-weight:700;color:#1a1a2e}
.kpi .l{font-size:12px;color:#7a8398}
.card{background:#fff;border-radius:10px;border:1px solid #e8ecf6;margin-bottom:20px}
.ch{padding:14px 18px;border-bottom:1px solid #e8ecf6;font-weight:600;font-size:14px;display:flex;align-items:center;justify-content:space-between}
.cb{padding:18px}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:12px;color:#7a8398;font-weight:500;padding:0 12px 10px;border-bottom:1px solid #e8ecf6}
td{padding:10px 12px;border-bottom:1px solid #f0f2f8;font-size:13px;vertical-align:middle}
input,select,textarea{width:100%;padding:8px 10px;border:1px solid #e0e4ef;border-radius:7px;font-size:13px;font-family:inherit;background:#fff}
.btn{padding:8px 16px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;border:none;font-family:inherit}
.btn-p{background:#1f54e0;color:#fff}
.btn-o{background:#fff;border:1px solid #e0e4ef;color:#5a6070}
.btn-s{padding:4px 10px;font-size:12px}
.btn-r{background:#e42a3b;color:#fff}
.fg{margin-bottom:14px}
.fg label{display:block;font-size:12px;font-weight:500;color:#5a6070;margin-bottom:5px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.alert{padding:10px 14px;border-radius:7px;font-size:13px;margin-bottom:14px;background:#e4f5e0;color:#1a6020}
.bp{background:#deeaff;color:#1f54e0;border-radius:5px;padding:3px 8px;font-size:11px;font-weight:500}
.bt{background:#fff8ec;color:#7a4a00;border-radius:5px;padding:3px 8px;font-size:11px;font-weight:500}
.be{background:#f0f2f8;color:#7a8398;border-radius:5px;padding:3px 8px;font-size:11px}
.bb{background:#fde8ea;color:#c42b3a;border-radius:5px;padding:3px 8px;font-size:11px}
</style></head><body>
<div class="layout">
<div class="sidebar">
<div class="logo">🤖 Zamira Admin</div>
<div class="nav-sep">Suhbatdosh Bot</div>
<a href="/admin" class="nav {%if p=='dash'%}on{%endif%}"><i class="ti ti-chart-bar"></i> Dashboard</a>
<a href="/admin/users" class="nav {%if p=='users'%}on{%endif%}"><i class="ti ti-users"></i> Foydalanuvchilar</a>
<a href="/admin/streak" class="nav {%if p=='streak'%}on{%endif%}"><i class="ti ti-flame"></i> Streak xabarlari</a>
<a href="/admin/topics" class="nav {%if p=='topics'%}on{%endif%}"><i class="ti ti-books"></i> Mavzular</a>
<a href="/admin/broadcast" class="nav {%if p=='bc'%}on{%endif%}"><i class="ti ti-speakerphone"></i> Xabar yuborish</a>
<a href="/admin/settings" class="nav {%if p=='sett'%}on{%endif%}"><i class="ti ti-settings"></i> Sozlamalar</a>
<div class="nav-sep">Lid Magnit Bot</div>
<a href="/admin/lid" class="nav {%if p=='lid'%}on{%endif%}"><i class="ti ti-magnet"></i> Dashboard</a>
<a href="/admin/lid/links" class="nav {%if p=='lid_links'%}on{%endif%}"><i class="ti ti-link"></i> Linklar</a>
<a href="/admin/lid/settings" class="nav {%if p=='lid_sett'%}on{%endif%}"><i class="ti ti-settings"></i> Sozlamalar</a>
<a href="/admin/logout" class="nav" style="color:#e42a3b;margin-top:20px"><i class="ti ti-logout"></i> Chiqish</a>
</div>
<div class="main">{{content}}</div>
</div></body></html>"""


def page(content, p=""):
    return BASE.replace("{{content}}", content).replace("{%if p=='%s'%}on{%endif%}" % p, "on").replace(
        "{%if p=='", "").replace("'%}on{%endif%}", "")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    from database import get_setting
    err = ""
    if request.method == "POST":
        if (request.form.get("login") == (get_setting("admin_login") or "admin") and
                request.form.get("password") == (get_setting("admin_password") or "zamira2024")):
            session["logged_in"] = True
            return redirect("/admin")
        err = "<p style='color:red;margin-bottom:12px'>Noto'g'ri</p>"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title>
    <style>*{{box-sizing:border-box}}body{{font-family:system-ui;background:#f0f4ff;display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .c{{background:#fff;border-radius:14px;padding:36px 32px;width:340px;border:1px solid #e8ecf6}}h2{{font-size:18px;font-weight:700;margin-bottom:20px;text-align:center}}
    label{{font-size:12px;color:#5a6070;display:block;margin-bottom:4px}}input{{width:100%;padding:9px 12px;border:1px solid #e0e4ef;border-radius:8px;font-size:13px;margin-bottom:14px}}
    button{{width:100%;padding:10px;background:#1f54e0;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}}</style></head>
    <body><div class="c"><h2>🤖 Zamira Admin</h2>{err}
    <form method="POST"><label>Login</label><input name="login"><label>Parol</label><input type="password" name="password"><button>Kirish</button></form>
    </div></body></html>"""


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")


@app.route("/admin")
@login_required
def admin_dash():
    from database import get_db
    from datetime import date
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    premium = conn.execute("SELECT COUNT(*) as c FROM users WHERE status='premium'").fetchone()["c"]
    today = str(date.today())
    active = conn.execute("SELECT COUNT(*) as c FROM users WHERE last_active=?", (today,)).fetchone()["c"]
    msgs = conn.execute("SELECT SUM(msg_today) as s FROM users WHERE msg_date=?", (today,)).fetchone()["s"] or 0
    conn.close()
    c = f"""<div class="title">Dashboard</div>
    <div class="kpis">
    <div class="kpi"><div class="n">{total}</div><div class="l">Jami userlar</div></div>
    <div class="kpi"><div class="n" style="color:#1f54e0">{active}</div><div class="l">Bugun faol</div></div>
    <div class="kpi"><div class="n">{msgs}</div><div class="l">Bugun xabarlar</div></div>
    <div class="kpi"><div class="n" style="color:#1baf7a">{premium}</div><div class="l">Premium</div></div>
    </div>
    <div class="card"><div class="ch">Tezkor harakatlar</div><div class="cb">
    <a href="/admin/broadcast" class="btn btn-o" style="margin-right:8px">📨 Xabar yuborish</a>
    <a href="/admin/users" class="btn btn-o">👥 Foydalanuvchilar</a>
    </div></div>"""
    return page(c, "dash")


@app.route("/admin/users", methods=["GET", "POST"])
@login_required
def admin_users():
    from database import get_db
    from datetime import date, timedelta
    conn = get_db()
    if request.method == "POST":
        tid = int(request.form.get("tid", 0))
        action = request.form.get("action", "")
        if action == "premium":
            conn.execute("UPDATE users SET status='premium' WHERE telegram_id=?", (tid,))
        elif action == "trial":
            conn.execute("UPDATE users SET status='trial', trial_start=?, trial_days=3 WHERE telegram_id=?",
                        (str(date.today()), tid))
        elif action == "blocked":
            conn.execute("UPDATE users SET status='blocked' WHERE telegram_id=?", (tid,))
        elif action == "unblock":
            conn.execute("UPDATE users SET status='trial' WHERE telegram_id=?", (tid,))
        conn.commit()

    q = request.args.get("q", "")
    sf = request.args.get("s", "all")
    sql = "SELECT * FROM users WHERE 1=1"
    params = []
    if q:
        sql += " AND (name LIKE ? OR telegram_id LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if sf != "all":
        sql += " AND status=?"
        params.append(sf)
    sql += " ORDER BY created_at DESC LIMIT 50"
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    today = str(date.today())
    rows_html = ""
    for r in rows:
        bmap = {"premium": "bp", "trial": "bt", "expired": "be", "blocked": "bb"}
        bc = bmap.get(r["status"], "be")
        sl = {"premium": "Premium", "trial": "Sinov", "expired": "Tugagan", "blocked": "Bloklangan"}.get(r["status"], r["status"])
        msgs = r["msg_today"] if r["msg_date"] == today else 0
        opts = ""
        if r["status"] == "premium":
            opts = '<option value="trial">Sinovga</option><option value="blocked">Bloklash</option>'
        elif r["status"] in ("trial", "expired"):
            opts = '<option value="premium">✅ Premium</option><option value="blocked">🚫 Bloklash</option>'
        elif r["status"] == "blocked":
            opts = '<option value="trial">🔓 Ochish</option><option value="premium">✅ Premium</option>'
        rows_html += f"""<tr><td>{r["name"] or "—"}</td><td style="color:#7a8398">{r["telegram_id"]}</td>
        <td>{"🔥 "+str(r["streak"]) if r["streak"] else "—"}</td><td>{msgs}</td>
        <td><span class="{bc}">{sl}</span></td>
        <td><form method="POST" style="display:flex;gap:4px">
        <input type="hidden" name="tid" value="{r["telegram_id"]}">
        <select name="action" style="width:auto;font-size:12px;padding:3px 6px"><option value="">Amal...</option>{opts}</select>
        <button type="submit" class="btn btn-o btn-s">OK</button></form></td></tr>"""

    c = f"""<div class="title">Foydalanuvchilar</div>
    <div class="card"><div class="ch">
    <form method="GET" style="display:flex;gap:8px">
    <input name="q" value="{q}" placeholder="Qidirish..." style="max-width:200px">
    <select name="s" style="width:auto">
    <option value="all">Hammasi</option><option value="premium" {"selected" if sf=="premium" else ""}>Premium</option>
    <option value="trial" {"selected" if sf=="trial" else ""}>Sinov</option>
    <option value="expired" {"selected" if sf=="expired" else ""}>Tugagan</option>
    <option value="blocked" {"selected" if sf=="blocked" else ""}>Bloklangan</option>
    </select><button class="btn btn-o btn-s">Qidirish</button></form></div>
    <div class="cb" style="padding:0"><table>
    <thead><tr><th>Ism</th><th>ID</th><th>Streak</th><th>Bugun</th><th>Status</th><th>Amal</th></tr></thead>
    <tbody>{rows_html}</tbody></table></div></div>"""
    return page(c, "users")


@app.route("/admin/streak", methods=["GET", "POST"])
@login_required
def admin_streak():
    from database import get_db
    conn = get_db()
    msg = ""
    if request.method == "POST":
        for key, val in request.form.items():
            if key.startswith("msg_"):
                rid = key.split("_")[1]
                conn.execute("UPDATE streak_messages SET message=? WHERE id=?", (val, rid))
        conn.commit()
        msg = '<div class="alert">✅ Saqlandi!</div>'
    rows = conn.execute("SELECT * FROM streak_messages ORDER BY range_start").fetchall()
    conn.close()
    rows_html = ""
    for r in rows:
        re_l = f"–{r['range_end']}" if r["range_end"] else "+"
        rows_html += f"""<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f2f8">
        <span style="background:#fff8ec;color:#7a4a00;border-radius:5px;padding:3px 9px;font-size:12px;white-space:nowrap;min-width:80px;text-align:center">{r["range_start"]}{re_l} kun</span>
        <input name="msg_{r["id"]}" value="{r["message"]}" style="flex:1;font-size:12px"></div>"""
    c = f"""<div class="title">Streak xabarlari</div>{msg}
    <div class="card"><div class="ch">Xabarlarni tahrirlash</div><div class="cb">
    <p style="font-size:12px;color:#7a8398;margin-bottom:12px">💡 <code>{{streak}}</code> — kun soni avtomatik qo'yiladi</p>
    <form method="POST">{rows_html}<button type="submit" class="btn btn-p" style="margin-top:16px">Saqlash</button></form>
    </div></div>"""
    return page(c, "streak")


@app.route("/admin/topics", methods=["GET", "POST"])
@login_required
def admin_topics():
    from database import get_db
    conn = get_db()
    msg = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "update":
            ids = request.form.getlist("id[]")
            titles = request.form.getlist("title[]")
            descs = request.form.getlist("desc[]")
            for i, tid in enumerate(ids):
                conn.execute("UPDATE topics SET title=?, description=?, ord=? WHERE id=?",
                            (titles[i], descs[i], i+1, tid))
            conn.commit()
            msg = '<div class="alert">✅ Saqlandi!</div>'
        elif action == "add":
            t = request.form.get("new_title", "")
            d = request.form.get("new_desc", "")
            if t:
                mo = conn.execute("SELECT MAX(ord) as m FROM topics").fetchone()["m"] or 0
                conn.execute("INSERT INTO topics (title, description, ord) VALUES (?,?,?)", (t, d, mo+1))
                conn.commit()
        elif action == "delete":
            conn.execute("DELETE FROM topics WHERE id=?", (request.form.get("del_id"),))
            conn.commit()
    rows = conn.execute("SELECT * FROM topics ORDER BY ord").fetchall()
    conn.close()
    rows_html = ""
    for r in rows:
        rows_html += f"""<tr><input type="hidden" name="id[]" value="{r["id"]}">
        <td style="color:#7a8398;width:30px">{r["ord"]}</td>
        <td><input name="title[]" value="{r["title"]}" style="font-size:12px"></td>
        <td><input name="desc[]" value="{r["description"] or ""}" style="font-size:12px"></td>
        <td><form method="POST"><input type="hidden" name="action" value="delete">
        <input type="hidden" name="del_id" value="{r["id"]}">
        <button type="submit" class="btn btn-r btn-s">O'ch</button></form></td></tr>"""
    c = f"""<div class="title">Mavzular</div>{msg}
    <div class="card"><div class="ch">Mavzular</div><div class="cb">
    <form method="POST"><input type="hidden" name="action" value="update">
    <table><thead><tr><th>#</th><th>Sarlavha</th><th>Tavsif</th><th></th></tr></thead>
    <tbody>{rows_html}</tbody></table>
    <button type="submit" class="btn btn-p" style="margin-top:14px">Saqlash</button></form>
    <hr style="margin:16px 0;border:none;border-top:1px solid #e8ecf6">
    <form method="POST"><input type="hidden" name="action" value="add">
    <div style="display:flex;gap:8px">
    <input name="new_title" placeholder="Mavzu nomi" style="flex:1">
    <input name="new_desc" placeholder="Tavsif" style="flex:1">
    <button type="submit" class="btn btn-p">Qo'shish</button></div></form>
    </div></div>"""
    return page(c, "topics")


@app.route("/admin/broadcast", methods=["GET", "POST"])
@login_required
def admin_broadcast():
    from database import get_users_by_target, get_db
    msg = ""
    if request.method == "POST":
        text = request.form.get("text", "")
        media_type = request.form.get("media_type", "")
        media_file_id = request.form.get("media_file_id", "")
        target = request.form.get("target", "all")
        import requests as req
        tids = get_users_by_target(target)
        base = f"https://api.telegram.org/bot{TOKEN}"
        for tid in tids:
            try:
                if media_type == "photo" and media_file_id:
                    req.post(f"{base}/sendPhoto", json={"chat_id": tid, "photo": media_file_id, "caption": text})
                elif media_type == "video" and media_file_id:
                    req.post(f"{base}/sendVideo", json={"chat_id": tid, "video": media_file_id, "caption": text})
                elif media_type == "audio" and media_file_id:
                    req.post(f"{base}/sendAudio", json={"chat_id": tid, "audio": media_file_id, "caption": text})
                elif media_type == "voice" and media_file_id:
                    req.post(f"{base}/sendVoice", json={"chat_id": tid, "voice": media_file_id, "caption": text})
                elif media_type == "document" and media_file_id:
                    req.post(f"{base}/sendDocument", json={"chat_id": tid, "document": media_file_id, "caption": text})
                elif text:
                    req.post(f"{base}/sendMessage", json={"chat_id": tid, "text": text, "parse_mode": "HTML"})
            except: pass
        msg = f'<div class="alert">✅ {len(tids)} ta userlarga yuborildi!</div>'

    targets = [("all","Hammaga"),("premium","Premiumga"),("trial","Sinov userlarga"),
               ("expired","Muddati tugaganlarga"),("inactive_3","3+ kun kelmayotganlarga"),
               ("inactive_5","5+ kun kelmayotganlarga"),("inactive_10","10+ kun kelmayotganlarga"),
               ("streak_5","Streak 5🔥"),("streak_10","Streak 10🔥"),("streak_20","Streak 20"),
               ("streak_30","Streak 30"),("streak_50","Streak 50"),("streak_60","Streak 60")]
    t_opts = "".join(f'<option value="{v}">{l}</option>' for v,l in targets)
    m_opts = "".join(f'<option value="{v}">{l}</option>' for v,l in
                     [("","Faqat matn"),("photo","🖼 Rasm"),("video","🎬 Video"),
                      ("audio","🎵 Audio"),("voice","🎤 Ovozli"),("document","📄 PDF")])
    c = f"""<div class="title">Xabar yuborish</div>{msg}
    <div class="card"><div class="ch">Yangi xabar</div><div class="cb">
    <form method="POST">
    <div class="fg"><label>Kimga?</label><select name="target">{t_opts}</select></div>
    <div class="fg"><label>Matn</label><textarea name="text" rows="4" placeholder="Xabar matni..."></textarea></div>
    <div class="two">
    <div class="fg"><label>Media turi</label><select name="media_type">{m_opts}</select></div>
    <div class="fg"><label>File ID</label><input name="media_file_id" placeholder="AgACBg..."></div>
    </div>
    <button type="submit" class="btn btn-p">Yuborish</button>
    </form></div></div>"""
    return page(c, "bc")


@app.route("/admin/settings", methods=["GET", "POST"])
@login_required
def admin_settings():
    from database import get_setting, set_setting
    msg = ""
    if request.method == "POST":
        sec = request.form.get("sec")
        if sec == "bot":
            for k in ["free_daily_limit","welcome_text","welcome_media_type","welcome_media_file_id",
                     "daily_text","daily_media_type","daily_media_file_id","daily_time","daily_target","trial_expired_text"]:
                set_setting(k, request.form.get(k, ""))
            set_setting("daily_enabled", "1" if request.form.get("daily_enabled") else "0")
            msg = '<div class="alert">✅ Saqlandi!</div>'
        elif sec == "admin":
            if request.form.get("new_pw"):
                set_setting("admin_password", request.form.get("new_pw"))
            set_setting("admin_login", request.form.get("admin_login", "admin"))
            msg = '<div class="alert">✅ Saqlandi!</div>'

    def gs(k): return get_setting(k) or ""
    mo = lambda cur: "".join(f'<option value="{v}" {"selected" if v==cur else ""}>{l}</option>'
                             for v,l in [("","Faqat matn"),("photo","🖼 Rasm"),("video","🎬 Video"),
                                        ("video_note","⭕ Dumaloq"),("audio","🎵 Audio"),("voice","🎤 Ovozli")])
    c = f"""<div class="title">Sozlamalar</div>{msg}
    <div class="two">
    <div class="card"><div class="ch">Bot sozlamalari</div><div class="cb">
    <form method="POST"><input type="hidden" name="sec" value="bot">
    <div class="fg"><label>Bepul kunlik limit</label><input type="number" name="free_daily_limit" value="{gs("free_daily_limit") or "3"}"></div>
    <div class="fg"><label>Salomlashuv matni</label><textarea name="welcome_text" rows="3">{gs("welcome_text")}</textarea></div>
    <div class="two"><div class="fg"><label>Media turi</label><select name="welcome_media_type">{mo(gs("welcome_media_type"))}</select></div>
    <div class="fg"><label>File ID</label><input name="welcome_media_file_id" value="{gs("welcome_media_file_id")}"></div></div>
    <div class="fg"><label>Kundalik xabar matni</label><textarea name="daily_text" rows="2">{gs("daily_text")}</textarea></div>
    <div class="two"><div class="fg"><label>Vaqt</label><input type="time" name="daily_time" value="{gs("daily_time") or "09:00"}"></div>
    <div class="fg"><label>Yoqilgan</label><br><input type="checkbox" name="daily_enabled" value="1" {"checked" if gs("daily_enabled")=="1" else ""} style="width:auto;margin-top:8px"></div></div>
    <div class="fg"><label>Sinov tugaganda xabar</label><input name="trial_expired_text" value="{gs("trial_expired_text")}"></div>
    <button type="submit" class="btn btn-p">Saqlash</button></form></div></div>
    <div class="card"><div class="ch">Admin kirish</div><div class="cb">
    <form method="POST"><input type="hidden" name="sec" value="admin">
    <div class="fg"><label>Login</label><input name="admin_login" value="{gs("admin_login") or "admin"}"></div>
    <div class="fg"><label>Yangi parol</label><input type="password" name="new_pw"></div>
    <button type="submit" class="btn btn-p">Saqlash</button></form></div></div></div>"""
    return page(c, "sett")


@app.route("/admin/lid")
@login_required
def admin_lid():
    from database import get_lid_stats
    total, links = get_lid_stats("lid")
    rows_html = ""
    for l in links:
        conv = round(l["lids"]/l["clicks"]*100,1) if l["clicks"] else 0
        rows_html += f"""<tr><td><code>?start={l["source"]}</code></td><td>{l["name"] or "—"}</td>
        <td>{l["clicks"]}</td><td style="color:#1baf7a;font-weight:600">{l["lids"]} ({conv}%)</td></tr>"""
    c = f"""<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <div class="title" style="margin:0">📨 Lid Magnit Bot</div>
    <a href="/admin/lid/links" class="btn btn-p">+ Yangi link</a></div>
    <div class="kpis"><div class="kpi"><div class="n">{total}</div><div class="l">Jami lidlar</div></div>
    <div class="kpi"><div class="n" style="color:#1f54e0">{len(links)}</div><div class="l">Linklar</div></div></div>
    <div class="card"><div class="ch">Tracking linklar</div>
    <div class="cb" style="padding:0"><table>
    <thead><tr><th>Link</th><th>Nomi</th><th>Bosildi</th><th>Lid</th></tr></thead>
    <tbody>{rows_html or "<tr><td colspan='4' style='text-align:center;padding:16px;color:#7a8398'>Hali link yo'q</td></tr>"}</tbody>
    </table></div></div>"""
    return page(c, "lid")


@app.route("/admin/lid/links", methods=["GET", "POST"])
@login_required
def admin_lid_links():
    from database import set_setting_for_bot, get_db
    msg = ""
    if request.method == "POST":
        source = request.form.get("source","").strip().replace(" ","_")
        name = request.form.get("name","")
        set_setting_for_bot("lid", f"link_{source}_text", request.form.get("text",""))
        set_setting_for_bot("lid", f"link_{source}_media_type", request.form.get("media_type",""))
        set_setting_for_bot("lid", f"link_{source}_media_id", request.form.get("media_file_id",""))
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO lid_links (source, name) VALUES (?,?)", (source, name))
        conn.commit()
        conn.close()
        msg = f'<div class="alert">✅ Link yaratildi: t.me/bot?start={source}</div>'
    mo = "".join(f'<option value="{v}">{l}</option>' for v,l in
                 [("","Faqat matn"),("photo","🖼 Rasm"),("video","🎬 Video"),
                  ("video_note","⭕ Dumaloq"),("audio","🎵 Audio"),("voice","🎤 Ovozli"),("document","📄 PDF")])
    c = f"""<div class="title">Yangi tracking link</div>{msg}
    <div class="card"><div class="cb"><form method="POST">
    <div class="two"><div class="fg"><label>Link ID (lotin, _ bilan)</label><input name="source" placeholder="instagram_post1" required></div>
    <div class="fg"><label>Nomi</label><input name="name" placeholder="Instagram post #1"></div></div>
    <div class="fg"><label>Xabar matni</label><textarea name="text" rows="3"></textarea></div>
    <div class="two"><div class="fg"><label>Media turi</label><select name="media_type">{mo}</select></div>
    <div class="fg"><label>File ID</label><input name="media_file_id" placeholder="AgACBg..."></div></div>
    <button type="submit" class="btn btn-p">Saqlash</button></form></div></div>"""
    return page(c, "lid_links")


@app.route("/admin/lid/settings", methods=["GET", "POST"])
@login_required
def admin_lid_settings():
    from database import set_setting_for_bot, get_setting_for_bot
    msg = ""
    if request.method == "POST":
        for k in ["welcome_text","welcome_media_type","welcome_media_file_id","auto_reply_text"]:
            set_setting_for_bot("lid", k, request.form.get(k,""))
        msg = '<div class="alert">✅ Saqlandi!</div>'
    def gs(k): return get_setting_for_bot("lid", k) or ""
    mo = lambda cur: "".join(f'<option value="{v}" {"selected" if v==cur else ""}>{l}</option>'
                             for v,l in [("","Faqat matn"),("photo","🖼 Rasm"),("video","🎬 Video"),
                                        ("document","📄 PDF"),("audio","🎵 Audio"),("voice","🎤 Ovozli")])
    c = f"""<div class="title">Lid Magnit — Sozlamalar</div>{msg}
    <div class="card"><div class="cb"><form method="POST">
    <div class="fg"><label>Salomlashuv matni (/start)</label>
    <textarea name="welcome_text" rows="3">{gs("welcome_text") or "Assalomu alaykum! 👋\nZamira Turganbayeva botiga yozdingiz."}</textarea></div>
    <div class="two"><div class="fg"><label>Media turi</label><select name="welcome_media_type">{mo(gs("welcome_media_type"))}</select></div>
    <div class="fg"><label>File ID</label><input name="welcome_media_file_id" value="{gs("welcome_media_file_id")}"></div></div>
    <div class="fg"><label>Avtomatik javob (user xabar yozganda)</label>
    <input name="auto_reply_text" value="{gs("auto_reply_text")}" placeholder="Xabaringiz qabul qilindi ⏰"></div>
    <button type="submit" class="btn btn-p">Saqlash</button></form></div></div>"""
    return page(c, "lid_sett")


# ========== START ==========
if __name__ == "__main__":
    from database import init_db, init_lid_tables
    init_db()
    init_lid_tables()
    threading.Thread(target=setup_webhooks, daemon=True).start()
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error(f"Scheduler: {e}")
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Flask {port} portda ishga tushmoqda...")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
