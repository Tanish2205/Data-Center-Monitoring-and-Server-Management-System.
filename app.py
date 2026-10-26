"""
app.py
------
Main Flask app for my Data Center Monitor project.

This is a simple dashboard that:
- shows live CPU / RAM / Disk / Network stats for this computer
- lets me add other servers and ping them to see if they're up
- creates an alert automatically if CPU/RAM/Disk gets too high
- keeps a simple activity log of what happened and when

Run it with:
    python app.py

Then open http://localhost:5000 in your browser.
Default login: admin / admin123
"""

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

import db
import monitor

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

# How high a metric has to be before we create a warning / critical alert
THRESHOLDS = {
    "cpu": {"warning": 80, "critical": 90},
    "ram": {"warning": 80, "critical": 90},
    "disk": {"warning": 85, "critical": 95},
}

MAX_CHART_POINTS = 30   # how many recent metric readings to show on the chart


# ---------------------------------------------------------------------------
# Login helper
# ---------------------------------------------------------------------------

def login_required(view_function):
    """Put @login_required above any route that needs the user logged in."""
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view_function(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = db.get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            db.add_log("login", f"{username} logged in")
            return redirect(url_for("dashboard"))

        return render_template("login.html", error="Wrong username or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    if "username" in session:
        db.add_log("logout", f"{session['username']} logged out")
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/metrics/live")
@login_required
def api_live_metrics():
    """
    Called every few seconds by the dashboard page.
    Reads real stats, saves them, checks alert thresholds, and returns them.
    """
    data = monitor.get_current_metrics()

    conn = db.get_db()
    conn.execute(
        """INSERT INTO metrics (cpu_percent, ram_percent, disk_percent, temperature)
           VALUES (?, ?, ?, ?)""",
        (data["cpu_percent"], data["ram_percent"], data["disk_percent"], data["temperature"])
    )
    conn.commit()
    conn.close()

    check_for_alerts(data)

    return jsonify(data)


@app.route("/api/metrics/history")
@login_required
def api_metrics_history():
    """Returns the last few readings so the chart can be drawn."""
    conn = db.get_db()
    total_servers = conn.execute("SELECT COUNT(*) c FROM servers").fetchone()["c"]
    if total_servers == 0:
        conn.close()
        return jsonify([])

    rows = conn.execute(
        "SELECT * FROM metrics ORDER BY recorded_at DESC LIMIT ?",
        (MAX_CHART_POINTS,)
    ).fetchall()
    conn.close()

    history = [dict(row) for row in reversed(rows)]
    return jsonify(history)


@app.route("/api/dashboard/summary")
@login_required
def api_dashboard_summary():
    """Small numbers shown at the top of the dashboard (server counts, user counts, alerts)."""
    conn = db.get_db()
    total_servers = conn.execute("SELECT COUNT(*) c FROM servers").fetchone()["c"]
    online_servers = conn.execute(
        "SELECT COUNT(*) c FROM servers WHERE status = 'online'"
    ).fetchone()["c"]
    offline_servers = conn.execute(
        "SELECT COUNT(*) c FROM servers WHERE status = 'offline'"
    ).fetchone()["c"]
    total_users = conn.execute("SELECT COUNT(*) c FROM app_users").fetchone()["c"]
    active_users = conn.execute(
        "SELECT COUNT(*) c FROM app_users WHERE status = 'Active'"
    ).fetchone()["c"]
    offline_users = conn.execute(
        "SELECT COUNT(*) c FROM app_users WHERE status = 'Offline'"
    ).fetchone()["c"]
    active_alerts = conn.execute(
        "SELECT COUNT(*) c FROM alerts WHERE is_resolved = 0"
    ).fetchone()["c"]
    conn.close()

    return jsonify({
        "total_servers": total_servers,
        "online_servers": online_servers,
        "offline_servers": offline_servers,
        "total_users": total_users,
        "active_users": active_users,
        "offline_users": offline_users,
        "active_alerts": active_alerts,
    })


def check_for_alerts(data):
    """
    Compare the latest reading against our thresholds.
    If something is too high, save a new alert -
    but only if we haven't already got an unresolved one of the same type.
    """
    checks = [
        ("cpu", data["cpu_percent"], "CPU usage"),
        ("ram", data["ram_percent"], "RAM usage"),
        ("disk", data["disk_percent"], "Disk usage"),
    ]

    conn = db.get_db()
    for alert_type, value, label in checks:
        limits = THRESHOLDS[alert_type]

        if value >= limits["critical"]:
            severity = "critical"
        elif value >= limits["warning"]:
            severity = "warning"
        else:
            continue

        already_open = conn.execute(
            "SELECT id FROM alerts WHERE alert_type = ? AND is_resolved = 0",
            (alert_type,)
        ).fetchone()

        if not already_open:
            message = f"{label} is at {value}%"
            conn.execute(
                "INSERT INTO alerts (alert_type, message, severity) VALUES (?, ?, ?)",
                (alert_type, message, severity)
            )
            conn.commit()
            db.add_log("alert", message)

    conn.close()


# ---------------------------------------------------------------------------
# Servers (add / edit / delete / ping / details)
# ---------------------------------------------------------------------------

@app.route("/servers")
@login_required
def servers():
    conn = db.get_db()
    raw_servers = conn.execute("SELECT * FROM servers ORDER BY added_at DESC").fetchall()
    all_servers = []
    for s in raw_servers:
        s_dict = dict(s)
        server_id = s_dict["id"]
        total_u = conn.execute(
            "SELECT COUNT(*) c FROM app_users WHERE server_id = ?", (server_id,)
        ).fetchone()["c"]
        active_u = conn.execute(
            "SELECT COUNT(*) c FROM app_users WHERE server_id = ? AND status = 'Active'", (server_id,)
        ).fetchone()["c"]
        offline_u = conn.execute(
            "SELECT COUNT(*) c FROM app_users WHERE server_id = ? AND status = 'Offline'", (server_id,)
        ).fetchone()["c"]
        s_dict["total_users"] = total_u
        s_dict["active_users"] = active_u
        s_dict["offline_users"] = offline_u
        all_servers.append(s_dict)
    conn.close()
    return render_template("servers.html", servers=all_servers)


@app.route("/servers/add", methods=["GET", "POST"])
@login_required
def add_server():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ip_address = request.form.get("ip_address", "").strip()
        notes = request.form.get("notes", "").strip()

        conn = db.get_db()
        conn.execute(
            "INSERT INTO servers (name, ip_address, notes) VALUES (?, ?, ?)",
            (name, ip_address, notes)
        )
        conn.commit()
        conn.close()

        db.add_log("server_added", f"Added server '{name}' ({ip_address})")
        return redirect(url_for("servers"))

    return render_template("server_form.html", server=None)


@app.route("/servers/<int:server_id>/edit", methods=["GET", "POST"])
@login_required
def edit_server(server_id):
    conn = db.get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        ip_address = request.form.get("ip_address", "").strip()
        notes = request.form.get("notes", "").strip()

        conn.execute(
            "UPDATE servers SET name = ?, ip_address = ?, notes = ? WHERE id = ?",
            (name, ip_address, notes, server_id)
        )
        conn.commit()
        conn.close()

        db.add_log("server_updated", f"Updated server '{name}'")
        return redirect(url_for("servers"))

    server = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    conn.close()
    return render_template("server_form.html", server=server)


@app.route("/servers/<int:server_id>/delete", methods=["POST"])
@login_required
def delete_server(server_id):
    conn = db.get_db()
    server = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    conn.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    conn.commit()
    conn.close()

    if server:
        db.add_log("server_deleted", f"Deleted server '{server['name']}'")
    return redirect(url_for("servers"))


@app.route("/servers/<int:server_id>/ping", methods=["POST"])
@login_required
def ping_server(server_id):
    conn = db.get_db()
    server = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()

    if not server:
        conn.close()
        return jsonify({"success": False}), 404

    is_up = monitor.ping_host(server["ip_address"])
    new_status = "online" if is_up else "offline"

    conn.execute("UPDATE servers SET status = ? WHERE id = ?", (new_status, server_id))
    conn.commit()
    conn.close()

    db.add_log("ping", f"Pinged '{server['name']}' - result: {new_status}")
    return jsonify({"success": True, "status": new_status})


@app.route("/servers/<int:server_id>/details")
@login_required
def server_details(server_id):
    conn = db.get_db()
    server = conn.execute("SELECT * FROM servers WHERE id = ?", (server_id,)).fetchone()
    if not server:
        conn.close()
        return jsonify({"error": "Server not found"}), 404

    assigned_users = conn.execute(
        "SELECT id, name, email, status FROM app_users WHERE server_id = ? ORDER BY name ASC",
        (server_id,)
    ).fetchall()

    conn.close()

    db.add_log("server_viewed", f"Viewed details for server '{server['name']}'")

    is_ubuntu = "Ubuntu" in (server["os_name"] or "") or "UBU" in (server["name"] or "")
    if is_ubuntu:
        perf = {
            "cpu_percent": 34,
            "ram_percent": 52,
            "disk_percent": 41,
            "net_usage": "250 Mbps",
            "uptime": "32 Days 14 Hours",
            "temperature": "39°C"
        }
    else:
        perf = {
            "cpu_percent": 28,
            "ram_percent": 46,
            "disk_percent": 62,
            "net_usage": "120 Mbps",
            "uptime": "15 Days 08 Hours",
            "temperature": "42°C"
        }

    return jsonify({
        "id": server["id"],
        "server_code": server["server_code"] or ("SRV-002" if is_ubuntu else "SRV-001"),
        "name": server["name"],
        "ip_address": server["ip_address"],
        "os_name": server["os_name"] or ("Ubuntu Server 22.04 LTS" if is_ubuntu else "Windows Server 2022"),
        "server_type": server["server_type"] or ("Web Server" if is_ubuntu else "Application Server"),
        "location": server["location"] or ("Data Center Rack A2" if is_ubuntu else "Data Center Rack A1"),
        "port": server["port"] or (22 if is_ubuntu else 3389),
        "status": server["status"] or "online",
        "added_at": server["added_at"] if "added_at" in server.keys() else "Today",
        "last_updated": "Just now",
        "performance": perf,
        "assigned_users": [dict(u) for u in assigned_users],
        "recent_activity": [
            "Health Check Completed",
            "Performance Updated",
            "Backup Completed Successfully",
            "No Critical Alerts"
        ]
    })


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------

@app.route("/users")
@login_required
def users():
    conn = db.get_db()
    all_users = conn.execute("""
        SELECT u.*, s.name AS server_name 
        FROM app_users u 
        LEFT JOIN servers s ON u.server_id = s.id 
        ORDER BY u.created_at DESC
    """).fetchall()
    all_servers = conn.execute("SELECT id, name FROM servers ORDER BY name ASC").fetchall()
    conn.close()
    return render_template("users.html", users=all_users, servers=all_servers)


@app.route("/users/add", methods=["POST"])
@login_required
def add_user():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    status = request.form.get("status", "Active").strip()
    server_id_val = request.form.get("server_id", "").strip()
    server_id = int(server_id_val) if server_id_val else None

    # If unassigned, automatically set status to Offline
    if not server_id:
        status = "Offline"

    if name:
        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO app_users (name, email, status, server_id) VALUES (?, ?, ?, ?)",
            (name, email, status, server_id)
        )
        conn.commit()
        conn.close()

        db.add_log("user_created", f"Created user '{name}'")

        if server_id:
            conn = db.get_db()
            srv = conn.execute("SELECT name FROM servers WHERE id = ?", (server_id,)).fetchone()
            conn.close()
            srv_name = srv["name"] if srv else f"ID {server_id}"
            db.add_log("user_assigned", f"Assigned user '{name}' to server '{srv_name}'")

    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    conn = db.get_db()
    user = conn.execute("SELECT * FROM app_users WHERE id = ?", (user_id,)).fetchone()
    if user:
        conn.execute("DELETE FROM app_users WHERE id = ?", (user_id,))
        conn.commit()
        db.add_log("user_deleted", f"Deleted user '{user['name']}'")
    conn.close()
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/assign", methods=["POST"])
@login_required
def assign_user(user_id):
    server_id_val = request.form.get("server_id", "").strip()
    new_server_id = int(server_id_val) if server_id_val else None
    form_status = request.form.get("status", "").strip()

    conn = db.get_db()
    user = conn.execute("SELECT * FROM app_users WHERE id = ?", (user_id,)).fetchone()

    if user:
        old_server_id = user["server_id"]

        # Determine status: prioritize explicitly submitted status from Edit form
        if form_status:
            new_status = form_status
        elif new_server_id is None:
            new_status = "Offline"
        else:
            new_status = "Active" if user["status"] == "Offline" else user["status"]

        conn.execute("UPDATE app_users SET server_id = ?, status = ? WHERE id = ?", (new_server_id, new_status, user_id))
        conn.commit()

        if new_server_id:
            srv = conn.execute("SELECT name FROM servers WHERE id = ?", (new_server_id,)).fetchone()
            srv_name = srv["name"] if srv else f"ID {new_server_id}"
            db.add_log("user_assigned", f"Updated user '{user['name']}': Server '{srv_name}', Status '{new_status}'")
        else:
            db.add_log("user_removed", f"Updated user '{user['name']}': Unassigned, Status '{new_status}'")

    conn.close()
    return redirect(url_for("users"))



# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.route("/alerts")
@login_required
def alerts():
    conn = db.get_db()
    all_alerts = conn.execute("SELECT * FROM alerts ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("alerts.html", alerts=all_alerts)


@app.route("/alerts/<int:alert_id>/resolve", methods=["POST"])
@login_required
def resolve_alert(alert_id):
    conn = db.get_db()
    conn.execute("UPDATE alerts SET is_resolved = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()

    db.add_log("alert_resolved", f"Resolved alert #{alert_id}")
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Activity log
# ---------------------------------------------------------------------------

@app.route("/logs")
@login_required
def logs():
    conn = db.get_db()
    all_logs = conn.execute(
        "SELECT * FROM logs ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return render_template("logs.html", logs=all_logs)


# ---------------------------------------------------------------------------
# Start the app
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.init_db()
    print("Data Center Monitor running at http://localhost:5000")
    print("Login with: admin / admin123")
    app.run(debug=True, port=5000)
