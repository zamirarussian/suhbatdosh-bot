"""
Bitta fayl — Flask + Webhook. Polling yo'q.
"""
import os
import logging
import asyncio
from flask import Flask, request, jsonify, session, redirect, url_for, render_template_string, send_from_directory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "zamira2024")

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
LID_TOKEN = os.environ.get("LID_BOT_TOKEN", "")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# ========== BOT APPS ==========
_apps = {}

def get_app(token, bot_module_name):
    if token not in _apps:
        from telegram.ext import Application
        tg_app = Application.builder().token(token).build()

        if bot_module_name == "main":
            import bot as b
            from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, filters
            tg_app.add_handler(CommandHandler("start", b.start))
            tg_app.add_handler(CommandHandler("reset", b.reset))
            tg_app.add_handler(CommandHandler("end", b.end_command))
            tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, b.handle_message))
            tg_app.add_handler(MessageHandler(filters.VOICE, b.handle_voice_msg))
            tg_app.add_handler(CallbackQueryHandler(b.handle_callback))
        elif bot_module_name == "lid":
            import lid_bot as lb
            from telegram.ext import CommandHandler, MessageHandler, filters
            tg_app.add_handler(CommandHandler("start", lb.start))
            tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lb.handle_message))
            tg_app.add_handler(MessageHandler(
                filters.PHOTO | filters.VIDEO | filters.AUDIO |
                filters.VOICE | filters.Document.ALL | filters.VIDEO_NOTE,
                lb.handle_media_message
            ))

        loop = asyncio.new_event_loop()
        loop.run_until_complete(tg_app.initialize())
        _apps[token] = (tg_app, loop)
        logger.info(f"{bot_module_name} bot tayyor")

    return _apps[token]


# ========== WEBHOOK ROUTES ==========

@app.route("/webhook/main", methods=["POST"])
def wh_main():
    if not TOKEN:
        return jsonify({"ok": False})
    try:
        from telegram import Update
        tg_app, loop = get_app(TOKEN, "main")
        update = Update.de_json(request.get_json(force=True), tg_app.bot)
        loop.run_until_complete(tg_app.process_update(update))
    except Exception as e:
        logger.error(f"wh_main: {e}")
    return jsonify({"ok": True})


@app.route("/webhook/lid", methods=["POST"])
def wh_lid():
    if not LID_TOKEN:
        return jsonify({"ok": False})
    try:
        from telegram import Update
        tg_app, loop = get_app(LID_TOKEN, "lid")
        update = Update.de_json(request.get_json(force=True), tg_app.bot)
        loop.run_until_complete(tg_app.process_update(update))
    except Exception as e:
        logger.error(f"wh_lid: {e}")
    return jsonify({"ok": True})


@app.route("/webhook/setup")
def wh_setup():
    import requests
    results = {}
    if TOKEN and WEBHOOK_URL:
        r = requests.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            json={"url": f"{WEBHOOK_URL}/webhook/main", "drop_pending_updates": True}
        )
        results["main"] = r.json()
    if LID_TOKEN and WEBHOOK_URL:
        r = requests.post(
            f"https://api.telegram.org/bot{LID_TOKEN}/setWebhook",
            json={"url": f"{WEBHOOK_URL}/webhook/lid", "drop_pending_updates": True}
        )
        results["lid"] = r.json()
    return jsonify(results)


@app.route("/status")
def status():
    return jsonify({"status": "ok", "webhook_url": WEBHOOK_URL})


@app.route("/miniapp.html")
def miniapp():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(base_dir, "miniapp.html")


# ========== ADMIN LOGIN ==========

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated


LOGIN_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui;background:#f0f4ff;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border-radius:14px;padding:36px 32px;width:340px;border:1px solid #e8ecf6;box-shadow:0 4px 20px rgba(0,0,0,.06)}
h2{font-size:18px;font-weight:700;margin-bottom:20px;text-align:center;color:#1a1a2e}
label{font-size:12px;color:#5a6070;display:block;margin-bottom:4px}
input{width:100%;padding:9px 12px;border:1px solid #e0e4ef;border-radius:8px;font-size:13px;margin-bottom:14px}
button{width:100%;padding:10px;background:#1f54e0;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}
.err{color:#e42a3b;font-size:12px;margin-bottom:10px}
</style></head><body>
<div class="card">
<h2>🤖 Zamira Admin</h2>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<form method="POST">
<label>Login</label><input name="login" required>
<label>Parol</label><input type="password" name="password" required>
<button>Kirish</button>
</form>
</div>
</body></html>
"""


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    from database import get_setting
    error = None
    if request.method == "POST":
        lg = request.form.get("login")
        pw = request.form.get("password")
        if lg == (get_setting("admin_login") or "admin") and pw == (get_setting("admin_password") or "zamira2024"):
            session["logged_in"] = True
            return redirect("/admin")
        error = "Login yoki parol noto'g'ri"
    return render_template_string(LOGIN_HTML, error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect("/admin/login")


# ========== ADMIN ROUTES ==========
# admin_routes.py dan import qilamiz

def init_admin_routes():
    try:
        from admin_routes import register_admin_routes
        register_admin_routes(app)
        logger.info("Admin routelar ulandi")
    except Exception as e:
        logger.error(f"Admin routes: {e}")


# ========== MAIN ==========

if __name__ == "__main__":
    from database import init_db, init_lid_tables
    init_db()
    init_lid_tables()

    init_admin_routes()

    # Scheduler
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.error(f"Scheduler: {e}")

    # Webhook sozlash (1 daqiqadan keyin)
    import threading, time
    def setup_wh():
        time.sleep(3)
        import requests
        if TOKEN and WEBHOOK_URL:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/setWebhook",
                json={"url": f"{WEBHOOK_URL}/webhook/main", "drop_pending_updates": True}
            )
            logger.info("Main bot webhook o'rnatildi")
        if LID_TOKEN and WEBHOOK_URL:
            requests.post(
                f"https://api.telegram.org/bot{LID_TOKEN}/setWebhook",
                json={"url": f"{WEBHOOK_URL}/webhook/lid", "drop_pending_updates": True}
            )
            logger.info("Lid bot webhook o'rnatildi")
    threading.Thread(target=setup_wh, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Flask {port} portda ishga tushdi")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
