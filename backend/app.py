"""
ARIA Backend - Flask app

Endpoints:
  POST /api/readings        <- ESP32 posts sensor data here
  GET  /api/readings/latest <- dashboard polls latest reading
  GET  /api/readings/history<- dashboard fetches history for charts
  GET  /api/commands        <- ESP32 polls for manual/remote overrides
  POST /api/commands        <- dashboard sends LED/fan override commands (auth required)
  POST /api/login           <- simple session-based login
  POST /api/logout
  GET  /api/status          <- auth check / health check

Run with:  python app.py
Backend will be reachable at http://<your-local-ip>:5000
and, once configured, at http://aria.local:5000 via mDNS.
"""

from flask import Flask, request, jsonify, session, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import os

import database as db

# The UI is a single static page in ui/index.html (no build step needed).
# Flask serves it directly so the whole system is one server on one port.
FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")

app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path="")
app.secret_key = os.environ.get("ARIA_SECRET_KEY", "aria-project-2026-xyz")
CORS(app, supports_credentials=True)

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "aria123"  # CHANGE THIS before any real deployment


def require_login():
    return session.get("logged_in", False)


def seed_default_user():
    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (DEFAULT_USERNAME,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (DEFAULT_USERNAME, generate_password_hash(DEFAULT_PASSWORD))
            )


# ---------------- AUTH ----------------

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()

    with db.get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE LOWER(username) = ?", (username,)).fetchone()

    if row and check_password_hash(row["password_hash"], password):
        session["logged_in"] = True
        session["username"] = username
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Invalid credentials"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({"logged_in": require_login()})


# ---------------- SENSOR READINGS (ESP32 -> backend) ----------------

@app.route("/api/readings", methods=["POST"])
def post_readings():
    # NOTE: no auth on this route since it's the ESP32 posting from the
    # trusted local network. If exposing this beyond LAN/Tailscale, add
    # a shared-secret header check here.
    data = request.get_json(force=True)
    db.insert_reading(data)
    return jsonify({"success": True})


@app.route("/api/readings/latest", methods=["GET"])
def latest_reading():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    reading = db.get_latest_reading()
    return jsonify(reading or {})


@app.route("/api/readings/history", methods=["GET"])
def history():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    limit = request.args.get("limit", default=200, type=int)
    return jsonify(db.get_history(limit))


# ---------------- COMMANDS (dashboard -> ESP32) ----------------

@app.route("/api/commands", methods=["GET"])
def get_commands():
    # Polled by the ESP32 -- no auth (trusted local network / same reasoning as above)
    return jsonify(db.get_commands())


@app.route("/api/commands", methods=["POST"])
def set_commands():
    if not require_login():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(force=True)
    db.set_commands(led=data.get("led"), fan=data.get("fan"))
    return jsonify({"success": True})


# ---------------- SERVE FRONTEND ----------------

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    # Never intercept API routes with this catch-all
    if path.startswith("api/"):
        return jsonify({"error": "not found"}), 404

    full_path = os.path.join(FRONTEND_DIST, path)
    if path and os.path.exists(full_path):
        return send_from_directory(FRONTEND_DIST, path)

    # Fallback to index.html (covers the root URL and any client-side route)
    if not os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return (
            "UI not found. Put index.html inside the ui/ folder next to app.py.",
            200,
        )
    return send_from_directory(FRONTEND_DIST, "index.html")


# ---------------- RETENTION JOB ----------------

def start_scheduler():
    db.cleanup_old_readings()
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=db.cleanup_old_readings, trigger="interval", hours=24)
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown())


# ---------------- mDNS REGISTRATION (aria.local) ----------------

def register_mdns():
    """
    Registers this machine as 'aria.local' on the network so the ESP32
    (and browsers) can find it without needing to know its IP address.
    Requires: pip install zeroconf
    """
    try:
        import socket
        from zeroconf import Zeroconf, ServiceInfo

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Connect to a public IP to force the OS to pick the default outbound interface
            s.connect(('8.8.8.8', 80))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = socket.gethostbyname(socket.gethostname())
        finally:
            s.close()

        zeroconf = Zeroconf()
        info = ServiceInfo(
            "_http._tcp.local.",
            "ARIA Backend._http._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=5000,
            server="aria.local.",
        )
        zeroconf.register_service(info)
        print(f"mDNS registered: aria.local -> {local_ip}")
        return zeroconf
    except Exception as e:
        print(f"mDNS registration skipped (non-fatal): {e}")
        return None


if __name__ == "__main__":
    db.init_db()
    seed_default_user()
    start_scheduler()
    _zc = register_mdns()
    app.run(host="0.0.0.0", port=5000, debug=False)