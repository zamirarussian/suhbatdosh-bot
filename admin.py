import os
import requests as req
from functools import wraps
from datetime import date, timedelta
from flask import Flask, request, redirect, session, render_template_string, jsonify, send_from_directory
from database import db, gs, ss, get_users_for_broadcast, get_user, set_daily_limit, effective_daily_limit

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "zamira2024")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")


def lr(f):
    @wraps(f)
    def d(*a, **kw):
        if not session.get("ok"): return redirect("/admin/login")
        return f(*a, **kw)
    return d


S = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Zamira Admin</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@2.44.0/tabler-icons.min.css">
<style>
*{box-sizing:border-box;margin:0;padding:0}body{font-family:system-ui,sans-serif;background:#f5f7fb;font-size:14px}
.lay{display:flex;min-height:100vh}.sb{width:220px;background:#fff;border-right:1px solid #e8ecf6;padding:20px 0;position:fixed;top:0;left:0;bottom:0}
.lg{padding:0 20px 16px;border-bottom:1px solid #e8ecf6;margin-bottom:12px;font-weight:700;font-size:15px;color:#1f54e0}
a.n{display:flex;align-items:center;gap:10px;padding:9px 20px;font-size:13px;color:#5a6070;text-decoration:none}
a.n:hover{background:#f0f4ff;color:#1f54e0}a.n.on{background:#e8f0ff;color:#1f54e0;font-weight:500}a.n i{font-size:17px}
.mn{margin-left:220px;padding:24px}.tt{font-size:20px;font-weight:700;margin-bottom:20px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:24px}
.kpi{background:#fff;border-radius:10px;padding:16px;border:1px solid #e8ecf6}
.kpi .n{font-size:26px;font-weight:700}.kpi .l{font-size:12px;color:#7a8398}
.card{background:#fff;border-radius:10px;border:1px solid #e8ecf6;margin-bottom:20px}
.ch{padding:14px 18px;border-bottom:1px solid #e8ecf6;font-weight:600;font-size:14px;display:flex;justify-content:space-between;align-items:center}
.cb{padding:18px}table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:12px;color:#7a8398;font-weight:500;padding:0 12px 10px;border-bottom:1px solid #e8ecf6}
td{padding:10px 12px;border-bottom:1px solid #f0f2f8;font-size:13px;vertical-align:middle}
input,select,textarea{width:100%;padding:8px 10px;border:1px solid #e0e4ef;border-radius:7px;font-size:13px;font-family:inherit;background:#fff}
.btn{padding:8px 16px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;border:none;font-family:inherit;text-decoration:none;display:inline-block}
.bp{background:#1f54e0;color:#fff}.bo{background:#fff;border:1px solid #e0e4ef;color:#5a6070}.bs{padding:4px 10px;font-size:12px}
.fg{margin-bottom:14px}.fg label{display:block;font-size:12px;font-weight:500;color:#5a6070;margin-bottom:5px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.al{padding:10px 14px;border-radius:7px;font-size:13px;margin-bottom:14px;background:#e4f5e0;color:#1a6020}
.sbp{background:#deeaff;color:#1f54e0;border-radius:5px;padding:3px 8px;font-size:11px;font-weight:500}
.sbt{background:#fff8ec;color:#7a4a00;border-radius:5px;padding:3px 8px;font-size:11px}
.sbe{background:#f0f2f8;color:#7a8398;border-radius:5px;padding:3px 8px;font-size:11px}
.sbb{background:#fde8ea;color:#c42b3a;border-radius:5px;padding:3px 8px;font-size:11px}
</style></head><body><div class="lay">
<div class="sb"><div class="lg">🤖 Zamira Admin</div>
<a href="/admin" class="n {%dash%}"><i class="ti ti-chart-bar"></i> Dashboard</a>
<a href="/admin/users" class="n {%users%}"><i class="ti ti-users"></i> Foydalanuvchilar</a>
<a href="/admin/streak" class="n {%streak%}"><i class="ti ti-flame"></i> Streak xabarlari</a>
<a href="/admin/topics" class="n {%topics%}"><i class="ti ti-books"></i> Mavzular</a>
<a href="/admin/broadcast" class="n {%bc%}"><i class="ti ti-speakerphone"></i> Xabar yuborish</a>
<a href="/admin/settings" class="n {%sett%}"><i class="ti ti-settings"></i> Sozlamalar</a>
<a href="/admin/logout" class="n" style="color:#e42a3b;margin-top:20px"><i class="ti ti-logout"></i> Chiqish</a>
</div><div class="mn">{{CONTENT}}</div></div></body></html>"""


def pg(content, active=""):
    h = S.replace("{{CONTENT}}", content)
    for k in ["dash","users","streak","topics","bc","sett"]:
        h = h.replace("{%"+k+"%}", "on" if k==active else "")
    return h


def tg(path, **kw):
    try: req.post(f"https://api.telegram.org/bot{TOKEN}/{path}", json=kw, timeout=10)
    except: pass


@app.route("/status")
def status():
    return jsonify({"ok": True})


@app.route("/miniapp.html")
def miniapp():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "miniapp.html")


@app.route("/admin/login", methods=["GET","POST"])
def login():
    err = ""
    if request.method == "POST":
        if request.form.get("login")==(gs("admin_login") or "admin") and \
           request.form.get("password")==(gs("admin_password") or "zamira2024"):
            session["ok"] = True; return redirect("/admin")
        err = "<p style='color:red;margin-bottom:10px'>Noto'g'ri</p>"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title>
    <style>*{{box-sizing:border-box}}body{{font-family:system-ui;background:#f0f4ff;display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .c{{background:#fff;border-radius:14px;padding:36px 32px;width:340px;border:1px solid #e8ecf6}}
    h2{{font-size:18px;font-weight:700;margin-bottom:20px;text-align:center;color:#1a1a2e}}
    label{{font-size:12px;color:#5a6070;display:block;margin-bottom:4px}}
    input{{width:100%;padding:9px 12px;border:1px solid #e0e4ef;border-radius:8px;font-size:13px;margin-bottom:14px}}
    button{{width:100%;padding:10px;background:#1f54e0;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}}
    </style></head><body><div class="c"><h2>🤖 Zamira Admin</h2>{err}
    <form method="POST"><label>Login</label><input name="login"><label>Parol</label>
    <input type="password" name="password"><button>Kirish</button></form></div></body></html>"""


@app.route("/admin/logout")
def logout():
    session.clear(); return redirect("/admin/login")


@app.route("/admin")
@lr
def dashboard():
    c = db()
    total = c.execute("SELECT COUNT(*) as n FROM users").fetchone()["n"]
    premium = c.execute("SELECT COUNT(*) as n FROM users WHERE status='premium'").fetchone()["n"]
    trial = c.execute("SELECT COUNT(*) as n FROM users WHERE status='trial'").fetchone()["n"]
    expired = c.execute("SELECT COUNT(*) as n FROM users WHERE status='expired'").fetchone()["n"]
    today = str(date.today())
    active = c.execute("SELECT COUNT(*) as n FROM users WHERE last_active=?", (today,)).fetchone()["n"]
    msgs = c.execute("SELECT SUM(msg_today) as s FROM users WHERE msg_date=?", (today,)).fetchone()["s"] or 0
    c.close()
    content = f"""<div class="tt">Dashboard</div>
    <div class="kpis">
    <div class="kpi"><div class="n">{total}</div><div class="l">Jami userlar</div></div>
    <div class="kpi"><div class="n" style="color:#1f54e0">{active}</div><div class="l">Bugun faol</div></div>
    <div class="kpi"><div class="n">{msgs}</div><div class="l">Bugun xabarlar</div></div>
    <div class="kpi"><div class="n" style="color:#1baf7a">{premium}</div><div class="l">Premium</div></div>
    <div class="kpi"><div class="n" style="color:#7a4a00">{trial}</div><div class="l">Sinov</div></div>
    <div class="kpi"><div class="n" style="color:#e42a3b">{expired}</div><div class="l">Tugagan</div></div>
    </div>"""
    return pg(content, "dash")


@app.route("/admin/users", methods=["GET","POST"])
@lr
def users():
    c = db()
    msg = ""
    if request.method == "POST":
        tid = int(request.form.get("tid",0))
        action = request.form.get("action","")
        today = str(date.today())
        if action == "premium":
            c.execute("UPDATE users SET status='premium' WHERE telegram_id=?", (tid,))
        elif action == "trial":
            c.execute("UPDATE users SET status='trial', trial_start=?, trial_days=3 WHERE telegram_id=?", (today, tid))
        elif action == "extend":
            u = c.execute("SELECT trial_days FROM users WHERE telegram_id=?", (tid,)).fetchone()
            days = (u["trial_days"] or 3) + 3
            c.execute("UPDATE users SET status='trial', trial_start=?, trial_days=? WHERE telegram_id=?", (today, days, tid))
        elif action == "blocked":
            c.execute("UPDATE users SET status='blocked' WHERE telegram_id=?", (tid,))
        elif action == "unblock":
            c.execute("UPDATE users SET status='trial', trial_start=? WHERE telegram_id=?", (today, tid))
        elif action == "setlimit":
            raw = (request.form.get("limit_val","") or "").strip().lower()
            if raw in ("", "standart", "default", "-"):
                c.execute("UPDATE users SET daily_limit=NULL WHERE telegram_id=?", (tid,))
                msg = '<div class="al">✅ Standart limitga qaytarildi</div>'
            elif raw in ("cheksiz", "unlimited", "0", "inf", "∞"):
                c.execute("UPDATE users SET daily_limit=0 WHERE telegram_id=?", (tid,))
                msg = '<div class="al">✅ Bu userga cheksiz xabar ruxsat etildi</div>'
            else:
                try:
                    n = max(1, int(raw))
                    c.execute("UPDATE users SET daily_limit=? WHERE telegram_id=?", (n, tid))
                    msg = f'<div class="al">✅ Bu userga kunlik limit: {n} ta xabar</div>'
                except ValueError:
                    msg = '<div class="al" style="background:#fde8ea;color:#c42b3a">⚠️ Noto\'g\'ri qiymat</div>'
        c.commit()
        if not msg:
            msg = '<div class="al">✅ Bajarildi</div>'

    q = request.args.get("q","")
    sf = request.args.get("s","all")
    sql = "SELECT * FROM users WHERE 1=1"
    params = []
    if q:
        sql += " AND (name LIKE ? OR CAST(telegram_id AS TEXT) LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if sf != "all":
        sql += " AND status=?"
        params.append(sf)
    sql += " ORDER BY created_at DESC LIMIT 100"
    rows = c.execute(sql, params).fetchall()
    c.close()

    today = str(date.today())
    rh = ""
    for r in rows:
        bm = {"premium":"sbp","trial":"sbt","expired":"sbe","blocked":"sbb"}
        bc = bm.get(r["status"],"sbe")
        sl = {"premium":"Premium","trial":"Sinov","expired":"Tugagan","blocked":"Bloklangan"}.get(r["status"],r["status"])
        m = r["msg_today"] if r["msg_date"]==today else 0
        eff_lim = effective_daily_limit(r)
        lim_disp = "∞" if eff_lim is None else str(eff_lim)
        is_custom = r["daily_limit"] is not None
        lim_badge = f' <span style="color:#1f54e0;font-size:10px">(maxsus)</span>' if is_custom else ""
        opts = ""
        if r["status"]=="premium": opts='<option value="trial">Sinovga</option><option value="blocked">Bloklash</option>'
        elif r["status"] in ("trial","expired"): opts='<option value="premium">✅ Premium</option><option value="extend">🔄 +3 kun</option><option value="blocked">🚫 Bloklash</option>'
        elif r["status"]=="blocked": opts='<option value="unblock">🔓 Ochish</option><option value="premium">✅ Premium</option>'
        rh += f"""<tr><td>{r["name"] or "—"}</td><td style="color:#7a8398">{r["telegram_id"]}</td>
        <td>{"🔥"+str(r["streak"]) if r["streak"] else "—"}</td><td>{m}/{lim_disp}{lim_badge}</td><td>{r["last_active"] or "—"}</td>
        <td><span class="{bc}">{sl}</span></td>
        <td><div style="display:flex;flex-direction:column;gap:4px">
        <form method="POST" style="display:flex;gap:4px"><input type="hidden" name="tid" value="{r["telegram_id"]}">
        <select name="action" style="width:auto;font-size:11px;padding:2px 5px"><option value="">Amal...</option>{opts}</select>
        <button type="submit" class="btn bo bs">OK</button></form>
        <form method="POST" style="display:flex;gap:4px"><input type="hidden" name="tid" value="{r["telegram_id"]}">
        <input type="hidden" name="action" value="setlimit">
        <input name="limit_val" placeholder="son/cheksiz/standart" style="width:auto;font-size:11px;padding:2px 5px;max-width:120px">
        <button type="submit" class="btn bo bs">Limit</button></form>
        </div></td></tr>"""

    filt = "".join(f'<option value="{v}" {"selected" if sf==v else ""}>{l}</option>'
                   for v,l in [("all","Hammasi"),("premium","Premium"),("trial","Sinov"),("expired","Tugagan"),("blocked","Bloklangan")])
    content = f"""<div class="tt">Foydalanuvchilar</div>{msg}
    <div class="card"><div class="ch">
    <form method="GET" style="display:flex;gap:8px;align-items:center">
    <input name="q" value="{q}" placeholder="Ism yoki ID..." style="max-width:180px">
    <select name="s" style="width:auto">{filt}</select>
    <button class="btn bo bs" type="submit">Qidirish</button></form></div>
    <div class="cb" style="padding:0"><table>
    <thead><tr><th>Ism</th><th>ID</th><th>Streak</th><th>Bugun</th><th>Oxirgi</th><th>Status</th><th>Amal</th></tr></thead>
    <tbody>{rh}</tbody></table></div></div>

    <div class="card"><div class="ch">Tez dostup berish</div><div class="cb">
    <form method="POST" style="display:flex;gap:8px;align-items:flex-end">
    <div class="fg" style="flex:1;margin:0"><label>Telegram ID</label><input name="tid" placeholder="12345678"></div>
    <div class="fg" style="width:200px;margin:0"><label>Tur</label>
    <select name="action"><option value="premium">Premium — cheksiz</option><option value="trial">Sinov — 3 kun</option></select></div>
    <button type="submit" class="btn bp">Berish</button></form></div></div>"""
    return pg(content, "users")


@app.route("/admin/streak", methods=["GET","POST"])
@lr
def streak():
    c = db()
    msg = ""
    if request.method == "POST":
        for k,v in request.form.items():
            if k.startswith("m_"):
                c.execute("UPDATE streak_msgs SET message=? WHERE id=?", (v, k[2:]))
        c.commit(); msg = '<div class="al">✅ Saqlandi!</div>'
    rows = c.execute("SELECT * FROM streak_msgs ORDER BY range_start").fetchall()
    c.close()
    rh = ""
    for r in rows:
        rl = f"–{r['range_end']}" if r["range_end"] else "+"
        rh += f"""<div style="display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid #f0f2f8">
        <span style="background:#fff8ec;color:#7a4a00;border-radius:5px;padding:3px 9px;font-size:11px;min-width:80px;text-align:center">{r["range_start"]}{rl} kun</span>
        <input name="m_{r['id']}" value="{r['message']}" style="flex:1;font-size:12px"></div>"""
    content = f"""<div class="tt">Streak xabarlari</div>{msg}
    <div class="card"><div class="ch">Xabarlarni tahrirlash</div><div class="cb">
    <p style="font-size:12px;color:#7a8398;margin-bottom:12px">💡 <code>{{streak}}</code> — kun soni avtomatik qo'yiladi</p>
    <form method="POST">{rh}<button type="submit" class="btn bp" style="margin-top:16px">Saqlash</button></form>
    </div></div>"""
    return pg(content, "streak")


@app.route("/admin/topics", methods=["GET","POST"])
@lr
def topics():
    c = db()
    msg = ""
    if request.method == "POST":
        act = request.form.get("action")
        if act == "update":
            for i,(tid,t,d) in enumerate(zip(request.form.getlist("id[]"),
                                              request.form.getlist("t[]"),
                                              request.form.getlist("d[]"))):
                c.execute("UPDATE topics SET title=?,description=?,ord=? WHERE id=?", (t,d,i+1,tid))
            c.commit(); msg = '<div class="al">✅ Saqlandi!</div>'
        elif act == "add":
            t = request.form.get("nt","")
            d = request.form.get("nd","")
            if t:
                mo = c.execute("SELECT MAX(ord) as m FROM topics").fetchone()["m"] or 0
                c.execute("INSERT INTO topics (title,description,ord) VALUES (?,?,?)", (t,d,mo+1))
                c.commit()
        elif act == "del":
            c.execute("DELETE FROM topics WHERE id=?", (request.form.get("did"),)); c.commit()
    rows = c.execute("SELECT * FROM topics ORDER BY ord").fetchall()
    c.close()
    rh = ""
    for r in rows:
        rh += f"""<tr><input type="hidden" name="id[]" value="{r['id']}">
        <td style="color:#7a8398;width:30px">{r['ord']}</td>
        <td><input name="t[]" value="{r['title']}" style="font-size:12px"></td>
        <td><input name="d[]" value="{r['description'] or ''}" style="font-size:12px"></td>
        <td><form method="POST"><input type="hidden" name="action" value="del"><input type="hidden" name="did" value="{r['id']}">
        <button type="submit" class="btn bs" style="background:#e42a3b;color:#fff">O'ch</button></form></td></tr>"""
    content = f"""<div class="tt">Mavzular</div>{msg}
    <div class="card"><div class="ch">Mavzular</div><div class="cb">
    <form method="POST"><input type="hidden" name="action" value="update">
    <table><thead><tr><th>#</th><th>Sarlavha</th><th>Tavsif</th><th></th></tr></thead><tbody>{rh}</tbody></table>
    <button type="submit" class="btn bp" style="margin-top:14px">Saqlash</button></form>
    <hr style="margin:16px 0;border:none;border-top:1px solid #e8ecf6">
    <form method="POST"><input type="hidden" name="action" value="add">
    <div style="display:flex;gap:8px"><input name="nt" placeholder="Mavzu nomi" style="flex:1">
    <input name="nd" placeholder="Tavsif" style="flex:1">
    <button type="submit" class="btn bp">Qo'shish</button></div></form>
    </div></div>"""
    return pg(content, "topics")


@app.route("/admin/broadcast", methods=["GET","POST"])
@lr
def broadcast():
    msg = ""
    if request.method == "POST":
        text = request.form.get("text","")
        mt = request.form.get("media_type","")
        mid = request.form.get("media_file_id","")
        target = request.form.get("target","all")
        tids = get_users_for_broadcast(target)
        base = f"https://api.telegram.org/bot{TOKEN}"
        for tid in tids:
            try:
                if mt=="photo" and mid: req.post(f"{base}/sendPhoto", json={"chat_id":tid,"photo":mid,"caption":text}, timeout=5)
                elif mt=="video" and mid: req.post(f"{base}/sendVideo", json={"chat_id":tid,"video":mid,"caption":text}, timeout=5)
                elif mt=="audio" and mid: req.post(f"{base}/sendAudio", json={"chat_id":tid,"audio":mid,"caption":text}, timeout=5)
                elif mt=="voice" and mid: req.post(f"{base}/sendVoice", json={"chat_id":tid,"voice":mid,"caption":text}, timeout=5)
                elif mt=="document" and mid: req.post(f"{base}/sendDocument", json={"chat_id":tid,"document":mid,"caption":text}, timeout=5)
                elif text: req.post(f"{base}/sendMessage", json={"chat_id":tid,"text":text,"parse_mode":"HTML"}, timeout=5)
            except: pass
        msg = f'<div class="al">✅ {len(tids)} ta userlarga yuborildi!</div>'

    topts = "".join(f'<option value="{v}">{l}</option>' for v,l in [
        ("all","Hammaga"),("premium","Premiumga"),("trial","Sinov userlarga"),
        ("expired","Muddati tugaganlarga"),("inactive_3","3+ kun kelmayotganlarga"),
        ("inactive_5","5+ kun kelmayotganlarga"),("inactive_10","10+ kun kelmayotganlarga"),
        ("streak_5","Streak 5🔥"),("streak_10","Streak 10🔥"),("streak_20","Streak 20"),
        ("streak_30","Streak 30"),("streak_50","Streak 50"),("streak_60","Streak 60")])
    mopts = "".join(f'<option value="{v}">{l}</option>' for v,l in [
        ("","Faqat matn"),("photo","🖼 Rasm"),("video","🎬 Video"),
        ("audio","🎵 Audio"),("voice","🎤 Ovozli"),("document","📄 PDF")])
    content = f"""<div class="tt">Xabar yuborish</div>{msg}
    <div class="card"><div class="ch">Yangi xabar</div><div class="cb"><form method="POST">
    <div class="fg"><label>Kimga?</label><select name="target">{topts}</select></div>
    <div class="fg"><label>Matn</label><textarea name="text" rows="4" placeholder="Xabar matni..."></textarea></div>
    <div class="two"><div class="fg"><label>Media turi</label><select name="media_type">{mopts}</select></div>
    <div class="fg"><label>File ID (ixtiyoriy)</label><input name="media_file_id" placeholder="AgACBg..."></div></div>
    <button type="submit" class="btn bp">Yuborish</button></form></div></div>"""
    return pg(content, "bc")


@app.route("/admin/settings", methods=["GET","POST"])
@lr
def settings():
    msg = ""
    if request.method == "POST":
        sec = request.form.get("sec")
        if sec == "bot":
            for k in ["free_limit","exam_questions","daily_start_text","welcome_text","welcome_media_type","welcome_media_file_id",
                      "daily_text","daily_media_type","daily_media_file_id","daily_time",
                      "daily_target","trial_expired_text"]:
                ss(k, request.form.get(k,""))
            ss("daily_enabled", "1" if request.form.get("daily_enabled") else "0")
            msg = '<div class="al">✅ Saqlandi!</div>'
        elif sec == "admin":
            if request.form.get("pw"): ss("admin_password", request.form.get("pw"))
            ss("admin_login", request.form.get("login","admin"))
            msg = '<div class="al">✅ Admin ma\'lumotlari yangilandi!</div>'

    def g(k): return gs(k) or ""
    mo = lambda cur: "".join(f'<option value="{v}" {"selected" if v==cur else ""}>{l}</option>'
                             for v,l in [("","Faqat matn"),("photo","🖼 Rasm"),("video","🎬 Video"),
                                        ("video_note","⭕ Dumaloq"),("audio","🎵 Audio"),("voice","🎤 Ovozli")])
    to = lambda cur: "".join(f'<option value="{v}" {"selected" if v==cur else ""}>{l}</option>'
                             for v,l in [("all","Hammaga"),("trial","Sinov userlarga"),("premium","Premiumga")])
    content = f"""<div class="tt">Sozlamalar</div>{msg}
    <div class="two">
    <div class="card"><div class="ch">Bot sozlamalari</div><div class="cb"><form method="POST">
    <input type="hidden" name="sec" value="bot">
    <div class="fg"><label>Bepul kunlik limit</label><input type="number" name="free_limit" value="{g('free_limit') or '3'}"></div>
    <div class="fg"><label>🎓 Imtihon — hafta oxirida nechta savol beriladi</label><input type="number" min="1" name="exam_questions" value="{g('exam_questions') or '5'}"></div>
    <div class="fg"><label>📚 Kunlik dars — boshlash xabari (ilovadan kirganda). <code>{{topic}}</code> — kun mavzusi avtomatik qo'yiladi</label>
    <textarea name="daily_start_text" rows="2">{g('daily_start_text') or "Salom! Bugun «{topic}» mavzusida gaplashamiz. Tayyormisiz?"}</textarea></div>
    <div class="fg"><label>Salomlashuv matni</label><textarea name="welcome_text" rows="3">{g('welcome_text')}</textarea></div>
    <div class="two"><div class="fg"><label>Media turi</label><select name="welcome_media_type">{mo(g('welcome_media_type'))}</select></div>
    <div class="fg"><label>File ID</label><input name="welcome_media_file_id" value="{g('welcome_media_file_id')}"></div></div>
    <div class="fg"><label>Kundalik xabar</label><textarea name="daily_text" rows="2">{g('daily_text')}</textarea></div>
    <div class="two"><div class="fg"><label>Media turi</label><select name="daily_media_type">{mo(g('daily_media_type'))}</select></div>
    <div class="fg"><label>File ID</label><input name="daily_media_file_id" value="{g('daily_media_file_id')}"></div></div>
    <div class="two">
    <div class="fg"><label>Vaqt</label><input type="time" name="daily_time" value="{g('daily_time') or '09:00'}"></div>
    <div class="fg"><label>Kimga</label><select name="daily_target">{to(g('daily_target'))}</select></div></div>
    <div class="fg"><label style="display:flex;align-items:center;gap:8px">
    <input type="checkbox" name="daily_enabled" value="1" {'checked' if g('daily_enabled')=='1' else ''} style="width:auto">
    Kundalik xabar yoqilgan</label></div>
    <div class="fg"><label>Sinov tugaganda xabar</label><input name="trial_expired_text" value="{g('trial_expired_text')}"></div>
    <button type="submit" class="btn bp">Saqlash</button></form></div></div>
    <div class="card"><div class="ch">Admin kirish</div><div class="cb"><form method="POST">
    <input type="hidden" name="sec" value="admin">
    <div class="fg"><label>Login</label><input name="login" value="{g('admin_login') or 'admin'}"></div>
    <div class="fg"><label>Yangi parol</label><input type="password" name="pw" placeholder="••••••••"></div>
    <button type="submit" class="btn bp">Saqlash</button></form></div></div></div>"""
    return pg(content, "sett")


# API for miniapp
@app.route("/api/profile")
def api_profile():
    tid = request.args.get("telegram_id")
    if not tid: return jsonify({"error":"no id"}), 400
    from database import get_user
    u = get_user(int(tid))
    if not u: return jsonify({"error":"not found"}), 404
    return jsonify({"name":u["name"],"streak":u["streak"],"status":u["status"],"last_active":u["last_active"]})


@app.route("/api/topics")
def api_topics():
    from database import get_topics
    return jsonify(get_topics())
